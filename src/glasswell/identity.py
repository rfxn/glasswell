"""API-10, in one place, under the identity rule row that governs the source (R8).

API-10 is the identity spine, and three loaders each decided for themselves what an API-14
literal is. A join key cannot be two things at once, so the rule row decides and this module
is the only translation of that row into a key.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from glasswell.lineage.errors import RuleSpecError
from glasswell.lineage.models import ConformanceRule


@dataclass(frozen=True, slots=True)
class Api10Identity:
    rule_id: str
    digits: int
    start: int
    stop: int
    separators: tuple[str, ...]

    def literal(self, value: object) -> str | None:
        """The separator-free API literal, or None when the value carries no identity."""
        if value is None:
            return None
        text = str(value).strip()
        for separator in self.separators:
            text = text.replace(separator, "")
        if len(text) != self.digits or not (text.isascii() and text.isdigit()):
            return None
        return text

    def normalize(self, value: object) -> str | None:
        """The API-10 key, or None — a caller quarantines that, it never keys on a guess."""
        literal = self.literal(value)
        return None if literal is None else literal[self.start : self.stop]


def api10_identity(rule: ConformanceRule) -> Api10Identity:
    """Read the identity spec off the rule row, refusing anything it does not fully declare."""
    digits = rule.spec.get("digits")
    if not isinstance(digits, int) or isinstance(digits, bool) or digits <= 0:
        raise RuleSpecError(f"{rule.rule_id}: digits must be a positive integer")

    bounds = rule.spec.get("api10_slice")
    if isinstance(bounds, str) or not isinstance(bounds, Sequence) or len(bounds) != 2:
        raise RuleSpecError(f"{rule.rule_id}: api10_slice must be a [start, stop] pair")
    try:
        start, stop = (int(bound) for bound in bounds)
    except (TypeError, ValueError):
        raise RuleSpecError(f"{rule.rule_id}: api10_slice bounds must be integers") from None
    if not 0 <= start < stop <= digits:
        raise RuleSpecError(
            f"{rule.rule_id}: api10_slice [{start}, {stop}] is not inside {digits} digits"
        )

    declared = rule.spec.get("separators")
    if declared is None:
        raise RuleSpecError(
            f"{rule.rule_id}: separators must be declared — whether a published API literal may"
            " carry display punctuation is an identity decision, and a rule row that is silent"
            " leaves each loader to invent its own answer"
        )
    if isinstance(declared, str) or not isinstance(declared, Sequence):
        raise RuleSpecError(f"{rule.rule_id}: separators must be a list of characters")
    separators = tuple(str(character) for character in declared)
    for separator in separators:
        if len(separator) != 1 or separator.isdigit():
            raise RuleSpecError(
                f"{rule.rule_id}: separator {separator!r} is not a single non-digit character"
            )

    return Api10Identity(
        rule_id=rule.rule_id, digits=digits, start=start, stop=stop, separators=separators
    )
