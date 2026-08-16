"""Structural gates that fail if the secure contracts drift toward generic serialization or binding.

These tests are the deny-by-default guarantee. They do not exercise behavior; they assert that the
code *cannot* start exposing or accepting a property just because somebody added a column.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml

from fieldblind.domain import (
    CANONICAL_PROPERTY_ORDER,
    CLAIM_FIXTURE,
    EMPLOYEE_VISIBLE_PROPERTIES,
    EMPLOYEE_WRITABLE_PROPERTIES,
    REVIEWER_ONLY_PROPERTIES,
    REVIEWER_WRITABLE_PROPERTIES,
)
from fieldblind.persistence import ClaimRecord
from fieldblind.projections import employee_projection, reviewer_projection
from fieldblind.schemas import (
    EMPLOYEE_RESPONSE_KEYS,
    EMPLOYEE_UPDATE_KEYS,
    REVIEWER_RESPONSE_KEYS,
    REVIEWER_UPDATE_KEYS,
    EmployeeClaimResponse,
    EmployeeClaimUpdate,
    ReviewerClaimResponse,
    ReviewerClaimUpdate,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPOSITORY_ROOT / "src" / "fieldblind"
SOURCE_FILES = sorted(PACKAGE_ROOT.glob("*.py"))

PUBLIC_MODELS: list[type[BaseModel]] = [
    EmployeeClaimResponse,
    ReviewerClaimResponse,
    EmployeeClaimUpdate,
    ReviewerClaimUpdate,
]

FORBIDDEN_ITERATION_METHODS = {"items", "keys", "values"}

EXPECTED_EMPLOYEE_RESPONSE_KEYS = frozenset(EMPLOYEE_VISIBLE_PROPERTIES)
EXPECTED_EMPLOYEE_UPDATE_KEYS = frozenset(EMPLOYEE_WRITABLE_PROPERTIES)
EXPECTED_REVIEWER_RESPONSE_KEYS = frozenset(CANONICAL_PROPERTY_ORDER)
EXPECTED_REVIEWER_UPDATE_KEYS = frozenset(REVIEWER_WRITABLE_PROPERTIES)


def _parsed(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_the_package_has_source_files_to_check() -> None:
    assert SOURCE_FILES


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda path: path.name)
def test_no_mapping_is_unpacked_into_a_call(path: Path) -> None:
    """`f(**untrusted)` is how whole-object binding gets in. It is banned outright."""
    for node in ast.walk(_parsed(path)):
        if isinstance(node, ast.Call):
            assert all(keyword.arg is not None for keyword in node.keywords), (
                f"{path.name}: dictionary unpacking into a call is forbidden"
            )


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda path: path.name)
def test_no_dynamic_attribute_assignment(path: Path) -> None:
    """`setattr(claim, key, value)` is mass assignment with extra steps."""
    for node in ast.walk(_parsed(path)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "setattr", (
                f"{path.name}: dynamic attribute assignment is forbidden"
            )


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda path: path.name)
def test_no_key_value_iteration(path: Path) -> None:
    """Iterating a caller-supplied mapping is the other half of whole-object binding."""
    for node in ast.walk(_parsed(path)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in FORBIDDEN_ITERATION_METHODS, (
                f"{path.name}: iterating key/value pairs is forbidden on the secure path"
            )


def test_projections_construct_responses_with_named_properties_only() -> None:
    """Every emitted property is written out by name, so nothing can ride along."""
    response_models = {"EmployeeClaimResponse", "ReviewerClaimResponse"}
    calls = 0
    for node in ast.walk(_parsed(PACKAGE_ROOT / "projections.py")):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in response_models
        ):
            calls += 1
            assert not node.args, "response models must be built from named properties only"
            assert all(keyword.arg is not None for keyword in node.keywords)
    assert calls == len(response_models)


@pytest.mark.parametrize("model", PUBLIC_MODELS, ids=lambda model: model.__name__)
def test_public_models_forbid_unknown_properties(model: type[BaseModel]) -> None:
    assert model.model_config.get("extra") == "forbid"


@pytest.mark.parametrize("model", PUBLIC_MODELS, ids=lambda model: model.__name__)
def test_public_models_are_not_built_from_the_persistence_model(model: type[BaseModel]) -> None:
    """`from_attributes` would let a stored column populate a public contract automatically."""
    assert model.model_config.get("from_attributes") is not True


def test_persistence_columns_match_the_canonical_property_set() -> None:
    columns = tuple(ClaimRecord.__table__.columns.keys())
    assert columns == CANONICAL_PROPERTY_ORDER


def test_employee_contract_excludes_every_reviewer_only_property() -> None:
    assert EMPLOYEE_RESPONSE_KEYS == EXPECTED_EMPLOYEE_RESPONSE_KEYS
    assert EMPLOYEE_RESPONSE_KEYS.isdisjoint(REVIEWER_ONLY_PROPERTIES)
    assert EMPLOYEE_UPDATE_KEYS == EXPECTED_EMPLOYEE_UPDATE_KEYS
    assert EMPLOYEE_UPDATE_KEYS.isdisjoint(REVIEWER_ONLY_PROPERTIES)


def test_reviewer_contract_covers_the_reviewer_properties() -> None:
    assert REVIEWER_RESPONSE_KEYS == EXPECTED_REVIEWER_RESPONSE_KEYS
    assert REVIEWER_UPDATE_KEYS == EXPECTED_REVIEWER_UPDATE_KEYS


def test_a_new_persistence_property_does_not_reach_a_public_contract() -> None:
    """Simulate somebody adding an internal property to the stored claim."""
    claim = ClaimRecord(
        claim_id=CLAIM_FIXTURE.claim_id,
        employee_id=CLAIM_FIXTURE.employee_id,
        merchant=CLAIM_FIXTURE.merchant,
        amount_cents=CLAIM_FIXTURE.amount_cents,
        purpose=CLAIM_FIXTURE.purpose,
        status=CLAIM_FIXTURE.status,
        submitted_on=CLAIM_FIXTURE.submitted_on,
        risk_score=CLAIM_FIXTURE.risk_score,
        reviewer_note=CLAIM_FIXTURE.reviewer_note,
        decision=CLAIM_FIXTURE.decision,
        approved_amount_cents=CLAIM_FIXTURE.approved_amount_cents,
    )
    new_property = "internal_ledger_ref"
    canary = "LEAK-CANARY"
    setattr(claim, new_property, canary)

    for projection in (employee_projection(claim), reviewer_projection(claim)):
        rendered = projection.model_dump_json()
        assert new_property not in rendered
        assert canary not in rendered


def _compose() -> dict[str, Any]:
    document: dict[str, Any] = yaml.safe_load(
        (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8"),
    )
    return document


def test_only_one_service_is_published_and_only_to_loopback() -> None:
    services: dict[str, Any] = _compose()["services"]
    published = {name: spec["ports"] for name, spec in services.items() if spec.get("ports")}
    assert list(published) == ["secure"]
    for mappings in published.values():
        for mapping in mappings:
            assert str(mapping).startswith("127.0.0.1:")


def test_no_intentionally_vulnerable_service_ships_in_this_slice() -> None:
    services: dict[str, Any] = _compose()["services"]
    assert set(services) == {"secure", "verify"}
    assert not (PACKAGE_ROOT / "vulnerable_app.py").exists()
