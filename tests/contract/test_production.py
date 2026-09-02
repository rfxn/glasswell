"""The series endpoint: SB-07 §9.1(b) sidecar form, per-point vintages, DIR-2 as-of."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10
from tests.support.seed import (
    seed_derivation,
    seed_placeholder_manifest,
    seed_production,
    seed_well,
)

PATH = f"/v1/wells/{EXAMPLE_API10}/production"


def test_the_series_is_the_sidecar_form(client: TestClient) -> None:
    """The axis opens at 2025-12: a withheld month has no canonical row, and the ledger is
    where the axis learns it exists at all (D2)."""
    data = client.get(PATH).json()["data"]

    assert data["series"]["pm"] == ["2025-12", *(f"2026-0{month}" for month in range(1, 7))]
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
    # The withheld month has no canonical row, so it has no vintage to report.
    assert set(vintages) == {"2026-08-01", None}


def test_null_semantics_are_not_collapsed(client: TestClient) -> None:
    """§3.0.3: a withheld value and an absent report are different facts."""
    data = client.get(PATH).json()["data"]

    assert data["series"]["water_bbl_null_semantics"][-1] == "withheld"
    # A month the ledger holds and a month canonical labels withheld are the same served
    # fact reached two ways; neither is a gap.
    assert data["series"]["oil_bbl_null_semantics"][0] == "withheld"
    assert set(data["series"]["oil_bbl_null_semantics"]) == {"withheld", "reported"}


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
    """SB-07 §4.4: a float round-trip re-introduces summation-order nondeterminism.

    Both arms, because filtering the withheld points out would pass just as well against a
    series that had quietly stopped carrying them (gate-v075 NIT-5): a withheld month is null,
    never a zero and never a string.
    """
    data = client.get(PATH).json()["data"]
    points = list(
        zip(data["series"]["oil_bbl"], data["series"]["oil_bbl_null_semantics"], strict=True)
    )

    assert [value for value, semantics in points if semantics == "withheld"] == [None]
    assert all(
        isinstance(value, str) for value, semantics in points if semantics != "withheld"
    )


def test_the_series_labels_its_vintage_column(client: TestClient) -> None:
    labels = client.get(PATH).json()["meta"]["labels"]

    assert labels["/series/oil_bbl_report_vintage"] == "gt_report_vintage"
    assert labels["/series/oil_bbl"] == "gt_liquids_policy"


def test_an_unknown_well_is_not_found(client: TestClient) -> None:
    assert client.get("/v1/wells/3300000000/production").status_code == 404


def test_source_freshness_is_reported_alongside_the_series(client: TestClient) -> None:
    meta = client.get(PATH).json()["meta"]

    assert meta["source_freshness"]["nd_mpr_xlsx"]["retrieval_vintage"] == "2026-08-01"


COLORADO_API10 = "0512324638"
COLORADO_MONTHS = (date(2026, 4, 1), date(2026, 5, 1))


def _seed_colorado(connection) -> None:
    """A Colorado well with the dual write beneath it: two completions in one month, one in
    the next, and the well row that carries their sum."""
    manifest_id = seed_placeholder_manifest(connection)
    derivation_id = seed_derivation(connection)
    seed_well(connection, api10=COLORADO_API10, state_code="05", basin=None)
    for month, completions in zip(COLORADO_MONTHS, ((10, 5), (7,)), strict=True):
        for index, volume in enumerate(completions):
            if len(completions) == 1:
                continue
            seed_production(
                connection,
                api10=COLORADO_API10,
                production_month=month,
                report_vintage=date(2026, 8, 14),
                volume=Decimal(volume),
                manifest_id=manifest_id,
                derivation_id=derivation_id,
                source_id="co_ecmc_monthly_prod",
                entity_type="well_completion_pool",
                entity_key=f"{COLORADO_API10}:00:POOL{index}:200221",
                reporting_level="well_completion_pool",
                well_completion_pool=f"00:POOL{index}:200221",
            )
        total = Decimal(sum(completions))
        aggregated = len(completions) > 1
        seed_production(
            connection,
            api10=COLORADO_API10,
            production_month=month,
            report_vintage=date(2026, 8, 14),
            volume=total,
            manifest_id=manifest_id,
            derivation_id=derivation_id,
            source_id="co_ecmc_monthly_prod",
            entity_type="well",
            entity_key=COLORADO_API10,
            reporting_level="well_completion_pool" if aggregated else "well",
            well_completion_pool=None if aggregated else "00:POOL0:200221",
            aggregation="sum_over_pools" if aggregated else None,
        )
    connection.commit()


def test_a_colorado_wells_own_series_is_not_empty(client: TestClient, seeded) -> None:
    """M-20's positive test. The route asks for entity_type='well'; pool rows alone would
    render an empty chart on a well that filed every month."""
    _seed_colorado(seeded)

    data = client.get(f"/v1/wells/{COLORADO_API10}/production").json()["data"]

    assert data["series"]["pm"] == ["2026-04", "2026-05"]
    assert data["series"]["oil_bbl"] == ["15.000", "7.000"]


def test_a_colorado_series_states_that_liquid_means_oil_plus_condensate(
    client: TestClient, seeded
) -> None:
    """ECMC files one liquid stream and no condensate column, so the basis is the shape of the
    filing rather than a glasswell rollup -- and it travels with the figure either way."""
    _seed_colorado(seeded)

    data = client.get(f"/v1/wells/{COLORADO_API10}/production").json()["data"]

    assert data["_basis"]["series.oil_bbl"] == "oil+condensate"


def test_a_colorado_month_says_which_of_its_completions_it_summed(
    client: TestClient, seeded
) -> None:
    """production.py serves the reporting level and links the rule that decided the rollup,
    so a reader can tell a summed month from a single-completion one rather than seeing one
    number for both. The rule id comes from Colorado's own registration, not North Dakota's."""
    _seed_colorado(seeded)

    envelope = client.get(f"/v1/wells/{COLORADO_API10}/production").json()

    assert envelope["data"]["reporting_level"] == "well_completion_pool"
    assert envelope["links"]["pools"] == f"/v1/wells/{COLORADO_API10}/production/pools"
    assert envelope["links"]["aggregation_rule"] == (
        "/v1/conformance/cr_co_production_grain_1"
    )
