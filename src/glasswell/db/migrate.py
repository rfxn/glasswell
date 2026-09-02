"""Plain-SQL migration runner. Applied versions live in public.schema_migrations."""

from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

from glasswell.db.dsn import add_dsn_argument, resolve_dsn

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_FILENAME_RE = re.compile(r"\A(\d{3})_([a-z0-9_]+)\.sql\Z")

_BOOTSTRAP = """
create table if not exists public.schema_migrations (
    version    integer     primary key,
    name       text        not null,
    sha256     text        not null,
    applied_at timestamptz not null default now()
)
"""


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    path: Path
    sha256: str
    sql: str


def discover_migrations(directory: Path | None = None) -> list[Migration]:
    root = directory or MIGRATIONS_DIR
    migrations: list[Migration] = []
    for path in sorted(p for p in root.iterdir() if p.is_file()):
        match = _FILENAME_RE.match(path.name)
        if match is None:
            raise MigrationError(f"filename {path.name!r} is not NNN_lower_snake.sql")
        body = path.read_bytes()
        migrations.append(
            Migration(
                version=int(match.group(1)),
                name=match.group(2),
                path=path,
                sha256=hashlib.sha256(body).hexdigest(),
                sql=body.decode("utf-8"),
            )
        )
    if not migrations:
        raise MigrationError(f"no migrations found in {root}")

    migrations.sort(key=lambda m: m.version)
    versions = [m.version for m in migrations]
    duplicates = {v for v in versions if versions.count(v) > 1}
    if duplicates:
        raise MigrationError(f"duplicate migration versions: {sorted(duplicates)}")
    if versions != list(range(1, len(versions) + 1)):
        raise MigrationError(f"gap in migration versions: {versions}")
    return migrations


def applied_migrations(connection: psycopg.Connection) -> dict[int, str]:
    with connection.cursor() as cursor:
        cursor.execute(_BOOTSTRAP)
        cursor.execute("select version, sha256 from public.schema_migrations")
        return dict(cursor.fetchall())


def migrate(connection: psycopg.Connection, directory: Path | None = None) -> list[Migration]:
    """Apply every unapplied migration in order. Returns only what this call applied."""
    migrations = discover_migrations(directory)
    already = applied_migrations(connection)
    connection.commit()

    newly_applied: list[Migration] = []
    for migration in migrations:
        recorded = already.get(migration.version)
        if recorded == migration.sha256:
            continue
        if recorded is not None:
            raise MigrationError(
                f"migration {migration.version:03d}_{migration.name} changed after it was applied"
                f" (recorded {recorded}, on disk {migration.sha256})"
            )
        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(migration.sql)
            cursor.execute(
                "insert into public.schema_migrations (version, name, sha256) values (%s, %s, %s)",
                (migration.version, migration.name, migration.sha256),
            )
        newly_applied.append(migration)
    return newly_applied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply glasswell database migrations.")
    add_dsn_argument(parser)
    parser.add_argument("--migrations-dir", type=Path, default=None)
    arguments = parser.parse_args(argv)
    arguments.dsn = resolve_dsn(arguments.dsn)

    with psycopg.connect(arguments.dsn) as connection:
        applied = migrate(connection, arguments.migrations_dir)
    for migration in applied:
        print(f"applied {migration.version:03d}_{migration.name}")
    if not applied:
        print("no migrations to apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
