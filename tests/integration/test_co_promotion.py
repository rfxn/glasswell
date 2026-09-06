"""The Colorado header promotion: what reaches canonical, and what is held beside it.

The eighteen byte-identical duplicate rows are the subject of this file. They are the reason
Colorado can register `identity_is_unique = true` at all, and a promotion that dropped them
silently would be indistinguishable from one that had never seen them.
"""

from __future__ import annotations

import pytest

from glasswell.ingest import co_wells
from glasswell.ingest.base import open_ingest_run
from tests.integration.test_co_staging import blank_text_columns
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


def test_the_class_is_not_written_at_promotion_and_the_codebook_is_what_supplies_it(
    promoted, seeded
) -> None:
    """Read-time resolution, measured at the promotion's own end of it.

    The promotion writes the filed code and no class: `canonical.wells` is append-only and ECMC
    republishes nightly, so a class written here would invent a valid time the regulator never
    filed. The join that turns one into the other is asserted against the registered codebook
    rather than against `canonical.status_resolution`, because the resolver that serves that
    view belongs to the facets track and merges after this one -- what this file can prove is
    that every filed code has a row waiting for it.
    """
    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(*), count(status_canonical), count(status_reported)"
            "  from canonical.wells where source_manifest_id = %s",
            (promoted.manifest_id,),
        )
        rows, classed, reported = cursor.fetchone()
        cursor.execute(
            "select count(*) from canonical.wells w"
            "  join lineage.co_facility_status_map m on m.status = w.status_reported"
            "  join lineage.jurisdictions_as_of(current_date, current_date) j"
            "    on j.identity_prefix = w.state_code and j.jurisdiction_code = 'CO'"
            " where w.source_manifest_id = %s",
            (promoted.manifest_id,),
        )
        resolvable = cursor.fetchone()[0]

    assert rows == 100
    assert classed == 0
    assert reported == 100
    assert resolvable == 100, "a filed code with no codebook row would resolve to nothing"


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


def test_a_blank_left_in_staging_by_an_earlier_generation_promotes_as_absent(
    staged_gis, seeded, lineage_env
) -> None:
    """The rule applied where the promotion reads, not only where the staging writes.

    staging.co_ecmc_wells holds two generations written before
    cr_co_wells_shp_blank_is_absent_1 existed, and staging is not edited in place -- so the
    empty strings in them are still there. A promotion that read them verbatim would put the
    empty string back into canonical the next time it ran. The update below reconstructs what
    the earlier generation staged.
    """
    with seeded.cursor() as cursor:
        cursor.execute("update staging.co_ecmc_wells set well_class = '' where well_class is null")
        assert cursor.rowcount == 10
    seeded.commit()

    with open_ingest_run(seeded, source_id=co_wells.SOURCE_ID, environment=lineage_env) as run:
        report = co_wells.promote_headers(run)
    seeded.commit()

    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(*) filter (where well_type_reported = ''),"
            "       count(*) filter (where well_type_reported is null)"
            "  from canonical.wells where source_manifest_id = %s",
            (report.manifest_id,),
        )
        empty, absent = cursor.fetchone()
        cursor.execute(
            "select rule_id from lineage.derivation_rules where derivation_id = %s",
            (report.derivation_id,),
        )
        cited = {row[0] for row in cursor.fetchall()}

    assert empty == 0
    assert absent > 0
    assert "cr_co_wells_shp_blank_is_absent_1" in cited


# Every non-key text attribute the promotion stages. The two identity fields are left alone on
# purpose: blanking them quarantines the row as key_incomplete before it can reach canonical,
# and a sweep over rows that never arrived proves nothing.
_BLANKABLE = (
    "operator", "operat_num", "well_name", "well_num", "facil_id", "facil_stat",
    "well_class", "loc_qual", "loc_id",
)


def test_no_text_column_of_the_spine_carries_an_empty_string_after_a_promotion(
    staged_gis, seeded, lineage_env
) -> None:
    """gate-cofix L-4: the class claim, made true at the write path rather than at the selector.

    The rule is registered per Colorado archive and the guard added with it lives in the
    selector, so "no jurisdiction can reproduce this" held for the handle and not for the
    column: nothing stopped a parser appending '' to canonical.wells. This is the standing
    sweep. Every non-key attribute is planted blank in staging -- the shape the two
    pre-rule generations really are in -- and no text column of the spine may hold an empty
    string afterwards, whichever column a later jurisdiction files one in.
    """
    with seeded.cursor() as cursor:
        cursor.execute(
            "update staging.co_ecmc_wells set "
            + ", ".join(f"{column} = ''" for column in _BLANKABLE)
        )
        planted = cursor.rowcount
    seeded.commit()

    with open_ingest_run(seeded, source_id=co_wells.SOURCE_ID, environment=lineage_env) as run:
        report = co_wells.promote_headers(run)
    seeded.commit()

    assert planted > 0
    assert report.wells_appended > 0
    assert blank_text_columns(seeded, "canonical.wells") == {}


def test_the_promotion_reads_no_mart_and_writes_no_staging(promoted) -> None:
    from pathlib import Path

    from tests.support.layers import schema_reads_in

    assert schema_reads_in(Path(co_wells.__file__), "marts") == []
    assert schema_reads_in(Path(co_wells.__file__), "staging") == ["staging.co_ecmc_wells"]
