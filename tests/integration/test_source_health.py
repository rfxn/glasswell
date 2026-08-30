from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg

from glasswell.api.routers.health import source_health_data
from tests.support.seed import seed_manifest

NOW = datetime(2026, 8, 28, 12, tzinfo=UTC)


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


def test_poll_policy_matches_the_recurring_units(db) -> None:
    policies = {
        row[0]: (row[1], row[2])
        for row in db.execute(
            "select source_id, cadence, expected_poll_interval"
            " from lineage.source_poll_policies"
        ).fetchall()
    }
    scheduled = {
        "blm_plss_sections",
        "blm_plss_townships",
        "nd_gis_directionals",
        "nd_gis_horizontals_line",
        "nd_gis_spacing_units",
        "nd_gis_wells",
        "nd_mpr_xlsx",
        "nm_c115b_upstream",
        # Montana publishes on the same cadence as the ND and BLM feeds. nm_ocd_wells_gis is
        # deliberately absent: 061 registers it owner-triggered, like its nine FTP siblings.
        "mt_bogc_well_production",
        "mt_bogc_pru_production",
        "mt_gis_wells",
        "mt_gis_well_paths",
    }

    assert all(policies[source] == ("Every 35 days", timedelta(days=35)) for source in scheduled)
    unscheduled_with_an_interval = {
        source
        for source, (_cadence, interval) in policies.items()
        if source not in scheduled and interval is not None
    }
    assert not unscheduled_with_an_interval, (
        f"{sorted(unscheduled_with_an_interval)} carry a poll interval but are not listed as"
        " scheduled — add them here, or register them owner-triggered with a null interval"
    )
    root = Path(__file__).resolve().parents[2]
    ingest_service = (root / "infra/systemd/glasswell-ingest.service").read_text()
    ingest_timer = (root / "infra/systemd/glasswell-ingest.timer").read_text()
    c115b_service = (root / "infra/systemd/glasswell-c115b.service").read_text()
    c115b_timer = (root / "infra/systemd/glasswell-c115b.timer").read_text()
    assert "glasswell.ingest.nd_gis --layer all" in ingest_service
    assert "glasswell.ingest.nd_mpr --month" in ingest_service
    assert "glasswell.ingest.blm_plss --layer all" in ingest_service
    assert "OnCalendar=*-*-05" in ingest_timer
    assert "glasswell.ingest.nm_c115b" in c115b_service
    assert "OnCalendar=*-*-12" in c115b_timer
    assert "fracfocus" not in ingest_service.lower()


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
