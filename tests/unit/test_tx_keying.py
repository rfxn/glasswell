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


def test_a_feature_whose_own_county_is_out_of_scope_leaves_with_a_reason() -> None:
    """The predicate reads the API the RRC gave the feature, not the archive's filename."""
    rows = staged(2, "H1", "H1")
    rows[1]["api"] = "15100001"  # Fisher county, which is not in the scope list
    keyed, quarantined = _keyed(
        rows, rule("cr_tx_api10_build_1"), rule("cr_tx_county_scope_1"), {"stcode": None}
    )
    assert len(keyed) == 1
    assert [batch.reason_code for batch in quarantined] == ["out_of_scope"]


def test_the_archive_name_does_not_decide_scope_either_way() -> None:
    """520 features across the 55 archives carry a county the archive is not named for. An
    in-scope well is in scope wherever the RRC filed it, and scoping on the filename made the
    predicate compare a value against the list it had just been assigned from."""
    rows = staged(1, "H1", "H1")
    rows[0]["source_county_code"] = "999"      # an archive name outside the list
    rows[0]["api"] = "13500001"                # Ector county, which is in it
    keyed, quarantined = _keyed(
        rows, rule("cr_tx_api10_build_1"), rule("cr_tx_county_scope_1"), {"stcode": None}
    )
    assert [row["api10"] for row in keyed] == ["4213500001"]
    assert quarantined == []


def test_a_county_plot_point_is_not_padded_up_into_a_well() -> None:
    """D1, the whole class: 78,856 of 794,826 point rows carry an API that is not eight
    characters, and `'003'.zfill(8)` builds 4200000003 — a syntactically perfect API-10 for a
    well that does not exist, which then reaches canonical, the mart and the map."""
    rows = staged(1, "H1", "H1")
    rows[0]["api"] = "003"
    keyed, quarantined = _keyed(
        rows, rule("cr_tx_api10_build_1"), rule("cr_tx_county_scope_1"), {"stcode": None}
    )
    assert keyed == []
    assert [batch.reason_code for batch in quarantined] == ["key_incomplete"]


def test_an_over_wide_component_is_refused_rather_than_truncated() -> None:
    """The other half of the same semantic (D1-P3): zfill silently overbuilds an eleven-character
    API-10 and SQL lpad silently truncates onto a different real well. Both are wrong."""
    frame = pl.DataFrame(
        {"state_code": ["42"], "api": ["003400001"]}, schema={"state_code": pl.String,
                                                              "api": pl.String}
    )
    applied = apply_rules(frame, [rule("cr_tx_api10_build_1")])

    assert applied.frame.height == 0
    assert [batch.reason_code for batch in applied.quarantined] == ["key_incomplete"]


def test_a_lease_number_shorter_than_its_pad_width_is_still_normalised() -> None:
    """min_width is per column and the lease number declares none: the RRC's own manual shows
    it six digits wide and the export ships five, so padding there is width normalisation
    rather than invention. Refusing it would have quarantined most of the lease links."""
    frame = pl.DataFrame(
        {"oil_gas_code": ["O"], "district_no": ["02"], "lease_no": ["04411"]},
        schema={"oil_gas_code": pl.String, "district_no": pl.String, "lease_no": pl.String},
    )
    applied = apply_rules(frame, [rule("cr_tx_lease_key_1")])

    assert applied.frame["lease_key"].to_list() == ["O-02-004411"]
    assert applied.quarantined == []


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
