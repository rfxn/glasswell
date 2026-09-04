"""`/v1/wells/{api10}/cumulatives`: a total, and the record it is a total of."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.cumulatives import refresh_well_cumulatives
from tests.contract.conftest import (
    NEVER_REPORTED_API10,
    STORED_CLASSES_API10,
    TX_API10,
    WITHHELD_LEDGER_MONTH,
)
from tests.contract.conftest import (
    NM_API10 as OUT_OF_SCOPE_API10,
)
from tests.support.fakes import FixedClock
from tests.support.seed import FIXTURE_ENV, seed_well


@pytest.fixture
def before_the_allocation(seeded: psycopg.Connection, client: TestClient) -> TestClient:
    """The load window: the allocated mart emptied and the cumulative mart refreshed over it,
    which is what `scripts/deploy.sh` does on every deploy before the manual load."""
    with seeded.cursor() as cursor:
        cursor.execute("delete from marts.tx_allocated_production")
    seeded.commit()
    with lineage_session(
        recorder=PostgresRecorder(seeded),
        environment=FIXTURE_ENV,
        clock=FixedClock(datetime(2026, 8, 27, 7, 0, 0, tzinfo=UTC)),
        correlation_id="run_contract_cumulatives_pending",
    ):
        refresh_well_cumulatives(seeded)
    seeded.commit()
    return client


def test_a_jurisdiction_whose_mart_is_pending_is_not_told_it_is_out_of_scope(
    before_the_allocation: TestClient,
) -> None:
    """H-10-C. The refresh skipped 42 and the 404 asserted the mart covers 42, which invites
    the reader to conclude the well is outside the scope -- the opposite of both halves of
    "an empty mart is a jurisdiction that is not ready, not a jurisdiction that filed
    nothing"."""
    response = before_the_allocation.get(f"/v1/wells/{TX_API10}/cumulatives")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "the last refresh skipped it" in detail
    assert "cr_tx_allocation_v0_1" in detail
    assert f"/v1/wells/{TX_API10}/production" in detail
    assert "The cumulative mart covers state API prefix" not in detail


def test_a_well_outside_every_registered_scope_is_still_told_which_prefixes_are_covered(
    before_the_allocation: TestClient,
) -> None:
    """The other arm, and the reason the sentence is read from the refresh: with 42 skipped
    the covered list is what the refresh wrote, not what the module is configured with."""
    response = before_the_allocation.get(f"/v1/wells/{OUT_OF_SCOPE_API10}/cumulatives")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "The cumulative mart covers state API prefix" in detail
    assert "42" not in detail.split(";")[0]


@pytest.fixture
def with_out_of_scope_well(seeded: psycopg.Connection, client: TestClient) -> TestClient:
    """One well in a jurisdiction that registers no `cumulatives_scope` decision.

    Local to this file rather than in the shared fixture: four standing gates prove New
    Mexico holds no rows and that the surface says so by name, and a well seeded for every
    test retires all four (gate-tx H-3).
    """
    with seeded.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id from canonical.production_monthly limit 1"
        )
        manifest_id, derivation_id = cursor.fetchone()
    seed_well(
        seeded,
        api10=OUT_OF_SCOPE_API10,
        manifest_id=manifest_id,
        derivation_id=derivation_id,
        state_code="30",
        county_code_at_permit="015",
        ndic_file_no=None,
        basin=None,
        land_unit_label=None,
        well_name="STATE COM 1H",
        operator_name_reported="MEWBOURNE OIL COMPANY",
        operator_id="14744",
        status_canonical="active",
        status_reported="A",
        well_type_reported="O",
        spud_date=None,
        total_depth_ft=None,
        completion_date=None,
    )
    seeded.commit()
    return client

PATH = f"/v1/wells/{EXAMPLE_API10}/cumulatives"
SNAPSHOT = "2026-08-01"
ADMITTED = ("reported", "reported_zero")


def handles(node) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        if isinstance(node.get("d"), str):
            found.add(node["d"])
        for key, value in node.items():
            if key == "_lineage" and isinstance(value, dict):
                found.update(str(handle) for handle in value.values())
            else:
                found.update(handles(value))
    elif isinstance(node, list):
        for value in node:
            found.update(handles(value))
    return found


def test_each_stream_is_a_figure_with_its_unit_and_its_basis(client: TestClient) -> None:
    data = client.get(PATH).json()["data"]

    oil = data["cumulative"]["oil_bbl"]
    assert (oil["value"], oil["unit"], oil["basis"]) == ("21000.000", "bbl", "oil+condensate")
    assert oil["granularity"] == "well_observed"
    assert oil["d"].startswith("drv_")


def test_a_gas_figure_carries_no_liquids_basis(client: TestClient) -> None:
    """STREAM_BASIS['gas'] is None: a basis on a gas figure would be a claim about nothing."""
    gas = client.get(PATH).json()["data"]["cumulative"]["gas_mcf"]

    assert (gas["value"], gas["unit"]) == ("50400.000", "mcf")
    assert "basis" not in gas


def test_a_withheld_month_is_counted_and_is_not_in_the_total(client: TestClient) -> None:
    data = client.get(PATH).json()["data"]

    water = data["coverage"]["water_bbl"]
    assert water["months_withheld"] == 2
    assert water["months_reported"] == 5
    assert water["months_no_report"] == 0
    # The last water month is a stored withheld carrying a non-zero volume; a total that
    # admitted it would read 16800.
    assert data["cumulative"]["water_bbl"]["value"] == "12000.000"


def test_the_coverage_counts_are_carried_by_a_sidecar_handle_per_stream(
    client: TestClient,
) -> None:
    """SB-07 §9.1(b): five figures a stream would put this response over /v1/explain's cap."""
    data = client.get(PATH).json()["data"]

    assert set(data["coverage"]["_lineage"]) == {"oil_bbl", "gas_mcf", "water_bbl"}
    assert set(data["coverage"]["_units"].values()) == {"months"}
    assert len(handles(data)) == 7


def test_the_well_level_withheld_count_is_its_own_figure(client: TestClient) -> None:
    data = client.get(PATH).json()["data"]

    assert data["months_withheld"]["unit"] == "months"
    assert data["months_withheld"]["value"] == "1"


def test_the_month_classes_add_up_to_the_span_on_every_stream(client: TestClient) -> None:
    coverage = client.get(PATH).json()["data"]["coverage"]

    for column in ("oil_bbl", "gas_mcf", "water_bbl"):
        block = coverage[column]
        assert block["span_months"] == (
            block["months_reported"]
            + block["months_reported_zero"]
            + block["months_no_report"]
            + block["months_withheld"]
        ), column


def test_the_span_opens_at_the_withheld_month_the_ledger_holds(client: TestClient) -> None:
    coverage = client.get(PATH).json()["data"]["coverage"]["oil_bbl"]

    assert coverage["first_month"] == WITHHELD_LEDGER_MONTH.strftime("%Y-%m")
    assert coverage["last_month"] == "2026-06"
    assert coverage["coverage_complete"] is False


def test_every_handle_resolves(client: TestClient) -> None:
    """The Phase 1 registry rows are what make the response and the mart handles resolve."""
    data = client.get(PATH).json()["data"]
    found = handles(data)

    assert found
    for handle in sorted(found):
        response = client.get("/v1/explain", params={"h": handle, "depth": "full"})
        assert response.status_code == 200, (handle, response.text)


def test_explain_changes_no_value_in_data(client: TestClient) -> None:
    """SB-07 §9.2: the flag adds a block beside `data` and moves nothing inside it."""
    plain = client.get(PATH).json()
    explained = client.get(PATH, params={"explain": "true"}).json()

    assert explained["data"] == plain["data"]
    assert set(explained["_explain"]) == handles(plain["data"])


def test_the_withheld_warning_names_the_count_and_the_ledger(client: TestClient) -> None:
    warnings = client.get(PATH).json()["meta"]["warnings"]

    withheld = [item for item in warnings if item["code"] == "months_withheld"]
    assert len(withheld) == 1
    assert "/v1/quarantine" in withheld[0]["detail"]


def test_a_well_outside_the_mart_is_refused_by_name(with_out_of_scope_well: TestClient) -> None:
    """An empty 200 would read as `produced nothing`; a well outside the mart's scope is
    simply not in it, and the refusal names the scope so a reader can tell the two apart.

    Texas entered the scope by registering a cumulatives_scope rule, so the out-of-scope
    example is a jurisdiction that has registered no such decision.
    """
    response = with_out_of_scope_well.get(f"/v1/wells/{OUT_OF_SCOPE_API10}/cumulatives")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "33" in detail
    assert "42" in detail


def test_the_well_offers_the_link_only_where_the_mart_holds_a_total(
    with_out_of_scope_well: TestClient,
) -> None:
    """The card reads the link rather than the API prefix: a jurisdiction test in the client
    is a mapping decision living in code (R8), and it would turn this 404 into `no production`.
    """
    client = with_out_of_scope_well
    in_scope = client.get(f"/v1/wells/{EXAMPLE_API10}").json()["links"]
    allocated = client.get(f"/v1/wells/{TX_API10}").json()["links"]
    out_of_scope = client.get(f"/v1/wells/{OUT_OF_SCOPE_API10}").json()["links"]

    assert in_scope["cumulatives"] == PATH
    # Texas is in scope on an allocated basis, which is a fact the block states rather than a
    # reason to withhold the link: a card offered no link would read the absence as "no total".
    assert allocated["cumulatives"] == f"/v1/wells/{TX_API10}/cumulatives"
    assert "cumulatives" not in out_of_scope


def test_an_as_of_before_the_snapshot_is_refused_and_one_after_it_is_served(
    client: TestClient,
) -> None:
    early = client.get(PATH, params={"as_of": "2026-01-01"})
    late = client.get(PATH, params={"as_of": "2026-08-20"})

    assert early.status_code == 422
    assert early.json()["type"].endswith("as_of_out_of_range")
    assert SNAPSHOT in early.json()["detail"]
    assert late.status_code == 200
    assert late.json()["meta"]["as_of"] == {"requested": "2026-08-20", "resolved": SNAPSHOT}


def test_the_links_reach_the_well_the_series_and_the_rule(client: TestClient) -> None:
    links = client.get(PATH).json()["links"]

    assert links["well"] == f"/v1/wells/{EXAMPLE_API10}"
    assert links["production"] == f"/v1/wells/{EXAMPLE_API10}/production"
    assert links["cr_nd_null_semantics_1"] == "/v1/conformance/cr_nd_null_semantics_1"


def test_the_total_equals_the_live_series_summed_at_the_same_vintage(client: TestClient) -> None:
    """Two surfaces serving one quantity must agree, and this is what proves they do.

    Truncated on the knowledge axis, which is the one the mart's snapshot is on and the one
    `_BEHIND_SERIES` compares: a point filed at a report vintage later than the snapshot is a
    point the mart has not absorbed, and including it would make this test fail for the one
    reason the response already explains.

    Only the months the cumulative admits are summed: the fixture's withheld water month
    carries a non-zero volume, so a naive sum of the series would disagree with the mart by
    exactly the value the regulator held back — which is the point, not a discrepancy.
    """
    cumulative = client.get(PATH).json()["data"]
    snapshot = cumulative["snapshot_vintage"]
    series = client.get(f"/v1/wells/{EXAMPLE_API10}/production").json()["data"]["series"]

    truncated = 0
    for column in ("oil_bbl", "gas_mcf", "water_bbl"):
        summed = Decimal(0)
        for value, semantics, vintage in zip(
            series[column],
            series[f"{column}_null_semantics"],
            series[f"{column}_report_vintage"],
            strict=True,
        ):
            if semantics not in ADMITTED or value is None:
                continue
            if vintage is not None and vintage > snapshot:
                truncated += 1
                continue
            summed += Decimal(value)
        assert summed == Decimal(cumulative["cumulative"][column]["value"]), column
    # The fixture holds nothing past the snapshot, so the truncation arm is exercised by
    # test_a_filing_newer_than_the_snapshot_is_stated_rather_than_left_to_arithmetic instead.
    assert truncated == 0


def test_every_cumulative_figure_carries_the_vintage_it_was_built_at(client: TestClient) -> None:
    """A copied payload still says which vintage it is (Figure.to_wire, envelope.py:105)."""
    data = client.get(PATH).json()["data"]

    assert data["snapshot_vintage"] == SNAPSHOT
    for column in ("oil_bbl", "gas_mcf", "water_bbl"):
        assert data["cumulative"][column]["report_vintage"] == SNAPSHOT


def test_a_current_mart_states_no_divergence(client: TestClient) -> None:
    """A warning that is always on is not a signal."""
    warnings = client.get(PATH).json()["meta"]["warnings"]

    assert [item for item in warnings if item["code"] == "cumulative_behind_series"] == []


def test_a_filing_newer_than_the_snapshot_is_stated_rather_than_left_to_arithmetic(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    from tests.contract.conftest import _insert_production

    _insert_production(
        seeded,
        api10=EXAMPLE_API10,
        production_month=date(2026, 7, 1),
        stream="oil",
        volume=Decimal("7000"),
        manifest_id="man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        derivation_id="drv_obqajdni25f25zmxcz7a",
        report_vintage=date(2026, 9, 1),
    )
    seeded.commit()
    body = client.get(PATH).json()

    behind = [
        item for item in body["meta"]["warnings"] if item["code"] == "cumulative_behind_series"
    ]
    assert len(behind) == 1
    assert SNAPSHOT in behind[0]["detail"]
    assert "2026-09-01" in behind[0]["detail"]
    assert body["links"]["production"]


def test_a_well_that_never_reported_is_served_rather_than_zeroed_or_refused(
    client: TestClient,
) -> None:
    """M5: the well exists; the honest answer is that nothing was ever filed for it."""
    body = client.get(f"/v1/wells/{NEVER_REPORTED_API10}/cumulatives")

    assert body.status_code == 200
    data = body.json()["data"]
    assert data["coverage_outcome"] == "never_reported"
    assert data["cumulative"] is None
    for column in ("oil_bbl", "gas_mcf", "water_bbl"):
        block = data["coverage"][column]
        assert (block["span_months"], block["months_reported"]) == (0, 0)
    assert data["months_withheld"]["value"] == "0"


def test_a_stored_no_report_and_a_stored_withheld_are_each_counted(client: TestClient) -> None:
    """B2: both are column values as well as absences, and a gap-only count loses them."""
    data = client.get(f"/v1/wells/{STORED_CLASSES_API10}/cumulatives").json()["data"]

    oil = data["coverage"]["oil_bbl"]
    assert (oil["months_no_report"], oil["months_withheld"], oil["span_months"]) == (1, 1, 2)
    assert oil["months_reported"] == 0
    assert data["coverage_outcome"] == "observed"
    assert data["cumulative"]["oil_bbl"] is None
