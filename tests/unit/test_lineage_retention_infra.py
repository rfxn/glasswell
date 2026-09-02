from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / "infra"
SERVICE = INFRA / "systemd" / "glasswell-lineage-retention.service"
TIMER = INFRA / "systemd" / "glasswell-lineage-retention.timer"
VERIFY = INFRA / "verify.sh"


def _setting(path: Path, name: str) -> str:
    prefix = f"{name}="
    values = [
        line.split("=", 1)[1]
        for line in path.read_text().splitlines()
        if line.startswith(prefix)
    ]
    assert len(values) == 1
    return values[0]


def test_retention_service_is_unprivileged_socket_only_and_bounded() -> None:
    assert _setting(SERVICE, "User") == "glasswell"
    assert _setting(SERVICE, "Group") == "glasswell"
    assert _setting(SERVICE, "ExecStart") == (
        "/opt/glasswell/venv/bin/python -m glasswell.lineage.retention"
    )
    assert _setting(SERVICE, "RestrictAddressFamilies") == "AF_UNIX"
    assert _setting(SERVICE, "NoNewPrivileges") == "yes"
    assert _setting(SERVICE, "CapabilityBoundingSet") == ""
    assert _setting(SERVICE, "TimeoutStartSec") == "300"


def test_retention_timer_is_nightly_persistent_and_alerted() -> None:
    assert _setting(TIMER, "OnCalendar") == "*-*-* 03:30:00"
    assert _setting(TIMER, "Persistent") == "true"
    assert _setting(TIMER, "Unit") == "glasswell-lineage-retention.service"
    assert _setting(TIMER, "WantedBy") == "timers.target"
    assert _setting(TIMER, "OnFailure") == "glasswell-alert@%n.service"


def test_retention_is_installed_armed_after_migrations_and_verified() -> None:
    install = (INFRA / "install.sh").read_text()
    deploy = (ROOT / "scripts" / "deploy.sh").read_text()
    verify = (INFRA / "verify.sh").read_text()

    assert "glasswell-lineage-retention.service glasswell-lineage-retention.timer" in install
    assert "systemctl enable glasswell-lineage-retention.timer" in install
    assert "systemctl enable --now glasswell-lineage-retention.timer" not in install
    migration = deploy.index("if (( with_migrations ))")
    timer = deploy.index('remote "systemctl start glasswell-lineage-retention.timer"')
    service = deploy.index('remote "systemctl start glasswell-lineage-retention.service"')
    collect = deploy.index('remote "systemctl start glasswell-status.service"')
    assert migration < timer < service < collect
    for fragment in (
        "systemctl is-enabled glasswell-lineage-retention.timer",
        "systemctl is-active glasswell-lineage-retention.timer",
        "systemctl show glasswell-lineage-retention.service -p Result --value",
    ):
        assert fragment in verify


def _last_run_state(tmp_path: Path, load_state: str, started: str) -> str:
    body = VERIFY.read_text().split("last_run_state() {", 1)[1].split("\n}", 1)[0]
    binaries = tmp_path / "bin"
    binaries.mkdir()
    systemctl = binaries / "systemctl"
    # `Result` is `success` here for every unit, which is exactly what systemd answers for one
    # that is absent or has never run.
    systemctl.write_text(
        "#!/bin/bash\n"
        'case "$4" in\n'
        "  LoadState) printf '%s\\n' \"$STUB_LOAD_STATE\" ;;\n"
        "  ExecMainStartTimestamp) printf '%s\\n' \"$STUB_STARTED\" ;;\n"
        "  Result) printf 'success\\n' ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)

    completed = subprocess.run(
        [
            "/bin/bash",
            "-c",
            f"last_run_state() {{{body}\n}}\nlast_run_state glasswell-lineage-retention.service",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{binaries}:{os.environ['PATH']}",
            "STUB_LOAD_STATE": load_state,
            "STUB_STARTED": started,
        },
    )

    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


@pytest.mark.parametrize(
    ("load_state", "started", "expected"),
    [
        ("not-found", "", "not-found"),
        ("masked", "", "masked"),
        ("loaded", "", "never-ran"),
        ("loaded", "Thu 2026-08-28 03:30:01 UTC", "ran"),
    ],
)
def test_a_sweep_that_is_absent_or_never_ran_is_not_reported_as_a_pass(
    tmp_path: Path, load_state: str, started: str, expected: str
) -> None:
    assert _last_run_state(tmp_path, load_state, started) == expected


def test_verify_asserts_run_evidence_beside_the_retention_result() -> None:
    verify = VERIFY.read_text()

    assert (
        'assert "glasswell-lineage-retention.service has run" ran \\\n'
        '    "$(last_run_state glasswell-lineage-retention.service)"'
    ) in verify


def test_the_job_registry_names_the_retention_job_and_both_its_units() -> None:
    """The collector generates its job list from the registry, so the rows are where the
    retention job is named; six literal calls in the collector became one registry read."""
    registry = (ROOT / "src" / "glasswell" / "seed" / "schedules.py").read_text()

    assert '"platform_lineage_retention"' in registry
    assert '"glasswell-lineage-retention.timer"' in registry
    assert '"glasswell-lineage-retention.service"' in registry
