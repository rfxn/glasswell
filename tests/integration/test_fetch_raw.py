from __future__ import annotations

import stat
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import orjson
import pytest

from glasswell.ingest.base import open_ingest_run
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.fetch import MANIFEST_FILENAME, fetch_raw
from glasswell.lineage.models import ManifestRecord
from glasswell.lineage.serialization import canonical_json, json_ready
from glasswell.lineage.store import PostgresRecorder
from tests.support.fakes import FixedClock

SOURCE_ID = "nd_mpr_xlsx"
SOURCE_KEY = "2026_03.xlsx"
URL = f"https://www.dmr.nd.gov/oilgas/mpr/{SOURCE_KEY}"
PAYLOAD = b"PK\x03\x04 not really a workbook, but the bytes are what identify it"
RESTATED = PAYLOAD + b" amended"


def client_for(payload: bytes) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload,
            headers={
                "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "etag": '"abc123"',
                "last-modified": "Tue, 18 Aug 2026 06:15:00 GMT",
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def fetch(db, raw_root: Path, lineage_env, payload: bytes = PAYLOAD, key: str = SOURCE_KEY):
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env), client_for(
        payload
    ) as client:
        return fetch_raw(
            db,
            SOURCE_ID,
            key,
            url=URL,
            raw_root=raw_root,
            client=client,
        )


def artifact_directories(raw_root: Path) -> list[Path]:
    return sorted(p.parent for p in raw_root.rglob(MANIFEST_FILENAME))


def count(db, table: str) -> int:
    with db.cursor() as cursor:
        cursor.execute(f"select count(*) from {table}")  # table names are literals in this test
        return cursor.fetchone()[0]


def test_a_first_fetch_writes_the_raw_zone_and_registers_a_manifest(db, raw_root, lineage_env):
    result = fetch(db, raw_root, lineage_env)
    db.commit()

    assert result.created is True
    assert result.unchanged is False
    assert result.payload_path.read_bytes() == PAYLOAD
    assert result.manifest.storage_uri == str(result.payload_path)
    assert result.manifest.fetch_vintage == result.manifest.fetched_at.date()
    assert count(db, "lineage.manifests") == 1


def test_the_raw_zone_uses_the_sb07_2_3_layout(db, raw_root, lineage_env):
    result = fetch(db, raw_root, lineage_env)
    directory = result.payload_path.parent

    assert directory.parent.parent.name == SOURCE_ID
    assert directory.parent.name == "2026-03-xlsx"
    vintage, _, tail = directory.name.partition("T")
    assert vintage == result.manifest.fetch_vintage.isoformat()
    assert tail.endswith(result.manifest.sha256[:12])
    assert result.payload_path.name == "payload.xlsx"


def test_the_colocated_manifest_json_round_trips_to_the_database_row(db, raw_root, lineage_env):
    result = fetch(db, raw_root, lineage_env)
    db.commit()

    on_disk = (result.payload_path.parent / MANIFEST_FILENAME).read_bytes()
    with db.cursor() as cursor:
        cursor.execute(
            "select * from lineage.manifests where manifest_id = %s", (result.manifest.manifest_id,)
        )
        columns = [description.name for description in cursor.description]
        row = dict(zip(columns, cursor.fetchone(), strict=True))

    assert on_disk == canonical_json(json_ready(ManifestRecord(**row).model_dump()))
    assert orjson.loads(on_disk)["sha256"] == result.manifest.sha256


def test_the_payload_and_its_directory_are_sealed_read_only(db, raw_root, lineage_env):
    result = fetch(db, raw_root, lineage_env)
    assert stat.S_IMODE(result.payload_path.stat().st_mode) == 0o444
    assert stat.S_IMODE((result.payload_path.parent / MANIFEST_FILENAME).stat().st_mode) == 0o444
    assert stat.S_IMODE(result.payload_path.parent.stat().st_mode) == 0o555


def test_the_fetch_is_recorded_as_a_derivation_the_manifest_cites(db, raw_root, lineage_env):
    result = fetch(db, raw_root, lineage_env)
    db.commit()

    assert result.manifest.fetch_derivation_id is not None
    with db.cursor() as cursor:
        cursor.execute(
            "select operation, output_dataset, output_sha256, status from lineage.derivations"
            " where derivation_id = %s",
            (result.manifest.fetch_derivation_id,),
        )
        assert cursor.fetchone() == ("raw.fetch", f"raw.{SOURCE_ID}", result.manifest.sha256, "ok")


def test_identical_bytes_re_register_as_a_recorded_check(db, raw_root, lineage_env):
    first = fetch(db, raw_root, lineage_env)
    db.commit()
    second = fetch(db, raw_root, lineage_env)
    db.commit()

    assert second.unchanged is True
    assert second.created is False
    assert second.manifest.manifest_id == first.manifest.manifest_id
    assert second.payload_path == first.payload_path
    assert count(db, "lineage.manifests") == 1
    assert len(artifact_directories(raw_root)) == 1
    # Content addressing makes the repeat fetch the same derivation, not a second one.
    assert count(db, "lineage.derivations") == 1

    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.audit_events where event_type = %s",
            ("raw.fetch_verified_unchanged",),
        )
        assert cursor.fetchone()[0] == 1


def test_changed_bytes_supersede_the_head_and_keep_both_artifacts(db, raw_root, lineage_env):
    first = fetch(db, raw_root, lineage_env)
    db.commit()
    second = fetch(db, raw_root, lineage_env, payload=RESTATED)
    db.commit()

    assert second.created is True
    assert second.manifest.supersedes_manifest_id == first.manifest.manifest_id
    assert count(db, "lineage.manifests") == 2
    assert len(artifact_directories(raw_root)) == 2
    assert first.payload_path.read_bytes() == PAYLOAD
    assert second.payload_path.read_bytes() == RESTATED


def test_the_incoming_directory_never_keeps_a_partial_download(db, raw_root, lineage_env):
    fetch(db, raw_root, lineage_env)
    assert list((raw_root / ".incoming").iterdir()) == []


def test_the_fetch_vintage_follows_the_injected_clock(db, raw_root, lineage_env):
    clock = FixedClock(start=datetime(2026, 5, 14, 13, 12, tzinfo=UTC))
    with lineage_session(
        recorder=PostgresRecorder(db), environment=lineage_env, clock=clock
    ), client_for(PAYLOAD) as client:
        result = fetch_raw(db, SOURCE_ID, SOURCE_KEY, url=URL, raw_root=raw_root, client=client)
    db.commit()

    assert result.manifest.fetched_at == datetime(2026, 5, 14, 13, 12, tzinfo=UTC)
    assert result.manifest.fetch_vintage.isoformat() == "2026-05-14"
    assert result.payload_path.parent.name.startswith("2026-05-14T")


def test_the_run_as_of_and_the_manifest_fetch_vintage_converge(db, raw_root, lineage_env):
    """B2: one clock per run. A divergence here republishes a restatement under the wrong day."""
    clock = FixedClock(start=datetime(2026, 5, 14, 13, 12, tzinfo=UTC))
    with open_ingest_run(
        db, source_id=SOURCE_ID, raw_root=raw_root, environment=lineage_env, clock=clock
    ) as run, client_for(PAYLOAD) as client:
        result = fetch_raw(
            run.connection, SOURCE_ID, SOURCE_KEY, url=URL, raw_root=run.raw_root, client=client
        )
    db.commit()

    assert result.manifest.fetch_vintage == run.as_of


def test_the_vintage_holds_when_the_fetch_crosses_utc_midnight(db, raw_root, lineage_env):
    """DR-31: a run opened at 23:59:30Z lands its bytes on the next day. It stamps one vintage."""
    clock = FixedClock(start=datetime(2026, 5, 14, 23, 59, 30, tzinfo=UTC), step_ms=30_000)
    with open_ingest_run(
        db,
        source_id=SOURCE_ID,
        raw_root=raw_root,
        environment=lineage_env,
        clock=clock,
        correlation_id="run_midnight",
    ) as run, client_for(PAYLOAD) as client:
        result = fetch_raw(
            run.connection, SOURCE_ID, SOURCE_KEY, url=URL, raw_root=run.raw_root, client=client
        )
    db.commit()

    assert run.as_of == date(2026, 5, 14)
    assert result.manifest.fetched_at.date() == date(2026, 5, 15), "the boundary was not crossed"
    assert result.manifest.fetch_vintage == run.as_of
    assert result.payload_path.parent.name.startswith("2026-05-14T")


def test_a_failed_fetch_leaves_no_manifest_and_records_the_attempt(db, raw_root, lineage_env):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env), httpx.Client(
        transport=httpx.MockTransport(handler)
    ) as client, pytest.raises(httpx.HTTPStatusError):
        fetch_raw(db, SOURCE_ID, SOURCE_KEY, url=URL, raw_root=raw_root, client=client)
    db.commit()

    assert count(db, "lineage.manifests") == 0
    assert count(db, "lineage.derivations") == 0
    with db.cursor() as cursor:
        cursor.execute(
            "select payload from lineage.audit_events where event_type = %s", ("raw.fetch_failed",)
        )
        assert cursor.fetchone()[0]["reason"] == "HTTPStatusError"
