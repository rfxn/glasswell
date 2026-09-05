"""The Colorado staging ingests, against the ephemeral database and the sampled real archives.

Staging is the terminus for all four sources: the tests assert it in two ways, by reading what
the modules can name and by reading what the database holds after they run.
"""

from __future__ import annotations

import csv
from pathlib import Path

import httpx
import psycopg
import pytest

from glasswell.ingest import co_ecmc_gis as gis
from glasswell.ingest import co_ecmc_production as production
from glasswell.ingest.base import open_ingest_run
from glasswell.ingest.shapefile import UnknownProjection
from glasswell.seed import seed_all
from tests.support.layers import schema_reads_in

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parents[1] / "fixtures" / "co_ecmc"
ARCHIVES = {
    gis.WELLS.source_key: FIXTURES / "Wells_sample.zip",
    gis.BOTTOMHOLE.source_key: FIXTURES / "DirectionalBottomholeLocations_sample.zip",
    gis.LINES.source_key: FIXTURES / "DirectionalLines_sample.zip",
}
ROLLING = FIXTURES / "monthly_prod_sample.csv"
DRIFTED = FIXTURES / "prod_reports_2025_sample.csv"


def client_for(path: Path, media_type: str) -> httpx.Client:
    payload = path.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload, headers={"content-type": media_type})

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def seeded(db: psycopg.Connection) -> psycopg.Connection:
    seed_all(db)
    db.commit()
    return db


@pytest.fixture
def staged_gis(seeded, raw_root, lineage_env) -> dict[str, gis.LayerReport]:
    reports: dict[str, gis.LayerReport] = {}
    for layer in gis.LAYERS:
        with (
            open_ingest_run(
                seeded, source_id=layer.source_id, raw_root=raw_root, environment=lineage_env
            ) as run,
            client_for(ARCHIVES[layer.source_key], "application/zip") as client,
        ):
            reports[layer.name] = gis.ingest_layer(run, layer, client=client)
    seeded.commit()
    return reports


@pytest.fixture
def staged_rolling(seeded, raw_root, lineage_env) -> production.LoadReport:
    with (
        open_ingest_run(
            seeded,
            source_id=production.ROLLING_SOURCE_ID,
            raw_root=raw_root,
            environment=lineage_env,
        ) as run,
        client_for(ROLLING, "text/csv") as client,
    ):
        report = production.load(run, production.ROLLING, client=client)
    seeded.commit()
    return report


def count(connection: psycopg.Connection, table: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"select count(*) from {table}")
        return int(cursor.fetchone()[0])


def test_all_three_archives_stage_and_carry_their_geometry(staged_gis, seeded) -> None:
    assert {name: report.rows_staged for name, report in staged_gis.items()} == {
        "wells": 118,
        "bottomhole": 61,
        "lines": 60,
    }
    assert {report.source_epsg for report in staged_gis.values()} == {26913}
    for table in (
        "staging.co_ecmc_wells",
        "staging.co_ecmc_directional_bh",
        "staging.co_ecmc_directional_lines",
    ):
        with seeded.cursor() as cursor:
            cursor.execute(f"select count(*) from {table} where geom is not null")
            assert cursor.fetchone()[0] > 0
            cursor.execute(f"select distinct st_srid(geom) from {table} where geom is not null")
            assert [row[0] for row in cursor.fetchall()] == [4326]


def blank_text_columns(connection: psycopg.Connection, table: str) -> dict[str, int]:
    """Every text column of a staging table holding an empty string, counted, by shape."""
    schema, _, name = table.partition(".")
    with connection.cursor() as cursor:
        cursor.execute(
            "select column_name from information_schema.columns"
            " where table_schema = %s and table_name = %s and data_type = 'text'"
            "   and column_name <> 'manifest_id'"
            " order by ordinal_position",
            (schema, name),
        )
        columns = [row[0] for row in cursor.fetchall()]
        found: dict[str, int] = {}
        for column in columns:
            cursor.execute(f'select count(*) from {table} where "{column}" = %s', ("",))
            blanks = int(cursor.fetchone()[0])
            if blanks:
                found[column] = blanks
    return found


def test_a_blank_attribute_stages_as_absent_and_not_as_an_empty_string(
    staged_gis, seeded
) -> None:
    """cr_co_*_blank_is_absent_1, swept over the shape rather than over one column.

    ECMC is the only publisher in the registry whose DBFs carry an empty string where they
    carry no value, and an empty string is not a value: it is unaddressable in the selector
    grammar, it ranks as a class in a legend, and it is a different answer from the null every
    other jurisdiction stages. The three sampled archives carry blanks in Well_Class (10),
    Loc_Qual (4), Field_Name (61 and 60) and Deviation (3).
    """
    for table in (
        "staging.co_ecmc_wells",
        "staging.co_ecmc_directional_bh",
        "staging.co_ecmc_directional_lines",
    ):
        assert blank_text_columns(seeded, table) == {}

    with seeded.cursor() as cursor:
        cursor.execute("select count(*) from staging.co_ecmc_wells where well_class is null")
        assert cursor.fetchone()[0] == 10
        cursor.execute(
            "select count(*) from staging.co_ecmc_directional_lines where deviation is null"
        )
        assert cursor.fetchone()[0] == 3


def test_the_header_is_staged_verbatim_including_the_duplicate_rows(staged_gis, seeded) -> None:
    """Deduplication is the promotion's decision under its own rule. Staging holds every row
    the regulator filed, so the quarantine ledger can point at one."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(*), count(distinct (api_county, api_seq, facil_id, loc_id,"
            "       facil_stat, latitude, longitude))"
            "  from staging.co_ecmc_wells"
        )
        rows, distinct = cursor.fetchone()

    assert rows == 118
    assert rows - distinct == 18


def test_a_reprojected_archive_is_refused_rather_than_replotted(seeded) -> None:
    """cr_co_wells_datum_1 records the code the archives ship; a different one is a refusal."""
    with pytest.raises(UnknownProjection, match="EPSG"):
        gis.stage_layer(
            seeded,
            gis.WELLS,
            archive=ARCHIVES[gis.WELLS.source_key],
            manifest_id="probe",
            expected_epsg=32613,
            storage_epsg=4326,
            null_tokens=[""],
        )


def test_the_rolling_file_stages_every_row_with_its_null_tokens_removed(
    staged_rolling, seeded
) -> None:
    with ROLLING.open(newline="") as handle:
        expected = sum(1 for _ in csv.DictReader(handle))

    assert staged_rolling.rows_staged == expected
    assert count(seeded, "staging.co_ecmc_production") == expected
    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(*) from staging.co_ecmc_production where oilsales = 'NULL'"
            "    or revised = 'NULL' or oilproduced = ''"
        )
        assert cursor.fetchone()[0] == 0


def test_the_drifted_archive_stages_to_the_same_columns_as_the_rolling_file(
    staged_rolling, seeded, raw_root, lineage_env
) -> None:
    """The measurement the schema-drift rule exists for, run rather than asserted."""
    before = count(seeded, "staging.co_ecmc_production")
    with (
        open_ingest_run(
            seeded,
            source_id=production.ARCHIVE_SOURCE_ID,
            raw_root=raw_root,
            environment=lineage_env,
        ) as run,
        client_for(DRIFTED, "text/csv") as client,
    ):
        report = production.load(run, "2025", client=client)
    seeded.commit()

    assert report.rows_staged == 17
    assert count(seeded, "staging.co_ecmc_production") == before + 17
    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(*) from staging.co_ecmc_production"
            " where gasshrinkage is not null or bominvent is not null"
        )
        assert cursor.fetchone()[0] > 0
        # The received-year trap, in the database rather than in the rule's prose.
        cursor.execute(
            "select reportyear, reportmonth from staging.co_ecmc_production"
            " where manifest_id = %s order by source_row_ordinal limit 1",
            (report.manifest_id,),
        )
        assert cursor.fetchone() == ("2024", "11")


def test_staging_is_the_terminus_for_both_modules() -> None:
    """The layer boundary, read off the modules: a parser that could name a canonical relation
    is a parser that could write one."""
    for module in (gis, production):
        assert schema_reads_in(Path(module.__file__), "canonical") == []
        assert schema_reads_in(Path(module.__file__), "marts") == []


def test_both_mains_open_the_durable_fetch_ledger() -> None:
    for module in (gis, production):
        assert "durable_fetch_attempts(arguments.dsn)" in Path(module.__file__).read_text()


def test_the_multi_wellbore_share_is_measurable_from_staging_and_is_not_a_gate(
    staged_gis, seeded
) -> None:
    """R-4: blueprint §3.0.5 sets a 2% trigger on the quarantined multi-wellbore share, and
    Colorado's geometry archives measure 4.18% over the full files. The carry is accepted
    because the header spine is one row per API-10 and these layers are staged, not promoted,
    so the share is reported here rather than gating anything."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(*), count(distinct left(api_label, 12))"
            "  from staging.co_ecmc_directional_lines"
        )
        wellbores, wells = cursor.fetchone()

    assert wellbores > wells, "the fixture carries no multi-wellbore well; the carry is unproven"
    assert wellbores - wells == 1
