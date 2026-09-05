#!/usr/bin/env python3
"""Select the tests a working-tree diff can reach, for `make test`.

A local tool, deliberately not a CI one. Measured over the last six merges, the same graph
selected the whole suite on five of them (`work-output/ci-lean/C-ci-shape.md` §4): real branches
here touch two to four migrations and a high-fan-in module, and one edit to
`glasswell.lineage.serialization` reaches almost every test. Per-commit local iteration is the
opposite distribution — 0-1 test files on 8 of 18 commits — which is the case this serves.

Three ways a test is reached, and any of them selects it: it imports a changed module (through
the transitive import graph), it is named `test_<stem>.py` for a changed `src/**/<stem>.py`, or
the change is one this tool refuses to reason about, in which case the whole suite runs. The
unit tier always runs: seven of its files read repository artifacts rather than importing
anything, and at 43 s that is cheaper than deciding which.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "glasswell"
TIERS = ("unit", "integration", "contract")
ALWAYS = "tests/unit"

# A change to any of these is one whose blast radius the graph cannot see: a fixture every tier
# builds on, a dependency set, the harness itself. Each falls back to the whole suite.
FULL_SUITE_PATHS = ("tests/conftest.py", "requirements.lock", "Makefile", "pyproject.toml")
FULL_SUITE_PREFIXES = ("tests/support/", "tests/fixtures/", ".github/workflows/")


def changed_paths(base: str | None) -> list[str]:
    def git(*args: str) -> list[str]:
        out = subprocess.run(
            ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
        ).stdout
        return [line for line in out.splitlines() if line]

    paths = set(git("diff", "--name-only")) | set(git("diff", "--cached", "--name-only"))
    if base is None:
        merge_base = subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "origin/main", "HEAD"],
            capture_output=True,
            text=True,
        )
        base = merge_base.stdout.strip() if merge_base.returncode == 0 else None
    if base:
        paths |= set(git("diff", "--name-only", f"{base}...HEAD"))
    return sorted(paths)


def module_name(path: Path) -> str:
    relative = path.relative_to(ROOT / "src").with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imported_modules(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if alias.name.startswith("glasswell"))
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and (node.module or "").startswith("glasswell")
        ):
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def build_graph() -> tuple[dict[str, set[str]], dict[str, set[str]], set[str]]:
    """Reverse edges over `src/`, reverse edges from test files, and the set of real modules."""
    modules = {module_name(path): path for path in SRC.rglob("*.py")}
    src_importers: dict[str, set[str]] = defaultdict(set)
    test_importers: dict[str, set[str]] = defaultdict(set)

    def edges(name: str, imported: set[str], into: dict[str, set[str]]) -> None:
        for target in imported:
            # `from glasswell.marts import wells` yields both `glasswell.marts` and
            # `glasswell.marts.wells`; only the ones that are modules become edges, and the
            # package edge is kept so a package-level change reaches its importers.
            if target in modules:
                into[target].add(name)
            package = target.rsplit(".", 1)[0]
            if package in modules:
                into[package].add(name)

    for name, path in modules.items():
        edges(name, imported_modules(path), src_importers)
    for tier in TIERS:
        for path in (ROOT / "tests" / tier).rglob("test_*.py"):
            edges(str(path.relative_to(ROOT)), imported_modules(path), test_importers)
    return src_importers, test_importers, set(modules)


def affected_modules(seeds: set[str], src_importers: dict[str, set[str]]) -> set[str]:
    seen, frontier = set(seeds), list(seeds)
    while frontier:
        for importer in src_importers.get(frontier.pop(), ()):
            if importer not in seen:
                seen.add(importer)
                frontier.append(importer)
    return seen


def select(paths: list[str]) -> tuple[list[str], list[str]]:
    """Returns (pytest arguments, the reasons a narrower selection was refused)."""
    reasons: list[str] = []
    seeds: set[str] = set()
    stems: set[str] = set()
    for path in paths:
        if path in FULL_SUITE_PATHS or path.startswith(FULL_SUITE_PREFIXES):
            if path == "pyproject.toml" and not _more_than_the_version(path):
                continue
            reasons.append(f"{path} reaches every tier")
            continue
        if path.startswith("src/glasswell/"):
            if not path.endswith(".py"):
                reasons.append(f"{path} is data the graph cannot read (migrations live here)")
                continue
            seeds.add(module_name(ROOT / path))
            stems.add(Path(path).stem)
        elif path.startswith("tests/"):
            if Path(path).name.startswith("test_") and Path(path).suffix == ".py":
                stems.add("")  # a test file selects itself, handled below
            continue
        # Everything else -- docs, web/, infra/, assets/ -- reaches no Python test by import,
        # and the unit tier that reads repository artifacts runs unconditionally anyway.

    if reasons:
        return ["tests"], reasons

    src_importers, test_importers, _ = build_graph()
    reached = affected_modules(seeds, src_importers)
    selected = {ALWAYS}
    for module in reached:
        selected.update(test_importers.get(module, ()))
    for stem in stems:
        if not stem:
            continue
        for tier in TIERS:
            candidate = ROOT / "tests" / tier / f"test_{stem}.py"
            if candidate.exists():
                selected.add(str(candidate.relative_to(ROOT)))
    selected.update(
        path for path in paths if path.startswith("tests/") and Path(ROOT / path).exists()
    )
    return sorted(selected), reasons


def _more_than_the_version(path: str) -> bool:
    diff = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "HEAD", "--", path], capture_output=True, text=True
    ).stdout
    body = [
        line
        for line in diff.splitlines()
        if line[:1] in "+-" and line[:3] not in ("+++", "---")
    ]
    return any("version" not in line.split("=", 1)[0] for line in body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", help="diff against this ref (default: merge-base origin/main)")
    parser.add_argument(
        "--print", action="store_true", help="write the selection to stdout, one path per line"
    )
    arguments = parser.parse_args(argv)

    paths = changed_paths(arguments.base)
    if not paths:
        print("test-scope: nothing changed; the unit tier alone", file=sys.stderr)
        selection, reasons = [ALWAYS], []
    else:
        selection, reasons = select(paths)

    if reasons:
        print(f"test-scope: whole suite — {'; '.join(sorted(set(reasons)))}", file=sys.stderr)
    else:
        excluded = _tier_files() - set(selection) - {ALWAYS}
        print(
            f"test-scope: {len(paths)} changed file(s) select {len(selection)} target(s);"
            f" {len(excluded)} test file(s) excluded because nothing changed reaches them"
            f" (tests/unit always runs)",
            file=sys.stderr,
        )

    separator = "\n" if arguments.print else " "
    print(separator.join(selection))
    return 0


def _tier_files() -> set[str]:
    return {
        str(path.relative_to(ROOT))
        for tier in TIERS
        for path in (ROOT / "tests" / tier).rglob("test_*.py")
    }


if __name__ == "__main__":
    raise SystemExit(main())
