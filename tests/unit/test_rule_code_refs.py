"""Every `module_function` a conformance rule names has to resolve to something.

R8's citation chain only holds if the thing cited exists: a rule served at
`/v1/conformance/<id>` whose `module_function` points at a symbol nobody wrote is a published
claim a reader cannot check, which is the mirror image of the defect the register exists to
prevent. Two rows shipped naming `glasswell.marts.neighbors:refresh`, which has never been the
name of that function, and nothing in the tree looked.

Fixtureless on purpose. The seeders are Python declarations and resolving one is an import and
a `getattr`, so this collects under `pytest -m unit` and fails before a container is started.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import glasswell.seed

pytestmark = pytest.mark.unit


def rule_specs() -> list[tuple[str, str, str]]:
    """`(module, rule_id, module_function)` for every seeded rule that names one.

    Walked rather than listed: a seeder added later is one this gate has to see without being
    told, which is how two rows got past a list of four.
    """
    found: list[tuple[str, str, str]] = []
    for info in pkgutil.iter_modules(glasswell.seed.__path__):
        if not info.name.startswith("conformance_"):
            continue
        module = importlib.import_module(f"glasswell.seed.{info.name}")
        for value in vars(module).values():
            if not isinstance(value, tuple):
                continue
            for row in value:
                if not isinstance(row, dict) or "rule_id" not in row:
                    continue
                spec = row.get("spec")
                if isinstance(spec, dict) and "module_function" in spec:
                    found.append((info.name, str(row["rule_id"]), str(spec["module_function"])))
    return sorted(set(found))


def superseded_rule_ids() -> set[str]:
    """Every rule id some other seeded rule declares it supersedes."""
    found: set[str] = set()
    for info in pkgutil.iter_modules(glasswell.seed.__path__):
        if not info.name.startswith("conformance_"):
            continue
        module = importlib.import_module(f"glasswell.seed.{info.name}")
        for value in vars(module).values():
            if not isinstance(value, tuple):
                continue
            for row in value:
                if isinstance(row, dict) and row.get("supersedes_rule_id"):
                    found.add(str(row["supersedes_rule_id"]))
    return found


SPECS = rule_specs()
# A rule a successor supersedes is history: it stays served at `/v1/conformance/<id>` and the
# derivations that cite it go on citing what shaped them, but what has to resolve is what is in
# force. There is no exception list and deliberately no way to write one -- the only thing that
# takes a row out of this gate is an appended successor, which is a row with a rationale and a
# date, and which the last test below holds to resolving itself.
SUPERSEDED = superseded_rule_ids()
LIVE = [item for item in SPECS if item[1] not in SUPERSEDED]


def test_the_walk_finds_the_rules_it_is_meant_to_guard() -> None:
    """A gate that collected nothing would pass over anything."""
    assert len(SPECS) >= 38
    named = {rule_id for _, rule_id, _ in SPECS}
    assert {"cr_nd_neighbors_scope_1", "cr_mt_neighbors_scope_1"} <= named
    # The skip is narrow: a supersession takes one row out, not a tier of them.
    assert len(LIVE) >= len(SPECS) - 10


@pytest.mark.parametrize(
    ("seeder", "rule_id", "reference"), LIVE, ids=[item[1] for item in LIVE]
)
def test_every_module_function_a_rule_names_resolves(
    seeder: str, rule_id: str, reference: str
) -> None:
    module_name, separator, symbol = reference.partition(":")

    assert separator, f"{rule_id}: {reference!r} names no symbol"
    assert module_name.startswith("glasswell."), f"{rule_id}: {module_name} is not ours"
    module = importlib.import_module(module_name)
    assert hasattr(module, symbol), (
        f"{rule_id} ({seeder}) cites {reference}, and {module_name} has no {symbol}"
    )


def test_a_supersession_cannot_be_used_to_hide_an_unresolvable_successor() -> None:
    """The one way past this gate is an appended successor, so the successor is held to the
    thing its ancestor failed: a `_2` naming a symbol that does not exist would otherwise
    retire its `_1` and inherit the silence."""
    by_id = {rule_id: reference for _, rule_id, reference in SPECS}
    families = {item.rpartition("_")[0] for item in SUPERSEDED}
    successors = {
        rule_id
        for _, rule_id, _ in SPECS
        if rule_id not in SUPERSEDED and rule_id.rpartition("_")[0] in families
    }

    assert successors, "no successor row exists; this check would be vacuous"
    for rule_id in successors:
        module_name, _, symbol = by_id[rule_id].partition(":")
        assert hasattr(importlib.import_module(module_name), symbol), rule_id
