from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from glasswell.ingest import tx_gis
from glasswell.lineage.fetch_attempts import failure_code
from glasswell.seed.conformance_c115b import C115B_SOURCES
from glasswell.seed.conformance_land import LAND_SOURCES
from glasswell.seed.conformance_tx import TX_SOURCES
from glasswell.seed.reference import SOURCES

ROOT = Path(__file__).parents[2]
INGEST = ROOT / "src" / "glasswell" / "ingest"
MIGRATIONS = ROOT / "src" / "glasswell" / "db" / "migrations"
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


def declared_poll_policy_ids() -> list[str]:
    """Every cadence row across the whole migration set.

    Migrations are immutable, so a source registered after 050 can only get its policy in a
    later file. Reading one filename made this guard blind to exactly that case, and pinned a
    migration number outside the migrations directory besides.
    """
    ids: list[str] = []
    for migration in sorted(MIGRATIONS.glob("*.sql")):
        # Terminated on a semicolon that ends its line: a cadence string may contain one
        # ("Owner-triggered; no recurring timer") and truncating there loses most of the block.
        for block in re.findall(
            r"insert\s+into\s+lineage\.source_poll_policies(.*?);\s*$",
            migration.read_text(),
            re.IGNORECASE | re.DOTALL | re.MULTILINE,
        ):
            ids.extend(re.findall(r"^\s*\('([^']+)',", block, re.MULTILINE))
    return ids


def test_every_registered_fetchable_source_has_one_cadence_policy() -> None:
    expected = {
        str(source["source_id"])
        for registry in (SOURCES, C115B_SOURCES, LAND_SOURCES, TX_SOURCES)
        for source in registry
    }
    policy_ids = declared_poll_policy_ids()

    assert set(policy_ids) == expected | {"tx_pdq_dsv"}
    assert len(policy_ids) == len(set(policy_ids))


def test_declared_numeric_failure_code_is_made_database_safe() -> None:
    error = RuntimeError("upstream request failed")
    error.glasswell_reason = "503 upstream unavailable"  # type: ignore[attr-defined]

    assert failure_code(error) == "fetch_503_upstream_unavailable"


def test_tx_county_failure_does_not_open_later_county_polls(monkeypatch) -> None:
    entered: list[str] = []
    failed: list[str] = []

    @contextmanager
    def poll(_source_id, source_key, **_kwargs):
        entered.append(source_key)
        try:
            yield
        except RuntimeError:
            failed.append(source_key)
            raise

    class Portal:
        client = object()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def url_for(self, name):
            return f"https://example.invalid/{name}"

    monkeypatch.setattr(tx_gis, "archive_name", lambda _connection, code: f"well{code}.zip")
    monkeypatch.setattr(tx_gis, "source_poll", poll)
    monkeypatch.setattr(tx_gis, "current_session", lambda: SimpleNamespace(correlation_id="run"))
    monkeypatch.setattr(tx_gis, "MftClient", lambda _link: Portal())
    monkeypatch.setattr(
        tx_gis,
        "load_county",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("first county failed")),
    )

    with pytest.raises(RuntimeError, match="first county failed"):
        tx_gis.load_scope(SimpleNamespace(), counties=("001", "003"))

    assert entered == ["well001.zip"]
    assert failed == ["well001.zip"]
