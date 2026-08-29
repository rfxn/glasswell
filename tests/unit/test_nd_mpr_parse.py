from __future__ import annotations

import importlib
import inspect
from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl

from glasswell.ingest import nd_mpr
from glasswell.lineage.conformance import apply_rules
from glasswell.lineage.models import ConformanceRule
from glasswell.seed.conformance_nd import EFFECTIVE_FROM, ND_RULES

FIXTURE = Path(__file__).parents[1] / "fixtures" / "nd_mpr" / "2026_03_truncated.xlsx"

EXPECTED_HEADER = [
    "ReportDate", "API_WELLNO", "FileNo", "Company", "WellName", "Quarter", "Section",
    "Township", "Range", "County", "FieldName", "Pool", "Oil", "Wtr", "Days", "Runs",
    "Gas", "GasSold", "Flared", "Lat", "Long",
]

DATA_SHEET = "Oil"
SKIMMED_SHEET = "SkimmedCrudeRecovery"


def seeded_rule(rule_id: str) -> ConformanceRule:
    row = next(rule for rule in ND_RULES if rule["rule_id"] == rule_id)
    return ConformanceRule(
        **row, rule_family=rule_id.rsplit("_", 1)[0], effective_from=EFFECTIVE_FROM
    )


def test_the_fixture_header_is_the_twenty_one_ndic_columns_in_order():
    assert nd_mpr.read_header(FIXTURE, sheet=DATA_SHEET) == EXPECTED_HEADER


def test_the_excel_serial_decodes_to_the_production_month():
    assert nd_mpr.excel_serial_to_month(46082) == date(2026, 3, 1)


def test_a_serial_inside_the_month_still_names_the_first_of_it():
    assert nd_mpr.excel_serial_to_month(46082 + 17) == date(2026, 3, 1)


# The API-10 slice is one registry-driven decision shared with the FracFocus and ND GIS
# loaders; all three read it in test_api10_identity.py.


def test_the_skimmed_crude_recovery_sheet_is_not_read():
    frame = nd_mpr.parse_workbook(FIXTURE, sheet=DATA_SHEET)

    assert frame.height == 200
    assert nd_mpr.read_header(FIXTURE, sheet=SKIMMED_SHEET) == EXPECTED_HEADER
    assert nd_mpr.parse_workbook(FIXTURE, sheet=SKIMMED_SHEET).height == 0


def test_the_sheet_name_is_never_a_literal_in_the_promotion_module():
    """SB-07 §6.3: a rule-governed decision is read from the registry, never hardcoded."""
    source = inspect.getsource(nd_mpr)
    assert f'"{DATA_SHEET}"' not in source
    assert f"'{DATA_SHEET}'" not in source


def test_the_parsed_frame_is_source_faithful_text_with_dense_one_based_ordinals():
    frame = nd_mpr.parse_workbook(FIXTURE, sheet=DATA_SHEET)

    assert set(frame.schema.values()) == {pl.String, pl.UInt32}
    assert frame["source_row_ordinal"].to_list() == list(range(1, 201))
    assert frame["api_wellno"][0] == "33105040370000"
    assert frame["oil"][0] == "304"


def test_the_regulator_writes_the_string_null_and_the_parser_keeps_it():
    frame = nd_mpr.parse_workbook(FIXTURE, sheet=DATA_SHEET)

    assert frame.filter(pl.col("oil") == "NULL").height == 5


def test_a_negative_oil_volume_is_flagged_with_a_reason_not_dropped_silently():
    frame = pl.DataFrame(
        {
            "api10": ["3305303901", "3305303899"],
            "oil": [Decimal("259.000"), Decimal("-3.000")],
            "wtr": [Decimal("845.000"), Decimal("0.000")],
            "gas": [Decimal("1885.000"), Decimal("0.000")],
        },
        schema_overrides=dict.fromkeys(("oil", "wtr", "gas"), pl.Decimal(18, 3)),
    )

    result = apply_rules(frame, [seeded_rule("cr_nd_volume_range_1")])

    assert result.frame["api10"].to_list() == ["3305303901"]
    assert [batch.reason_code for batch in result.quarantined] == ["impossible_volume"]
    assert result.quarantined[0].frame["api10"].to_list() == ["3305303899"]


def _pool_frame(entity_keys: list[str | None] | None = None) -> pl.DataFrame:
    """The real 2026-03 shape: 3303300241 files in two pools, 3303300213 in one."""
    frame = pl.DataFrame(
        {
            "source_row_ordinal": [2589, 2603, 2597],
            "api10": ["3303300241", "3303300241", "3303300213"],
            "production_month": [date(2026, 3, 1)] * 3,
            "stream_canonical": ["oil", "oil", "oil"],
            "pool": ["BIRDBEAR", "RED RIVER", "BIRDBEAR"],
            "volume": [Decimal("120.000"), Decimal("3585.000"), Decimal("40.000")],
            "unit": ["bbl", "bbl", "bbl"],
            "days": [30, 31, 28],
        }
    )
    if entity_keys is None:
        return frame
    return frame.with_columns(pl.Series("entity_key", entity_keys, dtype=pl.String))


def test_a_well_reporting_two_pools_promotes_both_and_a_well_row_that_sums_them():
    promoted = nd_mpr.pool_promotion_records(
        _pool_frame(["3303300241:BIRDBEAR", "3303300241:RED RIVER", "3303300213:BIRDBEAR"])
    )

    assert [(r["entity_type"], r["entity_key"], r["volume"]) for r in promoted.records] == [
        ("well_completion_pool", "3303300241:BIRDBEAR", Decimal("120.000")),
        ("well_completion_pool", "3303300241:RED RIVER", Decimal("3585.000")),
        ("well", "3303300213", Decimal("40.000")),
    ]
    assert [(r["entity_key"], r["volume"], r["aggregation"]) for r in promoted.aggregates] == [
        ("3303300241", Decimal("3705.000"), "sum_over_pools")
    ]
    assert promoted.aggregates[0]["days_produced"] == 31
    assert [(row["completion_key"], row["pool_reported"]) for row in promoted.completions] == [
        ("3303300241:BIRDBEAR", "BIRDBEAR"),
        ("3303300241:RED RIVER", "RED RIVER"),
        ("3303300213:BIRDBEAR", "BIRDBEAR"),
    ]
    assert promoted.collided.is_empty()


def test_completion_entities_are_emitted_once_across_production_streams():
    keys = ["3303300241:BIRDBEAR", "3303300241:RED RIVER", "3303300213:BIRDBEAR"]
    oil = _pool_frame(keys)
    frame = pl.concat(
        [
            oil,
            oil.with_columns(pl.lit("gas").alias("stream_canonical")),
            oil.with_columns(pl.lit("water").alias("stream_canonical")),
        ]
    )

    promoted = nd_mpr.pool_promotion_records(frame)

    assert [row["completion_key"] for row in promoted.completions] == keys


def test_without_the_key_rule_in_force_the_pipeline_behaves_as_it_did_before_it():
    """R7: replaying a vintage that predates cr_nd_entity_key_1 reproduces that vintage."""
    promoted = nd_mpr.pool_promotion_records(_pool_frame())

    assert [(r["entity_type"], r["entity_key"]) for r in promoted.records] == [
        ("well", "3303300241"),
        ("well", "3303300213"),
    ]
    assert promoted.aggregates == []
    assert promoted.collided["pool"].to_list() == ["RED RIVER"]


def test_the_null_semantics_classifier_separates_zero_from_absent():
    assert nd_mpr.classify_null_semantics(Decimal("259.000")) == "reported"
    assert nd_mpr.classify_null_semantics(Decimal("0")) == "reported_zero"
    assert nd_mpr.classify_null_semantics(None) == "no_report"
    assert nd_mpr.classify_null_semantics(None, confidential=True) == "withheld"


def test_the_code_ref_symbols_resolve_and_declare_the_seeded_rule_version():
    """SB-07 §6 contract (a) and (b); (c) needs code_ref_sha256, which the seed leaves null."""
    for rule_id in ("cr_nd_liquids_policy_1", "cr_nd_null_semantics_1"):
        rule = seeded_rule(rule_id)
        module_name, _, symbol = str(rule.spec["module_function"]).partition(":")
        module = importlib.import_module(module_name)

        assert callable(getattr(module, symbol))
        assert module.__rule_version__ == rule.spec["version"]
        assert rule.code_ref == rule.spec["module_function"]


def test_the_liquids_basis_matches_the_policy_rule_it_implements():
    rule = seeded_rule("cr_nd_liquids_policy_1")

    assert nd_mpr.liquids_basis() in str(rule.spec["contract_note"])
