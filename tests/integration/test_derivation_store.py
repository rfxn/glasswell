from __future__ import annotations

from datetime import date

import psycopg
import pytest

from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.errors import DeterminismViolation
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.store import PostgresRecorder
from tests.support.fakes import FixedClock
from tests.support.seed import FIXTURE_ENV, seed_manifest

OUTPUT = OutputSpec(
    store="parquet",
    dataset="canonical.production_monthly",
    partition={"source_id": "nd_mpr_xlsx", "report_vintage": "2026-08-01",
               "production_month": "2024-03"},
    locator="/data/canonical/nd/2024-03.parquet",
)


@pytest.fixture
def session(db):
    """Factory: each derive() run gets its own single-use session."""

    def make():
        return lineage_session(
            recorder=PostgresRecorder(db),
            environment=FIXTURE_ENV,
            clock=FixedClock(step_ms=7),
            correlation_id="run_integration",
        )

    return make


def fetch_one(db, sql, *parameters):
    with db.cursor() as cursor:
        cursor.execute(sql, parameters)
        return cursor.fetchone()


def test_a_derivation_lands_with_its_input_and_rule_edges(db, session):
    manifest = seed_manifest(db, sha256="1" * 64)
    with session(), derive("canonical.promote", output=OUTPUT, params={"convention": "pm"}) as ctx:
        ctx.add_input(
            InputRef(kind="manifest", ref_id=manifest, as_of_vintage=date(2026, 8, 1))
        )
        ctx.add_rule("cr_month_convention_1", applied_rows=4118203)
        ctx.set_output_hash("a" * 64)
        ctx.set_rows(4118203)
    db.commit()

    row = fetch_one(
        db,
        "select operation, output_dataset, output_rows, created_vintage, status, correlation_id,"
        " code_dirty, determinism_class from lineage.derivations where derivation_id = %s",
        ctx.derivation_id,
    )
    assert row == (
        "canonical.promote",
        "canonical.production_monthly",
        4118203,
        date(2026, 8, 1),
        "ok",
        "run_integration",
        False,
        "D1",
    )
    assert fetch_one(
        db,
        "select kind, ref_id, as_of_vintage, role from lineage.derivation_inputs"
        " where derivation_id = %s",
        ctx.derivation_id,
    ) == ("manifest", manifest, date(2026, 8, 1), "primary")
    assert fetch_one(
        db,
        "select rule_id, applied_rows from lineage.derivation_rules where derivation_id = %s",
        ctx.derivation_id,
    ) == ("cr_month_convention_1", 4118203)


def test_the_partition_is_queryable_as_jsonb(db, session):
    with session(), derive("canonical.promote", output=OUTPUT, params={}):
        pass
    db.commit()

    row = fetch_one(
        db,
        "select count(*) from lineage.derivations"
        " where output_partition @> %s::jsonb",
        '{"production_month": "2024-03"}',
    )
    assert row == (1,)


def test_a_repeat_run_of_the_same_spec_does_not_add_a_row(db, session):
    for _ in range(2):
        with session(), derive("canonical.promote", output=OUTPUT, params={"a": 1}) as ctx:
            ctx.set_output_hash("a" * 64)
        db.commit()

    assert fetch_one(db, "select count(*) from lineage.derivations") == (1,)


def test_the_store_detects_non_determinism_across_runs(db, session):
    with session(), derive("canonical.promote", output=OUTPUT, params={}) as first:
        first.set_output_hash("a" * 64)
    db.commit()

    with pytest.raises(DeterminismViolation) as excinfo, session():
        with derive("canonical.promote", output=OUTPUT, params={}) as second:
            second.set_output_hash("b" * 64)
    db.rollback()

    assert excinfo.value.derivation_id == first.derivation_id
    assert (excinfo.value.recorded_sha256, excinfo.value.observed_sha256) == ("a" * 64, "b" * 64)


def test_a_failed_derivation_is_retained_and_upgraded_by_a_later_success(db, session):
    with session(), pytest.raises(RuntimeError):
        with derive("stage.parse", output=OUTPUT, params={}):
            raise RuntimeError("parser blew up")
    db.commit()

    assert fetch_one(db, "select status from lineage.derivations") == ("failed",)

    with session(), derive("stage.parse", output=OUTPUT, params={}) as retry:
        retry.set_output_hash("c" * 64)
    db.commit()

    assert fetch_one(
        db, "select status, output_sha256 from lineage.derivations"
    ) == ("ok", "c" * 64)
    assert fetch_one(db, "select count(*) from lineage.derivations") == (1,)


def test_nested_transforms_write_a_parent_to_child_edge(db, session):
    manifest = seed_manifest(db, sha256="2" * 64)
    with session():
        with derive("canonical.promote", output=OUTPUT, params={}) as parent:
            with derive(
                "stage.parse",
                output=OutputSpec(store="postgres", dataset="staging.nd_mpr", partition={}),
                params={},
            ) as child:
                child.add_input(
                    InputRef(kind="manifest", ref_id=manifest, as_of_vintage=date(2026, 8, 1))
                )
    db.commit()

    assert fetch_one(
        db,
        "select ref_id, kind from lineage.derivation_inputs where derivation_id = %s",
        parent.derivation_id,
    ) == (child.derivation_id, "derivation")
    assert fetch_one(
        db,
        "select created_vintage from lineage.derivations where derivation_id = %s",
        parent.derivation_id,
    ) == (date(2026, 8, 1),)


def test_the_reverse_rule_index_answers_which_derivations_cited_a_rule(db, session):
    with session():
        with derive("canonical.promote", output=OUTPUT, params={"a": 1}) as first:
            first.add_rule("cr_tx_lease_key_1")
        with derive("canonical.promote", output=OUTPUT, params={"a": 2}) as second:
            second.add_rule("cr_tx_lease_key_1")
    db.commit()

    with db.cursor() as cursor:
        cursor.execute(
            "select derivation_id from lineage.derivation_rules where rule_id = %s order by 1",
            ("cr_tx_lease_key_1",),
        )
        cited = sorted(row[0] for row in cursor.fetchall())
    assert cited == sorted([first.derivation_id, second.derivation_id])


def test_an_unregistered_environment_cannot_produce_a_derivation(db):
    unpinned = FIXTURE_ENV.model_copy(update={"env_id": "env_never_registered"})
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with lineage_session(
            recorder=PostgresRecorder(db), environment=unpinned, clock=FixedClock()
        ), derive("canonical.promote", output=OUTPUT, params={}):
            pass
    db.rollback()
