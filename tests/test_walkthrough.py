"""The walkthrough runner: it proves every required case, and it actually notices when one fails."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from fieldblind.domain import DEMO_LABEL
from fieldblind.walkthrough import (
    SECURE_BASE_URL,
    VULNERABLE_BASE_URL,
    Mode,
    main,
    render,
    run_walkthrough,
)

if TYPE_CHECKING:
    from tests.conftest import LoopbackService

EXPECTED_CASE_NAMES = (
    "vulnerable read disclosure",
    "secure read projection",
    "vulnerable mass assignment",
    "secure whole-request rejection",
    "secure legitimate employee edit",
    "secure legitimate reviewer decision",
    "object-level control (secure)",
    "object-level control (vulnerable)",
)

ARGPARSE_EXIT_CODE = 2


def _urls(service: LoopbackService, vulnerable_service: LoopbackService) -> tuple[str, str]:
    return (str(service.client.base_url), str(vulnerable_service.client.base_url))


def test_the_full_walkthrough_passes(
    service: LoopbackService,
    vulnerable_service: LoopbackService,
) -> None:
    secure_url, vulnerable_url = _urls(service, vulnerable_service)
    report = run_walkthrough(secure_url, vulnerable_url, Mode.FULL)
    assert report.passed, render(report)


def test_the_full_walkthrough_runs_every_required_case(
    service: LoopbackService,
    vulnerable_service: LoopbackService,
) -> None:
    secure_url, vulnerable_url = _urls(service, vulnerable_service)
    report = run_walkthrough(secure_url, vulnerable_url, Mode.FULL)
    assert tuple(case.name for case in report.cases) == EXPECTED_CASE_NAMES


@pytest.mark.parametrize("mode", [Mode.SECURE, Mode.VULNERABLE])
def test_each_enumerated_mode_passes(
    service: LoopbackService,
    vulnerable_service: LoopbackService,
    mode: Mode,
) -> None:
    secure_url, vulnerable_url = _urls(service, vulnerable_service)
    report = run_walkthrough(secure_url, vulnerable_url, mode)
    assert report.cases
    assert report.passed, render(report)


def test_the_runner_fails_when_the_vulnerable_cases_cannot_hold(
    service: LoopbackService,
) -> None:
    """Point it at a service that refuses to leak, and it must say so rather than pass."""
    secure_url = str(service.client.base_url)
    report = run_walkthrough(secure_url, secure_url, Mode.VULNERABLE)
    assert not report.passed
    failed = [case.name for case in report.cases if not case.passed]
    assert "vulnerable read disclosure" in failed
    assert "vulnerable mass assignment" in failed


def test_the_runner_fails_when_the_secure_cases_cannot_hold(
    vulnerable_service: LoopbackService,
) -> None:
    """And the other way round: a leaking service must not pass the secure cases."""
    vulnerable_url = str(vulnerable_service.client.base_url)
    report = run_walkthrough(vulnerable_url, vulnerable_url, Mode.SECURE)
    assert not report.passed
    failed = [case.name for case in report.cases if not case.passed]
    assert "secure read projection" in failed
    assert "secure whole-request rejection" in failed


def test_a_failing_case_reports_why(service: LoopbackService) -> None:
    secure_url = str(service.client.base_url)
    report = run_walkthrough(secure_url, secure_url, Mode.VULNERABLE)
    for case in report.cases:
        if not case.passed:
            assert case.failures


def test_the_rendered_report_shows_every_required_column(
    service: LoopbackService,
    vulnerable_service: LoopbackService,
) -> None:
    secure_url, vulnerable_url = _urls(service, vulnerable_service)
    rendered = render(run_walkthrough(secure_url, vulnerable_url, Mode.FULL))
    assert DEMO_LABEL in rendered
    for column in ("actor", "object verdict", "property verdict", "http outcome", "response keys"):
        assert column in rendered
    assert "state diff" in rendered
    assert "WALKTHROUGH PASSED" in rendered


def test_the_rendered_report_announces_failure(service: LoopbackService) -> None:
    secure_url = str(service.client.base_url)
    rendered = render(run_walkthrough(secure_url, secure_url, Mode.VULNERABLE))
    assert "WALKTHROUGH FAILED" in rendered
    assert "[FAIL]" in rendered


@pytest.mark.parametrize(
    "argv",
    [
        ["--mode", "nonsense"],
        ["--mode"],
        ["--target", "http://example.invalid"],
        ["--base-url", "http://example.invalid"],
        ["EXP-999"],
        ["--claim", "EXP-999"],
    ],
)
def test_the_runner_rejects_anything_but_its_enumerated_modes(argv: list[str]) -> None:
    """There is no argument that redirects this runner or points it at another object."""
    with pytest.raises(SystemExit) as exit_info:
        main(argv)
    assert exit_info.value.code == ARGPARSE_EXIT_CODE


def test_the_runner_only_knows_the_compose_service_names() -> None:
    assert SECURE_BASE_URL == "http://secure:8000"
    assert VULNERABLE_BASE_URL == "http://vulnerable:8000"
