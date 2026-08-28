from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import psycopg
import pytest

from glasswell.lineage.capture import lineage_session
from glasswell.lineage.fetch import fetch_raw
from glasswell.lineage.fetch_attempts import FetchAttemptLedger, durable_fetch_attempts
from glasswell.lineage.store import PostgresRecorder

SOURCE_ID = "nd_mpr_xlsx"
URL = "https://example.test/month.xlsx"


def client_for(payload: bytes) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=payload))
    )


def attempts(db: psycopg.Connection) -> list[dict]:
    with db.cursor(row_factory=psycopg.rows.dict_row) as cursor:
        cursor.execute(
            "select attempt_id, source_key, outcome, manifest_id, failure_code, failure_detail"
            " from lineage.fetch_attempts order by attempted_at, attempt_id"
        )
        return [dict(row) for row in cursor.fetchall()]


def fetch(
    db: psycopg.Connection,
    raw_root: Path,
    lineage_env,
    *,
    key: str,
    payload: bytes,
) -> None:
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env), client_for(
        payload
    ) as client:
        fetch_raw(db, SOURCE_ID, key, url=URL, raw_root=raw_root, client=client)


def test_new_and_unchanged_are_finalized_only_after_the_manifest_commits(
    db,
    raw_root,
    lineage_env,
    postgres_password,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PGPASSWORD", postgres_password)

    with durable_fetch_attempts(db.info.dsn):
        fetch(db, raw_root, lineage_env, key="committed.xlsx", payload=b"first")
        assert attempts(db)[0]["outcome"] is None
        db.commit()

    with durable_fetch_attempts(db.info.dsn):
        fetch(db, raw_root, lineage_env, key="committed.xlsx", payload=b"first")
        db.commit()

    rows = attempts(db)
    assert [row["outcome"] for row in rows] == ["new", "unchanged"]
    assert rows[0]["manifest_id"] == rows[1]["manifest_id"]


def test_rolled_back_candidate_survives_as_open_attempt_not_false_new(
    db,
    raw_root,
    lineage_env,
    postgres_password,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PGPASSWORD", postgres_password)

    with durable_fetch_attempts(db.info.dsn):
        fetch(db, raw_root, lineage_env, key="rolled-back.xlsx", payload=b"rolled back")
        db.rollback()

    row = attempts(db)[0]
    assert row["outcome"] is None
    assert row["manifest_id"] is None
    assert db.execute(
        "select count(*) from lineage.manifests where source_key = 'rolled-back.xlsx'"
    ).fetchone()[0] == 0


def test_downstream_failure_survives_parent_rollback_as_failed_attempt(
    db,
    raw_root,
    lineage_env,
    postgres_password,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PGPASSWORD", postgres_password)

    def fail_after_rollback() -> None:
        with durable_fetch_attempts(db.info.dsn):
            fetch(db, raw_root, lineage_env, key="failed-promotion.xlsx", payload=b"candidate")
            db.rollback()
            raise RuntimeError("promotion failed")

    with pytest.raises(RuntimeError, match="promotion failed"):
        fail_after_rollback()

    row = attempts(db)[0]
    assert row["outcome"] == "failed"
    assert row["failure_code"] == "runtimeerror"
    assert row["manifest_id"] is None


def test_transport_failure_is_durable_private_and_bounded(
    db,
    raw_root,
    lineage_env,
    postgres_password,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PGPASSWORD", postgres_password)
    secret = "token=top-secret https://user:password@example.test/file?api_key=also-secret"

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(secret, request=request)

    with pytest.raises(httpx.ConnectError), durable_fetch_attempts(
        db.info.dsn
    ), lineage_session(
        recorder=PostgresRecorder(db), environment=lineage_env
    ), httpx.Client(transport=httpx.MockTransport(fail)) as client:
        fetch_raw(db, SOURCE_ID, "private.xlsx", url=URL, raw_root=raw_root, client=client)
    db.rollback()

    row = attempts(db)[0]
    assert row["outcome"] == "failed"
    assert row["failure_code"] == "connecterror"
    assert "top-secret" not in row["failure_detail"]
    assert "also-secret" not in row["failure_detail"]
    assert "user:password" not in row["failure_detail"]
    assert len(row["failure_detail"]) <= 256


def test_unfinished_durable_attempt_remains_distinguishable_and_ordered(
    db,
    postgres_password,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PGPASSWORD", postgres_password)
    moments = iter(
        [
            datetime(2026, 8, 28, 12, tzinfo=UTC),
            datetime(2026, 8, 28, 12, tzinfo=UTC) + timedelta(seconds=1),
        ]
    )
    ledger = FetchAttemptLedger(lambda: psycopg.connect(db.info.dsn), now=lambda: next(moments))

    ledger.begin(SOURCE_ID, "a.xlsx")
    ledger.begin(SOURCE_ID, "b.xlsx")

    rows = attempts(db)
    assert [row["source_key"] for row in rows] == ["a.xlsx", "b.xlsx"]
    assert [row["outcome"] for row in rows] == [None, None]


def test_migration_enforces_atomic_completion_and_current_read_indexes(db) -> None:
    db.execute(
        "insert into lineage.fetch_attempts"
        " (attempt_id, source_id, source_key, attempted_at)"
        " values ('fat_00000000000000000000000006', %s, 'guarded.xlsx', now())",
        (SOURCE_ID,),
    )
    db.execute(
        "update lineage.fetch_attempts set completed_at = now(), outcome = 'failed',"
        " failure_code = 'test_failure', failure_detail = 'test failure'"
        " where attempt_id = 'fat_00000000000000000000000006'"
    )

    with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
        db.execute(
            "update lineage.fetch_attempts set failure_code = 'rewritten'"
            " where attempt_id = 'fat_00000000000000000000000006'"
        )
    db.rollback()

    db.execute(
        "insert into lineage.fetch_attempts"
        " (attempt_id, source_id, source_key, attempted_at)"
        " values ('fat_00000000000000000000000007', %s, 'append-only.xlsx', now())",
        (SOURCE_ID,),
    )
    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"):
        db.execute(
            "delete from lineage.fetch_attempts"
            " where attempt_id = 'fat_00000000000000000000000007'"
        )
    db.rollback()

    definitions = {
        name: definition
        for name, definition in db.execute(
            "select indexname, indexdef from pg_indexes"
            " where schemaname = 'lineage' and tablename = 'fetch_attempts'"
        ).fetchall()
    }
    assert "attempted_at DESC" in definitions["fetch_attempts_current_idx"]
    assert "INCLUDE (completed_at, outcome, manifest_id, failure_code, failure_detail)" in (
        definitions["fetch_attempts_current_idx"]
    )
    assert "source_key" in definitions["fetch_attempts_key_current_idx"]
    assert "WHERE (outcome IS NULL)" in definitions["fetch_attempts_open_idx"]
