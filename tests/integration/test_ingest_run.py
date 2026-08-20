from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glasswell.ingest.base import open_ingest_run, resolve_environment
from tests.support.fakes import FixedClock

SOURCE_ID = "nd_mpr_xlsx"


def test_the_run_carries_the_connection_session_as_of_and_raw_zone(db, raw_root, lineage_env):
    with open_ingest_run(db, source_id=SOURCE_ID, environment=lineage_env) as run:
        assert run.connection is db
        assert run.session.environment is lineage_env
        assert run.raw_root == raw_root
        assert run.as_of == run.session.clock.now().date()


def test_as_of_follows_the_injected_clock(db, raw_root, lineage_env):
    clock = FixedClock(start=datetime(2026, 5, 14, 13, 12, tzinfo=UTC))
    with open_ingest_run(db, source_id=SOURCE_ID, environment=lineage_env, clock=clock) as run:
        assert run.as_of.isoformat() == "2026-05-14"


def test_an_unseeded_source_fails_before_any_fetch(db, raw_root, lineage_env):
    with pytest.raises(LookupError, match="nd_gis_spacing_units"):
        with open_ingest_run(db, source_id="nd_gis_spacing_units", environment=lineage_env):
            pass


def test_the_resolved_environment_row_is_written_once_and_reused(db):
    first = resolve_environment(db)
    second = resolve_environment(db)

    assert first == second
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.environments where env_id = %s", (first.env_id,)
        )
        assert cursor.fetchone()[0] == 1
