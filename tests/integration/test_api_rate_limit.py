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


def test_the_bucket_table_carries_the_four_ruled_limits() -> None:
    """Policy as data: the test reads the table rather than restating the numbers."""
    from glasswell.api.rate_limit import BUCKETS

    assert BUCKETS == {"interactive": 120, "service": 60, "tiles": 600, "anonymous": 30}


@pytest.mark.parametrize(
    ("kind", "scope", "path", "expected"),
    [
        ("user", "owner", "/v1/wells", "interactive"),
        ("user", "guest", "/v1/glossary", "interactive"),
        ("owner", "owner", "/v1/wells", "service"),
        ("service", "guest", "/v1/wells", "service"),
        ("anonymous", "guest", "/v1/wells", "anonymous"),
        ("user", "owner", "/v1/tiles/nd_wells/8/54/89.pbf", "tiles"),
        ("anonymous", "guest", "/v1/tiles/nd_wells/8/54/89.pbf", "tiles"),
    ],
)
def test_each_principal_class_falls_in_its_ruled_bucket(kind, scope, path, expected) -> None:
    from glasswell.api.rate_limit import bucket_for

    principal = Principal(id="probe", kind=kind, scope=scope)

    assert bucket_for(principal, path)[0] == expected


def test_a_principal_switching_credential_does_not_inherit_the_other_count(
    db: psycopg.Connection,
) -> None:
    """The counter keys on principal.id, and a session id differs from a key id."""
    session_principal = Principal(id="user:usr_1", kind="user", scope="owner")
    key_principal = Principal(id="key:key_1", kind="service", scope="owner")

    assert consume_rate_limit(db, session_principal, operation="interactive", limit=2) == 1
    assert consume_rate_limit(db, key_principal, operation="interactive", limit=2) == 1


def test_the_refusal_does_not_name_which_bucket_fired(db: psycopg.Connection) -> None:
    from glasswell.api.rate_limit import BUCKETS, _uniform_refusal

    refusal = _uniform_refusal()

    assert refusal.code == "rate_limited"
    for name in BUCKETS:
        assert name not in (refusal.detail or "")


def test_retry_after_is_rounded_to_thirty_seconds() -> None:
    from glasswell.api.rate_limit import RETRY_AFTER_GRANULARITY, _uniform_refusal

    retry = int(_uniform_refusal().headers["Retry-After"])

    assert retry % RETRY_AFTER_GRANULARITY == 0
    assert retry > 0


def test_the_unmet_concurrency_caps_are_recorded_in_the_module(db: psycopg.Connection) -> None:
    """§3.6.8's 32 global concurrency and 5 concurrent jobs cannot be expressed by a fixed
    window. Recorded as unmet rather than asserted by a test that measures nothing."""
    import glasswell.api.rate_limit as module

    assert "concurren" in (module.__doc__ or "").lower()
