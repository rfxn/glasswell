from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import psycopg
import pytest

from glasswell.lineage.audit import emit
from glasswell.lineage.errors import UnknownAuditEvent
from tests.support.seed import seed_derivation, seed_manifest, seed_production

OCCURRED_AT = datetime(2026, 8, 1, 5, 2, 11, tzinfo=UTC)


@pytest.fixture
def an_event(db):
    event_id = emit(
        db,
        "canonical.restatement_detected",
        subject_type="vintage",
        subject_id="vin_nm_ocd_wcproduction_2026-08-01",
        payload={"rows_appended": 9412, "months_touched": ["2026-05"]},
        correlation_id="run_nm_nightly",
        actor="system:promote",
        occurred_at=OCCURRED_AT,
    )
    db.commit()
    return event_id


def test_an_emitted_event_is_readable_with_its_payload(db, an_event):
    with db.cursor() as cursor:
        cursor.execute(
            "select actor, event_type, subject_type, correlation_id, payload"
            " from lineage.audit_events where event_id = %s",
            (an_event,),
        )
        assert cursor.fetchone() == (
            "system:promote",
            "canonical.restatement_detected",
            "vintage",
            "run_nm_nightly",
            {"rows_appended": 9412, "months_touched": ["2026-05"]},
        )


def test_event_ids_are_time_ordered(db):
    first = emit(db, "repro.attempted", subject_type="derivation", subject_id="drv_a",
                 occurred_at=OCCURRED_AT)
    second = emit(db, "repro.succeeded", subject_type="derivation", subject_id="drv_a",
                  occurred_at=datetime(2026, 8, 1, 6, tzinfo=UTC))
    db.commit()
    assert first < second


def test_an_event_type_outside_the_taxonomy_never_reaches_the_database(db):
    with pytest.raises(UnknownAuditEvent):
        emit(db, "raw.something_new", subject_type="manifest", subject_id="man_a",
             occurred_at=OCCURRED_AT)
    with db.cursor() as cursor:
        cursor.execute("select count(*) from lineage.audit_events")
        assert cursor.fetchone() == (0,)


def test_updating_an_audit_event_is_rejected(db, an_event):
    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"):
        with db.cursor() as cursor:
            cursor.execute(
                "update lineage.audit_events set actor = 'user:owner' where event_id = %s",
                (an_event,),
            )
    db.rollback()


def test_deleting_an_audit_event_is_rejected(db, an_event):
    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"):
        with db.cursor() as cursor:
            cursor.execute("delete from lineage.audit_events where event_id = %s", (an_event,))
    db.rollback()


def test_neither_runtime_role_holds_an_update_or_delete_grant(db):
    checks = [
        (role, table, privilege)
        for role in ("glasswell_pipeline", "glasswell_api")
        for table in ("lineage.audit_events", "lineage.conformance_rules",
                      "canonical.production_monthly")
        for privilege in ("UPDATE", "DELETE")
    ]
    with db.cursor() as cursor:
        granted = []
        for role, table, privilege in checks:
            cursor.execute("select has_table_privilege(%s, %s, %s)", (role, table, privilege))
            row = cursor.fetchone()
            if row is not None and row[0]:
                granted.append(f"{role} {privilege} {table}")
    assert granted == []


def test_the_api_role_can_append_lineage_but_not_rewrite_it(db):
    with db.cursor() as cursor:
        cursor.execute(
            "select has_table_privilege('glasswell_api', 'lineage.derivations', 'INSERT'),"
            "       has_table_privilege('glasswell_api', 'lineage.derivations', 'UPDATE')"
        )
        assert cursor.fetchone() == (True, False)


def test_a_production_observation_cannot_be_updated_in_place(db):
    manifest = seed_manifest(db, sha256="a" * 64)
    derivation = seed_derivation(db)
    seed_production(
        db,
        api10="33053012340000",
        production_month=date(2024, 3, 1),
        report_vintage=date(2026, 8, 1),
        volume=Decimal("12034.000"),
        manifest_id=manifest,
        derivation_id=derivation,
    )
    db.commit()

    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"):
        with db.cursor() as cursor:
            cursor.execute("update canonical.production_monthly set volume = 1")
    db.rollback()
