"""Measured proof that EPSG:5070 discovery cannot drop an in-domain v0 edge.

The zone envelope is the same question one layer up: the tuple Python holds and the CHECK the
migration writes are two spellings of one measurement, and the refresh binds a state tuple
rather than a literal. Neither needs a database to read.
"""

from __future__ import annotations

import math

import pytest
from pyproj import Transformer

from glasswell.db.migrate import discover_migrations
from glasswell.marts import neighbors
from glasswell.marts.neighbors import (
    CANDIDATE_EPSG,
    CANDIDATE_PAD,
    EAST_EPSG,
    MAX_RADIUS_M,
    SUPPORTED_LATITUDE_MAX,
    SUPPORTED_LATITUDE_MIN,
    SUPPORTED_LONGITUDE_MAX,
    SUPPORTED_LONGITUDE_MIN,
    SUPPORTED_ZONE_EPSGS,
    UTM_BOUNDARY_LONGITUDE,
    WEST_EPSG,
    utm_zone_epsg,
)
from glasswell.seed.jurisdictions import PREFIXES

pytestmark = pytest.mark.unit


def _linspace(start: float, stop: float, intervals: int) -> list[float]:
    step = (stop - start) / intervals
    return [start + step * index for index in range(intervals + 1)]


def _transform_selected(
    longitudes: list[float], latitudes: list[float], zones: list[int]
) -> tuple[list[float], list[float]]:
    eastings = [0.0] * len(longitudes)
    northings = [0.0] * len(longitudes)
    for zone in sorted(set(zones)):
        indexes = [index for index, selected in enumerate(zones) if selected == zone]
        transformer = Transformer.from_crs(4326, zone, always_xy=True)
        x_values, y_values = transformer.transform(
            [longitudes[index] for index in indexes],
            [latitudes[index] for index in indexes],
        )
        for index, x_value, y_value in zip(indexes, x_values, y_values, strict=True):
            eastings[index] = x_value
            northings[index] = y_value
    return eastings, northings


# Imported, never reimplemented: a second copy of the zone rule in the proof of the zone rule
# is how the two stop agreeing without either one looking wrong.
_zone_for_midpoint = utm_zone_epsg


def test_two_percent_candidate_pad_has_no_false_negative_in_supported_domain() -> None:
    boundary = float(UTM_BOUNDARY_LONGITUDE)
    longitudes = _linspace(float(SUPPORTED_LONGITUDE_MIN), boundary - 0.10, 14)
    longitudes.extend([boundary - 0.05, boundary, boundary + 0.05])
    longitudes.extend(
        _linspace(boundary + 0.10, float(SUPPORTED_LONGITUDE_MAX), 14)
    )
    latitudes = _linspace(float(SUPPORTED_LATITUDE_MIN), float(SUPPORTED_LATITUDE_MAX), 7)
    bearings = [index * 7.5 for index in range(48)]
    origins = [
        (longitude, latitude, bearing)
        for longitude in longitudes
        for latitude in latitudes
        for bearing in bearings
    ]
    assert len(origins) == 12_672

    origin_longitudes = [item[0] for item in origins]
    origin_latitudes = [item[1] for item in origins]
    seed_zones = [_zone_for_midpoint(longitude) for longitude in origin_longitudes]
    origin_x, origin_y = _transform_selected(origin_longitudes, origin_latitudes, seed_zones)
    radius_m = float(MAX_RADIUS_M)
    endpoint_x = [
        x_value + radius_m * math.sin(math.radians(item[2]))
        for x_value, item in zip(origin_x, origins, strict=True)
    ]
    endpoint_y = [
        y_value + radius_m * math.cos(math.radians(item[2]))
        for y_value, item in zip(origin_y, origins, strict=True)
    ]
    endpoint_longitudes = [0.0] * len(origins)
    endpoint_latitudes = [0.0] * len(origins)
    for zone in sorted(set(seed_zones)):
        indexes = [index for index, selected in enumerate(seed_zones) if selected == zone]
        transformer = Transformer.from_crs(zone, 4326, always_xy=True)
        lon_values, lat_values = transformer.transform(
            [endpoint_x[index] for index in indexes],
            [endpoint_y[index] for index in indexes],
        )
        for index, longitude, latitude in zip(
            indexes, lon_values, lat_values, strict=True
        ):
            endpoint_longitudes[index] = longitude
            endpoint_latitudes[index] = latitude

    candidate = Transformer.from_crs(4326, CANDIDATE_EPSG, always_xy=True)
    origin_candidate_x, origin_candidate_y = candidate.transform(
        origin_longitudes, origin_latitudes
    )
    endpoint_candidate_x, endpoint_candidate_y = candidate.transform(
        endpoint_longitudes, endpoint_latitudes
    )
    candidate_distances = [
        math.hypot(end_x - start_x, end_y - start_y)
        for start_x, start_y, end_x, end_y in zip(
            origin_candidate_x,
            origin_candidate_y,
            endpoint_candidate_x,
            endpoint_candidate_y,
            strict=True,
        )
    ]
    midpoint_x = [
        (start + end) / 2
        for start, end in zip(origin_candidate_x, endpoint_candidate_x, strict=True)
    ]
    midpoint_y = [
        (start + end) / 2
        for start, end in zip(origin_candidate_y, endpoint_candidate_y, strict=True)
    ]
    midpoint_longitudes, _ = Transformer.from_crs(
        CANDIDATE_EPSG, 4326, always_xy=True
    ).transform(midpoint_x, midpoint_y)
    final_zones = [_zone_for_midpoint(longitude) for longitude in midpoint_longitudes]
    final_origin_x, final_origin_y = _transform_selected(
        origin_longitudes, origin_latitudes, final_zones
    )
    final_endpoint_x, final_endpoint_y = _transform_selected(
        endpoint_longitudes, endpoint_latitudes, final_zones
    )
    final_distances = [
        math.hypot(end_x - start_x, end_y - start_y)
        for start_x, start_y, end_x, end_y in zip(
            final_origin_x,
            final_origin_y,
            final_endpoint_x,
            final_endpoint_y,
            strict=True,
        )
    ]

    false_negatives = [
        index
        for index, (candidate_distance, final_distance) in enumerate(
            zip(candidate_distances, final_distances, strict=True)
        )
        if final_distance <= radius_m
        and candidate_distance > radius_m * float(CANDIDATE_PAD)
    ]
    ratios = [
        candidate_distance / final_distance
        for candidate_distance, final_distance in zip(
            candidate_distances, final_distances, strict=True
        )
    ]
    boundary_straddles = sum(
        (origin - boundary) * (endpoint - boundary) < 0
        for origin, endpoint in zip(
            origin_longitudes, endpoint_longitudes, strict=True
        )
    )
    zone_switches = sum(
        seed != final for seed, final in zip(seed_zones, final_zones, strict=True)
    )

    assert false_negatives == []
    assert max(ratios) < 1.014 < float(CANDIDATE_PAD)
    assert set(final_zones) <= set(SUPPORTED_ZONE_EPSGS)
    assert len(set(final_zones)) > 1, "the domain must exercise more than one zone"
    assert {WEST_EPSG, EAST_EPSG} <= set(final_zones)
    assert boundary_straddles > 0
    assert zone_switches > 0
    assert _zone_for_midpoint(boundary) == EAST_EPSG


def test_the_refresh_binds_a_state_tuple_rather_than_a_literal() -> None:
    """The seam is a bind, not a literal. Which jurisdictions fill it is two registrations
    now -- `neighbors_available` and a serving `neighbors_scope` rule -- rather than a tuple
    pinned here, so this asserts the binding and leaves the membership to the registry."""
    assert "%(state_code)s" not in neighbors._COMPONENTS
    assert "any(%(state_codes)s)" in neighbors._COMPONENTS
    assert set(neighbors.STATE_CODES) <= PREFIXES


def test_the_python_envelope_and_the_migration_constraint_name_the_same_zones() -> None:
    """R-7. The zone set is a tuple in Python and a CHECK in 066; two spellings of one
    measurement drift the first time one of them is widened alone."""
    body = next(
        item.sql for item in discover_migrations() if item.name == "neighbors_multistate"
    )
    declared = ", ".join(str(epsg) for epsg in neighbors.SUPPORTED_ZONE_EPSGS)

    assert f"distance_epsg in ({declared})" in body
    assert str(neighbors.SUPPORTED_LONGITUDE_MIN) in body
    assert str(neighbors.SUPPORTED_LONGITUDE_MAX) in body
