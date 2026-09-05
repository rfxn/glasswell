from __future__ import annotations

import pytest

from glasswell.lineage.audit import (
    AUDIT_EVENT_TYPES,
    SUBJECT_TYPES,
    validate_event_type,
    validate_subject_type,
)
from glasswell.lineage.errors import UnknownAuditEvent


@pytest.mark.parametrize(
    "event_type",
    [
        "raw.fetch_verified_unchanged",
        "raw.manifest_created",
        "raw.manifest_superseded",
        "canonical.restatement_detected",
        "conformance.rule_superseded",
        "quarantine.opened",
        "repro.failed",
    ],
)
def test_the_sb07_taxonomy_is_present(event_type):
    validate_event_type(event_type)


@pytest.mark.parametrize("event_type", ["", "raw", "raw.made_up", "RAW.MANIFEST_CREATED"])
def test_events_outside_the_checked_in_enum_are_refused(event_type):
    with pytest.raises(UnknownAuditEvent):
        validate_event_type(event_type)


def test_every_event_type_is_dotted_and_lowercase():
    for event_type in AUDIT_EVENT_TYPES:
        assert event_type == event_type.lower()
        assert event_type.count(".") == 1


# The accounts surface adds operations, not event names. `session.revoked` is the name an
# implementer reaches for and the one the taxonomy does not have: a revocation is
# `session.ended` with a reason, so the stream has one name for a session ending.
ACCOUNTS_EVENTS = ("session.ended", "user.updated", "user.created", "user.disabled")


@pytest.mark.parametrize("event_type", ACCOUNTS_EVENTS)
def test_the_accounts_surface_emits_only_names_the_taxonomy_already_carries(event_type):
    validate_event_type(event_type)


def test_session_revoked_is_not_a_name_this_taxonomy_has():
    """A tripwire. Adding it would split one fact across two names retroactively."""
    assert "session.revoked" not in AUDIT_EVENT_TYPES
    with pytest.raises(UnknownAuditEvent):
        validate_event_type("session.revoked")


def test_subject_types_are_enforced():
    for subject_type in SUBJECT_TYPES:
        validate_subject_type(subject_type)
    with pytest.raises(UnknownAuditEvent):
        validate_subject_type("spreadsheet")


# The account half of the taxonomy, moved out of the integration tier: it reads two tuples
# and a database was being cloned for it.
EXPECTED_EVENTS = (
    "user.created",
    "user.updated",
    "user.disabled",
    "password.changed",
    "session.started",
    "session.ended",
    "login.failed",
)


@pytest.mark.parametrize("event_type", EXPECTED_EVENTS)
def test_the_taxonomy_carries_every_account_event(event_type: str) -> None:
    assert event_type in AUDIT_EVENT_TYPES


@pytest.mark.parametrize("subject", ["user", "session"])
def test_the_taxonomy_carries_the_new_subjects(subject: str) -> None:
    assert subject in SUBJECT_TYPES
