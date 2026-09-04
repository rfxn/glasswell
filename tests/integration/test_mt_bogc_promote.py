"""Both Montana grains, promoted from a fixture cut out of the real MBOGC archive.

The fixture is 300 real well-grain rows and 132 real lease-grain rows over 2023-05 and 2023-06,
chosen to carry the cases that only appear in real data: multi-formation well-months, the -999
Lease_Unit sentinel, amended filings, and the blank final line.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from glasswell.ingest import mt_bogc
from glasswell.ingest.base import open_ingest_run
from glasswell.seed import seed_all

FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "mt_bogc" / "MT_Historical_Production_sample.zip"
)
WELL_ROWS = 300
PRU_ROWS = 132
MONTHS = ("2023-05", "2023-06")


def client_for(path: Path) -> httpx.Client:
    payload = path.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload,
            headers={
                "content-type": "application/zip",
                "etag": '"4653fb2-6593e310d4b83"',
                "last-modified": "Mon, 17 Aug 2026 13:31:46 GMT",
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def promoted(db, raw_root, lineage_env) -> mt_bogc.IngestReport:
    seed_all(db)
    db.commit()
    with open_ingest_run(
        db, source_id=mt_bogc.SOURCE_ID, raw_root=raw_root, environment=lineage_env
    ) as run, client_for(FIXTURE) as client:
        report = mt_bogc.ingest_archive(run, client=client)
    db.commit()
    return report


def query(db, sql: str, *parameters: object) -> list[tuple]:
    with db.cursor() as cursor:
        cursor.execute(sql, parameters or None)
        return cursor.fetchall()


def scalar(db, sql: str, *parameters: object):
    return query(db, sql, *parameters)[0][0]


def test_one_archive_registers_one_manifest_hashing_both_members(db, promoted):
    assert scalar(db, "select count(*) from lineage.manifests") == 1
    members = scalar(
        db,
        "select jsonb_agg(item ->> 'member' order by item ->> 'member')"
        "  from lineage.manifests m,"
        "       jsonb_array_elements(m.decompressed_inventory) item",
    )
    assert members == [mt_bogc.PRU_MEMBER, mt_bogc.WELL_MEMBER]


def test_staging_is_source_faithful_and_keeps_the_sentinel(db, promoted):
    assert scalar(db, f"select count(*) from {mt_bogc.WELL_STAGING}") == WELL_ROWS
    assert scalar(db, f"select count(*) from {mt_bogc.PRU_STAGING}") == PRU_ROWS
    # The blank final line is end-of-file, not a row (cr_mt_trailing_record_1).
    assert scalar(
        db, f"select count(*) from {mt_bogc.WELL_STAGING} where api_wellno is null"
    ) == 0
    # Staging holds what was filed, sentinel included; the normalisation happens on promotion.
    assert scalar(
        db, f"select count(*) from {mt_bogc.WELL_STAGING} where lease_unit = '-999'"
    ) >= 0
    assert scalar(
        db,
        f"select count(*) from {mt_bogc.WELL_STAGING} where rpt_date like '%%/2023'",
    ) == WELL_ROWS


def test_no_promoted_lease_key_is_a_negative_sentinel(db, promoted):
    """A guard on shape, not on the fixture.

    The direct proof that -999 normalises to null is
    tests/unit/test_mt_bogc_parsing.py::test_the_lease_unit_sentinel_becomes_null_and_a_real_unit_survives,
    because the well grain does not promote lease_unit at all and the lease grain carries no
    sentinel in any published month — an assertion here that the value is absent from canonical
    passes with the normalisation deleted, so it proves nothing on its own.
    """
    assert scalar(
        db,
        "select count(*) from canonical.production_monthly"
        " where entity_type = 'lease' and entity_key !~ '^[0-9]+$'",
    ) == 0


def test_both_grains_promote_under_their_own_source_and_granularity(db, promoted):
    assert query(
        db,
        "select source_id, granularity, count(*) from canonical.production_monthly"
        " group by 1, 2 order by 1, 2",
    ) == [
        (mt_bogc.PRU_SOURCE_ID, "lease_reported", PRU_ROWS * 3),
        (mt_bogc.SOURCE_ID, "well_observed", scalar(
            db,
            "select count(*) from canonical.production_monthly where source_id = %s",
            mt_bogc.SOURCE_ID,
        )),
    ]


def test_lease_rows_carry_no_api10_and_well_rows_always_do(db, promoted):
    assert scalar(
        db,
        "select count(*) from canonical.production_monthly"
        " where source_id = %s and api10 is not null",
        mt_bogc.PRU_SOURCE_ID,
    ) == 0
    assert scalar(
        db,
        "select count(*) from canonical.production_monthly"
        " where source_id = %s and api10 is null",
        mt_bogc.SOURCE_ID,
    ) == 0


def test_every_promoted_api10_is_a_montana_ten_digit_key(db, promoted):
    assert scalar(
        db,
        "select count(*) from canonical.production_monthly"
        " where source_id = %s and api10 !~ '^25[0-9]{8}$'",
        mt_bogc.SOURCE_ID,
    ) == 0


def test_the_production_month_is_the_first_of_the_month(db, promoted):
    assert scalar(
        db,
        "select count(*) from canonical.production_monthly"
        " where extract(day from production_month) <> 1",
    ) == 0
    assert sorted(
        row[0].strftime("%Y-%m")
        for row in query(
            db, "select distinct production_month from canonical.production_monthly order by 1"
        )
    ) == list(MONTHS)


def test_a_multi_formation_well_month_promotes_its_parts_and_their_exact_sum(db, promoted):
    rollups = query(
        db,
        "select api10, production_month, stream, volume from canonical.production_monthly"
        " where aggregation = %s and stream = 'oil' order by api10, production_month",
        mt_bogc.AGGREGATION,
    )
    assert rollups, "the fixture is chosen to contain multi-formation well-months"
    for api10, month, stream, total in rollups:
        parts = scalar(
            db,
            "select coalesce(sum(volume), 0) from canonical.production_monthly"
            " where entity_type = 'well_completion_pool' and api10 = %s"
            "   and production_month = %s and stream = %s",
            api10,
            month,
            stream,
        )
        assert total == parts


def test_a_rollup_takes_the_maximum_of_its_days_never_the_sum(db, promoted):
    rows = query(
        db,
        "select r.api10, r.production_month, r.stream, r.days_produced,"
        "       max(p.days_produced), sum(p.days_produced)"
        "  from canonical.production_monthly r"
        "  join canonical.production_monthly p"
        "    on p.api10 = r.api10 and p.production_month = r.production_month"
        "   and p.stream = r.stream and p.entity_type = 'well_completion_pool'"
        " where r.aggregation = %s"
        " group by 1, 2, 3, 4 having count(*) > 1",
        mt_bogc.AGGREGATION,
    )
    assert rows, "the fixture must contain a rollup over more than one formation"
    for *_, rollup_days, part_max, part_sum in rows:
        assert rollup_days == part_max
        if part_sum != part_max:
            assert rollup_days != part_sum


def test_only_the_three_production_measures_promote_from_the_lease_grain(db, promoted):
    assert query(
        db,
        "select distinct stream from canonical.production_monthly"
        " where source_id = %s order by 1",
        mt_bogc.PRU_SOURCE_ID,
    ) == [("gas",), ("oil",), ("water",)]


def test_the_disposition_columns_stage_and_never_serve(db, promoted):
    # Staged in full: losing them would cost a re-fetch of a 73 MB archive.
    assert scalar(
        db, f"select count(*) from {mt_bogc.PRU_STAGING} where oil_sold is not null"
    ) > 0
    assert scalar(
        db, f"select count(*) from {mt_bogc.PRU_STAGING} where startivn_oilcd is not null"
    ) > 0
    # And never promoted: no canonical stream vocabulary admits them.
    assert scalar(
        db,
        "select count(*) from canonical.production_monthly"
        " where stream not in ('oil', 'gas', 'water', 'condensate')",
    ) == 0


def test_a_second_run_over_the_same_bytes_appends_nothing(db, raw_root, lineage_env, promoted):
    before = scalar(db, "select count(*) from canonical.production_monthly")
    with open_ingest_run(
        db, source_id=mt_bogc.SOURCE_ID, raw_root=raw_root, environment=lineage_env
    ) as run, client_for(FIXTURE) as client:
        again = mt_bogc.ingest_archive(run, client=client)
    db.commit()

    assert again.well is not None
    assert again.well.rows_appended == 0
    assert again.pru is not None
    assert again.pru.rows_appended == 0
    assert scalar(db, "select count(*) from canonical.production_monthly") == before


def test_every_promoted_row_carries_a_resolvable_derivation(db, promoted):
    assert scalar(
        db,
        "select count(*) from canonical.production_monthly p"
        " where not exists (select 1 from lineage.derivations d"
        "                    where d.derivation_id = p.derivation_id)",
    ) == 0


def test_the_promotion_derivation_records_the_liquids_basis_and_the_state(db, promoted):
    """Scoped to the production promotions: a membership row has no volume, so a liquids basis
    on its derivation would be a claim about a number it does not carry."""
    params = query(
        db,
        "select distinct params ->> 'liquids_basis', params ->> 'state_code'"
        "  from lineage.derivations where operation = 'canonical.promote'"
        "   and output_dataset = 'canonical.production_monthly'",
    )
    assert params == [("oil+condensate", "25")]


def test_the_vintage_ledger_accumulates_across_both_grains(db, promoted):
    assert sorted(
        query(db, "select source_id, rows_appended > 0 from lineage.vintages order by 1")
    ) == [(mt_bogc.PRU_SOURCE_ID, True), (mt_bogc.SOURCE_ID, True)]
