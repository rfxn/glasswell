"""M1-5: the pure half of the survey-trace promotion — identity, bounds, order, assembly.

Every decision these functions make is read out of a `conformance_rules` row, so the rules
under test are the seeded ones, not literals invented here (R8).
"""

from __future__ import annotations

import polars as pl
import pytest

from glasswell.ingest.nd_gis import (
    _SURVEYS_SCHEMA,
    keyed_stations,
    ordered_segments,
    survey_trace_wkt,
    withheld_measurements,
)
from glasswell.lineage.conformance import apply_rules
from glasswell.lineage.models import ConformanceRule
from glasswell.marts.tiles import TILE_LAYERS, tile_function_sql, tile_geometry_sql
from glasswell.seed import ND_RULES
from glasswell.seed.conformance_nd import EFFECTIVE_FROM

SURVEY_SOURCE = "nd_gis_directionals"
SURVEY_EVIDENCE_URL = "https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Directionals.zip"


def rule(rule_id: str) -> ConformanceRule:
    """The seeded row as the loader will read it back, so no spec is retyped in this file."""
    for seeded in ND_RULES:
        if seeded["rule_id"] == rule_id:
            return ConformanceRule(
                rule_family=rule_id.rsplit("_", 1)[0],
                effective_from=seeded.get("effective_from", EFFECTIVE_FROM),  # type: ignore[arg-type]
                **{key: value for key, value in seeded.items() if key != "effective_from"},
            )
    raise AssertionError(f"{rule_id} is not seeded")


def station(**overrides):
    base = {
        "source_row_ordinal": 0,
        "api_wellno": "33007001460000",
        "well_sub": "DIR",
        "station_type": "SPT",
        "measured_depth_ft": 4520.0,
        "true_vertical_depth_ft": 4519.56,
        "inclination_deg": 0.87,
        "azimuth_deg": 21.5,
        "ns_offset_ft": 2.04,
        "ns_offset_dir": "N",
        "ew_offset_ft": 31.44,
        "ew_offset_dir": "E",
        "longitude": -103.50273792,
        "latitude": 47.23949378,
    }
    return {**base, **overrides}


def keyed(**overrides):
    """A station as it leaves the identity and vocabulary rules, before the bounds are read."""
    segment_kind = overrides.pop("segment_kind", "directional")
    row = station(**overrides)
    api14 = row["api_wellno"]
    return {**row, "api14": api14, "api10": api14[:10], "segment_kind": segment_kind}


def test_the_api10_slice_and_the_digit_count_come_from_the_rule_not_the_loader():
    identity = rule("cr_nd_survey_api_identity_1")
    frame = pl.DataFrame([station()], schema=_SURVEYS_SCHEMA)

    promoted, rejected = keyed_stations(frame, identity)

    assert rejected == []
    assert (promoted[0]["api10"], promoted[0]["api14"]) == ("3300700146", "33007001460000")
    assert identity.spec["api10_slice"] == [0, 10]
    assert identity.spec["digits"] == 14


@pytest.mark.parametrize("api_wellno", ["", "  ", "330070014600", "3300700146000A", None])
def test_a_station_without_fourteen_digits_of_identity_is_never_keyed_on_a_guess(api_wellno):
    frame = pl.DataFrame([station(api_wellno=api_wellno)], schema=_SURVEYS_SCHEMA)

    promoted, rejected = keyed_stations(frame, rule("cr_nd_survey_api_identity_1"))

    assert promoted == []
    assert len(rejected) == 1


def test_an_impossible_measurement_is_withheld_while_its_position_still_promotes():
    """The reject is the value: ND computed the published coordinate and a 437-degree azimuth
    is no evidence against it."""
    rows, rejected = withheld_measurements(
        [keyed(azimuth_deg=437.0)], rule("cr_nd_survey_station_range_1")
    )

    assert len(rows) == 1
    assert rows[0]["azimuth_deg"] is None
    assert (rows[0]["longitude"], rows[0]["latitude"]) == (-103.50273792, 47.23949378)
    assert rows[0]["inclination_deg"] == 0.87
    assert [(r["field"], r["value"]) for r in rejected] == [("azimuth_deg", 437.0)]
    assert rejected[0]["admissible"] == "0 <= azimuth_deg <= 360 deg"


def test_a_tvd_deeper_than_its_own_measured_depth_is_withheld_against_the_row_it_broke():
    rows, rejected = withheld_measurements(
        [keyed(measured_depth_ft=4725.0, true_vertical_depth_ft=4725.77)],
        rule("cr_nd_survey_station_range_1"),
    )

    assert rows[0]["true_vertical_depth_ft"] is None
    assert rows[0]["measured_depth_ft"] == 4725.0
    assert rejected[0]["field"] == "true_vertical_depth_ft"
    assert rejected[0]["admissible"] == (
        "true_vertical_depth_ft <= measured_depth_ft (4725.0)"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("inclination_deg", 436.0), ("inclination_deg", -0.1), ("azimuth_deg", 360.5)],
)
def test_every_bound_in_the_rule_is_enforced_and_none_of_them_is_in_the_code(field, value):
    bounds = {b["field"] for b in rule("cr_nd_survey_station_range_1").spec["bounds"]}
    rows, rejected = withheld_measurements(
        [keyed(**{field: value})], rule("cr_nd_survey_station_range_1")
    )

    assert bounds == {"inclination_deg", "azimuth_deg", "true_vertical_depth_ft"}
    assert rows[0][field] is None
    assert len(rejected) == 1


def test_an_in_range_measurement_is_left_exactly_as_the_source_filed_it():
    rows, rejected = withheld_measurements([keyed()], rule("cr_nd_survey_station_range_1"))

    assert rejected == []
    assert rows[0]["azimuth_deg"] == 21.5
    assert rows[0]["inclination_deg"] == 0.87
    assert rows[0]["true_vertical_depth_ft"] == 4519.56


def test_a_null_measurement_is_absent_not_out_of_range():
    rows, rejected = withheld_measurements(
        [keyed(azimuth_deg=None)], rule("cr_nd_survey_station_range_1")
    )

    assert rejected == []
    assert rows[0]["azimuth_deg"] is None


def test_stations_are_ordered_by_measured_depth_whatever_order_the_file_arrived_in():
    shuffled = [
        keyed(source_row_ordinal=0, measured_depth_ft=4612.0, longitude=-103.3),
        keyed(source_row_ordinal=1, measured_depth_ft=4520.0, longitude=-103.1),
        keyed(source_row_ordinal=2, measured_depth_ft=4550.0, longitude=-103.2),
    ]

    segments, unorderable = ordered_segments(shuffled, rule("cr_nd_survey_station_order_1"))

    assert unorderable == []
    assert [s["measured_depth_ft"] for s in segments[0]["stations"]] == [4520.0, 4550.0, 4612.0]
    assert [s["station_ordinal"] for s in segments[0]["stations"]] == [0, 1, 2]
    assert segments[0]["geom_key"] == "33007001460000_DIR"
    assert segments[0]["station_count"] == 3


def test_a_repeated_measured_depth_is_broken_by_source_order_so_the_trace_is_reproducible():
    """Two segments upstream repeat a measured depth; without the tie-break their vertex order
    would be whatever the database happened to return."""
    repeated = [
        keyed(source_row_ordinal=7, measured_depth_ft=2050.0, longitude=-103.2),
        keyed(source_row_ordinal=6, measured_depth_ft=2050.0, longitude=-103.1),
    ]

    segments, _ = ordered_segments(repeated, rule("cr_nd_survey_station_order_1"))

    assert [s["source_row_ordinal"] for s in segments[0]["stations"]] == [6, 7]


def test_a_station_with_no_measured_depth_is_held_back_rather_than_placed_at_an_end():
    segments, unorderable = ordered_segments(
        [keyed(measured_depth_ft=None), keyed(source_row_ordinal=1, measured_depth_ft=10.0)],
        rule("cr_nd_survey_station_order_1"),
    )

    assert len(unorderable) == 1
    assert segments[0]["station_count"] == 1


def test_each_wellbore_segment_becomes_its_own_trace_key():
    stations = [
        keyed(well_sub="DIR", measured_depth_ft=1.0),
        keyed(well_sub="STK1", measured_depth_ft=2.0, segment_kind="sidetrack"),
        keyed(well_sub="VERT", measured_depth_ft=3.0, segment_kind="vertical"),
    ]

    segments, _ = ordered_segments(stations, rule("cr_nd_survey_station_order_1"))

    assert [s["geom_key"] for s in segments] == [
        "33007001460000_DIR",
        "33007001460000_STK1",
        "33007001460000_VERT",
    ]
    assert [s["segment_kind"] for s in segments] == ["directional", "sidetrack", "vertical"]


def test_the_trace_is_the_stations_in_the_order_they_were_given():
    wkt = survey_trace_wkt(
        [
            {"longitude": -103.50273792, "latitude": 47.23949378},
            {"longitude": -103.50273729, "latitude": 47.23949624},
        ]
    )

    assert wkt == "LINESTRING(-103.50273792 47.23949378, -103.50273729 47.23949624)"


def test_a_single_station_segment_is_held_back_rather_than_drawn_as_a_trace():
    """No segment upstream is this short today, so the path is proved here rather than left
    to be discovered by the first vintage that files one."""
    minimum = rule("cr_nd_survey_min_stations_1")
    segments = pl.DataFrame(
        {"geom_key": ["33007001460000_DIR", "33007001460000_STK1"], "station_count": [1, 2]}
    )

    applied = apply_rules(segments, [minimum])

    assert minimum.spec["min_stations"] == 2
    assert applied.frame["geom_key"].to_list() == ["33007001460000_STK1"]
    assert [batch.reason_code for batch in applied.quarantined] == ["insufficient_stations"]
    assert applied.quarantined[0].frame["geom_key"].to_list() == ["33007001460000_DIR"]


def test_the_row_level_predicate_and_the_per_field_bounds_are_the_same_statement():
    """The spec carries the bounds twice — one form the executor runs, one the ledger names a
    column from — so this is the assertion that they cannot mean different things."""
    ranges = rule("cr_nd_survey_station_range_1")
    frame = pl.DataFrame(
        {
            "inclination_deg": [0.87, 436.0, 0.87, 0.87, None],
            "azimuth_deg": [21.5, 21.5, 437.0, 21.5, 21.5],
            "true_vertical_depth_ft": [4519.56, 4519.56, 4519.56, 4725.77, 4519.56],
            "measured_depth_ft": [4520.0, 4520.0, 4520.0, 4725.0, 4520.0],
            "api10": ["3300700146"] * 5,
            "api14": ["33007001460000"] * 5,
            "well_sub": ["DIR"] * 5,
            "source_row_ordinal": [0, 1, 2, 3, 4],
        }
    )

    by_predicate = apply_rules(frame, [ranges])
    kept, rejected = withheld_measurements(frame.to_dicts(), ranges)

    assert by_predicate.frame["source_row_ordinal"].to_list() == [0, 4]
    assert sorted(r["source_row_ordinal"] for r in rejected) == [1, 2, 3]
    assert len(kept) == frame.height, "the per-field form keeps the position, the row form does not"


def test_the_azimuth_reference_gap_is_recorded_rather_than_assumed_away():
    """A survey azimuth without its north reference is a naked number; the rule is what makes
    it traceable instead."""
    reference = rule("cr_nd_survey_azimuth_reference_1")

    assert reference.spec["north_reference"] == "unstated_by_publisher"
    assert reference.spec["conversion"] == "none"


def test_the_survey_vocabulary_quarantines_an_unlisted_label_rather_than_tracing_it():
    vocabulary = rule("cr_nd_survey_segment_vocab_1")

    assert vocabulary.spec["mapping_table"] == "nd_survey_segment_promoted_map"
    assert vocabulary.spec["unmapped_action"] == "quarantine"
    assert vocabulary.spec["reason_code"] == "segment_not_promoted"


def test_every_survey_rule_is_scoped_to_the_survey_source_and_cites_the_artifact():
    survey_rules = [r for r in ND_RULES if r["source_id"] == SURVEY_SOURCE]

    assert len(survey_rules) == 6
    for seeded in survey_rules:
        assert seeded["evidence_url"] == SURVEY_EVIDENCE_URL
        assert len(str(seeded["rationale"])) > 200


def test_the_trace_layer_is_simplified_because_it_is_the_highest_vertex_line_on_the_map():
    layer = next(layer for layer in TILE_LAYERS if layer.name == "nd_survey_traces")

    assert layer.simplify is True
    assert "ST_Simplify" in tile_geometry_sql(layer)


def test_the_trace_layer_carries_no_overplot_gate_because_it_has_no_case_for_one():
    """586 traces over the whole state is not overplot, and the z<=7 rank was approved for the
    layers that are."""
    layer = next(layer for layer in TILE_LAYERS if layer.name == "nd_survey_traces")
    sql = tile_function_sql(layer)

    assert layer.thin is False
    assert "gw_overplot_rank" not in sql
    assert "ST_SnapToGrid" not in sql


def test_the_tile_publishes_the_provenance_that_tells_a_trace_from_a_gis_bore_line():
    layer = next(layer for layer in TILE_LAYERS if layer.name == "nd_survey_traces")

    assert ("geometry_provenance", "text") in layer.properties
    assert "geometry_provenance" in tile_function_sql(layer)


def test_no_numeric_survey_attribute_rides_the_wire_as_a_string():
    """ST_AsMVT has no numeric encoding, so a numeric column leaves the tile as a protobuf
    string and MapLibre compares '9000' > '22727' (N-2)."""
    layer = next(layer for layer in TILE_LAYERS if layer.name == "nd_survey_traces")
    numeric = {"station_count", "deepest_station_md_ft", "deepest_station_tvd_ft", "spud_year"}

    declared = dict(layer.properties)
    assert {declared[name] for name in numeric} <= {"int4", "float8"}
