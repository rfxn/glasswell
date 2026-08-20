"""D4: `applied_rows` is a count of rows a rule touched, not of rows that went past it."""

from __future__ import annotations

from decimal import Decimal

import polars as pl

from glasswell.lineage.conformance import apply_rules
from tests.unit.test_conformance import rule

LAND_UNIT = rule(
    "cr_nd_land_unit_1",
    "parse_directive",
    {"label_format": "{twp}N-{rng}W-{sec}"},
    applies_to_fields=["township", "range", "section"],
    stage="parse",
)
DAYS_RANGE = rule(
    "cr_nd_days_range_1",
    "validity_filter",
    {
        "predicate_ast": {"between": [{"col": "days"}, {"lit": 0}, {"lit": 31}]},
        "on_fail": "quarantine",
        "reason_code": "out_of_range_date",
    },
    stage="validate",
)
UNITS = rule(
    "cr_nd_units_1",
    "unit_conform",
    {"factor": "1", "rounding": "half_even", "scale": 3},
    applies_to_fields=["oil"],
)

FRAME = pl.DataFrame(
    {
        "township": ["151", "151"],
        "range": ["101", "101"],
        "section": ["11", "12"],
        "days": [31, 44],
        "oil": [Decimal("1.000"), Decimal("2.000")],
    },
    schema_overrides={"oil": pl.Decimal(18, 3)},
)


def test_a_rule_whose_executor_only_checks_the_header_touches_no_rows():
    """cr_nd_land_unit_1 stamped 22,223 on an MPR parse whose staging has no land-unit column."""
    application = apply_rules(FRAME, [LAND_UNIT])

    assert application.applied_rows == {"cr_nd_land_unit_1": 0}
    assert application.applied_rule_ids == ["cr_nd_land_unit_1"]


def test_a_rule_that_judges_every_row_counts_every_row():
    application = apply_rules(FRAME, [DAYS_RANGE])

    assert application.applied_rows == {"cr_nd_days_range_1": FRAME.height}
    assert application.frame.height == 1


def test_a_rule_that_rewrites_a_column_counts_the_rows_it_rewrote():
    application = apply_rules(FRAME, [UNITS])

    assert application.applied_rows == {"cr_nd_units_1": FRAME.height}


def test_each_rule_counts_the_frame_it_was_handed():
    """The second rule sees what the first left, so the counts are not all the same number."""
    application = apply_rules(FRAME, [DAYS_RANGE, UNITS])

    assert application.applied_rows == {"cr_nd_days_range_1": 2, "cr_nd_units_1": 1}
