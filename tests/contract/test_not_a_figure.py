"""SB-08 A-2: the exemption register, served.

`non_figure_allowlist.yml` states why every exempt number is not a figure, and until now it
said so only to CI. A-2 puts the same sentence on the property in the OpenAPI document, so the
explorer can render a number with no handle and answer "why?" in the exempter's own words.

The check is an equivalence, and it runs both ways: a property the allowlist covers and the
document does not annotate fails, and an annotation the allowlist does not cover fails too.

**G-4, the reading of A-2 this file implements.** SB-08 §7.1 asks for "the extension set and
`non_figure_allowlist.yml` identical in pointers and reasons". Taken literally that is not
implementable — an allowlist entry is a response-pointer glob and the extension lives on a
schema property, and the two are many-to-many. So the equivalence is computed over the pointer
set the schemas generate, which is what "identical" means once both sides are resolved. Two
consequences are worth stating because they look like bugs from the outside:

* A property served at both `/bytes` and `/*/bytes` carries **one** string, and it is the
  first matching entry in `ALLOWED` order — the same first-match-wins rule the runtime matcher
  uses. In this allowlist the root form always precedes its `/*/` twin, so the substantive
  reason wins over the "…, in a collection item." cross-reference. Reordering the file would
  change served prose; that is the trade for one matcher rather than two.
* A property the allowlist reaches only through a free-form bag (`/params/**`, `/spec/**`,
  `/row_payload/**`, `/restatement_summary/**`) has no declared property to annotate, so it
  generates no extension and the check must not demand one. Asserted below, not assumed.

The two directions run over two populations, and the asymmetry is deliberate. An extension is
**demanded** on the properties the R6 gate actually exempts: declared-numeric in a response
schema, or observed `allowed` by `test_naked_numbers`' own walker. The second half is not
decoration — `api10` and the other identifiers are numeric *text*, so the walker exempts them
while the schema calls them strings, and they are the exemptions the wells grid puts in front
of a reader first. It is also what keeps `Derivation.status` out: `/status` matches that
property's pointer, but its values are `ok` and `failed`, so R6 exempts nothing there and
annotating it would publish a sentence about HTTP status codes on a field that has none.

An extension is **accepted** on any declared property whose response pointer an entry matches,
which is a wider set. Demanding over the narrower set and accepting over the wider one is what
stops a fixture from governing the register: a property served null in every seeded row leaves
the observed half of the population, and a check that also refused its annotation would go red
on a correct tree for a reason no reader would guess from the failure.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from fastapi.testclient import TestClient

from glasswell.api.examples import NOT_A_FIGURE_KEY
from tests.contract.test_naked_numbers import ALLOWED, allowed_numbers, exercised, payload

COVERAGE_REPORT = Path("/tmp/gw-pa/not-a-figure-coverage.json")
NUMERIC_TYPES = frozenset({"integer", "number"})
BAG_ENTRIES = ("/params/**", "/spec/**", "/*/spec/**", "/row_payload/**", "/restatement_summary/**")
# A walker that silently matched nothing would satisfy every assertion below by vacuity. The
# floor is deliberately far under the measured register; it is a tripwire, not a target.
VACUITY_FLOOR = 25

Property = tuple[str, str]


def _deref(
    document: Any, schema: Any, seen: frozenset[str]
) -> tuple[Any, frozenset[str], str | None]:
    """Follow `$ref` to the schema it names, reporting which component that was."""
    owner = None
    while "$ref" in schema:
        ref = schema["$ref"]
        if ref in seen:
            return None, seen, owner
        seen = seen | {ref}
        owner = ref.rsplit("/", 1)[-1]
        schema = document["components"]["schemas"][owner]
    return schema, seen, owner


def _types(schema: Any) -> set[str]:
    declared = schema.get("type")
    return {declared} if isinstance(declared, str) else set(declared or ())


def _branches(schema: Any) -> tuple[Any, ...]:
    return (*schema.get("anyOf", ()), *schema.get("oneOf", ()), *schema.get("allOf", ()))


def _declared_pointers(
    document: Any, schema: Any, pointer: str, seen: frozenset[str], owner: str | None, name: str,
    found: dict[Property, set[str]], numeric: set[Property],
) -> None:
    """Every leaf property of a response schema, with the pointer it is served at.

    `*` stands in for an array index, which is what the allowlist's own `*` matches. `numeric`
    collects the declared-numeric subset, which is the half of the population that does not
    depend on the fixture having served a value.
    """
    schema, seen, ref_owner = _deref(document, schema, seen)
    if schema is None:
        return
    owner = ref_owner or owner
    for branch in _branches(schema):
        _declared_pointers(document, branch, pointer, seen, owner, name, found, numeric)
    for child, sub in schema.get("properties", {}).items():
        _declared_pointers(document, sub, f"{pointer}/{child}", seen, owner, child, found, numeric)
    items = schema.get("items")
    if "array" in _types(schema) and isinstance(items, dict):
        _declared_pointers(document, items, f"{pointer}/*", seen, owner, name, found, numeric)
    types = _types(schema)
    if types and not types & {"object", "array"} and owner is not None:
        found.setdefault((owner, name), set()).add(pointer)
        if types & NUMERIC_TYPES:
            numeric.add((owner, name))


def _served_pointers(
    document: Any, schema: Any, node: Any, pointer: str, seen: frozenset[str], owner: str | None,
    name: str, found: dict[str, Property],
) -> None:
    """Walk a response body against its schema, naming the property each scalar leaf came from.

    Leaves reached through `additionalProperties` are deliberately unnamed: a free-form bag has
    no declared property, so there is nothing to annotate and nothing to demand.
    """
    schema, seen, ref_owner = _deref(document, schema, seen)
    if schema is None:
        return
    owner = ref_owner or owner
    for branch in _branches(schema):
        _served_pointers(document, branch, node, pointer, seen, owner, name, found)
    if isinstance(node, dict):
        for child, sub in schema.get("properties", {}).items():
            if child in node:
                _served_pointers(document, sub, node[child], f"{pointer}/{child}", seen, owner,
                                 child, found)
    elif isinstance(node, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for index, value in enumerate(node):
                _served_pointers(document, items, value, f"{pointer}/{index}", seen, owner, name,
                                 found)
    elif owner is not None:
        found[pointer] = (owner, name)


def _data_schema(document: Any, operation: Any) -> tuple[Any, frozenset[str]] | None:
    body = operation["responses"].get("200", {}).get("content", {}).get("application/json", {})
    if "schema" not in body:
        return None
    envelope, seen, _ = _deref(document, body["schema"], frozenset())
    return envelope.get("properties", {}).get("data", envelope), seen


class Register(NamedTuple):
    """What the two directions of the equivalence are computed over.

    `pointers` spans every declared leaf property, so the reverse direction can decide whether
    an annotation is covered without asking the fixture. `demanded` is the narrower set an
    extension is *required* on: declared-numeric, or observed exempt by the R6 walker.
    """

    document: Any
    pointers: dict[Property, set[str]]
    demanded: set[Property]


def register(client: TestClient) -> Register:
    document = client.get("/openapi.json").json()
    pointers: dict[Property, set[str]] = {}
    demanded: set[Property] = set()
    for item in document["paths"].values():
        operation = item.get("get")
        if operation is None:
            continue
        resolved = _data_schema(document, operation)
        if resolved is None:
            continue
        schema, seen = resolved
        _declared_pointers(document, schema, "", seen, None, "data", pointers, demanded)

    for operation_id, call in exercised(client):
        body = payload(client.get(call["url"], params=call["params"]))
        if body is None:
            continue
        resolved = _data_schema(document, _operation(document, operation_id))
        if resolved is None:
            continue
        schema, seen = resolved
        leaves: dict[str, Property] = {}
        _served_pointers(document, schema, body, "", seen, None, "data", leaves)
        for pointer in allowed_numbers(body):
            if pointer in leaves:
                pointers.setdefault(leaves[pointer], set()).add(pointer)
                demanded.add(leaves[pointer])
    return Register(document, pointers, demanded)


def _operation(document: Any, operation_id: str) -> Any:
    """The operation an `exercised()` arm calls; jurisdiction arms reuse the base operation."""
    wanted = operation_id.removesuffix("[tx]")
    for item in document["paths"].values():
        operation = item.get("get")
        if operation is not None and operation["operationId"] == wanted:
            return operation
    raise AssertionError(f"{operation_id} is not a GET the document declares")


def matched_entry(pointers: set[str]) -> dict[str, str] | None:
    """First match wins over `ALLOWED`, exactly as the runtime matcher resolves a pointer."""
    for regex, entry in ALLOWED:
        if any(regex.match(pointer) for pointer in pointers):
            return entry
    return None


def expected_reasons(pointers: dict[Property, set[str]]) -> dict[Property, str]:
    matched = {prop: matched_entry(seen) for prop, seen in pointers.items()}
    return {prop: entry["reason"] for prop, entry in matched.items() if entry is not None}


def carried_reasons(document: Any) -> dict[Property, str]:
    return {
        (schema, prop): sub[NOT_A_FIGURE_KEY]
        for schema, definition in document["components"]["schemas"].items()
        for prop, sub in definition.get("properties", {}).items()
        if NOT_A_FIGURE_KEY in sub
    }


def audit(document: Any, register: Register) -> dict[str, dict[Property, Any]]:
    """The equivalence, both directions, as one comparable value."""
    expected = expected_reasons(register.pointers)
    carried = carried_reasons(document)
    return {
        "unannotated": {
            prop: reason
            for prop, reason in expected.items()
            if prop not in carried and prop in register.demanded
        },
        "unexempted": {prop: reason for prop, reason in carried.items() if prop not in expected},
        "misquoted": {
            prop: {"served": carried[prop], "allowlist": expected[prop]}
            for prop in carried.keys() & expected.keys()
            if carried[prop] != expected[prop]
        },
    }


CLEAN: dict[str, dict[Property, Any]] = {"unannotated": {}, "unexempted": {}, "misquoted": {}}


@pytest.fixture
def served(client: TestClient) -> Register:
    return register(client)


def test_every_exempt_number_says_why_beside_itself(served: Register) -> None:
    assert audit(served.document, served) == CLEAN


def test_a_reason_changed_in_one_file_only_fails_the_check(served: Register) -> None:
    """SB-08 §8.2 acceptance 6, run every time rather than recorded as a mutation once."""
    mutated = deepcopy(served.document)
    schema, prop = next(iter(sorted(carried_reasons(served.document))))
    mutated["components"]["schemas"][schema]["properties"][prop][NOT_A_FIGURE_KEY] = "Because."

    findings = audit(mutated, served)

    assert findings["misquoted"] == {
        (schema, prop): {
            "served": "Because.",
            "allowlist": carried_reasons(served.document)[schema, prop],
        }
    }


def test_an_exempt_property_without_the_extension_fails_the_check(served: Register) -> None:
    mutated = deepcopy(served.document)
    schema, prop = next(iter(sorted(carried_reasons(served.document))))
    del mutated["components"]["schemas"][schema]["properties"][prop][NOT_A_FIGURE_KEY]

    findings = audit(mutated, served)

    assert list(findings["unannotated"]) == [(schema, prop)]
    assert findings["unexempted"] == {}


def test_an_extension_the_allowlist_does_not_cover_fails_the_check(served: Register) -> None:
    """The direction that keeps the register honest: an exemption no entry granted."""
    mutated = deepcopy(served.document)
    mutated["components"]["schemas"]["WellSummary"]["properties"]["well_name"][NOT_A_FIGURE_KEY] = (
        "A name is not a measurement."
    )

    findings = audit(mutated, served)

    assert list(findings["unexempted"]) == [("WellSummary", "well_name")]
    assert findings["unannotated"] == {}


def test_a_free_form_bag_reaches_no_property_to_annotate(served: Register) -> None:
    """`/params/**` and its siblings cover verbatim objects with no declared members, so they
    generate no extension. Asserted so the next reader does not "complete" the register."""
    entries = {entry["pointer"] for _, entry in ALLOWED}

    assert set(BAG_ENTRIES) <= entries
    matched = {
        entry["pointer"] for entry in map(matched_entry, served.pointers.values()) if entry
    }
    assert matched & set(BAG_ENTRIES) == set()


def test_the_register_is_not_vacuous(served: Register) -> None:
    """Reports coverage per schema for the explorer, and floors the count so a walker that
    matched nothing cannot pass. The gating percentage is O-6's, not this file's."""
    carried = carried_reasons(served.document)
    per_schema: dict[str, int] = {}
    for schema, _ in carried:
        per_schema[schema] = per_schema.get(schema, 0) + 1
    COVERAGE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_REPORT.write_text(
        json.dumps({"total": len(carried), "per_schema": dict(sorted(per_schema.items()))},
                   indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    assert len(carried) >= VACUITY_FLOOR
    assert served.demanded <= set(carried)
