"""The fixed walkthrough: run every required case against fresh state and prove each outcome.

This runner is deliberately not a tool. It has no target option, no property list, no fixture
argument, and no way to point it anywhere but the two Compose service names below. It executes one
fixed script against one fictional local claim and exits nonzero the moment an expected status, key
set, audit event, or state diff is missing.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

import httpx

from fieldblind.domain import (
    CANONICAL_PROPERTY_ORDER,
    CLAIM_FIXTURE,
    DEMO_LABEL,
    EMPLOYEE_VISIBLE_PROPERTIES,
    REVIEWER_ONLY_PROPERTIES,
)
from fieldblind.errors import STATUS_INVALID_REQUEST, STATUS_NOT_FOUND, STATUS_OK

if TYPE_CHECKING:
    from collections.abc import Sequence

#: The only two places this runner ever talks to. They are Compose service names, so the runner
#: cannot reach anything outside its own project network even if someone tried.
SECURE_BASE_URL: Final = "http://secure:8000"
VULNERABLE_BASE_URL: Final = "http://vulnerable:8000"

CLAIM_PATH: Final = f"/claims/{CLAIM_FIXTURE.claim_id}"
STATE_PATH: Final = f"/demo/state/{CLAIM_FIXTURE.claim_id}"
RESET_PATH: Final = "/demo/reset"
EVENTS_PATH: Final = "/demo/events"

NIKO_CREDENTIAL: Final = "fictional-demo-token-niko"
UMA_CREDENTIAL: Final = "fictional-demo-token-uma"
SOL_CREDENTIAL: Final = "fictional-demo-token-sol"

REVISED_PURPOSE: Final = "Team offsite ferry catering (revised)"
MIXED_BODY: Final[dict[str, Any]] = {
    "purpose": REVISED_PURPOSE,
    "decision": "approved",
    "approved_amount_cents": CLAIM_FIXTURE.amount_cents,
}
REQUEST_TIMEOUT_SECONDS: Final = 10.0


class Mode(StrEnum):
    """The enumerated local modes. Nothing else is accepted."""

    FULL = "full"
    SECURE = "secure"
    VULNERABLE = "vulnerable"


@dataclass(frozen=True, slots=True)
class CaseResult:
    """One walkthrough case and everything the reader needs to judge it."""

    name: str
    actor: str
    object_verdict: str
    property_verdict: str
    http_outcome: str
    response_keys: tuple[str, ...]
    state_diff: tuple[str, ...]
    passed: bool
    failures: tuple[str, ...] = ()


@dataclass(slots=True)
class WalkthroughReport:
    """Every executed case, and whether the whole walkthrough held."""

    mode: Mode
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Report whether every executed case met every expectation."""
        return bool(self.cases) and all(case.passed for case in self.cases)


def _auth(credential: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {credential}"}


def _state(client: httpx.Client) -> dict[str, Any]:
    response = client.get(STATE_PATH)
    response.raise_for_status()
    claim: dict[str, Any] = response.json()["claim"]
    return claim


def _state_text(client: httpx.Client) -> str:
    response = client.get(STATE_PATH)
    response.raise_for_status()
    return response.text


def _rejection_count(client: httpx.Client) -> int:
    response = client.get(EVENTS_PATH)
    response.raise_for_status()
    events: list[dict[str, Any]] = response.json()["events"]
    return sum(1 for event in events if event["event"] == "property_update_rejected")


def _reset(client: httpx.Client) -> None:
    client.post(RESET_PATH).raise_for_status()


def _diff(before: dict[str, Any], after: dict[str, Any]) -> tuple[str, ...]:
    return tuple(name for name in CANONICAL_PROPERTY_ORDER if before[name] != after[name])


def vulnerable_read_disclosure(vulnerable: httpx.Client) -> CaseResult:
    """The owning employee reads their own claim and receives the reviewer's private view."""
    _reset(vulnerable)
    before = _state(vulnerable)
    response = vulnerable.get(CLAIM_PATH, headers=_auth(NIKO_CREDENTIAL))
    keys = tuple(response.json()) if response.status_code == STATUS_OK else ()

    failures: list[str] = []
    if response.status_code != STATUS_OK:
        failures.append(f"expected 200, got {response.status_code}")
    leaked = set(keys) - set(EMPLOYEE_VISIBLE_PROPERTIES)
    if leaked != set(REVIEWER_ONLY_PROPERTIES):
        failures.append(f"expected only the reviewer-only properties to leak, got {sorted(leaked)}")
    for name in REVIEWER_ONLY_PROPERTIES:
        if name in keys and response.json()[name] != getattr(CLAIM_FIXTURE, name):
            failures.append(f"{name} did not carry its fixed fictional value")
    return CaseResult(
        name="vulnerable read disclosure",
        actor="niko (employee, owner)",
        object_verdict="allowed — niko owns EXP-204",
        property_verdict="none applied — the whole object was serialized",
        http_outcome=f"{response.status_code}",
        response_keys=keys,
        state_diff=_diff(before, _state(vulnerable)),
        passed=not failures,
        failures=tuple(failures),
    )


def secure_read_projection(secure: httpx.Client) -> CaseResult:
    """The identical request to the secure service, plus the reviewer's legitimate read."""
    _reset(secure)
    before = _state(secure)
    employee = secure.get(CLAIM_PATH, headers=_auth(NIKO_CREDENTIAL))
    reviewer = secure.get(CLAIM_PATH, headers=_auth(SOL_CREDENTIAL))
    keys = tuple(employee.json()) if employee.status_code == STATUS_OK else ()

    failures: list[str] = []
    if employee.status_code != STATUS_OK:
        failures.append(f"expected 200 for the employee, got {employee.status_code}")
    if keys != EMPLOYEE_VISIBLE_PROPERTIES:
        failures.append(f"expected exactly the employee projection, got {list(keys)}")
    for name in REVIEWER_ONLY_PROPERTIES:
        if name in employee.text:
            failures.append(f"{name} appeared in the employee response")
        value = getattr(CLAIM_FIXTURE, name)
        if value is not None and str(value) in employee.text:
            failures.append(f"the value of {name} appeared in the employee response")
    if reviewer.status_code != STATUS_OK or tuple(reviewer.json()) != CANONICAL_PROPERTY_ORDER:
        failures.append("the reviewer did not receive the full review projection")
    return CaseResult(
        name="secure read projection",
        actor="niko (employee, owner), then sol (reviewer)",
        object_verdict="allowed for both",
        property_verdict="employee schema for niko, reviewer schema for sol",
        http_outcome=f"{employee.status_code} employee / {reviewer.status_code} reviewer",
        response_keys=keys,
        state_diff=_diff(before, _state(secure)),
        passed=not failures,
        failures=tuple(failures),
    )


def vulnerable_mass_assignment(vulnerable: httpx.Client) -> CaseResult:
    """One ordinary-looking edit, with two reviewer-only keys along for the ride."""
    _reset(vulnerable)
    before = _state(vulnerable)
    response = vulnerable.patch(CLAIM_PATH, headers=_auth(NIKO_CREDENTIAL), json=MIXED_BODY)
    after = _state(vulnerable)
    diff = _diff(before, after)

    failures: list[str] = []
    if response.status_code != STATUS_OK:
        failures.append(f"expected 200, got {response.status_code}")
    if set(diff) != {"purpose", "decision", "approved_amount_cents"}:
        failures.append(f"expected all three properties to change, changed {list(diff)}")
    if after["decision"] != "approved":
        failures.append("the employee did not manage to approve their own claim")
    if after["approved_amount_cents"] != CLAIM_FIXTURE.amount_cents:
        failures.append("the employee did not manage to set the approved amount")
    return CaseResult(
        name="vulnerable mass assignment",
        actor="niko (employee, owner)",
        object_verdict="allowed — niko owns EXP-204",
        property_verdict="none applied — every submitted key was bound",
        http_outcome=f"{response.status_code}",
        response_keys=tuple(response.json()) if response.status_code == STATUS_OK else (),
        state_diff=diff,
        passed=not failures,
        failures=tuple(failures),
    )


def secure_whole_request_rejection(secure: httpx.Client) -> CaseResult:
    """The identical bytes, refused whole, with the state untouched to the byte."""
    _reset(secure)
    before_text = _state_text(secure)
    before = _state(secure)
    rejections_before = _rejection_count(secure)
    response = secure.patch(CLAIM_PATH, headers=_auth(NIKO_CREDENTIAL), json=MIXED_BODY)
    after_text = _state_text(secure)
    after = _state(secure)
    emitted = _rejection_count(secure)

    failures: list[str] = []
    if rejections_before != 0:
        failures.append("the reset did not clear the audit history")
    if response.status_code != STATUS_INVALID_REQUEST:
        failures.append(f"expected 400, got {response.status_code}")
    if after_text != before_text:
        failures.append("canonical state changed")
    if after["purpose"] != CLAIM_FIXTURE.purpose:
        failures.append("the authorized part of the mixed body was applied")
    if emitted != 1:
        failures.append(f"expected exactly one audit event, saw {emitted}")
    for name in (*REVIEWER_ONLY_PROPERTIES, "purpose"):
        if name in response.text:
            failures.append(f"the rejection named {name}")
    return CaseResult(
        name="secure whole-request rejection",
        actor="niko (employee, owner)",
        object_verdict="allowed — niko owns EXP-204",
        property_verdict="refused — the body named properties niko may not write",
        http_outcome=f"{response.status_code} generic, {emitted} audit event",
        response_keys=tuple(response.json()),
        state_diff=_diff(before, after),
        passed=not failures,
        failures=tuple(failures),
    )


def secure_legitimate_employee_edit(secure: httpx.Client) -> CaseResult:
    """The fix did not take anything away: the edit niko may make still works."""
    _reset(secure)
    before = _state(secure)
    response = secure.patch(
        CLAIM_PATH,
        headers=_auth(NIKO_CREDENTIAL),
        json={"purpose": REVISED_PURPOSE},
    )
    after = _state(secure)
    diff = _diff(before, after)

    failures: list[str] = []
    if response.status_code != STATUS_OK:
        failures.append(f"expected 200, got {response.status_code}")
    if diff != ("purpose",):
        failures.append(f"expected only purpose to change, changed {list(diff)}")
    for name in REVIEWER_ONLY_PROPERTIES:
        if after[name] != getattr(CLAIM_FIXTURE, name):
            failures.append(f"{name} was not preserved")
    return CaseResult(
        name="secure legitimate employee edit",
        actor="niko (employee, owner)",
        object_verdict="allowed — niko owns EXP-204",
        property_verdict="allowed — purpose is niko's to change",
        http_outcome=f"{response.status_code}",
        response_keys=tuple(response.json()) if response.status_code == STATUS_OK else (),
        state_diff=diff,
        passed=not failures,
        failures=tuple(failures),
    )


def secure_legitimate_reviewer_decision(secure: httpx.Client) -> CaseResult:
    """And the reviewer can still do the job the reviewer-only properties exist for."""
    _reset(secure)
    before = _state(secure)
    read = secure.get(CLAIM_PATH, headers=_auth(SOL_CREDENTIAL))
    response = secure.patch(
        CLAIM_PATH,
        headers=_auth(SOL_CREDENTIAL),
        json={"decision": "approved", "approved_amount_cents": CLAIM_FIXTURE.amount_cents},
    )
    after = _state(secure)
    diff = _diff(before, after)

    failures: list[str] = []
    if read.status_code != STATUS_OK or tuple(read.json()) != CANONICAL_PROPERTY_ORDER:
        failures.append("the reviewer could not read the review projection")
    if response.status_code != STATUS_OK:
        failures.append(f"expected 200, got {response.status_code}")
    if set(diff) != {"decision", "approved_amount_cents"}:
        failures.append(f"expected only the decision properties to change, changed {list(diff)}")
    return CaseResult(
        name="secure legitimate reviewer decision",
        actor="sol (reviewer)",
        object_verdict="allowed — reviewers may access the claim",
        property_verdict="allowed — the decision properties are sol's to set",
        http_outcome=f"{read.status_code} read / {response.status_code} decide",
        response_keys=tuple(response.json()) if response.status_code == STATUS_OK else (),
        state_diff=diff,
        passed=not failures,
        failures=tuple(failures),
    )


def object_level_control(client: httpx.Client, variant: str) -> CaseResult:
    """The negative control: the deliberate flaw is property-level, not object-level."""
    _reset(client)
    before_text = _state_text(client)
    before = _state(client)
    read = client.get(CLAIM_PATH, headers=_auth(UMA_CREDENTIAL))
    write = client.patch(CLAIM_PATH, headers=_auth(UMA_CREDENTIAL), json=MIXED_BODY)
    after_text = _state_text(client)

    failures: list[str] = []
    for label, response in (("read", read), ("write", write)):
        if response.status_code != STATUS_NOT_FOUND:
            failures.append(f"expected 404 on {label}, got {response.status_code}")
        for name in CANONICAL_PROPERTY_ORDER:
            if name in response.text:
                failures.append(f"the {label} refusal named {name}")
    if after_text != before_text:
        failures.append("canonical state changed")
    return CaseResult(
        name=f"object-level control ({variant})",
        actor="uma (employee, not the owner)",
        object_verdict="refused — uma does not own EXP-204",
        property_verdict="never reached",
        http_outcome=f"{read.status_code} read / {write.status_code} write",
        response_keys=tuple(read.json()),
        state_diff=_diff(before, _state(client)),
        passed=not failures,
        failures=tuple(failures),
    )


def run_walkthrough(
    secure_base_url: str,
    vulnerable_base_url: str,
    mode: Mode = Mode.FULL,
) -> WalkthroughReport:
    """Execute the fixed script for one mode and return every case result."""
    report = WalkthroughReport(mode=mode)
    with (
        httpx.Client(base_url=secure_base_url, timeout=REQUEST_TIMEOUT_SECONDS) as secure,
        httpx.Client(base_url=vulnerable_base_url, timeout=REQUEST_TIMEOUT_SECONDS) as vulnerable,
    ):
        if mode in (Mode.FULL, Mode.VULNERABLE):
            report.cases.append(vulnerable_read_disclosure(vulnerable))
        if mode in (Mode.FULL, Mode.SECURE):
            report.cases.append(secure_read_projection(secure))
        if mode in (Mode.FULL, Mode.VULNERABLE):
            report.cases.append(vulnerable_mass_assignment(vulnerable))
        if mode in (Mode.FULL, Mode.SECURE):
            report.cases.append(secure_whole_request_rejection(secure))
            report.cases.append(secure_legitimate_employee_edit(secure))
            report.cases.append(secure_legitimate_reviewer_decision(secure))
            report.cases.append(object_level_control(secure, "secure"))
        if mode in (Mode.FULL, Mode.VULNERABLE):
            report.cases.append(object_level_control(vulnerable, "vulnerable"))
    return report


def render(report: WalkthroughReport) -> str:
    """Render the report so a reader can judge every case without reading source."""
    lines = [
        f"fieldblind walkthrough — {DEMO_LABEL} — mode: {report.mode.value}",
        f"claim {CLAIM_FIXTURE.claim_id}, every value below is fictional demonstration data",
        "",
    ]
    for case in report.cases:
        lines.append(f"[{'PASS' if case.passed else 'FAIL'}] {case.name}")
        lines.append(f"    actor            : {case.actor}")
        lines.append(f"    object verdict   : {case.object_verdict}")
        lines.append(f"    property verdict : {case.property_verdict}")
        lines.append(f"    http outcome     : {case.http_outcome}")
        lines.append(f"    response keys    : {', '.join(case.response_keys) or '(none)'}")
        lines.append(f"    state diff       : {', '.join(case.state_diff) or '(unchanged)'}")
        lines.extend(f"    !! {failure}" for failure in case.failures)
        lines.append("")
    passed = sum(1 for case in report.cases if case.passed)
    verdict = "WALKTHROUGH PASSED" if report.passed else "WALKTHROUGH FAILED"
    lines.append(f"{verdict} — {passed}/{len(report.cases)} cases met every expectation")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the fixed walkthrough against the Compose services and report success as an exit code."""
    parser = argparse.ArgumentParser(
        prog="fieldblind-walkthrough",
        description="Run the fixed local fieldblind walkthrough. Local demonstration only.",
    )
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in Mode],
        default=Mode.FULL.value,
        help="which enumerated local mode to run",
    )
    arguments = parser.parse_args(argv)
    report = run_walkthrough(SECURE_BASE_URL, VULNERABLE_BASE_URL, Mode(arguments.mode))
    print(render(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
