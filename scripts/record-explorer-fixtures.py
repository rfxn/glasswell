#!/usr/bin/env python3
"""Record the three Explorer fixture modules from a locally served branch.

Start the tracked branch harness first, then run this recorder against the URL and key file it
prints. Request ids are deliberately normalized because they are D3 envelope metadata, not part
of the API shape these fixtures pin.

    GW_PORT=8130 GW_KEY_FILE=/tmp/gw-serve/owner.key make serve-branch
    GW_BASE=http://127.0.0.1:8130 GW_KEY_FILE=/tmp/gw-serve/owner.key \
      .venv/bin/python scripts/record-explorer-fixtures.py
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("GW_BASE", "http://127.0.0.1:8130").rstrip("/")
PARSED_BASE = urlsplit(BASE)
if (
    PARSED_BASE.scheme != "http"
    or PARSED_BASE.hostname not in {"127.0.0.1", "localhost", "::1"}
    or PARSED_BASE.username is not None
    or PARSED_BASE.password is not None
):
    raise SystemExit("GW_BASE must be an unauthenticated loopback HTTP URL")
KEY = Path(os.environ.get("GW_KEY_FILE", "/tmp/gw-serve/owner.key")).read_text().strip()
STABLE_REQUEST_ID = "0" * 26

WELL = "3305310451"
POOLED_WELL = "3305302532"
DRY_WELL = "3305300003"
QUARANTINE_ROW = "qr_01explorer0059"
RULE = "cr_nd_stream_vocab_1"
MANIFEST = "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
VINTAGE = "vin_nd_gis_wells_2026-08-01"
DERIVATION = "drv_obqajdni25f25zmxcz7a"

COLLECTIONS = (
    ("wellsEnvelope", "list_wells", "/v1/wells?limit=8"),
    ("quarantineEnvelope", "list_quarantine", "/v1/quarantine?limit=10"),
    ("conformanceEnvelope", "list_conformance_rules", "/v1/conformance?limit=6"),
    ("manifestsEnvelope", "list_manifests", "/v1/manifests?limit=6"),
    ("derivationsEnvelope", "list_derivations", "/v1/derivations?limit=6"),
    ("vintagesEnvelope", "list_vintages", "/v1/vintages"),
    ("glossaryEnvelope", "list_glossary_terms", "/v1/glossary?limit=6"),
    ("healthEnvelope", "get_health", "/v1/health"),
    ("serviceIndexEnvelope", "get_service_index", "/v1"),
    ("quarantineSummaryEnvelope", "get_quarantine_summary", "/v1/quarantine/summary"),
    (
        "pooledProductionEnvelope",
        "get_well_production_pools",
        f"/v1/wells/{POOLED_WELL}/production/pools",
    ),
    ("emptyProductionEnvelope", "get_well_production", f"/v1/wells/{DRY_WELL}/production"),
    ("pagedQuarantineEnvelope", "list_quarantine", "/v1/quarantine?limit=2"),
)

DETAILS = (
    ("quarantineDetailEnvelope", "get_quarantine_row", f"/v1/quarantine/{QUARANTINE_ROW}"),
    ("conformanceRuleEnvelope", "get_conformance_rule", f"/v1/conformance/{RULE}"),
    ("manifestEnvelope", "get_manifest", f"/v1/manifests/{MANIFEST}"),
    ("vintageEnvelope", "get_vintage", f"/v1/vintages/{VINTAGE}"),
    ("derivationEnvelope", "get_derivation", f"/v1/derivations/{DERIVATION}"),
    ("wellDetailEnvelope", "get_well", f"/v1/wells/{WELL}"),
    ("glossaryTermEnvelope", "get_glossary_term", "/v1/glossary/gt_analog"),
)

COLLECTION_HEADER = '''// Recorded from the tracked `tests/support/serve_branch.py` harness by
// `scripts/record-explorer-fixtures.py`. Request ids are normalized because they are volatile
// D3 envelope metadata; every other value is the locally served branch response.
//
//   GW_PORT=8130 GW_KEY_FILE=/tmp/gw-serve/owner.key make serve-branch
//   GW_BASE=http://127.0.0.1:8130 GW_KEY_FILE=/tmp/gw-serve/owner.key \\
//     .venv/bin/python scripts/record-explorer-fixtures.py
//
// The owner key travels only in the request header and the recorder refuses to write it.

export { productionEnvelope } from "../test/fixtures.ts";
'''

DETAIL_HEADER = '''// Recorded from the tracked `tests/support/serve_branch.py` harness by
// `scripts/record-explorer-fixtures.py`. Request ids are normalized because they are volatile
// D3 envelope metadata; every other value is the locally served branch response.
//
// Collection and detail fixtures come from the same seeded database, so each detail id names
// the exact row carried by the collection fixture. The owner key is never written.
'''

GLOSSARY_HEADER = '''// Recorded from the tracked `tests/support/serve_branch.py` harness by
// `scripts/record-explorer-fixtures.py`, not hand-written from the router source.
//
// Every glossary term the served document binds to a parameter is keyed by the path the pane's
// `explain()` reads. Request ids are normalized D3 metadata; the owner key is never written.
'''


def get(path: str) -> dict[str, Any]:
    request = urllib.request.Request(f"{BASE}{path}", headers={"X-Glasswell-Key": KEY})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def normalize(node: Any) -> Any:
    if isinstance(node, Mapping):
        return {
            key: STABLE_REQUEST_ID if key == "request_id" else normalize(value)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [normalize(value) for value in node]
    return node


def rendered(body: Any) -> str:
    text = json.dumps(normalize(body), indent=2, sort_keys=True, ensure_ascii=False)
    if KEY in text:
        raise SystemExit("the owner key reached a recorded body; refusing to write")
    return text


def write_envelopes(
    destination: Path,
    header: str,
    recordings: tuple[tuple[str, str, str], ...],
) -> None:
    parts = [header]
    for name, operation, path in recordings:
        parts.append(
            f"\n/** `GET {path}` — {operation}. */\n"
            f"export const {name} = {rendered(get(path))};\n"
        )
    destination.write_text("".join(parts), encoding="utf-8")


def bound_terms(document: dict[str, Any]) -> list[str]:
    found: set[str] = set()
    for path_item in document.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, Mapping):
                continue
            for entry in (operation.get("x-glasswell-semantics") or {}).values():
                term = entry.get("x-glasswell-glossary")
                if isinstance(term, str):
                    found.add(term)
    return sorted(found)


def write_glossary() -> None:
    terms = bound_terms(get("/openapi.json"))
    if not terms:
        raise SystemExit("the served document binds no parameter to a glossary term")
    bodies = {f"/v1/glossary/{term}": get(f"/v1/glossary/{term}") for term in terms}
    destination = ROOT / "web" / "src" / "explore" / "api" / "fixtures.ts"
    destination.write_text(
        f"{GLOSSARY_HEADER}\n"
        f"export const glossaryBodies: Record<string, unknown> = {rendered(bodies)};\n",
        encoding="utf-8",
    )


def main() -> None:
    write_envelopes(
        ROOT / "web" / "src" / "explore" / "fixtures.ts",
        COLLECTION_HEADER,
        COLLECTIONS,
    )
    write_envelopes(
        ROOT / "web" / "src" / "explore" / "detail" / "fixtures.ts",
        DETAIL_HEADER,
        DETAILS,
    )
    write_glossary()
    print("recorded Explorer collection, detail and glossary fixtures")


if __name__ == "__main__":
    main()
