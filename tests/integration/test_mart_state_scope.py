"""Each basin's mart holds its own basin, with both loaded at once.

The ND mart selects filtered on `geom_type` and nothing else, so the first ND refresh after
another jurisdiction reached `canonical` would have swept its rows in — every TX well drawn a
second time under ND's layer, at doubled opacity, beneath a subtitle claiming 43,817 points.
Nothing failed and no test moved, because no test had ever run a refresh with two states in the
database. This one does.
"""

from __future__ import annotations

import psycopg
import pytest

from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.wells import refresh_for
from tests.integration.test_tx_gis_load import (  # noqa: F401
    client_for,
    identity,
    seeded,
)
from tests.integration.test_tx_gis_load import county as tx_loaded  # noqa: F401
from tests.support.seed import seed_manifest, seed_well, seed_well_spatial

ND_API10 = "3305300001"
ND_LATERAL_KEY = "33053000010000_LAT1"
ND_LATERAL = "LINESTRING(-103.5 47.9, -103.4 47.9)"
ND_SURFACE = "POINT(-103.5 47.9)"


@pytest.fixture
def both_basins(seeded: psycopg.Connection, tx_loaded, lineage_env):  # noqa: F811
    """The TX slice as loaded, plus one ND well with both geometries beside it."""
    manifest = seed_manifest(seeded, sha256="d" * 64, source_id="nd_gis_wells")
    seed_well(seeded, api10=ND_API10, manifest_id=manifest)
    seed_well_spatial(
        seeded, api10=ND_API10, geom_type="surface", wkt=ND_SURFACE, manifest_id=manifest
    )
    seed_well_spatial(
        seeded,
        api10=ND_API10,
        geom_type="lateral",
        geom_key=ND_LATERAL_KEY,
        wkt=ND_LATERAL,
        manifest_id=manifest,
    )
    seeded.commit()
    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env):
        nd = refresh_for(seeded, "ND")
        tx = refresh_for(seeded, "TX")
    seeded.commit()
    return {"nd": nd, "tx": tx, "tx_load": tx_loaded}


def counts(connection: psycopg.Connection, table: str) -> dict[str, int]:
    with connection.cursor() as cursor:
        cursor.execute(f"select left(api10, 2), count(*) from marts.{table} group by 1")
        return dict(cursor.fetchall())


def test_the_nd_marts_hold_north_dakota_only(both_basins, seeded) -> None:  # noqa: F811
    assert counts(seeded, "nd_wells_tile") == {"33": 1}
    assert counts(seeded, "nd_laterals_tile") == {"33": 1}


def test_the_tx_marts_hold_texas_only(both_basins, seeded) -> None:  # noqa: F811
    surface = both_basins["tx_load"].geometries["surface"]
    laterals = both_basins["tx_load"].geometries["lateral"]

    assert counts(seeded, "tx_wells_tile") == {"42": surface}
    assert counts(seeded, "tx_laterals_tile") == {"42": laterals}


def test_neither_refresh_reports_the_other_basin_as_its_own(both_basins) -> None:
    """The refresh's own row counts are what a deployer reads; they must not double either."""
    assert both_basins["nd"].row_counts == {
        "nd_wells_tile": 1, "nd_laterals_tile": 1, "nd_survey_traces_tile": 0
    }
    assert both_basins["tx"].row_counts["tx_wells_tile"] == (
        both_basins["tx_load"].geometries["surface"]
    )


def test_no_feature_is_drawn_by_both_basins_layers(both_basins, seeded) -> None:  # noqa: F811
    """The rendering consequence, stated as a query: one api10, one point layer."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(*) from marts.nd_wells_tile n join marts.tx_wells_tile t"
            "    on t.api10 = n.api10"
        )
        assert cursor.fetchone()[0] == 0
        cursor.execute(
            "select count(*) from marts.nd_laterals_tile n join marts.tx_laterals_tile t"
            "    on t.api10 = n.api10 and t.geom_key = n.linekey"
        )
        assert cursor.fetchone()[0] == 0


def test_each_refresh_declares_the_state_it_scoped_to(both_basins, seeded) -> None:  # noqa: F811
    """A reader of the derivation can tell which basin a mart was built for."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select params ->> 'state_code' from lineage.derivations where derivation_id = any(%s)"
            " order by params ->> 'state_code'",
            ([both_basins["nd"].derivation_id, both_basins["tx"].derivation_id],),
        )
        assert [row[0] for row in cursor.fetchall()] == ["33", "42"]


def test_no_wells_tile_serves_a_null_status_class(
    seeded,  # noqa: F811
    tx_loaded,  # noqa: F811
    lineage_env,
) -> None:
    """§3.4's fifth surface. The tile, the facet, the filter, the count and the card change
    together or not at all, and the tile was the one that did not.

    `resolved_status()` was called by two projections of nine, the two whose jurisdictions
    resolve at read time. The other seven selected `w.status_canonical` raw, so a
    promotion-time jurisdiction's tile carried a null for a well the serving path had already
    given the absence class. On screen that read as one class counted in the legend and drawn
    nowhere: `facetPredicate` matches the tile property, and a null matches nothing.

    Its own refresh rather than the shared fixture's, because the shared one has already run
    and `reconcile()` refuses a content-addressed id that repeats with a different output --
    which is the store saying, correctly, that the rows this well adds are new content.
    """
    manifest = seed_manifest(seeded, sha256="e" * 64, source_id="nd_gis_wells")
    # The well the defect is about: the source filed no status code, so no promotion wrote a
    # class and no map can resolve one. Its class is the absence class, and the tile has to
    # carry the word rather than a null.
    for api10, filed in (("3305300098", "A"), ("3305300099", None)):
        seed_well(
            seeded,
            api10=api10,
            manifest_id=manifest,
            status_canonical="active" if filed else None,
            status_reported=filed,
        )
        seed_well_spatial(
            seeded,
            api10=api10,
            geom_type="surface",
            wkt=f"POINT(-103.{api10[-2:]} 47.8)",
            manifest_id=manifest,
        )
    seeded.commit()
    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env):
        refresh_for(seeded, "ND")
        refresh_for(seeded, "TX")
    seeded.commit()

    with seeded.cursor() as cursor:
        cursor.execute(
            "select status_canonical from marts.nd_wells_tile where api10 = %s",
            ("3305300099",),
        )
        assert cursor.fetchone()[0] == "unmapped"
        cursor.execute(
            "select status_canonical from marts.nd_wells_tile where api10 = %s",
            ("3305300098",),
        )
        assert cursor.fetchone()[0] == "active"
        # And nowhere on any wells tile, over the whole loaded population.
        for table in ("nd_wells_tile", "nd_laterals_tile", "tx_wells_tile", "tx_laterals_tile"):
            cursor.execute(
                f"select count(*) from marts.{table} where status_canonical is null"
            )
            assert cursor.fetchone()[0] == 0, table
