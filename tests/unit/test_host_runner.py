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
import time
from dataclasses import dataclass
from itertools import pairwise
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
    "judged_by",
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
[ -n "${STUB_LAUNCH_ONLY:-}" ] && exit 0
if [ -n "${STUB_SNAPSHOT_DIR:-}" ] && [ -f "${STUB_STATUS_FILE:-}" ]; then
    cp "$STUB_STATUS_FILE" "$STUB_SNAPSHOT_DIR/$unit.json"
    stat -c %i "$STUB_STATUS_FILE" >> "$STUB_SNAPSHOT_DIR/inodes"
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

# `journalctl -u X` answers with the payload's output *and* systemd's own messages about the
# unit; `journalctl _SYSTEMD_UNIT=X.service` answers with the payload's alone. The stub models
# both, because a stub that emitted only the payload would make the runner's summary look
# right while the real journal put "Deactivated successfully." where the step's figures are.
JOURNALCTL_STUB = r"""#!/bin/bash
unit=""
payload_only=0
previous=""
for argument in "$@"; do
    case "$argument" in
        _SYSTEMD_UNIT=*)
            unit="${argument#_SYSTEMD_UNIT=}"
            unit="${unit%.service}"
            payload_only=1
            ;;
    esac
    [ "$previous" = -u ] && unit="$argument"
    previous="$argument"
done
[ -f "$STUB_JOURNAL_DIR/$unit.log" ] && cat "$STUB_JOURNAL_DIR/$unit.log"
if [ "$payload_only" = 0 ] && [ -f "$STUB_JOURNAL_DIR/$unit.rc" ]; then
    rc=$(cat "$STUB_JOURNAL_DIR/$unit.rc")
    if [ "$rc" = 0 ]; then
        printf '%s.service: Deactivated successfully.\n' "$unit"
    else
        printf '%s.service: Main process exited, code=exited, status=%s/n/a\n' "$unit" "$rc"
        printf "%s.service: Failed with result 'exit-code'.\n" "$unit"
    fi
fi
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
        assert steps[0]["judged_by"] == "summary"
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

    def test_systemd_own_verdict_is_not_the_step_s_summary(self, harness: Harness) -> None:
        # Measured against real systemd 2026-09-05: `journalctl -u <unit> -o cat` ends with
        # "<unit>.service: Deactivated successfully.", which is what the summary reported.
        harness.run(
            "--job", "verdict", "--", "load", "--expect", "staged ",
            "/bin/echo", "staged 5230000 rows",
        )

        status = harness.status("verdict")
        assert status["steps"][0]["summary"] == "staged 5230000 rows"
        # The log keeps systemd's own lines: they are the operator's evidence, not the step's.
        assert "Deactivated successfully" in harness.log("verdict")

    def test_a_failures_last_payload_line_survives_systemd_talking_over_it(
        self, harness: Harness
    ) -> None:
        harness.run(
            "--job", "drift", "--", "load", "/bin/sh", "-c",
            "echo 'cr_tx_pdq_format_2: the header carries FOO'; exit 4",
        )

        status = harness.status("drift")
        assert status["steps"][0]["summary"] == "cr_tx_pdq_format_2: the header carries FOO"
        assert "Failed with result" in harness.log("drift")

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
            '{"promoted": 1}',
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
            '{"ran": true}',
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


class TestAStepIsJudgedByWhatItWrote:
    """The 2026-09-05 20:00Z incident: `systemctl stop` of a running promotion answered
    `Result=success` and exit 0 to `systemd-run --wait`, and the ad-hoc runner ran the next
    step over a promotion that had not happened."""

    def test_a_step_that_exits_zero_without_its_summary_is_not_done(
        self, harness: Harness
    ) -> None:
        result = harness.run(
            "--job", "stopped-by-hand", "--",
            "promote", "/bin/true",
            "--", "marts", "/bin/echo", '{"rebuilt": 1}',
        )

        assert result.returncode == 1
        status = harness.status("stopped-by-hand")
        assert status["result"] == "stopped"
        assert status["step"] == "promote"
        assert status["steps"][0]["exit"] == 0
        assert status["steps"][0]["systemd_result"] == "success"
        assert status["steps"][0]["judged_by"] == "summary"
        assert not any("stopped-by-hand-2-marts" in line for line in harness.launches())

    def test_keep_going_does_not_carry_on_past_a_step_that_left_no_evidence(
        self, harness: Harness
    ) -> None:
        result = harness.run(
            "--job", "silent", "--keep-going", "--",
            "promote", "/bin/true",
            "--", "marts", "/bin/echo", '{"rebuilt": 1}',
        )

        assert result.returncode == 1
        assert len(harness.status("silent")["steps"]) == 1

    def test_keep_going_still_carries_on_past_a_step_that_failed_and_said_so(
        self, harness: Harness
    ) -> None:
        # An exit status that is not zero has already answered; --keep-going is about that.
        result = harness.run(
            "--job", "loud", "--keep-going", "--",
            "one", "/bin/sh", "-c", "echo broke; exit 3",
            "--", "two", "/bin/echo", '{"ran": 1}',
        )

        assert result.returncode == 3
        status = harness.status("loud")
        assert len(status["steps"]) == 2
        assert status["steps"][0]["judged_by"] == "exit"

    def test_a_killed_step_stops_the_chain_even_under_keep_going(
        self, harness: Harness
    ) -> None:
        result = harness.run(
            "--job", "culled", "--keep-going", "--",
            "one", "/bin/sh", "-c", "exit 137",
            "--", "two", "/bin/echo", '{"ran": 1}',
            STUB_FORCE_RESULT="oom-kill",
        )

        assert result.returncode == 137
        assert len(harness.status("culled")["steps"]) == 1

    def test_expect_names_the_evidence_a_step_that_prints_no_json_writes(
        self, harness: Harness
    ) -> None:
        # glasswell-mt-bogc prints one plain line per grain after it commits, and no JSON.
        result = harness.run(
            "--job", "montana", "--",
            "production", "--expect", ": staged ",
            "/bin/echo", "MT_HistoricalWellProduction.tab: staged 5809608, months 488",
        )

        assert result.returncode == 0, result.stderr
        status = harness.status("montana")
        assert status["result"] == "complete"
        assert status["steps"][0]["judged_by"] == "summary"

    def test_the_summary_is_the_evidence_line_when_the_step_named_one(
        self, harness: Harness
    ) -> None:
        # systemd's own "Deactivated successfully." follows the step's output in the journal,
        # and on a step with no JSON to prefer it would otherwise be the last word.
        harness.run(
            "--job", "montana", "--",
            "production", "--expect", ": staged ",
            "/bin/sh", "-c",
            "echo 'MT_HistoricalWellProduction.tab: staged 5809608';"
            " echo 'MT_HistoricalPRUProduction.tab: staged 1603216'; echo done",
        )

        summary = harness.status("montana")["steps"][0]["summary"]
        assert summary == "MT_HistoricalPRUProduction.tab: staged 1603216"

    def test_a_step_whose_expected_line_never_came_is_not_done(self, harness: Harness) -> None:
        result = harness.run(
            "--job", "montana", "--",
            "production", "--expect", ": staged ",
            "/bin/echo", "MT_HistoricalWellProduction.tab: opened",
        )

        assert result.returncode == 1
        assert harness.status("montana")["result"] == "stopped"

    def test_judge_by_exit_is_allowed_and_recorded_as_the_weakening_it_is(
        self, harness: Harness
    ) -> None:
        result = harness.run(
            "--job", "quiet", "--", "housekeeping", "--judge-by-exit", "/bin/true"
        )

        assert result.returncode == 0, result.stderr
        status = harness.status("quiet")
        assert status["result"] == "complete"
        assert status["steps"][0]["judged_by"] == "exit"

    def test_a_json_array_counts_as_a_document(self, harness: Harness) -> None:
        # glasswell-scheduler --run prints one JSON array of plan entries.
        result = harness.run(
            "--job", "planned", "--", "run", "/bin/echo", '[{"job_id": "ingest_nd_gis"}]'
        )

        assert result.returncode == 0, result.stderr


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


class TestTheStatusFileIsReplacedNotRewritten:
    """The file is written to `.tmp` and renamed over, so a poller never reads half a document.

    A rename gives the name a new inode every time; a direct write truncates the one a reader
    may have open. Consecutive transitions are compared rather than all of them, because the
    inode a rename frees is free for the transition after next to be given.
    """

    def observed_inodes(self, harness: Harness, job: str) -> list[str]:
        harness.run(
            *two_steps(job),
            STUB_SNAPSHOT_DIR=str(harness.snapshots),
            STUB_STATUS_FILE=str(harness.runs / f"{job}.json"),
        )
        seen = (harness.snapshots / "inodes").read_text(encoding="utf-8").split()
        return [*seen, str((harness.runs / f"{job}.json").stat().st_ino)]

    def test_no_transition_lands_on_the_document_the_last_one_published(
        self, harness: Harness
    ) -> None:
        observed = self.observed_inodes(harness, "atomic")

        # One per step launch, plus the completed document.
        assert len(observed) == 3
        assert all(before != after for before, after in pairwise(observed)), (
            f"the file a poller has open was rewritten under it: {observed}"
        )

    def test_nothing_half_written_is_left_beside_the_status_file(self, harness: Harness) -> None:
        harness.run(*two_steps("tidy"))

        assert sorted(path.name for path in harness.runs.iterdir()) == [
            "tidy.json",
            "tidy.stamps",
            "tidy.steps",
        ]


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


class TestResume:
    def test_it_continues_a_stopped_job_where_it_stopped(self, harness: Harness) -> None:
        harness.run(
            "--job", "tx-step3", "--",
            "batch-a", "/bin/echo", '{"rows": 5230000}',
            "--", "batch-b", "/bin/sh", "-c", "echo Killed; exit 137",
            "--", "batch-c", "/bin/echo", "never",
        )
        stopped = harness.status("tx-step3")

        resumed = harness.run(
            "--job", "tx-step3", "--resume", "--",
            "batch-b1", "/bin/echo", '{"appended": 2600000}',
            "--", "batch-b2", "/bin/echo", '{"appended": 2610000}',
        )

        assert resumed.returncode == 0, resumed.stderr
        status = harness.status("tx-step3")
        assert status["result"] == "complete"
        assert status["started"] == stopped["started"]
        assert [step["index"] for step in status["steps"]] == [1, 2, 3, 4]
        # The OOM-killed batch keeps its own record: the history is the job's, not the run's.
        assert status["steps"][1]["step"] == "batch-b"
        assert status["steps"][1]["exit"] == 137
        assert status["steps"][2]["step"] == "batch-b1"
        assert status["steps"][2]["unit"] == "tx-step3-3-batch-b1"
        assert status["steps_total"] == 4
        assert status["step_index"] == 4

    def test_the_log_and_the_stamps_are_appended_not_replaced(self, harness: Harness) -> None:
        harness.run("--job", "tx-step3", "--", "batch-a", "/bin/sh", "-c", "echo first; exit 9")

        harness.run(
            "--job", "tx-step3", "--resume", "--", "batch-b", "/bin/echo", '{"second": 1}'
        )

        log = harness.log("tx-step3")
        assert "first" in log
        assert "second" in log
        stamps = harness.status("tx-step3")["stamps"]
        assert any("batch-a start" in stamp for stamp in stamps)
        assert any("resumed" in stamp for stamp in stamps)

    def test_a_complete_job_has_nothing_to_resume(self, harness: Harness) -> None:
        harness.run(*two_steps())

        resumed = harness.run("--job", "demo", "--resume", "--", "again", "/bin/echo", "hi")

        assert resumed.returncode == 3
        assert "complete" in resumed.stderr

    def test_a_job_that_never_ran_has_nothing_to_resume(self, harness: Harness) -> None:
        resumed = harness.run("--job", "ghost", "--resume", "--", "one", "/bin/echo", "hi")

        assert resumed.returncode == 3
        assert "ghost" in resumed.stderr


class TestAfterJob:
    def test_it_runs_once_the_job_it_follows_has_completed(self, harness: Harness) -> None:
        harness.run("--job", "first", "--", "one", "/bin/echo", '{"done": 1}')

        second = harness.run(
            "--job", "second", "--after-job", "first", "--", "two", "/bin/echo", '{"ran": 1}'
        )

        assert second.returncode == 0, second.stderr
        assert harness.status("second")["result"] == "complete"

    def test_it_refuses_to_start_behind_a_job_that_stopped(self, harness: Harness) -> None:
        harness.run("--job", "first", "--", "one", "/bin/sh", "-c", "exit 7")

        second = harness.run(
            "--job", "second", "--after-job", "first", "--", "two", "/bin/echo", "never"
        )

        assert second.returncode == 1
        status = harness.status("second")
        assert status["result"] == "stopped"
        assert "first" in status["step"]
        assert status["steps"] == []
        assert not any("second-1-two" in line for line in harness.launches())

    def test_a_job_that_never_ran_cannot_be_followed(self, harness: Harness) -> None:
        second = harness.run(
            "--job", "second", "--after-job", "ghost", "--", "two", "/bin/echo", "never"
        )

        assert second.returncode == 2

    def test_while_it_waits_the_status_says_so(self, harness: Harness) -> None:
        harness.run("--record", "--job", "first", "--steps-total", "1", "--step", "one",
                    "--step-index", "1", "--result", "running")

        waiting = subprocess.Popen(
            [str(RUNNER), "--job", "second", "--after-job", "first", "--",
             "two", "/bin/echo", '{"ran": 1}'],
            env={**harness.env, "GLASSWELL_WAIT_INTERVAL": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            observed = None
            for _ in range(100):
                path = harness.runs / "second.json"
                if path.exists():
                    observed = json.loads(path.read_text(encoding="utf-8"))
                    if observed["result"] == "waiting":
                        break
                time.sleep(0.1)
            assert observed is not None, "the waiting job never wrote a status file"
            assert observed["result"] == "waiting", observed
            assert observed["step_index"] == 0
            assert observed["unit"] == "first"

            harness.run("--record", "--job", "first", "--steps-total", "1", "--step", "one",
                        "--step-index", "1", "--result", "complete")
            assert waiting.wait(timeout=30) == 0
        finally:
            if waiting.poll() is None:
                waiting.kill()

        assert harness.status("second")["result"] == "complete"


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
            'stage --memory 4G /bin/echo {"staged":1}\n'
            'promote /bin/echo {"promoted":1}\n',
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


class TestAKilledRunnerLeavesAReadableFile:
    def test_a_record_torn_by_a_kill_is_dropped_rather_than_assembled(
        self, harness: Harness
    ) -> None:
        harness.run("--job", "torn", "--", "one", "/bin/echo", "first")
        sidecar = harness.runs / "torn.steps"
        sidecar.write_text(
            sidecar.read_text(encoding="utf-8") + '{"index":2,"step":"half"', encoding="utf-8"
        )

        harness.run(
            "--record", "--job", "torn", "--steps-total", "3", "--step", "three",
            "--step-index", "3", "--result", "running",
        )

        status = harness.status("torn")
        assert [step["index"] for step in status["steps"]] == [1, 3]

    def test_a_step_record_is_one_append(self) -> None:
        # Two appends is a window in which a kill leaves a line nothing can parse.
        body = RUNNER.read_text(encoding="utf-8").split("record_step() {", 1)[1].split("\n}", 1)[0]

        assert body.count('>> "$steps_record"') == 1


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
        result = harness.run(
            "--job", "backgrounded", "--detach", "--", "load", "/bin/echo", '{"ok": 1}'
        )

        assert result.returncode == 0, result.stderr
        assert "--status backgrounded" in result.stdout
        launched = harness.launches()
        assert any("--unit=backgrounded-runner" in line for line in launched)
        assert not any("--detach" in line for line in launched)

    def test_the_detached_run_is_handed_the_configuration_this_one_resolved(
        self, harness: Harness
    ) -> None:
        # systemd starts the unit with PID 1's environment, so a detached job would otherwise
        # write its status somewhere other than where the launching command was told it does.
        harness.run("--job", "carried", "--detach", "--", "load", "/bin/echo", '{"ok": 1}')

        launch = harness.argv("carried-runner")
        assert f"--setenv=GLASSWELL_RUNS_DIR={harness.runs}" in launch
        assert f"--setenv=GLASSWELL_LOG_DIR={harness.logs}" in launch
        assert any(a.startswith("--setenv=GLASSWELL_DSN=") for a in launch)
        assert any(a.startswith("--setenv=GLASSWELL_RAW_ROOT=") for a in launch)

    def test_it_waits_for_the_status_file_before_handing_back_the_poll_command(
        self, harness: Harness
    ) -> None:
        # A unit that starts and writes nothing: the poll command still comes back, and the
        # operator is told there is nothing under it yet rather than reading a stale answer.
        result = harness.run(
            "--job", "silent", "--detach", "--", "load", "/bin/echo", "hi",
            STUB_LAUNCH_ONLY="1",
        )

        assert result.returncode == 0
        assert "--status silent" in result.stdout
        assert "nothing has been written" in result.stderr

    def test_a_failed_runner_unit_is_cleared_before_the_next_launch(
        self, harness: Harness
    ) -> None:
        # A resume reuses the job name, and a corpse under that name would refuse it.
        harness.run(
            "--job", "backgrounded", "--detach", "--", "load", "/bin/echo", '{"ok": 1}'
        )

        systemctl = (harness.root / "systemctl.log").read_text(encoding="utf-8")
        assert "reset-failed backgrounded-runner" in systemctl
