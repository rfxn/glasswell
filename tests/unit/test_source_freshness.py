from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from glasswell.lineage.fetch_attempts import sanitized_evidence_text
from glasswell.status.models import source_freshness

NOW = datetime(2026, 8, 28, 12, tzinfo=UTC)
INTERVAL = timedelta(days=8)
TIMEOUT = timedelta(hours=6)


def assess(**overrides):
    values = {
        "observed_at": NOW,
        "artifact_at": NOW - timedelta(days=90),
        "attempted_at": NOW - timedelta(minutes=2),
        "completed_at": NOW - timedelta(minutes=1),
        "recorded_outcome": "unchanged",
        "expected_interval": INTERVAL,
        "attempt_timeout": TIMEOUT,
        "cadence": "Every 8 days",
        "failure_code": None,
        "failure_detail": None,
    }
    return source_freshness(**{**values, **overrides})


def test_unchanged_poll_keeps_old_artifact_current_without_rewriting_its_age() -> None:
    result = assess()

    assert result.state == "current"
    assert result.last_outcome == "unchanged"
    assert "older artifact" in result.reason
    assert result.next_expected_poll == NOW - timedelta(minutes=1) + INTERVAL


def test_failed_poll_is_stale_even_when_an_artifact_exists() -> None:
    result = assess(
        recorded_outcome="failed",
        artifact_at=NOW - timedelta(minutes=1),
        failure_code="http_status_error",
        failure_detail="upstream returned 503",
    )

    assert result.state == "stale"
    assert result.last_outcome == "failed"
    assert "older artifact does not override" in result.reason
    assert "http_status_error" in result.reason


def test_failure_reason_is_redacted_and_bounded_before_status_serves_it() -> None:
    secret = "token=top-secret https://user:password@example.test/file?api_key=also-secret"
    result = assess(
        recorded_outcome="failed",
        failure_code="transport_error",
        failure_detail=secret * 20,
    )

    assert "top-secret" not in result.reason
    assert "also-secret" not in result.reason
    assert "user:password" not in result.reason
    assert "[redacted]" in result.reason
    assert len(result.reason) <= 512


def test_cadence_boundary_is_current_at_the_instant_and_stale_after_it() -> None:
    completed = NOW - INTERVAL

    assert assess(completed_at=completed, attempted_at=completed).state == "current"
    assert assess(
        observed_at=NOW + timedelta(microseconds=1),
        completed_at=completed,
        attempted_at=completed,
    ).state == "stale"


def test_open_attempt_becomes_interrupted_only_after_its_timeout() -> None:
    attempted = NOW - TIMEOUT

    at_boundary = assess(
        attempted_at=attempted,
        completed_at=None,
        recorded_outcome=None,
    )
    after_boundary = assess(
        observed_at=NOW + timedelta(microseconds=1),
        attempted_at=attempted,
        completed_at=None,
        recorded_outcome=None,
    )

    assert (at_boundary.state, at_boundary.last_outcome) == ("pending", "attempted")
    assert (after_boundary.state, after_boundary.last_outcome) == ("stale", "interrupted")


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"attempted_at": NOW + timedelta(minutes=6)}, "poll evidence"),
        ({"artifact_at": NOW + timedelta(minutes=6)}, "artifact timestamp"),
        (
            {
                "attempted_at": None,
                "completed_at": None,
                "recorded_outcome": None,
                "artifact_at": NOW + timedelta(minutes=6),
            },
            "artifact timestamp",
        ),
    ],
)
def test_future_timestamps_never_create_current_freshness(overrides, reason) -> None:
    result = assess(**overrides)

    assert result.state == "stale"
    assert reason in result.reason


def test_no_attempts_distinguish_empty_recent_and_overdue_artifacts() -> None:
    common = {
        "attempted_at": None,
        "completed_at": None,
        "recorded_outcome": None,
    }

    empty = assess(artifact_at=None, **common)
    recent = assess(artifact_at=NOW - timedelta(days=1), **common)
    overdue = assess(artifact_at=NOW - timedelta(days=9), **common)

    assert (empty.state, empty.last_outcome) == ("pending", None)
    assert recent.state == "pending"
    assert "not inferred" in recent.reason
    assert overdue.state == "stale"
    assert "older than the expected poll interval" in overdue.reason


def test_event_driven_success_has_no_invented_next_poll() -> None:
    result = assess(expected_interval=None, cadence="When the dependency pin changes")

    assert result.state == "current"
    assert result.next_expected_poll is None


@pytest.mark.parametrize(
    "detail",
    [
        "Authorization: Bearer sk-live-secret",
        "API key: sk-live-secret",
        "{'Authorization': 'Bearer sk-live-secret'}",
        "request failed with Bearer sk-live-secret",
        "request failed with Basic dXNlcjpzZWNyZXQ=",
    ],
)
def test_failure_sanitizer_redacts_header_and_standalone_credentials(detail: str) -> None:
    safe = sanitized_evidence_text(detail)

    assert "sk-live-secret" not in safe
    assert "dXNlcjpzZWNyZXQ=" not in safe
    assert "[redacted]" in safe


def test_failure_sanitizer_redacts_host_and_path_evidence() -> None:
    detail = (
        "connection to db01.prod.internal (10.1.2.3) failed while reading"
        " /srv/glasswell/raw/private.csv or C:\\glasswell\\private.csv"
    )

    safe = sanitized_evidence_text(detail)

    assert "db01.prod.internal" not in safe
    assert "10.1.2.3" not in safe
    assert "/srv/glasswell" not in safe
    assert "C:\\glasswell" not in safe
    assert "[redacted-host]" in safe
    assert "[redacted-path]" in safe


def test_an_artifact_that_was_fetched_and_never_parsed_is_not_current() -> None:
    """H-1. A fetch and a parse are two outcomes. An ingest that keeps its manifest when the
    parse refuses leaves an honestly successful poll behind, so the poll alone cannot say
    whether anything ever read the artifact."""
    result = assess(recorded_outcome="new", artifact_unloaded=True)

    assert result.state == "stale"
    assert result.last_outcome == "new"
    assert "never loaded into staging" in result.reason


def test_a_failed_poll_still_reads_as_the_failure_and_not_as_an_unloaded_artifact() -> None:
    """The two are different facts and the poll's is the stronger one: a source that could not
    be fetched at all should say so rather than reporting on a parse that never started."""
    result = assess(recorded_outcome="failed", failure_code="malformedarchive",
                    artifact_unloaded=True)

    assert result.state == "stale"
    assert result.last_outcome == "failed"
    assert "malformedarchive" in result.reason


def test_the_default_is_loaded_so_no_source_goes_stale_for_not_stamping() -> None:
    """Nothing but the Texas stage records a staging load today, so the parameter defaults to
    the answer that changes no other source's served state."""
    assert assess().state == "current"
