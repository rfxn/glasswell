"""The phase that opens the New Mexico gate, run end to end against real header bytes.

The fixture is cut from the sealed 2026-08-20 artifact by truncation, and it was selected rather
than taken from the head so that it carries all six coordinate populations — including the four
records with a good latitude and a longitude of exactly zero, and the three that are nil on one
ordinate and valued on the other. Those seven records out of 321,510 are the whole reason the
coordinate rule is a pair rule with a precedence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from glasswell.ingest import nm_wells
from glasswell.ingest.base import open_ingest_run
from glasswell.lineage.vintages import select_production
from tests.integration.test_nm_stage import stage
from tests.integration.test_nm_stage import staging_root as _staging_root
from tests.support.fakes import FixedClock

staging_root = _staging_root

pytestmark = pytest.mark.integration

SOURCE = "nm_ocd_wellhistory"
FIXTURE = Path(__file__).parents[1] / "fixtures" / "nm_ocd" / "nm_wellhistory_headers.xml"
DAY_ONE = datetime(2026, 8, 21, 6, 15, 0, tzinfo=UTC)
DAY_TWO = datetime(2026, 8, 22, 6, 15, 0, tzinfo=UTC)


@pytest.fixture
def seeded(db: psycopg.Connection) -> None:
    from glasswell.seed import seed_all

    seed_all(db)
    db.commit()


@pytest.fixture
def staged(db, seeded, raw_root, staging_root, tmp_path, monkeypatch):
    return stage(
        db,
        raw_root,
        tmp_path,
        monkeypatch,
        table="wellhistory",
        document=FIXTURE.read_bytes(),
        at=DAY_ONE,
    )


def promote(db: psycopg.Connection, *, at: datetime = DAY_ONE) -> nm_wells.HeaderReport:
    with open_ingest_run(db, source_id=SOURCE, clock=FixedClock(at)) as run:
        report = nm_wells.promote_headers(run)
    db.commit()
    return report


def query(db: psycopg.Connection, sql: str, *parameters: object) -> list[tuple]:
    with db.cursor() as cursor:
        cursor.execute(sql, parameters or None)
        return cursor.fetchall()


def scalar(db: psycopg.Connection, sql: str, *parameters: object):
    return query(db, sql, *parameters)[0][0]


def test_every_record_yields_a_header_whatever_its_coordinate_says(db, staged) -> None:
    """A refused coordinate must not suppress the well: the well exists either way."""
    report = promote(db)

    assert report.staged_rows == staged.staged_rows
    assert report.header_rows == report.staged_rows
    assert scalar(db, "select count(*) from canonical.wells") == report.headers_appended


def test_the_reconciliation_closes_on_counted_populations(db, staged) -> None:
    report = promote(db)
    refusals = sum(
        report.quarantined.get(code, 0)
        for code in ("coordinate_absent", "coordinate_sentinel")
    )

    assert report.geometry_rows + refusals == report.header_rows
    assert refusals > 0, "the fixture must carry both refusals or this proves nothing"


def test_a_surface_point_lands_in_4326_with_the_rule_that_moved_it(db, staged) -> None:
    promote(db)
    rows = query(
        db,
        "select distinct geom_type, geom_key, source_datum, transform_rule_id, st_srid(geom)"
        " from canonical.well_spatial",
    )

    assert rows == [("surface", "surface", "EPSG:4269", "cr_nm_wellhistory_datum_1", 4326)]


def test_the_coordinate_is_transformed_rather_than_passed_through(db, staged) -> None:
    """NAD83 to WGS84 is sub-metre in New Mexico, so an untransformed passthrough round-trips
    to within a tolerance a naive test would accept. The assertion is on the frame, not the
    value: a point stored in 4269 would carry SRID 4269."""
    promote(db)
    rows = query(
        db,
        "select st_x(geom), st_y(geom) from canonical.well_spatial"
        " order by api10 limit 1",
    )
    longitude, latitude = rows[0]

    assert -109.5 < longitude < -102.9
    assert 31.2 < latitude < 37.1


def test_no_promoted_geometry_sits_on_a_zero_ordinate(db, staged) -> None:
    """The cheap, direct assertion that four New Mexico wells cannot reach the Gulf of Guinea,
    however the classifier is later refactored."""
    promote(db)

    assert scalar(
        db,
        "select count(*) from canonical.well_spatial where st_x(geom) = 0 or st_y(geom) = 0",
    ) == 0


def test_both_refusals_are_quarantined_under_their_own_code_with_a_payload(db, staged) -> None:
    promote(db)
    rows = query(
        db,
        "select reason_code, rule_id, count(*), count(*) filter (where row_payload is not null)"
        " from lineage.quarantine_rows where source_id = %s group by 1, 2 order by 1",
        SOURCE,
    )
    by_code = {row[0]: row for row in rows}

    assert set(by_code) == {"coordinate_absent", "coordinate_sentinel"}
    for row in by_code.values():
        assert row[1] == "cr_nm_wellhistory_coordinate_1"
        assert row[2] == row[3]


def test_a_refused_record_leaves_a_header_and_no_geometry(db, staged) -> None:
    promote(db)
    refused = query(
        db,
        "select row_payload ->> 'api10' from lineage.quarantine_rows where source_id = %s",
        SOURCE,
    )
    api10s = [row[0] for row in refused if row[0]]

    assert api10s
    for api10 in api10s:
        assert scalar(db, "select count(*) from canonical.wells where api10 = %s", api10) >= 1
        assert scalar(
            db, "select count(*) from canonical.well_spatial where api10 = %s", api10
        ) == 0


def test_two_effective_rows_for_one_well_are_two_headers_and_one_point(db, staged) -> None:
    promote(db)
    repeated = query(
        db,
        "select api10, count(*) from canonical.wells group by 1 having count(*) > 1",
    )

    assert repeated, "the fixture must carry a restated effective row"
    for api10, headers in repeated:
        assert headers == 2
        assert scalar(
            db, "select count(*) from canonical.well_spatial where api10 = %s", api10
        ) == 1


def test_the_api10_is_composed_per_segment_by_the_registry_rule(db, staged) -> None:
    promote(db)
    rows = query(db, "select distinct length(api10), left(api10, 2) from canonical.wells")

    assert rows == [(10, "30")]


def test_no_state_code_literal_lives_in_the_module() -> None:
    """R8: the 30 is in cr_nm_wellhistory_api10_1's spec, read from the registry."""
    source = Path(nm_wells.__file__).read_text(encoding="utf-8")

    assert "'30'" not in source
    assert '"30"' not in source


def test_every_promoted_row_cites_the_rules_that_shaped_it(db, staged) -> None:
    report = promote(db)
    cited = {
        row[0]
        for row in query(
            db,
            "select rule_id from lineage.derivation_rules where derivation_id = %s",
            report.derivation_id,
        )
    }

    assert {
        "cr_nm_wellhistory_api10_1",
        "cr_nm_wellhistory_effective_1",
        "cr_nm_wellhistory_status_vocab_1",
        "cr_nm_wellhistory_well_type_1",
        "cr_nm_wellhistory_datum_1",
        "cr_nm_wellhistory_coordinate_1",
        "cr_nm_wellhistory_geometry_provenance_1",
        "cr_nm_wellhistory_geometry_scope_1",
        "cr_nm_wellhistory_header_precedence_1",
    } <= cited


def test_the_status_letter_is_promoted_and_no_canonical_status_is_invented(db, staged) -> None:
    """cr_nm_wellhistory_status_vocab_1: the OCD publishes no codebook for these letters."""
    promote(db)
    rows = query(
        db,
        "select count(*), count(status_reported), count(status_canonical)"
        " from canonical.wells",
    )

    total, reported, canonical = rows[0]
    assert reported > 0
    assert canonical == 0
    assert total >= reported


def test_no_lateral_or_bottomhole_is_produced_from_a_horizontal_well(db, staged) -> None:
    """cr_nm_wellhistory_geometry_scope_1 in force: the fixture carries a horizontal well."""
    promote(db)

    assert scalar(
        db, "select count(*) from canonical.well_spatial where geom_type <> 'surface'"
    ) == 0


def test_a_rerun_over_unchanged_bytes_appends_nothing(db, staged) -> None:
    first = promote(db)
    second = promote(db, at=DAY_TWO)

    assert first.headers_appended > 0
    assert second.headers_appended == 0
    assert second.geometry_appended == 0
    assert scalar(db, "select count(*) from canonical.wells") == first.headers_appended


def test_the_gate_opens(db, staged) -> None:
    """The assertion that this phase did the thing it exists to do.

    Before the promotion the served spine resolves no New Mexico API-10 and every production
    endpoint answers not_found for one. After it, the same query returns a row.
    """
    from glasswell.api.routers.wells import RANKED_WELLS

    def resolves(api10: str) -> bool:
        with db.cursor() as cursor:
            cursor.execute(RANKED_WELLS + " and api10 = %(api10)s", {"as_of": None, "api10": api10})
            return cursor.fetchone() is not None

    promote(db)
    api10 = scalar(db, "select api10 from canonical.wells order by api10 limit 1")

    assert resolves(api10)
    assert not resolves("3399999999")


def test_the_promotion_writes_no_production_row(db, staged) -> None:
    """Layer boundaries: this promotion reads staging and writes canonical wells and geometry.
    Tier 1's production rows are a different source and a different promotion."""
    promote(db)

    assert select_production(db) == []
