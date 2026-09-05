"""The gate's own self-checks: the diff classifier, and what the aggregate does with a skip.

`tests/conftest.py` was in `scripts/test-scope.py`'s tier-reaching fallback and absent from
`ci.yml`'s `db` regex, so a pull request that changed only the harness — which is most of this
track — ran ruff and the unit tier, skipped all four database shards, and reported `CI complete`
green. The workflow now asks the script for the pattern; these hold the two ends together.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SCRIPT = ROOT / "scripts" / "test-scope.py"

sys.path.insert(0, str(ROOT / "scripts"))


def db_pattern() -> str:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--db-filter"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    return completed.stdout.strip()


def classify_step() -> str:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = next(s for s in document["jobs"]["changes"]["steps"] if s.get("id") == "filter")
    return step["run"]


@pytest.mark.parametrize(
    ("path", "reaches_a_database_tier"),
    [
        ("tests/conftest.py", True),
        ("tests/contract/conftest.py", True),
        ("tests/integration/test_marts_nd.py", True),
        ("tests/support/seed.py", True),
        ("tests/fixtures/nd_gis/OGD_Wells_300.zip", True),
        ("src/glasswell/api/access_log.py", True),
        ("src/glasswell/db/migrations/081_tx_pdq_format.sql", True),
        ("requirements.lock", True),
        ("Makefile", True),
        (".github/workflows/ci.yml", True),
        ("tests/unit/test_envelope.py", False),
        ("tests/e2e/smoke.mjs", False),
        ("scripts/test-scope.py", False),
        ("web/src/map.ts", False),
        ("README.md", False),
    ],
)
def test_the_db_filter_classifies_a_path_the_way_the_tiers_do(
    path: str, reaches_a_database_tier: bool
) -> None:
    assert bool(re.search(db_pattern(), path)) is reaches_a_database_tier


def test_every_tier_reaching_path_the_local_tool_falls_back_on_is_in_the_filter() -> None:
    """The drift this closes: the script grew `tests/conftest.py` and the workflow did not."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("test_scope", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pattern = re.compile(module.db_filter_pattern())

    # pyproject.toml is the one deliberate omission: a release commit's only edit to it is the
    # version string, and both ends test that separately.
    for path in module.FULL_SUITE_PATHS:
        if path == "pyproject.toml":
            continue
        assert pattern.search(path), f"{path} reaches every tier locally but not in CI"
    for prefix in (*module.FULL_SUITE_PREFIXES, *module.DB_TIER_PREFIXES):
        assert pattern.search(f"{prefix}anything.py"), prefix


def test_the_workflow_derives_the_filter_rather_than_restating_it() -> None:
    """A literal in the workflow is a second list, and a second list drifts."""
    body = classify_step()

    assert "scripts/test-scope.py --db-filter" in body
    assert "tests/(contract|integration" not in body, "the regex is back in the workflow"


JOBS = (
    "changes",
    "python-lint",
    "python-db",
    "harness-hygiene",
    "web",
    "e2e-guards",
    "shell",
    "collateral",
    "map-chrome",
)


def aggregate_step() -> str:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return document["jobs"]["ci"]["steps"][0]["run"].replace("${{ toJSON(needs) }}", "")


def run_aggregate(results: dict[str, str], **verdicts: str) -> subprocess.CompletedProcess:
    """The shipped `CI complete` step, run verbatim against a planted `needs` context."""
    environment = {
        "RESULTS": json.dumps({job: {"result": result} for job, result in results.items()}),
        "COVERED": verdicts.get("covered", "false"),
        "DB": verdicts.get("db", "false"),
        "WEB": verdicts.get("web", "false"),
        "SHELL_": verdicts.get("shell", "false"),
        "COLLATERAL": verdicts.get("collateral", "false"),
        "PATH": "/usr/bin:/bin",
    }
    return subprocess.run(
        ["bash", "-c", aggregate_step()], env=environment, capture_output=True, text=True
    )


ALL_RAN = dict.fromkeys(JOBS, "success")
SHARDS_SKIPPED = {**ALL_RAN, "python-db": "skipped", "harness-hygiene": "skipped"}


def test_the_aggregate_is_green_when_every_job_ran() -> None:
    assert run_aggregate(ALL_RAN, db="true", web="true").returncode == 0


def test_the_aggregate_is_red_on_a_failed_shard() -> None:
    completed = run_aggregate({**ALL_RAN, "python-db": "failure"}, db="true")

    assert completed.returncode == 1
    assert "python-db=failure" in completed.stdout


def test_a_shard_skipped_though_the_diff_reached_a_database_tier_is_red() -> None:
    """The hole that made the missing `tests/conftest.py` filter entry silent: a skip was a pass
    whatever its cause, so four shards standing down read the same as nothing to run."""
    completed = run_aggregate(SHARDS_SKIPPED, db="true")

    assert completed.returncode == 1
    assert "python-db=skipped" in completed.stdout
    assert "harness-hygiene=skipped" in completed.stdout


def test_a_shard_skipped_because_nothing_database_shaped_changed_is_green() -> None:
    assert run_aggregate(SHARDS_SKIPPED, db="false").returncode == 0


def test_every_skip_is_accepted_when_the_tree_is_already_green() -> None:
    """`covered` skips the whole gate deliberately; the obligation to run does not apply."""
    assert run_aggregate(dict.fromkeys(JOBS, "skipped"), covered="true", db="true").returncode == 0


@pytest.mark.parametrize(
    ("verdict", "job"),
    [("web", "map-chrome"), ("shell", "shell"), ("collateral", "collateral")],
)
def test_each_filter_verdict_obliges_the_jobs_it_names(verdict: str, job: str) -> None:
    completed = run_aggregate({**ALL_RAN, job: "skipped"}, **{verdict: "true"})

    assert completed.returncode == 1
    assert f"{job}=skipped" in completed.stdout
