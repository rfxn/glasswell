"""What a launched job is confined by, and which entry points a timer already drives.

The hardening block is asserted against the shipped unit rather than against a copy of it: if
retirement is going to move ten invocations onto transient units, the transient units have to
confine them exactly as the unit they replace did, and a tuple nobody holds to the file drifts
the first time the file changes.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from glasswell.scheduler.runner import TICK_BUDGET_SECONDS
from glasswell.scheduler.units import (
    TRANSIENT_HARDENING,
    hardening_directives,
    render_transient_argv,
    timer_owned_entry_points,
    transient_unit_name,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SYSTEMD = ROOT / "infra" / "systemd"
INGEST_UNIT = SYSTEMD / "glasswell-ingest.service"
MIGRATIONS = ROOT / "src" / "glasswell" / "db" / "migrations"
RUN_ID = "jrn_01JQ8ZK4T7MFAB2CDEFGHJKMNP"


def console_scripts() -> dict[str, str]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["scripts"]


def rendered() -> tuple[str, ...]:
    return render_transient_argv(
        job_id="ingest_nd_gis",
        run_id=RUN_ID,
        entry_point="glasswell.ingest.nd_gis",
        argv=("--layer", "all"),
        run_as="glasswell",
        memory_max="6G",
        timeout_seconds=3600,
    )


def test_the_rendered_argv_carries_every_hardening_directive_the_retired_unit_carries() -> None:
    shipped = hardening_directives(INGEST_UNIT.read_text())

    assert len(shipped) == 14, shipped
    assert shipped == TRANSIENT_HARDENING
    argv = rendered()
    for directive in shipped:
        assert f"--property={directive}" in argv


def test_the_rendered_argv_never_carries_a_dsn_on_the_command_line() -> None:
    argv = rendered()

    assert not any(token.startswith("--dsn") for token in argv)
    assert "--dsn" not in argv
    assert any("Environment=GLASSWELL_DSN=postgresql:///glasswell" in token for token in argv)
    assert not any("password" in token for token in argv)


def test_the_rendered_argv_drops_to_the_registry_uid_and_carries_its_ceilings() -> None:
    argv = rendered()

    assert "--property=User=glasswell" in argv
    assert "--property=Group=glasswell" in argv
    assert "--property=MemoryMax=6G" in argv
    assert "--property=TimeoutStartSec=3600" in argv
    assert argv[-5:] == (
        "/opt/glasswell/venv/bin/python",
        "-m",
        "glasswell.ingest.nd_gis",
        "--layer",
        "all",
    )


def test_the_transient_unit_name_is_derived_from_the_run_it_records() -> None:
    unit = transient_unit_name("ingest_nd_gis", RUN_ID)

    assert unit == "gw-job-ingest_nd_gis-fghjkmnp"
    assert unit.endswith(RUN_ID[-8:].lower())


def test_the_job_timeout_ceiling_equals_the_ticks_own_budget() -> None:
    """No single job may outlive its parent, so the CHECK and the budget are one number."""
    migration = next(MIGRATIONS.glob("*_job_schedule_registry.sql")).read_text()
    ceiling = re.search(r"timeout_seconds\s+integer check \(timeout_seconds between 60 and (\d+)\)",
                        migration)

    assert ceiling is not None, "the timeout ceiling is no longer where this test looks"
    assert int(ceiling.group(1)) == TICK_BUDGET_SECONDS


def test_the_timer_owned_set_resolves_the_one_console_script_line() -> None:
    """glasswell-ingest.service:36 names a script, not a module, and it is marts.neighbors."""
    owned = timer_owned_entry_points([INGEST_UNIT.read_text()], console_scripts())

    assert "glasswell.marts.neighbors" in owned
    assert len(owned) == 10, sorted(owned)


def test_the_timer_owned_set_reads_a_module_inside_a_quoted_bash_argument() -> None:
    """NIT-13: the nd_mpr line wraps its command in /bin/bash -c, so tokenising returns -c."""
    owned = timer_owned_entry_points([INGEST_UNIT.read_text()], console_scripts())

    assert "glasswell.ingest.nd_mpr" in owned


def test_a_script_alias_is_matched_by_its_venv_path_and_never_by_basename() -> None:
    """A basename match would let one script name collide with another entry's suffix."""
    scripts = {"glasswell-tiles": "glasswell.marts.tiles:main",
               "co-tiles": "glasswell.marts.co_tiles:main"}
    unit = "[Service]\nExecStart=/opt/glasswell/venv/bin/glasswell-tiles --quiet\n"

    assert timer_owned_entry_points([unit], scripts) == frozenset({"glasswell.marts.tiles"})


def test_a_service_with_no_timer_is_not_in_the_set_the_caller_builds() -> None:
    """NIT-14: the construction is timer -> Unit= -> that service, not every glasswell-*.service."""
    timer = (SYSTEMD / "glasswell-ingest.timer").read_text()
    named = re.search(r"^Unit=(.+)$", timer, re.MULTILINE)

    assert named is not None, "the ingest timer no longer names its unit explicitly"
    assert named.group(1).strip() == "glasswell-ingest.service"
    assert not (SYSTEMD / "glasswell-api.timer").exists()
    assert not (SYSTEMD / "glasswell-alert@.timer").exists()
