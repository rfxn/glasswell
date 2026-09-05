"""`infra/bin/host-runner.sh`: the chain it runs, the status grammar, and the refusals.

There is no systemd in the test container, so `systemd-run`, `systemctl` and `journalctl` are
stubs on PATH. The `systemd-run` stub *executes* the step's command, so the exit codes, the
journal text and therefore the status file are the real ones rather than a second copy of the
assertion. `tests/unit/test_backup_script.py` runs the backup script the same way.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "infra" / "bin" / "host-runner.sh"

STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

STATUS_KEYS = {
    "job",
    "started",
    "updated",
    "step",
    "step_index",
    "steps_total",
    "unit",
    "exit",
    "result",
    "finished",
    "log",
    "steps",
    "stamps",
}
STEP_KEYS = {
    "index",
    "step",
    "unit",
    "started",
    "ended",
    "exit",
    "systemd_result",
    "memory_peak",
    "summary",
}

SYSTEMD_RUN_STUB = r"""#!/bin/bash
unit=""
command_argv=()
for argument in "$@"; do
    case "$argument" in
        --unit=*) unit="${argument#--unit=}" ;;
        --wait|--collect|--quiet|--pipe) ;;
        --property=*|--setenv=*|--description=*|--uid=*) ;;
        *) command_argv+=("$argument") ;;
    esac
done
printf '%s\n' "$*" >> "$STUB_RUN_LOG"
printf '%s\n' "$@" > "$STUB_JOURNAL_DIR/$unit.argv"
if [ -n "${STUB_SNAPSHOT_DIR:-}" ] && [ -f "${STUB_STATUS_FILE:-}" ]; then
    cp "$STUB_STATUS_FILE" "$STUB_SNAPSHOT_DIR/$unit.json"
fi
"${command_argv[@]}" > "$STUB_JOURNAL_DIR/$unit.log" 2>&1
rc=$?
printf '%s\n' "$rc" > "$STUB_JOURNAL_DIR/$unit.rc"
exit "$rc"
"""

SYSTEMCTL_STUB = r"""#!/bin/bash
printf '%s\n' "$*" >> "$STUB_SYSTEMCTL_LOG"
if [ "$1" = show ]; then
    unit="$2"
    property="$4"
    rc=0
    [ -f "$STUB_JOURNAL_DIR/$unit.rc" ] && rc=$(cat "$STUB_JOURNAL_DIR/$unit.rc")
    case "$property" in
        Result)
            if [ -n "${STUB_FORCE_RESULT:-}" ]; then echo "$STUB_FORCE_RESULT"
            elif [ "$rc" = 0 ]; then echo success
            else echo exit-code; fi ;;
        ExecMainStatus) echo "$rc" ;;
        MemoryPeak) echo "${STUB_MEMORY_PEAK:-1048576}" ;;
        LoadState) echo not-found ;;
        *) echo ;;
    esac
fi
exit 0
"""

JOURNALCTL_STUB = r"""#!/bin/bash
unit=""
previous=""
for argument in "$@"; do
    [ "$previous" = -u ] && unit="$argument"
    previous="$argument"
done
[ -f "$STUB_JOURNAL_DIR/$unit.log" ] && cat "$STUB_JOURNAL_DIR/$unit.log"
exit 0
"""


@dataclass
class Harness:
    root: Path
    runs: Path
    logs: Path
    journal: Path
    snapshots: Path
    run_log: Path
    env: dict[str, str]

    def run(self, *arguments: str, **overrides: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(RUNNER), *arguments],
            capture_output=True,
            text=True,
            check=False,
            env={**self.env, **overrides},
        )

    def status(self, job: str) -> dict:
        return json.loads((self.runs / f"{job}.json").read_text(encoding="utf-8"))

    def snapshot(self, unit: str) -> dict:
        return json.loads((self.snapshots / f"{unit}.json").read_text(encoding="utf-8"))

    def launches(self) -> list[str]:
        if not self.run_log.exists():
            return []
        return self.run_log.read_text(encoding="utf-8").splitlines()

    def argv(self, unit: str) -> list[str]:
        return (self.journal / f"{unit}.argv").read_text(encoding="utf-8").splitlines()

    def log(self, job: str) -> str:
        return (self.logs / f"{job}.log").read_text(encoding="utf-8")


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name, body in (
        ("systemd-run", SYSTEMD_RUN_STUB),
        ("systemctl", SYSTEMCTL_STUB),
        ("journalctl", JOURNALCTL_STUB),
    ):
        stub = binaries / name
        stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)

    journal = tmp_path / "journal"
    journal.mkdir()
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    # runs/ and logs/ are deliberately absent: creating them is the runner's job.
    return Harness(
        root=tmp_path,
        runs=tmp_path / "runs",
        logs=tmp_path / "logs",
        journal=journal,
        snapshots=snapshots,
        run_log=tmp_path / "systemd-run.log",
        env={
            **os.environ,
            "PATH": f"{binaries}:{os.environ['PATH']}",
            "GLASSWELL_RUNS_DIR": str(tmp_path / "runs"),
            "GLASSWELL_LOG_DIR": str(tmp_path / "logs"),
            "STUB_RUN_LOG": str(tmp_path / "systemd-run.log"),
            "STUB_JOURNAL_DIR": str(journal),
            "STUB_SYSTEMCTL_LOG": str(tmp_path / "systemctl.log"),
        },
    )


def two_steps(job: str = "demo") -> tuple[str, ...]:
    return (
        "--job",
        job,
        "--",
        "stage",
        "/bin/echo",
        '{"staged_rows": 12}',
        "--",
        "promote",
        "/bin/echo",
        '{"appended": 3}',
    )


class TestStatusGrammar:
    def test_a_completed_chain_fills_every_field(self, harness: Harness) -> None:
        result = harness.run(*two_steps())

        assert result.returncode == 0, result.stderr
        status = harness.status("demo")
        assert set(status) == STATUS_KEYS
        assert status["job"] == "demo"
        assert status["result"] == "complete"
        assert status["step"] == "promote"
        assert status["step_index"] == 2
        assert status["steps_total"] == 2
        assert status["unit"] == "demo-2-promote"
        assert status["exit"] == 0
        assert status["log"] == str(harness.logs / "demo.log")
        assert all(STAMP.match(status[field]) for field in ("started", "updated", "finished"))

    def test_every_step_carries_its_own_record(self, harness: Harness) -> None:
        harness.run(*two_steps())

        steps = harness.status("demo")["steps"]
        assert [step["index"] for step in steps] == [1, 2]
        assert set(steps[0]) == STEP_KEYS
        assert steps[0]["step"] == "stage"
        assert steps[0]["unit"] == "demo-1-stage"
        assert steps[0]["exit"] == 0
        assert steps[0]["systemd_result"] == "success"
        assert steps[0]["summary"] == '{"staged_rows": 12}'
        assert steps[1]["summary"] == '{"appended": 3}'
        assert all(STAMP.match(step["started"]) for step in steps)
        assert all(STAMP.match(step["ended"]) for step in steps)

    def test_stamps_record_the_start_and_the_end_of_each_step(self, harness: Harness) -> None:
        harness.run(*two_steps())

        stamps = harness.status("demo")["stamps"]
        assert len(stamps) == 4
        assert stamps[0].endswith("stage start")
        assert "stage end rc=0" in stamps[1]
        assert stamps[2].endswith("promote start")

    def test_the_job_log_holds_the_whole_journal(self, harness: Harness) -> None:
        harness.run(*two_steps())

        assert '{"staged_rows": 12}' in harness.log("demo")

    def test_it_creates_its_state_and_log_directories(self, harness: Harness) -> None:
        harness.run(*two_steps())

        assert harness.runs.is_dir()
        assert harness.logs.is_dir()
        assert oct(harness.runs.stat().st_mode)[-3:] == "750"


class TestSummaryIsNeverTruncated:
    def test_a_long_machine_readable_line_survives_whole(self, harness: Harness) -> None:
        # The first host instance cut this at 600 characters, which made the figures it
        # reported unparseable by `json.loads` (the lesson REG-HR was written from).
        payload = json.dumps({"rows": "x" * 2000})

        harness.run("--job", "wide", "--", "load", "/bin/echo", payload)

        summary = harness.status("wide")["steps"][0]["summary"]
        assert summary == payload
        assert json.loads(summary)["rows"] == "x" * 2000

    def test_the_runner_never_cuts_a_line(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")

        assert not re.search(r"\bcut\b", source), "a machine-readable line must not be cut"

    def test_the_last_json_line_wins_over_chatter_around_it(self, harness: Harness) -> None:
        harness.run(
            "--job",
            "chatty",
            "--",
            "load",
            "/bin/sh",
            "-c",
            'echo notice; echo \'{"appended": 7}\'; echo trailing',
        )

        assert harness.status("chatty")["steps"][0]["summary"] == '{"appended": 7}'


class TestTheChainStops:
    def test_a_failing_step_stops_the_chain_and_the_status_names_it(
        self, harness: Harness
    ) -> None:
        result = harness.run(
            "--job",
            "halt",
            "--",
            "first",
            "/bin/echo",
            "ok",
            "--",
            "second",
            "/bin/sh",
            "-c",
            "echo broke; exit 4",
            "--",
            "third",
            "/bin/echo",
            "never",
        )

        assert result.returncode == 4
        status = harness.status("halt")
        assert status["result"] == "stopped"
        assert status["step"] == "second"
        assert status["step_index"] == 2
        assert status["exit"] == 4
        assert STAMP.match(status["finished"])
        assert [step["index"] for step in status["steps"]] == [1, 2]
        assert status["steps"][1]["systemd_result"] == "exit-code"
        assert status["steps"][1]["summary"] == "broke"
        assert "halt-3-third" not in " ".join(harness.launches())

    def test_keep_going_runs_the_rest_and_still_refuses_to_call_it_complete(
        self, harness: Harness
    ) -> None:
        result = harness.run(
            "--job",
            "onward",
            "--keep-going",
            "--",
            "first",
            "/bin/sh",
            "-c",
            "exit 3",
            "--",
            "second",
            "/bin/echo",
            "ran anyway",
        )

        assert result.returncode == 3
        status = harness.status("onward")
        assert status["result"] == "stopped"
        assert status["step"] == "first"
        assert status["exit"] == 3
        assert len(status["steps"]) == 2
        assert status["steps"][1]["exit"] == 0

    def test_a_unit_that_exited_zero_without_succeeding_still_stops_the_chain(
        self, harness: Harness
    ) -> None:
        # `--wait` reports the process status; the unit's own verdict is a second reading, and
        # an OOM kill or a runtime cap is where the two disagree.
        result = harness.run(
            "--job",
            "oom",
            "--",
            "first",
            "/bin/echo",
            "looked fine",
            "--",
            "second",
            "/bin/echo",
            "never",
            STUB_FORCE_RESULT="oom-kill",
        )

        assert result.returncode == 1
        status = harness.status("oom")
        assert status["result"] == "stopped"
        assert status["step"] == "first"
        assert status["steps"][0]["systemd_result"] == "oom-kill"
        assert "oom-2-second" not in " ".join(harness.launches())

    def test_stop_on_fail_is_the_named_default(self, harness: Harness) -> None:
        explicit = harness.run(
            "--job",
            "explicit",
            "--stop-on-fail",
            "--",
            "first",
            "/bin/sh",
            "-c",
            "exit 5",
            "--",
            "second",
            "/bin/echo",
            "never",
        )

        assert explicit.returncode == 5
        assert len(harness.status("explicit")["steps"]) == 1


class TestWrittenAfterEveryTransition:
    def test_the_status_seen_from_inside_step_two_is_already_current(
        self, harness: Harness
    ) -> None:
        harness.run(
            *two_steps("watch"),
            STUB_SNAPSHOT_DIR=str(harness.snapshots),
            STUB_STATUS_FILE=str(harness.runs / "watch.json"),
        )

        mid = harness.snapshot("watch-2-promote")
        assert mid["result"] == "running"
        assert mid["step"] == "promote"
        assert mid["step_index"] == 2
        assert mid["exit"] is None
        assert mid["finished"] is None
        # Step 1 is already closed with its own summary: a poller reads finished work as
        # finished, not at the end of the job.
        assert mid["steps"][0]["exit"] == 0
        assert mid["steps"][0]["summary"] == '{"staged_rows": 12}'
        assert mid["steps"][1]["ended"] is None

    def test_the_first_snapshot_shows_the_job_starting(self, harness: Harness) -> None:
        harness.run(
            *two_steps("watch"),
            STUB_SNAPSHOT_DIR=str(harness.snapshots),
            STUB_STATUS_FILE=str(harness.runs / "watch.json"),
        )

        first = harness.snapshot("watch-1-stage")
        assert first["result"] == "running"
        assert first["step_index"] == 1
        assert first["steps_total"] == 2


class TestRefusals:
    def test_a_finished_job_refuses_to_run_again(self, harness: Harness) -> None:
        harness.run(*two_steps())
        before = (harness.runs / "demo.json").read_text(encoding="utf-8")

        again = harness.run(*two_steps())

        assert again.returncode == 3
        assert "demo" in again.stderr
        assert "--force" in again.stderr
        assert (harness.runs / "demo.json").read_text(encoding="utf-8") == before

    def test_force_runs_a_finished_job_again(self, harness: Harness) -> None:
        harness.run(*two_steps())

        again = harness.run("--force", *two_steps())

        assert again.returncode == 0, again.stderr
        assert harness.status("demo")["result"] == "complete"

    def test_a_run_still_in_flight_refuses_a_second_launch(self, harness: Harness) -> None:
        harness.run("--record", "--job", "busy", "--step", "load", "--step-index", "1",
                    "--steps-total", "2", "--result", "running")

        second = harness.run("--job", "busy", "--", "load", "/bin/echo", "hello")

        assert second.returncode == 3
        assert "in progress" in second.stderr

    def test_a_stopped_job_refuses_too(self, harness: Harness) -> None:
        harness.run("--job", "broke", "--", "one", "/bin/sh", "-c", "exit 2")

        again = harness.run("--job", "broke", "--", "one", "/bin/sh", "-c", "exit 2")

        assert again.returncode == 3

    def test_a_job_name_that_is_a_path_is_refused(self, harness: Harness) -> None:
        result = harness.run("--job", "../escape", "--", "one", "/bin/echo", "hi")

        assert result.returncode == 2
        assert not (harness.root / "escape.json").exists()

    def test_a_step_name_that_is_a_path_is_refused(self, harness: Harness) -> None:
        result = harness.run("--job", "fine", "--", "../escape", "/bin/echo", "hi")

        assert result.returncode == 2

    def test_a_step_without_a_command_is_refused(self, harness: Harness) -> None:
        result = harness.run("--job", "fine", "--", "lonely")

        assert result.returncode == 2
        assert "command" in result.stderr

    def test_no_job_is_refused(self, harness: Harness) -> None:
        assert harness.run("--", "one", "/bin/echo", "hi").returncode == 2


class TestStatusFlag:
    def test_it_prints_the_json_for_a_job(self, harness: Harness) -> None:
        harness.run(*two_steps())

        printed = harness.run("--status", "demo")

        assert printed.returncode == 0
        assert json.loads(printed.stdout)["result"] == "complete"

    def test_an_unknown_job_says_so(self, harness: Harness) -> None:
        printed = harness.run("--status", "never-ran")

        assert printed.returncode == 1
        assert "never-ran" in printed.stderr


class TestWhatReachesSystemd:
    def test_the_defaults_are_the_hosts(self, harness: Harness) -> None:
        harness.run("--job", "props", "--", "load", "/opt/glasswell/venv/bin/true", "--flag")

        argv = harness.argv("props-1-load")
        assert "--unit=props-1-load" in argv
        assert "--wait" in argv
        assert "--property=User=glasswell" in argv
        assert "--property=Group=glasswell" in argv
        assert "--property=EnvironmentFile=-/etc/glasswell/code-version.env" in argv
        assert "--property=MemoryMax=6G" in argv
        assert "--property=RuntimeMaxSec=3600" in argv
        assert "--property=TimeoutStartSec=3600" in argv
        assert any(a.startswith("--property=Environment=GLASSWELL_DSN=") for a in argv)
        assert any(a.startswith("--property=Environment=GLASSWELL_RAW_ROOT=") for a in argv)
        assert argv[-2:] == ["/opt/glasswell/venv/bin/true", "--flag"]

    def test_a_step_overrides_the_budget_and_the_user(self, harness: Harness) -> None:
        harness.run(
            "--job",
            "props",
            "--memory",
            "6G",
            "--",
            "tiles",
            "--user",
            "postgres",
            "--group",
            "postgres",
            "--memory",
            "2G",
            "--timeout",
            "1800",
            "--unit",
            "p1-tiles",
            "--setenv",
            "GLASSWELL_STAGING_ROOT=/data/staging",
            "/bin/echo",
            "done",
        )

        argv = harness.argv("p1-tiles")
        assert "--property=User=postgres" in argv
        assert "--property=Group=postgres" in argv
        assert "--property=MemoryMax=2G" in argv
        assert "--property=RuntimeMaxSec=1800" in argv
        assert "--setenv=GLASSWELL_STAGING_ROOT=/data/staging" in argv
        assert harness.status("props")["steps"][0]["unit"] == "p1-tiles"

    def test_a_failed_unit_is_reset_before_it_is_launched_again(self, harness: Harness) -> None:
        harness.run("--job", "reset", "--", "one", "/bin/echo", "hi")

        systemctl = (harness.root / "systemctl.log").read_text(encoding="utf-8")
        assert "reset-failed reset-1-one" in systemctl


class TestStepsFile:
    def test_a_file_drives_the_same_chain(self, harness: Harness) -> None:
        steps = harness.root / "steps.txt"
        steps.write_text(
            "# the two halves\n"
            "\n"
            "stage --memory 4G /bin/echo staged\n"
            "promote /bin/echo promoted\n",
            encoding="utf-8",
        )

        result = harness.run("--job", "filed", "--steps-file", str(steps))

        assert result.returncode == 0, result.stderr
        status = harness.status("filed")
        assert status["steps_total"] == 2
        assert [step["step"] for step in status["steps"]] == ["stage", "promote"]
        assert "--property=MemoryMax=4G" in harness.argv("filed-1-stage")

    def test_a_missing_file_is_refused(self, harness: Harness) -> None:
        result = harness.run("--job", "filed", "--steps-file", str(harness.root / "absent"))

        assert result.returncode == 2


class TestTheJsonStaysJson:
    def test_quotes_and_backslashes_in_a_summary_are_escaped(self, harness: Harness) -> None:
        harness.run(
            "--job",
            "quoted",
            "--",
            "load",
            "/bin/sh",
            "-c",
            r"""printf '%s\n' 'said "hi" \ then \t tabbed'""",
        )

        summary = harness.status("quoted")["steps"][0]["summary"]
        assert 'said "hi"' in summary

    def test_a_summary_that_impersonates_the_status_is_not_read_as_it(
        self, harness: Harness
    ) -> None:
        # The refusal reads the previous run's own `result` and `finished` out of the file. A
        # step that prints a JSON object of its own writes those same key names into it, and
        # must not be able to answer for the job.
        harness.run(
            "--job",
            "liar",
            "--",
            "load",
            "/bin/sh",
            "-c",
            """echo '{"result":"running","finished":null,"step":"invented"}'; exit 1""",
        )
        status = harness.status("liar")
        assert status["result"] == "stopped"
        assert status["step"] == "load"

        again = harness.run("--job", "liar", "--", "load", "/bin/echo", "hi")

        assert again.returncode == 3
        assert "already finished (stopped)" in again.stderr
        assert "in progress" not in again.stderr

    def test_control_bytes_do_not_break_the_document(self, harness: Harness) -> None:
        harness.run(
            "--job",
            "binary",
            "--",
            "load",
            "/bin/sh",
            "-c",
            r"""printf 'rows \033[31mred\033[0m done\n'""",
        )

        status = harness.status("binary")
        assert "red" in status["steps"][0]["summary"]
        assert "\x1b" not in status["steps"][0]["summary"]


class TestRecordMode:
    def test_records_assemble_into_the_same_grammar(self, harness: Harness) -> None:
        common = ("--record", "--job", "deploy-v0.83", "--steps-total", "2")
        harness.run(*common, "--step", "tree", "--step-index", "1", "--result", "running")
        harness.run(*common, "--step", "units", "--step-index", "2", "--result", "running")
        harness.run(*common, "--step", "units", "--step-index", "2", "--result", "complete")

        status = harness.status("deploy-v0.83")
        assert set(status) == STATUS_KEYS
        assert status["result"] == "complete"
        assert status["steps_total"] == 2
        assert [step["step"] for step in status["steps"]] == ["tree", "units"]
        # Opening step 2 closed step 1: a linear chain that refuses on failure has no other
        # reading of "the next step started".
        assert status["steps"][0]["exit"] == 0
        assert STAMP.match(status["steps"][0]["ended"])

    def test_the_start_time_survives_every_later_record(self, harness: Harness) -> None:
        harness.run("--record", "--job", "deploy-v0.83", "--steps-total", "2", "--step",
                    "tree", "--step-index", "1", "--result", "running")
        started = harness.status("deploy-v0.83")["started"]

        harness.run("--record", "--job", "deploy-v0.83", "--steps-total", "2", "--step",
                    "tree", "--step-index", "1", "--result", "step-ok")

        assert harness.status("deploy-v0.83")["started"] == started

    def test_a_stopped_record_carries_the_exit_and_the_step(self, harness: Harness) -> None:
        harness.run("--record", "--job", "shipwreck", "--steps-total", "9", "--step",
                    "migrations", "--step-index", "6", "--result", "running")
        harness.run("--record", "--job", "shipwreck", "--steps-total", "9", "--step",
                    "migrations", "--step-index", "6", "--result", "stopped", "--exit", "1",
                    "--summary", "migrations failed")

        status = harness.status("shipwreck")
        assert status["result"] == "stopped"
        assert status["exit"] == 1
        assert status["step"] == "migrations"
        assert status["steps"][0]["summary"] == "migrations failed"
        assert STAMP.match(status["finished"])

    def test_an_unknown_result_word_is_refused(self, harness: Harness) -> None:
        result = harness.run("--record", "--job", "x", "--steps-total", "1", "--step", "a",
                             "--step-index", "1", "--result", "fine")

        assert result.returncode == 2

    def test_a_record_does_not_trip_the_finished_job_refusal(self, harness: Harness) -> None:
        # deploy.sh records into the same job name across a retry; the refusal guards the
        # chain runner, not the recorder.
        harness.run("--record", "--job", "again", "--steps-total", "1", "--step", "a",
                    "--step-index", "1", "--result", "complete")

        second = harness.run("--record", "--job", "again", "--steps-total", "1", "--step", "a",
                             "--step-index", "1", "--result", "running")

        assert second.returncode == 0


class TestDetach:
    def test_it_hands_the_job_to_a_transient_unit_and_prints_the_poll_command(
        self, harness: Harness
    ) -> None:
        result = harness.run("--job", "backgrounded", "--detach", "--", "load", "/bin/echo", "hi")

        assert result.returncode == 0, result.stderr
        assert "--status backgrounded" in result.stdout
        launched = harness.launches()
        assert any("--unit=backgrounded-runner" in line for line in launched)
        assert not any("--detach" in line for line in launched)
