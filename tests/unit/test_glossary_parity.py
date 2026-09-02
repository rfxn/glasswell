"""The glossary has two writers, and only one of them wins.

`seed_glossary` upserts on `term_id`, so for any term the seed carries, the seed's text is what
survives the next seed run. A migration that writes the same term is therefore either identical
to the seed or silently dead. Nothing asserted that, and the drift is directional and quiet: the
migration's copy is the one that disappears (gate-v075 MINOR-7).

The reader below is deliberately small — it decodes exactly the two statement shapes the
migrations use — and `test_every_glossary_write_in_the_migrations_was_decoded` is what stops a
third shape from passing this gate by being invisible to it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from glasswell.seed.glossary import load_glossary_seed

MIGRATIONS = Path(__file__).resolve().parents[2] / "src" / "glasswell" / "db" / "migrations"
TABLE = "canonical.glossary_terms"

SEED = {row["term_id"]: row for row in load_glossary_seed()}

# The seed owns these; a migration setting one of them is setting something the seeder resets.
SHARED_COLUMNS = (
    "term",
    "aliases",
    "short_definition",
    "expanded_definition",
    "domain_tags",
    "related_terms",
    "source_refs",
    "first_surfaced_in",
    "highlightable",
)

_WRITE = re.compile(rf"(insert\s+into|update)\s+{re.escape(TABLE)}\b", re.IGNORECASE)
_INSERT = re.compile(
    rf"insert\s+into\s+{re.escape(TABLE)}\s*\((?P<columns>[^)]*)\)\s*values\s*",
    re.IGNORECASE,
)
_UPDATE = re.compile(
    rf"update\s+{re.escape(TABLE)}\s+set\s+(?P<assignments>.*?)\s+where\s+term_id\s*=\s*"
    r"'(?P<term_id>[^']+)'",
    re.IGNORECASE | re.DOTALL,
)


def _text(literal: str) -> str | None:
    """A run of adjacent SQL string literals, concatenated; None for a non-string expression."""
    parts = re.findall(r"'((?:[^']|'')*)'", literal)
    if not parts or not re.fullmatch(r"(?:\s*'(?:[^']|'')*')+\s*", literal):
        return None
    return "".join(part.replace("''", "'") for part in parts)


def _array(literal: str) -> list[str] | None:
    match = re.fullmatch(r"\s*array\[(?P<items>.*)\]\s*", literal, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return [_text(item) or "" for item in _split(match.group("items"))]


def _value(literal: str) -> object:
    """The Python value a migration's SQL literal writes, or the literal itself if unreadable."""
    stripped = literal.strip()
    lowered = stripped.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered == "null":
        return None
    array = _array(stripped)
    if array is not None:
        return array
    text = _text(stripped)
    return stripped if text is None else text


def _split(body: str) -> list[str]:
    """Top-level commas only: a comma inside a quoted string or an array is not a separator."""
    parts, depth, quoted, start = [], 0, False, 0
    for index, character in enumerate(body):
        if character == "'":
            quoted = not quoted
        elif quoted:
            continue
        elif character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif character == "," and depth == 0:
            parts.append(body[start:index])
            start = index + 1
    parts.append(body[start:])
    return parts


def _tuple(sql: str, start: int) -> tuple[str, int]:
    """The paren-balanced VALUES tuple beginning at `start`, and the offset just past it."""
    depth, quoted = 0, False
    for index in range(start, len(sql)):
        character = sql[index]
        if character == "'":
            quoted = not quoted
        elif quoted:
            continue
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return sql[start + 1 : index], index + 1
    raise AssertionError(f"unbalanced VALUES tuple at offset {start}")


def _writes(sql: str) -> list[dict[str, object]]:
    """Every glossary row a migration writes, as {term_id, columns it sets}."""
    found: list[dict[str, object]] = []
    for match in _INSERT.finditer(sql):
        body, _ = _tuple(sql, match.end())
        columns = [name.strip().lower() for name in match.group("columns").split(",")]
        values = [_value(part) for part in _split(body)]
        if len(columns) != len(values):
            continue
        row = dict(zip(columns, values, strict=True))
        if isinstance(row.get("term_id"), str):
            found.append(row)
    for match in _UPDATE.finditer(sql):
        row: dict[str, object] = {"term_id": match.group("term_id")}
        for assignment in _split(match.group("assignments")):
            name, _, literal = assignment.partition("=")
            row[name.strip().lower()] = _value(literal)
        found.append(row)
    return found


MIGRATION_WRITES = [
    (path.name, row)
    for path in sorted(MIGRATIONS.glob("*.sql"))
    for row in _writes(path.read_text(encoding="utf-8"))
]


def _normalised(value: object) -> object:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        return [_normalised(item) for item in value]
    return value


def test_the_migrations_write_glossary_rows_at_all():
    """A gate over an empty set is a gate that cannot fail."""
    assert MIGRATION_WRITES


def test_every_glossary_write_in_the_migrations_was_decoded():
    """A statement shape the reader cannot parse must redden here, not pass this gate silently."""
    statements = sum(
        len(_WRITE.findall(path.read_text(encoding="utf-8")))
        for path in sorted(MIGRATIONS.glob("*.sql"))
    )

    assert statements == len(MIGRATION_WRITES)


@pytest.mark.parametrize(
    ("migration", "row"),
    [pytest.param(name, row, id=f"{name}:{row['term_id']}") for name, row in MIGRATION_WRITES],
)
def test_a_migration_never_disagrees_with_the_seed_about_a_term_it_shares(migration, row):
    """Whatever the seed also carries, the seed wins on the next run — so they must agree."""
    seeded = SEED.get(str(row["term_id"]))
    if seeded is None:
        # The migration is that term's only writer; the seeder cannot overwrite what it lacks.
        return
    disagreements = {
        column: (_normalised(row[column]), _normalised(seeded[column]))
        for column in SHARED_COLUMNS
        if column in row and _normalised(row[column]) != _normalised(seeded[column])
    }

    assert disagreements == {}, f"{migration} would be overwritten by the seed"
