"""The append-only audit stream (SB-07 §5). One stream, one emitter."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from glasswell.lineage.clock import Clock, SystemClock
from glasswell.lineage.errors import UnknownAuditEvent
from glasswell.lineage.ids import new_ulid
from glasswell.lineage.models import AuditEvent

AUDIT_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "raw.fetch_attempted",
        "raw.fetch_verified_unchanged",
        "raw.manifest_created",
        "raw.manifest_superseded",
        "raw.guid_resolved",
        "raw.fetch_failed",
        "raw.integrity_verified",
        "raw.integrity_failed",
        "staging.load_completed",
        "staging.load_failed",
        "staging.rows_quarantined",
        # A record left out of staging because the run's scope did not cover it. Not a reject:
        # nothing failed, the raw bytes are unchanged, and widening the scope is a re-parse. The
        # count is what stops an exclusion from being invisible in the staged row total.
        "staging.scope_excluded",
        "canonical.promotion_completed",
        "canonical.vintage_opened",
        "canonical.restatement_detected",
        "canonical.repromotion_required",
        "conformance.rule_added",
        "conformance.rule_superseded",
        "conformance.rule_applied_summary",
        "quarantine.opened",
        "quarantine.reoccurred",
        "quarantine.released",
        "quarantine.accepted_loss",
        # Extends §5.2: migration 011 restores reason codes the 007 CHECK forced to degrade,
        # and a correction to the ledger is itself a fact about the ledger.
        "quarantine.relabelled",
        "model.training_started",
        "model.training_completed",
        "model.registered",
        "model.promoted",
        "model.retired",
        "publication.accepted",
        "ledger.graded",
        "mart.refreshed",
        "mart.invalidated",
        "tiles.built",
        "key.issued",
        "key.revoked",
        "access.denied",
        "config.changed",
        "repro.attempted",
        "repro.succeeded",
        "repro.failed",
        # Extends §5.2: the store-side determinism detector of §1.3 needs a stream entry.
        "lineage.determinism_violated",
    }
)

SUBJECT_TYPES: frozenset[str] = frozenset(
    {
        "manifest",
        "derivation",
        "rule",
        "model",
        "quarantine",
        "vintage",
        "key",
        "config",
        "aoi",
        "wellset",
        "publication",
        "ledger",
    }
)


def validate_event_type(event_type: str) -> None:
    if event_type not in AUDIT_EVENT_TYPES:
        raise UnknownAuditEvent(f"{event_type!r} is not in the checked-in event taxonomy")


def validate_subject_type(subject_type: str) -> None:
    if subject_type not in SUBJECT_TYPES:
        raise UnknownAuditEvent(f"{subject_type!r} is not a recorded subject type")


def emit(
    connection: psycopg.Connection,
    event_type: str,
    *,
    subject_type: str,
    subject_id: str,
    payload: Mapping[str, Any] | None = None,
    correlation_id: str | None = None,
    actor: str = "system:pipeline",
    occurred_at: datetime | None = None,
    clock: Clock | None = None,
) -> str:
    """Append one event. There is no update path — see migration 004."""
    validate_event_type(event_type)
    validate_subject_type(subject_type)
    happened_at = occurred_at or (clock or SystemClock()).now()
    event = AuditEvent(
        event_id=new_ulid(happened_at),
        occurred_at=happened_at,
        actor=actor,
        event_type=event_type,
        subject_type=subject_type,
        subject_id=subject_id,
        correlation_id=correlation_id,
        payload=payload or {},
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.audit_events (event_id, occurred_at, actor, event_type,"
            " subject_type, subject_id, correlation_id, payload)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                event.event_id,
                event.occurred_at,
                event.actor,
                event.event_type,
                event.subject_type,
                event.subject_id,
                event.correlation_id,
                Jsonb(dict(event.payload)),
            ),
        )
    return event.event_id
