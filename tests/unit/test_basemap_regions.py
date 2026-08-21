"""The basemap extract's region decides what a reader sees when they zoom out.

An extract narrower than the map's own viewport renders a cropped world — the whole
continent west of the box is simply absent, with no error anywhere to say so. These are
the checks that make that failure a test result rather than a screenshot someone happens
to look at.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
REGIONS = ROOT / "scripts" / "basemap-regions"
BUILD = ROOT / "scripts" / "basemap-build.sh"

# Corners a reader zoomed out over the lower 48 expects to see land at.
CONUS_LANDMARKS = {
    "Cape Mendocino": (-124.4, 40.4),
    "Point Roberts": (-123.0, 49.0),
    "Key West": (-81.8, 24.6),
    "West Quoddy Head": (-67.0, 44.8),
    "Brownsville": (-97.5, 26.0),
    "Memphis": (-90.0, 35.1),
    "Salt Lake City": (-111.9, 40.8),
}


def rings(geometry: dict) -> list[list[list[float]]]:
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"][0]]
    return [polygon[0] for polygon in geometry["coordinates"]]


def bbox(geometry: dict) -> tuple[float, float, float, float]:
    points = [point for ring in rings(geometry) for point in ring]
    lons = [point[0] for point in points]
    lats = [point[1] for point in points]
    return min(lons), min(lats), max(lons), max(lats)


def covers(geometry: dict, lon: float, lat: float) -> bool:
    """Every region in this directory is an axis-aligned box, so a bbox test is exact."""
    for ring in rings(geometry):
        lons = [point[0] for point in ring]
        lats = [point[1] for point in ring]
        if min(lons) <= lon <= max(lons) and min(lats) <= lat <= max(lats):
            return True
    return False


def load(name: str) -> dict:
    return json.loads((REGIONS / f"{name}.geojson").read_text())


@pytest.mark.parametrize("path", sorted(REGIONS.glob("*.geojson")), ids=lambda p: p.stem)
def test_every_region_is_a_well_formed_lon_lat_geometry(path):
    geometry = json.loads(path.read_text())
    assert geometry["type"] in {"Polygon", "MultiPolygon"}
    for ring in rings(geometry):
        assert ring[0] == ring[-1], "a ring has to close"
        for lon, lat in ring:
            assert -180.0 <= lon <= 180.0
            assert -90.0 <= lat <= 90.0


@pytest.mark.parametrize("path", sorted(REGIONS.glob("*.geojson")), ids=lambda p: p.stem)
def test_the_usage_text_names_every_region_that_exists(path):
    usage = subprocess.run(
        ["bash", str(BUILD), "--help"], capture_output=True, text=True, check=True
    ).stdout
    assert path.stem in usage


def test_conus_reaches_all_four_coasts():
    conus = load("conus")
    for name, (lon, lat) in CONUS_LANDMARKS.items():
        assert covers(conus, lon, lat), f"{name} falls outside the conus extract"


def test_conus_contains_every_basin_region_so_a_swap_cannot_lose_coverage():
    conus = load("conus")
    for name in ("nd", "nd-tx"):
        west, south, east, north = bbox(load(name))
        for lon, lat in ((west, south), (east, north), (west, north), (east, south)):
            assert covers(conus, lon, lat), f"{name} escapes conus at {lon},{lat}"


def test_the_basin_regions_do_not_reach_the_coasts_which_is_the_bug_conus_fixes():
    """Pins the defect: nd-tx is why zoom-out ended at the Rockies and at Memphis."""
    nd_tx = load("nd-tx")
    assert not covers(nd_tx, *CONUS_LANDMARKS["Cape Mendocino"])
    assert not covers(nd_tx, *CONUS_LANDMARKS["West Quoddy Head"])
