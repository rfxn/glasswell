"""The series endpoint: SB-07 §9.1(b) sidecar form, per-point vintages, DIR-2 as-of."""

from __future__ import annotations

from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10

PATH = f"/v1/wells/{EXAMPLE_API10}/production"


def test_the_series_is_the_sidecar_form(client: TestClient) -> None:
    data = client.get(PATH).json()["data"]

    assert data["series"]["pm"] == [f"2026-0{month}" for month in range(1, 7)]
    assert data["_lineage"]["series.oil_bbl"].startswith("drv_")
    assert data["_units"]["series.oil_bbl"] == "bbl"
    assert data["_units"]["series.gas_mcf"] == "mcf"


def test_the_oil_series_states_the_liquids_basis(client: TestClient) -> None:
    """cr_nd_liquids_policy_1: the basis travels with every ND liquids figure."""
    data = client.get(PATH).json()["data"]

    assert data["_basis"]["series.oil_bbl"] == "oil+condensate"


def test_every_point_carries_its_report_vintage(client: TestClient) -> None:
    data = client.get(PATH).json()["data"]

    vintages = data["series"]["oil_bbl_report_vintage"]
    assert len(vintages) == len(data["series"]["oil_bbl"])
    assert set(vintages) == {"2026-08-01"}


def test_null_semantics_are_not_collapsed(client: TestClient) -> None:
    """§3.0.3: a withheld value and an absent report are different facts."""
    data = client.get(PATH).json()["data"]

    assert data["series"]["water_bbl_null_semantics"][-1] == "withheld"
    assert set(data["series"]["oil_bbl_null_semantics"]) == {"reported"}


def test_the_granularity_is_declared(client: TestClient) -> None:
    data = client.get(PATH).json()["data"]

    assert data["granularity"] == "well_observed"


def test_a_stream_filter_selects_one_series(client: TestClient) -> None:
    data = client.get(PATH, params={"stream": "oil"}).json()["data"]

    assert "series.oil_bbl" in data["_lineage"]
    assert "series.gas_mcf" not in data["_lineage"]
    assert "gas_mcf" not in data["series"]


def test_a_month_window_narrows_the_axis(client: TestClient) -> None:
    data = client.get(PATH, params={"from": "2026-02", "to": "2026-04"}).json()["data"]

    assert data["series"]["pm"] == ["2026-02", "2026-03", "2026-04"]


def test_as_of_resolves_the_restatement_backwards(client: TestClient) -> None:
    """DIR-2: the March restatement is a new vintage; as_of picks the older one."""
    latest = client.get(PATH).json()
    earlier = client.get(PATH, params={"as_of": "2026-07-15"}).json()

    index = latest["data"]["series"]["pm"].index("2026-03")
    assert latest["data"]["series"]["oil_bbl"][index] == "3000.000"
    assert latest["data"]["series"]["oil_bbl_report_vintage"][index] == "2026-08-01"
    earlier_index = earlier["data"]["series"]["pm"].index("2026-03")
    assert earlier["data"]["series"]["oil_bbl"][earlier_index] == "2500.000"
    assert earlier["data"]["series"]["oil_bbl_report_vintage"][earlier_index] == "2026-07-01"


def test_the_resolved_vintage_is_reported(client: TestClient) -> None:
    meta = client.get(PATH, params={"as_of": "2026-07-15"}).json()["meta"]

    assert meta["as_of"] == {"requested": "2026-07-15", "resolved": "2026-07-01"}


def test_volumes_are_strings_not_floats(client: TestClient) -> None:
    """SB-07 §4.4: a float round-trip re-introduces summation-order nondeterminism."""
    data = client.get(PATH).json()["data"]

    assert all(isinstance(value, str) for value in data["series"]["oil_bbl"])


def test_the_series_labels_its_vintage_column(client: TestClient) -> None:
    labels = client.get(PATH).json()["meta"]["labels"]

    assert labels["/series/oil_bbl_report_vintage"] == "gt_report_vintage"
    assert labels["/series/oil_bbl"] == "gt_liquids_policy"


def test_an_unknown_well_is_not_found(client: TestClient) -> None:
    assert client.get("/v1/wells/3300000000/production").status_code == 404


def test_source_freshness_is_reported_alongside_the_series(client: TestClient) -> None:
    meta = client.get(PATH).json()["meta"]

    assert meta["source_freshness"]["nd_mpr_xlsx"]["retrieval_vintage"] == "2026-08-01"
