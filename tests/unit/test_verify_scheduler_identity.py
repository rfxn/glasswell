"""The scheduler-identity assertion, executed against the strings PostgreSQL actually returns.

`verify.sh` asserted `f|t` against `select rolsuper || '|' || rolcanlogin`. psql renders a bare
boolean column through `boolout`, which spells it `t`/`f`; a concatenation goes through the text
cast, which spells the same value `true`/`false`. So the expectation could not match any role at
all, and the line had never passed on any host -- including the one where the role is correct.
Grepping for the assertion would not have found that, so the line is lifted out of the real
script and run under `bash` against the three answers the query can give.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.test_verify_helpers import run_helper

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "infra" / "verify.sh"
MARKER = 'assert "glasswell_scheduler can log in and is not a superuser"'

# What `select rolsuper || '|' || rolcanlogin` returns, measured on the deployed host on
# 2026-09-03: the correct role, a superuser, and a role that cannot log in.
CORRECT = "false|true"
SUPERUSER = "true|true"
NOLOGIN = "false|false"


def identity_assertion() -> str:
    """The two physical lines of the real assertion, label and continuation."""
    text = VERIFY.read_text()
    start = text.index(MARKER)
    end = text.index("\n", text.index("\n", start) + 1)
    return text[start:end]


def verdict(tmp_path: Path, answer: str) -> str:
    result = run_helper(
        tmp_path,
        f'{identity_assertion()}\nprintf "passed=%s failed=%s\\n" "$passed" "$failed"',
        stub_env={"STUB_SQL_ANSWER": answer},
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1]


def test_the_assertion_passes_for_the_role_the_migration_creates(tmp_path: Path) -> None:
    assert verdict(tmp_path, CORRECT) == "passed=1 failed=0"


def test_a_superuser_scheduler_role_fails_it(tmp_path: Path) -> None:
    assert verdict(tmp_path, SUPERUSER) == "passed=0 failed=1"


def test_a_role_that_cannot_log_in_fails_it(tmp_path: Path) -> None:
    assert verdict(tmp_path, NOLOGIN) == "passed=0 failed=1"


def test_no_assertion_compares_a_boolean_concatenation_to_the_bare_rendering() -> None:
    """The class, not the instance: any `|| '|' ||` over booleans returns true/false, so an
    expectation spelled t/f is one no host can satisfy. The expectation and the query sit on
    two physical lines, so the sweep reads the label line together with its continuation."""
    lines = VERIFY.read_text().splitlines()
    concatenations = [
        (lines[index - 1], line)
        for index, line in enumerate(lines)
        if index and "|| '|' ||" in line and "pg_roles" in line
    ]

    assert concatenations, "no boolean concatenation is left; this sweep would be vacuous"
    bare = [
        expectation.strip()
        for expectation, _query in concatenations
        if "'t|" in expectation or "'f|" in expectation
    ]

    assert bare == [], f"{bare} expect psql's bare boolean rendering from a text concatenation"
