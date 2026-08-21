"""One regeneration path for the snapshot, and the test that keeps it one.

`test_openapi_snapshot.py` holds the committed file to the served document; nothing held the
script an agent runs to rewrite that file to the same bytes. A scratch renderer that is
*nearly* right is how a generated artifact ends up hand-repaired (CADENCE N-3), so the script
is run here as a subprocess — the way a person runs it — rather than imported.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

import glasswell
from tests.contract.test_openapi_snapshot import served

SOURCE_ROOT = Path(glasswell.__file__).parents[1]
SCRIPT = SOURCE_ROOT.parent / "scripts" / "regen-snapshot.py"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    # The child has to import the tree these tests imported, which in a worktree is not the
    # tree the venv was installed against.
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(SOURCE_ROOT)},
        check=False,
    )


def test_the_script_writes_exactly_what_the_snapshot_gate_demands(
    client: TestClient, tmp_path: Path
) -> None:
    target = tmp_path / "openapi_snapshot.json"

    completed = _run(str(target))

    assert completed.returncode == 0, completed.stderr
    assert target.read_text(encoding="utf-8") == served(client)


def test_the_script_reports_a_stale_snapshot_without_rewriting_it(tmp_path: Path) -> None:
    """`--check` is the arm a build step calls: it fails on drift and touches nothing."""
    target = tmp_path / "openapi_snapshot.json"
    assert _run(str(target)).returncode == 0
    fresh = _run("--check", str(target))
    assert fresh.returncode == 0, fresh.stdout
    target.write_text(
        target.read_text(encoding="utf-8").replace('"openapi"', '"openapi_drifted"', 1),
        encoding="utf-8",
    )

    completed = _run("--check", str(target))

    assert completed.returncode == 1
    assert "stale" in completed.stdout
    assert '"openapi_drifted"' in target.read_text(encoding="utf-8")
