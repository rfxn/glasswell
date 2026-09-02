"""One regeneration path for the client's registry module, and the test that keeps it one.

The generated module is committed, so a stale copy is a client naming a rule the registry no
longer serves. The script is run as a subprocess — the way a person runs `make jurisdictions` —
rather than imported, because a scratch renderer that is *nearly* right is how a generated
artifact ends up hand-repaired.
"""

from __future__ import annotations

import json
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
TS_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
GENERATED = ROOT / "web" / "src" / "map" / "jurisdictions.generated.ts"
ROSTER = ROOT / "web" / "src" / "map" / "wells-roster.json"


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
    # The header explains why counts are absent, so the scan is over the body below it, and
    # with the doc comments stripped: prose about a measurement is documentation, and the same
    # cut `tests/unit/test_add_a_state.py` makes before it judges a TypeScript line.
    body_only = TS_COMMENT.sub("", body.split("export interface GeneratedJurisdiction", 1)[1])
    assert "well_count" not in body_only
    assert "measured" not in body_only
    # No number in the body is wider than a prefix or an array index, so a count — 43_817, or
    # any of the four tables this module replaced — cannot have been generated into it.
    standalone = re.findall(r"(?<![\w])\d[\d_]*(?![\w])", body_only)
    assert standalone
    assert [found for found in standalone if len(found) > 2] == []


def test_it_carries_the_presentation_facts_each_wells_row_used_to_hold_as_a_literal() -> None:
    """Seven facts per row lived in `web/src/map/registry.ts` as object literals, where no gate
    could read them and a fifth jurisdiction was four hand edits."""
    body = GENERATED.read_text(encoding="utf-8")

    for row in JURISDICTIONS:
        assert f'wellsLayerId: "{row["wells_layer_id"]}"' in body
        assert f"wellsDrawOrder: {row['wells_draw_order']}," in body
        for layer in row["wells_style_layer_ids"]:  # type: ignore[union-attr]
            assert f'"{layer}"' in body
    # The count is not in the template; the slot for it is, once per row.
    assert TS_COMMENT.sub("", body).count("{count}") == len(JURISDICTIONS)


def test_the_roster_is_the_same_rows_as_data_for_the_reader_that_cannot_import_a_module() -> None:
    """`tests/e2e/chrome-fold.mjs` is plain node ESM with no TypeScript loader, and its refusal
    on zero rows is what the map-chrome gate rests on."""
    roster = json.loads(ROSTER.read_text(encoding="utf-8"))

    assert [row["code"] for row in roster] == sorted(
        (str(row["jurisdiction_code"]) for row in JURISDICTIONS),
        key=lambda code: next(
            int(item["wells_draw_order"])  # type: ignore[arg-type]
            for item in JURISDICTIONS
            if item["jurisdiction_code"] == code
        ),
    )
    assert [row["drawOrder"] for row in roster] == sorted(row["drawOrder"] for row in roster)
    assert all(row["id"] in row["styleLayers"] for row in roster)


def test_a_registration_with_no_tile_layer_is_refused_by_name(monkeypatch) -> None:
    """The column is nullable and an f-string rendered an explicit None as the string "None",
    which became `marts.None_tile` in a provenance line and a style layer that 404s every
    tile. An absent key raises, which is loud and fine; a rendered "None" is neither."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("regen_jurisdictions", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "JURISDICTIONS",
        tuple(
            {**row, "wells_tile_layer_id": None} if row["jurisdiction_code"] == "MT" else row
            for row in JURISDICTIONS
        ),
    )

    with pytest.raises(SystemExit) as refused:
        module.rendered()

    assert "MT" in str(refused.value)
    assert "None" not in str(refused.value)
