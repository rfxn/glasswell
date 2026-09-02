"""`/v1/wells/facets` warnings: every `detail` a reader is served is a sentence, not a list."""

from __future__ import annotations

from glasswell.api.routers.facets import ABSENT_BY_RULE, CARRIED, _warnings

UNREGISTERED_ABSENCE = {"label": "not reported", "rule_id": None}
JURISDICTIONS = (
    {"code": "33", "name": "North Dakota", "dimension": CARRIED, "rule_id": None},
    {
        "code": "25",
        "name": "Montana",
        "dimension": ABSENT_BY_RULE,
        "rule_id": "cr_mt_operator_absence_1",
    },
)


def test_every_warning_detail_is_a_string_on_every_arm() -> None:
    """A stray comma inside the parens makes `detail` a 1-tuple. `meta.warnings` is typed
    `list[dict[str, Any]]`, so pydantic serialises it as a JSON array and nothing refuses it."""
    emitted = _warnings(
        absence=UNREGISTERED_ABSENCE,
        truncated=True,
        q="chevron",
        jurisdictions=JURISDICTIONS,
    )

    assert {warning["code"] for warning in emitted} == {
        "absence_unregistered",
        "dimension_absent_by_rule",
        "list_truncated",
        "search_scopes_the_ranking",
    }
    for warning in emitted:
        assert isinstance(warning["detail"], str), f"{warning['code']}: {warning['detail']!r}"
        assert isinstance(warning["code"], str)
        assert isinstance(warning["pointer"], str)


def test_a_set_that_every_jurisdiction_carries_raises_no_absence_warning() -> None:
    """The warning names a population that left the `not reported` bucket. With nothing out of
    it, saying so would send a reader looking for a figure that is not there."""
    emitted = _warnings(
        absence=None, truncated=False, q=None, jurisdictions=JURISDICTIONS[:1]
    )

    assert emitted == []


def test_the_absent_by_rule_sentence_reconciles_against_what_the_search_left_standing() -> None:
    """The identity the warning states is the unsearched one, and a `q` moves it.

    Under a search the ranked arms read `matched` and reconcile against `matched_wells`; the
    operation's own description says so. A warning that names `absence` and a total the reader
    is not looking at sends them to check an arithmetic that does not hold on the response in
    front of them.
    """
    unsearched = _warnings(
        absence=UNREGISTERED_ABSENCE, truncated=False, q=None, jurisdictions=JURISDICTIONS
    )
    searched = _warnings(
        absence=UNREGISTERED_ABSENCE, truncated=False, q="chevron", jurisdictions=JURISDICTIONS
    )

    def detail(emitted: list[dict[str, object]]) -> str:
        return next(w["detail"] for w in emitted if w["code"] == "dimension_absent_by_rule")

    assert "sum to the total" in detail(unsearched)
    assert "matched_wells" in detail(searched)
    assert "sum to the total" not in detail(searched)
