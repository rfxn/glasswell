"""A staging table the pipeline upserts needs UPDATE, and the grant must say so.

`insert ... on conflict do update` is checked for UPDATE, not INSERT. Migration 028 granted the
New Mexico partition registry select and insert alongside its eight append-only siblings, and the
mismatch survived every scratch-database run because there the executing role owned the table.
Production is where a least-privileged pipeline role first consults the grant, and the first
`--stage-only` run there refused after 33 minutes with eight tables staged and the ninth denied.
"""

from __future__ import annotations

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPOSITORY_ROOT / "src" / "glasswell"
MIGRATIONS = SOURCE / "db" / "migrations"

# `insert into <table> (...) ... on conflict ... do update`, across newlines.
_UPSERT = re.compile(
    r"insert\s+into\s+(?P<table>\{[A-Z][A-Z0-9_]*\}|(?:staging\.)?[a-z0-9_]+)"
    r".*?on\s+conflict\b[^;]*?do\s+update",
    re.IGNORECASE | re.DOTALL,
)
_GRANT_UPDATE = re.compile(
    r"grant[^;]*\bupdate\b[^;]*?\bon\b(?P<targets>[^;]*?)\bto\b", re.IGNORECASE | re.DOTALL
)


def _staging_upsert_targets() -> set[str]:
    """Bare table names the ingest path upserts into, resolved through PARTITION_TABLE-style
    constants so an f-string target is not silently skipped."""
    targets: set[str] = set()
    for path in sorted(SOURCE.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        constants = dict(
            re.findall(r'^([A-Z][A-Z0-9_]*)\s*=\s*"(staging\.[a-z0-9_]+)"', text, re.MULTILINE)
        )
        for match in _UPSERT.finditer(text):
            table = match.group("table")
            if table.startswith("{") or "{" in table:
                name = constants.get(table.strip("{}"))
                if name is None:
                    continue
                table = name
            if table.startswith("staging."):
                targets.add(table.split(".", 1)[1])
    return targets


def _tables_granted_update() -> set[str]:
    granted: set[str] = set()
    for path in sorted(MIGRATIONS.glob("*.sql")):
        for match in _GRANT_UPDATE.finditer(path.read_text(encoding="utf-8")):
            for token in re.findall(r"staging\.([a-z0-9_]+)", match.group("targets")):
                granted.add(token)
    return granted


def test_every_upserted_staging_table_is_granted_update() -> None:
    targets = _staging_upsert_targets()
    assert targets, "no staging upsert found — the pattern moved and this guard is now blind"
    missing = sorted(targets - _tables_granted_update())
    assert not missing, (
        f"{missing} are upserted with `on conflict do update` but no migration grants UPDATE on"
        " them; Postgres checks UPDATE for that statement, so the pipeline role is refused"
    )
