#!/usr/bin/env python3
"""Fold changelog.d/ fragments into CHANGELOG.md under a dated Unreleased heading.

    scripts/changelog-assemble.py --title "wave 2 merge train"   # fold, then delete fragments
    scripts/changelog-assemble.py --check                        # fail while fragments pend
    scripts/changelog-assemble.py --lint                         # grammar-check every fragment
    scripts/changelog-assemble.py --dry-run --title "..."        # print the fold, change nothing
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_GRAMMAR = None


def grammar():
    """scripts/render-changelog.py owns the one changelog grammar; this file borrows it.

    Restating the grammar here is what let gate-rel B1 happen: the fold and the page have to be
    the same rules, or a fragment is admitted by one and refused by the other — and by then the
    tag is cut.
    """
    global _GRAMMAR
    if _GRAMMAR is not None:
        return _GRAMMAR
    path = ROOT / "scripts" / "render-changelog.py"
    spec = importlib.util.spec_from_file_location("render_changelog", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"{path}: cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    # No bytecode: importing by path writes scripts/__pycache__, and release.py's preconditions
    # are about to assert this tree is clean.
    written, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = written
    _GRAMMAR = module
    return _GRAMMAR


# Re-exported so callers can name the tags without loading the renderer; the renderer's own
# tuple is the source of truth and tests hold the two together.
TAGS = ("New", "Change", "Fix", "Remove")


def pending_fragments(directory: Path) -> list[Path]:
    return sorted(path for path in directory.glob("*.md") if path.name != "README.md")


def read_entries(fragment: Path) -> str:
    """Every line, not only the first (gate-rel B1). Raises the page's own `Refused`."""
    return grammar().check_fragment(fragment)


def fold(changelog: Path, fragments: list[Path], title: str) -> str:
    lines = changelog.read_text().splitlines()
    try:
        unreleased = lines.index("## Unreleased")
    except ValueError:
        raise SystemExit(f"{changelog}: no '## Unreleased' heading") from None
    heading = f"### {date.today().isoformat()} — {title}"
    body = "\n".join(read_entries(fragment) for fragment in fragments).splitlines()
    if heading in lines:
        start = lines.index(heading)
        end = next(
            (i for i in range(start + 1, len(lines)) if lines[i].startswith(("### ", "## "))),
            len(lines),
        )
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        lines[end:end] = body
    else:
        lines[unreleased + 1 : unreleased + 1] = ["", heading, "", *body]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", default="", help="cycle title for the dated heading")
    parser.add_argument("--check", action="store_true", help="exit 1 while fragments pend")
    parser.add_argument("--lint", action="store_true", help="grammar-check every fragment")
    parser.add_argument("--dry-run", action="store_true", help="print the fold, change nothing")
    parser.add_argument("--changelog", type=Path, default=ROOT / "CHANGELOG.md")
    parser.add_argument("--fragments", type=Path, default=ROOT / "changelog.d")
    arguments = parser.parse_args(argv)

    fragments = pending_fragments(arguments.fragments)
    if arguments.lint:
        for fragment in fragments:
            read_entries(fragment)
        print(f"{len(fragments)} fragment(s) parse against the changelog grammar")
        return 0
    if arguments.check:
        for fragment in fragments:
            shown = fragment.relative_to(ROOT) if fragment.is_relative_to(ROOT) else fragment
            print(f"pending: {shown}")
        return 1 if fragments else 0
    if not fragments:
        print("changelog.d is empty — nothing to fold")
        return 0
    if not arguments.title:
        raise SystemExit("--title is required to fold fragments")

    folded = fold(arguments.changelog, fragments, arguments.title)
    if arguments.dry_run:
        next_section = folded.find("\n## ", folded.index("## Unreleased") + 1)
        print(folded[: next_section if next_section != -1 else len(folded)])
        return 0
    arguments.changelog.write_text(folded)
    for fragment in fragments:
        fragment.unlink()
    print(f"folded {len(fragments)} fragment(s) into {arguments.changelog.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # dry-run output piped to head is normal usage
        sys.exit(0)
