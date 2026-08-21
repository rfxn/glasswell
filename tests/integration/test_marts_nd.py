from __future__ import annotations

import json
import math
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import httpx
import psycopg
import pytest
import yaml

from glasswell.api.routers.tiles import PUBLISHED_LAYERS
from glasswell.ingest.base import LOCKFILE_SHA256_ENV
from glasswell.ingest.nd_gis import load_laterals, load_spacing_units, load_wells
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.explain import resolve_chain
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts import ND_LAYERS, TILE_LAYERS, refresh_all
from glasswell.marts.nd_wells import main
from glasswell.marts.tiles import simplify_tolerance
from glasswell.seed import seed_all
from glasswell.units import METRES_PER_FOOT

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "nd_gis"
REPO_ROOT = Path(__file__).resolve().parents[2]
MARTIN_CONFIG = REPO_ROOT / "infra" / "martin" / "config.yaml"
MARTS_PACKAGE = REPO_ROOT / "src" / "glasswell" / "marts"
ARCHIVES = {
    "wells": FIXTURES / "OGD_Wells_300.zip",
    "laterals": FIXTURES / "OGD_Horizontals_Line_300.zip",
    "spacing_units": FIXTURES / "OGD_DrillingSpacingUnits_300.zip",
}
LOADERS = {
    "wells": load_wells,
    "laterals": load_laterals,
    "spacing_units": load_spacing_units,
}

MAX_PROBE_ZOOM = 14
PROJECTED_MARTS = ("nd_laterals_tile", "nd_wells_tile")


def client_for(archive: Path) -> httpx.Client:
    payload = archive.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload, headers={"content-type": "application/zip"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def scalar(connection: psycopg.Connection, sql: str, parameters: tuple = ()):
    with connection.cursor() as cursor:
        cursor.execute(sql, parameters)
        row = cursor.fetchone()
    return row[0] if row else None


def rows(connection: psycopg.Connection, sql: str, parameters: tuple = ()) -> list[tuple]:
    with connection.cursor() as cursor:
        cursor.execute(sql, parameters)
        return cursor.fetchall()


def tile_of(longitude: float, latitude: float, zoom: int) -> tuple[int, int]:
    """The web-Mercator tile a point falls in — the inverse of P7's ST_Extent smoke SQL."""
    side = 2**zoom
    radians = math.radians(latitude)
    x = int((longitude + 180.0) / 360.0 * side)
    y = int((1 - math.log(math.tan(radians) + 1 / math.cos(radians)) / math.pi) / 2 * side)
    return min(x, side - 1), min(y, side - 1)


def covering_tile(extent: tuple[float, float, float, float]) -> tuple[int, int, int]:
    """The deepest tile that still contains the whole extent, so it cannot be empty (B9)."""
    xmin, ymin, xmax, ymax = extent
    for zoom in range(MAX_PROBE_ZOOM, 0, -1):
        north_west = tile_of(xmin, ymax, zoom)
        south_east = tile_of(xmax, ymin, zoom)
        if north_west == south_east:
            return zoom, *north_west
    raise AssertionError(f"no single tile above z0 contains {extent}")


def extent_of(connection: psycopg.Connection, relation: str) -> tuple[float, float, float, float]:
    box = rows(
        connection,
        "select ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e)"
        f" from (select ST_Extent(geom) e from {relation}) extent",
    )[0]
    assert None not in box, f"{relation} has no geometry to derive a tile from"
    return box


def _counts(connection: psycopg.Connection) -> dict[str, int]:
    return {
        table: scalar(connection, f"select count(*) from marts.{table}")
        for table in PROJECTED_MARTS
    }


def load_layer(connection: psycopg.Connection, raw_root, lineage_env, layer: str) -> None:
    with lineage_session(
        recorder=PostgresRecorder(connection), environment=lineage_env
    ), client_for(ARCHIVES[layer]) as client:
        LOADERS[layer](connection, raw_root=raw_root, client=client)
    connection.commit()


@pytest.fixture
def canonical_nd(db: psycopg.Connection, raw_root, lineage_env) -> psycopg.Connection:
    """P3's fixture load: wells first, then the laterals that reference them."""
    seed_all(db)
    db.commit()
    for layer in ("wells", "laterals", "spacing_units"):
        load_layer(db, raw_root, lineage_env, layer)
    return db


@pytest.fixture
def refreshed(canonical_nd: psycopg.Connection, lineage_env):
    with lineage_session(recorder=PostgresRecorder(canonical_nd), environment=lineage_env):
        report = refresh_all(canonical_nd)
    canonical_nd.commit()
    return report


def test_refresh_projects_canonical_into_both_tile_marts(canonical_nd, refreshed):
    laterals = scalar(
        canonical_nd, "select count(*) from canonical.well_spatial where geom_type = 'lateral'"
    )
    surfaces = scalar(
        canonical_nd, "select count(*) from canonical.well_spatial where geom_type = 'surface'"
    )
    assert laterals > 0
    assert surfaces > 0

    assert scalar(canonical_nd, "select count(*) from marts.nd_laterals_tile") == laterals
    assert scalar(canonical_nd, "select count(*) from marts.nd_wells_tile") == surfaces
    assert refreshed.row_counts == {"nd_laterals_tile": laterals, "nd_wells_tile": surfaces}

    styled = rows(
        canonical_nd,
        "select count(*) filter (where operator_name is not null),"
        "       count(*) filter (where status_canonical is not null),"
        "       count(*) filter (where spud_year is not null)"
        "  from marts.nd_laterals_tile",
    )[0]
    assert all(count > 0 for count in styled), "styling attributes never reached the tile mart"


def test_the_well_card_mart_is_deliberately_empty(canonical_nd, refreshed):
    """M6 demoted the card mart: it lands when the API reads it, and no sooner."""
    assert scalar(canonical_nd, "select count(*) from marts.nd_well_card") == 0
    assert "nd_well_card" not in refreshed.row_counts


def test_lateral_length_is_the_measured_length_in_feet(canonical_nd, refreshed):
    """The reciprocal is the module's own Decimal, not a literal: A3-F7 made 3.28084 unable
    to fail this at abs=0.01, so the comparison is exact against glasswell.units."""
    measured = rows(
        canonical_nd,
        "select t.lateral_length_ft_exact, ST_Length(s.geom::geography)"
        "  from marts.nd_laterals_tile t"
        "  join canonical.well_spatial s"
        "    on s.api10 = t.api10 and s.geom_key = t.linekey and s.geom_type = 'lateral'",
    )
    assert measured
    for stored, metres in measured:
        assert stored == pytest.approx(Decimal(repr(metres)) / METRES_PER_FOOT, abs=Decimal("1e-9"))
    # SHAPE_Leng is degrees (~1.5e-2); a mart that read it would never clear one foot.
    assert min(float(stored) for stored, _ in measured) > 1.0


def test_the_card_figure_equals_the_length_the_tile_carries(canonical_nd, refreshed, api_client):
    """M-2: the handle on the card claims to explain the number the tile renders. One number.

    The policy is round-final: both paths convert with `glasswell.units`, the mart stores the
    conversion unrounded, and the only quantize step is the serving edge.
    """
    multilateral = rows(
        canonical_nd,
        "select api10, sum(lateral_length_ft_exact) from marts.nd_laterals_tile"
        " group by api10 having count(*) > 1 order by api10",
    )
    assert multilateral, "the GIS fixture holds no multi-lateral well, so M-2 cannot regress here"

    for api10, tiled in multilateral:
        served = api_client.get(f"/v1/wells/{api10}").json()["data"]["lateral_length_ft"]
        assert served["unit"] == "ft"
        assert Decimal(served["value"]) == tiled.quantize(Decimal("0.01")), api10


def test_the_tile_mart_stores_the_length_unrounded(canonical_nd, refreshed):
    """A mart that rounds per lateral cannot be summed back to the served figure."""
    stored = [
        row[0]
        for row in rows(canonical_nd, "select lateral_length_ft_exact from marts.nd_laterals_tile")
    ]

    assert stored
    assert any(value != value.quantize(Decimal("0.01")) for value in stored)


def test_every_tile_row_carries_a_handle_that_resolves_to_a_manifest(canonical_nd, refreshed):
    for table in PROJECTED_MARTS:
        handles = [
            row[0]
            for row in rows(canonical_nd, f"select distinct derivation_id from marts.{table}")
        ]
        assert handles == [refreshed.derivation_id]
        chain = resolve_chain(canonical_nd, handles[0], depth="full")
        assert chain.terminals, f"marts.{table} rows do not walk back to a manifest"
        known = scalar(
            canonical_nd,
            "select count(*) from lineage.manifests where manifest_id = any(%s)",
            (list(set(chain.terminals)),),
        )
        assert known == len(set(chain.terminals))


def test_a_second_refresh_is_idempotent_and_content_addressed(canonical_nd, refreshed, lineage_env):
    before = _counts(canonical_nd)
    with lineage_session(recorder=PostgresRecorder(canonical_nd), environment=lineage_env):
        again = refresh_all(canonical_nd)
    canonical_nd.commit()

    assert again.derivation_id == refreshed.derivation_id
    assert again.row_counts == refreshed.row_counts
    after = _counts(canonical_nd)
    assert after == before
    recorded = scalar(
        canonical_nd, "select count(*) from lineage.derivations where operation = 'mart.refresh'"
    )
    assert recorded == 1


def test_the_wells_tile_mart_holds_surface_points_only(canonical_nd, refreshed):
    shapes = {
        row[0]
        for row in rows(
            canonical_nd, "select distinct ST_GeometryType(geom) from marts.nd_wells_tile"
        )
    }
    assert shapes == {"ST_Point"}
    assert scalar(canonical_nd, "select count(*) from marts.nd_wells_tile") == scalar(
        canonical_nd,
        "select count(distinct api10) from canonical.well_spatial where geom_type = 'surface'",
    )


# ND_LAYERS, not TILE_LAYERS: this fixture holds the ND slice, and a TX layer with no rows in
# it would fail for having no data rather than for producing a bad tile. The TX layers get the
# same two assertions against TX data in test_tx_marts.py.
@pytest.mark.parametrize("layer", ND_LAYERS, ids=lambda layer: layer.name)
def test_the_function_source_returns_a_tile_over_the_data(canonical_nd, refreshed, layer):
    zoom, x, y = covering_tile(extent_of(canonical_nd, layer.source))
    tile = scalar(canonical_nd, f"select marts.{layer.name}(%s, %s, %s, null)", (zoom, x, y))
    assert tile, f"{layer.name} produced no MVT for {zoom}/{x}/{y}, which covers its own extent"
    assert layer.name.encode() in bytes(tile), "the MVT layer name is not the tile source id"


@pytest.mark.parametrize("layer", ND_LAYERS, ids=lambda layer: layer.name)
def test_the_function_source_returns_nothing_off_the_data(canonical_nd, refreshed, layer):
    zoom, x, y = covering_tile(extent_of(canonical_nd, layer.source))
    opposite = (x + 2**zoom // 2) % 2**zoom
    tile = scalar(canonical_nd, f"select marts.{layer.name}(%s, %s, %s, null)", (zoom, opposite, y))
    assert not tile, "an empty tile must be empty so the proxy can answer 204, not 200"


def test_the_function_sources_carry_the_signature_martin_discovers(canonical_nd, refreshed):
    discovered = {
        name: (arguments, result, volatility, parallel)
        for name, arguments, result, volatility, parallel in rows(
            canonical_nd,
            "select p.proname, pg_get_function_arguments(p.oid), pg_get_function_result(p.oid),"
            "       p.provolatile, p.proparallel"
            "  from pg_proc p join pg_namespace n on n.oid = p.pronamespace"
            " where n.nspname = 'marts'",
        )
    }
    assert set(discovered) == {layer.name for layer in TILE_LAYERS}
    for arguments, result, volatility, parallel in discovered.values():
        assert arguments.startswith("z integer, x integer, y integer, query json")
        assert result == "bytea"
        assert (volatility, parallel) == ("s", "s")


def test_the_cli_refreshes_the_database_p7_points_it_at(canonical_nd, monkeypatch, capsys):
    monkeypatch.setenv("PGPASSWORD", "glasswell")
    assert main(["--dsn", canonical_nd.info.dsn, "--env-id", "env_p5_cli"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["row_counts"]["nd_laterals_tile"] > 0

    canonical_nd.rollback()
    assert scalar(canonical_nd, "select count(*) from marts.nd_laterals_tile") == (
        report["row_counts"]["nd_laterals_tile"]
    )
    assert scalar(canonical_nd, "select derivation_id from marts.nd_laterals_tile limit 1") == (
        report["derivation_id"]
    )


def test_the_cli_pins_the_lockfile_the_ingest_unit_exports(canonical_nd, monkeypatch, capsys):
    """M-4: the refresh is one of the two paths that used to stamp an unpinned `env_cli`."""
    monkeypatch.setenv("PGPASSWORD", "glasswell")
    monkeypatch.setenv(LOCKFILE_SHA256_ENV, "7c" * 32)

    assert main(["--dsn", canonical_nd.info.dsn]) == 0
    report = json.loads(capsys.readouterr().out)

    canonical_nd.rollback()
    assert scalar(
        canonical_nd,
        "select e.lockfile_sha256 from lineage.derivations d"
        "  join lineage.environments e on e.env_id = d.env_id"
        " where d.derivation_id = %s",
        (report["derivation_id"],),
    ) == "7c" * 32


def _function_bodies(connection: psycopg.Connection) -> dict[str, str]:
    return {
        name: definition.lower()
        for name, definition in rows(
            connection,
            "select p.proname, pg_get_functiondef(p.oid) from pg_proc p"
            "  join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'marts'",
        )
    }


def test_only_the_line_layer_is_thinned(canonical_nd, refreshed):
    """Points have nothing to thin, and topology-safe polygon simplification measured 171%
    slower for 3% fewer bytes, so applying it there would be a cost with no return."""
    bodies = _function_bodies(canonical_nd)

    assert "st_simplify(" in bodies["nd_laterals"]
    for name in ("nd_wells", "nd_spacing_units"):
        assert "st_simplify(" not in bodies[name], f"{name} pays for simplification it cannot use"


def test_the_geometry_expression_is_evaluated_once_per_row(canonical_nd, refreshed):
    """Inlined, the planner evaluates ST_AsMVTGeom for the null test and again for the
    aggregate: 246 ms against 134 ms on the live z4 laterals tile."""
    for name, body in _function_bodies(canonical_nd).items():
        assert "as materialized" in body, f"{name} would evaluate ST_AsMVTGeom twice per row"
        assert body.count("st_asmvtgeom") == 1


@pytest.mark.parametrize("zoom", [4, 9, 13])
def test_a_thinned_lateral_stays_within_the_tolerance_its_zoom_allows(
    canonical_nd, refreshed, zoom
):
    """Every vertex the simplifier drops is within the tolerance of the line that replaces
    it, so the deviation is bounded by a quarter of a rendered pixel at every zoom."""
    tolerance = simplify_tolerance(zoom)
    worst = scalar(
        canonical_nd,
        "select max(ST_Distance(vertex.geom, thinned))"
        "  from (select ST_Transform(geom, 3857) as full,"
        "               ST_Simplify(ST_Transform(geom, 3857), %s, true) as thinned"
        "          from marts.nd_laterals_tile) shape,"
        "       lateral ST_DumpPoints(shape.full) vertex",
        (tolerance,),
    )

    assert worst is not None, "the fixture carries no lateral geometry to bound"
    assert worst <= tolerance


@pytest.mark.parametrize("zoom", [4, 9, 13])
def test_thinning_never_drops_a_lateral(canonical_nd, refreshed, zoom):
    """preserveCollapsed: a feature count that varies with zoom would make a tile a lie
    about how many laterals are there."""
    kept = scalar(
        canonical_nd,
        "select count(*) from marts.nd_laterals_tile"
        " where ST_Simplify(ST_Transform(geom, 3857), %s, true) is not null",
        (simplify_tolerance(zoom),),
    )

    assert kept == scalar(canonical_nd, "select count(*) from marts.nd_laterals_tile")


def test_a_whole_basin_tile_is_smaller_than_it_was_unthinned(canonical_nd, refreshed):
    """The regression bound: the low-zoom tile the fix targets must not grow back."""
    zoom, x, y = covering_tile(extent_of(canonical_nd, "marts.nd_laterals_tile"))
    thinned = scalar(canonical_nd, "select marts.nd_laterals(%s, %s, %s, null)", (zoom, x, y))
    columns = ", ".join(f"t.{column}" for column in TILE_LAYERS[0].columns)
    unthinned = scalar(
        canonical_nd,
        "with feature as materialized ("
        "  select ST_AsMVTGeom(ST_Transform(t.geom, 3857), ST_TileEnvelope(%(z)s, %(x)s, %(y)s),"
        "                      4096, 64, true) as geom,"
        f"        {columns}"
        "    from marts.nd_laterals_tile t"
        "   where t.geom && ST_Transform(ST_TileEnvelope(%(z)s, %(x)s, %(y)s), 4326))"
        " select ST_AsMVT(feature, 'nd_laterals', 4096, 'geom') from feature"
        "  where feature.geom is not null",
        {"z": zoom, "x": x, "y": y},
    )

    assert len(bytes(thinned)) < len(bytes(unthinned))


def test_the_module_runs_as_the_command_p7_documents():
    completed = subprocess.run(
        [sys.executable, "-m", "glasswell.marts.nd_wells", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--dsn" in completed.stdout


def test_the_marts_read_canonical_and_never_staging():
    """Blueprint §3.0.1: marts read canonical only, and staging never serves."""
    for source in sorted(MARTS_PACKAGE.glob("*.py")):
        assert "staging." not in source.read_text(), f"{source.name} reads staging"


def test_the_martin_config_declares_the_same_layers_the_proxy_admits():
    """The config is what the adopted unit publishes; the proxy's allowlist is what it will
    answer for. The two must not drift apart."""
    config = yaml.safe_load(MARTIN_CONFIG.read_text())
    postgres = config["postgres"]

    assert config["listen_addresses"] == "127.0.0.1:3000"
    assert set(postgres["functions"]) == PUBLISHED_LAYERS == {layer.name for layer in TILE_LAYERS}
    for layer in TILE_LAYERS:
        source = postgres["functions"][layer.name]
        assert source["schema"] == "marts"
        assert source["function"] == layer.name
        assert "derivation_id" in layer.columns, f"{layer.name} serves an unhandled figure"
    # Publishing the same ids twice — once as functions, once as the tables they read — is a
    # martin id collision, so the config carries exactly one mechanism.
    assert "tables" not in postgres
