#!/usr/bin/env python3
"""Rewrite the committed OpenAPI snapshot from the served document.

The byte-equality gate compares the file to `json.dumps(document, indent=2, sort_keys=True)`
plus a trailing newline, so that rendering is written down once — here — rather than in
whichever scratch script an agent reaches for next (CADENCE N-3). Regenerating touches no
database: the document comes from the app object, not from a request.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from glasswell.api import create_app

SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "tests" / "contract" / "openapi_snapshot.json"


def rendered() -> str:
    return json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate the committed OpenAPI snapshot.")
    parser.add_argument(
        "target",
        nargs="?",
        type=Path,
        default=SNAPSHOT_PATH,
        help=f"file to write (default: {SNAPSHOT_PATH})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report whether the target is current and write nothing",
    )
    arguments = parser.parse_args(argv)

    document = rendered()
    if arguments.check:
        committed = (
            arguments.target.read_text(encoding="utf-8") if arguments.target.exists() else ""
        )
        if committed == document:
            print(f"{arguments.target}: current")
            return 0
        print(f"{arguments.target}: stale — run scripts/regen-snapshot.py to rewrite it")
        return 1

    arguments.target.write_text(document, encoding="utf-8")
    print(f"{arguments.target}: {len(document.splitlines())} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
