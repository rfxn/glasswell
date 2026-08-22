"""Load the TX RRC county GIS well layers into staging and canonical (SB-01 §2.8).

One county archive carries three shapefiles — surface points, bottom-hole points and well arcs
— each with its own `.prj`, and every one of them is NAD27. The transform to EPSG:4326 happens
here, in promotion, through the NADCON grid `cr_tx_nad27_1` pins and fetches as its own
manifested artifact: PostGIS on a host without that grid answers `ST_Transform(geom, 4326)`
with a three-parameter fit that is wrong by metres and says nothing about it.

The arcs are the TX lateral geometry. No free parseable TX directional survey data exists, so
this is a bore trace and not a survey, and length is measured geodesically under
`cr_tx_compute_crs_1` rather than read from the shipped SHAPE_LEN.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import psycopg
from psycopg.rows import dict_row

from glasswell.ingest.base import record_vintage_day, resolve_environment
from glasswell.ingest.shapefile import ShapefileRecord, ZippedShapefile
from glasswell.ingest.tx_mft import MftClient
from glasswell.lengths import LengthMethod, compute_crs_rule, length_method
from glasswell.lineage import (
    ConformanceRule,
    InputRef,
    OutputSpec,
    PostgresRecorder,
    apply_rules,
    current_session,
    derive,
    fetch_raw,
    lineage_session,
    load_rules,
    quarantine,
)
from glasswell.lineage.serialization import hash_payload, json_ready
from glasswell.units import METRES_PER_FOOT

SOURCE_ID = "tx_gis_wells_county"
GRID_SOURCE_ID = "proj_grid_nad27"
GRID_KEY = "us_noaa_conus.tif"
GRID_URL = "https://cdn.proj.org/us_noaa_conus.tif"
GIS_LINK = "https://mft.rrc.texas.gov/link/d551fb20-442e-4b67-84fa-ac3f23ecabb4"
DATUM_RULE = "cr_tx_nad27_1"
LAYERS_RULE = "cr_tx_gis_layers_1"
SCOPE_RULE = "cr_tx_county_scope_1"
API10_RULE = "cr_tx_api10_build_1"
WELLBORE_KEY_RULE = "cr_tx_wellbore_key_1"
SURVIVOR_RULE = "cr_tx_geometry_survivor_1"
BOUNDS_RULE = "cr_tx_lateral_bounds_1"
MULTI_WELLBORE_RULE = "cr_tx_multi_wellbore_1"
BASIN = "permian"
BOTTOMHOLE_DEFAULT_KEY = "bottomhole"
# The RRC's API is three county digits then five well digits; the county the feature
# belongs to is the first three, whatever the archive it shipped in is called.
COUNTY_CODE_WIDTH = 3
# ~1 cm at this latitude: below the difference between the .shp point and the .dbf
# columns the same row publishes, and far below the 43 m the datum shift moves it.
UNCONVERTED_DEGREES = 1e-7


class SchemaDrift(ValueError):
    """The shipped DBF no longer carries a column the staging table declares."""


class DatumMismatch(ValueError):
    """The shipped .prj is not a datum cr_tx_nad27_1 accepts, so nothing is loaded from it."""


class GridUnavailable(RuntimeError):
    """The pinned NADCON grid is missing or is not the bytes the rule names."""


class IdentityNotPromoted(RuntimeError):
    """The wellbore export has not been promoted for this county, so identity would be lost."""


@dataclass(frozen=True, slots=True)
class TxLayer:
    layer: str
    suffix: str
    staging_table: str
    columns: tuple[str, ...]
    geometry_type: str
    # A county with no horizontal wells ships no arcs shapefile at all — four of the 55
    # Permian-district archives on 2026-08-20. Absent is a fact about the county; a missing
    # surface or bottom-hole layer would be a truncated download.
    optional: bool = False


LAYERS: Mapping[str, TxLayer] = {
    "surface": TxLayer(
        layer="surface",
        suffix="s",
        staging_table="staging.tx_gis_wells_surface",
        columns=(
            "surface_id", "symnum", "api", "reliab", "long27", "lat27", "long83", "lat83",
            "wellid",
        ),
        geometry_type="Point",
    ),
    "bottomhole": TxLayer(
        layer="bottomhole",
        suffix="b",
        staging_table="staging.tx_gis_wells_bottomhole",
        columns=(
            "bottom_id", "surface_id", "symnum", "apinum", "reliab", "api10", "api", "long27",
            "lat27", "long83", "lat83", "out_fips", "cwellnum", "radioact", "wellid", "stcode",
        ),
        geometry_type="Point",
    ),
    "lines": TxLayer(
        layer="lines",
        suffix="l",
        staging_table="staging.tx_gis_wells_lines",
        columns=("bottom_id", "surface_id", "api10", "api", "stcode", "shape_len"),
        geometry_type="Geometry",
        optional=True,
    ),
}

REASON_CODES = (
    "parse_error", "key_incomplete", "out_of_scope", "duplicate_row", "datum_undetermined",
    "multi_wellbore_policy", "unreliable_numeric",
)


@dataclass(frozen=True, slots=True)
class CountyLoad:
    county_code: str
    manifest_id: str
    staged: Mapping[str, int]
    wells_added: int
    geometries: Mapping[str, int]
    quarantined: Mapping[str, int]
    datum_residual_m: Mapping[str, float] = field(default_factory=dict)
    length_stats_ft: Mapping[str, float] = field(default_factory=dict)
    multi_wellbore_api10s: int = 0
    unchanged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "county_code": self.county_code,
            "manifest_id": self.manifest_id,
            "staged": dict(self.staged),
            "wells_added": self.wells_added,
            "geometries": dict(self.geometries),
            "quarantined": dict(self.quarantined),
            "datum_residual_m": dict(self.datum_residual_m),
            "length_stats_ft": dict(self.length_stats_ft),
            "multi_wellbore_api10s": self.multi_wellbore_api10s,
            "unchanged": self.unchanged,
        }


def county_scope(connection: psycopg.Connection) -> tuple[str, ...]:
    """The county files in scope, from the rule rather than from a list in this module."""
    return tuple(str(code) for code in _rule(connection, SCOPE_RULE).spec["county_codes"])


def archive_name(connection: psycopg.Connection, county_code: str) -> str:
    pattern = str(_rule(connection, SCOPE_RULE).spec["artifact_pattern"])
    return pattern.format(county_code=county_code)


def _rule(connection: psycopg.Connection, rule_id: str) -> ConformanceRule:
    for candidate in load_rules(connection, source_id=SOURCE_ID):
        if candidate.rule_id == rule_id:
            return candidate
    raise LookupError(f"rule {rule_id} is not seeded for {SOURCE_ID}")


def ensure_grid(
    connection: psycopg.Connection,
    datum: ConformanceRule,
    *,
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
) -> tuple[Path, str]:
    """Fetch the NADCON grid into the raw zone and check it against the hash the rule names."""
    fetched = fetch_raw(
        connection,
        GRID_SOURCE_ID,
        GRID_KEY,
        url=GRID_URL,
        raw_root=raw_root,
        client=client,
        media_type="image/tiff",
        license_note="Public domain NOAA grid redistributed by the PROJ CDN.",
        redistributable=True,
    )
    declared = str(datum.spec["grid_sha256"])
    if fetched.manifest.sha256 != declared:
        raise GridUnavailable(
            f"{GRID_KEY} hashes {fetched.manifest.sha256}; {datum.rule_id} pins {declared}."
            " A different grid is a different transform and is not silently accepted."
        )
    return fetched.payload_path, fetched.manifest.manifest_id


def datum_transformer(datum: ConformanceRule, grid_path: Path):
    """The pinned pipeline, bound to the manifested grid. Lazy import: PROJ is not free."""
    from pyproj import Transformer
    from pyproj.exceptions import ProjError

    pipeline = str(datum.spec["pipeline"]).format(grid_path=grid_path)
    try:
        return Transformer.from_pipeline(pipeline)
    except ProjError as error:
        raise GridUnavailable(f"{datum.rule_id}: PROJ refused the pinned pipeline: {error}"
                              ) from error


def _transform(transformer, lons: Sequence[float], lats: Sequence[float]
               ) -> tuple[list[float], list[float]]:
    """The pipeline is lat/lon ordered by its own axisswap step, so the call is too."""
    if not lons:
        return [], []
    ys, xs = transformer.transform(list(lats), list(lons))
    return list(xs), list(ys)


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return str(value)


def _staging_rows(
    layer: TxLayer, source: ZippedShapefile, manifest_id: str, county_code: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for record in source:
        attributes = {key.lower(): value for key, value in record.attributes.items()}
        missing = [column for column in layer.columns if column not in attributes]
        if missing:
            raise SchemaDrift(
                f"well{county_code}{layer.suffix} has no {', '.join(missing)} field"
            )
        row = {column: _text(attributes[column]) for column in layer.columns}
        row["manifest_id"] = manifest_id
        row["source_row_ordinal"] = record.ordinal
        row["source_county_code"] = county_code
        note = _unstorable(record, layer.geometry_type)
        row["geom_wkt"] = None if note else record.geometry.wkt
        rows.append(row)
        if note:
            rejected.append(
                {key: value for key, value in row.items() if key != "geom_wkt"} | {"detail": note}
            )
    return rows, rejected


def _unstorable(record: ShapefileRecord, declared: str) -> str | None:
    if record.is_empty:
        return "the source record carries no geometry"
    shape = record.geometry.geom_type
    if declared == "Geometry" or shape == declared:
        return None
    return f"{shape} does not fit the declared {declared} column"


def _has_layer(payload_path: Path, suffix: str) -> bool:
    with zipfile.ZipFile(payload_path) as bundle:
        return any(
            name.rpartition(".")[0].lower().endswith(suffix) and name.lower().endswith(".shp")
            for name in bundle.namelist()
        )


def _absent_layer(layer: TxLayer, manifest_id: str, county_code: str) -> tuple[str, int, int]:
    """An absent optional layer still gets a derivation: nothing is quietly not done."""
    with derive(
        "stage.parse",
        output=OutputSpec(
            store="postgis",
            dataset=layer.staging_table,
            partition={"manifest_id": manifest_id, "county_code": county_code},
        ),
        params={"layer": layer.layer, "county_code": county_code, "layer_absent": True},
        inputs=[InputRef(kind="manifest", ref_id=manifest_id)],
        rules=[LAYERS_RULE],
    ) as context:
        context.set_rows(0)
        context.set_output_hash(
            hash_payload({"rows": 0, "manifest_id": manifest_id, "layer": layer.layer})
        )
    return context.derivation_id, 0, 0


def _stage_layer(
    connection: psycopg.Connection,
    layer: TxLayer,
    payload_path: Path,
    manifest_id: str,
    county_code: str,
    *,
    datum: ConformanceRule,
) -> tuple[str, int, int]:
    source_epsg = int(datum.spec["source_epsg"])
    accepted = {int(code) for code in datum.spec["detect"]["accepted_epsg"]}
    if layer.optional and not _has_layer(payload_path, layer.suffix):
        return _absent_layer(layer, manifest_id, county_code)
    with ZippedShapefile(payload_path, layer_suffix=layer.suffix) as source:
        if source.source_epsg not in accepted:
            raise DatumMismatch(
                f"well{county_code}{layer.suffix}.prj resolves to EPSG:{source.source_epsg};"
                f" {datum.rule_id} accepts {sorted(accepted)} and never defaults a datum"
            )
        rows, rejected = _staging_rows(layer, source, manifest_id, county_code)

    columns = ", ".join(layer.columns)
    placeholders = ", ".join(f"%({column})s" for column in layer.columns)
    statement = (
        f"insert into {layer.staging_table}"
        f" (manifest_id, source_row_ordinal, source_county_code, {columns}, geom)"
        f" values (%(manifest_id)s, %(source_row_ordinal)s, %(source_county_code)s,"
        f" {placeholders}, ST_GeomFromText(%(geom_wkt)s, {source_epsg}))"
        " on conflict (manifest_id, source_row_ordinal) do nothing"
    )
    with derive(
        "stage.parse",
        output=OutputSpec(
            store="postgis",
            dataset=layer.staging_table,
            partition={"manifest_id": manifest_id, "county_code": county_code},
        ),
        params={
            "layer": layer.layer,
            "county_code": county_code,
            "source_epsg": source_epsg,
            "loaded_in_source_crs": True,
        },
        inputs=[InputRef(kind="manifest", ref_id=manifest_id)],
        rules=[LAYERS_RULE],
    ) as context:
        with connection.cursor() as cursor:
            cursor.executemany(statement, rows)
        context.set_rows(len(rows))
        context.set_output_hash(
            hash_payload({"rows": len(rows), "manifest_id": manifest_id, "layer": layer.layer})
        )
    held = _quarantine(
        connection,
        _quarantine_frame(rejected),
        layer=layer,
        manifest_id=manifest_id,
        reason_code="parse_error",
        stage="parse",
    )
    return context.derivation_id, len(rows), held


def _arc_feet(geometry) -> float:
    """The arc's geodesic length, measured the way cr_tx_compute_crs_1 measures every other."""
    coords = [point for part in getattr(geometry, "geoms", [geometry]) for point in part.coords]
    metres = sum(_geod().inv(a[0], a[1], b[0], b[1])[2] for a, b in pairwise(coords))
    return abs(metres) / float(METRES_PER_FOOT)


def _head(geometry) -> tuple[float, float]:
    """The arc's first vertex — the wellbore head, which is where two arcs for one wellbore
    are compared. An arc with no vertices has no position to be a duplicate of."""
    for part in getattr(geometry, "geoms", [geometry]):
        for point in part.coords:
            return float(point[0]), float(point[1])
    raise ValueError("an arc carrying no vertices cannot be promoted or displaced")


def _quarantine_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    """Scan every row for the schema: a column that is null for the first 100 rows and a
    wellbore code after them is a real shape of this data, not a malformed frame."""
    return pl.DataFrame(rows, infer_schema_length=None)


def _quarantine(
    connection: psycopg.Connection,
    rows: pl.DataFrame,
    *,
    layer: TxLayer,
    manifest_id: str,
    reason_code: str,
    stage: str,
    rule_id: str | None = None,
) -> int:
    if rows.is_empty():
        return 0
    session = current_session()
    quarantine(
        connection,
        rows,
        reason_code=reason_code,
        manifest_id=manifest_id,
        source_id=SOURCE_ID,
        staging_table=layer.staging_table,
        stage=stage,
        seen_at=session.clock.now(),
        rule_id=rule_id,
        correlation_id=session.correlation_id,
    )
    return rows.height


_POINTS = """
select source_row_ordinal, source_county_code, api, {extra}
       ST_X(geom) as lon27, ST_Y(geom) as lat27,
       nullif(long83, '')::double precision as lon83,
       nullif(lat83, '')::double precision as lat83
  from {table}
 where manifest_id = %s and geom is not null
 order by source_row_ordinal
"""

_LINES = """
select source_row_ordinal, source_county_code, api, stcode, ST_AsText(geom) as wkt
  from staging.tx_gis_wells_lines
 where manifest_id = %s and geom is not null
 order by source_row_ordinal
"""


def _read(connection: psycopg.Connection, sql: str, manifest_id: str) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(sql, (manifest_id,))
        return cursor.fetchall()


def _keyed(
    rows: Sequence[Mapping[str, Any]],
    api10_rule: ConformanceRule,
    scope_rule: ConformanceRule,
    extra: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list]:
    """API-10 through the key rule, so the state prefix is never a literal in this module.

    The scope predicate judges the **feature's own county**, read from the first three
    characters of the API the RRC gave it, not the county the archive is named for. Those two
    disagree for 520 surface features across the 55 archives, and 23 of them carry a county
    outside the scope list entirely. Scoping on the archive name made the predicate compare a
    value against the list it had just been assigned from, so it could never fire and the
    disagreeing features landed as wells whose identity the export - which scopes on the
    record's own county - had already excluded.
    """
    if not rows:
        return [], []
    state_code = str(api10_rule.spec["state_code"])
    # Declared, not inferred: `stcode` is empty on the first thousand bottom-holes and a
    # wellbore code after them, and an inferred Null column then refuses the first real value.
    frame = pl.DataFrame(
        [
            {
                "source_row_ordinal": row["source_row_ordinal"],
                "archive_county_code": row["source_county_code"],
                "feature_county_code": (row["api"] or "")[:COUNTY_CODE_WIDTH],
                "api": (row["api"] or ""),
                "state_code": state_code,
                **{name: row.get(name) or "" for name in extra},
            }
            for row in rows
        ],
        schema={
            "source_row_ordinal": pl.Int32,
            "archive_county_code": pl.String,
            "feature_county_code": pl.String,
            "api": pl.String,
            "state_code": pl.String,
            **dict.fromkeys(extra, pl.String),
        },
    )
    applied = apply_rules(frame, [scope_rule, api10_rule])
    return applied.frame.to_dicts(), applied.quarantined


@lru_cache(maxsize=1)
def _geod():
    from pyproj import Geod

    return Geod(ellps="WGS84")


def _metres_apart(lon_a: float, lat_a: float, lon_b: float, lat_b: float) -> float:
    """Geodesic, not a degree scale factor. The flat approximation this replaced used a fixed
    111,132 m per degree of latitude against ~110,895 at 32.4N, which overstated every residual
    it reported by 0.21 percent — immaterial at 4 mm, and the wrong instrument to measure a
    transform with when the ellipsoid is right there."""
    _, _, metres = _geod().inv(lon_a, lat_a, lon_b, lat_b)
    return abs(metres)


def _residuals(
    transformed: Sequence[tuple[float, float]],
    source: Sequence[tuple[float, float]],
    published: Sequence[tuple[float, float]],
) -> dict[str, float]:
    """The datum truth set, in band: the RRC publishes NAD83 columns beside the NAD27 geometry.

    Both halves of the guard are measured here — how close the transform lands to the
    regulator's own converted coordinate, and how far the untransformed coordinate would have
    been. A guard that cannot fail loudly is not a guard (SB-01 P7b-T2).

    Rows whose published pair is identical to the NAD27 pair were never converted upstream;
    scoring against them would measure the RRC's omission, so they are counted instead.
    """
    residual: list[float] = []
    offset: list[float] = []
    unconverted = 0
    for (lon, lat), (lon27, lat27), (lon83, lat83) in zip(
        transformed, source, published, strict=True
    ):
        if lon83 is None or lat83 is None:
            continue
        # A tolerance, not equality: the shipped geometry and the DBF's own decimal columns
        # differ in the last millimetre, so an exact test never fires and 602 of Andrews'
        # 27,704 rows - whose published NAD83 pair the RRC never converted - would be scored
        # against the transform as if they had been.
        if abs(lon83 - lon27) < UNCONVERTED_DEGREES and abs(lat83 - lat27) < UNCONVERTED_DEGREES:
            unconverted += 1
            continue
        residual.append(_metres_apart(lon, lat, lon83, lat83))
        offset.append(_metres_apart(lon27, lat27, lon83, lat83))
    if not residual:
        return {"unconverted_rows": float(unconverted)}
    ordered = sorted(residual)
    return {
        "n": float(len(ordered)),
        "median": ordered[len(ordered) // 2],
        "p99": ordered[min(len(ordered) - 1, int(len(ordered) * 0.99))],
        "max": ordered[-1],
        # The share is the guard, not the maximum: a few RRC rows carry a published NAD83 pair
        # that was never converted, and one of those sets a maximum in kilometres while saying
        # nothing at all about the transform.
        "within_1m": sum(1 for metres in ordered if metres <= 1.0) / len(ordered),
        "untransformed_median": sorted(offset)[len(offset) // 2],
        "unconverted_rows": float(unconverted),
    }


_INSERT_WELL = """
insert into canonical.wells (api10, state_code, county_code_at_permit, basin, effective_from,
                             source_manifest_id, derivation_id)
select %(api10)s, %(state_code)s, %(county_code)s, %(basin)s, %(effective_from)s,
       %(manifest_id)s, %(derivation_id)s
 where not exists (select 1 from canonical.wells
                    where api10 = %(api10)s and effective_from = %(effective_from)s)
"""

_INSERT_SPATIAL = """
insert into canonical.well_spatial (api10, geom_type, geom_key, geom, source_datum,
                                    transform_rule_id, source_manifest_id, derivation_id)
values (%(api10)s, %(geom_type)s, %(geom_key)s,
        ST_SetSRID(ST_GeomFromText(%(wkt)s), %(storage_epsg)s), %(source_datum)s,
        %(transform_rule_id)s, %(manifest_id)s, %(derivation_id)s)
on conflict (api10, geom_type, geom_key) do nothing
"""


def _promote_points(
    connection: psycopg.Connection,
    layer: TxLayer,
    *,
    manifest_id: str,
    county_code: str,
    vintage: date,
    parse_derivation_id: str,
    datum: ConformanceRule,
    transformer,
    grid_manifest_id: str,
    api10_rule: ConformanceRule,
    scope_rule: ConformanceRule,
    counts: dict[str, int],
) -> tuple[str, int, int, dict[str, float]]:
    extra = {"stcode": None} if layer.layer == "bottomhole" else {}
    columns = "stcode," if layer.layer == "bottomhole" else ""
    rows = _read(
        connection, _POINTS.format(table=layer.staging_table, extra=columns), manifest_id
    )
    keyed, rejected = _keyed(rows, api10_rule, scope_rule, extra)
    for batch in rejected:
        counts[batch.reason_code] = counts.get(batch.reason_code, 0) + _quarantine(
            connection, batch.frame, layer=layer, manifest_id=manifest_id,
            reason_code=batch.reason_code, stage="join", rule_id=batch.rule_id,
        )
    by_ordinal = {row["source_row_ordinal"]: row for row in rows}
    lons, lats = _transform(
        transformer,
        [by_ordinal[row["source_row_ordinal"]]["lon27"] for row in keyed],
        [by_ordinal[row["source_row_ordinal"]]["lat27"] for row in keyed],
    )
    published = [
        (by_ordinal[row["source_row_ordinal"]]["lon83"],
         by_ordinal[row["source_row_ordinal"]]["lat83"])
        for row in keyed
    ]
    source = [
        (by_ordinal[row["source_row_ordinal"]]["lon27"],
         by_ordinal[row["source_row_ordinal"]]["lat27"])
        for row in keyed
    ]
    residuals = _residuals(list(zip(lons, lats, strict=True)), source, published)

    storage_epsg = int(datum.spec["target_epsg"])
    payload: list[dict[str, Any]] = []
    # The row that took the key, so a displaced one can be read against what displaced it.
    promoted_at: dict[tuple[str, str], tuple[float, float, int]] = {}
    duplicates: list[dict[str, Any]] = []
    for row, lon, lat in zip(keyed, lons, lats, strict=True):
        geom_key = (
            (row.get("stcode") or BOTTOMHOLE_DEFAULT_KEY)
            if layer.layer == "bottomhole"
            else "surface"
        )
        key = (row["api10"], geom_key)
        if key in promoted_at:
            # A verdict a reader cannot check is not a verdict. The payload carries both
            # positions and how far apart they are, because "duplicate" is a claim about
            # distance and the two rows are sometimes tens of kilometres apart.
            kept_lon, kept_lat, kept_ordinal = promoted_at[key]
            duplicates.append(
                {
                    **row,
                    "geom_key": geom_key,
                    "lon": lon,
                    "lat": lat,
                    "promoted_lon": kept_lon,
                    "promoted_lat": kept_lat,
                    "promoted_source_row_ordinal": kept_ordinal,
                    "metres_from_promoted": round(
                        _metres_apart(lon, lat, kept_lon, kept_lat), 3
                    ),
                }
            )
            continue
        promoted_at[key] = (lon, lat, row["source_row_ordinal"])
        payload.append(
            {
                "api10": row["api10"],
                "geom_type": layer.layer,
                "geom_key": geom_key,
                "wkt": f"POINT({lon!r} {lat!r})",
                "storage_epsg": storage_epsg,
                "source_datum": f"EPSG:{int(datum.spec['source_epsg'])}",
                "transform_rule_id": datum.rule_id,
                "manifest_id": manifest_id,
                "state_code": str(api10_rule.spec["state_code"]),
                "county_code": county_code,
                "basin": BASIN,
                "effective_from": vintage,
            }
        )
    counts["duplicate_row"] += _quarantine(
        connection, _quarantine_frame(duplicates), layer=layer, manifest_id=manifest_id,
        reason_code="duplicate_row", stage="conform", rule_id=SURVIVOR_RULE,
    )

    with derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgis",
            dataset="canonical.well_spatial",
            partition={"manifest_id": manifest_id, "geom_type": layer.layer},
        ),
        params={
            "layer": layer.layer,
            "county_code": county_code,
            "source_epsg": int(datum.spec["source_epsg"]),
            "storage_epsg": storage_epsg,
            "pipeline": str(datum.spec["pipeline"]).format(grid_path=GRID_KEY),
            "datum_residual_m": residuals,
        },
        inputs=[
            InputRef(kind="derivation", ref_id=parse_derivation_id),
            InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage),
            InputRef(kind="manifest", ref_id=grid_manifest_id),
        ],
        rules=[datum.rule_id, api10_rule.rule_id],
    ) as context:
        context.set_rows(len(payload))
        context.set_output_hash(
            hash_payload(
                json_ready({"keys": sorted(f"{a}/{k}" for a, k in sorted(promoted_at))})
            )
        )

    added = 0
    with connection.cursor() as cursor:
        if layer.layer == "surface":
            # The spatial layer is the well universe: an API the identity export never listed
            # still belongs on the map, and the row says only what the GIS file knows.
            cursor.executemany(
                _INSERT_WELL,
                [{**row, "derivation_id": context.derivation_id} for row in payload],
            )
            added = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        cursor.executemany(
            _INSERT_SPATIAL,
            [{**row, "derivation_id": context.derivation_id} for row in payload],
        )
    return context.derivation_id, len(payload), added, residuals


def _promote_lines(
    connection: psycopg.Connection,
    *,
    manifest_id: str,
    county_code: str,
    vintage: date,
    parse_derivation_id: str,
    datum: ConformanceRule,
    transformer,
    grid_manifest_id: str,
    api10_rule: ConformanceRule,
    scope_rule: ConformanceRule,
    wellbore_rule: ConformanceRule,
    bounds_rule: ConformanceRule,
    method: LengthMethod,
    counts: dict[str, int],
) -> tuple[str, int]:
    from shapely import ops
    from shapely import wkt as shapely_wkt

    layer = LAYERS["lines"]
    rows = _read(connection, _LINES, manifest_id)
    keyed, rejected = _keyed(rows, api10_rule, scope_rule, {"stcode": None})
    for batch in rejected:
        counts[batch.reason_code] = counts.get(batch.reason_code, 0) + _quarantine(
            connection, batch.frame, layer=layer, manifest_id=manifest_id,
            reason_code=batch.reason_code, stage="join", rule_id=batch.rule_id,
        )
    wellbore = (
        apply_rules(pl.DataFrame(keyed, infer_schema_length=None), [wellbore_rule])
        if keyed
        else None
    )
    if wellbore is not None:
        for batch in wellbore.quarantined:
            counts[batch.reason_code] = counts.get(batch.reason_code, 0) + _quarantine(
                connection, batch.frame, layer=layer, manifest_id=manifest_id,
                reason_code=batch.reason_code, stage="join", rule_id=batch.rule_id,
            )
    arcs = wellbore.frame.to_dicts() if wellbore is not None else []
    by_ordinal = {row["source_row_ordinal"]: row for row in rows}

    def project(x, y):
        ys, xs = transformer.transform(list(y), list(x))
        return xs, ys

    storage_epsg = int(datum.spec["target_epsg"])
    ceiling_ft = float(bounds_rule.spec["max_length_ft"])
    payload: list[dict[str, Any]] = []
    # The arc that took the key, so a displaced one can be read against what displaced it.
    promoted_at: dict[tuple[str, str], tuple[float, float, int]] = {}
    duplicates: list[dict[str, Any]] = []
    implausible: list[dict[str, Any]] = []
    for row in arcs:
        key = (row["api10"], row["geom_key"])
        geometry = shapely_wkt.loads(by_ordinal[row["source_row_ordinal"]]["wkt"])
        if key in promoted_at:
            kept_lon, kept_lat, kept_ordinal = promoted_at[key]
            lon, lat = _head(ops.transform(project, geometry))
            duplicates.append(
                {
                    **row,
                    "lon": lon,
                    "lat": lat,
                    "promoted_lon": kept_lon,
                    "promoted_lat": kept_lat,
                    "promoted_source_row_ordinal": kept_ordinal,
                    "metres_from_promoted": round(
                        _metres_apart(lon, lat, kept_lon, kept_lat), 3
                    ),
                }
            )
            continue
        # Measured before promotion, so a sixty-mile straight line never reaches a card, a
        # tile or a length statistic — the length is the thing being judged.
        feet = _arc_feet(geometry)
        if feet > ceiling_ft:
            implausible.append({**row, "length_ft": round(feet, 1), "ceiling_ft": ceiling_ft})
            continue
        projected = ops.transform(project, geometry)
        promoted_at[key] = (*_head(projected), row["source_row_ordinal"])
        payload.append(
            {
                "api10": row["api10"],
                "geom_type": "lateral",
                "geom_key": row["geom_key"],
                "wkt": projected.wkt,
                "storage_epsg": storage_epsg,
                "source_datum": f"EPSG:{int(datum.spec['source_epsg'])}",
                "transform_rule_id": datum.rule_id,
                "manifest_id": manifest_id,
            }
        )
    counts["duplicate_row"] += _quarantine(
        connection, _quarantine_frame(duplicates), layer=layer, manifest_id=manifest_id,
        reason_code="duplicate_row", stage="conform", rule_id=SURVIVOR_RULE,
    )
    counts["unreliable_numeric"] = counts.get("unreliable_numeric", 0) + _quarantine(
        connection, _quarantine_frame(implausible), layer=layer, manifest_id=manifest_id,
        reason_code="unreliable_numeric", stage="validate", rule_id=bounds_rule.rule_id,
    )

    with derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgis",
            dataset="canonical.well_spatial",
            partition={"manifest_id": manifest_id, "geom_type": "lateral"},
        ),
        params={
            "layer": "lateral",
            "county_code": county_code,
            "length_method": method.method,
            "compute_epsg": method.compute_epsg,
            "length_rule": method.rule_id,
            "storage_epsg": storage_epsg,
        },
        inputs=[
            InputRef(kind="derivation", ref_id=parse_derivation_id),
            InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage),
            InputRef(kind="manifest", ref_id=grid_manifest_id),
        ],
        rules=[datum.rule_id, api10_rule.rule_id, wellbore_rule.rule_id, method.rule_id],
    ) as context:
        context.set_rows(len(payload))
        context.set_output_hash(
            hash_payload(json_ready({"keys": sorted(f"{a}/{k}" for a, k in sorted(promoted_at))}))
        )
    with connection.cursor() as cursor:
        cursor.executemany(
            _INSERT_SPATIAL,
            [{**row, "derivation_id": context.derivation_id} for row in payload],
        )
    return context.derivation_id, len(payload)


_WELLBORE_CODES = """
select api10, count(distinct code) as wellbores,
       string_agg(distinct code, ',' order by code) as codes
  from (select %(state_code)s || b.api as api10,
               coalesce(nullif(b.stcode, ''), %(default_key)s) as code
          from staging.tx_gis_wells_bottomhole b
         where b.manifest_id = %(manifest_id)s and length(b.api) = %(api_width)s
        union
        select %(state_code)s || l.api, coalesce(nullif(l.stcode, ''), %(default_key)s)
          from staging.tx_gis_wells_lines l
         where l.manifest_id = %(manifest_id)s and length(l.api) = %(api_width)s) codes
 group by api10
having count(distinct code) > 1
 order by api10
"""


def _flag_multi_wellbore(
    connection: psycopg.Connection,
    *,
    manifest_id: str,
    api10_rule: ConformanceRule,
    api_width: int,
    counts: dict[str, int],
) -> int:
    """One quarantine row per API-10 the RRC gives more than one wellbore code (§3.0.5).

    A measurement, not a removal: every wellbore keeps its geometry. Keyed on the wellbore code
    because that is the API-12 fact in the regulator's own notation — counting an API-10's rows
    in the identity export measures how many completions it reports, which is a different thing
    and 96.3 percent of the time a larger one.
    """
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            _WELLBORE_CODES,
            {
                "manifest_id": manifest_id,
                "state_code": str(api10_rule.spec["state_code"]),
                "default_key": BOTTOMHOLE_DEFAULT_KEY,
                "api_width": api_width,
            },
        )
        multi = cursor.fetchall()
    held = _quarantine(
        connection,
        _quarantine_frame([dict(row) for row in multi]),
        layer=LAYERS["bottomhole"],
        manifest_id=manifest_id,
        reason_code="multi_wellbore_policy",
        stage="validate",
        rule_id=MULTI_WELLBORE_RULE,
    )
    counts["multi_wellbore_policy"] = counts.get("multi_wellbore_policy", 0) + held
    return held


def _length_stats(
    connection: psycopg.Connection, derivation_id: str, method: LengthMethod
) -> dict[str, float]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select min(feet), percentile_cont(0.5) within group (order by feet), max(feet),"
            "       count(*)"
            f"  from (select {method.metres_sql()} / %s as feet"
            "          from canonical.well_spatial"
            "         where derivation_id = %s and geom_type = 'lateral') lengths",
            (float(METRES_PER_FOOT), derivation_id),
        )
        minimum, median, maximum, rows = cursor.fetchone()
    if not rows:
        return {}
    return {
        "min_ft": float(minimum),
        "median_ft": float(median),
        "max_ft": float(maximum),
        "rows": float(rows),
    }


def _already_promoted(connection: psycopg.Connection, manifest_id: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "select 1 from canonical.well_spatial where source_manifest_id = %s limit 1",
            (manifest_id,),
        )
        return cursor.fetchone() is not None


def _require_identity(
    connection: psycopg.Connection, county_code: str, vintage: date, state_code: str
) -> None:
    """SB-01 §1.1 promote_requires, enforced: identity first, or the well loses its operator.

    canonical.wells is keyed (api10, effective_from). If the spatial pass wrote a bare row for
    an API first, the identity pass's insert at the same vintage would be skipped by its own
    conflict clause and the well would silently keep no operator, status or depth.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "select 1 from canonical.wells"
            " where state_code = %s and effective_from = %s"
            "   and operator_name_reported is not null limit 1",
            (state_code, vintage),
        )
        if cursor.fetchone() is None:
            raise IdentityNotPromoted(
                f"no TX identity is promoted at vintage {vintage}, so county {county_code}'s"
                " wells would land with no operator and could never gain one at this vintage:"
                " run `python -m glasswell.ingest.tx_wellbore` before the GIS layers"
            )


def load_county(
    connection: psycopg.Connection,
    county_code: str,
    *,
    url: str | None = None,
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
    grid_client: httpx.Client | None = None,
    restage: bool = False,
) -> CountyLoad:
    """Fetch one county archive, stage its three layers and promote geometry for the state."""
    datum = _rule(connection, DATUM_RULE)
    api10_rule = _rule(connection, API10_RULE)
    wellbore_rule = _rule(connection, WELLBORE_KEY_RULE)
    scope_rule = _rule(connection, SCOPE_RULE)
    bounds_rule = _rule(connection, BOUNDS_RULE)
    method = length_method(compute_crs_rule(load_rules(connection, source_id=SOURCE_ID)))
    scope = tuple(str(code) for code in scope_rule.spec["county_codes"])
    if county_code not in scope:
        raise ValueError(
            f"county {county_code} is outside {SCOPE_RULE}; widen the rule, not the caller"
        )
    name = archive_name(connection, county_code)
    grid_path, grid_manifest_id = ensure_grid(
        connection, datum, raw_root=raw_root, client=grid_client
    )
    transformer = datum_transformer(datum, grid_path)

    fetched = fetch_raw(
        connection,
        SOURCE_ID,
        name,
        url=url or f"{GIS_LINK}?filename={name}",
        acquisition_method="mft_guid_resolve",
        raw_root=raw_root,
        client=client,
        media_type="application/zip",
    )
    manifest = fetched.manifest
    counts = dict.fromkeys(REASON_CODES, 0)
    if restage:
        with connection.cursor() as cursor:
            for layer in LAYERS.values():
                cursor.execute(
                    f"delete from {layer.staging_table} where manifest_id = %s",
                    (manifest.manifest_id,),
                )
    elif _already_promoted(connection, manifest.manifest_id):
        return CountyLoad(
            county_code=county_code,
            manifest_id=manifest.manifest_id,
            staged={},
            wells_added=0,
            geometries={},
            quarantined=counts,
            unchanged=True,
        )
    _require_identity(
        connection, county_code, manifest.fetch_vintage, str(api10_rule.spec["state_code"])
    )

    staged: dict[str, int] = {}
    parse_ids: dict[str, str] = {}
    for layer in LAYERS.values():
        parse_id, rows, held = _stage_layer(
            connection, layer, fetched.payload_path, manifest.manifest_id, county_code,
            datum=datum,
        )
        staged[layer.layer] = rows
        parse_ids[layer.layer] = parse_id
        counts["parse_error"] += held

    geometries: dict[str, int] = {}
    residuals: dict[str, float] = {}
    wells_added = 0
    for name_ in ("surface", "bottomhole"):
        _, promoted, added, measured = _promote_points(
            connection,
            LAYERS[name_],
            manifest_id=manifest.manifest_id,
            county_code=county_code,
            vintage=manifest.fetch_vintage,
            parse_derivation_id=parse_ids[name_],
            datum=datum,
            transformer=transformer,
            grid_manifest_id=grid_manifest_id,
            api10_rule=api10_rule,
            scope_rule=scope_rule,
            counts=counts,
        )
        geometries[name_] = promoted
        wells_added += added
        if name_ == "surface":
            residuals = measured

    lateral_id, laterals = _promote_lines(
        connection,
        manifest_id=manifest.manifest_id,
        county_code=county_code,
        vintage=manifest.fetch_vintage,
        parse_derivation_id=parse_ids["lines"],
        datum=datum,
        transformer=transformer,
        grid_manifest_id=grid_manifest_id,
        api10_rule=api10_rule,
        scope_rule=scope_rule,
        wellbore_rule=wellbore_rule,
        bounds_rule=bounds_rule,
        method=method,
        counts=counts,
    )
    geometries["lateral"] = laterals
    multi_wellbore = _flag_multi_wellbore(
        connection,
        manifest_id=manifest.manifest_id,
        api10_rule=api10_rule,
        api_width=int(api10_rule.spec["min_width"]["api"]),
        counts=counts,
    )

    # A backfill loads many counties in one day, all upserting one (source, day) ledger row —
    # accumulate onto it rather than letting each county overwrite the last (DR-85).
    record_vintage_day(
        connection,
        source_id=SOURCE_ID,
        vintage_date=manifest.fetch_vintage,
        manifest_ids=[manifest.manifest_id],
        opened_at=current_session().clock.now(),
        promotion_derivation_id=lateral_id,
        rows_examined=sum(staged.values()),
        rows_appended=sum(geometries.values()),
    )
    return CountyLoad(
        county_code=county_code,
        manifest_id=manifest.manifest_id,
        staged=staged,
        wells_added=wells_added,
        geometries=geometries,
        quarantined=counts,
        datum_residual_m=residuals,
        length_stats_ft=_length_stats(connection, lateral_id, method),
        multi_wellbore_api10s=multi_wellbore,
    )


def load_scope(
    connection: psycopg.Connection,
    counties: Iterable[str] | None = None,
    *,
    raw_root: Path | str | None = None,
    restage: bool = False,
) -> list[CountyLoad]:
    """One connection to the portal, one pull per county archive, in listing order."""
    wanted = tuple(counties) if counties is not None else county_scope(connection)
    results: list[CountyLoad] = []
    with MftClient(GIS_LINK) as mft:
        for county_code in wanted:
            name = archive_name(connection, county_code)
            results.append(
                load_county(
                    connection,
                    county_code,
                    url=mft.url_for(name),
                    client=mft.client,
                    raw_root=raw_root,
                    restage=restage,
                )
            )
            connection.commit()
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load TX RRC county GIS well layers into PostGIS.")
    parser.add_argument("--dsn", required=True)
    parser.add_argument(
        "--county", action="append", default=None, help="county code; repeatable, default is scope"
    )
    parser.add_argument("--raw-root", default=None)
    parser.add_argument("--env-id", default=None, help="override the fingerprinted env id")
    parser.add_argument("--code-version", default=None)
    parser.add_argument("--restage", action="store_true")
    arguments = parser.parse_args(argv)

    with psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        with lineage_session(recorder=PostgresRecorder(connection), environment=environment):
            for result in load_scope(
                connection,
                arguments.county,
                raw_root=arguments.raw_root,
                restage=arguments.restage,
            ):
                print(json.dumps(result.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
