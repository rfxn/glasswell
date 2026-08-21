#!/usr/bin/env python3
"""Fold changelog.d/ fragments into CHANGELOG.md under a dated Unreleased heading.

    scripts/changelog-assemble.py --title "wave 2 merge train"   # fold, then delete fragments
    scripts/changelog-assemble.py --check                        # fail while fragments pend
    scripts/changelog-assemble.py --dry-run --title "..."        # print the fold, change nothing
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = re.compile(r"^- \[(New|Change|Fix)\] ")


def pending_fragments(directory: Path) -> list[Path]:
    return sorted(path for path in directory.glob("*.md") if path.name != "README.md")


def read_entries(fragment: Path) -> str:
    text = fragment.read_text().strip("\n")
    first = next((line for line in text.splitlines() if line.strip()), "")
    if not ENTRY.match(first):
        raise SystemExit(f"{fragment}: first line must start with '- [New|Change|Fix] '")
    return text


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", default="", help="cycle title for the dated heading")
    parser.add_argument("--check", action="store_true", help="exit 1 while fragments pend")
    parser.add_argument("--dry-run", action="store_true", help="print the fold, change nothing")
    parser.add_argument("--changelog", type=Path, default=ROOT / "CHANGELOG.md")
    parser.add_argument("--fragments", type=Path, default=ROOT / "changelog.d")
    arguments = parser.parse_args()

    fragments = pending_fragments(arguments.fragments)
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
