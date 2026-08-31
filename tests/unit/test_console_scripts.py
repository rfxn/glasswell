"""The New Mexico entry points, and the Tier 1 load that deliberately has none.

Scoped to the New Mexico pair on purpose: whether every declared script resolves at all is
`test_operator_entrypoints.py`'s question, and asking it twice is duplicate coverage. What is
only asked here is the Tier 2 boundary — an entry point is a form of encouragement, and the
production-history load is not something to encourage.
"""

from __future__ import annotations

import importlib
import inspect
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
PYPROJECT = ROOT / "pyproject.toml"

TIER2_COMMANDS = {
    "glasswell-nm-wells": "glasswell.ingest.nm_wells",
    "glasswell-nm-tiles": "glasswell.marts.nm_wells",
}
# `nm_ocd --promote-only` is the ~89-minute, ~24.8M-row production-history load and `nm_dims`
# is its dimension half. Both are Tier 1, both need a named owner authorisation, and neither
# gets a shorter spelling than `python -m`. See docs/runbook-nm-tier2.md.
TIER1_MODULES = ("glasswell.ingest.nm_ocd", "glasswell.ingest.nm_dims")


def declared() -> dict[str, str]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["scripts"]


@pytest.mark.parametrize(("command", "module_path"), sorted(TIER2_COMMANDS.items()))
def test_both_halves_of_the_new_mexico_gate_are_reachable_as_a_command(
    command: str, module_path: str
) -> None:
    """The spine and the map: either one missing leaves New Mexico off the map."""
    assert declared().get(command) == f"{module_path}:main"

    entry = getattr(importlib.import_module(module_path), "main", None)
    parameters = inspect.signature(entry).parameters

    assert next(iter(parameters), None) == "argv"
    assert all(
        parameter.default is not inspect.Parameter.empty for parameter in parameters.values()
    ), "a console_scripts launcher calls the target as main(), with no arguments"


def test_no_console_script_shortens_the_tier_1_production_load() -> None:
    targets = {target.partition(":")[0] for target in declared().values()}

    assert targets.isdisjoint(TIER1_MODULES)
