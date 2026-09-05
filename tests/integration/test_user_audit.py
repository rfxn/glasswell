"""Every account change leaves a record. A credential that appears or disappears with no
trace is the one change nobody can reconstruct afterwards, which is why `keys.py` audits
issuance and revocation and why the account paths do the same.

That the taxonomy carries the account event types is asserted in
tests/unit/test_audit_taxonomy.py, which needs no database to read a tuple.
"""

from __future__ import annotations

import psycopg
import pytest

pytestmark = pytest.mark.integration

def test_the_event_type_column_carries_no_database_check(db: psycopg.Connection) -> None:
    """Why adding the types above needed no migration, asserted rather than assumed."""
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from information_schema.constraint_column_usage ccu"
            "  join information_schema.table_constraints tc"
            "    on tc.constraint_name = ccu.constraint_name"
            " where ccu.table_schema = 'lineage' and ccu.table_name = 'audit_events'"
            "   and ccu.column_name = 'event_type' and tc.constraint_type = 'CHECK'"
        )
        assert cursor.fetchone()[0] == 0
