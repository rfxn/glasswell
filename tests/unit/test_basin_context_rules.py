"""The five basin_context rules, and the classification they decide.

A well's basin was a cross-source mapping that existed only in code: `canonical.wells.basin` is
the slice the ingest took, and 182,626 wells carried no value at all. R8 says that decision is
a row with a rationale and an effective date, and these are the rows.
"""

from __future__ import annotations

import pytest

from glasswell.marts.well_basin_context import (
    AGREES,
    DISAGREES,
    IN_BOUNDARY,
    NO_GEOMETRY,
    NO_LABEL,
    NO_PLAY,
    NOT_LABELLED,
    PLAYS,
    classify,
)
from glasswell.seed.conformance_basin_context import (
    BASIN_CONTEXT,
    BASIN_CONTEXT_RULES,
    COVERAGE,
    GEOMETRY_BASIS,
    GEOMETRY_DRIVEN,
    GEOMETRY_ONLY_MT,
    OUTSIDE,
    PUBLISHED_SHARES,
    TEXAS_DISAGREEMENT,
)
from glasswell.seed.jurisdictions import JURISDICTION_RULES, JURISDICTIONS

pytestmark = pytest.mark.unit

BY_ID = {str(rule["rule_id"]): rule for rule in BASIN_CONTEXT_RULES}


def row(**overrides: object) -> dict[str, object]:
    return {
        "api10": "3305310451",
        "state_code": "33",
        "basin_label_filed": "williston",
        "basin_name": "WILLISTON",
        "boundary_id": "eia_basin_williston",
        "boundary_vintage": "2024",
        "basin_overlap": 1,
        "play_name": ["BAKKEN"],
        "has_geometry": True,
        **overrides,
    }


def test_one_rule_per_registered_jurisdiction_and_no_orphans() -> None:
    registered = {str(item["jurisdiction_code"]) for item in JURISDICTIONS}
    covered = set(COVERAGE)
    assert len(BASIN_CONTEXT_RULES) == 5
    assert registered <= covered, sorted(registered - covered)
    for rule in BASIN_CONTEXT_RULES:
        spec = rule["spec"]
        assert spec["decision"] == BASIN_CONTEXT
        assert spec["driven_off"] == "canonical.wells_latest"
        assert spec["geometry_basis"] == GEOMETRY_BASIS
        assert spec["absent_class"] == OUTSIDE
        assert rule["evidence_url"]
        assert rule["rationale"]


def test_the_four_measured_coverage_shares_are_asserted_not_discovered() -> None:
    """Measured on the deployed spine 2026-09-02, driven off wells_latest as the mart is."""
    assert COVERAGE["ND"] == {"wells": 43817, "inside": 43424, "outside": 393, "no_geometry": 0}
    assert COVERAGE["TX"] == {
        "wells": 359421,
        "inside": 344611,
        "outside": 10852,
        "no_geometry": 3958,
    }
    assert COVERAGE["NM"] == {
        "wells": 142000,
        "inside": 137505,
        "outside": 4273,
        "no_geometry": 222,
    }
    assert COVERAGE["MT"] == {
        "wells": 40626,
        "inside": 13062,
        "outside": 27564,
        "no_geometry": 0,
    }
    # The mart's own population, by construction: one row per well in wells_latest.
    assert sum(item["wells"] for item in COVERAGE.values()) == 585864
    for code, item in COVERAGE.items():
        assert item["inside"] + item["outside"] + item["no_geometry"] == item["wells"], code


def test_the_published_shares_are_reproduced_at_the_precision_they_are_published_at() -> None:
    """The spec's four shares, asserted rather than discovered.

    They are quoted on the geometry table -- distinct surface api10s intersecting a published
    basin -- and the mart is driven off the well list, so the two bases are both recorded and
    the assertion is made against the one each figure was taken on. The tolerance is the
    published precision: one decimal place, which is what the spec prints.
    """
    for code, published in PUBLISHED_SHARES.items():
        measured = GEOMETRY_DRIVEN[code]
        share = 100.0 * measured["inside"] / measured["surface_api10s"]
        assert round(share, 1) == published, (code, share)


def test_the_two_bases_differ_by_the_geometry_rows_with_no_well_behind_them() -> None:
    """N-3 as arithmetic: the mart's Montana numbers are smaller than the published ones by
    exactly the surface api10s that have no row in wells_latest, which is the whole reason the
    mart is driven off the well list."""
    montana = COVERAGE["MT"]
    assert montana["wells"] + GEOMETRY_ONLY_MT["surface_api10s"] == (
        GEOMETRY_DRIVEN["MT"]["surface_api10s"]
    )
    assert montana["inside"] + GEOMETRY_ONLY_MT["inside"] == GEOMETRY_DRIVEN["MT"]["inside"]
    # And for the other three the two bases agree once the wells with no surface point are
    # taken off the well count, because every geometry-only api10 in the spine is Montana's.
    for code in ("ND", "TX", "NM"):
        item = COVERAGE[code]
        assert item["wells"] - item["no_geometry"] == GEOMETRY_DRIVEN[code]["surface_api10s"]
        assert item["inside"] == GEOMETRY_DRIVEN[code]["inside"]


def test_montanas_win_is_stated_as_the_smaller_one_it_is() -> None:
    # Two thirds of Montana is outside every published boundary, so the honest sentence is
    # "outside every basin we publish", not "here is your basin".
    montana = COVERAGE["MT"]
    assert montana["outside"] / montana["wells"] == pytest.approx(0.678, abs=0.001)
    outside_geometry_driven = (
        GEOMETRY_DRIVEN["MT"]["surface_api10s"] - GEOMETRY_DRIVEN["MT"]["inside"]
    ) / GEOMETRY_DRIVEN["MT"]["surface_api10s"]
    assert round(100 * outside_geometry_driven, 1) == 67.6
    rationale = str(BY_ID["cr_mt_basin_context_1"]["rationale"])
    assert "27,564" in rationale
    # Both bases are named, because they answer to two thirds and a reader comparing the rule
    # against the spec has to find the spec's number in it.
    assert "67.8 percent of the wells" in rationale
    assert "67.6 percent" in rationale
    # And it says the ingest scope rule still stands rather than claiming to replace it.
    assert "does not supersede it" in rationale
    assert BY_ID["cr_mt_basin_context_1"].get("supersedes_rule_id") is None


def test_the_texas_disagreement_is_measured_and_named() -> None:
    """`permian` on all 359,421 rows is a scope label, and R-14 says the disagreement is
    served rather than hidden."""
    assert TEXAS_DISAGREEMENT["comparable"] == 344611
    assert TEXAS_DISAGREEMENT["disagreeing"] == 10896
    assert TEXAS_DISAGREEMENT["by_polygon"]["FORT WORTH"] == 10030
    share = TEXAS_DISAGREEMENT["disagreeing"] / TEXAS_DISAGREEMENT["comparable"]
    assert share == pytest.approx(float(TEXAS_DISAGREEMENT["share"]), abs=0.0001)
    rationale = str(BY_ID["cr_tx_basin_context_1"]["rationale"])
    assert "10,896" in rationale
    assert "Fort Worth" in rationale


def test_the_ingest_scope_rules_are_left_where_they_are() -> None:
    """These five decide a mart column and supersede nothing.

    `cr_mt_basin_scope_1` decides whether the ingest writes `canonical.wells.basin` at all, and
    it still governs a served sentence: Montana's map subtitle cites it for "no basin tag".
    Repointing the registry's `basin_scope` decision at a rule about polygons would move that
    citation onto a rule that never made that decision, and the register is append-only.
    """
    basin_scope = {
        (str(row["jurisdiction_code"]), str(row["rule_id"]))
        for row in JURISDICTION_RULES
        if row["decision"] == "basin_scope"
    }
    assert basin_scope == {
        ("ND", "cr_nd_basin_scope_1"),
        ("TX", "cr_tx_basin_scope_1"),
        ("NM", "cr_nm_wellhistory_basin_scope_1"),
        ("MT", "cr_mt_basin_scope_1"),
    }
    for rule in BASIN_CONTEXT_RULES:
        assert rule.get("supersedes_rule_id") is None, rule["rule_id"]
        assert "basin_scope" in str(rule["spec"]["does_not_supersede"]), rule["rule_id"]
    # And the five are registered as their own decision, one per jurisdiction, nothing shared.
    context = [row for row in JURISDICTION_RULES if row["decision"] == BASIN_CONTEXT]
    assert len(context) == len(BASIN_CONTEXT_RULES) == 5
    assert len({str(row["jurisdiction_code"]) for row in context}) == 5


def test_the_label_is_kept_beside_the_polygon_rather_than_overwritten() -> None:
    for rule in BASIN_CONTEXT_RULES:
        assert "never overwritten" in str(rule["spec"]["label_kept"])


class TestClassify:
    def test_a_point_inside_a_published_basin_answers_with_it(self) -> None:
        answered = classify(row(), "cr_nd_basin_context_1")
        assert answered["basin_class"] == IN_BOUNDARY
        assert answered["basin_name"] == "WILLISTON"
        assert answered["geometry_basis"] == GEOMETRY_BASIS
        assert answered["play_class"] == PLAYS
        assert answered["rule_id"] == "cr_nd_basin_context_1"

    def test_outside_every_boundary_is_an_answer_and_not_a_null(self) -> None:
        answered = classify(
            row(basin_name=None, boundary_id=None, boundary_vintage=None, basin_overlap=0),
            None,
            "SedimentaryBasins_US_May2011_v2",
        )
        assert answered["basin_class"] == OUTSIDE
        assert answered["basin_name"] is None
        # Outside what: the set that was asked, named with its own published vintage.
        assert answered["boundary_vintage"] == "SedimentaryBasins_US_May2011_v2"
        # A label with nothing to compare it against is not a label that disagrees.
        assert answered["label_class"] == NO_LABEL
        assert answered["label_agrees"] is None

    def test_no_geometry_is_a_different_absence_from_outside(self) -> None:
        answered = classify(
            row(
                has_geometry=False,
                basin_name=None,
                boundary_id=None,
                boundary_vintage=None,
            ),
            None,
            "SedimentaryBasins_US_May2011_v2",
        )
        assert answered["basin_class"] == NO_GEOMETRY
        assert answered["geometry_basis"] == NO_GEOMETRY
        # And no boundary set is named, because none was asked: a vintage here would be a
        # claim about a question nobody put to it.
        assert answered["boundary_vintage"] is None

    def test_a_jurisdiction_that_files_no_label_has_nothing_to_disagree_with(self) -> None:
        answered = classify(row(basin_label_filed=None), None)
        assert answered["label_class"] == NOT_LABELLED
        assert answered["label_agrees"] is None

    def test_the_texas_case_marks_the_disagreement_rather_than_hiding_it(self) -> None:
        answered = classify(
            row(state_code="42", basin_label_filed="permian", basin_name="FORT WORTH"), None
        )
        assert answered["label_class"] == DISAGREES
        assert answered["label_agrees"] is False
        assert answered["basin_label_filed"] == "permian"
        assert answered["basin_name"] == "FORT WORTH"

    def test_agreement_is_read_case_insensitively_because_the_two_sources_spell_differently(
        self,
    ) -> None:
        answered = classify(row(basin_label_filed="williston", basin_name="WILLISTON"), None)
        assert answered["label_class"] == AGREES
        assert answered["label_agrees"] is True

    def test_a_location_with_no_play_says_so_rather_than_serving_an_empty_list(self) -> None:
        answered = classify(row(play_name=[]), None)
        assert answered["play_name"] == []
        assert answered["play_class"] == NO_PLAY
