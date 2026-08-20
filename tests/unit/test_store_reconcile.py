from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glasswell.lineage.errors import DeterminismViolation
from glasswell.lineage.models import DerivationRecord
from glasswell.lineage.store import reconcile


def record(status: str = "ok", output_sha256: str | None = "a" * 64) -> DerivationRecord:
    return DerivationRecord(
        derivation_id="drv_test",
        operation="canonical.promote",
        output_store="parquet",
        output_dataset="canonical.production_monthly",
        output_partition={},
        output_locator="",
        output_sha256=output_sha256,
        output_rows=None,
        output_schema_version="",
        params={},
        params_hash="0" * 64,
        code_version="git:0000test",
        code_dirty=False,
        env_id="env_test",
        model_id=None,
        recipe_id=None,
        created_vintage=None,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
        duration_ms=1,
        correlation_id="run_test",
        status=status,  # pyright: ignore[reportArgumentType]
        determinism_class="D1",
        ttl_class="permanent",
    )


def test_an_unseen_spec_is_inserted():
    assert reconcile(existing_status=None, existing_sha256=None, incoming=record()) == "insert"


def test_a_repeat_of_a_recorded_success_is_a_no_op():
    assert reconcile(
        existing_status="ok", existing_sha256="a" * 64, incoming=record()
    ) == "noop"


def test_a_first_recorded_hash_upgrades_a_hashless_row():
    assert reconcile(existing_status="ok", existing_sha256=None, incoming=record()) == "update"


def test_a_response_store_derivation_without_a_hash_stays_a_no_op():
    assert reconcile(
        existing_status="ok", existing_sha256=None, incoming=record(output_sha256=None)
    ) == "noop"


def test_a_retry_after_failure_upgrades_the_failed_row():
    assert reconcile(existing_status="failed", existing_sha256=None, incoming=record()) == "update"


def test_a_second_failure_of_a_failed_row_changes_nothing():
    assert reconcile(
        existing_status="failed", existing_sha256=None, incoming=record(status="failed")
    ) == "noop"


def test_a_failure_never_overwrites_a_recorded_success():
    assert reconcile(
        existing_status="ok", existing_sha256="a" * 64, incoming=record(status="failed")
    ) == "noop"


def test_a_different_hash_for_the_same_spec_is_a_determinism_violation():
    with pytest.raises(DeterminismViolation) as excinfo:
        reconcile(
            existing_status="ok", existing_sha256="a" * 64, incoming=record(output_sha256="b" * 64)
        )
    assert excinfo.value.derivation_id == "drv_test"
