"""What a launched job is confined by, and which entry points a timer already drives.

The hardening block is asserted against the shipped unit rather than against a copy of it: if
retirement is going to move ten invocations onto transient units, the transient units have to
confine them exactly as the unit they replace did, and a tuple nobody holds to the file drifts
the first time the file changes.
"""

from __future__ import annotations

import os
import re
import subprocess
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


SCHEDULER_UNIT = SYSTEMD / "glasswell-scheduler.service"
SCHEDULER_TIMER = SYSTEMD / "glasswell-scheduler.timer"
STATUS_UNIT = SYSTEMD / "glasswell-status.service"
CF_RANGES_UNIT = SYSTEMD / "glasswell-cf-ranges.service"
INSTALL = ROOT / "infra" / "install.sh"
VERIFY = ROOT / "infra" / "verify.sh"
IDENT_MAP = ROOT / "infra" / "postgres" / "pg_ident.d" / "glasswell.conf"

# `install -o root -g postgres` needs root, and none of that is what these tests are about.
INSTALL_STUB = """#!/bin/bash
dirmode=0
files=()
while (( $# )); do
    case "$1" in
        -d) dirmode=1 ;;
        -o|-g|-m) shift ;;
        -*) ;;
        *) files+=("$1") ;;
    esac
    shift
done
if (( dirmode )); then mkdir -p "${files[@]}"; else cp "${files[0]}" "${files[1]}"; fi
"""


def service_block(text: str) -> list[str]:
    body = text.split("[Service]", 1)[-1].split("[Install]", 1)[0]
    return [line.strip() for line in body.splitlines() if line.strip() and not line.startswith("#")]


def hardening(text: str) -> list[str]:
    keys = ("NoNewPrivileges", "Protect", "Private", "Restrict", "Lock", "Capability",
            "SystemCall", "Proc")
    return [line for line in service_block(text) if line.startswith(keys)]


def test_the_scheduler_unit_carries_the_status_units_hardening_minus_its_state_lines() -> None:
    """N-17: not cf-ranges' block, which grants /etc/glasswell write and omits the caps drop."""
    scheduler = hardening(SCHEDULER_UNIT.read_text())
    status = hardening(STATUS_UNIT.read_text())

    assert scheduler == status
    assert len(scheduler) == 21, scheduler
    assert "CapabilityBoundingSet=" in scheduler
    body = service_block(SCHEDULER_UNIT.read_text())
    assert not any(line.startswith("StateDirectory") for line in body)
    assert not any(line.startswith("ReadWritePaths") for line in body)
    # cf-ranges is the block rev 2 pointed at, and it is the wrong one twice over.
    cf_ranges = hardening(CF_RANGES_UNIT.read_text())
    assert "ReadWritePaths=/etc/glasswell" in service_block(CF_RANGES_UNIT.read_text())
    assert "CapabilityBoundingSet=" not in cf_ranges


def test_the_scheduler_unit_runs_as_root_and_reads_only_its_own_environment_file() -> None:
    body = service_block(SCHEDULER_UNIT.read_text())

    assert "User=root" in body
    assert "EnvironmentFile=/etc/glasswell/scheduler.env" in body
    assert not any(line.startswith("EnvironmentFile=/etc/glasswell/db.env") for line in body)
    assert "TimeoutStartSec=6h" in body
    assert not any("--dsn" in line for line in body)
    assert "OnFailure=glasswell-alert@%n.service" in SCHEDULER_UNIT.read_text()


def test_the_timer_names_its_unit_and_survives_a_missed_tick() -> None:
    timer = SCHEDULER_TIMER.read_text()

    assert "Unit=glasswell-scheduler.service" in timer
    assert "OnCalendar=hourly" in timer
    assert "RandomizedDelaySec=300" in timer
    assert "Persistent=true" in timer


def test_the_ident_map_keeps_every_existing_peer_identity() -> None:
    """A map removes the implicit self-mapping, so the regex line is what stops a lockout."""
    lines = [
        line.split()
        for line in IDENT_MAP.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

    assert ["glasswell", "root", "glasswell_scheduler"] in lines
    assert ["glasswell", "/^(.*)$", r"\1"] in lines
    assert len(lines) == 2


def test_install_places_both_units_generates_scheduler_env_and_ships_no_retired_unit() -> None:
    install = INSTALL.read_text()

    assert "glasswell-scheduler.service glasswell-scheduler.timer" in install
    assert "RETIRED_UNITS=()" in install, "the mechanism ships empty; v0.78 fills it"
    assert "user=glasswell_scheduler" in install
    assert "systemctl reload postgresql" in install
    assert "pg_hba_file_rules where error is not null" in install
    assert "pg_ident_file_mappings where error is not null" in install
    assert "$ETC_DIR/db.env" not in install, "db.env has three readers and is not ours to write"


def test_verify_pins_the_rules_through_the_catalogue_and_the_dropin_by_bytes() -> None:
    """N-23: a text pin proves a rule is written; the catalogue proves it is in force."""
    verify = VERIFY.read_text()

    assert "pg_ident_file_mappings" in verify
    assert "pg_hba_file_rules" in verify
    assert "cmp -s" in verify
    assert "--timer-owned" in verify
    assert "--read-relations" in verify
    assert "no role named root exists" in verify


def extract(text: str, start: str, end: str) -> str:
    assert start in text, f"anchor missing: {start!r}"
    assert end in text, f"anchor missing: {end!r}"
    return start + text.split(start, 1)[1].split(end, 1)[0]


def run_fragment(tmp_path, fragment: str, preamble: str = "") -> subprocess.CompletedProcess:
    stub = tmp_path / "bin"
    stub.mkdir(exist_ok=True)
    (stub / "systemctl").write_text(
        '#!/bin/bash\nprintf "%s\\n" "$*" >> "$SYSTEMCTL_LOG"\nexit 0\n'
    )
    (stub / "systemctl").chmod(0o755)
    # `install` needs root for -o/-g and psql needs a server; neither is what is under test.
    (stub / "install").write_text(INSTALL_STUB)
    (stub / "install").chmod(0o755)
    (stub / "sudo").write_text('#!/bin/bash\nprintf "0\\n"\n')
    (stub / "sudo").chmod(0o755)
    script = tmp_path / "fragment.sh"
    script.write_text(f"set -euo pipefail\n{preamble}\n{fragment}\n")
    return subprocess.run(
        ["/bin/bash", str(script)],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{stub}:{os.environ['PATH']}",
            "SYSTEMCTL_LOG": str(tmp_path / "systemctl.log"),
        },
        check=False,
    )


def test_the_retired_unit_mechanism_disables_and_removes_a_planted_unit(tmp_path) -> None:
    """It ships empty, so this is the only place it is ever exercised before v0.78 fills it."""
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    planted = unit_dir / "glasswell-planted.timer"
    planted.write_text("[Unit]\nDescription=planted\n")
    fragment = extract(INSTALL.read_text(), "RETIRED_UNITS=()", "\ndone\n") + "\ndone\n"
    fragment = fragment.replace(
        "RETIRED_UNITS=()", 'RETIRED_UNITS=(glasswell-planted.timer)', 1
    )

    result = run_fragment(tmp_path, fragment, preamble=f'UNIT_DIR={unit_dir}')

    assert result.returncode == 0, result.stderr
    assert not planted.exists()
    assert "disable --now glasswell-planted.timer" in (tmp_path / "systemctl.log").read_text()
    assert "retired glasswell-planted.timer" in result.stdout
    assert "RETIRED_UNITS=()" in INSTALL.read_text(), "the shipped list stays empty"


HBA_START = 'hba="$PG_ETC_DIR/pg_hba.conf"'
HBA_END = 'install -d -o root -g root -m 0755 "$PG_IDENT_DROPIN_DIR"'


def run_hba_guard(tmp_path, hba_body: str) -> subprocess.CompletedProcess:
    etc = tmp_path / "pg"
    etc.mkdir(exist_ok=True)
    (etc / "pg_hba.conf").write_text(hba_body)
    (etc / "pg_ident.conf").write_text("# MAPNAME SYSTEM-USERNAME PG-USERNAME\n")
    fragment = extract(INSTALL.read_text(), HBA_START, HBA_END)
    return run_fragment(
        tmp_path, fragment, preamble=f'PG_ETC_DIR={etc}\nPG_IDENT_MAP=glasswell'
    )


@pytest.mark.parametrize(
    ("label", "body"),
    [
        ("absent", "local all postgres peer\nhost all all 127.0.0.1/32 scram-sha-256\n"),
        ("duplicated", "local all all peer\nlocal all all peer\n"),
        ("already mapped", "local all all peer map=someone_else\n"),
    ],
)
def test_install_refuses_before_writing_when_the_target_hba_line_is_wrong(
    tmp_path, label, body
) -> None:
    """N-22: refuse before writing. A guess about which rule to edit is a lockout."""
    result = run_hba_guard(tmp_path, body)

    assert result.returncode != 0, f"{label} was accepted: {result.stdout}"
    assert result.stderr.strip(), f"{label} refused without saying why"


def test_install_accepts_the_one_line_it_expects(tmp_path) -> None:
    body = "local all postgres peer\nlocal all all peer\nlocal replication all peer\n"

    result = run_hba_guard(tmp_path, body)

    assert result.returncode == 0, result.stderr


def test_install_accepts_a_line_it_has_already_mapped_itself(tmp_path) -> None:
    """A second install.sh run is a no-op, which is what idempotent has to mean here."""
    result = run_hba_guard(tmp_path, "local all all peer map=glasswell\n")

    assert result.returncode == 0, result.stderr


IDENT_END = "printf 'placed the %s ident map and reloaded postgresql"


def run_ident_placement(tmp_path, hba_body: str, run_twice: bool = False):
    etc = tmp_path / "pg"
    etc.mkdir(exist_ok=True)
    (etc / "pg_hba.conf").write_text(hba_body)
    (etc / "pg_ident.conf").write_text("# MAPNAME SYSTEM-USERNAME PG-USERNAME\n")
    fragment = extract(INSTALL.read_text(), HBA_START, IDENT_END)
    if run_twice:
        fragment = f"{fragment}\n{fragment}"
    result = run_fragment(
        tmp_path,
        fragment,
        preamble=(
            f"PG_ETC_DIR={etc}\n"
            f"PG_IDENT_DROPIN_DIR={etc}/pg_ident.d\n"
            "PG_IDENT_MAP=glasswell\n"
            f"INFRA_DIR={ROOT / 'infra'}"
        ),
    )
    return result, etc


HOST_HBA = (
    "local   all             postgres                                peer\n"
    "local   all             all                                     peer\n"
    "local   replication     all                                     peer\n"
)


def test_the_map_is_placed_once_and_a_second_run_changes_nothing(tmp_path) -> None:
    """The raw sed is not idempotent, so the guard in front of it is what has to be."""
    result, etc = run_ident_placement(tmp_path, HOST_HBA, run_twice=True)

    assert result.returncode == 0, result.stderr
    hba = (etc / "pg_hba.conf").read_text()
    assert hba.count("map=glasswell") == 1, hba
    assert "local   all             postgres                                peer\n" in hba
    assert "local   replication     all                                     peer\n" in hba
    ident = (etc / "pg_ident.conf").read_text()
    assert ident.count("include_if_exists 'pg_ident.d/glasswell.conf'") == 1, ident
    assert (etc / "pg_ident.d" / "glasswell.conf").exists()
    assert "reload postgresql" in (tmp_path / "systemctl.log").read_text()


def test_the_map_leaves_the_other_local_rules_untouched(tmp_path) -> None:
    """A map on the wrong rule is a lockout, and the other two rules are how root and
    replication get in."""
    _result, etc = run_ident_placement(tmp_path, HOST_HBA)
    mapped = [line for line in (etc / "pg_hba.conf").read_text().splitlines() if "map=" in line]

    assert len(mapped) == 1
    assert mapped[0].split()[:4] == ["local", "all", "all", "peer"]


def top_level_lines(text: str) -> set[str]:
    """Lines the script runs on every invocation: column zero, outside every flag branch."""
    return {line.strip() for line in text.splitlines() if line and not line[0].isspace()}


def test_the_ident_map_is_placed_on_every_run_and_not_behind_a_flag() -> None:
    """`deploy.sh` runs `./install.sh` with no arguments, so anything behind `--with-postgres`
    never reaches the host — the same defect the Caddyfile step exists to fix one row above."""
    install = INSTALL.read_text()
    top = top_level_lines(install)

    assert 'install -d -o root -g root -m 0755 "$PG_IDENT_DROPIN_DIR"' in top
    assert "systemctl reload postgresql || {" in top
    assert "systemctl enable glasswell-scheduler.timer" in top
    # The tuning drop-in is one-time provisioning and stays behind the flag.
    assert "if [[ $with_postgres -eq 1 ]]; then" in top
    assert '"$INFRA_DIR/postgres/postgresql.conf.d/glasswell.conf" "$PG_CONF_DIR/glasswell.conf"' \
        not in top
    # Named only in the comment that explains why it does not exist.
    assert "enable_scheduler" not in install, (
        "a flag nothing passes is how the map was lost; the timer arms on every run"
    )


def test_the_deploy_starts_the_scheduler_timer_the_way_it_starts_the_others() -> None:
    deploy = (ROOT / "scripts" / "deploy.sh").read_text()

    assert 'remote "systemctl start glasswell-scheduler.timer"' in deploy
    assert "list-unit-files glasswell-scheduler.timer" not in deploy, (
        "the unit is placed on every run now, so the existence guard is a way to skip silently"
    )


def test_the_add_a_state_runbook_registers_rows_and_does_not_edit_a_unit_file() -> None:
    """It told a new state to add an ExecStart line, which puts its entry point in the
    timer-owned set and makes the double-run guard forbid the launch rows that state wants."""
    runbook = (ROOT / "docs" / "runbook-add-a-state.md").read_text()

    assert "Add an `ExecStart=` line" not in runbook
    assert "runbook-scheduler.md" in runbook
    for shape in ("seed/schedules.py", "conformance_schedules.py",
                  "conformance_rule_publications", "launch_mode"):
        assert shape in runbook, shape


def test_the_two_runbooks_agree_about_where_a_schedule_lives() -> None:
    scheduler = (ROOT / "docs" / "runbook-scheduler.md").read_text()

    assert "it has not been a unit-file edit since v0.78" in scheduler


UNIT_COUNT_PRECONDITION = re.compile(r"grep -c '\^glasswell-'.*expect \d+")


def test_no_runbook_precondition_pins_the_unit_count_as_a_literal() -> None:
    """It read "expect 14" against a tree of 18 — already stale by two before this track and
    by four after it, in two files this track rewrote. An operator running a precondition whose
    whole preamble is about stopping when something disagrees would have stopped."""
    literal = [
        f"{path.name}:{number}"
        for path in sorted((ROOT / "docs").glob("*.md"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if UNIT_COUNT_PRECONDITION.search(line)
    ]

    assert literal == []


def test_the_two_runbooks_compare_the_host_against_the_tree_instead() -> None:
    """Derived, the way verify.sh's own unit loop is: it cannot go stale."""
    for name in ("runbook-nm-promotion.md", "runbook-nm-tier2.md"):
        text = (ROOT / "docs" / name).read_text(encoding="utf-8")
        assert "ls /etc/systemd/system/glasswell-* | wc -l" in text, name
        assert "ls $SRC/infra/systemd/glasswell-* | wc -l" in text, name


INFRA_README = ROOT / "infra" / "README.md"


def test_the_host_readme_documents_what_install_now_always_does() -> None:
    """It is the host's unit inventory and its `/etc` inventory, and after the flag fix
    `install.sh` unconditionally edits two PostgreSQL config files, places a drop-in, reloads
    the server, writes an env file, places two units and arms an hourly timer. None of that
    was in it."""
    readme = INFRA_README.read_text(encoding="utf-8")

    for shape in (
        "glasswell-scheduler.service",
        "glasswell-scheduler.timer",
        "/etc/glasswell/scheduler.env",
        "pg_ident.d/glasswell.conf",
        "glasswell_scheduler",
        "map=glasswell",
    ):
        assert shape in readme, shape


def test_the_readme_usage_block_no_longer_says_the_flag_is_what_places_the_map() -> None:
    usage = INFRA_README.read_text(encoding="utf-8").split("## Usage", 1)[1][:900]

    assert "--enable-scheduler" not in usage
    assert "scheduler" in usage.lower()
