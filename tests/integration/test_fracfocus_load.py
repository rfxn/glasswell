from __future__ import annotations

import hashlib
import io
from datetime import UTC, date, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import httpx
import psycopg
import pytest

from glasswell.ingest.fracfocus import DOWNLOAD_URL, TERMS_URL, load_disclosures
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.seed import seed_all
from tests.support.fakes import FixedClock
from tests.support.seed import seed_well

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "fracfocus"
RUN_AT = datetime(2026, 8, 26, 16, 0, tzinfo=UTC)
TERMS = b"FracFocus fixture terms and conditions"


def archive_bytes() -> bytes:
    payload = io.BytesIO()
    with ZipFile(payload, "w", ZIP_DEFLATED) as archive:
        for name in ("DisclosureList_1.csv", "readme csv.txt"):
            member = ZipInfo(name, date_time=(2026, 8, 26, 8, 0, 0))
            member.compress_type = ZIP_DEFLATED
            archive.writestr(member, (FIXTURES / name).read_bytes())
        member = ZipInfo("WaterSource_1.csv", date_time=(2026, 8, 26, 8, 0, 0))
        member.compress_type = ZIP_DEFLATED
        archive.writestr(member, b"WaterSourceId,DisclosureId\n")
    return payload.getvalue()


def client_for(payload: bytes) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TERMS_URL:
            return httpx.Response(200, content=TERMS, headers={"content-type": "text/html"})
        if str(request.url) == DOWNLOAD_URL:
            return httpx.Response(200, content=payload, headers={"content-type": "application/zip"})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def scalar(connection, sql: str, parameters: tuple = ()):
    with connection.cursor() as cursor:
        cursor.execute(sql, parameters)
        row = cursor.fetchone()
    return row[0] if row else None


@pytest.fixture
def loaded(db: psycopg.Connection, raw_root, lineage_env):
    seed_all(db)
    for api10 in ("3304300002", "3305303901", "3304300004", "3304300003"):
        seed_well(db, api10=api10, basin=None)
    payload = archive_bytes()
    with lineage_session(
        recorder=PostgresRecorder(db),
        environment=lineage_env,
        clock=FixedClock(start=RUN_AT),
    ), client_for(payload) as client:
        result = load_disclosures(db, raw_root=raw_root, client=client)
    db.commit()
    return result, payload


def test_fracfocus_records_terms_inventory_and_source_faithful_staging(loaded, db):
    result, payload = loaded
    assert result.staged_rows == 8
    assert result.anchor_rows == 3
    assert result.well_rows == 4
    assert result.quarantined == {
        "parse_error": 1,
        "out_of_range_date": 1,
        "orphan_fk": 1,
        "duplicate_row": 1,
    }
    with db.cursor() as cursor:
        cursor.execute(
            "select sha256, acquisition_method, acquisition_params, decompressed_inventory"
            " from lineage.manifests where manifest_id = %s",
            (result.manifest_id,),
        )
        sha256, method, params, inventory = cursor.fetchone()
    assert sha256 == hashlib.sha256(payload).hexdigest()
    assert method == "click_wall_accept"
    assert params["terms_sha256"] == hashlib.sha256(TERMS).hexdigest()
    assert params["terms_manifest_id"] == result.terms_manifest_id
    assert {member["member"] for member in inventory} == {
        "DisclosureList_1.csv",
        "WaterSource_1.csv",
        "readme csv.txt",
    }
    assert all(len(member["sha256"]) == 64 for member in inventory)


def test_earliest_valid_job_end_is_selected_without_a_spud_fallback(loaded, db):
    assert scalar(
        db,
        "select completion_date from canonical.wells_latest where api10 = '3304300002'",
    ) == date(2012, 1, 20)
    assert scalar(
        db,
        "select completion_date from canonical.wells_latest where api10 = '3305303901'",
    ) == date(2020, 2, 15)
    assert scalar(
        db,
        "select completion_date from canonical.wells_latest where api10 = '3304300004'",
    ) is None
    assert scalar(db, "select count(*) from canonical.wells_latest where basin = 'williston'") == 4
    assert scalar(db, "select count(*) from canonical.well_completion_anchors") == 3


def test_completion_anchors_are_append_only(loaded, db):
    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"):
        with db.cursor() as cursor:
            cursor.execute(
                "update canonical.well_completion_anchors set completion_date = '2020-01-01'"
            )
    db.rollback()


def test_reloading_identical_terms_and_archive_is_a_no_op(loaded, db, raw_root, lineage_env):
    first, payload = loaded
    before = scalar(db, "select count(*) from canonical.wells")
    with lineage_session(
        recorder=PostgresRecorder(db),
        environment=lineage_env,
        clock=FixedClock(start=RUN_AT),
    ), client_for(payload) as client:
        second = load_disclosures(db, raw_root=raw_root, client=client)
    db.commit()

    assert second.unchanged is True
    assert second.manifest_id == first.manifest_id
    assert scalar(db, "select count(*) from canonical.wells") == before
