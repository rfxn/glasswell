"""Sweep successful unreferenced ephemeral derivations after their retention window.

Also sweeps the two session-side tables. Both grow with traffic rather than with data, and
`login_attempts` in particular is written by every failed login on a public origin — a table
nobody prunes is how a login flood turns into a disk-space incident.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import psycopg

DEFAULT_DSN = "postgresql:///glasswell?host=/var/run/postgresql"

# Kept past the cap so a revoked or expired session is still explicable for a week.
SESSION_GRACE = timedelta(days=7)
ATTEMPT_RETENTION = timedelta(days=90)

_SWEEP_SESSIONS = """
delete from lineage.sessions
 where absolute_expires_at < %(cutoff)s
"""

_SWEEP_ATTEMPTS = """
delete from lineage.login_attempts
 where attempted_at < %(cutoff)s
"""


def sweep(connection: psycopg.Connection, *, cutoff: datetime | None = None) -> int:
    with connection.cursor() as cursor:
        if cutoff is None:
            cursor.execute("select lineage.sweep_ephemeral_derivations()")
        else:
            cursor.execute("select lineage.sweep_ephemeral_derivations(%s)", (cutoff,))
        return int(cursor.fetchone()[0])


def sweep_sessions(connection: psycopg.Connection, *, now: datetime | None = None) -> int:
    """Sessions whose absolute cap passed more than SESSION_GRACE ago.

    Keyed on the cap, never on `revoked_at`: a live session has a cap in the future, so this
    cannot reach one no matter how the row was last touched.
    """
    moment = now or datetime.now(UTC)
    with connection.cursor() as cursor:
        cursor.execute(_SWEEP_SESSIONS, {"cutoff": moment - SESSION_GRACE})
        return cursor.rowcount


def sweep_login_attempts(connection: psycopg.Connection, *, now: datetime | None = None) -> int:
    moment = now or datetime.now(UTC)
    with connection.cursor() as cursor:
        cursor.execute(_SWEEP_ATTEMPTS, {"cutoff": moment - ATTEMPT_RETENTION})
        return cursor.rowcount


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("GLASSWELL_DSN", DEFAULT_DSN))
    arguments = parser.parse_args(argv)

    with psycopg.connect(arguments.dsn) as connection:
        removed = sweep(connection)
        sessions = sweep_sessions(connection)
        attempts = sweep_login_attempts(connection)
        connection.commit()
    print(f"removed {removed} expired ephemeral derivation(s)")
    print(f"removed {sessions} expired session(s) and {attempts} login attempt(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
