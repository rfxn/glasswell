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
INSTALL = ROOT / "infra" / "install.sh"
DEPLOY_README = ROOT / "infra" / "README.md"

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


ADHOC_RUNNERS = (
    "co-load-runner.sh",
    "tx-step3-runner.sh",
    "tx-step3-resume-runner.sh",
    "tx-step3-resume2-runner.sh",
    "tx-step45-runner.sh",
)


# `systemctl list-units` names the active services and `systemctl show -p ExecStart --value`
# says what each one runs. The stub answers both from one mapping, because the question the
# retirement asks — is a unit running this script right now — is answered by the pair.
SYSTEMCTL_UNITS_STUB = """#!/bin/bash
if [ "$1" = list-units ]; then
    for pair in $STUB_ACTIVE; do printf '%s\\n' "${pair%%=*}"; done
    exit 0
fi
if [ "$1" = show ]; then
    for pair in $STUB_ACTIVE; do
        [ "$pair" = "${2}=${pair#*=}" ] || continue
        printf '%s\\n' "${pair#*=}"
    done
    exit 0
fi
exit 0
"""


def retire_adhoc_runs(root: Path, active: dict[str, str] | None = None) -> str:
    """install.sh's own retirement function, lifted and executed against a tree under `root`.

    `active` maps a unit name to the script its ExecStart runs, which is how the host says a
    runner is still going. `tests/unit/test_verify_run_state.py` runs verify.sh's helpers the
    same way: a text assertion would catch a deleted line and miss a mover that archives the
    wrong file.
    """
    text = INSTALL.read_text(encoding="utf-8")
    opening = "retire_adhoc_runs() {"
    assert opening in text, "install.sh does not retire the ad-hoc runners"
    body = opening + text.split(opening, 1)[1].split("\n}\n", 1)[0] + "\n}\n"

    binaries = root / "systemctl-bin"
    binaries.mkdir(exist_ok=True)
    stub = binaries / "systemctl"
    stub.write_text(SYSTEMCTL_UNITS_STUB, encoding="utf-8")
    stub.chmod(0o755)

    harness = root / "retire.sh"
    harness.write_text(
        "\n".join(
            [
                "#!/bin/bash",
                "set -uo pipefail",
                f'RUNS_DIR="{root / "runs"}"',
                f'SBIN_DIR="{root / "sbin"}"',
                'RUN_USER="$(id -gn)"',
                body,
                "retire_adhoc_runs",
            ]
        ),
        encoding="utf-8",
    )
    environment = {
        **os.environ,
        "PATH": f"{binaries}:{os.environ['PATH']}",
        "STUB_ACTIVE": " ".join(f"{unit}={path}" for unit, path in (active or {}).items()),
    }
    completed = subprocess.run(
        ["/bin/bash", str(harness)], capture_output=True, text=True, check=False, env=environment
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def fenced_text(text: str) -> str:
    """Only the fenced blocks: prose may still discuss systemd, and does."""
    inside = False
    kept: list[str] = []
    for line in text.splitlines():
        # A fence indented under a list item is still a fence, and the runner form for a
        # resume is written inside one.
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if inside:
            kept.append(line)
    return "\n".join(kept)


def fenced(name: str) -> str:
    return fenced_text((DOCS / name).read_text(encoding="utf-8"))


def test_the_deploy_readme_starts_no_unit_in_the_operators_session() -> None:
    # infra/README.md is the deploy runbook written as prose, and its step 4 was the last
    # `systemd-run --pipe --wait` in the tree: a create-or-replace whose output the operator
    # read inline, and therefore a job that died with the ssh session that started it.
    offenders = [
        line
        for line in fenced_text(DEPLOY_README.read_text(encoding="utf-8")).splitlines()
        if "systemd-run" in line
    ]

    assert offenders == [], f"infra/README.md runs a job in the operator's session: {offenders}"


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


@pytest.mark.parametrize("name", LONG_STEP_RUNBOOKS)
def test_every_launched_job_is_one_the_runbook_polls(name: str) -> None:
    # The converse of the rule above, and the one the deliverable is about: a launch with no
    # `--status` beside it is a job the operator is told to start and never told to read.
    blocks = fenced(name)
    launched = set(JOB.findall(blocks))
    polled = set(STATUS.findall(blocks))

    assert launched <= polled, f"{name} launches a job it never polls: {launched - polled}"


def test_every_documented_launch_hands_the_chain_to_a_unit_and_returns() -> None:
    # The reason for moving a step onto the runner is that a dropped session must not take the
    # job with it. Without `--detach` the chain runs in the operator's ssh session: the step's
    # own transient unit survives the drop, but the driver that writes the verdict does not, so
    # the status file reads `running` for ever and the lines after it never run.
    # Continuations closed up first: `--detach` may sit on the second physical line.
    sources = [(name, joined(name)) for name in RUNBOOKS]
    sources.append((
        "infra/README.md",
        re.sub(r"\\\n\s*", " ", fenced_text(DEPLOY_README.read_text(encoding="utf-8"))),
    ))

    attached = [
        f"{name}: {line.strip()}"
        for name, blocks in sources
        for line in blocks.splitlines()
        if "host-runner.sh" in line and "--job" in line and "--detach" not in line
    ]

    assert attached == [], f"a launch that dies with the session that started it: {attached}"


AFTER_JOB = re.compile(r"--after-job\s+([A-Za-z0-9._-]+)")


def joined(name: str) -> str:
    """The fenced blocks with `\\`-continuations closed up, so one command is one line."""
    return re.sub(r"\\\n\s*", " ", fenced(name))


@pytest.mark.parametrize("name", RUNBOOKS)
def test_a_documented_wait_always_carries_its_deadline(name: str) -> None:
    # `--after-job` polls another job's status file, and a job that never finishes leaves the
    # follower waiting. The default is 86400 s; a document that arms one says what it waits to.
    undated = [
        line.strip()
        for line in joined(name).splitlines()
        if "--after-job" in line and "--after-timeout" not in line
    ]

    assert undated == [], f"{name} arms a job behind another with no deadline: {undated}"


def test_the_texas_marts_are_armed_behind_the_promotion_they_must_not_precede() -> None:
    # The ad-hoc `tx-step45-runner.sh` polled `systemctl is-active` in a loop, which is the
    # shape `test_no_fenced_block_waits_on_a_unit_by_hand` forbids a runbook from teaching.
    blocks = joined("runbook-tx-load.md")
    followed = set(AFTER_JOB.findall(blocks))

    assert followed, "Step 4 is still a hand-off the operator has to watch for"
    assert followed <= set(JOB.findall(blocks)), (
        f"the runbook follows a job it does not launch: {followed - set(JOB.findall(blocks))}"
    )


@pytest.mark.parametrize("name", RUNBOOKS)
def test_every_documented_relaunch_states_how_it_recovers(name: str) -> None:
    # A job that already has a status file is refused a second launch. A runbook that shows the
    # same job twice is showing a relaunch, and the second one has to say which recovery it is
    # — `--resume` where a stopped job continues, `--force` where starting over is the answer —
    # or the operator reads `pass --force` from the runner at the worst possible moment.
    launched: list[str] = []
    silent: list[str] = []
    for line in joined(name).splitlines():
        if "host-runner.sh" not in line or "--job" not in line:
            continue
        job = JOB.search(line).group(1)
        if job in launched and "--resume" not in line and "--force" not in line:
            silent.append(line.strip())
        launched.append(job)

    assert silent == [], f"{name} relaunches a job with no recovery stated: {silent}"


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


class TestNoRunbookLaunchesANameAnAdHocRunnerOwns:
    """A job name an ad-hoc runner has written a status under is a name a runbook cannot use.

    The retirement clears such a name only when the runner that wrote it is finished; while it
    is live the deferral keeps it, correctly, and a documented launch under that name is refused
    for as long as that lasts — at least a release. Colorado's `co-load` is the case that works:
    its runner is done, so the same deploy that defers Texas clears Colorado.
    """

    # The host's own tx-step45.json, 2026-09-05, shortened at `stamps`.
    HOST_TX_STEP45 = (
        '{"job":"tx-step45","started":"2026-09-05T20:06:14Z","step":"wait-step3",'
        '"step_index":0,"steps_total":3,"unit":"t3-tx-runner","exit":null,"result":"%s",'
        '"finished":%s,"stamps":["2026-09-05T20:06:14Z waiting on t3-tx-runner"]}'
    )

    @staticmethod
    def texas_marts_launch() -> list[str]:
        found = [
            arguments
            for arguments in TestTheDocumentedInvocationsParse.invocations("runbook-tx-load.md")
            if any("tx_allocation" in token for token in arguments)
            and "--resume" not in arguments
        ]
        assert len(found) == 1, f"the Texas marts are launched {len(found)} times"
        return found[0]

    def test_the_deploy_that_defers_texas_still_frees_every_name_a_runbook_launches(
        self, tmp_path: Path
    ) -> None:
        runs, sbin = TestALiveRunnerIsNeverArchived.host(tmp_path)
        retire_adhoc_runs(
            tmp_path,
            active={
                "t3-tx-runner.service": f"{sbin}/tx-step3-resume2-runner.sh",
                "tx-step45-runner.service": f"{sbin}/tx-step45-runner.sh",
            },
        )

        blocked = []
        for name in LONG_STEP_RUNBOOKS:
            for arguments in TestTheDocumentedInvocationsParse.invocations(name):
                if "--resume" in arguments or "--force" in arguments:
                    continue  # a relaunch says how it recovers; that is the case below
                job = arguments[arguments.index("--job") + 1]
                if (runs / f"{job}.json").exists():
                    blocked.append(f"{name}: --job {job}")

        assert blocked == [], f"launched under a name an ad-hoc runner still owns: {blocked}"

    @pytest.mark.parametrize(
        ("state", "finished"),
        [("waiting", "null"), ("complete", '"2026-09-05T23:14:02Z"')],
    )
    def test_the_texas_marts_line_runs_against_the_ad_hoc_status_in_either_state(
        self, tmp_path: Path, state: str, finished: str
    ) -> None:
        # Both reachable states of the live runner: waiting tonight, complete when it lands.
        runs = tmp_path / "runs"
        runs.mkdir(parents=True)
        (runs / "tx-step45.json").write_text(self.HOST_TX_STEP45 % (state, finished), "utf-8")
        environment = stub_environment(tmp_path / "stubs", runs)
        arguments = self.texas_marts_launch()
        subprocess.run(
            [str(RUNNER), "--record", "--job", arguments[arguments.index("--after-job") + 1],
             "--step", "lead", "--step-index", "1", "--steps-total", "1", "--result", "complete"],
            env=environment, check=True, capture_output=True,
        )

        completed = subprocess.run(
            [str(RUNNER), *arguments], env=environment, capture_output=True, text=True
        )

        assert completed.returncode != 3, completed.stderr
        assert "pass --force" not in completed.stderr


class TestTheDocumentedInvocationsParse:
    """A runbook command the runner cannot parse is a step nobody can run.

    Each fenced invocation is executed against the same stub systemd-run the unit tier uses, so
    the assertion is the runner's own parse of the line as written, not a second reading of it.
    """

    @staticmethod
    def invocations_in(blocks: str) -> list[list[str]]:
        joined = re.sub(r"\\\n\s*", " ", blocks)
        lines = joined.splitlines()
        found: list[list[str]] = []
        position = 0
        while position < len(lines):
            line = lines[position]
            position += 1
            if "host-runner.sh" not in line or "--job" not in line:
                continue
            # A quoted argument may run over several lines — a `python -c` script does — so
            # the command is however many lines it takes for the quoting to close.
            candidate = line.strip()
            while True:
                try:
                    tokens = shlex.split(candidate, comments=True)
                    break
                except ValueError:
                    assert position < len(lines), f"unbalanced quoting: {candidate}"
                    candidate = f"{candidate}\n{lines[position]}"
                    position += 1
            while tokens and "host-runner.sh" not in tokens[0]:
                tokens.pop(0)
            if tokens and " " in tokens[0]:  # the ssh form arrives as one quoted token
                tokens = shlex.split(tokens[0])
            found.append([token for token in tokens[1:] if token != "--detach"])
        return found

    @staticmethod
    def invocations(name: str) -> list[list[str]]:
        return TestTheDocumentedInvocationsParse.invocations_in(fenced(name))

    def parses(self, name: str, invocations: list[list[str]], tmp_path: Path) -> None:
        assert invocations, f"{name} has no runner invocation to parse"

        for position, arguments in enumerate(invocations):
            runs = tmp_path / f"runs-{position}"
            environment = stub_environment(tmp_path / f"stubs-{position}", runs)
            job = arguments[arguments.index("--job") + 1]
            if "--after-job" in arguments:
                # A job that never ran cannot be followed, and the refusal comes first.
                subprocess.run(
                    [str(RUNNER), "--record", "--job",
                     arguments[arguments.index("--after-job") + 1], "--step", "lead",
                     "--step-index", "1", "--steps-total", "1", "--result", "complete"],
                    env=environment, check=True, capture_output=True,
                )
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

    @pytest.mark.parametrize("name", LONG_STEP_RUNBOOKS)
    def test_every_fenced_invocation_parses_into_steps(self, name: str, tmp_path: Path) -> None:
        self.parses(name, self.invocations(name), tmp_path)

    def test_the_deploy_readmes_own_invocation_parses_into_steps(self, tmp_path: Path) -> None:
        # Step 4's tile-function reinstall, whose command is a multi-line `python -c` script.
        blocks = fenced_text(DEPLOY_README.read_text(encoding="utf-8"))

        self.parses("infra/README.md", self.invocations_in(blocks), tmp_path)


class TestTheColoradoRunbookRunsOnTheHostAsItStands:
    """`--job co-load` is the first tracked run, and the host already has that name spoken for.

    The ad-hoc `co-load-runner.sh` wrote `/var/lib/glasswell/runs/co-load.json` (complete,
    18:28:30Z) before this track existed, and the tracked runner refuses a job whose status file
    says it already finished. The job name is the runbook's, so what moves is the ad-hoc
    verdict: install.sh archives it, unread by the refusal and still on disk as the evidence of
    the load it records.
    """

    # The host's own file, 2026-09-05, shortened at `stamps`. It carries neither `log` nor
    # `steps`, which is what tells an ad-hoc verdict from a tracked one.
    ADHOC_CO_LOAD = (
        '{"job":"co-load","started":"2026-09-05T18:21:35Z","step":"complete","step_index":5,'
        '"steps_total":5,"unit":"c5-co-marts-counts","exit":0,"result":"complete",'
        '"finished":"2026-09-05T18:28:30Z","stamps":["2026-09-05T18:28:30Z step5 end rc=0"]}'
    )

    @staticmethod
    def seed_adhoc(root: Path, body: str) -> None:
        # The host's shape: the ad-hoc script in place beside the verdict it wrote. The
        # retirement is keyed on the script, so both halves are what a real deploy meets.
        runs = root / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        (runs / "co-load.json").write_text(body, encoding="utf-8")
        (runs / "co-load.stamps").write_text("2026-09-05T18:28:30Z step5 end rc=0\n", "utf-8")
        sbin = root / "sbin"
        sbin.mkdir(parents=True, exist_ok=True)
        (sbin / "co-load-runner.sh").write_text("#!/bin/bash\n", encoding="utf-8")

    @staticmethod
    def colorado_launch() -> list[str]:
        invocations = TestTheDocumentedInvocationsParse.invocations("runbook-co-tier2.md")
        launches = [line for line in invocations if "--status" not in line]
        assert len(launches) == 1, f"the Colorado runbook launches {len(launches)} jobs"
        return launches[0]

    def test_the_first_tracked_run_is_refused_by_the_ad_hoc_verdict_under_its_name(
        self, tmp_path: Path
    ) -> None:
        # The finding itself, kept as the reason the archiving below exists.
        runs = tmp_path / "runs"
        self.seed_adhoc(tmp_path, self.ADHOC_CO_LOAD)
        environment = stub_environment(tmp_path / "stubs", runs)

        completed = subprocess.run(
            [str(RUNNER), *self.colorado_launch()], env=environment, capture_output=True, text=True
        )

        assert completed.returncode == 3
        assert "already finished" in completed.stderr

    def test_install_archives_the_ad_hoc_verdict_and_the_runbook_line_then_runs(
        self, tmp_path: Path
    ) -> None:
        runs = tmp_path / "runs"
        self.seed_adhoc(tmp_path, self.ADHOC_CO_LOAD)

        retire_adhoc_runs(tmp_path)

        assert not (runs / "co-load.json").exists()
        archived = runs / "archive" / "co-load.json"
        assert json.loads(archived.read_text(encoding="utf-8"))["finished"] == (
            "2026-09-05T18:28:30Z"
        ), "the ad-hoc load's own record is evidence and is kept whole"
        assert (runs / "archive" / "co-load.stamps").exists()

        environment = stub_environment(tmp_path / "stubs", runs)
        completed = subprocess.run(
            [str(RUNNER), *self.colorado_launch()], env=environment, capture_output=True, text=True
        )

        assert completed.returncode != 3, f"still refused: {completed.stderr}"
        assert json.loads((runs / "co-load.json").read_text(encoding="utf-8"))["job"] == "co-load"

    def test_a_tracked_run_of_the_same_job_is_never_archived_by_a_later_install(
        self, tmp_path: Path
    ) -> None:
        # install.sh runs on every deploy. The migration is keyed on the ad-hoc script: once
        # `co-load-runner.sh` has been retired, `co-load` is the tracked runner's job name and
        # every later deploy leaves its records alone.
        runs = tmp_path / "runs"
        environment = stub_environment(tmp_path / "stubs", runs)
        subprocess.run(
            [str(RUNNER), "--job", "co-load", "--", "stage", "/bin/echo", '{"staged": 1}'],
            env=environment, check=True, capture_output=True,
        )

        retire_adhoc_runs(tmp_path)

        assert (runs / "co-load.json").exists()
        assert not (runs / "archive" / "co-load.json").exists()

    def test_a_status_file_that_is_no_ad_hoc_runners_is_never_swept(self, tmp_path: Path) -> None:
        # The step retires five named runners, not everything in the directory: an operator's
        # own record has neither a script nor a name here, and a deploy is not a cleaner.
        (runs := tmp_path / "runs").mkdir()
        (runs / "post-deploy-v082.json").write_text('{"job":"post-deploy-v082"}', "utf-8")
        (sbin := tmp_path / "sbin").mkdir()
        (sbin / "co-load-runner.sh").write_text("#!/bin/bash\n", encoding="utf-8")

        retire_adhoc_runs(tmp_path)

        assert (runs / "post-deploy-v082.json").exists()
        assert not (runs / "archive" / "post-deploy-v082.json").exists()


class TestALiveRunnerIsNeverArchived:
    """A deploy lands while a load is running — it already restarts the API beside one.

    The shapes below are VM 111's at 2026-09-05 21:00Z: `t3-tx-runner` and `tx-step45-runner`
    active, their ExecStart paths two of the five scripts, and `tx-step45.json` reading
    `waiting` with no `log` key at all. Deciding on the document's shape archived every one of
    them: the operator's poll path, the stamps the eventual verdict is assembled from, and the
    script the running unit was started from.
    """

    WAITING = (
        '{"job":"tx-step45","started":"2026-09-05T20:06:14Z","step":"wait-step3",'
        '"step_index":0,"steps_total":3,"unit":"t3-tx-runner","exit":null,"result":"waiting",'
        '"finished":null,"stamps":["2026-09-05T20:06:14Z waiting on t3-tx-runner"]}'
    )
    FINISHED = (
        '{"job":"co-load","started":"2026-09-05T18:21:35Z","step":"complete","step_index":5,'
        '"steps_total":5,"unit":"c5-co-marts-counts","exit":0,"result":"complete",'
        '"finished":"2026-09-05T18:28:30Z","stamps":["2026-09-05T18:28:30Z step5 end rc=0"]}'
    )

    @staticmethod
    def host(tmp_path: Path) -> tuple[Path, Path]:
        runs = tmp_path / "runs"
        runs.mkdir()
        sbin = tmp_path / "sbin"
        sbin.mkdir()
        for name in ADHOC_RUNNERS:
            (sbin / name).write_text("#!/bin/bash\n", encoding="utf-8")
        for job, body in (("tx-step45", TestALiveRunnerIsNeverArchived.WAITING),
                          ("co-load", TestALiveRunnerIsNeverArchived.FINISHED)):
            (runs / f"{job}.json").write_text(body, encoding="utf-8")
            (runs / f"{job}.stamps").write_text("2026-09-05T20:06:14Z waiting\n", "utf-8")
        return runs, sbin

    def test_the_live_texas_runners_keep_their_scripts_status_and_stamps(
        self, tmp_path: Path
    ) -> None:
        runs, sbin = self.host(tmp_path)

        printed = retire_adhoc_runs(
            tmp_path,
            active={
                "t3-tx-runner.service": f"{sbin}/tx-step3-resume2-runner.sh",
                "tx-step45-runner.service": f"{sbin}/tx-step45-runner.sh",
            },
        )

        assert (runs / "tx-step45.json").exists(), "the operator's poll path was moved"
        assert (runs / "tx-step45.stamps").exists(), "the verdict's evidence trail was moved"
        assert (sbin / "tx-step45-runner.sh").exists()
        assert (sbin / "tx-step3-resume2-runner.sh").exists()
        assert "deferred: live (t3-tx-runner.service)" in printed
        assert "deferred: live (tx-step45-runner.service)" in printed

    def test_the_finished_one_beside_them_is_archived_in_the_same_pass(
        self, tmp_path: Path
    ) -> None:
        # A deferral is per-runner, not a refusal: the deploy continues and takes what it can.
        runs, sbin = self.host(tmp_path)

        retire_adhoc_runs(
            tmp_path, active={"tx-step45-runner.service": f"{sbin}/tx-step45-runner.sh"}
        )

        assert (runs / "archive" / "co-load.json").exists()
        assert not (sbin / "co-load-runner.sh").exists()

    def test_a_status_that_reads_running_defers_with_no_unit_to_name(
        self, tmp_path: Path
    ) -> None:
        # The unit may already be gone from `list-units` while the job is still going — the
        # file it published is the other half of the same question.
        runs, sbin = self.host(tmp_path)
        (runs / "co-load.json").write_text(self.FINISHED.replace("complete", "running"), "utf-8")

        printed = retire_adhoc_runs(tmp_path)

        assert (runs / "co-load.json").exists()
        assert (sbin / "co-load-runner.sh").exists()
        assert "deferred: live (co-load" in printed

    def test_the_deferred_one_is_retired_by_the_next_deploy_once_it_has_finished(
        self, tmp_path: Path
    ) -> None:
        runs, sbin = self.host(tmp_path)
        retire_adhoc_runs(
            tmp_path, active={"tx-step45-runner.service": f"{sbin}/tx-step45-runner.sh"}
        )
        assert (runs / "tx-step45.json").exists()

        (runs / "tx-step45.json").write_text(
            self.WAITING.replace('"result":"waiting"', '"result":"complete"'), encoding="utf-8"
        )
        retire_adhoc_runs(tmp_path)

        assert (runs / "archive" / "tx-step45.json").exists()
        assert (runs / "archive" / "tx-step45.stamps").exists()
        assert (runs / "archive" / "tx-step45-runner.sh").exists()

    def test_the_five_ad_hoc_runners_are_retired_into_the_archive_not_deleted(
        self, tmp_path: Path
    ) -> None:
        sbin = tmp_path / "sbin"
        sbin.mkdir()
        for name in ADHOC_RUNNERS:
            (sbin / name).write_text("#!/bin/bash\n", encoding="utf-8")
        (sbin / "host-runner.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (runs := tmp_path / "runs").mkdir()

        retire_adhoc_runs(tmp_path)

        assert [name for name in ADHOC_RUNNERS if (sbin / name).exists()] == []
        assert sorted(path.name for path in (runs / "archive").iterdir()) == sorted(ADHOC_RUNNERS)
        assert (sbin / "host-runner.sh").exists(), "the tracked runner is not an ad-hoc one"
