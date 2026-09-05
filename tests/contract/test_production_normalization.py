"""`?normalization=per_lateral_ft`: a served arm, because a client division cannot say why.

Dividing in the browser and keeping the served handle would be a naked number wearing someone
else's papers: the ⌾ would open the production chain and say nothing about the length it was
divided by. So the division is the server's, the unit says what it is, the basis names the
divisor and the method, and one chain resolves both inputs.

Every refusal here is a jurisdiction the card hides the control on. This is what answers a
caller who asks anyway, which is the half a hidden control cannot cover.
"""

from __future__ import annotations

from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10
from tests.contract.conftest import TX_API10

pytestmark = pytest.mark.contract

PATH = f"/v1/wells/{EXAMPLE_API10}/production"


def served(client: TestClient) -> dict:
    return client.get(PATH, params={"normalization": "per_lateral_ft"}).json()


def test_the_points_are_divided_and_the_unit_says_so(client: TestClient) -> None:
    plain = client.get(PATH).json()["data"]
    body = served(client)["data"]

    assert body["_units"]["series.oil_bbl"] == "bbl/kft"
    assert body["_units"]["series.gas_mcf"] == "mcf/kft"
    # The same months, the same order: normalisation changes the value and nothing else.
    assert body["series"]["pm"] == plain["series"]["pm"]
    # The arithmetic, against the length the well record serves for the same well: the point
    # is the served volume divided by the lateral in thousands of feet, and nothing else.
    at = next(index for index, value in enumerate(plain["series"]["oil_bbl"]) if value)
    feet = Decimal(
        client.get(f"/v1/wells/{EXAMPLE_API10}").json()["data"]["lateral_length_ft"]["value"]
    )
    expected = (Decimal(plain["series"]["oil_bbl"][at]) / (feet / 1000)).quantize(
        Decimal("0.001")
    )
    assert Decimal(body["series"]["oil_bbl"][at]) == expected


def test_the_basis_names_the_divisor_and_the_method_it_was_measured_by(
    client: TestClient,
) -> None:
    body = served(client)["data"]

    basis = body["_basis"]["series.oil_bbl"]
    assert "per lateral foot" in basis
    assert "ft" in basis
    # A reader cannot reproduce a per-foot number without the length and how it was measured.
    assert any(method in basis for method in ("geodesic", "projected"))


def test_the_liquids_policy_survives_normalisation(client: TestClient) -> None:
    """State the policy wherever the number appears: a per-foot oil figure still has to say
    that oil means oil plus condensate, beside the divisor it now also carries."""
    plain = client.get(PATH).json()["data"]["_basis"]["series.oil_bbl"]
    basis = served(client)["data"]["_basis"]["series.oil_bbl"]

    assert plain in basis
    assert "per lateral foot" in basis


def test_the_handle_changes_with_the_number_and_resolves_both_inputs(
    client: TestClient,
) -> None:
    """The whole reason this is a served arm: one chain, two inputs, at the depth the card
    opens the drawer at."""
    body = served(client)
    handle = body["data"]["_lineage"]["series.oil_bbl"]
    plain = client.get(PATH).json()["data"]["_lineage"]["series.oil_bbl"]

    assert handle != plain
    chain = client.get(
        "/v1/explain", params={"h": handle, "depth": "4"}
    ).json()["data"]["chains"][0]

    datasets = [(node.get("output") or {}).get("dataset") for node in chain["nodes"]]
    assert "api.well_production" in datasets
    # The production it divided, and the geometry it divided by.
    assert "canonical.production_monthly" in datasets
    assert "canonical.well_spatial" in datasets
    # The chart addresses a point by appending its month to the column's handle, so every
    # drawn month has to be evidence the response derivation recorded, not only the column.
    month = body["data"]["series"]["pm"][
        next(index for index, value in enumerate(body["data"]["series"]["oil_bbl"]) if value)
    ]
    point = client.get("/v1/explain", params={"h": f"{handle}&pm={month}", "depth": "1"})
    assert point.status_code == 200, point.text


def test_a_withheld_month_is_served_as_an_absence_and_not_as_a_figure(
    client: TestClient,
) -> None:
    """The other half of R8's second rule: the normalised arm records an evidence row per
    divided point, so a month with no volume has none — and a ⌾ drawn on it would answer
    `selector_ambiguous` for a figure that was never served (visual M5)."""
    body = served(client)["data"]
    at = body["series"]["water_bbl_null_semantics"].index("withheld")

    assert body["series"]["water_bbl"][at] is None
    handle = f"{body['_lineage']['series.water_bbl']}&pm={body['series']['pm'][at]}"
    assert client.get("/v1/explain", params={"h": handle, "depth": "1"}).status_code == 422


def test_the_rule_that_measured_the_length_is_linked(client: TestClient) -> None:
    assert served(client)["links"]["length_rule"].startswith("/v1/conformance/cr_")


def test_a_jurisdiction_that_withholds_the_length_is_refused_by_name(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """Montana registers `cr_mt_paths_length_scope_1`, so there is no divisor to serve and the
    refusal says which rule decided that rather than answering with a number."""
    answer = client.get(
        f"/v1/wells/{TX_API10}/production", params={"normalization": "per_lateral_ft"}
    )

    assert answer.status_code == 422
    detail = answer.json()["detail"]
    assert "cr_" in detail or "no lateral geometry" in detail


def test_the_lateral_floor_is_the_rule_s_and_moves_when_the_rule_does(
    client: TestClient, db: psycopg.Connection
) -> None:
    """R8: cr_ff_fluid_intensity registers the floor as data and completions reads it at
    request time; the divisor has to read the same row, or a superseded floor leaves the
    refusal describing a registry that no longer says that. The registry is append-only, so
    the floor moves the only way it can: a successor rule."""
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.conformance_rule_publications"
            " (rule_id, published_vintage, evidence_tag, evidence_commit)"
            " values ('cr_ff_fluid_intensity_2', current_date, 'contract-fixture', %s)",
            ("a" * 40,),
        )
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, supersedes_rule_id,"
            " source_id, stage, applies_to_fields, rule_kind, spec, rule, rationale,"
            " evidence_url, effective_from, published_vintage)"
            " select 'cr_ff_fluid_intensity_2', rule_family, rule_id, source_id, stage,"
            " applies_to_fields, rule_kind, jsonb_set(spec, '{min_lateral_ft}', '20000'),"
            " rule, rationale, evidence_url, current_date, current_date"
            " from lineage.conformance_rules where rule_id = 'cr_ff_fluid_intensity_1'"
        )
    db.commit()

    response = client.get(PATH, params={"normalization": "per_lateral_ft"})

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert "20000" in detail
    assert "cr_ff_fluid_intensity_2" in detail


def test_an_unknown_normalisation_is_refused_rather_than_ignored(client: TestClient) -> None:
    # A parameter the API has not agreed to answer must not fall through to the plain series.
    assert client.get(PATH, params={"normalization": "per_barrel"}).status_code == 422


def test_the_pool_grain_arm_gates_the_pools_section_on_a_link(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """M-11: every other section is gated on a link, and this one was gated on the client
    recognising a warning code. The predicate is the one `_pool_grain_warning` already
    computes, so the arm costs no query."""
    body = client.get(PATH).json()

    # The ND fixture rolls up, so it carries no pool-grain arm and says so by omission.
    assert "pools" not in body["links"] or body["links"]["pools"].endswith("/pools")
    # WC-P2-4: the rule that decides whether this jurisdiction carries a per-well cumulative
    # at all is a link rather than a sentence the client would have to write.
    assert body["links"]["cumulatives_rule"].startswith("/v1/conformance/cr_")
