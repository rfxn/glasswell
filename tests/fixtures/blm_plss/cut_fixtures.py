"""Cut the checked-in BLM CadNSDI PLSS fixtures from the live service.

    python tests/fixtures/blm_plss/cut_fixtures.py

Record selection only: no attribute value is edited, and the layer-metadata documents are
stored verbatim because the paginator reads its paging contract from them.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import httpx

SERVICE_URL = (
    "https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI_NAD83/MapServer"
)
TOWNSHIPS = ("ND051520N0950W0", "ND051530N0950W0")
SECTIONS = ("1", "2", "13", "36")
HERE = Path(__file__).resolve().parent


def _write(path: Path, content: bytes) -> None:
    path.write_bytes(content)
    print(f"{path.name}: {len(content)} bytes")


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    plssids = ", ".join(f"'{plssid}'" for plssid in TOWNSHIPS)
    divisions = ", ".join(f"'{number}'" for number in SECTIONS)
    with httpx.Client(timeout=60.0) as client:
        for layer in (1, 2):
            _write(
                HERE / f"layer_{layer}.json",
                client.get(f"{SERVICE_URL}/{layer}", params={"f": "json"}).content,
            )
        _write(
            HERE / "nd_townships.geojson",
            client.get(
                f"{SERVICE_URL}/1/query",
                params={
                    "where": f"PLSSID IN ({plssids})",
                    "outFields": "*",
                    "orderByFields": "OBJECTID ASC",
                    "f": "geojson",
                },
            ).content,
        )
        _write(
            HERE / "nd_sections.geojson",
            client.get(
                f"{SERVICE_URL}/2/query",
                params={
                    "where": f"PLSSID IN ({plssids}) AND FRSTDIVNO IN ({divisions})",
                    "outFields": "*",
                    "orderByFields": "OBJECTID ASC",
                    "f": "geojson",
                },
            ).content,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
