"""Appending a corrected successor to a conformance rule that has already been published.

`lineage.conformance_rules` is append-only, so a rule that named the wrong thing is corrected
by a successor row and never by an edit: the original stays served at `/v1/conformance/<id>`,
and the derivations that cite it go on citing what shaped them. The successor carries the same
decision at a later effective date, and the registry holds both.
"""

from __future__ import annotations

from datetime import date

# The rationale a reference correction carries. One wording, because the class is one class:
# the decision did not move, the citation did, and a citation a reader cannot follow to the
# code is a published claim nobody can check.
CORRECTED_REFERENCE = (
    "A correction to the reference, not to the decision. The superseded row's module_function"
    " named {symbol}, which has never been the name of anything in {module}: R8 asks a rule to"
    " be referenced by the derivations it shaped, and a citation that resolves to nothing is a"
    " published claim a reader cannot check. Behaviour is unchanged and the spec is otherwise"
    " byte-identical, derived from the row this one supersedes rather than copied beside it."
    " The original stays served and historical, and every derivation that cites it goes on"
    " citing what shaped it."
)


def correcting_module_function(
    rule: dict[str, object],
    *,
    module_function: str,
    effective_from: date,
    rationale: str,
) -> dict[str, object]:
    """`rule`'s successor, identical but for the symbol it names and the version it declares.

    Derived from the row it supersedes rather than copied beside it, because the successor's
    whole claim is that nothing but the reference changed -- and a hand copy of a forty-line
    spec is a claim a reader cannot check and a pair that drifts on the first correction to
    either half.
    """
    rule_id = str(rule["rule_id"])
    stem, _, version = rule_id.rpartition("_")
    successor = str(int(version) + 1)
    spec = dict(rule["spec"])  # type: ignore[arg-type]
    return {
        **rule,
        "rule_id": f"{stem}_{successor}",
        "supersedes_rule_id": rule_id,
        "effective_from": effective_from,
        "spec": {**spec, "module_function": module_function, "version": successor,
                 "corrects": rule_id},
        "rationale": rationale,
    }
