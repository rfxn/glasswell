"""The operational Status contract: fresh telemetry, honest gaps and stale-state refusal."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
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
    JobStatus,
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
        jobs=[
            JobStatus(
                id="restore_drill",
                label="Weekly restore drill",
                state="ok",
                last_run_at=observed_at - timedelta(hours=2),
                next_run_at=observed_at + timedelta(days=5),
                detail="Durable restore proof passed; scratch cleanup verified.",
            )
        ],
        platform=PlatformStatus(
            code_version="v0.test+abc1234",
            schema_version=43,
            database_bytes=4096,
            database_bytes_reason=DATABASE_BYTES_REASON,
        ),
        disclosures=[
            StatusDisclosure(
                id="remote_backup_copy",
                label="Remote backup copy",
                state="not_instrumented",
                detail="Remote-copy success is not persisted separately.",
            ),
        ],
    )


def _publish(path: Path, snapshot: StatusSnapshot) -> None:
    path.write_text(snapshot.model_dump_json(), encoding="utf-8")


def _metrics(dataset: DatasetInventory) -> dict[str, int]:
    return {metric.metric_id: metric.value for metric in dataset.metrics}


NM_API10S = ("3002540209", "3004508708")
NM_POOLS = ("96269", "72319")


def _seed_new_mexico_production(connection: psycopg.Connection) -> int:
    """New Mexico rows on New Mexico's own grain, reusing the fixture's lineage anchors.

    The defect this file now guards was invisible to a single-state fixture: an aggregate with
    no state filter is indistinguishable from a correct one until a second state is present.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id from canonical.production_monthly limit 1"
        )
        manifest_id, derivation_id = cursor.fetchone()
        rows = [
            {
                "api10": api10,
                "entity_key": f"{api10}:{pool}",
                "pool": pool,
                "production_month": date(2026, month, 1),
                "stream": stream,
                "manifest_id": manifest_id,
                "derivation_id": derivation_id,
            }
            for api10, pool in zip(NM_API10S, NM_POOLS, strict=True)
            for month in (7, 8)
            for stream in ("oil", "gas")
        ]
        cursor.executemany(
            "insert into canonical.production_monthly (api10, entity_type, entity_key,"
            " reporting_level, well_completion_pool, production_month, stream, source_id,"
            " report_vintage, volume, unit, granularity, value_hash, null_semantics,"
            " source_manifest_id, derivation_id)"
            " values (%(api10)s, 'well_completion_pool', %(entity_key)s, 'well_completion_pool',"
            " %(pool)s, %(production_month)s, %(stream)s, 'nm_ocd_wcproduction',"
            " %(report_vintage)s, %(volume)s, 'bbl', 'well_observed', %(value_hash)s,"
            " 'reported', %(manifest_id)s, %(derivation_id)s)",
            [
                row
                | {
                    "report_vintage": date(2026, 8, 20),
                    "volume": Decimal("101.500"),
                    "value_hash": "f" * 64,
                }
                for row in rows
            ],
        )
    return len(rows)


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
    nd_source = next(
        source for source in data["sources"] if source["source_id"] == "nd_mpr_xlsx"
    )
    assert nd_source["last_outcome"] is None
    assert nd_source["cadence"] == "Every 35 days"
    assert nd_source["freshness_reason"]
    restore = next(job for job in data["jobs"] if job["id"] == "restore_drill")
    assert restore["state"] == "ok"
    assert "cleanup verified" in restore["detail"]
    remote_copy = next(
        disclosure
        for disclosure in data["disclosures"]
        if disclosure["id"] == "remote_backup_copy"
    )
    assert remote_copy["state"] == "not_instrumented"
    assert "success" in remote_copy["detail"]
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

    nd_wells = inventory["canonical.wells_latest/nd"].metrics[0].value
    tx_wells = inventory["canonical.wells_latest/tx"].metrics[0].value
    with seeded.cursor() as cursor:
        cursor.execute(
            "select state_code, count(*) from canonical.wells_latest"
            " where state_code in ('33', '42') group by state_code"
        )
        direct_well_counts = dict(cursor.fetchall())
    assert (nd_wells, tx_wells) == (7, 1)
    assert {"33": nd_wells, "42": tx_wells} == direct_well_counts

    production = inventory["canonical.production_monthly/nd"]
    metrics = {metric.metric_id: metric.value for metric in production.metrics}
    assert metrics["rows"] > metrics["wells"]
    assert production.grain == "one append-only source revision per well, month and stream"
    assert production.latest_knowledge_at is not None
    assert inventory["canonical.well_completions/nd"].detail.startswith("Repeated source-month")
    assert inventory["canonical.well_completions/nm"].metrics[0].value == 0
    assert inventory["marts.published_map_layers/nd"].scope == "North Dakota"
    assert inventory["marts.published_map_layers/tx"].scope == "Texas"
    subject_metrics = {
        metric.metric_id: metric.value
        for metric in inventory["marts.nd_neighbor_subjects"].metrics
    }
    edge_metrics = {
        metric.metric_id: metric.value for metric in inventory["marts.nd_neighbor_edges"].metrics
    }
    assert subject_metrics == {"subjects": 3, "dated_subjects": 3}
    assert edge_metrics == {"directed_edges": 4}
    assert inventory["marts.nd_neighbor_subjects"].valid_from is None
    assert inventory["marts.nd_neighbor_subjects"].valid_to is None
    assert inventory["lineage.quarantine_rows"].detail.startswith("A count only")
    assert platform.schema_version == discover_migrations()[-1].version


def test_production_is_inventoried_under_the_state_that_reported_it(
    seeded: psycopg.Connection,
) -> None:
    """A New Mexico row served under a North Dakota jurisdiction is a naked number, not a label.

    `glasswell-status.timer` runs `*:0/15`, so the first New Mexico promotion would have
    published its rows under North Dakota within fifteen minutes, unattended, into an
    append-only surface, over rows with no well header.
    """
    observed = datetime(2026, 8, 26, 18, tzinfo=UTC)
    nm_rows = _seed_new_mexico_production(seeded)

    datasets, _ = _inventory(seeded, observed)
    inventory = {dataset.dataset_id: dataset for dataset in datasets}

    assert "canonical.production_monthly" not in inventory, (
        "the unqualified id claimed one jurisdiction for every state's rows"
    )
    nd, nm = (
        inventory["canonical.production_monthly/nd"],
        inventory["canonical.production_monthly/nm"],
    )
    assert (nd.scope, nm.scope) == ("North Dakota", "New Mexico")
    assert _metrics(nm) == {"rows": nm_rows, "wells": len(NM_API10S)}
    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(*), count(distinct api10) from canonical.production_monthly"
            " where left(api10, 2) = '33'"
        )
        nd_rows, nd_wells = cursor.fetchone()
        cursor.execute("select count(*) from canonical.production_monthly")
        total = cursor.fetchone()[0]
    assert _metrics(nd) == {"rows": nd_rows, "wells": nd_wells}
    # The two datasets partition the table. A third population — a Texas lease row, whose api10
    # is null by migration 020 — would be counted by neither, so it must fail here rather than
    # disappear from a served figure.
    assert _metrics(nd)["rows"] + _metrics(nm)["rows"] == total
    assert nm.valid_from == "2026-07-01"
    assert nm.valid_to == "2026-08-01"
    assert nd.valid_from != nm.valid_from
    assert nd.valid_to != nm.valid_to


def test_new_mexico_production_reports_zero_before_its_rows_arrive(
    seeded: psycopg.Connection,
) -> None:
    """The convention `canonical.well_completions/nm` already sets: zero, under its own scope."""
    datasets, _ = _inventory(seeded, datetime(2026, 8, 26, 18, tzinfo=UTC))
    inventory = {dataset.dataset_id: dataset for dataset in datasets}

    nm = inventory["canonical.production_monthly/nm"]
    assert [metric.value for metric in nm.metrics] == [0, 0]
    assert nm.scope == "New Mexico"
    assert nm.valid_from is None
    assert nm.valid_to is None
