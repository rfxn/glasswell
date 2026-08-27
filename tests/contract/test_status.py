"""The operational Status contract: fresh telemetry, honest gaps and stale-state refusal."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient

from glasswell.db.migrate import discover_migrations
from glasswell.status.collector import SNAPSHOT_ENV, _inventory
from glasswell.status.models import (
    DATABASE_BYTES_REASON,
    INVENTORY_REASON,
    DatasetInventory,
    InventoryMetric,
    PlatformStatus,
    StatusCheck,
    StatusDisclosure,
    StatusSnapshot,
)


def _snapshot(observed_at: datetime) -> StatusSnapshot:
    return StatusSnapshot(
        observed_at=observed_at,
        checks=[
            StatusCheck(
                id="edge",
                label="HTTPS edge",
                state="ok",
                observed_at=observed_at,
                detail="Certificate-verified request answered.",
            )
        ],
        datasets=[
            DatasetInventory(
                dataset_id="canonical.wells_latest",
                label="Current wells",
                scope="North Dakota and Texas",
                grain="one latest effective row per API-10",
                state="available",
                counted_at=observed_at,
                metrics=[
                    InventoryMetric(
                        metric_id="rows",
                        label="Current wells",
                        value=8,
                        unit="wells",
                        precision="exact",
                        reason=INVENTORY_REASON,
                    )
                ],
                detail="Current well entities.",
            )
        ],
        jobs=[],
        platform=PlatformStatus(
            code_version="v0.test+abc1234",
            schema_version=43,
            database_bytes=4096,
            database_bytes_reason=DATABASE_BYTES_REASON,
        ),
        disclosures=[
            StatusDisclosure(
                id="source_check_attempts",
                label="Source check attempts",
                state="limited",
                detail="Registered-artifact age is not last-checked time.",
            )
        ],
    )


def _publish(path: Path, snapshot: StatusSnapshot) -> None:
    path.write_text(snapshot.model_dump_json(), encoding="utf-8")


def test_status_names_the_resource_from_the_service_index(client: TestClient) -> None:
    assert client.get("/v1").json()["links"]["status"] == "/v1/status"


def test_status_joins_live_signals_to_the_current_snapshot(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "status.json"
    _publish(path, _snapshot(datetime.now(UTC)))
    monkeypatch.setenv(SNAPSHOT_ENV, str(path))

    body = client.get("/v1/status").json()
    data = body["data"]

    assert data["snapshot_state"] == "current"
    states = {check["id"]: check["state"] for check in data["checks"]}
    assert {key: states[key] for key in ("api", "postgres", "status_snapshot", "edge")} == {
        "api": "ok",
        "postgres": "ok",
        "status_snapshot": "ok",
        "edge": "ok",
    }
    assert data["datasets"][0]["metrics"][0] == {
        "metric_id": "rows",
        "label": "Current wells",
        "value": 8,
        "unit": "wells",
        "precision": "exact",
        "reason": INVENTORY_REASON,
    }
    assert len(data["sources"]) > 1
    assert body["meta"]["source_freshness"]


def test_status_never_repeats_stale_green_infrastructure(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "status.json"
    _publish(path, _snapshot(datetime.now(UTC) - timedelta(hours=2)))
    monkeypatch.setenv(SNAPSHOT_ENV, str(path))

    data = client.get("/v1/status").json()["data"]
    checks = {check["id"]: check for check in data["checks"]}

    assert data["snapshot_state"] == "stale"
    assert data["state"] == "degraded"
    assert checks["status_snapshot"]["state"] == "degraded"
    assert checks["edge"]["state"] == "unavailable"
    assert "Last detail" in checks["edge"]["detail"]


def test_status_exposes_an_invalid_snapshot_as_a_gap(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "status.json"
    path.write_text('{"observed_at": "not-a-date"}', encoding="utf-8")
    monkeypatch.setenv(SNAPSHOT_ENV, str(path))

    data = client.get("/v1/status").json()["data"]

    assert data["snapshot_state"] == "invalid"
    assert data["state"] == "degraded"
    assert data["datasets"] == []
    assert data["platform"]["schema_version"] is None
    assert data["disclosures"][0]["state"] == "not_instrumented"


def test_inventory_queries_the_declared_grains_not_promotion_bookkeeping(
    seeded: psycopg.Connection,
) -> None:
    observed = datetime(2026, 8, 26, 18, tzinfo=UTC)

    datasets, platform = _inventory(seeded, observed)
    inventory = {dataset.dataset_id: dataset for dataset in datasets}

    production = inventory["canonical.production_monthly"]
    metrics = {metric.metric_id: metric.value for metric in production.metrics}
    assert metrics["rows"] > metrics["wells"]
    assert production.grain == "one append-only source revision per well, month and stream"
    assert production.latest_knowledge_at is not None
    assert inventory["canonical.well_completions/nd"].detail.startswith("Repeated source-month")
    assert inventory["canonical.well_completions/nm"].metrics[0].value == 0
    assert inventory["marts.published_map_layers/nd"].scope == "North Dakota"
    assert inventory["marts.published_map_layers/tx"].scope == "Texas"
    assert inventory["lineage.quarantine_rows"].detail.startswith("A count only")
    assert platform.schema_version == discover_migrations()[-1].version
