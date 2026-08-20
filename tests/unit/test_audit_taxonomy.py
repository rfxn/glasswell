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


def test_subject_types_are_enforced():
    for subject_type in SUBJECT_TYPES:
        validate_subject_type(subject_type)
    with pytest.raises(UnknownAuditEvent):
        validate_subject_type("spreadsheet")
