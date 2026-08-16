"""Containment: the two-action opt-in, the container hardening boundary, and no egress."""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any

import pytest
import yaml

from fieldblind.config import ALLOW_VULNERABLE_VARIABLE, Settings
from fieldblind.persistence import create_database_engine, reset_state
from fieldblind.vulnerable_app import VulnerableDemoNotEnabledError, create_vulnerable_app

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# Compose mount targets, not host temporary paths.
EXPECTED_TMPFS_TARGETS = {"/state", "/tmp"}  # noqa: S108

#: The unprivileged user baked into the image, which the state mount must belong to.
IMAGE_UID = "10001"

SECURE_PORT = "127.0.0.1:8000:8000"
VULNERABLE_PORT = "127.0.0.1:8001:8000"

#: A public address the demo must not be able to reach from inside its container.
EGRESS_PROBE = ("1.1.1.1", 443)
EGRESS_TIMEOUT_SECONDS = 3.0


def _compose() -> dict[str, Any]:
    document: dict[str, Any] = yaml.safe_load(
        (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8"),
    )
    return document


def _services() -> dict[str, Any]:
    services: dict[str, Any] = _compose()["services"]
    return services


SERVICE_NAMES = ["secure", "vulnerable", "verify"]


# --- the two-action opt-in ------------------------------------------------------------------


def test_the_vulnerable_app_refuses_to_start_without_the_flag(tmp_path: Path) -> None:
    with pytest.raises(VulnerableDemoNotEnabledError):
        create_vulnerable_app(Settings(database_path=tmp_path / "blocked.db"))


def test_the_vulnerable_app_refuses_by_default(tmp_path: Path) -> None:
    """The flag defaults to off, so forgetting it fails closed rather than open."""
    assert Settings(database_path=tmp_path / "x.db").allow_vulnerable_demo is False


@pytest.mark.parametrize(
    "value",
    ["", "false", "TRUE", "True", "yes", "1", "true "],
)
def test_only_the_exact_flag_value_enables_the_vulnerable_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    value: str,
) -> None:
    monkeypatch.setenv(ALLOW_VULNERABLE_VARIABLE, value)
    monkeypatch.setenv("FIELDBLIND_DB_PATH", str(tmp_path / "env.db"))
    assert Settings.from_environment().allow_vulnerable_demo is False


def test_the_exact_flag_value_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(ALLOW_VULNERABLE_VARIABLE, "true")
    monkeypatch.setenv("FIELDBLIND_DB_PATH", str(tmp_path / "env.db"))
    assert Settings.from_environment().allow_vulnerable_demo is True


def test_the_vulnerable_service_is_behind_a_compose_profile() -> None:
    """A plain `docker compose up` must never start it."""
    assert _services()["vulnerable"]["profiles"] == ["vulnerable"]


def test_the_secure_service_is_the_only_default_service() -> None:
    """Every other service needs a profile, so `docker compose up` starts the secure one alone."""
    defaults = [name for name, spec in _services().items() if not spec.get("profiles")]
    assert defaults == ["secure"]


def test_compose_never_enables_the_vulnerable_flag_itself() -> None:
    """The flag comes from the host environment; nothing in the file turns it on."""
    vulnerable_env = _services()["vulnerable"]["environment"]
    assert vulnerable_env[ALLOW_VULNERABLE_VARIABLE].startswith(f"${{{ALLOW_VULNERABLE_VARIABLE}")
    for name in ("secure", "verify"):
        assert ALLOW_VULNERABLE_VARIABLE not in _services()[name].get("environment", {})


# --- the container hardening boundary -------------------------------------------------------


@pytest.mark.parametrize("name", SERVICE_NAMES)
def test_every_container_drops_all_capabilities(name: str) -> None:
    assert _services()[name]["cap_drop"] == ["ALL"]


@pytest.mark.parametrize("name", SERVICE_NAMES)
def test_every_container_forbids_privilege_escalation(name: str) -> None:
    assert "no-new-privileges:true" in _services()[name]["security_opt"]


@pytest.mark.parametrize("name", SERVICE_NAMES)
def test_every_container_has_a_read_only_root_filesystem(name: str) -> None:
    assert _services()[name]["read_only"] is True


def _tmpfs_targets(name: str) -> set[str]:
    return {str(entry).split(":", maxsplit=1)[0] for entry in _services()[name]["tmpfs"]}


@pytest.mark.parametrize("name", SERVICE_NAMES)
def test_every_container_keeps_its_state_in_tmpfs(name: str) -> None:
    assert _tmpfs_targets(name) == EXPECTED_TMPFS_TARGETS


@pytest.mark.parametrize("name", SERVICE_NAMES)
def test_the_state_mount_belongs_to_the_unprivileged_user(name: str) -> None:
    """A tmpfs takes the covered directory's mode and resets ownership to root, so say the ids."""
    state = next(entry for entry in _services()[name]["tmpfs"] if entry.startswith("/state"))
    assert f"uid={IMAGE_UID}" in state
    assert f"gid={IMAGE_UID}" in state


@pytest.mark.parametrize("name", SERVICE_NAMES)
def test_every_container_runs_on_the_egress_free_network(name: str) -> None:
    assert _services()[name]["networks"] == ["demo"]


@pytest.mark.parametrize("name", SERVICE_NAMES)
def test_no_container_asks_for_extra_privilege(name: str) -> None:
    service = _services()[name]
    assert "privileged" not in service
    assert "cap_add" not in service
    assert "pid" not in service
    assert "devices" not in service
    assert "volumes" not in service


def test_the_demo_network_cannot_masquerade_traffic_off_the_host() -> None:
    network = _compose()["networks"]["demo"]
    assert network["driver"] == "bridge"
    assert network["driver_opts"]["com.docker.network.bridge.enable_ip_masquerade"] == "false"


def test_the_image_declares_a_non_root_user() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "\nUSER demo\n" in dockerfile
    assert "--uid 10001" in dockerfile


def test_this_container_is_not_running_as_root() -> None:
    """The static declaration above is worth little without the runtime proof beside it."""
    assert os.getuid() != 0


# --- published ports ------------------------------------------------------------------------


def test_the_secure_service_publishes_only_its_loopback_port() -> None:
    assert _services()["secure"]["ports"] == [SECURE_PORT]


def test_the_vulnerable_service_publishes_a_different_loopback_port() -> None:
    assert _services()["vulnerable"]["ports"] == [VULNERABLE_PORT]


def test_the_verification_service_publishes_nothing() -> None:
    assert "ports" not in _services()["verify"]


def test_every_published_port_is_bound_to_loopback() -> None:
    for service in _services().values():
        for mapping in service.get("ports", []):
            assert str(mapping).startswith("127.0.0.1:")


# --- runtime proof --------------------------------------------------------------------------


def _can_reach_an_external_network() -> bool:
    try:
        socket.create_connection(EGRESS_PROBE, timeout=EGRESS_TIMEOUT_SECONDS).close()
    except OSError:
        return False
    return True


def test_the_application_container_has_no_egress() -> None:
    """Proved at runtime, not just declared: nothing here can reach an external network."""
    assert not _can_reach_an_external_network()


def test_the_configured_state_directory_is_actually_writable() -> None:
    """Regression: a read-only rootfs plus a root-owned tmpfs stopped the service from booting.

    The suite keeps its own fixtures elsewhere, so nothing else here touches the deployed state
    path. This exercises it with the same code the services use at startup.
    """
    settings = Settings.from_environment()
    reset_state(create_database_engine(settings.database_path))
    assert settings.database_path.exists()
