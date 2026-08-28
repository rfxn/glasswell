from __future__ import annotations

from datetime import UTC, datetime

import psycopg
import pytest
from psycopg.types.json import Jsonb

from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.models import InputRef, Operation, OutputSpec, OutputStore, TtlClass
from glasswell.lineage.retention import sweep
from glasswell.lineage.serialization import hash_payload
from glasswell.lineage.store import PostgresRecorder
from tests.support.fakes import FixedClock
from tests.support.seed import FIXTURE_ENV


def _record(
    connection: psycopg.Connection,
    name: str,
    *,
    clock: datetime,
    ttl_class: TtlClass = "ephemeral",
    input_derivation: str | None = None,
    fail: bool = False,
    operation: Operation = "api.respond",
    store: OutputStore = "response",
    dataset: str | None = None,
) -> str:
    inputs = (
        [InputRef(kind="derivation", ref_id=input_derivation)] if input_derivation else []
    )
    with lineage_session(
        recorder=PostgresRecorder(connection),
        environment=FIXTURE_ENV,
        clock=FixedClock(clock),
        correlation_id=f"run_retention_{name}",
    ):
        if fail:
            with pytest.raises(RuntimeError), derive(
                operation,
                output=OutputSpec(store=store, dataset=dataset or f"api.{name}"),
                params={"name": name},
                inputs=inputs,
                ttl_class=ttl_class,
                determinism_class="D3",
            ) as context:
                raise RuntimeError("expected fixture failure")
            return context.derivation_id
        with derive(
            operation,
            output=OutputSpec(store=store, dataset=dataset or f"api.{name}"),
            params={"name": name},
            inputs=inputs,
            ttl_class=ttl_class,
            determinism_class="D3",
        ) as context:
            context.set_output_hash(hash_payload({"col=value": {"value": name}}))
            context.set_rows(1)
        return context.derivation_id


def test_sweep_removes_only_expired_successful_unreferenced_ephemeral_derivations(db) -> None:
    old = datetime(2026, 1, 1, tzinfo=UTC)
    recent = datetime(2026, 8, 27, tzinfo=UTC)
    cutoff = datetime(2026, 5, 30, tzinfo=UTC)

    expired = _record(db, "expired", clock=old)
    permanent = _record(db, "permanent", clock=old, ttl_class="permanent")
    failed = _record(db, "failed", clock=old, fail=True)
    recent_ephemeral = _record(db, "recent", clock=recent)
    referenced = _record(db, "referenced", clock=old)
    served_mart = _record(
        db,
        "served_mart",
        clock=old,
        operation="mart.refresh",
        store="postgis",
        dataset="marts.nd_neighbors",
    )
    db.execute(
        "insert into marts.nd_neighbor_subjects"
        " (api10, formation_status, lateral_component_count, snapshot_vintage, derivation_id)"
        " values ('3305301234', 'pool_unavailable', 1, '2026-01-01', %s)",
        (served_mart,),
    )
    child = _record(
        db,
        "surviving_child",
        clock=recent,
        ttl_class="permanent",
        input_derivation=referenced,
    )
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.response_selector_outputs"
            " (derivation_id, selector, evidence) values (%s, 'col=value', %s)",
            (expired, Jsonb({"value": "expired"})),
        )
        cursor.execute(
            "insert into lineage.derivation_rules (derivation_id, rule_id, applied_rows)"
            " values (%s, 'cr_nd_status_vocab_1', 1)",
            (expired,),
        )
    db.commit()

    assert sweep(db, cutoff=cutoff) == 1
    db.commit()

    remaining = {
        row[0]
        for row in db.execute(
            "select derivation_id from lineage.derivations where derivation_id = any(%s)",
            ([expired, permanent, failed, recent_ephemeral, referenced, child, served_mart],),
        ).fetchall()
    }
    assert expired not in remaining
    assert remaining == {
        permanent,
        failed,
        recent_ephemeral,
        referenced,
        child,
        served_mart,
    }
    assert db.execute(
        "select derivation_id from marts.nd_neighbor_subjects where api10 = '3305301234'"
    ).fetchone()[0] == served_mart
    assert db.execute(
        "select count(*) from lineage.response_selector_outputs where derivation_id = %s",
        (expired,),
    ).fetchone()[0] == 0
    assert db.execute(
        "select count(*) from lineage.derivation_rules where derivation_id = %s", (expired,)
    ).fetchone()[0] == 0


def test_api_role_cannot_invoke_or_mutate_retention_evidence(db) -> None:
    with db.cursor() as cursor:
        cursor.execute("set role glasswell_api")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute("select lineage.sweep_ephemeral_derivations()")
    db.rollback()
