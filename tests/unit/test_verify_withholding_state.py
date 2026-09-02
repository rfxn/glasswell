"""The withholding-mart check, executed rather than read (gate-v075 MINOR-6).

It shipped as an unconditional `count(*) > 0`, which refused a deploy on two states that are
not system faults: a host where the cumulatives refresh has never run, and a regulator that
has released every confidential well. The design check twelve lines below already made the
opposite argument for its own source, and made it well.

Every branch has to report a check. A branch that only printed would quietly drop the
deploy's check count, which is the same defect in a different direction: the gate would look
smaller rather than louder.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

VERIFY = Path(__file__).resolve().parents[2] / "infra" / "verify.sh"
HELPERS = ("ok", "bad", "assert_true")


def extract(name: str) -> str:
    source = VERIFY.read_text(encoding="utf-8")
    oneline = re.search(rf"^{re.escape(name)}\(\) \{{.*\}}$", source, re.MULTILINE)
    if oneline:
        return oneline.group(0)
    start = re.search(rf"^{re.escape(name)}\(\) \{{$", source, re.MULTILINE)
    assert start, f"{name}() is not defined in verify.sh"
    end = source.index("\n}\n", start.start())
    return source[start.start() : end + 3]


def case_block() -> str:
    """The shipped `case`, lifted whole so the test drives the real branches."""
    source = VERIFY.read_text(encoding="utf-8")
    start = source.index('case "$withholding_state" in')
    end = source.index("\nesac\n", start)
    return source[start : end + 6]


def run_with(state: str) -> tuple[int, int, str]:
    script = "\n".join(
        [
            "set -uo pipefail",
            "passed=0",
            "failed=0",
            "withholding=0",
            f"withholding_state={state!r}",
            *(extract(name) for name in HELPERS),
            case_block(),
            'printf "RESULT %s %s\\n" "$passed" "$failed"',
        ]
    )
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, check=False
    )
    tail = [line for line in result.stdout.splitlines() if line.startswith("RESULT ")]
    assert tail, result.stdout + result.stderr
    _, passed, failed = tail[0].split()
    return int(passed), int(failed), result.stdout


@pytest.mark.parametrize("state", ["pending", "none_open", "ok"])
def test_a_state_that_is_not_a_system_fault_passes_and_still_counts(state: str) -> None:
    passed, failed, output = run_with(state)

    assert (passed, failed) == (1, 0), output


def test_a_refresh_that_ran_and_held_nothing_it_should_have_still_refuses() -> None:
    """The one arm that is a fault: rows were open to hold and the mart is empty anyway."""
    passed, failed, output = run_with("bad")

    assert (passed, failed) == (0, 1), output
    assert "well withholding populated" in output


def test_every_branch_reports_exactly_one_check() -> None:
    """The count cannot drop: a silent branch would shrink the deploy gate without failing."""
    for state in ("pending", "none_open", "ok", "bad"):
        passed, failed, output = run_with(state)
        assert passed + failed == 1, f"{state} reported {passed + failed} checks: {output}"
