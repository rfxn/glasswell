"""Classify a change to the published API surface as additive or breaking.

Byte equality against the committed snapshot says *something moved*. After the S1 freeze the
question is *which kind of move*: §3.6.1 makes a removal or an incompatible tightening a
`/v2` event, while an addition is ordinary. This turns that judgement into a check.

The traversal follows `test_naked_numbers.py`: flatten the document to classified facts in
one pass, then compare fact sets, so the two directions of the diff cannot disagree about
what a fact is. Run as a module for the CI mode:

    python -m tests.contract.openapi_diff before.json after.json
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

Verdict = Literal["additive", "breaking"]

METHODS = ("get", "put", "post", "delete", "patch", "head", "options")

# A fact's kind decides what its appearance and its disappearance mean. Request and response
# obligations run in opposite directions, which is why request schemas are identified first.
_RULES: dict[str, tuple[Verdict, Verdict]] = {
    # kind: (verdict when added, verdict when removed)
    "path": ("additive", "breaking"),
    "operation": ("additive", "breaking"),
    "parameter": ("additive", "breaking"),
    "required-parameter": ("breaking", "additive"),
    "response": ("additive", "breaking"),
    "schema": ("additive", "breaking"),
    "property": ("additive", "breaking"),
    "required-request-property": ("breaking", "additive"),
    "required-response-property": ("additive", "breaking"),
    "enum-value": ("additive", "breaking"),
    # A type is one fact per shape, so a change reports as the old shape leaving.
    "type": ("additive", "breaking"),
    # UDM-SPEC §5.3/§5.2a (N-5): a relaxed identifier grammar produced no fact at all before
    # this kind existed, so the classifier answered `additive` having examined nothing.
    "pattern": ("additive", "breaking"),
}


@dataclass(frozen=True, slots=True)
class Change:
    kind: str
    fact: str
    direction: Literal["added", "removed"]

    @property
    def verdict(self) -> Verdict:
        added, removed = _RULES[self.kind]
        return added if self.direction == "added" else removed

    def __str__(self) -> str:
        return f"{self.verdict:9} {self.direction:7} {self.kind}: {self.fact}"


@dataclass(frozen=True, slots=True)
class Fact:
    kind: str
    container: str | None
    """The path, operation or schema this fact lives inside — not its syntactic parent.

    `required` is a modifier on a parameter, not a child of it: a new required parameter on
    an existing operation breaks callers, while the same parameter inside a brand-new
    operation breaks nobody. Only a container answers that question.
    """


def _request_schema_names(document: dict[str, Any]) -> set[str]:
    """Schemas reachable from a request body. Their `required` runs the other way."""
    names: set[str] = set()
    for operations in document.get("paths", {}).values():
        for method in METHODS:
            body = (operations.get(method) or {}).get("requestBody") or {}
            for media in body.get("content", {}).values():
                names |= _referenced(media.get("schema"))
    frontier = set(names)
    schemas = document.get("components", {}).get("schemas", {})
    while frontier:
        name = frontier.pop()
        for value in (schemas.get(name) or {}).get("properties", {}).values():
            for nested in _referenced(value) - names:
                names.add(nested)
                frontier.add(nested)
    return names


def _referenced(node: Any) -> set[str]:
    if isinstance(node, dict):
        found: set[str] = set()
        reference = node.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/components/schemas/"):
            found.add(reference.rsplit("/", 1)[-1])
        for value in node.values():
            found |= _referenced(value)
        return found
    if isinstance(node, list):
        return set().union(*(_referenced(item) for item in node)) if node else set()
    return set()


def facts(document: dict[str, Any]) -> dict[str, Fact]:
    """Every published commitment in the document, as `fact -> (kind, parent fact)`."""
    return dict(_walk(document))


def _walk(document: dict[str, Any]) -> Iterator[tuple[str, Fact]]:
    for path, operations in document.get("paths", {}).items():
        yield path, Fact("path", None)
        for method in METHODS:
            operation = operations.get(method)
            if operation is None:
                continue
            route = f"{method.upper()} {path}"
            yield route, Fact("operation", path)
            for parameter in operation.get("parameters", ()):
                name = f"{route} ?{parameter['name']}"
                yield name, Fact("parameter", route)
                if parameter.get("required"):
                    yield f"{name} (required)", Fact("required-parameter", route)
                yield from _shape(parameter.get("schema"), name, route)
            for status in operation.get("responses", {}):
                yield f"{route} -> {status}", Fact("response", route)

    request_schemas = _request_schema_names(document)
    for name, schema in document.get("components", {}).get("schemas", {}).items():
        container = f"schema {name}"
        yield container, Fact("schema", None)
        required = set(schema.get("required", ()))
        kind = (
            "required-request-property"
            if name in request_schemas
            else "required-response-property"
        )
        for field, value in schema.get("properties", {}).items():
            field_fact = f"{name}.{field}"
            yield field_fact, Fact("property", container)
            if field in required:
                yield f"{field_fact} (required)", Fact(kind, container)
            yield from _shape(value, field_fact, container)


def _shape(schema: Any, label: str, container: str) -> Iterator[tuple[str, Fact]]:
    """One type fact per field — a union renders as one name, not one fact per branch."""
    if not isinstance(schema, dict):
        return
    name = _type_name(schema)
    if name:
        yield f"{label} : {name}", Fact("type", container)
    yield from _constraints(schema, label, container)


def _constraints(schema: dict[str, Any], label: str, container: str) -> Iterator[tuple[str, Fact]]:
    """What a field admits, beyond its type. `str | None` carries both one branch down."""
    for value in schema.get("enum", ()):
        yield f"{label} = {value!r}", Fact("enum-value", container)
    pattern = schema.get("pattern")
    if isinstance(pattern, str):
        yield f"{label} =~ {pattern}", Fact("pattern", container)
    for branch in schema.get("anyOf", ()) or schema.get("oneOf", ()):
        if isinstance(branch, dict):
            yield from _constraints(branch, label, container)


def _type_name(schema: dict[str, Any]) -> str:
    """A stable rendering of one node's shape. `str` widening to `str | None` is a change."""
    declared = schema.get("type")
    if isinstance(declared, str):
        return declared
    branches = schema.get("anyOf") or schema.get("oneOf")
    if isinstance(branches, list):
        names = sorted(
            name for branch in branches if (name := _type_name(branch or {}))
        )
        return "|".join(names)
    reference = schema.get("$ref")
    return reference.rsplit("/", 1)[-1] if isinstance(reference, str) else ""


def classify(before: dict[str, Any], after: dict[str, Any]) -> list[Change]:
    """Every outermost fact that appeared or disappeared, and what it costs a caller.

    A change inside a container that itself appeared or disappeared is not reported: the
    required parameters of a brand-new operation oblige nobody, and the parameters of a
    deleted path are already said by the path.
    """
    old, new = facts(before), facts(after)
    changes: list[Change] = []
    for direction, moved, source in (
        ("added", new.keys() - old.keys(), new),
        ("removed", old.keys() - new.keys(), old),
    ):
        for fact in moved:
            if _inside_a_moved_container(fact, source, moved):
                continue
            changes.append(Change(kind=source[fact].kind, fact=fact, direction=direction))
    return sorted(changes, key=lambda change: (change.verdict, change.kind, change.fact))


def _inside_a_moved_container(
    fact: str, source: dict[str, Fact], moved: set[str]
) -> bool:
    container = source[fact].container
    while container is not None:
        if container in moved:
            return True
        container = source[container].container if container in source else None
    return False


def breaking(before: dict[str, Any], after: dict[str, Any]) -> list[Change]:
    return [change for change in classify(before, after) if change.verdict == "breaking"]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    before, after = (json.loads(Path(name).read_text(encoding="utf-8")) for name in argv)
    changes = classify(before, after)
    for change in changes:
        print(change)
    offenders = [change for change in changes if change.verdict == "breaking"]
    if offenders:
        print(
            f"\n{len(offenders)} breaking change(s): a removal or an incompatible tightening"
            " after the S1 freeze is a /v2 event (blueprint §3.6.1).",
            file=sys.stderr,
        )
        return 1
    print(f"\n{len(changes)} change(s), all additive.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
