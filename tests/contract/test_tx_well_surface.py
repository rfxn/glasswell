"""What a TX well serves, and what it deliberately does not.

The ND fixtures cannot exercise any of this: a Texas well is the only one with a depth figure,
a jurisdiction that reports at the lease, and a production endpoint whose honest answer is a
disclosure rather than a series. A gate that only ever sees ND data is green on data it does
not represent (N-1).
"""

from __future__ import annotations

from datetime import date

import psycopg
from fastapi.testclient import TestClient

from tests.contract.conftest import TX_API10

PENDING = "production_pending_allocation"
ALLOCATION_RULE = "cr_tx_allocation_scope_1"


def envelope(client: TestClient, path: str, **params) -> dict:
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_tx_well_is_served_by_the_same_endpoint_nd_wells_are(client: TestClient) -> None:
    body = envelope(client, f"/v1/wells/{TX_API10}")

    assert body["data"]["api10"] == TX_API10
    assert body["data"]["state_code"] == "42"
    assert body["data"]["basin"] == "permian"
    assert body["data"]["operator_name_reported"]
    assert body["data"]["surface_point"] is not None


def test_the_tx_well_appears_in_the_collection_and_filters_by_county(client: TestClient) -> None:
    listed = envelope(client, "/v1/wells", county="003", limit=50)

    assert [item["api10"] for item in listed["data"]] == [TX_API10]
    assert listed["data"][0]["spud_date"] is None, "TX publishes no spud date in this slice"


def test_total_depth_is_a_figure_with_a_handle_that_resolves(client: TestClient) -> None:
    """R6: a served number carries its derivation, and the depth is the TX card's own number."""
    depth = envelope(client, f"/v1/wells/{TX_API10}")["data"]["total_depth_ft"]

    assert depth["unit"] == "ft"
    assert depth["value"] == "11450.0"
    assert "#" in depth["d"]
    chain = envelope(client, "/v1/explain", h=depth["d"], depth="full")["data"]["chains"][0]
    assert chain["handle"] == depth["d"]
    assert chain["terminals"], "the depth figure resolves to no checksummed file"


def test_the_geometry_records_the_datum_the_rrc_published_and_the_rule_that_moved_it(
    client: TestClient,
) -> None:
    body = envelope(client, f"/v1/wells/{TX_API10}")

    assert [row["source_datum"] for row in body["data"]["geometry"]] == ["EPSG:4267"]
    assert body["data"]["storage_crs"] == "EPSG:4326"


def test_the_card_says_production_is_pending_allocation_not_absent(client: TestClient) -> None:
    """DIR-3: TX reports at the lease, so 'no production reported' would be false."""
    body = envelope(client, f"/v1/wells/{TX_API10}")

    warnings = {warning["code"]: warning for warning in body["meta"]["warnings"]}
    assert PENDING in warnings
    assert ALLOCATION_RULE in warnings[PENDING]["detail"]
    assert warnings[PENDING]["pointer"] == "/production"
    assert body["links"]["reporting_rule"] == f"/v1/conformance/{ALLOCATION_RULE}"


def test_the_production_endpoint_carries_the_same_disclosure_and_no_series(
    client: TestClient,
) -> None:
    body = envelope(client, f"/v1/wells/{TX_API10}/production")

    assert body["data"]["streams"] == []
    assert PENDING in {warning["code"] for warning in body["meta"]["warnings"]}
    assert body["links"]["reporting_rule"] == f"/v1/conformance/{ALLOCATION_RULE}"


def test_an_nd_well_carries_no_such_disclosure(client: TestClient) -> None:
    """The disclosure is a registry fact about a jurisdiction, not a banner on every well."""
    from glasswell.api.examples import EXAMPLE_API10

    body = envelope(client, f"/v1/wells/{EXAMPLE_API10}")

    assert PENDING not in {warning["code"] for warning in body["meta"]["warnings"]}
    assert "reporting_rule" not in body["links"]


def test_the_rule_behind_the_disclosure_is_readable(client: TestClient) -> None:
    body = envelope(client, f"/v1/conformance/{ALLOCATION_RULE}")

    assert body["data"]["rule_kind"] == "code_ref"
    assert body["data"]["spec"]["reporting_level"] == "lease"
    assert body["data"]["rationale"]


def test_backdated_reporting_change_waits_for_publication_on_both_tx_surfaces(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    successor = "cr_contract_tx_well_reporting_2"
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into lineage.conformance_rule_publications"
            " (rule_id, published_vintage, evidence_tag, evidence_commit)"
            " values (%s, %s, 'contract-fixture', %s)",
            (successor, date(2026, 9, 1), "b" * 40),
        )
        cursor.execute(
            "insert into lineage.conformance_rules"
            " (rule_id, rule_family, supersedes_rule_id, source_id, stage, rule_kind, spec,"
            " rule, rationale, evidence_url, effective_from)"
            " select %s, rule_family, rule_id, source_id, stage, rule_kind,"
            " '{\"state_code\":\"42\",\"reporting_level\":\"well\","
            "\"allocation_required\":false}'::jsonb, 'TX reports at well level.',"
            " 'Contract clock fixture.', evidence_url, %s"
            " from lineage.conformance_rules where rule_id = %s",
            (successor, date(2020, 1, 1), ALLOCATION_RULE),
        )
    seeded.commit()

    for path in (f"/v1/wells/{TX_API10}", f"/v1/wells/{TX_API10}/production"):
        before = envelope(client, path, as_of="2026-08-28")
        after = envelope(client, path, as_of="2026-09-01")

        assert PENDING in {warning["code"] for warning in before["meta"]["warnings"]}
        assert PENDING not in {warning["code"] for warning in after["meta"]["warnings"]}
