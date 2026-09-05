"""Every runbook's long step runs under the tracked host runner, and says what to poll.

A fenced `systemd-run` in a runbook is a job that lives in an ssh session: the session drops,
the unit keeps running, and nothing on the host records how far it got. `--wait` belongs inside
`infra/bin/host-runner.sh` and nowhere else, so the rule here is mechanical — no fenced block in
any runbook may call systemd-run — and every runbook with a long step has to name the runner and
say what to poll.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest

from tests.unit.test_host_runner import JOURNALCTL_STUB, SYSTEMCTL_STUB, SYSTEMD_RUN_STUB

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
RUNNER_PATH = "/usr/local/sbin/host-runner.sh"
RUNNER = ROOT / "infra" / "bin" / "host-runner.sh"

RUNBOOKS = sorted(path.name for path in DOCS.glob("runbook-*.md"))
LONG_STEP_RUNBOOKS = [
    "runbook-basin-load.md",
    "runbook-co-tier2.md",
    "runbook-mt-load.md",
    "runbook-nm-promotion.md",
    "runbook-nm-tier2.md",
    "runbook-scheduler.md",
    "runbook-tx-load.md",
]

# A job name is what host-runner.sh accepts as one; the surrounding ssh quoting is not
# part of it.
JOB = re.compile(r"--job\s+([A-Za-z0-9._-]+)")
STATUS = re.compile(r"--status\s+([A-Za-z0-9._-]+)")
RESUME_JOB = re.compile(r"--job\s+([A-Za-z0-9._-]+)\s+--resume")


def stub_environment(binaries: Path, runs: Path) -> dict[str, str]:
    """The unit tier's stubs, so a documented line is parsed by the runner and run by nothing."""
    binaries.mkdir(parents=True, exist_ok=True)
    journal = binaries.parent / f"{binaries.name}-journal"
    journal.mkdir(exist_ok=True)
    for stub_name, body in (
        ("systemd-run", SYSTEMD_RUN_STUB),
        ("systemctl", SYSTEMCTL_STUB),
        ("journalctl", JOURNALCTL_STUB),
    ):
        stub = binaries / stub_name
        stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)
    return {
        **os.environ,
        "PATH": f"{binaries}:{os.environ['PATH']}",
        "GLASSWELL_RUNS_DIR": str(runs),
        "GLASSWELL_LOG_DIR": str(runs.parent / f"{runs.name}-logs"),
        "STUB_RUN_LOG": str(journal / "systemd-run.log"),
        "STUB_JOURNAL_DIR": str(journal),
        "STUB_SYSTEMCTL_LOG": str(journal / "systemctl.log"),
    }


def fenced(name: str) -> str:
    """Only the fenced blocks of a runbook: prose may still discuss systemd, and does."""
    inside = False
    kept: list[str] = []
    for line in (DOCS / name).read_text(encoding="utf-8").splitlines():
        # A fence indented under a list item is still a fence, and the runner form for a
        # resume is written inside one.
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if inside:
            kept.append(line)
    return "\n".join(kept)


def test_the_long_step_runbooks_are_all_of_them_but_the_meta_one() -> None:
    # A new runbook is covered by the rules below the moment it is written, rather than when
    # somebody remembers to add it to this list.
    assert set(RUNBOOKS) - set(LONG_STEP_RUNBOOKS) == {"runbook-add-a-state.md"}


@pytest.mark.parametrize("name", RUNBOOKS)
def test_no_fenced_block_calls_systemd_run(name: str) -> None:
    offenders = [line for line in fenced(name).splitlines() if "systemd-run" in line]

    assert offenders == [], f"{name} runs a job in the operator's session: {offenders}"


@pytest.mark.parametrize("name", RUNBOOKS)
def test_no_fenced_block_waits_on_a_unit_by_hand(name: str) -> None:
    # `systemctl is-active` in a loop is the ssh --wait shape wearing a different hat; the
    # runner follows another job through its status file.
    offenders = [
        line
        for line in fenced(name).splitlines()
        if "is-active" in line and ("while" in line or "until" in line)
    ]

    assert offenders == [], f"{name} polls a unit rather than a status file: {offenders}"


@pytest.mark.parametrize("name", LONG_STEP_RUNBOOKS)
def test_the_long_steps_run_under_the_installed_runner(name: str) -> None:
    blocks = fenced(name)

    assert RUNNER_PATH in blocks, f"{name} has no step running under the host runner"
    assert JOB.search(blocks), f"{name} launches the runner without naming a job"
    assert "host-runner.sh" not in blocks.replace(RUNNER_PATH, ""), (
        f"{name} calls the runner by a path other than the installed one"
    )


@pytest.mark.parametrize("name", LONG_STEP_RUNBOOKS)
def test_each_one_says_to_poll_the_status_file(name: str) -> None:
    text = (DOCS / name).read_text(encoding="utf-8").lower()

    assert "poll the status file" in text, f"{name} never says what to poll"


@pytest.mark.parametrize("name", LONG_STEP_RUNBOOKS)
def test_every_polled_job_is_one_the_runbook_launches(name: str) -> None:
    blocks = fenced(name)
    launched = set(JOB.findall(blocks))
    polled = set(STATUS.findall(blocks))

    assert polled, f"{name} launches a job and never polls it"
    assert polled <= launched, f"{name} polls a job it does not launch: {polled - launched}"


def test_the_texas_resume_is_documented_against_the_job_it_resumes() -> None:
    blocks = fenced("runbook-tx-load.md")
    resumed = set(RESUME_JOB.findall(blocks))

    assert resumed, "the Texas promotion never shows how to resume a stopped batch"
    assert resumed <= set(JOB.findall(blocks))


def test_the_texas_promotion_sizes_its_batches_by_rows() -> None:
    text = (DOCS / "runbook-tx-load.md").read_text(encoding="utf-8")

    # Measured 2026-09-05: 2011-2016 was OOM-killed at MemoryMax=6G after batches of 5.23 M,
    # 5.72 M and 6.72 M rows landed under the same ceiling.
    assert "oom-kill" in text.lower()
    assert "5.23" in text
    assert "6.72" in text
    assert re.search(r"MemoryMax|--memory", text)


class TestTheDocumentedInvocationsParse:
    """A runbook command the runner cannot parse is a step nobody can run.

    Each fenced invocation is executed against the same stub systemd-run the unit tier uses, so
    the assertion is the runner's own parse of the line as written, not a second reading of it.
    """

    @staticmethod
    def invocations(name: str) -> list[list[str]]:
        joined = re.sub(r"\\\n\s*", " ", fenced(name))
        found: list[list[str]] = []
        for line in joined.splitlines():
            if "host-runner.sh" not in line or "--job" not in line:
                continue
            tokens = shlex.split(line.strip(), comments=True)
            while tokens and "host-runner.sh" not in tokens[0]:
                tokens.pop(0)
            if tokens and " " in tokens[0]:  # the ssh form arrives as one quoted token
                tokens = shlex.split(tokens[0])
            found.append([token for token in tokens[1:] if token != "--detach"])
        return found

    @pytest.mark.parametrize("name", LONG_STEP_RUNBOOKS)
    def test_every_fenced_invocation_parses_into_steps(self, name: str, tmp_path: Path) -> None:
        invocations = self.invocations(name)
        assert invocations, f"{name} has no runner invocation to parse"

        for position, arguments in enumerate(invocations):
            runs = tmp_path / f"runs-{position}"
            environment = stub_environment(tmp_path / f"stubs-{position}", runs)
            job = arguments[arguments.index("--job") + 1]
            if "--resume" in arguments:
                # Nothing to resume until something has stopped, and the refusal comes first.
                subprocess.run(
                    [str(RUNNER), "--record", "--job", job, "--step", "prior", "--step-index",
                     "1", "--steps-total", "1", "--result", "stopped", "--exit", "137"],
                    env=environment, check=True, capture_output=True,
                )
            completed = subprocess.run(
                [str(RUNNER), *arguments], env=environment, capture_output=True, text=True
            )

            assert completed.returncode != 2, (
                f"{name}: the runner refused this line as unparseable — "
                f"{' '.join(arguments)}\n{completed.stderr}"
            )
            status = json.loads((runs / f"{job}.json").read_text(encoding="utf-8"))
            assert status["steps_total"] >= 1
            assert status["job"] == job
