"""Console scripts are the operator surface, and a load path with no entry point never runs.

The boundary layer shipped with its tables, tile functions and martin sources installed and
stayed empty because neither half of the load was reachable as a command.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
PYPROJECT = ROOT / "pyproject.toml"

# Bytes into canonical, then canonical into the tile mart; either one missing serves nothing.
BOUNDARY_COMMANDS = {
    "glasswell-basin-boundaries": "glasswell.marts.basin_boundaries",
    "glasswell-eia-boundaries": "glasswell.ingest.eia_boundaries",
}


def declared_scripts() -> dict[str, str]:
    return tomllib.loads(PYPROJECT.read_text())["project"]["scripts"]


@pytest.mark.parametrize("name", sorted(declared_scripts()))
def test_every_declared_console_script_resolves_to_a_callable(name: str) -> None:
    module_path, _, attribute = declared_scripts()[name].partition(":")

    assert callable(getattr(importlib.import_module(module_path), attribute, None))


@pytest.mark.parametrize(("command", "module_path"), sorted(BOUNDARY_COMMANDS.items()))
def test_both_halves_of_the_boundary_load_are_reachable_as_a_command(
    command: str, module_path: str
) -> None:
    assert declared_scripts().get(command) == f"{module_path}:main"
    assert callable(getattr(importlib.import_module(module_path), "main", None))


def test_the_nd_wells_module_runs_as_the_command_p7_documents():
    """P7 documents `python -m glasswell.marts.nd_wells --dsn ...`; a module that stopped being
    runnable that way would leave the documented command with nothing behind it."""
    completed = subprocess.run(
        [sys.executable, "-m", "glasswell.marts.nd_wells", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--dsn" in completed.stdout
