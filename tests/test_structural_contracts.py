"""Structural gates that fail if the secure contracts drift toward generic serialization or binding.

These tests are the deny-by-default guarantee. They do not exercise behavior; they assert that the
code *cannot* start exposing or accepting a property just because somebody added a column.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

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

#: The one module allowed to serialize and bind generically. Everything else is the secure path.
VULNERABLE_MODULES = frozenset({"vulnerable_app.py"})

SOURCE_FILES = sorted(PACKAGE_ROOT.glob("*.py"))
SECURE_SOURCE_FILES = [path for path in SOURCE_FILES if path.name not in VULNERABLE_MODULES]

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
    assert SECURE_SOURCE_FILES
    assert len(SECURE_SOURCE_FILES) < len(SOURCE_FILES)


@pytest.mark.parametrize("path", SECURE_SOURCE_FILES, ids=lambda path: path.name)
def test_no_mapping_is_unpacked_into_a_call(path: Path) -> None:
    """`f(**untrusted)` is how whole-object binding gets in. It is banned outright."""
    for node in ast.walk(_parsed(path)):
        if isinstance(node, ast.Call):
            assert all(keyword.arg is not None for keyword in node.keywords), (
                f"{path.name}: dictionary unpacking into a call is forbidden"
            )


@pytest.mark.parametrize("path", SECURE_SOURCE_FILES, ids=lambda path: path.name)
def test_no_dynamic_attribute_assignment(path: Path) -> None:
    """`setattr(claim, key, value)` is mass assignment with extra steps."""
    for node in ast.walk(_parsed(path)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "setattr", (
                f"{path.name}: dynamic attribute assignment is forbidden"
            )


@pytest.mark.parametrize("path", SECURE_SOURCE_FILES, ids=lambda path: path.name)
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


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(_parsed(path)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("path", SECURE_SOURCE_FILES, ids=lambda path: path.name)
def test_no_secure_module_imports_the_vulnerable_one(path: Path) -> None:
    """The flaws must be unreachable from the secure service, not merely unused by it."""
    assert "fieldblind.vulnerable_app" not in _imported_modules(path)


def test_the_vulnerable_module_exists_and_is_the_only_excluded_one() -> None:
    for name in VULNERABLE_MODULES:
        assert (PACKAGE_ROOT / name).exists()


@pytest.mark.parametrize("flaw", ["serialize_whole_object", "bind_whole_object"])
def test_each_flaw_is_defined_only_in_the_vulnerable_module(flaw: str) -> None:
    definitions = {
        path.name
        for path in SOURCE_FILES
        for node in ast.walk(_parsed(path))
        if isinstance(node, ast.FunctionDef) and node.name == flaw
    }
    assert definitions == {"vulnerable_app.py"}


def test_the_vulnerable_module_reuses_the_shared_boundary() -> None:
    """It must be the same product, differing only where the demonstration needs it to."""
    imported = _imported_modules(PACKAGE_ROOT / "vulnerable_app.py")
    assert "fieldblind.authentication" in imported
    assert "fieldblind.object_policy" in imported
    assert "fieldblind.demo_support" in imported


def test_the_vulnerable_module_uses_no_secure_property_contract() -> None:
    """If it borrowed the projections or the update contracts, it would not be vulnerable."""
    imported = _imported_modules(PACKAGE_ROOT / "vulnerable_app.py")
    assert "fieldblind.projections" not in imported
    assert "fieldblind.schemas" not in imported
    assert "fieldblind.service" not in imported
