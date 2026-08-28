from __future__ import annotations

import re
from pathlib import Path

from glasswell.lineage.fetch_attempts import failure_code
from glasswell.seed.conformance_c115b import C115B_SOURCES
from glasswell.seed.conformance_land import LAND_SOURCES
from glasswell.seed.conformance_tx import TX_SOURCES
from glasswell.seed.reference import SOURCES

ROOT = Path(__file__).parents[2]
INGEST = ROOT / "src" / "glasswell" / "ingest"
MIGRATION = ROOT / "src" / "glasswell" / "db" / "migrations" / "050_durable_fetch_attempts.sql"
FETCH_COMMANDS = (
    "nd_mpr.py",
    "nd_gis.py",
    "fracfocus.py",
    "tx_wellbore.py",
    "tx_gis.py",
    "nm_ocd.py",
    "blm_plss.py",
    "nm_c115b.py",
)


def test_every_network_fetch_command_opens_the_independent_attempt_ledger() -> None:
    missing = [
        name
        for name in FETCH_COMMANDS
        if "durable_fetch_attempts(arguments.dsn)" not in (INGEST / name).read_text()
    ]

    assert missing == []


def test_nd_month_range_driver_opens_the_independent_attempt_ledger() -> None:
    driver = (ROOT / "infra" / "load-nd-months.py").read_text()

    assert "durable_fetch_attempts(arguments.dsn)" in driver


def test_fetch_registrars_wrap_failures_and_successes_in_source_polls() -> None:
    raw = (ROOT / "src" / "glasswell" / "lineage" / "fetch.py").read_text()
    arcgis = (INGEST / "arcgis.py").read_text()

    assert "with source_poll(source_id, source_key" in raw
    assert "attempt.succeeded(" in raw
    assert "with source_poll(source_id, source_key" in arcgis
    assert "attempt.succeeded(" in arcgis


def test_every_registered_fetchable_source_has_one_cadence_policy() -> None:
    expected = {
        str(source["source_id"])
        for registry in (SOURCES, C115B_SOURCES, LAND_SOURCES, TX_SOURCES)
        for source in registry
    }
    policy_ids = re.findall(r"^\s*\('([^']+)',", MIGRATION.read_text(), re.MULTILINE)

    assert set(policy_ids) == expected | {"tx_pdq_dsv"}
    assert len(policy_ids) == len(set(policy_ids))


def test_declared_numeric_failure_code_is_made_database_safe() -> None:
    error = RuntimeError("upstream request failed")
    error.glasswell_reason = "503 upstream unavailable"  # type: ignore[attr-defined]

    assert failure_code(error) == "fetch_503_upstream_unavailable"
