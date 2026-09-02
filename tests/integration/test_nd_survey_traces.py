"""M1-5: the real chain from OGD_Directionals bytes to a survey trace on a tile.

The fixture is cut from the regulator download by whole `(api_wellno, well_sub)` segments, so
every count below is the file's own truth and not a shape this test invented — see
`tests/fixtures/nd_gis/SOURCE.md` for the cut and the upstream sha256.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import httpx
import psycopg
import pytest

from glasswell.ingest.nd_gis import LAYERS, load_surveys, load_wells
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.explain import resolve_chain
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts import refresh_for
from glasswell.seed import seed_all
from tests.support.seed import seed_well

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "nd_gis"
SURVEY_ARCHIVE = FIXTURES / "OGD_Directionals_stations.zip"
WELLS_ARCHIVE = FIXTURES / "OGD_Wells_300.zip"

# The fixture's measured truth. Every one of these is a count of the real file.
STATION_RECORDS = 676
SEGMENTS = 13
SURVEY_WELLS = 10
# 33053105500000 is deliberately never given a well row, so its segment is the orphan case.
ORPHAN_API14 = "33053105500000"
ORPHAN_SEGMENTS = 1
PROMOTED_SEGMENTS = SEGMENTS - ORPHAN_SEGMENTS
PROMOTED_STATIONS = STATION_RECORDS - 3
# One inclination of 436 deg, one azimuth of 437 deg, four TVDs deeper than their own MD.
WITHHELD_VALUES = 6
SEGMENT_STATIONS = {
    "33007003310000_STK1": 199,
    "33007006800000_DIR": 57,
    "33007011660000_DIR": 52,
    "33053019370000_DIR": 19,
    "33053021020000_DIR": 64,
    "33053105500000_VERT": 3,
    "33075011520000_DIR": 2,
    "33075014950000_DIR": 150,
    "33089006260000_STK4": 12,
    "33105903760000_STK1": 17,
    "33105903760000_STK2": 43,
    "33105903760000_STK3": 33,
    "33105903760000_VERT": 25,
}
SEGMENT_KINDS = {
    "DIR": "directional",
    "VERT": "vertical",
    "STK1": "sidetrack",
    "STK2": "sidetrack",
    "STK3": "sidetrack",
    "STK4": "sidetrack",
}
SURVEY_RULES = (
    "cr_nd_datum_1",
    "cr_nd_survey_api_identity_2",
    "cr_nd_survey_azimuth_reference_1",
    "cr_nd_survey_min_stations_1",
    "cr_nd_survey_segment_vocab_1",
    "cr_nd_survey_station_order_1",
    "cr_nd_survey_station_range_1",
)


def client_for(archive: Path) -> httpx.Client:
    payload = archive.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload, headers={"content-type": "application/zip"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def scalar(connection: psycopg.Connection, sql: str, parameters: tuple = ()):
    with connection.cursor() as cursor:
        cursor.execute(sql, parameters)
        row = cursor.fetchone()
    return row[0] if row else None


def rows(connection: psycopg.Connection, sql: str, parameters: tuple = ()) -> list[tuple]:
    with connection.cursor() as cursor:
        cursor.execute(sql, parameters)
        return cursor.fetchall()


@pytest.fixture
def wells_seeded(db: psycopg.Connection) -> psycopg.Connection:
    """A well row for every api10 the survey fixture references but one.

    Seeded rather than cut from OGD_Wells, because the point of the omission is the orphan
    path: a trace whose api10 has no well row must quarantine, not promote unattached.
    """
    seed_all(db)
    for api14 in sorted({key.split("_")[0] for key in SEGMENT_STATIONS}):
        if api14 == ORPHAN_API14:
            continue
        seed_well(db, api10=api14[:10], api14=api14)
    db.commit()
    return db


@pytest.fixture
def surveys_loaded(wells_seeded, raw_root, lineage_env):
    with lineage_session(
        recorder=PostgresRecorder(wells_seeded), environment=lineage_env
    ), client_for(SURVEY_ARCHIVE) as client:
        result = load_surveys(wells_seeded, raw_root=raw_root, client=client)
    wells_seeded.commit()
    return result


def test_the_archive_stages_the_station_layer_and_not_the_line_layer_beside_it(surveys_loaded):
    """OGD_Directionals.zip ships two shapefiles; the loader names the one it reads."""
    assert LAYERS["surveys"].layer_suffix == "directionals"
    assert surveys_loaded.staged_rows == STATION_RECORDS


def test_every_staged_station_keeps_its_source_row_and_a_transformed_position(
    surveys_loaded, wells_seeded
):
    assert scalar(wells_seeded, "select count(*) from staging.nd_gis_directionals") == (
        STATION_RECORDS
    )
    assert scalar(
        wells_seeded,
        "select count(*) from staging.nd_gis_directionals where ST_SRID(geom) <> 4326",
    ) == 0
    assert scalar(
        wells_seeded,
        "select count(*) from staging.nd_gis_directionals where geom is null",
    ) == 0
    # Staging is source-faithful: the truncated DBF spelling is kept, not corrected.
    assert scalar(
        wells_seeded,
        "select inclinatio from staging.nd_gis_directionals where source_row_ordinal = 0",
    ) is not None


def test_the_station_count_matches_the_fixture_s_own_truth_segment_by_segment(
    surveys_loaded, wells_seeded
):
    counted = dict(
        rows(
            wells_seeded,
            "select api14 || '_' || wellbore_segment, count(*)::int"
            "  from canonical.well_survey_stations group by 1 order by 1",
        )
    )

    expected = {k: v for k, v in SEGMENT_STATIONS.items() if not k.startswith(ORPHAN_API14)}
    assert counted == expected
    assert sum(counted.values()) == PROMOTED_STATIONS
    assert surveys_loaded.station_rows == PROMOTED_STATIONS


def test_one_trace_lands_per_wellbore_segment_keyed_the_way_nd_keys_its_own_lines(
    surveys_loaded, wells_seeded
):
    keys = [
        row[0]
        for row in rows(
            wells_seeded,
            "select geom_key from canonical.well_spatial where geom_type = 'survey_trace'"
            " order by geom_key",
        )
    ]

    assert keys == sorted(k for k in SEGMENT_STATIONS if not k.startswith(ORPHAN_API14))
    assert surveys_loaded.promoted_rows == PROMOTED_SEGMENTS
    assert scalar(
        wells_seeded,
        "select count(*) from canonical.well_spatial"
        " where geom_type = 'survey_trace' and ST_GeometryType(geom) <> 'ST_LineString'",
    ) == 0


def test_the_trace_has_one_vertex_per_station_in_ascending_measured_depth(
    surveys_loaded, wells_seeded
):
    """Station n and vertex n are the same station, or the MD a reader clicks belongs to a
    different point than the one under the cursor."""
    mismatched = rows(
        wells_seeded,
        "select s.geom_key, ST_NPoints(s.geom), count(st.*)"
        "  from canonical.well_spatial s"
        "  join canonical.well_survey_stations st"
        "    on st.api10 = s.api10 and s.geom_key = st.api14 || '_' || st.wellbore_segment"
        " where s.geom_type = 'survey_trace'"
        " group by s.geom_key, s.geom"
        " having ST_NPoints(s.geom) <> count(st.*)",
    )
    assert mismatched == []

    drifted = rows(
        wells_seeded,
        "select st.api14, st.wellbore_segment, st.station_ordinal"
        "  from canonical.well_survey_stations st"
        "  join canonical.well_spatial s"
        "    on s.api10 = st.api10 and s.geom_key = st.api14 || '_' || st.wellbore_segment"
        " where s.geom_type = 'survey_trace'"
        "   and not ST_Equals(st.geom, ST_PointN(s.geom, st.station_ordinal + 1))",
    )
    assert drifted == []

    out_of_order = rows(
        wells_seeded,
        "select api14, wellbore_segment from ("
        "  select api14, wellbore_segment, measured_depth_ft,"
        "         lag(measured_depth_ft) over (partition by api10, wellbore_segment"
        "                                      order by station_ordinal) as previous"
        "    from canonical.well_survey_stations) ordered"
        " where previous is not null and measured_depth_ft < previous",
    )
    assert out_of_order == []


def test_the_well_sub_vocabulary_is_read_from_the_registry_and_covers_every_label(
    surveys_loaded, wells_seeded
):
    mapped = dict(
        rows(
            wells_seeded,
            "select distinct wellbore_segment, segment_kind from canonical.well_survey_stations",
        )
    )

    # All six labels the file ships survive the orphan: VERT also appears on a promoted well.
    assert mapped == SEGMENT_KINDS
    assert surveys_loaded.quarantined["segment_not_promoted"] == 0
    # LAT is seeded with no station behind it because ND's own metadata documents the value.
    assert dict(
        rows(wells_seeded, "select well_sub, segment_kind from lineage.nd_survey_segment_map")
    ) == {**SEGMENT_KINDS, "LAT": "lateral"}


def test_reading_field_action_from_the_rule_row_left_the_promoted_output_where_it_was(
    surveys_loaded, wells_seeded
):
    """gate-m15d cleared the R8 fix on condition it move no promoted number. The seeded row
    says `null_field`, so every count here is the one the gate reproduced."""
    assert surveys_loaded.staged_rows == STATION_RECORDS
    assert surveys_loaded.station_rows == PROMOTED_STATIONS
    assert surveys_loaded.promoted_rows == PROMOTED_SEGMENTS
    assert surveys_loaded.quarantined["unreliable_numeric"] == WITHHELD_VALUES
    assert scalar(
        wells_seeded, "select count(*) from canonical.well_survey_stations"
    ) == PROMOTED_STATIONS


def test_an_impossible_measurement_is_withheld_and_the_station_still_carries_its_position(
    surveys_loaded, wells_seeded
):
    """The reject is the value. Quarantining the row would have truncated 33075014950000's
    trace at its deepest station, which is the honesty gap this layer exists to close."""
    assert surveys_loaded.quarantined["unreliable_numeric"] == WITHHELD_VALUES

    withheld = rows(
        wells_seeded,
        "select row_payload ->> 'field', row_payload ->> 'value', row_payload ->> 'admissible'"
        "  from lineage.quarantine_rows"
        " where reason_code = 'unreliable_numeric' and rule_id = 'cr_nd_survey_station_range_1'"
        " order by row_payload ->> 'field', row_payload ->> 'value'",
    )
    assert [field for field, _, _ in withheld].count("inclination_deg") == 1
    assert [field for field, _, _ in withheld].count("azimuth_deg") == 1
    assert [field for field, _, _ in withheld].count("true_vertical_depth_ft") == 4
    assert ("azimuth_deg", "437.0", "0 <= azimuth_deg <= 360 deg") in withheld

    # The deepest station of 33075014950000 is the one with the 437-degree azimuth.
    deepest = rows(
        wells_seeded,
        "select azimuth_deg, inclination_deg, ST_X(geom) is not null"
        "  from canonical.well_survey_stations"
        " where api14 = '33075014950000' and wellbore_segment = 'DIR'"
        " order by station_ordinal desc limit 1",
    )
    assert deepest == [(None, 0.75, True)]
    assert scalar(
        wells_seeded,
        "select count(*) from canonical.well_survey_stations where api14 = '33075014950000'",
    ) == SEGMENT_STATIONS["33075014950000_DIR"]
    assert scalar(
        wells_seeded,
        "select ST_NPoints(geom) from canonical.well_spatial"
        " where geom_key = '33075014950000_DIR'",
    ) == SEGMENT_STATIONS["33075014950000_DIR"]


def test_the_ledger_tells_a_withheld_value_from_a_lost_row(surveys_loaded, wells_seeded):
    """Six `unreliable_numeric` rows and one `orphan_fk` row are both rejects, and they mean
    opposite things: six values were withheld from stations that promoted, one segment was
    lost entirely. A count alone cannot say which, so each reject carries what was done to it."""
    filed = rows(
        wells_seeded,
        "select reason_code, row_payload ->> 'field_action', row_payload ->> 'disposition',"
        "       count(*)::int"
        "  from lineage.quarantine_rows where source_id = 'nd_gis_directionals'"
        " group by 1, 2, 3 order by 1",
    )

    assert filed == [
        ("orphan_fk", None, None, ORPHAN_SEGMENTS),
        ("unreliable_numeric", "null_field", "measure_only", WITHHELD_VALUES),
    ]

    # measure_only is a claim about the data, so it has to be true: the stations behind those
    # six withheld values are all in canonical, and the segment behind the lost row is not.
    withheld_from = rows(
        wells_seeded,
        "select distinct row_payload ->> 'api14', row_payload ->> 'wellbore_segment'"
        "  from lineage.quarantine_rows"
        " where source_id = 'nd_gis_directionals' and reason_code = 'unreliable_numeric'",
    )
    for api14, segment in withheld_from:
        assert scalar(
            wells_seeded,
            "select count(*) from canonical.well_survey_stations"
            " where api14 = %s and wellbore_segment = %s",
            (api14, segment),
        ) == SEGMENT_STATIONS[f"{api14}_{segment}"]


def test_a_trace_whose_well_has_no_row_quarantines_instead_of_promoting_unattached(
    surveys_loaded, wells_seeded
):
    assert surveys_loaded.quarantined["orphan_fk"] == ORPHAN_SEGMENTS
    held = rows(
        wells_seeded,
        "select row_payload ->> 'geom_key', row_payload ->> 'station_count', stage"
        "  from lineage.quarantine_rows where reason_code = 'orphan_fk'",
    )
    assert held == [(f"{ORPHAN_API14}_VERT", "3", "join")]
    assert scalar(
        wells_seeded,
        "select count(*) from canonical.well_survey_stations where api14 = %s",
        (ORPHAN_API14,),
    ) == 0
    # It is not dropped: the source rows are in staging and the reason is in the ledger.
    assert scalar(
        wells_seeded,
        "select count(*) from staging.nd_gis_directionals where api_wellno = %s",
        (ORPHAN_API14,),
    ) == SEGMENT_STATIONS[f"{ORPHAN_API14}_VERT"]


def test_nothing_is_dropped_between_the_file_and_the_ledger(surveys_loaded, wells_seeded):
    """SB-01 §0.4 invariant 2, at the grain the loader promotes: every staged station is
    either a canonical station or accounted for by a segment the ledger holds back."""
    staged = scalar(wells_seeded, "select count(*) from staging.nd_gis_directionals")
    promoted = scalar(wells_seeded, "select count(*) from canonical.well_survey_stations")
    held_back = sum(
        int(row[0])
        for row in rows(
            wells_seeded,
            "select row_payload ->> 'station_count' from lineage.quarantine_rows"
            " where reason_code in ('orphan_fk', 'insufficient_stations', 'segment_not_promoted')"
            "   and row_payload ? 'station_count'",
        )
    )

    assert staged == STATION_RECORDS
    assert promoted + held_back == staged


def test_every_survey_geometry_records_the_datum_and_the_transform_that_moved_it(
    surveys_loaded, wells_seeded
):
    for relation in ("canonical.well_survey_stations", "canonical.well_spatial"):
        assert scalar(
            wells_seeded,
            f"select count(*) from {relation}"
            " where source_datum <> 'EPSG:4269' or transform_rule_id <> 'cr_nd_datum_1'"
            "    or ST_SRID(geom) <> 4326",
        ) == 0


def test_the_promotion_cites_every_rule_that_shaped_it(surveys_loaded, wells_seeded):
    cited = [
        row[0]
        for row in rows(
            wells_seeded,
            "select rule_id from lineage.derivation_rules where derivation_id = %s order by 1",
            (surveys_loaded.promote_derivation_id,),
        )
    ]

    assert cited == list(SURVEY_RULES)


def test_a_station_walks_back_to_the_bytes_it_came_from(surveys_loaded, wells_seeded):
    handle = scalar(
        wells_seeded, "select derivation_id from canonical.well_survey_stations limit 1"
    )
    chain = resolve_chain(wells_seeded, handle, depth="full")

    assert surveys_loaded.manifest_id in chain.terminals


def test_a_station_row_can_never_be_edited_or_removed(surveys_loaded, wells_seeded):
    for statement in (
        "update canonical.well_survey_stations set azimuth_deg = 0",
        "delete from canonical.well_survey_stations",
    ):
        with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"):
            with wells_seeded.cursor() as cursor:
                cursor.execute(statement)
        wells_seeded.rollback()


def test_reloading_the_identical_archive_appends_nothing(
    surveys_loaded, wells_seeded, raw_root, lineage_env
):
    before = scalar(wells_seeded, "select count(*) from canonical.well_survey_stations")
    with lineage_session(
        recorder=PostgresRecorder(wells_seeded), environment=lineage_env
    ), client_for(SURVEY_ARCHIVE) as client:
        again = load_surveys(wells_seeded, raw_root=raw_root, client=client)
    wells_seeded.commit()

    assert again.unchanged is True
    assert again.manifest_id == surveys_loaded.manifest_id
    assert again.promoted_rows == 0
    assert scalar(wells_seeded, "select count(*) from canonical.well_survey_stations") == before
    for relation in ("manifests", "vintages"):
        assert scalar(
            wells_seeded,
            f"select count(*) from lineage.{relation} where source_id = 'nd_gis_directionals'",
        ) == 1


def test_a_revised_archive_whose_segments_all_conflict_is_detected_not_silently_promoted(
    surveys_loaded, wells_seeded, raw_root, lineage_env, tmp_path
):
    """DR-89: a revision with identical members re-keys nothing — every trace and every
    station already belongs to the first manifest, so the pass lands zero rows and must say
    so with a quarantine fact instead of reporting the attempted counts."""
    revised = tmp_path / "OGD_Directionals_dr89.zip"
    with zipfile.ZipFile(SURVEY_ARCHIVE) as source, zipfile.ZipFile(revised, "w") as target:
        target.comment = b"dr89 all-conflict revision"
        for name in source.namelist():
            target.writestr(name, source.read(name))

    with lineage_session(
        recorder=PostgresRecorder(wells_seeded), environment=lineage_env
    ), client_for(revised) as client:
        second = load_surveys(wells_seeded, raw_root=raw_root, client=client)
    wells_seeded.commit()

    assert second.manifest_id != surveys_loaded.manifest_id
    assert second.unchanged is False
    assert second.promoted_rows == 0
    assert second.station_rows == 0
    assert second.quarantined["key_collision"] == PROMOTED_SEGMENTS
    assert scalar(
        wells_seeded,
        "select count(*) from canonical.well_spatial where geom_type = 'survey_trace'",
    ) == PROMOTED_SEGMENTS
    assert scalar(
        wells_seeded, "select count(*) from canonical.well_survey_stations"
    ) == PROMOTED_STATIONS

    with lineage_session(
        recorder=PostgresRecorder(wells_seeded), environment=lineage_env
    ), client_for(revised) as client:
        again = load_surveys(wells_seeded, raw_root=raw_root, client=client)
    wells_seeded.commit()
    assert again.unchanged is True, "a detected all-conflict revision reloads as unchanged"


def test_a_wells_load_beside_the_surveys_leaves_the_two_geometries_distinguishable(
    surveys_loaded, wells_seeded, raw_root, lineage_env
):
    """The mart has to be able to say survey trace rather than GIS bore line, and geom_type is
    where that fact lives."""
    with lineage_session(
        recorder=PostgresRecorder(wells_seeded), environment=lineage_env
    ), client_for(WELLS_ARCHIVE) as client:
        load_wells(wells_seeded, raw_root=raw_root, client=client)
    wells_seeded.commit()

    kinds = {
        row[0]
        for row in rows(wells_seeded, "select distinct geom_type from canonical.well_spatial")
    }
    assert kinds == {"surface", "survey_trace"}


@pytest.fixture
def refreshed(surveys_loaded, wells_seeded, lineage_env):
    with lineage_session(recorder=PostgresRecorder(wells_seeded), environment=lineage_env):
        report = refresh_for(wells_seeded, "ND")
    wells_seeded.commit()
    return report


def test_the_mart_publishes_one_row_per_trace_with_the_station_count_behind_it(
    refreshed, wells_seeded
):
    published = rows(
        wells_seeded,
        "select trace_key, station_count, wellbore_segment, segment_kind, geometry_provenance"
        "  from marts.nd_survey_traces_tile order by trace_key",
    )

    assert [key for key, *_ in published] == sorted(
        k for k in SEGMENT_STATIONS if not k.startswith(ORPHAN_API14)
    )
    for key, count, segment, kind, provenance in published:
        assert count == SEGMENT_STATIONS[key]
        assert key.endswith(f"_{segment}")
        assert kind == SEGMENT_KINDS[segment]
        assert provenance == "survey_trace"
    assert refreshed.row_counts["nd_survey_traces_tile"] == PROMOTED_SEGMENTS


def test_the_mart_publishes_measured_depth_and_never_a_length(refreshed, wells_seeded):
    """ST_Length over a plan-view trace measures horizontal travel; publishing it as a length
    would name it the one thing it is not."""
    columns = {
        row[0]
        for row in rows(
            wells_seeded,
            "select column_name from information_schema.columns"
            " where table_schema = 'marts' and table_name = 'nd_survey_traces_tile'",
        )
    }
    assert not [name for name in columns if "length" in name]

    deepest = rows(
        wells_seeded,
        "select t.trace_key, t.deepest_station_md_ft, max(s.measured_depth_ft)"
        "  from marts.nd_survey_traces_tile t"
        "  join canonical.well_survey_stations s"
        "    on s.api10 = t.api10 and t.trace_key = s.api14 || '_' || s.wellbore_segment"
        " group by t.trace_key, t.deepest_station_md_ft",
    )
    assert deepest
    for _, published, measured in deepest:
        assert published == measured


def test_the_tile_function_returns_a_trace_over_the_fixture_extent(refreshed, wells_seeded):
    from tests.integration.test_marts_nd import covering_tile, extent_of
    from tests.support.mvt import attribute_keys, attribute_values, feature_count, layers

    zoom, x, y = covering_tile(extent_of(wells_seeded, "marts.tile_nd_survey_traces"))
    tile = scalar(wells_seeded, "select marts.nd_survey_traces(%s, %s, %s, null)", (zoom, x, y))

    assert tile, f"nd_survey_traces produced no MVT for {zoom}/{x}/{y} over its own extent"
    assert b"nd_survey_traces" in bytes(tile), "the MVT layer name is not the tile source id"
    decoded = layers(bytes(tile))
    assert len(decoded) == 1
    assert feature_count(decoded[0]) > 0
    keys = attribute_keys(decoded[0])
    assert {"geometry_provenance", "station_count", "trace_key", "derivation_id"} <= set(keys)
    values = attribute_values(decoded[0])
    assert ("string", "survey_trace") in values
    # station_count and the depths are numbers on the wire, not strings (N-2).
    assert {kind for kind, _ in values} >= {"double"}


def test_the_mart_row_carries_a_handle_that_resolves_to_the_manifest(refreshed, wells_seeded):
    handles = {
        row[0]
        for row in rows(
            wells_seeded, "select distinct derivation_id from marts.nd_survey_traces_tile"
        )
    }

    assert handles == {refreshed.derivation_id}
    chain = resolve_chain(wells_seeded, refreshed.derivation_id, depth="full")
    assert chain.terminals
