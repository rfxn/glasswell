"""A ship writes where it got to on the host it is shipping to.

`deploy.sh` drives its remote steps from a workstation, and a workstation dies. Every step
records a transition into `/var/lib/glasswell/runs/deploy-<version>.json` through the same
runner every load uses, and the verdict at the end is read back out of that file rather than
from this shell's own exit. The end-to-end test below runs the real script against a stub `ssh`
that executes the recording commands for real and answers everything else, so the numbers it
asserts are the ones a deploy actually writes.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scripts" / "deploy.sh"
RUNNER = ROOT / "infra" / "bin" / "host-runner.sh"

GIT_STUB = """#!/bin/bash
case "$1" in
    status) exit 0 ;;
    rev-parse) echo abc1234 ;;
    describe) echo v0.83 ;;
    archive) printf '' ;;
    *) exit 0 ;;
esac
"""

# $1 is the host and $2 the command, exactly as deploy.sh calls it. A recording command is run
# for real against the tree's own runner; everything else answers the way the host would.
SSH_STUB = """#!/bin/bash
printf '%s\\n' "$2" >> "$STUB_SSH_LOG"
if [ -n "${STUB_FAIL_PATTERN:-}" ]; then
    case "$2" in
        *"$STUB_FAIL_PATTERN"*) exit 1 ;;
    esac
fi
case "$2" in
    *"tar -x"*) cat >/dev/null; exit 0 ;;
    *host-runner.sh*)
        eval "${2//\\/opt\\/glasswell\\/src\\/infra\\/bin\\/host-runner.sh/$STUB_REAL_RUNNER}"
        exit $?
        ;;
    *schema_migrations*) echo 1; exit 0 ;;
    *) exit 0 ;;
esac
"""


def script() -> str:
    return DEPLOY.read_text(encoding="utf-8")


def declared_steps() -> list[str]:
    # `5b`, `6b2` and `7d` are step numbers too, and the two step 6s are indented inside
    # the branch that chooses between them — a narrower pattern silently counts fewer
    # steps than the script takes.
    return re.findall(r'^\s*step "(\d+[a-z0-9]*)\.', script(), re.MULTILINE)


class TestWhatTheScriptDeclares:
    def test_the_step_count_is_what_one_run_actually_takes(self) -> None:
        # Step 6 is written twice — migrations, or the head comparison — and exactly one of
        # them runs. Every other number appears once, so the positions a run takes is the
        # count of distinct numbers.
        declared = declared_steps()
        assert len(declared) == 24
        assert f"DEPLOY_STEP_COUNT={len(set(declared))}" in script()

    def test_every_step_opens_a_transition_and_a_refusal_closes_one(self) -> None:
        assert re.search(r"^step\(\) \{(.|\n)*?record_state running", script(), re.MULTILINE)
        assert re.search(r"^refuse\(\) \{(.|\n)*?record_state stopped", script(), re.MULTILINE)

    def test_it_records_through_the_copy_it_just_shipped(self) -> None:
        # install.sh has not run yet at step 1, so the installed path does not exist for the
        # first records; the unpacked tree does.
        assert 'HOST_RUNNER="$DEPLOY_SRC/infra/bin/host-runner.sh"' in script()

    def test_the_usage_documents_a_hand_run_mart_refresh_on_the_runner(self) -> None:
        assert "systemd-run" not in script()
        assert "host-runner.sh --job" in script()


@pytest.fixture
def deployment(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """A tree deploy.sh will accept, and the stubs that stand in for the host."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name, body in (("git", GIT_STUB), ("ssh", SSH_STUB)):
        stub = binaries / name
        stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)

    tree = tmp_path / "tree"
    (tree / "scripts").mkdir(parents=True)
    (tree / "scripts" / "deploy.sh").write_text(script(), encoding="utf-8")
    (tree / "scripts" / "deploy.sh").chmod(0o755)
    (tree / "src" / "glasswell" / "db" / "migrations").mkdir(parents=True)
    (tree / "src" / "glasswell" / "db" / "migrations" / "001_init.sql").write_text("", "utf-8")
    (tree / "tests").mkdir()
    (tree / "web" / "dist" / "changelog").mkdir(parents=True)
    (tree / "web" / "dist" / "index.html").write_text("", encoding="utf-8")
    (tree / "web" / "dist" / "changelog" / "index.html").write_text("", encoding="utf-8")
    (tree / "requirements.lock").write_text("glasswell\n", encoding="utf-8")

    environment = {
        **os.environ,
        "PATH": f"{binaries}:{os.environ['PATH']}",
        "STUB_SSH_LOG": str(tmp_path / "ssh.log"),
        "STUB_REAL_RUNNER": str(RUNNER),
        "GLASSWELL_RUNS_DIR": str(tmp_path / "runs"),
        "GLASSWELL_LOG_DIR": str(tmp_path / "logs"),
    }
    return tree, environment


def deploy(tree: Path, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(tree / "scripts" / "deploy.sh")],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def ship(environment: dict[str, str]) -> dict:
    path = Path(environment["GLASSWELL_RUNS_DIR"]) / "deploy-v0.83-abc1234.json"
    return json.loads(path.read_text(encoding="utf-8"))


class TestWhatAShipWrites:
    def test_a_clean_deploy_ends_complete_on_the_host(
        self, deployment: tuple[Path, dict[str, str]]
    ) -> None:
        tree, environment = deployment

        result = deploy(tree, environment)

        assert result.returncode == 0, result.stdout + result.stderr
        status = ship(environment)
        assert status["result"] == "complete"
        assert status["steps_total"] == len(set(declared_steps()))
        assert status["step"].startswith("9. smoke.sh")
        assert status["finished"] is not None

    def test_the_recorded_steps_are_the_ones_that_ran_after_the_tree_landed(
        self, deployment: tuple[Path, dict[str, str]]
    ) -> None:
        tree, environment = deployment

        deploy(tree, environment)

        steps = ship(environment)["steps"]
        # Nothing is recorded before the runner exists on the host, and the tree carrying it
        # lands in the second position.
        assert steps[0]["index"] == 2
        assert steps[0]["step"].startswith("1. the tree at HEAD")
        assert [step["index"] for step in steps] == list(range(2, 24))
        assert all(step["exit"] == 0 for step in steps)

    def test_the_local_side_reads_the_verdict_back_off_the_host(
        self, deployment: tuple[Path, dict[str, str]]
    ) -> None:
        tree, environment = deployment

        result = deploy(tree, environment)

        commands = Path(environment["STUB_SSH_LOG"]).read_text(encoding="utf-8")
        assert "--status deploy-v0.83-abc1234" in commands
        assert "deploy-v0.83-abc1234" in result.stdout

    def test_a_refused_step_is_the_one_the_status_names(
        self, deployment: tuple[Path, dict[str, str]]
    ) -> None:
        tree, environment = deployment

        result = deploy(tree, {**environment, "STUB_FAIL_PATTERN": "infra && ./install.sh"})

        assert result.returncode == 1
        status = ship(environment)
        assert status["result"] == "stopped"
        assert status["step"].startswith("5. config and units")
        assert status["exit"] == 1

    def test_a_failing_gate_stops_the_ship_in_the_file_too(
        self, deployment: tuple[Path, dict[str, str]]
    ) -> None:
        tree, environment = deployment

        result = deploy(tree, {**environment, "STUB_FAIL_PATTERN": "infra/verify.sh"})

        assert result.returncode == 1
        status = ship(environment)
        assert status["result"] == "stopped"
        assert status["exit"] == 1
