from __future__ import annotations

import psycopg
import pytest

from glasswell.api.errors import ProblemError
from glasswell.api.principal import Principal
from glasswell.api.rate_limit import consume_rate_limit


def test_rate_window_is_bounded_atomic_and_per_principal(db: psycopg.Connection) -> None:
    owner = Principal(id="owner", kind="owner", scope="owner")
    guest = Principal(id="key:key_fixture", kind="service", scope="guest")

    assert consume_rate_limit(db, owner, operation="bounded", limit=2) == 1
    assert consume_rate_limit(db, owner, operation="bounded", limit=2) == 2
    with pytest.raises(ProblemError, match="2 requests") as refused:
        consume_rate_limit(db, owner, operation="bounded", limit=2)
    assert refused.value.code == "rate_limited"
    assert consume_rate_limit(db, guest, operation="bounded", limit=2) == 1

    assert db.execute(
        "select principal_id, requests from lineage.api_rate_windows order by principal_id"
    ).fetchall() == [("key:key_fixture", 1), ("owner", 2)]


def test_api_role_cannot_delete_or_truncate_rate_evidence(db: psycopg.Connection) -> None:
    db.execute(
        "insert into lineage.api_rate_windows"
        " (principal_id, operation, window_started_at, requests)"
        " values ('owner', 'bounded', now(), 1)"
    )
    db.commit()

    with db.cursor() as cursor:
        cursor.execute("set role glasswell_api")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute("delete from lineage.api_rate_windows")
    db.rollback()


def test_a_principal_switching_credential_does_not_inherit_the_other_count(
    db: psycopg.Connection,
) -> None:
    """The counter keys on principal.id, and a session id differs from a key id."""
    session_principal = Principal(id="user:usr_1", kind="user", scope="owner")
    key_principal = Principal(id="key:key_1", kind="service", scope="owner")

    assert consume_rate_limit(db, session_principal, operation="interactive", limit=2) == 1
    assert consume_rate_limit(db, key_principal, operation="interactive", limit=2) == 1
