"""Sweep successful unreferenced ephemeral derivations after their retention window."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from datetime import datetime

import psycopg

DEFAULT_DSN = "postgresql:///glasswell?host=/var/run/postgresql"


def sweep(connection: psycopg.Connection, *, cutoff: datetime | None = None) -> int:
    with connection.cursor() as cursor:
        if cutoff is None:
            cursor.execute("select lineage.sweep_ephemeral_derivations()")
        else:
            cursor.execute("select lineage.sweep_ephemeral_derivations(%s)", (cutoff,))
        return int(cursor.fetchone()[0])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("GLASSWELL_DSN", DEFAULT_DSN))
    arguments = parser.parse_args(argv)

    with psycopg.connect(arguments.dsn) as connection:
        removed = sweep(connection)
    print(f"removed {removed} expired ephemeral derivation(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
