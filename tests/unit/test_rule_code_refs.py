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


# Three rules published before this gate existed name a symbol that has since been renamed.
# They are not corrected in place: all three are on applied migrations and
# `lineage.conformance_rules` is append-only, so the correction is an appended successor rule
# and a repoint of everything citing it -- the shape `cr_mt_paths_length_scope_2` took -- not an
# edit to a row a deployed database already holds. Named with the symbol each one meant, so
# whoever appends the successor is not re-deriving it. Routed to the owner (gate-seam H-1).
PUBLISHED_BEFORE_THIS_GATE = {
    # glasswell.ingest.eia_boundaries:_promote_plays -> :_promote
    "cr_eia_basin_link_1",
    "cr_eia_geometry_repair_1",
    # glasswell.ingest.nm_wells:promote -> :promote_headers
    "cr_nm_wellhistory_header_precedence_1",
}

SPECS = rule_specs()
LIVE = [item for item in SPECS if item[1] not in PUBLISHED_BEFORE_THIS_GATE]


def test_the_walk_finds_the_rules_it_is_meant_to_guard() -> None:
    """A gate that collected nothing would pass over anything."""
    assert len(SPECS) >= 38
    named = {rule_id for _, rule_id, _ in SPECS}
    assert {"cr_nd_neighbors_scope_1", "cr_mt_neighbors_scope_1"} <= named


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


def test_the_carried_exceptions_are_still_the_only_ones_and_still_broken() -> None:
    """An allowlist nothing matches is a hole. Each of the three has to still be unresolvable,
    or it has been corrected and belongs back under the gate."""
    by_id = {rule_id: reference for _, rule_id, reference in SPECS}

    assert set(by_id) >= PUBLISHED_BEFORE_THIS_GATE
    for rule_id in PUBLISHED_BEFORE_THIS_GATE:
        module_name, _, symbol = by_id[rule_id].partition(":")
        module = importlib.import_module(module_name)
        assert not hasattr(module, symbol), (
            f"{rule_id} resolves now; drop it from PUBLISHED_BEFORE_THIS_GATE"
        )
