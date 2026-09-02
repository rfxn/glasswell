"""One regeneration path for the client's registry module, and the test that keeps it one.

The generated module is committed, so a stale copy is a client naming a rule the registry no
longer serves. The script is run as a subprocess — the way a person runs `make jurisdictions` —
rather than imported, because a scratch renderer that is *nearly* right is how a generated
artifact ends up hand-repaired.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import glasswell
from glasswell.seed.jurisdictions import JURISDICTION_RULES, JURISDICTIONS, rule_parameters

pytestmark = pytest.mark.unit

SOURCE_ROOT = Path(glasswell.__file__).parents[1]
ROOT = SOURCE_ROOT.parent
SCRIPT = ROOT / "scripts" / "regen-jurisdictions.py"
GENERATED = ROOT / "web" / "src" / "map" / "jurisdictions.generated.ts"


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


def test_the_committed_module_is_what_the_script_writes(tmp_path: Path) -> None:
    target = tmp_path / "jurisdictions.generated.ts"

    result = _run(str(target))

    assert result.returncode == 0, result.stderr
    assert target.read_text(encoding="utf-8") == GENERATED.read_text(encoding="utf-8")


def test_the_check_mode_refuses_a_stale_file(tmp_path: Path) -> None:
    """`make jurisdictions` is a step in the runbook, so forgetting it has to be loud."""
    stale = tmp_path / "jurisdictions.generated.ts"
    stale.write_text("// hand-edited\n", encoding="utf-8")

    assert _run(str(GENERATED), "--check").returncode == 0
    refusal = _run(str(stale), "--check")
    assert refusal.returncode == 1
    assert "stale" in refusal.stderr


def test_it_carries_every_registration_and_its_serving_rules_and_no_counts() -> None:
    """Registrations only. A count needs the date it was measured on beside it and a constant
    cannot carry one, so counts are fetched at runtime instead (§4 design A)."""
    body = GENERATED.read_text(encoding="utf-8")

    for row in JURISDICTIONS:
        assert f'code: "{row["jurisdiction_code"]}"' in body
        assert f'name: "{row["name"]}"' in body
        assert f'prefix: "{row["identity_prefix"]}"' in body
        assert f'colour: "{row["map_colour"]}"' in body
        assert f'wellsTileLayerId: "{row["wells_tile_layer_id"]}"' in body
    for rule in (rule_parameters(row) for row in JURISDICTION_RULES):
        if rule["serving"]:
            assert f'"{rule["rule_id"]}"' in body
    # The header explains why counts are absent, so the scan is over the body below it.
    body_only = body.split("export interface GeneratedJurisdiction", 1)[1]
    assert "well_count" not in body_only
    assert "measured" not in body_only
    # No number in the body is wider than a prefix or an array index, so a count — 43_817, or
    # any of the four tables this module replaced — cannot have been generated into it.
    standalone = re.findall(r"(?<![\w])\d[\d_]*(?![\w])", body_only)
    assert standalone
    assert [found for found in standalone if len(found) > 2] == []
