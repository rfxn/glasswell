"""Glossary seed (DIR-8, R9): the terms the card, the drawer and the field descriptions surface."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import psycopg
import yaml

GLOSSARY_SEED_PATH = Path(__file__).parent / "data" / "glossary_seed.yml"

_NOT_IDENTIFIER = re.compile(r"[^a-z0-9]+")

_INSERT = """
insert into canonical.glossary_terms
    (term_id, term, aliases, short_definition, expanded_definition, domain_tags,
     related_terms, source_refs, first_surfaced_in, highlightable)
values (%(term_id)s, %(term)s, %(aliases)s, %(short_definition)s, %(expanded_definition)s,
        %(domain_tags)s, %(related_terms)s, %(source_refs)s, %(first_surfaced_in)s,
        %(highlightable)s)
on conflict do nothing
"""


def slug(term: str) -> str:
    return _NOT_IDENTIFIER.sub("_", term.lower()).strip("_")


def _normalized(entry: dict[str, Any]) -> dict[str, Any]:
    term = str(entry.get("term") or "").strip()
    return {
        "term_id": f"gt_{slug(term)}",
        "term": term,
        "aliases": [str(alias) for alias in entry.get("aliases") or ()],
        "short_definition": str(entry.get("short_definition") or "").strip(),
        "expanded_definition": str(entry.get("expanded_definition") or "").strip(),
        "domain_tags": [str(tag) for tag in entry.get("domain_tags") or ()],
        "related_terms": [str(related) for related in entry.get("related_terms") or ()],
        "source_refs": [str(ref) for ref in entry.get("source_refs") or ()],
        "first_surfaced_in": entry.get("first_surfaced_in"),
        "highlightable": bool(entry.get("highlightable", True)),
    }


def load_glossary_seed(path: Path | None = None) -> list[dict[str, Any]]:
    """Parse the seed without a database, so the unit tier gates it before any migration runs."""
    with (path or GLOSSARY_SEED_PATH).open(encoding="utf-8") as handle:
        return [_normalized(entry) for entry in yaml.safe_load(handle)]


def seed_glossary(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT, load_glossary_seed())
        cursor.execute("select count(*) from canonical.glossary_terms")
        return int(cursor.fetchone()[0])
