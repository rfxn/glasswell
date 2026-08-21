"""DIR-2 arms B and D: identical bytes make one vintage, and the vintage never comes from FTP.

Arm A (changed bytes on two days) and arm C (a moved mod_dte) need the parse half and land in
phase 4's `test_nm_restatement.py`. The FTP server here is a fake: `pyftpdlib` is not in the
lock and the pull against the real host happened exactly once, in phase 1 (SB-01 §1.3).
"""

from __future__ import annotations

import ftplib
import stat
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import ClassVar

import psycopg
import pytest

from glasswell.ingest.base import open_ingest_run
from glasswell.ingest.nm_ocd import FETCH_ATTEMPTS, FTP_HOST, fetch_all, fetch_table, main
from glasswell.lineage import ftp as ftp_module
from glasswell.lineage.fetch import MANIFEST_FILENAME
from glasswell.seed import seed_all
from tests.support.fakes import FixedClock

TABLE = "pool"
SOURCE_ID = "nm_ocd_pool"
PAYLOAD = b"PK\x03\x04\xff\xfe<pool/>" * 64
# The export ran the night before the pull, which is exactly why it cannot be the vintage.
MDTM = "213 20260819225600"
UPSTREAM_MTIME = datetime(2026, 8, 19, 22, 56, tzinfo=UTC)
DAY_ONE = datetime(2026, 8, 20, 6, 15, 0, tzinfo=UTC)
DAY_TWO = DAY_ONE + timedelta(days=1)


class FakeFtp:
    payload: ClassVar[bytes] = PAYLOAD

    def __init__(self, timeout: float | None = None) -> None:
        self.timeout = timeout

    def connect(self, host: str, port: int = 21) -> str:
        return "220 ready"

    def login(self, user: str = "", passwd: str = "") -> str:
        return "230 logged in"

    def set_pasv(self, value: bool) -> None:
        return None

    def voidcmd(self, command: str) -> str:
        return f"200 {command}"

    def sendcmd(self, command: str) -> str:
        return MDTM

    def size(self, path: str) -> int:
        return len(type(self).payload)

    def retrbinary(self, command: str, callback, blocksize: int = 8192) -> str:
        payload = type(self).payload
        for start in range(0, len(payload), blocksize):
            callback(payload[start : start + blocksize])
        return "226 transfer complete"

    def quit(self) -> str:
        return "221 bye"

    def close(self) -> None:
        return None


@pytest.fixture
def fake_ftp(monkeypatch: pytest.MonkeyPatch) -> type[FakeFtp]:
    monkeypatch.setattr(ftp_module, "FTP", FakeFtp)
    return FakeFtp


@pytest.fixture
def seeded(db: psycopg.Connection) -> None:
    seed_all(db)
    db.commit()


def pull(db: psycopg.Connection, raw_root: Path, at: datetime):
    with open_ingest_run(
        db, source_id=SOURCE_ID, raw_root=raw_root, clock=FixedClock(at)
    ) as run:
        result = fetch_table(run, TABLE)
    db.commit()
    return result


def count(db: psycopg.Connection, sql: str, *parameters: object) -> int:
    with db.cursor() as cursor:
        cursor.execute(sql, parameters or None)
        return int(cursor.fetchone()[0])


def harness_dsn(db: psycopg.Connection) -> str:
    """`info.dsn` masks the password, and the CLI opens its own connection."""
    return f"postgresql://glasswell:glasswell@{db.info.host}:{db.info.port}/{db.info.dbname}"


def artifact_directories(raw_root: Path) -> list[Path]:
    return sorted(path.parent for path in raw_root.rglob(MANIFEST_FILENAME))


def test_arm_d_the_vintage_is_the_runs_own_stamp(db, seeded, raw_root, fake_ftp):
    result = pull(db, raw_root, DAY_ONE)

    assert result.fetch_vintage == DAY_ONE.date().isoformat()
    assert result.upstream_mtime == UPSTREAM_MTIME.isoformat()
    assert UPSTREAM_MTIME.date() != DAY_ONE.date()


def test_arm_d_the_ftp_metadata_is_recorded_verbatim(db, seeded, raw_root, fake_ftp):
    pull(db, raw_root, DAY_ONE)

    with db.cursor() as cursor:
        cursor.execute(
            "select acquisition_method, acquisition_url, acquisition_params"
            " from lineage.manifests where source_id = %s",
            (SOURCE_ID,),
        )
        method, url, params = cursor.fetchone()

    assert method == "ftp_anon"
    assert url.startswith(f"ftp://{FTP_HOST}/Public/OCD/OCD%20Interface%20v1.1/")
    assert params["mdtm"] == MDTM
    assert params["size_reported"] == len(PAYLOAD)
    assert params["host"] == FTP_HOST
    assert params["host_resolved_from"] == "pinned_config"


def test_arm_d_a_run_that_crosses_midnight_stamps_one_day(db, seeded, raw_root, fake_ftp):
    """capture.py:110 reads the vintage once, when the session opens (DR-31)."""
    opened_at = datetime(2026, 8, 20, 23, 59, 50, tzinfo=UTC)
    with open_ingest_run(
        db, source_id=SOURCE_ID, raw_root=raw_root, clock=FixedClock(opened_at, step_ms=15_000)
    ) as run:
        result = fetch_table(run, TABLE)
    db.commit()

    assert result.fetch_vintage == "2026-08-20"
    with db.cursor() as cursor:
        cursor.execute(
            "select fetched_at, fetch_vintage from lineage.manifests where source_id = %s",
            (SOURCE_ID,),
        )
        fetched_at, vintage = cursor.fetchone()
    assert fetched_at.date() > vintage
    assert vintage == date(2026, 8, 20)


def test_arm_b_identical_bytes_on_two_days_make_one_vintage(db, seeded, raw_root, fake_ftp):
    first = pull(db, raw_root, DAY_ONE)
    manifests = count(db, "select count(*) from lineage.manifests where source_id = %s", SOURCE_ID)
    second = pull(db, raw_root, DAY_TWO)

    assert first.unchanged is False
    assert second.unchanged is True
    assert second.manifest_id == first.manifest_id
    assert second.fetch_vintage == first.fetch_vintage
    assert manifests == 1
    assert (
        count(db, "select count(*) from lineage.manifests where source_id = %s", SOURCE_ID) == 1
    )


def test_arm_b_the_unchanged_check_is_recorded_and_the_derivation_is_a_noop(
    db, seeded, raw_root, fake_ftp
):
    pull(db, raw_root, DAY_ONE)
    derivations = count(
        db, "select count(*) from lineage.derivations where operation = 'raw.fetch'"
    )
    pull(db, raw_root, DAY_TWO)

    assert (
        count(db, "select count(*) from lineage.derivations where operation = 'raw.fetch'")
        == derivations
    )
    assert (
        count(
            db,
            "select count(*) from lineage.audit_events"
            " where event_type = 'raw.fetch_verified_unchanged'",
        )
        == 1
    )
    assert (
        count(
            db,
            "select count(*) from lineage.audit_events"
            " where event_type = 'raw.manifest_created'",
        )
        == 1
    )


def test_arm_b_the_raw_zone_gains_nothing_and_stays_sealed(db, seeded, raw_root, fake_ftp):
    pull(db, raw_root, DAY_ONE)
    directories = artifact_directories(raw_root)
    pull(db, raw_root, DAY_TWO)

    assert artifact_directories(raw_root) == directories
    assert len(directories) == 1
    assert stat.S_IMODE(directories[0].stat().st_mode) == 0o555
    for entry in directories[0].iterdir():
        assert stat.S_IMODE(entry.stat().st_mode) == 0o444


def test_arm_b_nothing_was_promoted_by_a_fetch(db, seeded, raw_root, fake_ftp):
    pull(db, raw_root, DAY_ONE)
    pull(db, raw_root, DAY_TWO)

    assert count(db, "select count(*) from canonical.production_monthly") == 0
    assert count(db, "select count(*) from lineage.vintages") == 0


def test_the_fetch_derivation_cites_the_rules_that_shaped_it(db, seeded, raw_root, fake_ftp):
    pull(db, raw_root, DAY_ONE)

    with db.cursor() as cursor:
        cursor.execute(
            "select r.rule_id from lineage.derivation_rules r"
            "  join lineage.derivations d on d.derivation_id = r.derivation_id"
            " where d.operation = 'raw.fetch' order by r.rule_id"
        )
        cited = [row[0] for row in cursor.fetchall()]

    assert cited == [
        f"cr_nm_{TABLE}_ftp_layout_1",
        f"cr_nm_{TABLE}_host_pin_1",
        f"cr_nm_{TABLE}_undated_vintage_1",
    ]
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_id = any(%s)", (cited,)
        )
        assert cursor.fetchone()[0] == len(cited)


def test_a_host_that_does_not_answer_halts_and_says_so(db, seeded, raw_root, monkeypatch):
    class Unreachable(FakeFtp):
        def connect(self, host: str, port: int = 21) -> str:
            raise ftplib.error_temp("421 service not available")

    monkeypatch.setattr(ftp_module, "FTP", Unreachable)
    with pytest.raises(OSError, match="anonymous FTP host"):
        pull(db, raw_root, DAY_ONE)

    assert count(db, "select count(*) from lineage.manifests where source_id = %s", SOURCE_ID) == 0
    with db.cursor() as cursor:
        cursor.execute(
            "select payload from lineage.audit_events where event_type = 'raw.fetch_failed'"
        )
        payload = cursor.fetchone()
    assert payload is not None
    assert payload[0]["reason"] == "host_unresolved"
    assert payload[0]["url"].startswith(f"ftp://{FTP_HOST}/")


def test_the_command_line_commits_the_failure_it_halted_on(db, seeded, raw_root, monkeypatch):
    """A halt whose evidence is rolled back is a silent failure (SB-01 §1.2)."""

    class Unreachable(FakeFtp):
        def connect(self, host: str, port: int = 21) -> str:
            raise ftplib.error_temp("421 service not available")

    monkeypatch.setattr(ftp_module, "FTP", Unreachable)
    with pytest.raises(OSError, match="anonymous FTP host"):
        main(
            [
                "--dsn",
                harness_dsn(db),
                "--fetch-only",
                "--tables",
                TABLE,
                "--raw-root",
                str(raw_root),
            ]
        )

    assert (
        count(
            db,
            "select count(*) from lineage.audit_events where event_type = 'raw.fetch_failed'",
        )
        == 1
    )


def test_a_reset_data_channel_is_retried_on_a_fresh_session(db, seeded, raw_root, monkeypatch):
    """164.64.106.6 reset the data channel on the third transfer of the real pull.

    The control connection is unusable afterwards, so the retry reconnects rather than issuing
    another RETR down a broken channel — bounded, spaced, and each failure recorded.
    """
    connections: list[Resetting] = []

    class Resetting(FakeFtp):
        resets: ClassVar[int] = 1

        def __init__(self, timeout: float | None = None) -> None:
            super().__init__(timeout)
            connections.append(self)

        def retrbinary(self, command: str, callback, blocksize: int = 8192) -> str:
            if Resetting.resets:
                Resetting.resets -= 1
                raise ConnectionResetError(104, "Connection reset by peer")
            return super().retrbinary(command, callback, blocksize)

    slept: list[float] = []
    monkeypatch.setattr(ftp_module, "FTP", Resetting)
    with open_ingest_run(
        db, source_id=SOURCE_ID, raw_root=raw_root, clock=FixedClock(DAY_ONE)
    ) as run:
        results = fetch_all(
            run,
            tables=[TABLE],
            raw_root=raw_root,
            backoff_seconds=0.0,
            sleep=slept.append,
        )
    db.commit()

    assert [result.table for result in results] == [TABLE]
    assert len(connections) == 2
    assert slept == [0.0]
    with db.cursor() as cursor:
        cursor.execute(
            "select payload->>'reason' from lineage.audit_events"
            " where event_type = 'raw.fetch_failed'"
        )
        assert [row[0] for row in cursor.fetchall()] == ["ftp_transfer_failed"]
    assert count(db, "select count(*) from lineage.manifests where source_id = %s", SOURCE_ID) == 1


def test_a_source_that_keeps_resetting_stops_being_asked(db, seeded, raw_root, monkeypatch):
    class AlwaysResets(FakeFtp):
        def retrbinary(self, command: str, callback, blocksize: int = 8192) -> str:
            raise ConnectionResetError(104, "Connection reset by peer")

    monkeypatch.setattr(ftp_module, "FTP", AlwaysResets)
    with pytest.raises(OSError, match="transfer failed"):
        with open_ingest_run(
            db, source_id=SOURCE_ID, raw_root=raw_root, clock=FixedClock(DAY_ONE)
        ) as run:
            fetch_all(
                run, tables=[TABLE], raw_root=raw_root, backoff_seconds=0.0, sleep=lambda _: None
            )

    assert (
        count(
            db,
            "select count(*) from lineage.audit_events where event_type = 'raw.fetch_failed'",
        )
        == FETCH_ATTEMPTS
    )
