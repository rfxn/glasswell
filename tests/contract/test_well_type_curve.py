"""`/v1/wells/{api10}/type-curve`: N1's exit criteria, asserted on the served surface."""

from __future__ import annotations

from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10
from glasswell.lineage.explain import MAX_DEPTH
from glasswell.modeling.p3_publication import CONTROL_SHA256_KEY
from tests.contract.conftest import OTHER_API10S

CURVE = f"/v1/wells/{EXAMPLE_API10}/type-curve"
UNAVAILABLE = f"/v1/wells/{OTHER_API10S[2]}/type-curve"
BASIN_RUNG = f"/v1/wells/{OTHER_API10S[1]}/type-curve"


def _curve(client: TestClient, url: str = CURVE, **params) -> dict:
    response = client.get(url, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_curve_is_month_indexed_to_its_horizon(client: TestClient) -> None:
    body = _curve(client)
    assert body["data"]["horizon_months"] == 24
    assert body["data"]["series"]["month_index"] == list(range(1, 25))
    assert len(body["data"]["series"]["monthly_p50"]) == 24

    twelve = _curve(client, horizon=12)
    assert twelve["data"]["horizon_months"] == 12
    assert twelve["data"]["series"]["month_index"] == list(range(1, 13))
    assert twelve["data"]["split_id"] != body["data"]["split_id"]


def test_both_normalisation_arms_are_reachable_and_differ(client: TestClient) -> None:
    absolute = _curve(client, normalization="typecurve_absolute")["data"]
    per_kft = _curve(client, normalization="typecurve_per_kft")["data"]
    assert absolute["series"]["monthly_p50"] != per_kft["series"]["monthly_p50"]
    assert absolute["_units"]["series.monthly_p50"] == "bbl"
    assert per_kft["_units"]["series.monthly_p50"] == "bbl/kft"


def test_the_cumulative_at_horizon_is_the_cum12_or_cum24_figure(client: TestClient) -> None:
    data = _curve(client)["data"]
    band = data["cumulative_at_horizon"]
    assert band["p50"]["value"] == data["series"]["cumulative_p50"][-1]
    assert band["p10"]["unit"] == "bbl"
    assert all(band[level]["d"] for level in ("p10", "p50", "p90"))
    twelve = _curve(client, horizon=12)["data"]
    assert twelve["cumulative_at_horizon"]["p50"]["value"] != band["p50"]["value"]


def test_the_quantiles_are_statistical_ascending_and_say_so(client: TestClient) -> None:
    data = _curve(client)["data"]
    assert data["quantile_convention"] == "statistical_ascending"
    band = data["cumulative_at_horizon"]
    assert float(band["p10"]["value"]) < float(band["p50"]["value"]) < float(band["p90"]["value"])


def test_the_peer_ladder_rung_is_served_not_assumed(client: TestClient) -> None:
    assert _curve(client)["data"]["fallback_level"] == "formation_area_length"
    basin = _curve(client, BASIN_RUNG)
    assert basin["data"]["fallback_level"] == "formation_basin"
    codes = [item["code"] for item in basin["meta"]["warnings"]]
    assert "control_fallback_rung" in codes
    assert "control_peer_floor" in codes


def test_the_support_distribution_rides_every_month(client: TestClient) -> None:
    data = _curve(client)["data"]
    assert data["series"]["peer_count"] == [34] * 24
    assert data["_units"]["series.peer_count"] == "wells"
    assert data["_lineage"]["series.cumulative_peer_count"]
    assert "mean" not in str(data["series"])


def test_control_unavailable_is_a_stated_outcome_with_a_two_hundred(client: TestClient) -> None:
    response = client.get(UNAVAILABLE)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["outcome"] == "control_unavailable"
    assert data["fallback_level"] == "control_unavailable"
    assert data["control_unavailable_reasons"] == ["missing_lateral_length"]
    assert data["peer_set_id"] is None
    assert data["subject_lateral_length_ft"] is None
    assert data["cumulative_at_horizon"] is None
    assert data["series"]["monthly_p50"] == [None] * 24
    assert data["series"]["peer_count"] == [0] * 24
    assert data["_lineage"]["series.monthly_p50"]
    assert data["_units"]["series.monthly_p50"] == "bbl"
    assert data["_basis"]["series.monthly_p50"] == "oil+condensate"
    warnings = [item["code"] for item in response.json()["meta"]["warnings"]]
    assert warnings == ["control_unavailable"]


def test_outcome_is_a_required_field_in_the_schema(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()["components"]["schemas"]["WellTypeCurve"]
    assert "outcome" in schema["required"]
    assert schema["properties"]["outcome"]["enum"] == ["available", "control_unavailable"]


def test_an_unavailable_control_still_resolves_its_handles(client: TestClient) -> None:
    """The chain answers where the absence comes from: the same artifact, the rung that ended."""
    body = _curve(client, UNAVAILABLE, explain="true")
    handle = body["data"]["_lineage"]["series.monthly_p50"]
    chain = body["_explain"][handle]
    assert chain["terminals"]
    ids = {node["id"] for node in chain["nodes"]}
    assert body["data"]["publication_id"]
    assert any(node["type"] == "derivation" for node in chain["nodes"])
    assert len(ids) > 1


def test_a_well_that_is_not_a_test_subject_is_not_found(client: TestClient) -> None:
    response = client.get("/v1/wells/3399999999/type-curve")
    assert response.status_code == 404
    assert "is not a test subject of sset_" in response.json()["detail"]


def test_an_origin_the_subject_does_not_have_is_not_found_and_lists_what_it_does(
    client: TestClient,
) -> None:
    response = client.get(CURVE, params={"origin": "2021-07-01"})
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "2021-01-01/24m" in detail
    assert "2021-01-01/12m" in detail


def test_every_handle_names_the_control_derivation_and_the_split_set(client: TestClient) -> None:
    body = _curve(client, explain="true")
    data = body["data"]
    publication = client.get(
        f"/v1/modeling/publications/{data['publication_id']}"
    ).json()["data"]
    control = publication["derivations"]["type_curve"]
    band = data["cumulative_at_horizon"]
    # Every served figure, not only the eight series sidecars: the three band members and the
    # subject's lateral length carry inline `d` handles and are minted the same way.
    handles = {
        *data["_lineage"].values(),
        *(band[level]["d"] for level in ("p10", "p50", "p90")),
        data["subject_lateral_length_ft"]["d"],
    }
    assert len(handles) == 12
    for handle in handles:
        chain = body["_explain"][handle]
        assert control in {node["id"] for node in chain["nodes"]}
    node = next(
        node
        for node in body["_explain"][next(iter(handles))]["nodes"]
        if node["id"] == control
    )
    assert node["output"]["partition"]["split_set_id"] == data["split_set_id"]
    assert node["output"]["sha256"] == publication["artifact_sha256"][CONTROL_SHA256_KEY]


def test_the_chain_terminates_in_manifests_with_headroom(client: TestClient) -> None:
    """Tautological in this tier and kept anyway: the fixture registers one manifest input, so
    its chain is two levels deep and this cannot fail here whatever the real build gains. The
    guard that can fire is the deployed measurement recorded in SMOKE.md."""
    body = _curve(client, explain="true", explain_depth=8)
    for chain in body["_explain"].values():
        kinds = {node["id"]: node["type"] for node in chain["nodes"]}
        assert chain["terminals"]
        assert all(kinds[terminal] == "manifest" for terminal in chain["terminals"])
        assert chain["truncated"] is False
        assert chain["depth"] <= MAX_DEPTH - 1


def test_the_default_inline_depth_still_reaches_the_control_derivation(
    client: TestClient,
) -> None:
    body = _curve(client, explain="true")
    handle = body["data"]["_lineage"]["series.monthly_p50"]
    control = client.get(
        f"/v1/modeling/publications/{body['data']['publication_id']}"
    ).json()["data"]["derivations"]["type_curve"]
    assert control in {node["id"] for node in body["_explain"][handle]["nodes"]}


def test_the_response_does_not_disclose_a_filesystem_path(client: TestClient) -> None:
    body = client.get(CURVE).text
    assert "part-0000.parquet" not in body
    assert "typecurve_control/" not in body


def test_an_oil_figure_states_the_liquids_basis(client: TestClient) -> None:
    for arm in ("typecurve_absolute", "typecurve_per_kft"):
        data = _curve(client, normalization=arm)["data"]
        assert data["_basis"]["series.monthly_p50"] == "oil+condensate"
        assert data["cumulative_at_horizon"]["p50"]["basis"] == "oil+condensate"
    gas = _curve(client, stream="gas")["data"]
    assert gas["_units"]["series.monthly_p50"] == "mcf"
    assert "series.monthly_p50" not in gas.get("_basis", {})


def test_the_relation_says_it_is_not_a_forecast(client: TestClient) -> None:
    assert _curve(client)["data"]["relation"] == "control_type_curve_not_a_forecast"


def test_no_as_of_is_offered_on_the_control(client: TestClient) -> None:
    """The control is pinned to one eval vintage; as_of would imply a history it does not have."""
    document = client.get("/openapi.json").json()
    names = {
        parameter["name"]
        for parameter in document["paths"]["/v1/wells/{api10}/type-curve"]["get"]["parameters"]
    }
    assert "as_of" not in names
    assert {"stream", "normalization", "horizon", "origin", "publication"} <= names
