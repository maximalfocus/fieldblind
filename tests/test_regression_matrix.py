"""The security regression matrix.

Every row below is a behavior the gate must prove. The mapping is checked mechanically, so renaming
or deleting a load-bearing test fails the build instead of quietly shrinking the matrix.
"""

from __future__ import annotations

import importlib
from typing import Final

import pytest

#: row -> the test that proves it, as (module, function).
MATRIX: Final[dict[str, tuple[str, str]]] = {
    "vulnerable reviewer-property disclosure": (
        "tests.test_vulnerable_read",
        "test_vulnerable_employee_read_exposes_exactly_the_reviewer_only_properties",
    ),
    "vulnerable protected-property mutation": (
        "tests.test_vulnerable_update",
        "test_the_employee_changed_the_reviewer_decision_and_amount",
    ),
    "secure employee projection": (
        "tests.test_read_projections",
        "test_employee_read_returns_exactly_the_authorized_key_set",
    ),
    "secure employee projection hides reviewer-only names": (
        "tests.test_read_projections",
        "test_employee_read_hides_reviewer_only_property_names",
    ),
    "secure employee projection hides reviewer-only values": (
        "tests.test_read_projections",
        "test_employee_read_hides_reviewer_only_values",
    ),
    "secure mixed-body rejection": (
        "tests.test_employee_update",
        "test_forbidden_employee_body_is_refused_generically",
    ),
    "secure mixed-body byte-for-byte state preservation": (
        "tests.test_employee_update",
        "test_forbidden_employee_body_preserves_state",
    ),
    "no partial update of a mixed body": (
        "tests.test_employee_update",
        "test_mixed_body_does_not_partially_apply_the_authorized_edit",
    ),
    "secure employee edit": (
        "tests.test_employee_update",
        "test_authorized_purpose_edit_changes_only_that_property",
    ),
    "secure reviewer read": (
        "tests.test_read_projections",
        "test_reviewer_read_includes_the_reviewer_only_properties",
    ),
    "secure reviewer decision": (
        "tests.test_reviewer_update",
        "test_reviewer_approval_changes_exactly_the_authorized_properties",
    ),
    "reviewer decision invariants": (
        "tests.test_reviewer_update",
        "test_forbidden_reviewer_body_is_refused_generically",
    ),
    "non-owner parity": (
        "tests.test_variant_parity",
        "test_the_object_boundary_is_identical_in_both_variants",
    ),
    "unknown-object parity": (
        "tests.test_object_policy",
        "test_non_owner_and_unknown_object_are_indistinguishable",
    ),
    "missing, malformed, and unknown authentication": (
        "tests.test_authentication",
        "test_read_without_a_valid_credential_is_uniformly_unauthorized",
    ),
    "authentication parity across variants": (
        "tests.test_variant_parity",
        "test_authentication_is_identical_in_both_variants",
    ),
    "empty, unknown, read-only, and reviewer-only employee inputs": (
        "tests.test_employee_update",
        "test_forbidden_employee_body_is_refused_generically",
    ),
    "malformed employee input": (
        "tests.test_employee_update",
        "test_malformed_body_is_refused_and_preserves_state",
    ),
    "duplicate employee input": (
        "tests.test_employee_update",
        "test_duplicate_property_is_refused",
    ),
    "transaction rollback": (
        "tests.test_atomicity",
        "test_pre_commit_failure_rolls_back_the_employee_update",
    ),
    "audit-event cardinality": (
        "tests.test_audit_events",
        "test_mixed_body_emits_exactly_one_audit_event",
    ),
    "audit-event redaction": (
        "tests.test_audit_events",
        "test_logs_contain_no_body_credential_or_protected_value",
    ),
    "variant isolation": (
        "tests.test_variant_parity",
        "test_mutating_the_vulnerable_variant_leaves_the_secure_one_untouched",
    ),
    "reset": (
        "tests.test_variant_parity",
        "test_each_variant_resets_to_the_canonical_fixture",
    ),
    "two-action vulnerable-service gate": (
        "tests.test_containment",
        "test_the_vulnerable_app_refuses_to_start_without_the_flag",
    ),
    "vulnerable service stays behind its Compose profile": (
        "tests.test_containment",
        "test_the_vulnerable_service_is_behind_a_compose_profile",
    ),
    "container hardening": (
        "tests.test_containment",
        "test_every_container_has_a_read_only_root_filesystem",
    ),
    "no application egress": (
        "tests.test_containment",
        "test_the_application_container_has_no_egress",
    ),
    "deny-by-default property contracts": (
        "tests.test_structural_contracts",
        "test_a_new_persistence_property_does_not_reach_a_public_contract",
    ),
    "bounded audit history": (
        "tests.test_audit_events",
        "test_the_audit_history_stays_bounded",
    ),
    "the full walkthrough": (
        "tests.test_walkthrough",
        "test_the_full_walkthrough_passes",
    ),
    "the walkthrough detects a missing outcome": (
        "tests.test_walkthrough",
        "test_the_runner_fails_when_the_vulnerable_cases_cannot_hold",
    ),
}


@pytest.mark.parametrize(("row", "location"), sorted(MATRIX.items()), ids=str)
def test_every_matrix_row_is_proved_by_a_named_test(row: str, location: tuple[str, str]) -> None:
    module_name, function_name = location
    module = importlib.import_module(module_name)
    assert hasattr(module, function_name), f"{row}: {module_name}.{function_name} is missing"
    assert callable(getattr(module, function_name))


def test_the_matrix_covers_every_required_row() -> None:
    """A row can be added, but none of the required ones may quietly disappear."""
    required = {
        "vulnerable reviewer-property disclosure",
        "vulnerable protected-property mutation",
        "secure employee projection",
        "secure mixed-body rejection",
        "secure mixed-body byte-for-byte state preservation",
        "secure employee edit",
        "secure reviewer read",
        "secure reviewer decision",
        "non-owner parity",
        "unknown-object parity",
        "missing, malformed, and unknown authentication",
        "empty, unknown, read-only, and reviewer-only employee inputs",
        "malformed employee input",
        "duplicate employee input",
        "reviewer decision invariants",
        "no partial update of a mixed body",
        "transaction rollback",
        "audit-event cardinality",
        "audit-event redaction",
        "variant isolation",
        "reset",
        "two-action vulnerable-service gate",
    }
    assert required <= set(MATRIX)
