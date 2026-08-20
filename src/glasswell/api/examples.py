"""The documented request examples, which are also the naked-number harness's input set.

SB-07 §10 check 1 fails an operation with no example, and check 2 calls every operation
with the example it publishes. So the example ids are written down once, here, and the
contract fixture seeds exactly them.
"""

from __future__ import annotations

from typing import Any

KEY_HEADER = "X-Glasswell-Key"
REQUEST_EXAMPLE_KEY = "x-glasswell-request-example"
GLOSSARY_KEY = "x-glasswell-glossary"

EXAMPLE_API10 = "3305301234"
EXAMPLE_MANIFEST_ID = "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
EXAMPLE_DERIVATION_ID = "drv_obqajdni25f25zmxcz7a"
EXAMPLE_RULE_ID = "cr_nd_stream_vocab_1"
EXAMPLE_SOURCE_ID = "nd_mpr_xlsx"
EXAMPLE_QUARANTINE_ID = "qr_01contract0001"
EXAMPLE_TERM_ID = "gt_report_vintage"
EXAMPLE_ERROR_CODE = "lineage_unresolved"
EXAMPLE_TILE = {"layer": "nd_laterals", "z": 8, "x": 54, "y": 89}


def request_example(
    *, path: dict[str, Any] | None = None, query: dict[str, Any] | None = None
) -> dict[str, Any]:
    """`openapi_extra` payload: the parameters a caller (or the harness) can replay."""
    return {REQUEST_EXAMPLE_KEY: {"path": path or {}, "query": query or {}}}
