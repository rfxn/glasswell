"""The registry object itself: what it indexes, what it refuses, and what it will not guess.

No database. `build_registry` is the half of the loader that decides, and the two refusals it
owns -- a prefix that resolves to two jurisdictions (N-3) and a scheme that has no prefix at
all (R-7) -- are the ones no constraint in the jurisdictions migration can reach.
"""

from __future__ import annotations

from datetime import date

import pytest

from glasswell.lineage.jurisdictions import (
    Jurisdiction,
    JurisdictionRegistryError,
    JurisdictionRule,
    build_registry,
)

pytestmark = pytest.mark.unit

KNOWLEDGE = date(2026, 9, 30)
VALID = date(2026, 9, 30)


def registration(code: str, prefix: str | None, *, scheme: str = "api10", **overrides):
    row = {
        "jurisdiction_code": code,
        "level": "state",
        "effective_from": date(2026, 9, 1),
        "published_at": date(2026, 9, 1),
        "evidence_tag": "v0.76",
        "evidence_commit": "a" * 40,
        "name": code,
        "regulator_name": f"{code} regulator",
        "regulator_url": "https://example.invalid/",
        "identity_scheme": scheme,
        "identity_is_unique": True,
        "identity_prefix": prefix,
        "identity_pattern": None if prefix is None else f"^{prefix}[0-9]{{8}}$",
        "source_ids": ("src_one",),
        "liquids_basis": None,
        "wells_tile_layer_id": None,
        "map_colour": None,
        "neighbors_available": False,
        "land_grid_state": False,
        "land_grid_scope": False,
        "status_dataset_detail": None,
        "rationale": "fixture",
        "rules": (),
    }
    return Jurisdiction(**{**row, **overrides})


def test_a_registration_is_reachable_by_its_code_and_by_its_prefix() -> None:
    registry = build_registry([registration("ND", "33")], KNOWLEDGE, VALID)

    assert registry.by_code["ND"].name == "ND"
    assert registry.by_prefix["33"].jurisdiction_code == "ND"
    assert len(registry) == 1
    assert [row.jurisdiction_code for row in registry] == ["ND"]


def test_one_prefix_resolving_to_two_jurisdictions_is_a_refusal_not_a_last_writer() -> None:
    """N-3: the partial unique index only sees a collision at one (effective_from,
    published_at). An executed probe inserted CO with prefix 33 one day after ND's and both
    resolved, so the standing gate is here rather than in the DDL."""
    rows = [registration("ND", "33"), registration("CO", "33")]

    with pytest.raises(JurisdictionRegistryError) as refusal:
        build_registry(rows, KNOWLEDGE, VALID)

    assert "33" in str(refusal.value)
    assert "ND" in str(refusal.value)
    assert "CO" in str(refusal.value)


def test_a_uwi_registration_carries_no_prefix_and_is_not_reachable_by_one() -> None:
    """R-7: Canada has no API-10. A consumer that cannot find it by prefix must fail to find
    it, never fall back to the first two characters of something that is not an API-10."""
    registry = build_registry(
        [registration("ND", "33"), registration("CA-AB", None, scheme="uwi")], KNOWLEDGE, VALID
    )

    assert registry.by_code["CA-AB"].identity_scheme == "uwi"
    assert sorted(registry.by_prefix) == ["33"]
    assert all(row.jurisdiction_code != "CA-AB" for row in registry.by_prefix.values())


def test_a_jurisdiction_whose_key_is_not_unique_says_so_rather_than_being_absent() -> None:
    """M-11: API-10 is not a well key in UT, AK, AL or MS. That is a property of the key, so
    the registration is present and carries the fact; dropping it would hide the state."""
    registry = build_registry(
        [registration("UT", "43", identity_is_unique=False)], KNOWLEDGE, VALID
    )

    assert registry.by_prefix["43"].identity_is_unique is False


def test_the_serving_rule_for_a_decision_is_the_one_answer_and_an_unregistered_one_is_null():
    rules = (
        JurisdictionRule("inventory_jurisdiction", "cr_mt_inventory_jurisdiction_1", True, None),
        JurisdictionRule(
            "inventory_jurisdiction", "cr_mt_pru_inventory_jurisdiction_1", False,
            "PRU lease grain",
        ),
    )
    row = build_registry([registration("MT", "25", rules=rules)], KNOWLEDGE, VALID).by_code["MT"]

    assert row.rule("inventory_jurisdiction") == "cr_mt_inventory_jurisdiction_1"
    assert row.rule("geometry_provenance") is None
    assert row.decisions() == frozenset({"inventory_jurisdiction"})
    assert len(row.rules) == 2
