from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl
import pytest

from glasswell.lineage.conformance import _EXECUTORS, apply_rules, executor_for
from glasswell.lineage.errors import RuleSpecError
from glasswell.lineage.models import ConformanceRule

# NAD83 lat/long of a Williston-basin well, as the ND GIS well points ship them.
ND_LAT = 47.9226
ND_LONG = -103.2846


def rule(rule_id: str, kind: str, spec: dict[str, Any], **kwargs: Any) -> ConformanceRule:
    return ConformanceRule(
        rule_id=rule_id,
        rule_family=rule_id.rsplit("_", 1)[0],
        source_id=kwargs.pop("source_id", "nd_mpr_xlsx"),
        stage=kwargs.pop("stage", "conform"),
        applies_to_fields=kwargs.pop("applies_to_fields", []),
        rule_kind=kind,
        spec=spec,
        rule=kwargs.pop("rule", "test rule"),
        rationale=kwargs.pop("rationale", "test rationale"),
        effective_from=date(2026, 1, 1),
        **kwargs,
    )


def test_only_the_texas_and_ci_kinds_remain_unimplemented():
    unimplemented = {kind for kind, fn in _EXECUTORS.items() if "unimplemented" in repr(fn)}
    assert unimplemented == {"key_composite", "code_ref"}


MPR_FRAME = pl.DataFrame(
    {
        "report_date": ["46082", "46082"],
        "api_wellno": ["33053039010000", "33053039020000"],
        "oil": ["1200", "-3"],
        "days": ["30", "30"],
    }
)

FORMAT_RULE = rule(
    "cr_nd_mpr_format_1",
    "parse_directive",
    {
        "format_pin": "xlsx",
        "sheet": "Oil",
        "header_policy": "declared",
        "encoding": "utf-8",
        "expected_columns": ["report_date", "api_wellno", "oil", "days"],
    },
    applies_to_fields=["all"],
)


def test_parse_directive_passes_a_frame_that_matches_the_pinned_header():
    frame, batches = executor_for("parse_directive")(MPR_FRAME, FORMAT_RULE)
    assert batches == []
    assert frame.equals(MPR_FRAME)


def test_parse_directive_does_not_transform_the_values_it_validates():
    frame, _ = executor_for("parse_directive")(MPR_FRAME, FORMAT_RULE)
    # The Excel serial is decoded by the reader the directive configures, never here.
    assert frame["report_date"].to_list() == ["46082", "46082"]


def test_parse_directive_quarantines_a_frame_whose_header_lost_a_declared_column():
    frame, batches = executor_for("parse_directive")(MPR_FRAME.drop("days"), FORMAT_RULE)
    assert frame.is_empty()
    assert [batch.reason_code for batch in batches] == ["schema_mismatch"]
    assert batches[0].rule_id == "cr_nd_mpr_format_1"
    assert batches[0].frame.height == 2


def test_parse_directive_quarantines_an_undeclared_extra_column():
    widened = MPR_FRAME.with_columns(pl.lit("x").alias("surprise"))
    _, batches = executor_for("parse_directive")(widened, FORMAT_RULE)
    assert [batch.reason_code for batch in batches] == ["schema_mismatch"]


def test_parse_directive_with_only_reader_directives_is_a_passthrough():
    reader_only = rule(
        "cr_nd_month_convention_1",
        "parse_directive",
        {"encoding": "excel_serial", "epoch": "1899-12-30", "semantics": "production_month"},
        applies_to_fields=["all"],
    )
    frame, batches = executor_for("parse_directive")(MPR_FRAME, reader_only)
    assert batches == []
    assert frame.equals(MPR_FRAME)


def test_parse_directive_reads_expected_columns_from_applies_to_fields():
    identity = rule(
        "cr_nd_api_identity_1",
        "parse_directive",
        {"source_field": "API_WELLNO", "digits": 14},
        applies_to_fields=["api_wellno"],
    )
    _, batches = executor_for("parse_directive")(MPR_FRAME.drop("api_wellno"), identity)
    assert [batch.reason_code for batch in batches] == ["schema_mismatch"]


VOLUME_RULE = rule(
    "cr_nd_volume_range_1",
    "validity_filter",
    {
        "predicate_ast": {"cmp": [{"col": "oil"}, ">=", {"lit": 0}]},
        "on_fail": "quarantine",
        "reason_code": "impossible_volume",
    },
    applies_to_fields=["oil"],
)

VOLUMES = pl.DataFrame({"api10": ["3305301234", "3305305678", "3305309999"], "oil": [12, -4, None]})


def test_validity_filter_routes_a_negative_volume_to_quarantine_without_dropping_it():
    frame, batches = executor_for("validity_filter")(VOLUMES, VOLUME_RULE)
    assert frame["api10"].to_list() == ["3305301234"]
    assert [batch.reason_code for batch in batches] == ["impossible_volume"]
    assert batches[0].frame["api10"].to_list() == ["3305305678", "3305309999"]
    assert batches[0].frame.height + frame.height == VOLUMES.height


def test_validity_filter_leaves_a_clean_frame_untouched():
    clean = VOLUMES.head(1)
    frame, batches = executor_for("validity_filter")(clean, VOLUME_RULE)
    assert batches == []
    assert frame.equals(clean)


def test_validity_filter_applied_through_apply_rules_reports_the_rule_id():
    application = apply_rules(VOLUMES, [VOLUME_RULE])
    assert application.applied_rule_ids == ["cr_nd_volume_range_1"]
    assert application.quarantined[0].rule_id == "cr_nd_volume_range_1"


@pytest.mark.parametrize(
    "spec",
    [
        {"on_fail": "quarantine", "reason_code": "impossible_volume"},
        {"predicate_ast": {"cmp": [{"col": "oil"}, ">=", {"lit": 0}]}, "on_fail": "drop_flag"},
        {
            "predicate_ast": {"cmp": [{"col": "oil"}, ">=", {"lit": 0}]},
            "on_fail": "quarantine",
        },
    ],
)
def test_a_malformed_validity_filter_spec_is_rejected(spec):
    with pytest.raises(RuleSpecError):
        executor_for("validity_filter")(VOLUMES, rule("cr_bad_1", "validity_filter", spec))


DATUM_RULE = rule(
    "cr_nd_datum_1",
    "datum_transform",
    {
        "source_epsg": 4269,
        "target_epsg": 4326,
        "detect": {"prj_contains": "GCS_North_American_1983"},
    },
    source_id="nd_gis_wells",
    applies_to_fields=["latitude", "longitude"],
)

POINTS = pl.DataFrame(
    {
        "fileno": ["17045", "17046"],
        "latitude": [ND_LAT, 48.1002],
        "longitude": [ND_LONG, -102.9987],
    }
)


def test_datum_transform_moves_nad83_coordinates_into_wgs84():
    frame, batches = executor_for("datum_transform")(POINTS, DATUM_RULE)
    assert batches == []
    assert frame["latitude"][0] == pytest.approx(ND_LAT, abs=1e-7)
    assert frame["longitude"][0] == pytest.approx(ND_LONG, abs=1e-7)
    assert frame.columns == POINTS.columns


def test_datum_transform_can_project_for_a_compute_crs():
    projected = rule(
        "cr_nd_compute_crs_1",
        "datum_transform",
        {
            "source_epsg": 4326,
            "target_epsg": 32614,
            "detect": {"x_col": "longitude", "y_col": "latitude"},
        },
        source_id="nd_gis_horizontals_line",
    )
    frame, _ = executor_for("datum_transform")(POINTS, projected)
    # UTM 14N metres, not degrees: the whole point of the compute-CRS rule.
    assert 100_000 < frame["longitude"][0] < 900_000
    assert 5_000_000 < frame["latitude"][0] < 5_500_000

    inverse = rule(
        "cr_nd_inverse_projection_1",
        "datum_transform",
        {
            "source_epsg": 32614,
            "target_epsg": 4326,
            "detect": {"x_col": "longitude", "y_col": "latitude"},
        },
        source_id="nd_gis_horizontals_line",
    )
    restored, _ = executor_for("datum_transform")(frame, inverse)
    assert restored["longitude"][0] == pytest.approx(ND_LONG, abs=1e-7)
    assert restored["latitude"][0] == pytest.approx(ND_LAT, abs=1e-7)


def test_datum_transform_refuses_to_assume_a_source_datum():
    undeclared = rule(
        "cr_nd_datum_2",
        "datum_transform",
        {"target_epsg": 4326, "detect": {"x_col": "longitude", "y_col": "latitude"}},
        source_id="nd_gis_wells",
    )
    with pytest.raises(RuleSpecError, match="source_epsg"):
        executor_for("datum_transform")(POINTS, undeclared)


def test_datum_transform_quarantines_a_row_it_cannot_place():
    unplaceable = POINTS.with_columns(
        pl.Series("latitude", [ND_LAT, None], dtype=pl.Float64),
    )
    frame, batches = executor_for("datum_transform")(unplaceable, DATUM_RULE)
    assert frame["fileno"].to_list() == ["17045"]
    assert [batch.reason_code for batch in batches] == ["datum_undetermined"]
    assert batches[0].frame["fileno"].to_list() == ["17046"]


def test_datum_transform_reads_a_per_row_source_epsg_and_quarantines_the_unknown_ones():
    per_row = rule(
        "cr_nd_datum_3",
        "datum_transform",
        {
            "target_epsg": 4326,
            "detect": {"x_col": "longitude", "y_col": "latitude", "epsg_col": "srid"},
        },
        source_id="nd_gis_wells",
    )
    frame, batches = executor_for("datum_transform")(
        POINTS.with_columns(pl.Series("srid", [4269, None], dtype=pl.Int64)), per_row
    )
    assert frame["fileno"].to_list() == ["17045"]
    assert [batch.reason_code for batch in batches] == ["datum_undetermined"]


def test_datum_transform_needs_a_coordinate_column_pair():
    geometry_only = rule(
        "cr_nd_datum_4",
        "datum_transform",
        {"source_epsg": 4269, "target_epsg": 4326, "detect": {}},
        source_id="nd_gis_wells",
        applies_to_fields=["geom"],
    )
    with pytest.raises(RuleSpecError):
        executor_for("datum_transform")(POINTS, geometry_only)
