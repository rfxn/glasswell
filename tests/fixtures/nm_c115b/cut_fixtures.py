"""Cut the checked-in NM OCD C-115B fixtures from the live service.

    python tests/fixtures/nm_c115b/cut_fixtures.py

Record selection only: no attribute value is edited, and the layer-metadata document is
stored verbatim because the paginator reads its paging contract from it.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import httpx

SERVICE_URL = (
    "https://gis.emnrd.nm.gov/arcgis/rest/services/OCDPUB/C115B_NaturalGasWaste/FeatureServer"
)
LAYER_ID = 0
# Two wells in two counties whose rows between them carry both waste types, three reporting
# periods, and a duplicate (api10, period, waste_type) key the service really publishes.
WELLS = ("30-015-54573", "30-045-38469")
OUT_SR = "4269"
USER_AGENT = "glasswell (data platform; ryan@rfxn.com)"
HERE = Path(__file__).resolve().parent


def _write(path: Path, content: bytes) -> None:
    path.write_bytes(content)
    print(f"{path.name}: {len(content)} bytes")


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    wells = ", ".join(f"'{api}'" for api in WELLS)
    with httpx.Client(timeout=60.0, headers={"User-Agent": USER_AGENT}) as client:
        _write(
            HERE / f"layer_{LAYER_ID}.json",
            client.get(f"{SERVICE_URL}/{LAYER_ID}", params={"f": "json"}).content,
        )
        _write(
            HERE / "upstream_by_well.geojson",
            client.get(
                f"{SERVICE_URL}/{LAYER_ID}/query",
                params={
                    "where": f"id IN ({wells})",
                    "outFields": "*",
                    "orderByFields": "OBJECTID ASC",
                    "outSR": OUT_SR,
                    "f": "geojson",
                },
            ).content,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
