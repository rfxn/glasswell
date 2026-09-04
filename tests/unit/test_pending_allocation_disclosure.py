"""The sentence a Texas well serves while its allocated mart is empty.

Two registry lookups feed it and only one of them admitted the arm: the grain decision is what
routes a well here, and the rule that computes the share is read separately from the
registration's cumulative scope. A registration carrying the first and not the second resolves
None for the second, and the sentence has to survive that -- the link beside it already does
(gate-tx D-1).
"""

from __future__ import annotations

from glasswell.api.routers.production import pending_allocation_detail

GRAIN = "cr_tx_production_grain_1"
MODEL = "cr_tx_allocation_v0_1"


def test_the_sentence_names_both_rules_where_the_registration_carries_both() -> None:
    """The shipped wording, pinned: the card asserts this string and the visual gate photographs
    it, so a reword is a deliberate change to two other surfaces."""
    detail = pending_allocation_detail(GRAIN, MODEL)

    assert detail == (
        "This well's regulator reports production at the lease"
        " (cr_tx_production_grain_1), and the allocated mart holds no rows on this"
        " instance, so no well-level figure is served rather than an empty series"
        " that would read as nothing produced. cr_tx_allocation_v0_1 is the rule"
        " that computes it; the lease volumes it splits are promoted at their"
        " native grain and are served as the lease's own."
    )


def test_no_computing_rule_registered_serves_a_sentence_rather_than_the_word_none() -> None:
    detail = pending_allocation_detail(GRAIN, None)

    assert "None" not in detail
    assert "is the rule that computes it" not in detail
    assert detail.endswith("are served as the lease's own.")


def test_the_grain_decision_is_named_either_way() -> None:
    """It is the rule that routed the well here, so it is never absent and never guarded."""
    for model_rule in (MODEL, None):
        assert f"({GRAIN})" in pending_allocation_detail(GRAIN, model_rule)
