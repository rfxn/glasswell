"""A router may borrow a name another router owns, and never one it is only passing on.

`api/routers/jurisdictions.py` read `NEIGHBORS_SCOPE` from `api/routers/wells.py` when
`lineage/jurisdictions.py` defines it and every other consumer reads it there. Nothing was
served wrongly, but the router layer had become a route to a definition it does not own: a
circular-import hazard, and a second place to look when the name moves. Routers share plenty of
names they genuinely define; what this refuses is the borrowed one passed along.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROUTERS = Path(__file__).resolve().parents[2] / "src" / "glasswell" / "api" / "routers"
PREFIX = "glasswell.api.routers."


def module_tree(name: str) -> ast.Module:
    return ast.parse((ROUTERS / f"{name}.py").read_text(encoding="utf-8"))


def names_defined_in(tree: ast.Module) -> set[str]:
    """Bound by this module itself: assignments, functions and classes, never imports."""
    defined: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            defined.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
    return defined


def borrowed_imports() -> list[tuple[str, str, str]]:
    """(importer, source router, name) for every router-to-router import in the package."""
    found: list[tuple[str, str, str]] = []
    for path in sorted(ROUTERS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(PREFIX):
                source = (node.module or "").removeprefix(PREFIX)
                found.extend((path.stem, source, alias.name) for alias in node.names)
    return found


def test_no_router_reads_a_name_another_router_only_passes_on() -> None:
    borrowed = borrowed_imports()

    assert borrowed, "no router imports another; this guard would be vacuous"
    relayed = sorted(
        f"{importer} reads {name} from {source}, which does not define it"
        for importer, source, name in borrowed
        if name not in names_defined_in(module_tree(source))
    )

    assert relayed == []
