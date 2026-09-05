"""The selector layer's own guard: an empty value is a facet, never a term.

`parse_selector` refuses an empty value outright, so any surface that renders one builds a
handle nothing can resolve and refuses the whole response with selector_ambiguous. One blank
ECMC well type did exactly that to `/v1/wells/status-summary` for every viewport touching
Colorado. The read-time rule keeps the empty string out of the grouping; this keeps the next
jurisdiction that files one out of the selector.
"""

from __future__ import annotations

import pytest

from glasswell.api.routers.wells import _selector_term
from glasswell.lineage.errors import InvalidSelector
from glasswell.lineage.ids import parse_selector


@pytest.mark.parametrize("value", [None, ""])
def test_an_absent_and_an_empty_value_are_the_same_facet(value: str | None) -> None:
    assert _selector_term("well_type", value) == "well_type_null=1"


def test_a_value_the_source_did_file_is_still_rendered_as_itself() -> None:
    assert _selector_term("well_type", "GW") == "well_type=GW"


def test_the_grammar_this_guards_against_refuses_the_empty_value_it_would_have_built() -> None:
    """The refusal is real, not hypothetical: this is the 422 the deployed endpoint served."""
    with pytest.raises(InvalidSelector, match="disallowed characters"):
        parse_selector("col=wells&well_type_b64=")


def test_every_selector_the_summary_builds_from_a_row_parses() -> None:
    """Each of the four dimensions the summary classes a box by, at its absent value."""
    for name in ("status", "geometry_provenance", "well_type", "basin"):
        assert parse_selector(f"col=wells&{_selector_term(name, '')}")
