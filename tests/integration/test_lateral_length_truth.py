"""A3-F1: the served lateral length is geodesic, and it is checked against a second library.

`ST_Length(geom::geography)` is the claim; `pyproj.Geod` is an independent implementation of
the same measurement. The bound between them is what the conformance rule states, so this
file is where that number is kept honest.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from pyproj import Geod

from glasswell.ingest.nd_gis import load_laterals, load_wells
from glasswell.lengths import resolve_length_method
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts import refresh_for
from glasswell.seed import seed_all
from glasswell.units import METRES_PER_FOOT
from tests.integration.test_marts_nd import ARCHIVES, client_for, rows, scalar

SUPERSEDED_EPSG = 32614
# The rule's stated agreement with an independent geodesic, in feet. The VM's 100-lateral
# sample spanning 104.01W-100.97W measured 8e-8 ft; the fixture worst case is 3e-8 ft.
# ST_AsGeoJSON needs its full 15 digits here: the 9-digit default rounds each vertex by
# ~0.1 mm, which accumulates to 1e-4 ft over a 33-vertex trace and hides the real agreement.
GEODESIC_AGREEMENT_FT = 1e-6
GEOD = Geod(ellps="WGS84")


@pytest.fixture
def laterals_loaded(db: psycopg.Connection, raw_root: Path, lineage_env) -> psycopg.Connection:
    seed_all(db)
    db.commit()
    for layer, loader in (("wells", load_wells), ("laterals", load_laterals)):
        with lineage_session(
            recorder=PostgresRecorder(db), environment=lineage_env
        ), client_for(ARCHIVES[layer]) as client:
            loader(db, raw_root=raw_root, client=client)
        db.commit()
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        refresh_for(db, "ND")
    db.commit()
    return db


def geodesic_feet(geojson: str) -> float:
    """A traverse over the vertices, computed by pyproj rather than by PostGIS."""
    coordinates = json.loads(geojson)["coordinates"]
    metres = sum(
        GEOD.inv(*coordinates[index], *coordinates[index + 1])[2]
        for index in range(len(coordinates) - 1)
    )
    return metres / float(METRES_PER_FOOT)


def test_the_active_rule_is_what_the_mart_measured_with(laterals_loaded):
    assert resolve_length_method(laterals_loaded).method == "geodesic"


def test_the_mart_length_is_the_geodesic_length_not_a_projected_one(laterals_loaded):
    measured = rows(
        laterals_loaded,
        "select t.lateral_length_ft_exact,"
        "       ST_Length(s.geom::geography) / %s,"
        f"       ST_Length(ST_Transform(s.geom, {SUPERSEDED_EPSG})) / %s"
        "  from marts.nd_laterals_tile t"
        "  join canonical.well_spatial s"
        "    on s.api10 = t.api10 and s.geom_key = t.linekey and s.geom_type = 'lateral'",
        (float(METRES_PER_FOOT), float(METRES_PER_FOOT)),
    )
    assert measured

    for stored, geodesic, projected in measured:
        assert float(stored) == pytest.approx(geodesic, abs=1e-9)
        assert float(stored) != pytest.approx(projected, abs=1e-9) or geodesic == 0


def test_an_independent_geodesic_agrees_within_the_bound_the_rule_states(laterals_loaded):
    measured = rows(
        laterals_loaded,
        "select t.lateral_length_ft_exact, ST_AsGeoJSON(s.geom, 15)"
        "  from marts.nd_laterals_tile t"
        "  join canonical.well_spatial s"
        "    on s.api10 = t.api10 and s.geom_key = t.linekey and s.geom_type = 'lateral'",
    )
    assert measured

    worst = max(abs(float(stored) - geodesic_feet(geojson)) for stored, geojson in measured)
    assert worst < GEODESIC_AGREEMENT_FT, f"PostGIS and pyproj disagree by {worst} ft"


def test_the_superseded_projection_overstated_the_same_geometry(laterals_loaded):
    """The +144,379 ft fleet delta, in the direction the fixture can prove."""
    projected, geodesic, worst = rows(
        laterals_loaded,
        "select sum(ST_Length(ST_Transform(geom, %s))) / %s,"
        "       sum(ST_Length(geom::geography)) / %s,"
        "       max(abs(ST_Length(ST_Transform(geom, %s)) - ST_Length(geom::geography))) / %s"
        "  from canonical.well_spatial where geom_type = 'lateral'",
        (
            SUPERSEDED_EPSG,
            float(METRES_PER_FOOT),
            float(METRES_PER_FOOT),
            SUPERSEDED_EPSG,
            float(METRES_PER_FOOT),
        ),
    )[0]

    assert projected > geodesic, "UTM 14N no longer overstates, so the fixture lost its evidence"
    assert worst > 0.5, "no fixture lateral is far enough out of zone to guard the regression"


def test_the_card_and_the_tile_still_agree_after_the_supersession(laterals_loaded, api_client):
    """M-2 holds under the new method: one conversion, one quantize, two paths."""
    multilateral = rows(
        laterals_loaded,
        "select api10, sum(lateral_length_ft_exact) from marts.nd_laterals_tile"
        " group by api10 having count(*) > 1 order by api10",
    )
    assert multilateral

    for api10, tiled in multilateral:
        served = api_client.get(f"/v1/wells/{api10}").json()["data"]["lateral_length_ft"]
        assert Decimal(served["value"]) == Decimal(str(tiled)).quantize(Decimal("0.01")), api10


def test_the_card_states_the_method_and_the_rule_that_chose_it(laterals_loaded, api_client):
    api10 = scalar(laterals_loaded, "select api10 from marts.nd_laterals_tile limit 1")

    data = api_client.get(f"/v1/wells/{api10}").json()["data"]

    assert data["length_method"] == "geodesic"
    assert data["compute_crs"] == "EPSG:4326"


def test_the_refresh_records_the_method_it_rebuilt_under(laterals_loaded):
    """The re-derivation the deployer runs is auditable: one event naming the rule."""
    payload = rows(
        laterals_loaded,
        "select payload from lineage.audit_events where event_type = 'mart.refreshed'",
    )[-1][0]

    assert payload["length_method"] == "geodesic"
    assert payload["length_rule_id"] == "cr_nd_compute_crs_2"
    assert payload["row_counts"]["nd_laterals_tile"] > 0
