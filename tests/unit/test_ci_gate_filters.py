"""The gate's diff classifier and `make test`'s selection read the same list, or neither is safe.

`tests/conftest.py` was in `scripts/test-scope.py`'s tier-reaching fallback and absent from
`ci.yml`'s `db` regex, so a pull request that changed only the harness — which is most of this
track — ran ruff and the unit tier, skipped all four database shards, and reported `CI complete`
green. The workflow now asks the script for the pattern; these hold the two ends together.
"""

from __future__ import annotations

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
