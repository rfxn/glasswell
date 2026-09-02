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

from glasswell.ingest.base import LOCKFILE_SHA256_ENV
from glasswell.ingest.nd_gis import (
    load_laterals,
    load_spacing_units,
    load_surveys,
    load_wells,
)
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.explain import resolve_chain
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts import ND_LAYERS, TILE_LAYERS, refresh_for
from glasswell.marts.nd_wells import main
from glasswell.marts.tiles import simplify_tolerance, thin_key_sql
from glasswell.seed import seed_all
from glasswell.units import METRES_PER_FOOT
from tests.support.layers import schema_reads_in
from tests.support.mvt import attribute_keys, attribute_values, feature_count, layer_name, layers

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "nd_gis"
REPO_ROOT = Path(__file__).resolve().parents[2]
MARTIN_CONFIG = REPO_ROOT / "infra" / "martin" / "config.yaml"
MARTS_PACKAGE = REPO_ROOT / "src" / "glasswell" / "marts"
ARCHIVES = {
    "wells": FIXTURES / "OGD_Wells_300.zip",
    "laterals": FIXTURES / "OGD_Horizontals_Line_300.zip",
    "spacing_units": FIXTURES / "OGD_DrillingSpacingUnits_300.zip",
    "surveys": FIXTURES / "OGD_Directionals_stations.zip",
}
LOADERS = {
    "wells": load_wells,
    "laterals": load_laterals,
    "spacing_units": load_spacing_units,
    "surveys": load_surveys,
}

MAX_PROBE_ZOOM = 14
PROJECTED_MARTS = ("nd_laterals_tile", "nd_wells_tile", "nd_survey_traces_tile")


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
    """P3's fixture load: wells first, then the geometry layers that reference them.

    The survey fixture and the wells fixture were cut independently and overlap on three
    API-10s, so this database carries both mart geometries for the same slice — which is the
    condition the survey layer has to hold up under, not a clean-room one.
    """
    seed_all(db)
    db.commit()
    for layer in ("wells", "laterals", "spacing_units", "surveys"):
        load_layer(db, raw_root, lineage_env, layer)
    return db


@pytest.fixture
def refreshed(canonical_nd: psycopg.Connection, lineage_env):
    with lineage_session(recorder=PostgresRecorder(canonical_nd), environment=lineage_env):
        report = refresh_for(canonical_nd, "ND")
    canonical_nd.commit()
    return report


def test_refresh_projects_canonical_into_every_tile_mart(canonical_nd, refreshed):
    counts = {
        f"nd_{name}_tile": scalar(
            canonical_nd,
            "select count(*) from canonical.well_spatial where geom_type = %s",
            (geom_type,),
        )
        for name, geom_type in (
            ("laterals", "lateral"), ("wells", "surface"), ("survey_traces", "survey_trace")
        )
    }
    assert all(count > 0 for count in counts.values())

    for table, expected in counts.items():
        assert scalar(canonical_nd, f"select count(*) from marts.{table}") == expected
    assert refreshed.row_counts == counts

    styled = rows(
        canonical_nd,
        "select count(*) filter (where operator_name is not null),"
        "       count(*) filter (where status_canonical is not null),"
        "       count(*) filter (where spud_year is not null)"
        "  from marts.nd_laterals_tile",
    )[0]
    assert all(count > 0 for count in styled), "styling attributes never reached the tile mart"


def test_the_wells_mart_carries_the_regulator_well_type_onto_the_wire(canonical_nd, refreshed):
    """M1-7: the disposal layer keys on well_type_reported, so the column must survive every
    stage — mart, published view, and the MVT itself. The fixture slice holds SWD and WI
    wells, so the class is non-empty here rather than vacuously green."""
    mismatched = scalar(
        canonical_nd,
        "select count(*) from marts.nd_wells_tile t"
        " join canonical.wells_latest w on w.api10 = t.api10"
        " where t.well_type_reported is distinct from w.well_type_reported",
    )
    assert mismatched == 0, "the mart's well_type disagrees with canonical"

    injection = scalar(
        canonical_nd,
        "select count(*) from marts.nd_wells_tile where well_type_reported in"
        " ('SWD', 'WI', 'CO2I', 'AI', 'GI', 'SFI', 'MWUI', 'INJP')",
    )
    assert injection > 0, "no injection-class well reached the mart"
    # The publication boundary: martin reads the view and no base relation (DR-05).
    assert scalar(
        canonical_nd,
        "select count(*) from marts.tile_nd_wells where well_type_reported is not null",
    ) == scalar(
        canonical_nd,
        "select count(*) from marts.nd_wells_tile where well_type_reported is not null",
    )

    swd = rows(
        canonical_nd,
        "select ST_X(geom), ST_Y(geom) from marts.nd_wells_tile"
        " where well_type_reported = 'SWD' limit 1",
    )[0]
    zoom, x, y = covering_tile((swd[0], swd[1], swd[0], swd[1]))
    tile = scalar(canonical_nd, "select marts.nd_wells(%s, %s, %s, null)", (zoom, x, y))
    drawn = layers(bytes(tile))
    assert drawn, "the tile covering an SWD well is empty"
    assert "well_type_reported" in attribute_keys(drawn[0])
    assert ("string", "SWD") in attribute_values(drawn[0])


def test_the_disposal_class_is_a_conformance_row_not_a_web_constant(canonical_nd):
    """R8: which well_type codes the disposal layer draws is a mapping decision, so it is a
    row served at /v1/conformance, and the web filter cites it rather than owning it."""
    spec = scalar(
        canonical_nd,
        "select spec from lineage.conformance_rules"
        " where rule_id = 'cr_nd_well_type_disposal_1'",
    )
    assert spec is not None, "the classing rule is not seeded"
    assert spec["well_type_codes"] == ["SWD", "WI", "CO2I", "AI", "GI", "SFI", "MWUI", "INJP"]
    assert spec["classification"] == "disposal_injection"


def test_every_nd_layer_carries_its_geometry_provenance_onto_the_wire(canonical_nd, refreshed):
    """M1-3: geom_type is served verbatim as geometry_provenance on all three ND layers, so
    the laterals row's "not a directional survey trace" caveat has a machine-readable
    backing. The traces mart has carried it since 030; wells and laterals join here."""
    for table, expected in (
        ("nd_wells_tile", "surface"),
        ("nd_laterals_tile", "lateral"),
        ("nd_survey_traces_tile", "survey_trace"),
    ):
        total = scalar(canonical_nd, f"select count(*) from marts.{table}")
        assert total > 0, f"{table} is empty; the provenance assertion would be vacuous"
        assert (
            scalar(
                canonical_nd,
                f"select count(*) from marts.{table} where geometry_provenance = %s",
                (expected,),
            )
            == total
        ), f"{table} is not homogeneous in geometry_provenance = {expected!r}"

    # The publication boundary: martin reads the views and no base relation (DR-05).
    for view in ("tile_nd_wells", "tile_nd_laterals"):
        assert scalar(
            canonical_nd,
            f"select count(*) from marts.{view} where geometry_provenance is not null",
        ) == scalar(canonical_nd, f"select count(*) from marts.{view}")

    surface = rows(
        canonical_nd, "select ST_X(geom), ST_Y(geom) from marts.nd_wells_tile limit 1"
    )[0]
    zoom, x, y = covering_tile((surface[0], surface[1], surface[0], surface[1]))
    tile = scalar(canonical_nd, "select marts.nd_wells(%s, %s, %s, null)", (zoom, x, y))
    drawn = layers(bytes(tile))
    assert drawn, "the tile covering a surface well is empty"
    assert "geometry_provenance" in attribute_keys(drawn[0])
    assert ("string", "surface") in attribute_values(drawn[0])

    lateral = rows(
        canonical_nd,
        "select ST_X(ST_PointOnSurface(geom)), ST_Y(ST_PointOnSurface(geom))"
        " from marts.nd_laterals_tile limit 1",
    )[0]
    zoom, x, y = covering_tile((lateral[0], lateral[1], lateral[0], lateral[1]))
    tile = scalar(canonical_nd, "select marts.nd_laterals(%s, %s, %s, null)", (zoom, x, y))
    drawn = layers(bytes(tile))
    assert drawn, "the tile covering a lateral is empty"
    assert "geometry_provenance" in attribute_keys(drawn[0])
    assert ("string", "lateral") in attribute_values(drawn[0])


def test_the_provenance_classing_is_a_conformance_row_not_a_web_constant(canonical_nd):
    """R8: which ND filing each geometry family's coordinates come from is a mapping
    decision, so it is a row served at /v1/conformance, and the tiles cite it through the
    refresh derivation rather than owning it (rules=[..., PROVENANCE_RULE])."""
    spec = scalar(
        canonical_nd,
        "select spec from lineage.conformance_rules"
        " where rule_id = 'cr_nd_geometry_provenance_1'",
    )
    assert spec is not None, "the provenance classing rule is not seeded"
    assert sorted(spec["classes"]) == ["lateral", "surface", "survey_trace"]
    assert spec["classification"] == "geometry_provenance"
    # The ND-only scope ruling is stated where a reader would look for the TX half (RF-1).
    assert "RF-1" in spec["tx_exclusion"]


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
        again = refresh_for(canonical_nd, "ND")
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


def test_the_cli_refreshes_the_database_p7_points_it_at(
    canonical_nd, postgres_password, monkeypatch, capsys
):
    monkeypatch.setenv("PGPASSWORD", postgres_password)
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


def test_the_cli_pins_the_lockfile_the_ingest_unit_exports(
    canonical_nd, postgres_password, monkeypatch, capsys
):
    """M-4: the refresh is one of the two paths that used to stamp an unpinned `env_cli`."""
    monkeypatch.setenv("PGPASSWORD", postgres_password)
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
        # Exactly one geometry evaluation per emitted sublayer: a label-emitting function
        # (M2-3/F1) encodes two layers from two geometries, never the same geometry twice.
        assert body.count("st_asmvtgeom") == body.count("st_asmvt(") >= 1


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
    """Blueprint §3.0.1: marts read canonical only, and staging never serves.

    Read from the parsed module, so a name spelled in pieces is folded before it is judged --
    `"stag" + "ing" + ".nd_mpr_oil"` greps clean and still reads staging.

    `status_resolution.py` is walked with the package though it sits outside it: the New
    Mexico mart no longer holds all of its own SQL, and the shared resolver's join and
    coalesce are composed there. It is not moved under `marts/` because the serving routers
    read it too, and importing `glasswell.marts.*` from `api/routers/` would invert the very
    layer direction this test protects.
    """
    modules = [
        *sorted(MARTS_PACKAGE.glob("*.py")),
        MARTS_PACKAGE.parent / "status_resolution.py",
    ]

    assert modules, "the marts package walked no modules, so this test cannot fail"
    for source in modules:
        assert source.is_file(), f"{source} is not on disk, so this test cannot fail"
        assert schema_reads_in(source, "staging") == [], f"{source.name} reads staging"


def _cells_at(connection: psycopg.Connection, relation: str, zoom: int) -> int:
    """How many distinct grid cells the whole mart occupies at `zoom`.

    The cell expression comes from the module, so what is measured here is the rule the
    installed function ranks within rather than a restatement of it.
    """
    return scalar(
        connection,
        f"select count(distinct {thin_key_sql().replace('src.', 'src.')})"
        f"  from {relation} src, (values (%(z)s::int)) as e(z)",
        {"z": zoom},
    )


def _features_in(connection: psycopg.Connection, layer, zoom: int, x: int, y: int) -> int:
    """The features the installed function puts on one tile, read back out of the protobuf."""
    tile = scalar(connection, f"select marts.{layer}(%s, %s, %s, null)", (zoom, x, y))
    drawn = layers(bytes(tile)) if tile else []
    return feature_count(drawn[0]) if drawn else 0


def test_the_overplot_gate_collapses_features_inside_the_band_it_is_gated_to(
    canonical_nd, refreshed
):
    """A gate that removes nothing anywhere is not a gate, and the bytes the approval rests
    on are features that do not ride the tile."""
    total = scalar(canonical_nd, "select count(*) from marts.nd_wells_tile")

    assert _cells_at(canonical_nd, "marts.nd_wells_tile", 4) < total


@pytest.mark.parametrize("zoom", [8, 11, 14])
def test_the_overplot_gate_keeps_wells_that_share_one_coordinate_above_the_band(
    canonical_nd, refreshed, zoom
):
    """547 of Texas's 355,463 wells and 144 of North Dakota's 43,817 sit at a coordinate
    another well already occupies. Ranking inside the cell keeps them; collapsing the cell
    to a set dropped them at every zoom, which no fixture without a coincident pair can
    show (measured on VM 111, 2026-08-21)."""
    twin = scalar(canonical_nd, "select api10 from marts.nd_wells_tile order by api10 limit 1")
    canonical_nd.execute(
        "insert into marts.nd_wells_tile (api10, operator_name, status_canonical, spud_year,"
        " derivation_id, geom)"
        " select %s, operator_name, status_canonical, spud_year, derivation_id, geom"
        "   from marts.nd_wells_tile where api10 = %s",
        (f"{twin[:-1]}X", twin),
    )
    where_it_is = rows(
        canonical_nd,
        "select ST_X(geom), ST_Y(geom) from marts.nd_wells_tile where api10 = %s",
        (twin,),
    )[0]
    zoom_x, zoom_y = tile_of(where_it_is[0], where_it_is[1], zoom)
    both = rows(
        canonical_nd,
        "select count(*) from marts.nd_wells_tile where api10 in (%s, %s)",
        (twin, f"{twin[:-1]}X"),
    )

    assert both[0][0] == 2, "the coincident pair was not staged"
    assert _cells_at(canonical_nd, "marts.nd_wells_tile", zoom) < scalar(
        canonical_nd, "select count(*) from marts.nd_wells_tile"
    ), "the pair must share a cell, or this test proves nothing"
    on_the_tile = scalar(
        canonical_nd,
        "select count(*) from marts.nd_wells_tile t"
        " where t.geom && ST_Transform(ST_TileEnvelope(%s, %s, %s), 4326)",
        (zoom, zoom_x, zoom_y),
    )

    assert on_the_tile >= 2, "the tile chosen does not carry the coincident pair"
    assert _features_in(canonical_nd, "nd_wells", zoom, zoom_x, zoom_y) == on_the_tile


def test_a_spacing_unit_label_is_emitted_exactly_once_across_any_tiling(canonical_nd, refreshed):
    """The spacing function shares the labelled template, so its anchors get the same seam
    guarantee the land layers assert (visual-m14 F1; ported per gate-m23 residual 7)."""
    units = scalar(canonical_nd, "select count(*) from marts.nd_spacing_units_tile")
    assert units > 0
    zoom, x, y = covering_tile(extent_of(canonical_nd, "marts.nd_spacing_units_tile"))
    fragments = 0
    labels = 0
    for dx in range(4):
        for dy in range(4):
            tile = scalar(
                canonical_nd,
                "select marts.nd_spacing_units(%s, %s, %s)",
                (zoom + 2, 4 * x + dx, 4 * y + dy),
            )
            if tile is None:
                continue
            named = {layer_name(layer): layer for layer in layers(bytes(tile))}
            fragments += feature_count(named.get("nd_spacing_units", b""))
            labels += feature_count(named.get("nd_spacing_units_label", b""))
    assert fragments >= units
    assert labels == units
