"""The launch-posture assertion, executed rather than grepped, and read for its own scope.

`verify.sh` asserted "every resident and cross-jurisdiction row observes" over a query that
named `ND`, `TX`, `NM`, `MT` or a null jurisdiction. Colorado's six launching rows were outside
that list, so the one gate that reads the posture on the host could not have seen them -- and a
seventh state's rows would be invisible in exactly the same way. A jurisdiction nobody listed is
where a launching row lands, so the query is held to the ruling as ruled: every resolved row.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.test_verify_helpers import run_helper

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "infra" / "verify.sh"
MARKER = 'launching="$('


def posture_assertion() -> str:
    """The two physical lines of the real assertion: the query and the count it is held to."""
    text = VERIFY.read_text()
    start = text.index(MARKER)
    end = text.index("\n", text.index("\n", start) + 1)
    return text[start:end]


def verdict(tmp_path: Path, answer: str) -> str:
    result = run_helper(
        tmp_path,
        f'{posture_assertion()}\nprintf "passed=%s failed=%s\\n" "$passed" "$failed"',
        stub_env={"STUB_SQL_ANSWER": answer},
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1]


def test_a_host_where_nothing_launches_passes(tmp_path: Path) -> None:
    assert verdict(tmp_path, "0") == "passed=1 failed=0"


def test_one_launching_row_anywhere_fails_it(tmp_path: Path) -> None:
    assert verdict(tmp_path, "1") == "passed=0 failed=1"


def test_six_of_them_fail_it_too(tmp_path: Path) -> None:
    """Colorado's count, which the scoped query returned zero for."""
    assert verdict(tmp_path, "6") == "passed=0 failed=1"


def test_the_query_scopes_to_no_jurisdiction_at_all() -> None:
    """The class, not the instance: any state list in this query is a state list that will be
    out of date the next time a jurisdiction registers."""
    query = posture_assertion()

    assert "launch_mode = 'launch'" in query
    assert "jurisdiction" not in query, "the posture query names jurisdictions, so it scopes"
