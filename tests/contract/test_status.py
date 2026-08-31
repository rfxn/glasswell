"""The operational Status contract: fresh telemetry, honest gaps and stale-state refusal."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

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


MT_API10S = ("2508321001", "2508321002")
MT_LEASE_UNITS = ("05100", "05101", "05102")


def _seed_montana_production(connection: psycopg.Connection) -> tuple[int, int]:
    """Both MBOGC grains, because only one of them is reachable by an API-10 prefix.

    The lease grain carries a lease `entity_key` and a null api10 — the third population the
    partition assertion above was written to catch — so a Montana arm filtered the way the ND
    and NM arms are filtered would report the well grain and silently drop 28% of the state.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id from canonical.production_monthly limit 1"
        )
        manifest_id, derivation_id = cursor.fetchone()
        common = {
            "report_vintage": date(2026, 8, 30),
            "volume": Decimal("42.000"),
            "manifest_id": manifest_id,
            "derivation_id": derivation_id,
        }
        well_rows = [
            common
            | {
                "api10": api10,
                "entity_key": api10,
                "production_month": date(2026, month, 1),
                "stream": stream,
                "value_hash": f"{index:064d}",
            }
            for index, (api10, month, stream) in enumerate(
                (api10, month, stream)
                for api10 in MT_API10S
                for month in (5, 6)
                for stream in ("oil", "gas")
            )
        ]
        cursor.executemany(
            "insert into canonical.production_monthly (api10, entity_type, entity_key,"
            " reporting_level, production_month, stream, source_id, report_vintage, volume,"
            " unit, granularity, value_hash, null_semantics, source_manifest_id, derivation_id)"
            " values (%(api10)s, 'well', %(entity_key)s, 'well', %(production_month)s,"
            " %(stream)s, 'mt_bogc_well_production', %(report_vintage)s, %(volume)s, 'bbl',"
            " 'well_observed', %(value_hash)s, 'reported', %(manifest_id)s, %(derivation_id)s)",
            well_rows,
        )
        lease_rows = [
            common
            | {
                "entity_key": unit,
                "production_month": date(2026, month, 1),
                "stream": stream,
                "value_hash": f"{index + 1000:064d}",
            }
            for index, (unit, month, stream) in enumerate(
                (unit, month, stream)
                for unit in MT_LEASE_UNITS
                for month in (5, 6)
                for stream in ("oil", "gas")
            )
        ]
        cursor.executemany(
            "insert into canonical.production_monthly (api10, entity_type, entity_key,"
            " reporting_level, production_month, stream, source_id, report_vintage, volume,"
            " unit, granularity, value_hash, null_semantics, source_manifest_id, derivation_id)"
            " values (null, 'lease', %(entity_key)s, 'lease', %(production_month)s, %(stream)s,"
            " 'mt_bogc_pru_production', %(report_vintage)s, %(volume)s, 'bbl',"
            " 'lease_reported', %(value_hash)s, 'reported', %(manifest_id)s, %(derivation_id)s)",
            lease_rows,
        )
    return len(well_rows), len(lease_rows)


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


def test_deployment_posture_is_read_from_the_serving_process_not_the_snapshot(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    """Only the process that enforces the posture can report it, so it is not snapshot state."""
    monkeypatch.setenv(SNAPSHOT_ENV, str(tmp_path / "absent.json"))
    monkeypatch.setenv("GLASSWELL_PUBLIC", "1")
    monkeypatch.delenv("GLASSWELL_ALLOW_ANON", raising=False)
    monkeypatch.setenv("GLASSWELL_MARTIN_URL", "http://tiles.invalid:3000")

    posture = client.get("/v1/status").json()["data"]["deployment"]

    assert posture == {
        "public_origin": True,
        "anonymous_reads": False,
        "spa_served": False,
        "basemap_served": False,
        "tile_upstream": "configured",
        "csp_report_only": False,
    }
    # The upstream address is host state; only that it was overridden is served.
    assert "tiles.invalid" not in client.get("/v1/status").text

    monkeypatch.setenv("GLASSWELL_ALLOW_ANON", "1")
    monkeypatch.delenv("GLASSWELL_PUBLIC", raising=False)
    monkeypatch.delenv("GLASSWELL_MARTIN_URL", raising=False)
    reread = client.get("/v1/status").json()["data"]["deployment"]
    assert (reread["public_origin"], reread["anonymous_reads"], reread["tile_upstream"]) == (
        False,
        True,
        "default",
    )


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
    assert inventory["lineage.quarantine_rows"].detail.startswith("Counts only")
    assert platform.schema_version == discover_migrations()[-1].version
    assert platform.edge_host is not None


def test_quarantine_is_inventoried_by_reason_and_the_reasons_partition_the_total(
    seeded: psycopg.Connection,
) -> None:
    """A single open-row count says a number was rejected, never what refused it."""
    quarantine = {
        dataset.dataset_id: dataset
        for dataset in _inventory(seeded, datetime(2026, 8, 26, 18, tzinfo=UTC))[0]
    }["lineage.quarantine_rows"]
    metrics = _metrics(quarantine)

    with seeded.cursor() as cursor:
        cursor.execute(
            "select reason_code, count(*) from lineage.quarantine_rows"
            " where state = 'open' group by reason_code"
        )
        direct = {f"reason_{code}": rows for code, rows in cursor.fetchall()}

    assert direct, "the fixture must hold open quarantine, or this test cannot fail"
    assert {key: value for key, value in metrics.items() if key != "open_rows"} == direct
    assert sum(direct.values()) == metrics["open_rows"]
    assert all(metric.precision == "exact" for metric in quarantine.metrics)


def test_registered_conformance_rules_are_inventoried_with_the_rules_in_force(
    seeded: psycopg.Connection,
) -> None:
    """R8 makes the registry the mapping surface; a page that never counts it cannot show that."""
    rules = {
        dataset.dataset_id: dataset
        for dataset in _inventory(seeded, datetime(2026, 8, 26, 18, tzinfo=UTC))[0]
    }["lineage.conformance_rules"]
    metrics = _metrics(rules)

    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(*), count(distinct rule_family), count(distinct source_id)"
            " from lineage.conformance_rules"
        )
        total, families, sources = cursor.fetchone()

    assert metrics == {
        "rules": total,
        "in_force": metrics["in_force"],
        "families": families,
        "sources": sources,
    }
    assert 0 < metrics["in_force"] <= total
    assert rules.grain == "one registered mapping decision per rule id"
    # A registry has no validity interval; claiming one from min/max effective_from would be
    # a span that qualifies nothing. `in_force` is the temporal fact it does carry.
    assert (rules.valid_from, rules.valid_to) == (None, None)


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
    # Montana too, and specifically its lease grain: the partition below is only load-bearing
    # while a population exists that no api10 predicate can reach.
    mt_well_rows, mt_lease_rows = _seed_montana_production(seeded)

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
    assert _metrics(nm) == {"rows": nm_rows, "wells": len(NM_API10S), "months": 2}
    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(*), count(distinct api10), count(distinct production_month)"
            " from canonical.production_monthly where left(api10, 2) = '33'"
        )
        nd_rows, nd_wells, nd_months = cursor.fetchone()
        cursor.execute("select count(*) from canonical.production_monthly")
        total = cursor.fetchone()[0]
    assert _metrics(nd) == {"rows": nd_rows, "wells": nd_wells, "months": nd_months}
    # A span of two endpoints cannot show a hole between them; the month count can.
    assert nd_months <= 12 * 12
    # The datasets partition the table. A population counted by none of them — a lease row,
    # whose api10 is null by migration 020 — must fail here rather than disappear from a
    # served figure. Montana files exactly such a grain, so its two arms join the sum.
    montana = sum(
        _metrics(inventory[f"canonical.production_monthly/mt-{grain}"])["rows"]
        for grain in ("well", "lease")
    )
    assert montana == mt_well_rows + mt_lease_rows
    assert mt_lease_rows > 0, "without a null-api10 population the partition proves nothing"
    assert _metrics(nd)["rows"] + _metrics(nm)["rows"] + montana == total
    assert nm.valid_from == "2026-07-01"
    assert nm.valid_to == "2026-08-01"
    assert nd.valid_from != nm.valid_from
    assert nd.valid_to != nm.valid_to


def test_montana_is_inventoried_on_both_grains_it_files(seeded: psycopg.Connection) -> None:
    """The lease grain is the population an API-10 prefix cannot see.

    MBOGC files the same production at a well level and a lease level. The lease rows carry a
    lease `entity_key` and no api10 at all, so `left(api10, 2) = '25'` reaches none of them —
    on the real 2026-08-17 archive that is 59,778 of 215,742 rows, 28% of the state, absent
    from a figure labelled Montana. The arms are filtered by source instead.
    """
    well_rows, lease_rows = _seed_montana_production(seeded)

    datasets, _ = _inventory(seeded, datetime(2026, 8, 30, 18, tzinfo=UTC))
    inventory = {dataset.dataset_id: dataset for dataset in datasets}
    well = inventory["canonical.production_monthly/mt-well"]
    lease = inventory["canonical.production_monthly/mt-lease"]

    assert (well.scope, lease.scope) == ("Montana", "Montana")
    assert _metrics(well) == {"rows": well_rows, "wells": len(MT_API10S)}
    assert _metrics(lease) == {"rows": lease_rows, "lease_units": len(MT_LEASE_UNITS)}
    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(*) from canonical.production_monthly where left(api10, 2) = '25'"
        )
        assert cursor.fetchone()[0] == well_rows, "the prefix filter must miss the lease grain"


def test_the_two_montana_grains_are_never_added_into_one_figure(
    seeded: psycopg.Connection,
) -> None:
    """They are the same production reported at two levels, not two populations. One row
    summing them would double the state."""
    _seed_montana_production(seeded)

    datasets, _ = _inventory(seeded, datetime(2026, 8, 30, 18, tzinfo=UTC))
    inventory = {dataset.dataset_id: dataset for dataset in datasets}

    assert "canonical.production_monthly/mt" not in inventory
    assert inventory["canonical.production_monthly/mt-lease"].detail.count("Never summed") == 1
    assert "lease_units" not in _metrics(inventory["canonical.production_monthly/mt-well"])
    assert "wells" not in _metrics(inventory["canonical.production_monthly/mt-lease"])


def test_montana_production_reports_zero_before_its_rows_arrive(
    seeded: psycopg.Connection,
) -> None:
    """The convention the New Mexico arms set: zero, under its own scope, on both grains."""
    datasets, _ = _inventory(seeded, datetime(2026, 8, 30, 18, tzinfo=UTC))
    inventory = {dataset.dataset_id: dataset for dataset in datasets}

    for grain in ("well", "lease"):
        entry = inventory[f"canonical.production_monthly/mt-{grain}"]
        assert [metric.value for metric in entry.metrics] == [0, 0], grain
        assert entry.scope == "Montana"
        assert entry.valid_from is None


def test_montana_wells_are_inventoried_under_montana(seeded: psycopg.Connection) -> None:
    """The `canonical.wells` block already carried three states; Montana is the fourth."""
    datasets, _ = _inventory(seeded, datetime(2026, 8, 30, 18, tzinfo=UTC))
    inventory = {dataset.dataset_id: dataset for dataset in datasets}

    assert inventory["canonical.wells_latest/mt"].scope == "Montana"
    assert inventory["marts.published_map_layers/mt"].scope == "Montana"
    assert {metric.metric_id for metric in inventory["marts.published_map_layers/mt"].metrics} == {
        "mt_wells", "mt_paths"
    }


def test_no_montana_completions_arm_is_claimed_because_no_source_files_them(
    seeded: psycopg.Connection,
) -> None:
    """Checked per block rather than assumed symmetric. `canonical.well_completions` is written
    only by nd_mpr and nm_dims; no Montana ingest touches it, so an arm here would be a figure
    of zero standing in for a measurement nothing takes."""
    datasets, _ = _inventory(seeded, datetime(2026, 8, 30, 18, tzinfo=UTC))
    inventory = {dataset.dataset_id: dataset for dataset in datasets}

    assert "canonical.well_completions/mt" not in inventory
    assert {"canonical.well_completions/nd", "canonical.well_completions/nm"} <= set(inventory)


def test_new_mexico_production_reports_zero_before_its_rows_arrive(
    seeded: psycopg.Connection,
) -> None:
    """The convention `canonical.well_completions/nm` already sets: zero, under its own scope."""
    datasets, _ = _inventory(seeded, datetime(2026, 8, 26, 18, tzinfo=UTC))
    inventory = {dataset.dataset_id: dataset for dataset in datasets}

    nm = inventory["canonical.production_monthly/nm"]
    assert [metric.value for metric in nm.metrics] == [0, 0, 0]
    assert nm.scope == "New Mexico"
    assert nm.valid_from is None
    assert nm.valid_to is None


def _register_production_source(
    connection: psycopg.Connection, *, source_id: str, jurisdiction: str, rule_id: str
) -> None:
    """Everything a state has to add to be inventoried: a source row and a rule row."""
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.sources (source_id, name, jurisdiction)"
            " values (%s, %s, %s)",
            (source_id, f"{jurisdiction} production", jurisdiction),
        )
        cursor.execute(
            "insert into lineage.conformance_rule_publications"
            " (rule_id, published_vintage, evidence_tag, evidence_commit)"
            " values (%s, current_date, 'UNRELEASED', %s)",
            (rule_id, "0" * 40),
        )
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, source_id, stage,"
            " applies_to_fields, rule_kind, spec, rule, rationale, effective_from)"
            " values (%s, %s, %s, 'join', '{source_id}', 'code_ref', %s, 'r', 'r', current_date)",
            (
                rule_id,
                rule_id.rsplit("_", 1)[0],
                source_id,
                Jsonb(
                    {
                        "module_function": (
                            "glasswell.status.collector:_production_inventory"
                        ),
                        "contract_note": "registered for the inventory",
                        "jurisdiction": jurisdiction,
                        "entity_identity_column": "entity_key",
                    }
                ),
            ),
        )


def test_a_new_state_is_inventoried_by_registering_a_rule_not_by_editing_the_collector(
    seeded: psycopg.Connection,
) -> None:
    """The scaling property, asserted directly.

    Every state used to be two more arms in one filtered aggregate over the whole table, so the
    thirtieth state's arms read the other twenty-nine states' rows on every fifteen-minute run.
    A state now registers a row and is counted by a query bounded to its own source.
    """
    with seeded.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id from canonical.production_monthly limit 1"
        )
        manifest_id, derivation_id = cursor.fetchone()
    _register_production_source(
        seeded,
        source_id="ok_occ_production",
        jurisdiction="OK",
        rule_id="cr_ok_inventory_jurisdiction_1",
    )
    with seeded.cursor() as cursor:
        cursor.executemany(
            "insert into canonical.production_monthly (entity_type, entity_key, reporting_level,"
            " api10, production_month, stream, source_id, report_vintage, volume, unit,"
            " granularity, value_hash, source_manifest_id, derivation_id, null_semantics)"
            " values ('well', %(api10)s, 'well', %(api10)s, %(month)s, 'oil',"
            " 'ok_occ_production', date '2026-08-30', 1.0, 'bbl', 'well_observed',"
            " %(value_hash)s, %(manifest)s, %(derivation)s, 'reported')",
            [
                {
                    "api10": api10,
                    "month": date(2026, month, 1),
                    "value_hash": f"ok{index:062d}",
                    "manifest": manifest_id,
                    "derivation": derivation_id,
                }
                for index, (api10, month) in enumerate(
                    (api10, month) for api10 in ("3500100001", "3500100002") for month in (5, 6)
                )
            ],
        )

    datasets, _ = _inventory(seeded, datetime(2026, 8, 30, 18, tzinfo=UTC))
    inventory = {dataset.dataset_id: dataset for dataset in datasets}

    entry = inventory["canonical.production_monthly/ok_occ_production"]
    assert entry.scope == "OK", "an unnamed jurisdiction must read as its own code, not as a guess"
    assert _metrics(entry) == {"rows": 4, "entities": 2, "months": 2}
    assert entry.valid_from == "2026-05-01"
    assert entry.valid_to == "2026-06-01"


def test_the_lease_grain_is_counted_on_the_identity_it_actually_carries(
    seeded: psycopg.Connection,
) -> None:
    """The Montana PRU rows carry a lease entity_key and a null api10.

    Counting distinct api10 over them returns zero while the rows plainly exist, which is the
    failure mode that made an api10-prefix discriminator unusable for this grain in the first
    place. entity_key is the one identity every grain has.
    """
    _seed_montana_production(seeded)

    datasets, _ = _inventory(seeded, datetime(2026, 8, 30, 18, tzinfo=UTC))
    lease = {dataset.dataset_id: dataset for dataset in datasets}[
        "canonical.production_monthly/mt-lease"
    ]
    counted = _metrics(lease)

    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(distinct api10), count(distinct entity_key), count(*)"
            " from canonical.production_monthly where source_id = 'mt_bogc_pru_production'"
        )
        distinct_api10, distinct_entity, rows = cursor.fetchone()

    assert distinct_api10 == 0, "the fixture stopped exercising the null-api10 grain"
    assert counted["lease_units"] == distinct_entity > 0
    assert counted["rows"] == rows
