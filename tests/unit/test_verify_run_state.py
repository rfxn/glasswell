"""Where the host runner is placed, and the two directories a polled job needs.

`directory_state` is lifted out of the real `verify.sh` and executed, the way
`tests/unit/test_verify_helpers.py` runs the durability helpers — a text assertion would catch
a deleted line and miss a helper that answers wrongly about the mode it is there to police.
The placement assertions read `install.sh` as text, as `tests/unit/test_backup_script.py` does.
"""

from __future__ import annotations

import grp
import os
import pwd
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "infra" / "verify.sh"
INSTALL = ROOT / "infra" / "install.sh"
RUNNER = ROOT / "infra" / "bin" / "host-runner.sh"

RUNS_DIR = "/var/lib/glasswell/runs"
RUN_LOG_DIR = "/var/log/glasswell"


def extract(name: str) -> str:
    text = VERIFY.read_text(encoding="utf-8")
    opening = f"{name}() {{"
    assert opening in text, f"{name} is not defined in verify.sh"
    body = text.split(opening, 1)[1]
    return opening + body.split("\n}\n", 1)[0] + "\n}\n"


def run_helper(tmp_path: Path, command: str) -> str:
    harness = tmp_path / "harness.sh"
    harness.write_text(
        "\n".join(["#!/bin/bash", "set -uo pipefail", extract("directory_state"), command]),
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["/bin/bash", str(harness)], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def whoami() -> str:
    return f"{pwd.getpwuid(os.getuid()).pw_name}:{grp.getgrgid(os.getgid()).gr_name}"


class TestDirectoryState:
    def test_an_absent_directory_says_missing(self, tmp_path: Path) -> None:
        assert run_helper(tmp_path, f'directory_state "{tmp_path / "absent"}"') == "missing"

    def test_it_reports_the_mode_without_its_leading_zero_and_the_ownership(
        self, tmp_path: Path
    ) -> None:
        private = tmp_path / "runs"
        private.mkdir(mode=0o750)
        private.chmod(0o750)

        assert run_helper(tmp_path, f'directory_state "{private}"') == f"750 {whoami()}"

    def test_a_loosened_directory_reports_the_mode_it_actually_has(self, tmp_path: Path) -> None:
        # The assertion compares one string, so a widened mode has to change the answer.
        loose = tmp_path / "runs"
        loose.mkdir()
        loose.chmod(0o777)

        assert run_helper(tmp_path, f'directory_state "{loose}"') == f"777 {whoami()}"

    def test_a_file_where_the_directory_should_be_is_missing(self, tmp_path: Path) -> None:
        impostor = tmp_path / "runs"
        impostor.write_text("not a directory", encoding="utf-8")

        assert run_helper(tmp_path, f'directory_state "{impostor}"') == "missing"


class TestVerifyAssertsThem:
    def test_it_holds_the_runner_equal_to_the_tree(self) -> None:
        text = VERIFY.read_text(encoding="utf-8")

        assert 'cmp -s "$INFRA_DIR/bin/host-runner.sh" "$SBIN_DIR/host-runner.sh"' in text
        assert 'test -x "$SBIN_DIR/host-runner.sh"' in text

    def test_it_pins_both_directories_to_the_modes_install_places(self) -> None:
        text = VERIFY.read_text(encoding="utf-8")

        assert f"RUNS_DIR={RUNS_DIR}" in text
        assert f"RUN_LOG_DIR={RUN_LOG_DIR}" in text
        assert '"750 glasswell:glasswell" "$(directory_state "$RUNS_DIR")"' in text
        assert '"755 glasswell:glasswell" "$(directory_state "$RUN_LOG_DIR")"' in text


class TestInstallPlacesThem:
    def test_the_runner_is_installed_executable(self) -> None:
        text = INSTALL.read_text(encoding="utf-8")

        assert (
            'install -o root -g root -m 0755 "$INFRA_DIR/bin/host-runner.sh" '
            '"$SBIN_DIR/host-runner.sh"' in text
        )

    def test_both_directories_are_created_before_any_job_runs(self) -> None:
        text = INSTALL.read_text(encoding="utf-8")

        assert 'RUNS_DIR="$STATE_DIR/runs"' in text
        assert f"RUN_LOG_DIR={RUN_LOG_DIR}" in text
        assert 'install -d -o "$RUN_USER" -g "$RUN_USER" -m 0750 "$RUNS_DIR"' in text
        assert 'install -d -o "$RUN_USER" -g "$RUN_USER" -m 0755 "$RUN_LOG_DIR"' in text

    def test_the_tree_copy_is_executable_so_the_deploy_can_run_it_before_install(self) -> None:
        # scripts/deploy.sh records its own steps through the copy `git archive` unpacked,
        # which is in place two steps before install.sh runs.
        assert RUNNER.stat().st_mode & 0o111
