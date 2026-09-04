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


def test_an_unknown_normalisation_is_refused_rather_than_ignored(client: TestClient) -> None:
    # A parameter the API has not agreed to answer must not fall through to the plain series.
    assert client.get(PATH, params={"normalization": "per_barrel"}).status_code == 422
