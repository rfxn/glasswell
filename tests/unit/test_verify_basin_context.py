"""The basin-context deploy check, executed rather than read (gate H-18).

It shipped as `resident >= live well count`. The mart is written by the deploy and by a
scheduler that is disabled; the ingest timer is enabled and promotes wells between deploys, so
one promoted well made a healthy host's verify red. The check is now over two facts that
cannot race each other: the mart is not empty where the spine has wells, and its resident count
is the one its own refresh recorded on the derivation it wrote.

Every branch has to report exactly one check. A branch that only printed would shrink the
deploy gate without failing it, which is the same defect pointing the other way.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

VERIFY = Path(__file__).resolve().parents[2] / "infra" / "verify.sh"
HELPERS = ("ok", "bad", "basin_context_check")


def extract(name: str) -> str:
    """The shipped definition, one-liner or block, so the test drives the real branches."""
    source = VERIFY.read_text(encoding="utf-8")
    oneline = re.search(rf"^{re.escape(name)}\(\) \{{.*\}}$", source, re.MULTILINE)
    if oneline:
        return oneline.group(0)
    start = re.search(rf"^{re.escape(name)}\(\) \{{$", source, re.MULTILINE)
    assert start, f"{name}() is not defined in verify.sh"
    end = source.index("\n}\n", start.start())
    return source[start.start() : end + 3]


def run_with(rows: int, wells: int, recorded: int) -> tuple[int, int, str]:
    script = "\n".join(
        [
            "set -uo pipefail",
            "passed=0",
            "failed=0",
            *(extract(name) for name in HELPERS),
            f'basin_context_check "{rows}" "{wells}" "{recorded}"',
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


def test_a_mart_that_holds_what_its_own_run_wrote_passes() -> None:
    passed, failed, output = run_with(rows=585_864, wells=585_864, recorded=585_864)

    assert (passed, failed) == (1, 0), output


def test_a_well_promoted_since_the_refresh_is_not_a_deploy_failure() -> None:
    """The regression this check exists for: the ingest timer lands one well between deploys
    and the mart, which is correct for the run that wrote it, was refused for being behind."""
    passed, failed, output = run_with(rows=585_864, wells=585_865, recorded=585_864)

    assert (passed, failed) == (1, 0), output


def test_a_spine_with_no_wells_asserts_nothing_and_still_reports() -> None:
    passed, failed, output = run_with(rows=0, wells=0, recorded=-1)

    assert (passed, failed) == (1, 0), output
    assert "holds no wells yet" in output


def test_an_empty_mart_on_a_spine_with_wells_refuses_and_names_the_step() -> None:
    passed, failed, output = run_with(rows=0, wells=585_864, recorded=-1)

    assert (passed, failed) == (0, 1), output
    assert "6d2" in output


def test_a_count_that_is_not_what_the_run_recorded_refuses() -> None:
    """Rows deleted, half a refresh, or two runs interleaved: the mart no longer holds what
    any single derivation claims to have written, and that is a fault whatever caused it."""
    passed, failed, output = run_with(rows=585_000, wells=585_864, recorded=585_864)

    assert (passed, failed) == (0, 1), output
    assert "recorded by the refresh derivation" in output


def test_every_branch_reports_exactly_one_check() -> None:
    for rows, wells, recorded in (
        (585_864, 585_864, 585_864),
        (585_864, 585_865, 585_864),
        (0, 0, -1),
        (0, 585_864, -1),
        (585_000, 585_864, 585_864),
    ):
        passed, failed, output = run_with(rows, wells, recorded)
        assert passed + failed == 1, f"{rows}/{wells}/{recorded}: {output}"
