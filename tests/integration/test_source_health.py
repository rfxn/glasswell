from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
from psycopg.types.json import Jsonb

from glasswell.api.routers.health import source_health_data
from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.schedules import load_schedules
from glasswell.lineage.store import PostgresRecorder
from glasswell.seed import seed_all
from tests.support.seed import seed_manifest

NOW = datetime(2026, 8, 28, 12, tzinfo=UTC)
# expected_poll_interval states the publisher's rhythm and drives the freshness verdict; the
# job's trigger states who runs it. Montana's production archive is republished on the same
# 35-day rhythm as the ND and BLM feeds, and the load is measured at 74 MB down, 7.4 million
# rows, about an hour and two extra gigabytes, so the owner runs it rather than a tick. Both
# facts are true, and the interval stays so /v1/health still calls the source stale when
# Montana has moved on and glasswell has not.
PUBLISHER_PACED_OWNER_RUN = frozenset({"mt_bogc_pru_production", "mt_bogc_well_production"})


def add_attempt(
    db: psycopg.Connection,
    *,
    attempt_id: str,
    source_id: str,
    attempted_at: datetime,
    outcome: str | None = None,
    manifest_id: str | None = None,
    failure_code: str | None = None,
    failure_detail: str | None = None,
) -> None:
    completed_at = attempted_at + timedelta(minutes=1) if outcome is not None else None
    db.execute(
        "insert into lineage.fetch_attempts"
        " (attempt_id, source_id, source_key, attempted_at, completed_at, outcome, manifest_id,"
        "  failure_code, failure_detail)"
        " values (%s, %s, 'artifact.bin', %s, %s, %s, %s, %s, %s)",
        (
            attempt_id,
            source_id,
            attempted_at,
            completed_at,
            outcome,
            manifest_id,
            failure_code,
            failure_detail,
        ),
    )


def by_id(db: psycopg.Connection) -> dict[str, dict]:
    served, _ = source_health_data(db, observed_at=NOW)
    return {source["source_id"]: source for source in served}


def test_source_health_uses_unchanged_attempt_not_old_artifact_age(db) -> None:
    manifest_id = seed_manifest(
        db,
        sha256="a" * 64,
        fetched_at=NOW - timedelta(days=90),
    )
    add_attempt(
        db,
        attempt_id="fat_00000000000000000000000001",
        source_id="nd_mpr_xlsx",
        attempted_at=NOW - timedelta(minutes=2),
        outcome="unchanged",
        manifest_id=manifest_id,
    )

    source = by_id(db)["nd_mpr_xlsx"]

    assert source["state"] == "current"
    assert source["last_outcome"] == "unchanged"
    assert source["last_attempt_at"] == "2026-08-28T11:58:00+00:00"
    assert source["next_expected_poll"] == "2026-10-02T11:59:00+00:00"
    assert source["cadence"] == "Every 35 days"


def test_source_health_uses_a_cross_source_content_observation(db) -> None:
    db.execute(
        "insert into lineage.sources"
        " (source_id, name, jurisdiction, license_note, redistributable)"
        " values ('cross_source_fixture', 'Cross-source fixture', 'US', 'test only', false)"
    )
    manifest_id = seed_manifest(
        db,
        sha256="9" * 64,
        source_id="cross_source_fixture",
        source_key="shared.zip",
        fetched_at=NOW - timedelta(days=90),
    )
    add_attempt(
        db,
        attempt_id="fat_00000000000000000000000009",
        source_id="nd_mpr_xlsx",
        attempted_at=NOW - timedelta(minutes=2),
        outcome="unchanged",
        manifest_id=manifest_id,
    )

    source = by_id(db)["nd_mpr_xlsx"]

    assert source["state"] == "current"
    assert source["last_manifest_id"] == manifest_id
    assert source["manifest_count"] == 1


def test_source_health_refuses_old_artifact_after_failed_poll_and_redacts_reason(db) -> None:
    seed_manifest(db, sha256="b" * 64, fetched_at=NOW - timedelta(days=90))
    add_attempt(
        db,
        attempt_id="fat_00000000000000000000000002",
        source_id="nd_mpr_xlsx",
        attempted_at=NOW - timedelta(minutes=2),
        outcome="failed",
        failure_code="transport_error",
        failure_detail="token=secret https://user:password@example.test/private",
    )

    source = by_id(db)["nd_mpr_xlsx"]

    assert source["state"] == "stale"
    assert source["last_outcome"] == "failed"
    assert "older artifact does not override" in source["freshness_reason"]
    assert "secret" not in source["freshness_reason"]
    assert "user:password" not in source["freshness_reason"]


def test_source_health_marks_open_attempt_interrupted_and_no_attempt_pending(db) -> None:
    add_attempt(
        db,
        attempt_id="fat_00000000000000000000000003",
        source_id="nd_mpr_xlsx",
        attempted_at=NOW - timedelta(hours=7),
    )

    sources = by_id(db)

    assert (sources["nd_mpr_xlsx"]["state"], sources["nd_mpr_xlsx"]["last_outcome"]) == (
        "stale",
        "interrupted",
    )
    assert sources["nm_ocd_wcproduction"]["state"] == "pending"
    assert sources["nm_ocd_wcproduction"]["last_outcome"] is None


def test_source_health_rejects_future_poll_and_orders_sources_deterministically(db) -> None:
    manifest_id = seed_manifest(db, sha256="c" * 64, fetched_at=NOW)
    add_attempt(
        db,
        attempt_id="fat_00000000000000000000000004",
        source_id="nd_mpr_xlsx",
        attempted_at=NOW + timedelta(minutes=6),
        outcome="new",
        manifest_id=manifest_id,
    )

    served, freshness = source_health_data(db, observed_at=NOW)

    assert [source["source_id"] for source in served] == sorted(freshness)
    nd = next(source for source in served if source["source_id"] == "nd_mpr_xlsx")
    assert nd["state"] == "stale"
    assert "future timestamp" in nd["freshness_reason"]


def test_status_api_serves_bounded_attempt_fields(api_client, db) -> None:
    manifest_id = seed_manifest(db, sha256="d" * 64, fetched_at=datetime.now(UTC))
    attempted_at = datetime.now(UTC) - timedelta(minutes=2)
    add_attempt(
        db,
        attempt_id="fat_00000000000000000000000005",
        source_id="nd_mpr_xlsx",
        attempted_at=attempted_at,
        outcome="new",
        manifest_id=manifest_id,
    )
    db.commit()

    response = api_client.get("/v1/status")
    source = next(
        item for item in response.json()["data"]["sources"] if item["source_id"] == "nd_mpr_xlsx"
    )

    assert response.status_code == 200
    assert source["last_outcome"] == "new"
    assert source["last_attempt_at"] is not None
    assert source["next_expected_poll"] is not None
    assert source["cadence"] == "Every 35 days"
    assert 0 < len(source["freshness_reason"]) <= 512


def test_every_poll_interval_is_bound_to_a_scheduled_job(db) -> None:
    """The invariant the unit-file greps used to carry, read from the registry instead.

    A source with an interval is really scheduled, and one without carries none. Until v0.77
    that was asserted by naming the ten ExecStart lines and two OnCalendar values here, which
    made the test a copy of the unit files rather than a statement about the schedule; the
    registry is now where the decision lives, so this reads it.
    """
    seed_all(db)
    registry = load_schedules(db)
    interval_by_source = {
        row[0]: row[1]
        for row in db.execute(
            "select source_id, expected_poll_interval from lineage.source_poll_policies"
        ).fetchall()
    }
    triggers: dict[str, set[str]] = {}
    for job in registry:
        for source_id in job.source_ids:
            triggers.setdefault(source_id, set()).add(job.trigger)

    scheduled = {
        source_id
        for source_id, interval in interval_by_source.items()
        if interval is not None
    } - PUBLISHER_PACED_OWNER_RUN
    unbacked = {
        source_id
        for source_id in scheduled
        if "cadence" not in triggers.get(source_id, set())
    }
    assert unbacked == set(), (
        f"{sorted(unbacked)} carry a poll interval and no job resolves a cadence over them:"
        " register a job, or register them owner-triggered with a null interval"
    )

    assert set(interval_by_source) >= PUBLISHER_PACED_OWNER_RUN, (
        "an exemption that names a source with no policy row cannot fail, so it is not one"
    )
    assert all(
        triggers[source_id] == {"manual"} for source_id in PUBLISHER_PACED_OWNER_RUN
    ), "an exempted source whose job went on a clock no longer needs the exemption"

    clock_without_an_interval = {
        source_id
        for source_id, kinds in triggers.items()
        if "cadence" in kinds and interval_by_source.get(source_id) is None
    }
    assert clock_without_an_interval == set(), (
        f"{sorted(clock_without_an_interval)} are driven by a cadence job and carry no"
        " interval, so the due rule can compute no instant for them"
    )

    owner_triggered = {
        source_id
        for source_id, interval in interval_by_source.items()
        if interval is None and source_id in triggers
    }
    assert all(triggers[source_id] == {"manual"} for source_id in owner_triggered), {
        source_id: sorted(triggers[source_id])
        for source_id in owner_triggered
        if triggers[source_id] != {"manual"}
    }


def test_a_cadence_job_takes_the_shortest_interval_its_sources_carry(db) -> None:
    """The derivation each cr_job_cadence rule states, asserted rather than restated."""
    seed_all(db)
    registry = load_schedules(db)
    interval_by_source = {
        row[0]: row[1]
        for row in db.execute(
            "select source_id, expected_poll_interval from lineage.source_poll_policies"
        ).fetchall()
    }

    checked = 0
    for job in registry:
        if job.trigger != "cadence" or job.cadence_interval is None or not job.source_ids:
            continue
        expected = min(interval_by_source[source_id] for source_id in job.source_ids)
        assert job.cadence_interval == expected, job.job_id
        checked += 1
    assert checked >= 6, "no multi-source cadence job was checked; this test cannot fail"


def test_later_success_for_another_key_does_not_mask_failed_key(db) -> None:
    failed_at = NOW - timedelta(minutes=4)
    add_attempt(
        db,
        attempt_id="fat_00000000000000000000000006",
        source_id="nd_mpr_xlsx",
        attempted_at=failed_at,
        outcome="failed",
        failure_code="not_found",
        failure_detail="requested month was unavailable",
    )
    manifest_id = seed_manifest(
        db,
        sha256="e" * 64,
        source_key="later.xlsx",
        fetched_at=NOW - timedelta(minutes=2),
    )
    db.execute(
        "insert into lineage.fetch_attempts"
        " (attempt_id, source_id, source_key, attempted_at, completed_at, outcome, manifest_id)"
        " values ('fat_00000000000000000000000007', %s, 'later.xlsx', %s, %s, 'new', %s)",
        (
            "nd_mpr_xlsx",
            NOW - timedelta(minutes=2),
            NOW - timedelta(minutes=1),
            manifest_id,
        ),
    )

    source = by_id(db)["nd_mpr_xlsx"]

    assert source["last_outcome"] == "new"
    assert source["state"] == "stale"
    assert "another key does not clear" in source["freshness_reason"]

    db.execute(
        "insert into lineage.fetch_attempts"
        " (attempt_id, source_id, source_key, attempted_at, completed_at, outcome, manifest_id)"
        " values ('fat_00000000000000000000000008', %s, 'artifact.bin', %s, %s,"
        " 'unchanged', %s)",
        ("nd_mpr_xlsx", NOW, NOW, manifest_id),
    )

    recovered = by_id(db)["nd_mpr_xlsx"]

    assert recovered["state"] == "current"
    assert recovered["last_outcome"] == "unchanged"


def load_ref(db: psycopg.Connection, lineage_env, manifest_id: str) -> None:
    """Stamp a manifest as loaded, through the machinery a stage uses rather than by hand."""
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env), derive(
        "stage.parse",
        output=OutputSpec(
            store="postgres",
            dataset="staging.fixture",
            partition={"manifest_id": manifest_id},
        ),
        params={"member": "fixture"},
        inputs=[InputRef(kind="manifest", ref_id=manifest_id)],
    ) as context:
        context.set_rows(1)
        context.set_output_hash("0" * 64)
    db.execute(
        "update lineage.manifests set staging_load_ref = %s where manifest_id = %s",
        (context.derivation_id, manifest_id),
    )


def test_a_fetched_artifact_whose_parse_refused_is_not_a_current_source(db) -> None:
    """H-1. A refused parse leaves a manifest whose staging load never happened. The poll is
    honestly `new` -- the bytes did land -- so nothing in the attempt ledger says the source is
    behind, and without this the artifact reads current with a fresh retrieval vintage."""
    manifest_id = seed_manifest(db, sha256="b" * 64, fetched_at=NOW - timedelta(minutes=3))
    add_attempt(
        db,
        attempt_id="fat_00000000000000000000000021",
        source_id="nd_mpr_xlsx",
        attempted_at=NOW - timedelta(minutes=3),
        outcome="new",
        manifest_id=manifest_id,
    )
    db.execute(
        "insert into lineage.audit_events (event_id, occurred_at, actor, event_type,"
        " subject_type, subject_id, payload)"
        " values ('evt_parse_refused_fixture', %s, 'system:pipeline', 'staging.load_failed',"
        " 'manifest', %s, %s)",
        (NOW, manifest_id, Jsonb({"source_id": "nd_mpr_xlsx", "reason_code": "format_refused"})),
    )

    source = by_id(db)["nd_mpr_xlsx"]

    assert source["state"] == "stale"
    assert source["last_outcome"] == "new"
    assert "staging" in source["freshness_reason"]


def test_the_parse_that_reads_the_archive_through_is_what_clears_it(db, lineage_env) -> None:
    """The refusal must not be permanent: a manifest that records its staging load is current
    again, which is what makes the refused-then-re-run path resolve on a successful parse."""
    manifest_id = seed_manifest(db, sha256="c" * 64, fetched_at=NOW - timedelta(minutes=3))
    add_attempt(
        db,
        attempt_id="fat_00000000000000000000000022",
        source_id="nd_mpr_xlsx",
        attempted_at=NOW - timedelta(minutes=3),
        outcome="new",
        manifest_id=manifest_id,
    )
    load_ref(db, lineage_env, manifest_id)

    source = by_id(db)["nd_mpr_xlsx"]

    assert source["state"] == "current"


def test_a_refusal_answers_the_same_whether_the_fetch_was_kept_or_rolled_back(db) -> None:
    """H-1's parity, as the sentinel measured it on VM 111: `tx_pdq_dsv` records `failed |
    archiveformaterror` and `co_ecmc_directional_bh` records `failed | malformedarchive`, one
    class of outcome. Texas commits its fetch and Colorado does not, so the two now leave
    different ledger rows -- and the served state must not depend on that difference."""
    seed_all(db)
    texas = seed_manifest(
        db,
        sha256="d" * 64,
        source_id="tx_pdq_dsv",
        source_key="PDQ_DSV.zip",
        fetched_at=NOW - timedelta(minutes=3),
    )
    add_attempt(
        db,
        attempt_id="fat_00000000000000000000000023",
        source_id="tx_pdq_dsv",
        attempted_at=NOW - timedelta(minutes=3),
        outcome="new",
        manifest_id=texas,
    )
    # What a refused Texas stage records: the poll is `new` because the bytes did land, and the
    # refusal is a fact about the parse, against the manifest that names them.
    db.execute(
        "insert into lineage.audit_events (event_id, occurred_at, actor, event_type,"
        " subject_type, subject_id, payload)"
        " values ('evt_tx_parse_refused', %s, 'system:pipeline', 'staging.load_failed',"
        " 'manifest', %s, %s)",
        (
            NOW,
            texas,
            Jsonb({"source_id": "tx_pdq_dsv", "reason_code": "archiveformaterror"}),
        ),
    )
    add_attempt(
        db,
        attempt_id="fat_00000000000000000000000024",
        source_id="co_ecmc_directional_bh",
        attempted_at=NOW - timedelta(minutes=3),
        outcome="failed",
        failure_code="malformedarchive",
        failure_detail="malformedarchive; transport detail withheld from shared status",
    )

    served = by_id(db)

    assert served["tx_pdq_dsv"]["state"] == served["co_ecmc_directional_bh"]["state"] == "stale"
