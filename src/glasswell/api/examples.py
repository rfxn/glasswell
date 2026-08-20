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

EXAMPLE_API10 = "3305310451"
EXAMPLE_MANIFEST_ID = "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
EXAMPLE_DERIVATION_ID = "drv_obqajdni25f25zmxcz7a"

CONTENT_ADDRESS_NOTE = (
    " The example id is the contract fixture's. `drv_`, `man_` and `qr_` ids are content"
    " addresses over bytes and run parameters, so they differ per deployment by construction"
    " — take a live one from the `d` handle on any served figure, or from `/v1/manifests`."
)
VINTAGE_ID_NOTE = (
    " The example id is the contract fixture's. A vintage id is `vin_<source_id>_<date>`,"
    " where the date is a knowledge date this deployment actually promoted — it is composed,"
    " not addressed, so list `/v1/vintages` and take one rather than building it."
)
EXAMPLE_RULE_ID = "cr_nd_stream_vocab_1"
EXAMPLE_SOURCE_ID = "nd_mpr_xlsx"
EXAMPLE_VINTAGE_ID = "vin_nd_mpr_xlsx_2026-08-01"
EXAMPLE_QUARANTINE_ID = "qr_01contract0001"
EXAMPLE_TERM_ID = "gt_report_vintage"
EXAMPLE_ERROR_CODE = "lineage_unresolved"
EXAMPLE_TILE = {"layer": "nd_laterals", "z": 8, "x": 54, "y": 89}


def request_example(
    *, path: dict[str, Any] | None = None, query: dict[str, Any] | None = None
) -> dict[str, Any]:
    """`openapi_extra` payload: the parameters a caller (or the harness) can replay."""
    return {REQUEST_EXAMPLE_KEY: {"path": path or {}, "query": query or {}}}
