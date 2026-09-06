"""Every selector term the API builds, and what keeps its value non-empty.

`parse_selector` admits no empty value, so a term built from one renders a handle that refuses
the whole response — `?q=` on `/v1/wells/facets` rendered `q_b64=` and answered 422
`selector_ambiguous`, which is the Colorado blank-well-type class in another router. A call
site is cheap to add and the defect is invisible until a request happens to carry the empty
string, so each site is declared here with the check that makes its value non-empty.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from glasswell.lineage.ids import InvalidSelector, parse_selector
from glasswell.lineage.selector_registry import identity_selector_term

pytestmark = pytest.mark.unit

ROUTERS = Path(__file__).resolve().parents[2] / "src" / "glasswell" / "api"

DECLARED: dict[tuple[str, str], str] = {
    ("facets.py", "identity_selector_term('state', scope)"): (
        "`_require_states` refuses an empty scope before this line, and `all` resolves to the"
        " registered jurisdictions that carry wells, so the join is never the empty string"
    ),
    ("facets.py", "identity_selector_term(name, value)"): (
        "`_partition_term`; its two callers pass `scope` and `q`, both declared here"
    ),
    ("facets.py", "identity_selector_term('jurisdiction', jurisdiction)"): (
        "a state code out of the resolved scope, which `_require_states` refused when empty"
    ),
    ("facets.py", "identity_selector_term('value', value)"): (
        "the value a jurisdiction filed. Blank-is-absent is a read-time rule in the mart and"
        " belongs to the Colorado track, not to this router: a bucket whose value is the empty"
        " string would refuse here, and closing it is that track's `absence.py`"
    ),
    ("facets.py", "identity_selector_term('q', q)"): (
        "the request's search, normalised to None at the top of the handler: no search and a"
        " search for nothing are the same request"
    ),
    ("production.py", "identity_selector_term('entity_key', entity_key)"): (
        "read off a mart row; `canonical.production_monthly.entity_key` is not null and part"
        " of the primary key (020_production_entity_key.sql)"
    ),
    ("wells.py", "identity_selector_term('api10', api10)"): (
        "the route's path parameter, matched against API10_PATTERN before the handler runs"
    ),
    ("wells.py", "identity_selector_term(name, value)"): (
        "`_selector_term`, which renders the null facet rather than a term when there is no"
        " value to name"
    ),
}


def call_sites() -> set[tuple[str, str]]:
    found = set()
    for path in sorted(ROUTERS.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "id", "") == "identity_selector_term":
                found.add((path.name, ast.unparse(node)))
    return found


def test_the_grammar_admits_no_empty_value() -> None:
    """The premise every declaration below rests on."""
    with pytest.raises(InvalidSelector, match="disallowed characters"):
        parse_selector(identity_selector_term("q", ""))


def test_every_selector_term_the_api_builds_is_declared_with_what_keeps_it_non_empty() -> None:
    found = call_sites()

    assert len(found) >= 8, "the walk found almost nothing; it is reading the wrong tree"
    assert found == set(DECLARED)


def test_every_declaration_says_which_check_holds_rather_than_that_one_does() -> None:
    assert all(len(reason) > 40 for reason in DECLARED.values())
