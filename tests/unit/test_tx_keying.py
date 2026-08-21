from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from glasswell.ingest.tx_gis import _keyed, _metres_apart, _residuals
from glasswell.lineage.conformance import apply_rules
from glasswell.lineage.models import ConformanceRule
from glasswell.seed.conformance_tx import TX_RULES


def rule(rule_id: str) -> ConformanceRule:
    declared = next(row for row in TX_RULES if row["rule_id"] == rule_id)
    return ConformanceRule(
        rule_id=str(declared["rule_id"]),
        rule_family=str(declared["rule_id"])[:-2],
        source_id=str(declared["source_id"]),
        stage=str(declared["stage"]),
        rule_kind=str(declared["rule_kind"]),
        applies_to_fields=list(declared["applies_to_fields"]),  # type: ignore[arg-type]
        spec=dict(declared["spec"]),  # type: ignore[arg-type]
        rule=str(declared["rule"]),
        rationale=str(declared["rationale"]),
        effective_from=date(2026, 8, 20),
    )


def staged(count: int, first_stcode: str | None, later_stcode: str) -> list[dict]:
    """The shape that broke a 55-county run: a column empty at the head and set at the tail."""
    return [
        {
            "source_row_ordinal": index,
            "source_county_code": "003",
            "api": f"0034{index:04d}",
            "stcode": first_stcode if index < count - 1 else later_stcode,
            "lon27": -102.5,
            "lat27": 32.4,
            "lon83": -102.5004,
            "lat83": 32.4001,
        }
        for index in range(count)
    ]


def test_a_wellbore_code_that_only_appears_late_does_not_break_the_batch() -> None:
    keyed, quarantined = _keyed(
        staged(300, None, "H1"),
        rule("cr_tx_api10_build_1"),
        rule("cr_tx_county_scope_1"),
        {"stcode": None},
    )
    assert quarantined == []
    assert len(keyed) == 300
    assert keyed[-1]["stcode"] == "H1"
    assert keyed[0]["stcode"] == ""


def test_the_api10_is_the_state_prefix_and_the_rrcs_eight_digits() -> None:
    keyed, _ = _keyed(
        staged(1, "H1", "H1"), rule("cr_tx_api10_build_1"), rule("cr_tx_county_scope_1"), {}
    )
    assert keyed[0]["api10"] == "4200340000"
    assert len(keyed[0]["api10"]) == 10


def test_a_row_from_a_county_outside_the_scope_leaves_with_a_reason() -> None:
    rows = staged(2, "H1", "H1")
    rows[1]["source_county_code"] = "999"
    keyed, quarantined = _keyed(
        rows, rule("cr_tx_api10_build_1"), rule("cr_tx_county_scope_1"), {"stcode": None}
    )
    assert len(keyed) == 1
    assert [batch.reason_code for batch in quarantined] == ["out_of_scope"]


def test_an_arc_is_keyed_on_the_wellbore_code_and_one_without_it_is_refused() -> None:
    frame = pl.DataFrame(
        {"api10": ["4200347302", "4200347303"], "stcode": ["H1", ""]},
        schema={"api10": pl.String, "stcode": pl.String},
    )
    applied = apply_rules(frame, [rule("cr_tx_wellbore_key_1")])

    assert applied.frame["geom_key"].to_list() == ["4200347302_H1"]
    assert [batch.reason_code for batch in applied.quarantined] == ["key_incomplete"]


def test_the_residual_counts_an_unconverted_row_rather_than_scoring_it() -> None:
    """602 of Andrews' 27,704 rows publish a NAD83 pair the RRC never converted."""
    transformed = [(-102.54002287, 32.46316374), (-102.53957912, 32.46306437)]
    source = [(-102.53957912, 32.46306437), (-102.53957912, 32.46306437)]
    published = [(-102.54002287, 32.46316374), (-102.53957912, 32.46306437)]

    measured = _residuals(transformed, source, published)

    assert measured["unconverted_rows"] == 1.0
    assert measured["n"] == 1.0
    assert measured["median"] < 0.01
    assert measured["untransformed_median"] > 20.0


def test_the_untransformed_offset_is_the_hazard_the_rule_names() -> None:
    """~43 m in the Permian, which is what makes the transform load-bearing rather than tidy."""
    assert _metres_apart(-102.53957912, 32.46306437, -102.54002287, 32.46316374) == pytest.approx(
        43.0, abs=3.0
    )
