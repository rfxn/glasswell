"""F30, F31: the docker branch of the hygiene sweep, driven with a stubbed daemon.

`orphan_volumes` folded stderr into the value it asserts on, so any daemon warning became a
"volume" and `make check-workstation` exited 1 naming it. `CONTAINER_MAX_HOURS` was read and
printed but never used: the threshold was baked into the regex, and the unparenthesised
alternation matched a container whose *name* contained `days`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "workstation-hygiene.sh"

pytestmark = pytest.mark.unit

_DOCKER_STUB = """#!/bin/bash
case "$1" in
  info) exit 0 ;;
  volume)
    printf '%s' "${STUB_DOCKER_STDERR:-}" >&2
    printf '%s' "${STUB_VOLUMES:-}"
    exit 0 ;;
  ps) printf '%s' "${STUB_CONTAINERS:-}"; exit 0 ;;
esac
exit 0
"""

# Everything else the sweep shells out to; a workstation's real state is not under test here.
_QUIET = ("systemctl", "crontab", "ss", "pgrep", "find", "du", "xargs")


@pytest.fixture
def sweep(tmp_path: Path):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker"
    docker.write_text(_DOCKER_STUB, encoding="utf-8")
    docker.chmod(0o755)
    for name in _QUIET:
        stub = binaries / name
        stub.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)

    def run(**stub_environment: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["/bin/bash", str(SCRIPT)],
            capture_output=True,
            text=True,
            env={**os.environ, "PATH": f"{binaries}:{os.environ['PATH']}", **stub_environment},
            check=False,
        )

    return run


def test_a_clean_workstation_passes(sweep):
    """The floor: a sweep that failed on everything would satisfy the assertions below."""
    completed = sweep()

    assert completed.returncode == 0, completed.stdout
    assert "  FAIL " not in completed.stdout


def test_a_daemon_warning_is_not_reported_as_an_orphan_volume(sweep):
    completed = sweep(STUB_DOCKER_STDERR="WARNING: bridge-nf-call-iptables is disabled\n")

    assert completed.returncode == 0, completed.stdout
    assert "bridge-nf" not in completed.stdout


def test_a_real_orphan_volume_still_fails(sweep):
    completed = sweep(STUB_VOLUMES="gw_test_abc123\n")

    assert completed.returncode == 1
    assert "no labelled test volume outlived its session" in completed.stdout
    assert "gw_test_abc123" in completed.stdout


@pytest.mark.parametrize("age", ["3 hours", "2 days", "5 weeks"])
def test_a_container_past_the_configured_age_is_flagged(sweep, age):
    completed = sweep(STUB_CONTAINERS=f"gw-test-1 {age} ago\n", CONTAINER_MAX_HOURS="2")

    assert completed.returncode == 1
    assert "no test container outlived a suite run" in completed.stdout


def test_the_threshold_is_the_configured_one_and_not_a_baked_in_two(sweep):
    """`CONTAINER_MAX_HOURS=8` still fired at 2 hours and reported "older than 8h" — a message
    contradicting the condition that produced it."""
    completed = sweep(STUB_CONTAINERS="gw-test-1 3 hours ago\n", CONTAINER_MAX_HOURS="8")

    assert completed.returncode == 0, completed.stdout


def test_a_container_named_after_a_time_unit_is_not_a_stale_container(sweep):
    """The alternation was unparenthesised, so `days|weeks|months` matched the whole line."""
    completed = sweep(STUB_CONTAINERS="gw-test-days-of-thunder 4 minutes ago\n")

    assert completed.returncode == 0, completed.stdout


def test_a_young_container_passes(sweep):
    completed = sweep(STUB_CONTAINERS="gw-test-1 About a minute ago\n")

    assert completed.returncode == 0, completed.stdout
