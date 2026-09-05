"""Every served New Mexico figure carries the rule that shaped it.

Phase 12 makes New Mexico figures servable — the spine is rooted on `canonical.wells`, so the
first prefix-30 header opens the gate for 17.6M production rows already resident. This file is
about what has to be true at that instant: a status vocabulary handle, a geometry provenance
handle, a liquids basis that is New Mexico's and not North Dakota's, and an aggregation rule
that says what New Mexico's pool grain actually means.

The North Dakota and Texas equivalents are asserted in the same file, because a dictionary
lookup that gained a third key is exactly where a regression hides.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from glasswell.api.examples import EXAMPLE_API10
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.jurisdictions import clear_jurisdiction_cache, load_jurisdictions
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.well_pool_rollup import refresh_well_pool_rollup
from tests.contract.conftest import TX_API10
from tests.support.jurisdictions import (
    declared_rule,
    declared_rule_ids,
    prefixes_registering,
    restate,
)
from tests.support.seed import seed_well, seed_well_spatial

NM_API10 = "3001599001"
NM_POOL = "96269"
NM_SURFACE = "POINT(-103.9000 32.1000)"
NM_MONTHS = (date(2026, 5, 1), date(2026, 6, 1))
NM_VINTAGE = date(2026, 8, 20)
ZERO_MONTH = date(2026, 7, 1)
# Later than the other two, so a per-point vintage cannot be the well's maximum by coincidence.
ZERO_VINTAGE = date(2026, 8, 25)
NO_NUMBER_MONTH = date(2026, 8, 1)
NO_NUMBER_VINTAGE = date(2026, 8, 27)


@pytest.fixture
def with_new_mexico(seeded: psycopg.Connection, client: TestClient) -> TestClient:
    """One New Mexico well beside the fixture's North Dakota and Texas ones.

    Its production is filed at pool grain and nothing rolls it up, which is the live shape:
    17,597,960 rows, every one well_completion_pool, not one entity_type = well among them.
    """
    with seeded.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id from canonical.production_monthly limit 1"
        )
        manifest_id, derivation_id = cursor.fetchone()
    seed_well(
        seeded,
        api10=NM_API10,
        state_code="30",
        county_code_at_permit="015",
        ndic_file_no=None,
        basin="permian",
        land_unit_label=None,
        status_canonical=None,
        status_reported="A",
        well_type_reported="O",
        well_name="MEWBOURNE 22 FEDERAL COM 1H",
        operator_name_reported="MEWBOURNE OIL COMPANY",
        manifest_id=manifest_id,
        derivation_id=derivation_id,
    )
    seed_well_spatial(
        seeded,
        api10=NM_API10,
        geom_type="surface",
        wkt=NM_SURFACE,
        manifest_id=manifest_id,
        derivation_id=derivation_id,
    )
    with seeded.cursor() as cursor:
        cursor.executemany(
            "insert into canonical.production_monthly (api10, entity_type, entity_key,"
            " reporting_level, well_completion_pool, production_month, stream, source_id,"
            " report_vintage, volume, unit, granularity, value_hash, null_semantics,"
            " source_manifest_id, derivation_id)"
            " values (%(api10)s, 'well_completion_pool', %(entity_key)s, 'well_completion_pool',"
            " %(pool)s, %(month)s, %(stream)s, 'nm_ocd_wcproduction', %(vintage)s, %(volume)s,"
            " %(unit)s, 'well_observed', %(value_hash)s, 'reported', %(manifest_id)s,"
            " %(derivation_id)s)",
            [
                {
                    "api10": NM_API10,
                    "entity_key": f"{NM_API10}:{NM_POOL}",
                    "pool": NM_POOL,
                    "month": month,
                    "stream": stream,
                    "vintage": NM_VINTAGE,
                    "volume": Decimal("101.500"),
                    "unit": unit,
                    "value_hash": "e" * 64,
                    "manifest_id": manifest_id,
                    "derivation_id": derivation_id,
                }
                for month in NM_MONTHS
                for stream, unit in (("oil", "bbl"), ("gas", "mcf"), ("water", "bbl"))
            ],
        )
        cursor.execute(
            "insert into lineage.quarantine_rows (quarantine_id, row_fingerprint, source_id,"
            " staging_table, stage, reason_code, rule_id, row_payload, first_seen_at,"
            " first_seen_manifest_id, last_seen_at, last_seen_manifest_id, occurrence_count,"
            " state) values ('qtn_nm_coord', %s, 'nm_ocd_wellhistory',"
            " 'staging.stg_nm_ocd_wellhistory__records', 'validate', 'coordinate_sentinel',"
            " 'cr_nm_wellhistory_coordinate_1', %s, now(), %s, now(), %s, 4, 'open')",
            ("c" * 64, Jsonb({"api10": "3001599009"}), manifest_id, manifest_id),
        )
    seeded.commit()
    return client


@pytest.fixture
def with_the_rollup(
    with_new_mexico: TestClient, seeded: psycopg.Connection, lineage_env
) -> TestClient:
    """The same well, after the rollup mart has been built from its pool filings.

    The mart is built here rather than assumed, because a served sum with no mart behind it is
    the state an instance is in between `make deploy` and the refresh, and that state has its
    own answer: the panel, which the case below still asserts.
    """
    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env):
        refresh_well_pool_rollup(seeded)
    seeded.commit()
    return with_new_mexico


@pytest.fixture
def with_a_zero_month(
    with_new_mexico: TestClient, seeded: psycopg.Connection, lineage_env
) -> TestClient:
    """A third month whose only filing is an explicit zero, and only for oil.

    The fixture above files `reported` in every month and every stream, so the served token is
    right by construction whatever the arm does. Two of the four states the card's legend
    advertises are only reachable through a month like this one: an explicit zero the regulator
    filed, and a stream that filed nothing in a month the well has.
    """
    with seeded.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id from canonical.production_monthly limit 1"
        )
        manifest_id, derivation_id = cursor.fetchone()
        cursor.execute(
            "insert into canonical.production_monthly (api10, entity_type, entity_key,"
            " reporting_level, well_completion_pool, production_month, stream, source_id,"
            " report_vintage, volume, unit, granularity, value_hash, null_semantics,"
            " source_manifest_id, derivation_id)"
            " values (%s, 'well_completion_pool', %s, 'well_completion_pool', %s, %s, 'oil',"
            " 'nm_ocd_wcproduction', %s, 0, 'bbl', 'well_observed', %s, 'reported_zero', %s, %s)",
            (
                NM_API10, f"{NM_API10}:{NM_POOL}", NM_POOL, ZERO_MONTH,
                ZERO_VINTAGE, "f" * 64, manifest_id, derivation_id,
            ),
        )
    seeded.commit()
    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env):
        refresh_well_pool_rollup(seeded)
    seeded.commit()
    return with_new_mexico


@pytest.fixture
def with_a_month_its_pools_filed_no_number_for(
    with_new_mexico: TestClient, seeded: psycopg.Connection, lineage_env
) -> TestClient:
    """A fourth month where oil is filed, gas says `no_report` and water says `withheld`.

    The sum admits neither of the last two, so both reach the arm through the same door, in a
    month the axis holds because oil filed. `withheld` has no New Mexico producer today
    (`nm_ocd.py:139`) but is in the store's own jurisdiction-neutral vocabulary, and filing both
    tokens in one month is the only way to tell a served token from a served constant.
    """
    with seeded.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id from canonical.production_monthly limit 1"
        )
        manifest_id, derivation_id = cursor.fetchone()
        cursor.executemany(
            "insert into canonical.production_monthly (api10, entity_type, entity_key,"
            " reporting_level, well_completion_pool, production_month, stream, source_id,"
            " report_vintage, volume, unit, granularity, value_hash, null_semantics,"
            " source_manifest_id, derivation_id)"
            " values (%(api10)s, 'well_completion_pool', %(entity_key)s, 'well_completion_pool',"
            " %(pool)s, %(month)s, %(stream)s, 'nm_ocd_wcproduction', %(vintage)s, %(volume)s,"
            " %(unit)s, 'well_observed', %(value_hash)s, %(semantics)s, %(manifest_id)s,"
            " %(derivation_id)s)",
            [
                {
                    "api10": NM_API10,
                    "entity_key": f"{NM_API10}:{NM_POOL}",
                    "pool": NM_POOL,
                    "month": NO_NUMBER_MONTH,
                    "stream": stream,
                    "vintage": NO_NUMBER_VINTAGE,
                    # canonical.volume is NOT NULL, so an unfiled volume is carried as zero and
                    # null_semantics is all that separates it from a filed one (nm_ocd.py:858).
                    "volume": volume,
                    "unit": unit,
                    "value_hash": digit * 64,
                    "semantics": semantics,
                    "manifest_id": manifest_id,
                    "derivation_id": derivation_id,
                }
                for stream, unit, volume, semantics, digit in (
                    ("oil", "bbl", Decimal("55.000"), "reported", "1"),
                    ("gas", "mcf", Decimal("0"), "no_report", "2"),
                    ("water", "bbl", Decimal("0"), "withheld", "3"),
                )
            ],
        )
    seeded.commit()
    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env):
        refresh_well_pool_rollup(seeded)
    seeded.commit()
    return with_new_mexico


def body(client: TestClient, path: str, **params) -> dict:
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_new_mexico_well_resolves_rather_than_404ing(with_new_mexico: TestClient) -> None:
    """The gate, from the serving side."""
    data = body(with_new_mexico, f"/v1/wells/{NM_API10}")["data"]

    assert data["api10"] == NM_API10
    assert data["state_code"] == "30"


def test_the_status_vocabulary_rule_is_new_mexicos(with_new_mexico: TestClient) -> None:
    summary = body(
        with_new_mexico, "/v1/wells/status-summary", bbox="-104.5,31.5,-103.0,32.8"
    )["data"]
    basins = {row["state_code"]: row for row in summary["basins"]}

    assert basins["30"]["status_vocabulary_rule"] == "cr_nm_wellhistory_status_vocab_2"
    assert "cr_nm_wellhistory_status_vocab_2" in summary["vocabulary_rules"]


def test_no_status_vocabulary_unavailable_warning_is_emitted_for_new_mexico(
    with_new_mexico: TestClient,
) -> None:
    """`wells.py` warns for every state its mapping does not carry; 30 is now carried."""
    envelope = body(with_new_mexico, "/v1/wells/status-summary", bbox="-104.5,31.5,-103.0,32.8")
    codes = {item["code"] for item in envelope["meta"].get("warnings", [])}

    assert "status_vocabulary_unavailable" not in codes


def test_every_pinned_status_rule_resolves_to_a_seeded_row_that_decides_a_vocabulary(
    client: TestClient,
) -> None:
    """Stronger than a kind check: a `vocab_map` must name the table it maps through, and a
    declaration must say in its own spec that no mapping exists. Both are decisions about the
    status vocabulary; only one of them is a mapping."""
    for state_code in sorted(prefixes_registering("status_vocabulary")):
        rule_id = declared_rule(state_code, "status_vocabulary")
        response = client.get(f"/v1/conformance/{rule_id}")
        assert response.status_code == 200, (state_code, rule_id)
        rule = response.json()["data"]

        assert rule["rule_kind"] in {"vocab_map", "parse_directive"}, rule_id
        if rule["rule_kind"] == "vocab_map":
            assert rule["spec"].get("mapping_table"), rule_id
        else:
            assert rule["spec"].get("mapping_table") is None, rule_id
            assert rule["spec"].get("status_canonical") is None, rule_id
            assert rule["spec"].get("measured_domain"), rule_id


def test_the_geometry_provenance_rule_is_new_mexicos(with_new_mexico: TestClient) -> None:
    envelope = body(with_new_mexico, "/v1/wells/status-summary", bbox="-104.5,31.5,-103.0,32.8")

    assert envelope["data"]["geometry_provenance"]
    assert (
        envelope["links"]["cr_nm_wellhistory_geometry_provenance_1"]
        == "/v1/conformance/cr_nm_wellhistory_geometry_provenance_1"
    )
    assert "cr_nd_geometry_provenance_1" not in envelope["links"]


def test_every_registered_provenance_rule_resolves(client: TestClient) -> None:
    for rule_id in sorted(declared_rule_ids("geometry_provenance")):
        assert client.get(f"/v1/conformance/{rule_id}").status_code == 200, rule_id


def test_the_pool_series_cites_new_mexicos_grain_rule_not_north_dakotas(
    with_new_mexico: TestClient,
) -> None:
    envelope = body(with_new_mexico, f"/v1/wells/{NM_API10}/production/pools")

    assert (
        envelope["links"]["aggregation_rule"]
        == "/v1/conformance/cr_nm_wcproduction_pool_rollup_2"
    )
    assert "cr_nd_pool_rollup_1" not in envelope["links"]["aggregation_rule"]


def test_the_grain_rule_the_pool_series_links_is_a_registry_row(
    with_new_mexico: TestClient, seeded: psycopg.Connection
) -> None:
    """§4: the grain rule comes from the row. Restating New Mexico's registration moves the
    link, which no `ROLLUP_RULES` entry could have done."""
    restate(seeded, "NM", rules={"production_grain": "cr_nm_wcproduction_amend_ind_1"})

    envelope = body(with_new_mexico, f"/v1/wells/{NM_API10}/production/pools")

    assert (
        envelope["links"]["aggregation_rule"]
        == "/v1/conformance/cr_nm_wcproduction_amend_ind_1"
    )


def test_every_pool_cell_the_card_draws_a_ring_on_resolves(
    with_new_mexico: TestClient,
) -> None:
    """The pool table is the same table the chart draws, so its cells compose the same
    `<column handle>&pm=<month>` selector. On a pool-grain well this table is the whole
    record, and a cell whose ⌾ does not resolve is R8's "untraceable equals wrong"."""
    data = body(with_new_mexico, f"/v1/wells/{NM_API10}/production/pools")["data"]

    checked = 0
    for index, pool in enumerate(data["pools"]):
        prefix = f"pools.{index}.series."
        for column in ("oil_bbl", "gas_mcf", "water_bbl"):
            values = pool["series"].get(column)
            if values is None:
                continue
            shared = data["_lineage"].get(f"{prefix}{column}")
            for at, month in enumerate(pool["series"]["pm"]):
                if values[at] is None:
                    continue
                handle = data["_lineage"].get(f"{prefix}{column}.{at}") or shared
                assert handle is not None, f"{column} {month} is drawn with no handle"
                point = handle if "&pm=" in handle else f"{handle}&pm={month}"
                answer = with_new_mexico.get("/v1/explain", params={"h": point, "depth": "1"})
                assert answer.status_code == 200, f"{column} {month}: {answer.text}"
                checked += 1
    assert checked > 0


def test_the_liquids_basis_on_a_new_mexico_oil_figure_is_new_mexicos(
    with_new_mexico: TestClient,
) -> None:
    """New Mexico reports condensate as its own stream (cr_nm_wcproduction_liquids_1), so its
    oil is oil as filed. Serving North Dakota's oil+condensate here would be a liquids policy
    with no New Mexico row behind it, on a sidecar `lineage/envelope.py` makes mandatory."""
    data = body(with_new_mexico, f"/v1/wells/{NM_API10}/production/pools")["data"]
    basis = data["_basis"]

    assert set(basis.values()) == {"oil", "water"}
    assert "oil+condensate" not in str(basis)
    assert any(key.endswith("oil_bbl") for key in basis)
    assert data["pools"][0]["series"]["oil_bbl"]


def test_a_new_mexico_well_is_served_the_sum_of_its_pool_filings_and_says_it_is_one(
    with_the_rollup: TestClient,
) -> None:
    """The card-track case for the pool-grain panel, amended where this track falsifies it.

    It asserted that a New Mexico well shows a titled panel naming
    cr_nm_wcproduction_pool_rollup_1 and linking down to the Pools section. After the rollup
    mart the well has a series, so what it must say instead is that the series is a sum: the
    warning names the successor, the chart is drawn rather than replaced, and the link down to
    the filings is still there. The panel keeps its own arm, asserted below on a rule that
    registers no rollup, which is the state a sixth pool-grain jurisdiction arrives in.
    """
    envelope = body(with_the_rollup, f"/v1/wells/{NM_API10}/production")
    warnings = {item["code"]: item for item in envelope["meta"].get("warnings", [])}

    assert envelope["data"]["series"]["pm"] == ["2026-05", "2026-06"]
    assert "production_reported_at_pool_grain" not in warnings
    summed = warnings["production_summed_over_pools"]
    assert summed["rule_id"] == "cr_nm_wcproduction_pool_rollup_2"
    assert "cr_nm_wcproduction_pool_rollup_2" in summed["detail"]
    assert f"/v1/wells/{NM_API10}/production/pools" in summed["detail"]
    assert envelope["links"]["pools"] == f"/v1/wells/{NM_API10}/production/pools"
    assert (
        envelope["links"]["aggregation_rule"]
        == "/v1/conformance/cr_nm_wcproduction_pool_rollup_2"
    )
    assert envelope["data"]["reporting_level"] == "well_completion_pool"
    assert envelope["data"]["series"]["oil_bbl_aggregation"] == ["sum_over_pools"] * 2


def test_a_summed_month_whose_filings_were_all_zero_is_served_as_a_filed_zero(
    with_a_zero_month: TestClient,
) -> None:
    """H-3, measured on the deployed spine at 901,568 served points over 43,921 wells.

    The arm wrote the constant `reported` for every month that had a mart row, so an explicit
    zero the regulator filed rendered "The operator reported a volume for this month" -- and
    `format.ts:47` states the client's own invariant that the four states are never collapsed
    into one another. The mart sums `reported` and `reported_zero` alike, so the distinction is
    not in the mart and has to be re-read from the filings the sum was taken over.
    """
    series = body(with_a_zero_month, f"/v1/wells/{NM_API10}/production")["data"]["series"]
    months = series["pm"]
    zero = months.index("2026-07")

    assert months == ["2026-05", "2026-06", "2026-07"]
    assert series["oil_bbl"][zero] == "0.000"
    assert series["oil_bbl_null_semantics"] == ["reported", "reported", "reported_zero"]


def test_a_stream_with_no_filing_in_a_served_month_says_no_report_not_null(
    with_a_zero_month: TestClient,
) -> None:
    """NIT-3. A null token falls through `format.ts` to gw-state-unknown, which style.css
    paints in the gas red, and `keyStates()` skips a null so the key never gains a row for it:
    a mark on the band with nothing in the key to read it by."""
    series = body(with_a_zero_month, f"/v1/wells/{NM_API10}/production")["data"]["series"]

    assert series["gas_mcf"][2] is None
    assert series["gas_mcf_null_semantics"] == ["reported", "reported", "no_report"]
    assert series["water_bbl_null_semantics"] == ["reported", "reported", "no_report"]
    assert None not in series["gas_mcf_null_semantics"]


def test_a_summed_month_whose_filings_all_say_no_report_is_not_called_withheld(
    with_a_month_its_pools_filed_no_number_for: TestClient,
) -> None:
    """H-12. The arm inferred `withheld` from the sum admitting no filing, so on the only
    jurisdiction it serves -- one that files no `withheld` at all -- a stream that filed no
    number was served as one the operator held back. `format.ts:47` is the client's invariant
    that the four states are never collapsed, and the token that keeps them apart is in the
    filings: this month carries both unadmitted tokens, so a constant cannot answer it.
    """
    series = body(
        with_a_month_its_pools_filed_no_number_for, f"/v1/wells/{NM_API10}/production"
    )["data"]["series"]
    month = series["pm"].index("2026-08")

    assert series["pm"] == ["2026-05", "2026-06", "2026-08"]
    assert [series["gas_mcf"][month], series["water_bbl"][month]] == [None, None]
    assert series["oil_bbl_null_semantics"][month] == "reported"
    assert series["gas_mcf_null_semantics"][month] == "no_report"
    assert series["water_bbl_null_semantics"][month] == "withheld"


def test_every_point_of_a_summed_series_carries_its_own_months_vintage(
    with_a_zero_month: TestClient,
) -> None:
    """H-7. One scalar for the well was written onto every point of a field documented per
    point, so the first OCD restatement would date every month at the restated month's vintage.
    Both the observed arm and the allocated arm serve the month's own."""
    series = body(with_a_zero_month, f"/v1/wells/{NM_API10}/production")["data"]["series"]

    assert series["oil_bbl_report_vintage"] == ["2026-08-20", "2026-08-20", "2026-08-25"]
    assert series["gas_mcf_report_vintage"] == ["2026-08-20", "2026-08-20", None]


def test_every_point_of_the_summed_series_resolves_to_the_refresh_that_produced_it(
    with_the_rollup: TestClient, seeded: psycopg.Connection
) -> None:
    """One derivation for the series is coarser than one per month, which is why the address is
    not: each point carries col, api10 and pm, and every one of them resolves."""
    envelope = body(with_the_rollup, f"/v1/wells/{NM_API10}/production")
    handles = [
        value for key, value in envelope["data"]["_lineage"].items()
        if key.startswith("series.oil_bbl")
    ]

    assert len(handles) == 2
    # Fail-closed: the shape that may address a summed point is a registered profile, so a
    # handle the registry does not admit resolves to a refusal rather than to a figure.
    resolved = with_the_rollup.get(
        "/v1/explain", params={"h": handles[0], "depth": 3}
    )
    assert resolved.status_code == 200, resolved.text
    assert handles[0].split("#")[0] in resolved.text

    with seeded.cursor() as cursor:
        cursor.execute("select distinct derivation_id from marts.well_pool_rollup")
        refreshes = {row[0] for row in cursor.fetchall()}
    assert {handle.split("#")[0] for handle in handles} == refreshes
    for index, month in enumerate(("2026-05", "2026-06")):
        assert handles[index].endswith(f"api10={NM_API10}&col=oil_bbl&pm={month}")


def test_as_of_is_refused_on_the_summed_series_with_a_stated_reason(
    with_the_rollup: TestClient,
) -> None:
    """HB-34 / H-5. The refusal was a 200 becoming a 4xx on a public surface with no test
    behind it, in no phase exit and in no changelog line. It is the right answer -- the mart
    holds one snapshot per key and the pool filings underneath it are bitemporal and answer
    as_of -- and it is asserted here in the shape the allocated arm's refusal already uses.

    It is also conditional on mart freshness by construction: this arm is only entered when the
    mart holds rows, so between a deploy and the first refresh the same request answers 200.
    The case below is the other side of that, on the same well before the refresh.
    """
    response = with_the_rollup.get(
        f"/v1/wells/{NM_API10}/production", params={"as_of": "2026-08-25"}
    )

    assert response.status_code == 422, response.text
    problem = response.json()
    assert problem["type"].endswith("as_of_not_supported")
    assert "one snapshot per key" in problem["detail"]
    assert "cr_nm_wcproduction_pool_rollup_2" in problem["detail"]
    assert f"/v1/wells/{NM_API10}/production/pools" in problem["detail"]


def test_the_same_request_is_answered_before_the_mart_is_refreshed(
    with_new_mexico: TestClient,
) -> None:
    """The freshness condition, stated as a served fact rather than left to be discovered: on
    an instance whose rollup mart is empty the well still answers as_of, because there is no
    sum to date wrongly. Two answers to one request, decided by a mart's build state."""
    response = with_new_mexico.get(
        f"/v1/wells/{NM_API10}/production", params={"as_of": "2026-08-25"}
    )

    assert response.status_code == 200, response.text


def test_a_per_foot_rate_is_refused_on_the_summed_arm_rather_than_ignored(
    with_the_rollup: TestClient, seeded: psycopg.Connection
) -> None:
    """H-6. The summed arm returned before `divisor` was consulted, so a caller asking for a
    per-foot rate was answered with the undivided sum under the plain unit. The allocated arm
    forty lines above refuses by name for the same reason and this one said nothing.

    A lateral is seeded because New Mexico registers no length_scope rule and holds surface
    points only, so the divisor refuses first today; the arm is live the moment a pool-grain
    jurisdiction with laterals registers a rollup, which this design advertises as a spec key.
    """
    seed_well_spatial(seeded, api10=NM_API10, geom_type="lateral")
    seeded.commit()

    answer = with_the_rollup.get(
        f"/v1/wells/{NM_API10}/production", params={"normalization": "per_lateral_ft"}
    )

    assert answer.status_code == 422, answer.text
    detail = answer.json()["detail"]
    assert "cr_nm_wcproduction_pool_rollup_2" in detail
    assert "not a per-foot rate anybody measured" in detail


def test_a_registered_well_whose_filings_the_mart_admits_none_of_keeps_the_panel(
    with_new_mexico: TestClient,
) -> None:
    """BLOCKER-1, on a served response from a registered jurisdiction rather than on a branch.

    New Mexico registers a served rollup, so before the mart is refreshed -- and for every well
    whose filings the sum admits none of, which on the deployed spine is every well that filed
    only withheld months -- there is no sum. The card gates its Production-by-pool section on
    this code, so serving the summed code here removed that section from a well whose whole
    production record is in it, and the reader was shown `No production reported.` instead.
    """
    envelope = body(with_new_mexico, f"/v1/wells/{NM_API10}")
    warnings = {item["code"]: item for item in envelope["meta"].get("warnings", [])}

    assert "production_summed_over_pools" not in warnings
    disclosure = warnings["production_reported_at_pool_grain"]
    assert disclosure["rule_id"] == "cr_nm_wcproduction_pool_rollup_2"
    assert "none of this well's are admitted into that sum" in disclosure["detail"]
    assert disclosure["pointer"] == "/producing"


def test_the_two_envelopes_agree_on_which_pool_grain_state_a_well_is_in(
    with_new_mexico: TestClient,
) -> None:
    """The card reads the well's warnings for its sections and the series' for its chart, so
    the two disagreeing is two answers to one question on one screen. They did: the well said
    a sum was served for a well the mart holds no row for, while /production said the panel."""
    well = body(with_new_mexico, f"/v1/wells/{NM_API10}")
    series = body(with_new_mexico, f"/v1/wells/{NM_API10}/production")
    codes = {"production_reported_at_pool_grain", "production_summed_over_pools"}

    assert {
        item["code"] for item in well["meta"].get("warnings", [])
    } & codes == {
        item["code"] for item in series["meta"].get("warnings", [])
    } & codes


def test_a_registered_well_that_filed_nothing_below_it_is_told_of_no_sum(
    with_the_rollup: TestClient, seeded: psycopg.Connection
) -> None:
    """MAJOR-1. The disclosure fired on the registration, so a New Mexico well with no pool
    filing at all was told the served series is glasswell's sum of those filings and that the
    filings are served separately -- naming a surface the same response declines to link,
    about filings that do not exist."""
    quiet = "3001599002"
    with seeded.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id from canonical.production_monthly limit 1"
        )
        manifest_id, derivation_id = cursor.fetchone()
    seed_well(
        seeded,
        api10=quiet,
        state_code="30",
        county_code_at_permit="015",
        ndic_file_no=None,
        basin="permian",
        land_unit_label=None,
        status_canonical=None,
        status_reported="A",
        well_name="CHAVES NO POOLS 1",
        manifest_id=manifest_id,
        derivation_id=derivation_id,
    )
    seeded.commit()

    envelope = body(with_the_rollup, f"/v1/wells/{quiet}")
    codes = {item["code"] for item in envelope["meta"].get("warnings", [])}

    assert envelope["data"]["producing"] == "unknown"
    assert "production_summed_over_pools" not in codes
    assert "production_reported_at_pool_grain" not in codes
    assert "pools" not in envelope["links"]


def test_the_panel_is_still_what_a_pool_grain_jurisdiction_with_no_rollup_is_served(
) -> None:
    """The other arm, asserted where it is decided rather than through a planted registration:
    no resident jurisdiction files at pool grain and registers no rollup any more, and the body
    a sixth one would get is the panel, with its own words intact."""
    from glasswell.api.routers.wells import reported_at_pool_grain

    unrolled = reported_at_pool_grain(
        {
            "rule_id": "cr_xx_pool_grain_1",
            "rule": "files per completion pool",
            "reporting_level": "well_completion_pool",
            "effective_from": date(2026, 1, 1),
            "published_vintage": date(2026, 1, 1),
            "served_rollup": None,
        },
        filings=True,
        summed=False,
    )
    rolled = reported_at_pool_grain(
        {
            "rule_id": "cr_nm_wcproduction_pool_rollup_2",
            "rule": "files per completion pool, summed in the mart layer",
            "reporting_level": "well_completion_pool",
            "effective_from": date(2026, 9, 3),
            "published_vintage": date(2026, 9, 3),
            "served_rollup": "sum_over_pools",
        },
        filings=True,
        summed=True,
    )

    assert unrolled["code"] == "production_reported_at_pool_grain"
    assert "glasswell performs no rollup to the well" in unrolled["detail"]
    assert rolled["code"] == "production_summed_over_pools"
    assert "performs no rollup" not in rolled["detail"]


def test_a_new_mexico_well_is_producing_unknown_and_the_reason_is_disclosed(
    with_the_rollup: TestClient,
) -> None:
    """`unknown` is the safe value and the wrong story without the reason.

    marts/producing.py evaluates `entity_type = 'well'` and New Mexico has none, so an NM well
    that filed 17.6M pool rows would otherwise be reported under a field whose description
    offers only "filed nothing", "withheld" and "reports at the lease" — none of which is true
    of it.

    On the rollup fixture, because the summed sentence is what a well the mart serves is owed
    and this case is about the well that has one; the two the mart does not serve are asserted
    above.
    """
    envelope = body(with_the_rollup, f"/v1/wells/{NM_API10}")
    warnings = {item["code"]: item for item in envelope["meta"].get("warnings", [])}

    assert envelope["data"]["producing"] == "unknown"
    # The reason moved with the mart and the code moved with it: `card.ts:428` replaces the
    # chart with a panel for the pool-grain code, and a New Mexico well now has a chart to draw.
    assert "production_reported_at_pool_grain" not in warnings
    disclosure = warnings["production_summed_over_pools"]
    assert "cr_nm_wcproduction_pool_rollup_2" in disclosure["detail"]
    assert "canonical holds no well-grain row" in disclosure["detail"]
    assert disclosure["pointer"] == "/producing"


def test_the_reason_comes_from_the_registry_not_from_a_state_code_in_the_path(
    seeded: psycopg.Connection,
) -> None:
    """Both causes of an absent well-level series resolve from `lineage.conformance_rules`."""
    from glasswell.lineage.conformance import lease_reporting_rule, pool_grain_rule
    from glasswell.marts.producing import no_well_series_states

    assert pool_grain_rule(seeded, "30") is not None
    assert pool_grain_rule(seeded, "33") is None
    # Texas's absence is the lease reason, not this one; the two must not collapse.
    assert pool_grain_rule(seeded, "42") is None
    assert "30" in no_well_series_states(seeded)
    assert "33" not in no_well_series_states(seeded)
    if lease_reporting_rule(seeded, "42") is not None:
        assert "42" in no_well_series_states(seeded)


def test_a_north_dakota_well_carries_no_pool_grain_disclosure(client: TestClient) -> None:
    """The regression half: ND rolls up under cr_nd_pool_rollup_1, so the reason does not apply."""
    envelope = body(client, f"/v1/wells/{EXAMPLE_API10}")
    codes = {item["code"] for item in envelope["meta"].get("warnings", [])}

    assert "production_reported_at_pool_grain" not in codes


def test_the_pool_figures_selector_validates_at_the_pool_grain(
    with_new_mexico: TestClient, seeded: psycopg.Connection
) -> None:
    """The last `entity_type = 'well'` predicate in a serving path, checked rather than argued.

    `selector_registry` branches: an api10 selector validates at well grain and an entity_key
    selector at well_completion_pool grain. New Mexico's pool series carries the second, so the
    output gate resolves it instead of counting zero rows at a grain New Mexico never files.
    """
    data = body(with_new_mexico, f"/v1/wells/{NM_API10}/production/pools")["data"]
    handles = [
        handle for key, handle in data["_lineage"].items() if key.startswith("pools.0.series.")
    ]

    assert handles
    for handle in handles:
        derivation_id, _, selector = handle.partition("#")
        assert derivation_id.startswith("drv_")
        assert selector.startswith("entity_key="), selector
        assert "api10=" not in selector, selector
    # Every point resolves; the gate that would refuse an unregistered selector runs on the way
    # out of the endpoint, so a 200 with these handles is the proof.
    assert data["reporting_level"] == "well_completion_pool"


def test_the_north_dakota_equivalents_are_unchanged(client: TestClient) -> None:
    """The regression half. A third key in a lookup is where the first two get lost."""
    data = body(client, f"/v1/wells/{EXAMPLE_API10}/production")["data"]

    assert data["_basis"]["series.oil_bbl"] == "oil+condensate"
    assert data["_basis"]["series.water_bbl"] == "water"
    assert declared_rule("33", "status_vocabulary") == "cr_nd_status_vocab_1"
    assert declared_rule("33", "production_grain") == "cr_nd_pool_rollup_1"
    assert declared_rule("33", "liquids") == "cr_nd_liquids_policy_1"
    assert declared_rule("33", "geometry_provenance") == "cr_nd_geometry_provenance_1"


def test_texas_now_registers_its_own_three_and_still_borrows_none(client: TestClient) -> None:
    """Inverted at v0.80, which is when Texas registered them (gate-tx H-4).

    The property is unchanged and is the point of the file: a rule Texas cites is a rule about
    Texas. It used to cite North Dakota's geometry provenance -- a rule about ND geometry
    served on a Texas well -- and R-4 asked for its own; the supersession registers it, along
    with the grain decision and the liquids policy the allocation needs.
    """
    data = body(client, f"/v1/wells/{TX_API10}")["data"]

    assert data["state_code"] == "42"
    assert declared_rule("42", "status_vocabulary") == "cr_tx_status_vocab_1"
    assert declared_rule("42", "geometry_provenance") == "cr_tx_geometry_provenance_1"
    assert declared_rule("42", "production_grain") == "cr_tx_production_grain_1"
    assert declared_rule("42", "liquids") == "cr_tx_liquids_basis_1"
    assert declared_rule("33", "geometry_provenance") == "cr_nd_geometry_provenance_1"


def test_a_state_with_no_registered_policy_gets_no_other_states_policy(
    seeded: psycopg.Connection,
) -> None:
    """The failure mode this phase exists to close, stated as a property of the resolvers.

    Re-targeted at v0.81: Texas registered both decisions and Montana registered the grain, so
    every resident registration now declares one and the only null left is `35`, a prefix no
    registration claims at all. An unregistered prefix is not an unregistered *registry*, which
    is why this is a null and not a refusal (gate-tx H-4).
    """
    from glasswell.api.routers.production import rollup_rule, stream_basis

    clear_jurisdiction_cache()
    registry = load_jurisdictions(seeded)

    assert registry.at_prefix("35") is None, "35 is claimed; pick a prefix that is not"
    assert stream_basis("oil", "35", registry=registry) is None
    assert stream_basis("oil", None, registry=registry) is None
    assert stream_basis("water", "35", registry=registry) == "water"
    assert stream_basis("gas", "33", registry=registry) is None
    assert stream_basis("oil", "33", registry=registry) == "oil+condensate"
    assert stream_basis("oil", "30", registry=registry) == "oil"
    # Montana's grain decision was registered on this train, so the resolver answers Montana's
    # own rule and not North Dakota's, which is the property the assertion was written for.
    assert rollup_rule("25", registry=registry) == "cr_mt_bogc_pool_rollup_1"
    assert rollup_rule("35", registry=registry) is None
    assert rollup_rule("30", registry=registry) == "cr_nm_wcproduction_pool_rollup_2"
    # Texas's own, and its own rule id: the same basis string as North Dakota's is not the
    # same decision, and this is the assertion that tells them apart.
    assert stream_basis("oil", "42", registry=registry) == "oil+condensate"
    assert rollup_rule("42", registry=registry) == "cr_tx_production_grain_1"


def test_the_new_mexico_quarantine_reason_is_servable_with_its_rule(
    with_new_mexico: TestClient,
) -> None:
    envelope = body(with_new_mexico, "/v1/quarantine", reason_code="coordinate_sentinel")
    rows = envelope["data"]["rows"] if "rows" in envelope["data"] else envelope["data"]

    assert rows
    assert any(
        row.get("rule_id") == "cr_nm_wellhistory_coordinate_1"
        for row in (rows if isinstance(rows, list) else [rows])
    )


def test_explain_resolves_a_new_mexico_figure_to_a_real_derivation(
    with_new_mexico: TestClient,
) -> None:
    envelope = body(with_new_mexico, f"/v1/wells/{NM_API10}/production/pools", explain="true")

    assert envelope["_explain"]


def test_the_well_card_serves_the_class_the_registry_resolves_and_not_a_null(
    with_new_mexico: TestClient,
) -> None:
    """The whole reason the resolver is below the API rather than in it: `marts.tile_nm_wells`
    and `/v1/wells/{api10}` read one view, so the map and the card cannot answer differently
    about the same well on the same screen."""
    detail = body(with_new_mexico, f"/v1/wells/{NM_API10}")["data"]

    assert detail["status_reported"] == "A"
    assert detail["status_canonical"] == "active"


def test_the_collection_filters_new_mexico_by_the_resolved_class(
    with_new_mexico: TestClient,
) -> None:
    """A filter that read the promoted column would return nothing for a class the map paints,
    which is the same defect as the tiles and the card disagreeing."""
    listed = body(with_new_mexico, "/v1/wells", status="active", state="30")["data"]

    assert [row["api10"] for row in listed] == [NM_API10]
    assert body(with_new_mexico, "/v1/wells", status="plugged", state="30")["data"] == []


def test_the_status_summary_counts_new_mexico_under_a_class_rather_than_as_unmapped(
    with_new_mexico: TestClient,
) -> None:
    summary = body(
        with_new_mexico, "/v1/wells/status-summary", bbox="-104.5,31.5,-103.0,32.8"
    )["data"]
    permian_nm = next(row for row in summary["basins"] if row["state_code"] == "30")

    assert [row["status"] for row in permian_nm["statuses"]] == ["active"]
    assert permian_nm["unmapped_wells"] is None


def test_the_status_facet_buckets_new_mexico_by_the_resolved_class(
    with_new_mexico: TestClient,
) -> None:
    """Wells-By reads the spine directly rather than the tile, so it needs the same join or a
    press on `Active` narrows the canvas and finds nothing to list."""
    buckets = body(
        with_new_mexico, "/v1/wells/facets", by="status", state="30"
    )["data"]["buckets"]

    assert [bucket["value"] for bucket in buckets] == ["active"]


def test_the_served_status_names_the_rule_that_decided_it_and_not_the_one_that_refused(
    with_new_mexico: TestClient,
) -> None:
    """R8, the handle rather than the value. An NM well's row derivation is the promotion's,
    which cites `_1` — the rule whose text says these letters map to nothing. The class was
    decided by `_2`, so `_2` is what the row names and what the reader can open."""
    envelope = body(with_new_mexico, f"/v1/wells/{NM_API10}")
    detail = envelope["data"]

    assert detail["status_canonical"] == "active"
    assert detail["status_vocabulary_rule"] == "cr_nm_wellhistory_status_vocab_2"
    assert envelope["links"]["status_rule"] == (
        "/v1/conformance/cr_nm_wellhistory_status_vocab_2"
    )
    assert (
        with_new_mexico.get("/v1/conformance/cr_nm_wellhistory_status_vocab_2").status_code
        == 200
    )


def test_the_collection_row_names_the_deciding_rule_too(with_new_mexico: TestClient) -> None:
    """The list row and the record answer with the same handle: a reader who never opens the
    card must not get a class with no rule behind it."""
    listed = body(with_new_mexico, "/v1/wells", status="active", state="30")["data"]

    assert [row["status_vocabulary_rule"] for row in listed] == [
        "cr_nm_wellhistory_status_vocab_2"
    ]


def test_the_other_states_still_name_their_own_status_rule(client: TestClient) -> None:
    """The regression half: a third key in a lookup is where the first two get lost."""
    nd = body(client, f"/v1/wells/{EXAMPLE_API10}")
    tx = body(client, f"/v1/wells/{TX_API10}")

    assert nd["data"]["status_vocabulary_rule"] == "cr_nd_status_vocab_1"
    assert nd["links"]["status_rule"] == "/v1/conformance/cr_nd_status_vocab_1"
    assert tx["data"]["status_vocabulary_rule"] == "cr_tx_status_vocab_1"


def test_the_well_response_links_the_pool_filings_where_the_regulator_files_by_pool(
    with_new_mexico: TestClient,
) -> None:
    """M-11: the card's section list is built from the well envelope, so the predicate the
    production response serves has to be on this one too -- as a link, which is what a
    section is gated on, rather than as a warning code the client has to recognise."""
    envelope = body(with_new_mexico, f"/v1/wells/{NM_API10}")

    assert envelope["links"]["pools"] == f"/v1/wells/{NM_API10}/production/pools"
    assert envelope["links"]["pools_rule"].startswith("/v1/conformance/cr_nm_")
    codes = {warning["code"] for warning in envelope["meta"]["warnings"]}
    assert "production_reported_at_pool_grain" in codes


def test_a_rolled_up_jurisdiction_serves_no_pools_link(with_new_mexico: TestClient) -> None:
    from glasswell.api.examples import EXAMPLE_API10

    links = body(with_new_mexico, f"/v1/wells/{EXAMPLE_API10}")["links"]

    assert "pools" not in links
    assert "pools_rule" not in links
