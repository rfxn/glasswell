"""SB-08 §2.6, from the other side: the parameter the card emits, issued against the API.

`bridge.test.ts` already holds `TARGETS` to the committed document — but only that the named
parameter *exists*, which a name search handed an API-10 satisfies while returning nothing. The
crossing shipped broken under a green suite because no test ever asked the parameter to answer.
This file asks. It reads the same declaration the browser ships and issues it, so a filter that
cannot match the identity it is handed fails here rather than on a reader's screen.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10

BRIDGE = Path(__file__).resolve().parents[2] / "web" / "src" / "explore" / "bridge.ts"

_ENTRY = re.compile(r"^\s*(?P<name>\w+):\s*\{(?P<body>[^}]*)\},\s*$", re.MULTILINE)
_FILTER = re.compile(r"""filter:\s*(?:"(?P<filter>[^"]+)"|null)""")


def crossing_targets() -> dict[str, str | None]:
    """`TARGETS` in `bridge.ts`, as a mapping of crossing name to the parameter it narrows by."""
    source = BRIDGE.read_text(encoding="utf-8")
    table = source.split("export const TARGETS", 1)
    if len(table) != 2:
        raise AssertionError(f"{BRIDGE} declares no TARGETS table to check")
    body = table[1].split("};", 1)[0]
    found = {}
    for entry in _ENTRY.finditer(body):
        filter_match = _FILTER.search(entry["body"])
        if filter_match is None:
            raise AssertionError(f"crossing {entry['name']!r} declares no filter")
        found[entry["name"]] = filter_match["filter"]
    return found


def test_the_declaration_this_file_reads_is_the_one_the_browser_ships() -> None:
    """A parser that quietly found nothing would make every assertion below vacuous."""
    targets = crossing_targets()

    assert set(targets) == {"wells", "production", "vintages"}
    assert targets["vintages"] is None


def test_the_parameter_the_well_card_emits_returns_the_well_it_was_built_from(
    client: TestClient,
) -> None:
    """The owner-reported defect, stated as the property it broke: `Rows for this well` builds
    its link from an API-10, so whatever parameter it puts that API-10 into has to answer with
    that well. Under `f.q` it answered with nothing for every well ever built."""
    narrows_by = crossing_targets()["wells"]
    assert narrows_by is not None

    found = client.get("/v1/wells", params={narrows_by: EXAMPLE_API10}).json()["data"]

    assert [item["api10"] for item in found] == [EXAMPLE_API10]
