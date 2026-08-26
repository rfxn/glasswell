"""`/v1/conformance`: every mapping decision with its rationale and its evidence (R8, S11)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_DERIVATION_ID, EXAMPLE_RULE_ID
from glasswell.seed.conformance_fracfocus import FRACFOCUS_RULES
from glasswell.seed.conformance_land import LAND_RULES
from glasswell.seed.conformance_nd import ND_RULES
from glasswell.seed.conformance_nm import NM_RULES
from glasswell.seed.conformance_tx import TX_RULES

SEEDED_RULES = 14


def test_every_seeded_rule_is_served(client: TestClient) -> None:
    data = client.get("/v1/conformance", params={"limit": 200}).json()["data"]

    assert len(data) >= SEEDED_RULES


def test_every_rule_carries_a_rationale_and_evidence(client: TestClient) -> None:
    """Smoke check 10 asserts this off-box; assert it here so it cannot regress first."""
    data = client.get("/v1/conformance", params={"limit": 200}).json()["data"]

    assert all(item["rationale"] for item in data)
    assert all(item["evidence_url"] for item in data)


def test_rules_are_ordered_newest_effective_first(client: TestClient) -> None:
    data = client.get("/v1/conformance", params={"limit": 200}).json()["data"]

    keys = [(item["effective_from"], item["rule_id"]) for item in data]
    assert keys == sorted(keys, key=lambda key: (key[0], key[1]), reverse=True)


def test_the_collection_filters_on_source_and_kind(client: TestClient) -> None:
    data = client.get(
        "/v1/conformance", params={"source_id": "nd_gis_wells", "kind": "vocab_map"}
    ).json()["data"]

    assert data
    assert {item["source_id"] for item in data} == {"nd_gis_wells"}
    assert {item["rule_kind"] for item in data} == {"vocab_map"}


def test_the_collection_filters_on_stage(client: TestClient) -> None:
    data = client.get("/v1/conformance", params={"stage": "validate"}).json()["data"]

    assert data
    assert {item["stage"] for item in data} == {"validate"}


def test_the_detail_serves_the_spec_verbatim(client: TestClient) -> None:
    data = client.get(f"/v1/conformance/{EXAMPLE_RULE_ID}").json()["data"]

    assert data["rule_id"] == EXAMPLE_RULE_ID
    assert data["spec"]
    assert data["rule"]
    assert data["evidence_url"].startswith("https://")


def test_include_applied_by_is_the_reverse_index(client: TestClient) -> None:
    """U21: which derivations cited this rule is one index scan on derivation_rules."""
    data = client.get(
        f"/v1/conformance/{EXAMPLE_RULE_ID}", params={"include": "applied_by"}
    ).json()["data"]

    assert [entry["derivation_id"] for entry in data["applied_by"]] == [EXAMPLE_DERIVATION_ID]


def test_applied_by_is_absent_unless_asked_for(client: TestClient) -> None:
    data = client.get(f"/v1/conformance/{EXAMPLE_RULE_ID}").json()["data"]

    assert "applied_by" not in data


def test_an_unknown_rule_is_not_found(client: TestClient) -> None:
    assert client.get("/v1/conformance/cr_nope_1").status_code == 404


def _seeded_policy_rule_ids() -> set[str]:
    return {
        str(rule["rule_id"])
        for registry in (FRACFOCUS_RULES, LAND_RULES, ND_RULES, NM_RULES, TX_RULES)
        for rule in registry
        if rule.get("rule_kind") == "code_ref"
    }


def test_the_policy_declarations_are_visible_as_such(client: TestClient) -> None:
    """The code_ref rows are registry data with no executor; they are not hidden. The
    expectation derives from the seed registries, so a new policy declaration changes seeding
    and serving as one act (gate-m17 R-4); the one deliberate membership pin is POLICY_RULES
    in tests/integration/test_seed_rules.py. The floor keeps the derivation non-vacuous."""
    data = client.get("/v1/conformance", params={"kind": "code_ref"}).json()["data"]

    expected = _seeded_policy_rule_ids()
    assert {
        "cr_nd_liquids_policy_1",
        "cr_nd_well_type_disposal_1",
        "cr_nm_wcproduction_host_pin_1",
        "cr_tx_allocation_scope_1",
    } <= expected
    assert {item["rule_id"] for item in data} == expected
