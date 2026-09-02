"""The Colorado header promotion: what reaches canonical, and what is held beside it.

The eighteen byte-identical duplicate rows are the subject of this file. They are the reason
Colorado can register `identity_is_unique = true` at all, and a promotion that dropped them
silently would be indistinguishable from one that had never seen them.
"""

from __future__ import annotations

import pytest

from glasswell.ingest import co_wells
from glasswell.ingest.base import open_ingest_run
from tests.integration.test_co_staging import seeded as _seeded
from tests.integration.test_co_staging import staged_gis as _staged_gis

# Bound under their own names rather than imported into the namespace: pytest resolves
# fixtures by name and an unbound import is dead to it, which is the idiom the New
# Mexico promotion tests use across the same seam.
seeded = _seeded
staged_gis = _staged_gis

pytestmark = pytest.mark.integration


@pytest.fixture
def promoted(staged_gis, seeded, lineage_env) -> co_wells.HeaderReport:
    with open_ingest_run(
        seeded, source_id=co_wells.SOURCE_ID, environment=lineage_env
    ) as run:
        report = co_wells.promote_headers(run)
    seeded.commit()
    return report


def test_every_staged_row_is_either_promoted_or_held_with_a_reason(promoted) -> None:
    """Nothing is dropped: the arithmetic closes over the staged rows."""
    assert promoted.rows_read == 118
    assert promoted.wells_appended == 100
    assert promoted.quarantined["duplicate_row"] == 18
    assert promoted.wells_appended + promoted.quarantined["duplicate_row"] == promoted.rows_read


def test_the_duplicate_count_is_exactly_the_measured_one_and_any_other_refuses(
    promoted,
) -> None:
    """A count other than eighteen means the archive changed shape, and that is a finding
    rather than a number to absorb."""
    assert promoted.quarantined["duplicate_row"] == 18
    assert promoted.quarantined["key_incomplete"] == 0


def test_the_row_kept_is_the_one_the_regulator_wrote_first(promoted, seeded) -> None:
    with seeded.cursor() as cursor:
        cursor.execute(
            "select row_payload->>'kept_source_row_ordinal', row_payload->>'source_row_ordinal'"
            "  from lineage.quarantine_rows where reason_code = 'duplicate_row'"
        )
        pairs = cursor.fetchall()

    assert pairs
    assert all(int(kept) < int(discarded) for kept, discarded in pairs)


def test_the_class_is_not_written_at_promotion_and_the_resolver_supplies_it(
    promoted, seeded
) -> None:
    """Read-time resolution, measured: the promotion writes the filed code and no class, and
    the registry's own view is what turns one into the other."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(*), count(status_canonical), count(status_reported)"
            "  from canonical.wells where source_manifest_id = %s",
            (promoted.manifest_id,),
        )
        rows, classed, reported = cursor.fetchone()
        cursor.execute(
            "select count(*) from canonical.wells w"
            "  join canonical.status_resolution r"
            "    on r.for_state_code = w.state_code"
            "   and r.for_status_reported = w.status_reported"
            " where w.source_manifest_id = %s",
            (promoted.manifest_id,),
        )
        resolvable = cursor.fetchone()[0]

    assert rows == 100
    assert classed == 0
    assert reported == 100
    assert resolvable == 100


def test_the_surface_geometry_lands_as_the_only_class_this_release_promotes(
    promoted, seeded
) -> None:
    with seeded.cursor() as cursor:
        cursor.execute(
            "select geom_type, count(*) from canonical.well_spatial"
            " where source_manifest_id = %s group by geom_type",
            (promoted.manifest_id,),
        )
        by_type = dict(cursor.fetchall())
        cursor.execute(
            "select distinct st_srid(geom) from canonical.well_spatial"
            " where source_manifest_id = %s",
            (promoted.manifest_id,),
        )
        srids = [row[0] for row in cursor.fetchall()]

    assert by_type == {"surface": 100}
    assert srids == [4326]
    assert promoted.geometry_appended == 100


def test_the_valid_time_is_the_status_date_and_a_second_run_appends_nothing(
    promoted, seeded, lineage_env
) -> None:
    """Append-only under a daily republication: the spine must not grow a row per pull."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(distinct effective_from) from canonical.wells"
            " where source_manifest_id = %s",
            (promoted.manifest_id,),
        )
        distinct_dates = cursor.fetchone()[0]
        cursor.execute("select count(*) from canonical.wells")
        before = cursor.fetchone()[0]

    with open_ingest_run(
        seeded, source_id=co_wells.SOURCE_ID, environment=lineage_env
    ) as run:
        co_wells.promote_headers(run)
    seeded.commit()

    with seeded.cursor() as cursor:
        cursor.execute("select count(*) from canonical.wells")
        after = cursor.fetchone()[0]

    assert distinct_dates > 1, "one effective_from for every well is a pull clock, not a filing"
    assert after == before


def test_the_promotion_reads_no_mart_and_writes_no_staging(promoted) -> None:
    from pathlib import Path

    from tests.support.layers import schema_reads_in

    assert schema_reads_in(Path(co_wells.__file__), "marts") == []
    assert schema_reads_in(Path(co_wells.__file__), "staging") == ["staging.co_ecmc_wells"]
