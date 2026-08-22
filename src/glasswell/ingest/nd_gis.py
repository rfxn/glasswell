"""Load the ND DMR GIS layers into staging and canonical (blueprint §2, SB-01 §2).

Every coordinate reaches storage through the seeded datum rule, and lateral length is
computed in the projected CRS the registry names — never from the shipped SHAPE_Leng.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import psycopg
from psycopg.rows import dict_row

from glasswell.ingest.base import record_vintage_day, resolve_environment
from glasswell.ingest.shapefile import ShapefileRecord, ZippedShapefile
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
from glasswell.lineage.conformance import rule_for_family
from glasswell.lineage.errors import RuleSpecError
from glasswell.lineage.serialization import hash_payload, json_ready
from glasswell.units import METRES_PER_FOOT

BASE_URL = "https://gis.dmr.nd.gov/downloads/oilgas/shapefile"
DATUM_RULE_SOURCE = "nd_gis_wells"
LAND_UNIT_RULE_ID = "cr_nd_land_unit_1"
SEGMENT_FAMILY = "cr_nd_segment_vocab"
SURVEY_SEGMENT_FAMILY = "cr_nd_survey_segment_vocab"
SURVEY_TRACE_GEOM_TYPE = "survey_trace"
_LINEKEY = re.compile(r"\A(?P<api14>\d{14})_(?P<segment>[A-Za-z]+)(?P<ordinal>\d*)\Z")


class SchemaDrift(ValueError):
    """The shipped DBF no longer carries a column the staging table declares."""


class DatumMismatch(ValueError):
    """The shipped .prj disagrees with the datum the conformance registry declares."""


@dataclass(frozen=True, slots=True)
class LayerSpec:
    layer: str
    source_id: str
    source_key: str
    staging_table: str
    canonical_table: str
    columns: tuple[str, ...]
    geometry_type: str
    reason_codes: tuple[str, ...] = ()
    # OGD_Directionals.zip ships two shapefiles; picking one by stem suffix is a declaration,
    # where relying on the reader's member scan order would be an accident that holds.
    layer_suffix: str | None = None


LAYERS: Mapping[str, LayerSpec] = {
    "wells": LayerSpec(
        layer="wells",
        source_id="nd_gis_wells",
        source_key="OGD_Wells.zip",
        staging_table="staging.nd_gis_wells",
        canonical_table="canonical.wells",
        columns=(
            "fileno", "api_no", "operator", "well_name", "td", "spud_date", "field_name", "qq",
            "sec", "twp", "rng", "feet_ns", "fnsl", "feet_ew", "fewl", "latitude", "longitude",
            "well_type", "status", "api", "county", "symbol",
        ),
        geometry_type="Point",
        reason_codes=("datum_undetermined", "unknown_vocab", "out_of_range_date", "parse_error"),
    ),
    "laterals": LayerSpec(
        layer="laterals",
        source_id="nd_gis_horizontals_line",
        source_key="OGD_Horizontals_Line.zip",
        staging_table="staging.nd_gis_laterals",
        canonical_table="canonical.well_spatial",
        columns=("linekey", "fileno", "shape_leng"),
        # The layer ships multi-part centrelines; the staging column holds any geometry (017).
        geometry_type="Geometry",
        reason_codes=(
            "parse_error", "segment_not_promoted", "multi_wellbore_policy", "orphan_fk",
        ),
    ),
    "spacing_units": LayerSpec(
        layer="spacing_units",
        source_id="nd_gis_spacing_units",
        source_key="OGD_DrillingSpacingUnits.zip",
        staging_table="staging.nd_gis_spacing_units",
        canonical_table="canonical.spacing_units",
        columns=(
            "formation", "refcode", "caseno", "orderno", "welltype", "mapsymbol", "dssize",
            "dstype",
        ),
        geometry_type="MultiPolygon",
        reason_codes=("parse_error", "duplicate_row"),
    ),
    "surveys": LayerSpec(
        layer="surveys",
        source_id="nd_gis_directionals",
        source_key="OGD_Directionals.zip",
        staging_table="staging.nd_gis_directionals",
        canonical_table="canonical.well_spatial",
        columns=(
            "wl_permit", "api_wellno", "api_format", "long", "lat", "well_sub", "measdpth",
            "inclinatio", "azimuth", "tvd", "coordns", "coordnsdir", "coordew", "coordewdir",
            "surveytype",
        ),
        geometry_type="Point",
        reason_codes=(
            "parse_error", "key_incomplete", "segment_not_promoted", "unreliable_numeric",
            "insufficient_stations", "orphan_fk",
        ),
        layer_suffix="directionals",
    ),
}


@dataclass(frozen=True, slots=True)
class LineKey:
    """`<API14>_LAT1`, `<API14>_STK1` and `<API14>_VERT` all appear in the horizontals layer."""

    api14: str
    segment: str
    ordinal: int | None

    @property
    def api10(self) -> str:
        return self.api14[:10]

    @property
    def is_lateral(self) -> bool:
        return self.segment == "LAT"


@dataclass(frozen=True, slots=True)
class LoadResult:
    layer: str
    source_id: str
    manifest_id: str
    parse_derivation_id: str
    promote_derivation_id: str
    staged_rows: int
    promoted_rows: int
    quarantined: Mapping[str, int]
    unchanged: bool = False
    compute_epsg: int | None = None
    length_rule_id: str | None = None
    length_stats: Mapping[str, float] = field(default_factory=dict)
    multi_lateral_rate: float | None = None
    # Surveys promote at two grains under one derivation: promoted_rows counts the traces in
    # canonical.well_spatial, station_rows the stations behind them.
    station_rows: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "manifest_id": self.manifest_id,
            "staged_rows": self.staged_rows,
            "promoted_rows": self.promoted_rows,
            "station_rows": self.station_rows,
            "quarantined": dict(self.quarantined),
            "unchanged": self.unchanged,
            "length_stats": dict(self.length_stats),
        }


def parse_linekey(value: str) -> LineKey:
    match = _LINEKEY.match((value or "").strip())
    if match is None:
        raise ValueError(f"{value!r} is not an ND linekey (<API14>_LAT1, _STK1 or _VERT)")
    ordinal = match.group("ordinal")
    return LineKey(
        api14=match.group("api14"),
        segment=match.group("segment").upper(),
        ordinal=int(ordinal) if ordinal else None,
    )


def api10_from_linekey(value: str) -> str:
    return parse_linekey(value).api10


def load_wells(
    connection: psycopg.Connection,
    *,
    url: str | None = None,
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
) -> LoadResult:
    """Fetch OGD_Wells, stage it, and promote to canonical.wells + surface geometry."""
    return _load(connection, LAYERS["wells"], url=url, raw_root=raw_root, client=client)


def load_laterals(
    connection: psycopg.Connection,
    *,
    url: str | None = None,
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
    restage: bool = False,
) -> LoadResult:
    """Fetch OGD_Horizontals_Line, stage it, and promote lateral centrelines."""
    return _load(
        connection, LAYERS["laterals"], url=url, raw_root=raw_root, client=client, restage=restage
    )


def load_spacing_units(
    connection: psycopg.Connection,
    *,
    url: str | None = None,
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
) -> LoadResult:
    """Fetch OGD_DrillingSpacingUnits, stage it, and promote canonical.spacing_units."""
    return _load(connection, LAYERS["spacing_units"], url=url, raw_root=raw_root, client=client)


def load_surveys(
    connection: psycopg.Connection,
    *,
    url: str | None = None,
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
    restage: bool = False,
) -> LoadResult:
    """Fetch OGD_Directionals, stage its stations, and promote stations plus survey traces."""
    return _load(
        connection, LAYERS["surveys"], url=url, raw_root=raw_root, client=client, restage=restage
    )


def load_layer(connection: psycopg.Connection, layer: str, **kwargs: Any) -> LoadResult:
    return _load(connection, LAYERS[layer], **kwargs)


def _load(
    connection: psycopg.Connection,
    spec: LayerSpec,
    *,
    url: str | None = None,
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
    restage: bool = False,
) -> LoadResult:
    datum = _datum_rule(connection)
    source_epsg = int(datum.spec["source_epsg"])
    storage_epsg = int(datum.spec["target_epsg"])

    fetched = fetch_raw(
        connection,
        spec.source_id,
        spec.source_key,
        url=url or f"{BASE_URL}/{spec.source_key}",
        raw_root=raw_root,
        client=client,
        media_type="application/zip",
    )
    manifest = fetched.manifest
    if restage:
        # Re-derivation after a rule or schema change: staging is rebuildable from the raw
        # bytes, and the insert is conflict-skipping, so the old rows have to go first.
        _clear_staging(connection, spec, manifest.manifest_id)
    elif _already_promoted(connection, spec, manifest.manifest_id):
        parse_id, promote_id = _existing_derivations(connection, manifest.manifest_id)
        return LoadResult(
            layer=spec.layer,
            source_id=spec.source_id,
            manifest_id=manifest.manifest_id,
            parse_derivation_id=parse_id,
            promote_derivation_id=promote_id,
            staged_rows=0,
            promoted_rows=0,
            quarantined=dict.fromkeys(spec.reason_codes, 0),
            unchanged=True,
        )

    parse_id, staged_rows, parse_quarantined = _stage(
        connection,
        spec,
        fetched.payload_path,
        manifest.manifest_id,
        source_epsg=source_epsg,
        storage_epsg=storage_epsg,
    )
    result = _PROMOTERS[spec.layer](
        connection,
        spec,
        manifest_id=manifest.manifest_id,
        vintage=manifest.fetch_vintage,
        parse_derivation_id=parse_id,
        staged_rows=staged_rows,
        datum=datum,
    )
    counts = dict(result.quarantined)
    for reason, rows in parse_quarantined.items():
        counts[reason] = counts.get(reason, 0) + rows
    return replace(result, quarantined=counts)


def _datum_rule(connection: psycopg.Connection) -> ConformanceRule:
    """The transform belongs to the registry, so its EPSG pair is read, never written here."""
    for rule in load_rules(connection, source_id=DATUM_RULE_SOURCE, stage="conform"):
        if rule.rule_kind == "datum_transform":
            return rule
    raise LookupError(f"no datum_transform rule is seeded for {DATUM_RULE_SOURCE}")


def _rule(connection: psycopg.Connection, source_id: str, rule_id: str) -> ConformanceRule:
    for rule in load_rules(connection, source_id=source_id):
        if rule.rule_id == rule_id:
            return rule
    raise LookupError(f"rule {rule_id} is not seeded for {source_id}")


def _already_promoted(connection: psycopg.Connection, spec: LayerSpec, manifest_id: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            f"select 1 from {spec.canonical_table} where source_manifest_id = %s limit 1",
            (manifest_id,),
        )
        return cursor.fetchone() is not None


def _clear_staging(connection: psycopg.Connection, spec: LayerSpec, manifest_id: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"delete from {spec.staging_table} where manifest_id = %s", (manifest_id,))
        return cursor.rowcount


def _existing_derivations(connection: psycopg.Connection, manifest_id: str) -> tuple[str, str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select operation, derivation_id from lineage.derivations"
            " where output_partition ->> 'manifest_id' = %s"
            "   and operation in ('stage.parse', 'canonical.promote')",
            (manifest_id,),
        )
        found = dict(cursor.fetchall())
    return found.get("stage.parse", ""), found.get("canonical.promote", "")


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    if isinstance(value, str):
        return value
    return str(value)


def _stage(
    connection: psycopg.Connection,
    spec: LayerSpec,
    payload_path: Path,
    manifest_id: str,
    *,
    source_epsg: int,
    storage_epsg: int,
) -> tuple[str, int, dict[str, int]]:
    with ZippedShapefile(payload_path, layer_suffix=spec.layer_suffix) as layer:
        if layer.source_epsg != source_epsg:
            raise DatumMismatch(
                f"{spec.source_key} ships EPSG:{layer.source_epsg}; the registry declares"
                f" EPSG:{source_epsg}"
            )
        rows, rejected = _staging_rows(spec, layer, manifest_id)

    geometry = f"ST_Transform(ST_GeomFromText(%(geom_wkt)s, {source_epsg}), {storage_epsg})"
    if spec.geometry_type.startswith("Multi"):
        geometry = f"ST_Multi({geometry})"
    columns = ", ".join(spec.columns)
    placeholders = ", ".join(f"%({column})s" for column in spec.columns)
    statement = (
        f"insert into {spec.staging_table} (manifest_id, source_row_ordinal, {columns}, geom)"
        f" values (%(manifest_id)s, %(source_row_ordinal)s, {placeholders}, {geometry})"
        " on conflict (manifest_id, source_row_ordinal) do nothing"
    )

    output = OutputSpec(
        store="postgres",
        dataset=spec.staging_table,
        partition={"manifest_id": manifest_id},
    )
    with derive(
        "stage.parse",
        output=output,
        params={"layer": spec.layer, "source_key": spec.source_key, "source_epsg": source_epsg},
        inputs=[InputRef(kind="manifest", ref_id=manifest_id)],
    ) as context:
        with connection.cursor() as cursor:
            cursor.executemany(statement, rows)
        context.set_rows(len(rows))
        context.set_output_hash(hash_payload({"rows": len(rows), "manifest_id": manifest_id}))

    quarantined = {
        "parse_error": _quarantine(
            connection,
            pl.DataFrame(rejected),
            spec,
            manifest_id=manifest_id,
            reason_code="parse_error",
            stage="parse",
        )
    }
    return context.derivation_id, len(rows), quarantined


def _staging_rows(
    spec: LayerSpec, layer: ZippedShapefile, manifest_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for record in layer:
        attributes = {key.lower(): value for key, value in record.attributes.items()}
        missing = [column for column in spec.columns if column not in attributes]
        if missing:
            raise SchemaDrift(f"{spec.source_key} has no {', '.join(missing)} field")
        row = {column: _text(attributes[column]) for column in spec.columns}
        row["manifest_id"] = manifest_id
        row["source_row_ordinal"] = record.ordinal
        note = _unstorable(record, spec.geometry_type)
        row["geom_wkt"] = None if note else record.geometry.wkt
        rows.append(row)
        if note:
            rejected.append(
                {key: value for key, value in row.items() if key != "geom_wkt"} | {"detail": note}
            )
    return rows, rejected


def _unstorable(record: ShapefileRecord, declared: str) -> str | None:
    """The staging column pins one geometry type; a shape that cannot be stored says so."""
    if record.is_empty:
        return "the source record carries no geometry"
    shape = record.geometry.geom_type
    if declared == "Geometry" or shape == declared:
        return None
    if declared.startswith("Multi") and f"Multi{shape}" == declared:
        return None
    return f"{shape} does not fit the declared {declared} column"


def _quarantine(
    connection: psycopg.Connection,
    rows: pl.DataFrame,
    spec: LayerSpec,
    *,
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
        source_id=spec.source_id,
        staging_table=spec.staging_table,
        stage=stage,
        seen_at=session.clock.now(),
        rule_id=rule_id,
        correlation_id=session.correlation_id,
    )
    return rows.height


def _staging_frame(
    connection: psycopg.Connection, sql: str, manifest_id: str, schema: Mapping[str, Any]
) -> pl.DataFrame:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(sql, (manifest_id,))
        records = cursor.fetchall()
    return pl.DataFrame(records, schema=dict(schema))


_WELLS_SELECT = """
select source_row_ordinal, api, api_no, fileno, operator, well_name, status, well_type,
       spud_date, sec, twp, rng, county, latitude::double precision as latitude,
       longitude::double precision as longitude
  from staging.nd_gis_wells
 where manifest_id = %s
 order by source_row_ordinal
"""

_WELLS_SCHEMA = {
    "source_row_ordinal": pl.Int32,
    "api": pl.String,
    "api_no": pl.String,
    "fileno": pl.String,
    "operator": pl.String,
    "well_name": pl.String,
    "status": pl.String,
    "well_type": pl.String,
    "spud_date": pl.String,
    "sec": pl.String,
    "twp": pl.String,
    "rng": pl.String,
    "county": pl.String,
    "latitude": pl.Float64,
    "longitude": pl.Float64,
}

_INSERT_WELL = """
insert into canonical.wells (
    api10, api14, state_code, county_code_at_permit, ndic_file_no, operator_name_reported,
    well_name, status_canonical, status_reported, well_type_reported, spud_date,
    confidential_flag, land_unit_label, effective_from, source_manifest_id, derivation_id)
values (%(api10)s, %(api14)s, %(state_code)s, %(county_code)s, %(ndic_file_no)s, %(operator)s,
        %(well_name)s, %(status_canonical)s, %(status_reported)s, %(well_type)s, %(spud_date)s,
        %(confidential)s, %(land_unit_label)s, %(effective_from)s, %(manifest_id)s,
        %(derivation_id)s)
on conflict (api10, effective_from) do nothing
"""

_INSERT_SURFACE = """
insert into canonical.well_spatial (
    api10, geom_type, geom_key, geom, source_datum, transform_rule_id, source_manifest_id,
    derivation_id)
values (%(api10)s, 'surface', 'surface',
        ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), %(storage_epsg)s),
        %(source_datum)s, %(transform_rule_id)s, %(manifest_id)s, %(derivation_id)s)
on conflict (api10, geom_type, geom_key) do nothing
"""


def _spud_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y%m%d").date()


def _promote_wells(
    connection: psycopg.Connection,
    spec: LayerSpec,
    *,
    manifest_id: str,
    vintage: date,
    parse_derivation_id: str,
    staged_rows: int,
    datum: ConformanceRule,
) -> LoadResult:
    frame = _staging_frame(connection, _WELLS_SELECT, manifest_id, _WELLS_SCHEMA)
    rules = [
        rule
        for rule in load_rules(connection, source_id=spec.source_id, stage="conform")
        # The code_ref executor is unimplemented in this slice: those rows are policy
        # records the serving surfaces cite (cr_nd_well_type_disposal_1), not frame
        # transforms — the same carve-out nd_mpr makes for its rollup rule.
        if rule.rule_kind != "code_ref"
    ]
    applied = apply_rules(frame, rules)

    counts = dict.fromkeys(spec.reason_codes, 0)
    for batch in applied.quarantined:
        counts[batch.reason_code] = counts.get(batch.reason_code, 0) + _quarantine(
            connection,
            batch.frame,
            spec,
            manifest_id=manifest_id,
            reason_code=batch.reason_code,
            stage="conform",
            rule_id=batch.rule_id,
        )

    label_format = str(_rule(connection, "nd_mpr_xlsx", LAND_UNIT_RULE_ID).spec["label_format"])
    confidential = _confidential_statuses(connection)
    storage_epsg = int(datum.spec["target_epsg"])
    source_datum = f"EPSG:{int(datum.spec['source_epsg'])}"

    wells: list[dict[str, Any]] = []
    undated: list[dict[str, Any]] = []
    for row in applied.frame.iter_rows(named=True):
        try:
            spud = _spud_date(row["spud_date"])
        except ValueError:
            undated.append(row)
            continue
        api14 = row["api"]
        wells.append(
            {
                "api10": api14[:10],
                "api14": api14,
                "state_code": api14[:2],
                "county_code": api14[2:5],
                "ndic_file_no": row["fileno"],
                "operator": row["operator"],
                "well_name": row["well_name"],
                "status_canonical": row["status_canonical"],
                "status_reported": row["status"],
                "well_type": row["well_type"],
                "spud_date": spud,
                "confidential": confidential.get(row["status"], False),
                "land_unit_label": _land_unit_label(label_format, row),
                "effective_from": vintage,
                "manifest_id": manifest_id,
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "storage_epsg": storage_epsg,
                "source_datum": source_datum,
                "transform_rule_id": datum.rule_id,
            }
        )
    if undated:
        counts["out_of_range_date"] = counts.get("out_of_range_date", 0) + _quarantine(
            connection,
            pl.DataFrame(undated),
            spec,
            manifest_id=manifest_id,
            reason_code="out_of_range_date",
            stage="conform",
        )

    output = OutputSpec(
        store="postgis", dataset=spec.canonical_table, partition={"manifest_id": manifest_id}
    )
    with derive(
        "canonical.promote",
        output=output,
        params={"layer": spec.layer, "storage_epsg": storage_epsg, "source_datum": source_datum},
        inputs=[
            InputRef(kind="derivation", ref_id=parse_derivation_id),
            InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage),
        ],
        rules=[*applied.applied_rule_ids, LAND_UNIT_RULE_ID],
    ) as context:
        context.set_rows(len(wells))
        context.set_output_hash(hash_payload(json_ready({"api10s": [w["api10"] for w in wells]})))

    derivation_id = context.derivation_id
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_WELL, [{**row, "derivation_id": derivation_id} for row in wells])
        cursor.executemany(
            _INSERT_SURFACE, [{**row, "derivation_id": derivation_id} for row in wells]
        )
    _open_vintage(connection, spec, manifest_id, vintage, derivation_id, staged_rows, len(wells))

    return LoadResult(
        layer=spec.layer,
        source_id=spec.source_id,
        manifest_id=manifest_id,
        parse_derivation_id=parse_derivation_id,
        promote_derivation_id=derivation_id,
        staged_rows=staged_rows,
        promoted_rows=len(wells),
        quarantined=counts,
    )


def _land_unit_label(label_format: str, row: Mapping[str, Any]) -> str | None:
    if not (row["twp"] and row["rng"] and row["sec"]):
        return None
    return label_format.format(twp=row["twp"], rng=row["rng"], sec=row["sec"])


def _confidential_statuses(connection: psycopg.Connection) -> dict[str, bool]:
    with connection.cursor() as cursor:
        cursor.execute("select status, confidential from lineage.nd_status_map")
        return {row[0]: row[1] for row in cursor.fetchall()}


_LATERALS_SELECT = """
select source_row_ordinal, linekey, fileno
  from staging.nd_gis_laterals
 where manifest_id = %s and geom is not null
 order by source_row_ordinal
"""

_LATERALS_SCHEMA = {
    "source_row_ordinal": pl.Int32,
    "linekey": pl.String,
    "fileno": pl.String,
}

# parse_linekey's output, declared so an empty layer still presents the columns the rule maps.
_PARSED_SCHEMA = {
    **_LATERALS_SCHEMA,
    "api10": pl.String,
    "segment": pl.String,
    "lateral_ordinal": pl.Int64,
}

_INSERT_LATERAL = """
insert into canonical.well_spatial (
    api10, geom_type, geom_key, geom, source_datum, transform_rule_id, source_manifest_id,
    derivation_id)
select %(api10)s, 'lateral', %(geom_key)s, geom, %(source_datum)s, %(transform_rule_id)s,
       %(manifest_id)s, %(derivation_id)s
  from staging.nd_gis_laterals
 where manifest_id = %(manifest_id)s and source_row_ordinal = %(source_row_ordinal)s
on conflict (api10, geom_type, geom_key) do nothing
"""


def _promote_laterals(
    connection: psycopg.Connection,
    spec: LayerSpec,
    *,
    manifest_id: str,
    vintage: date,
    parse_derivation_id: str,
    staged_rows: int,
    datum: ConformanceRule,
) -> LoadResult:
    # The family, not a pinned id: a supersession changes the id and must not be missed.
    directive = compute_crs_rule(load_rules(connection, source_id=spec.source_id))
    multilateral = _rule(connection, spec.source_id, "cr_nd_multilateral_1")
    method = length_method(directive)
    forbidden = str(directive.spec.get("forbidden_field", "")).lower()

    frame = _staging_frame(connection, _LATERALS_SELECT, manifest_id, _LATERALS_SCHEMA)
    if forbidden and forbidden in {column.lower() for column in frame.columns}:
        raise ValueError(f"{directive.rule_id}: {forbidden} is degrees and is never a length")

    counts = dict.fromkeys(spec.reason_codes, 0)
    parsed: list[dict[str, Any]] = []
    unparseable: list[dict[str, Any]] = []
    for row in frame.iter_rows(named=True):
        try:
            key = parse_linekey(row["linekey"])
        except ValueError:
            unparseable.append(row)
            continue
        parsed.append(
            {**row, "api10": key.api10, "segment": key.segment, "lateral_ordinal": key.ordinal}
        )
    counts["parse_error"] += _quarantine(
        connection,
        pl.DataFrame(unparseable),
        spec,
        manifest_id=manifest_id,
        reason_code="parse_error",
        stage="parse",
    )

    # The layer also ships vertical holes and sidetracks. Which of the three is a producing
    # centreline is a vocabulary, so it is a rule row, not a literal in this function.
    segment_rule = rule_for_family(
        load_rules(connection, source_id=spec.source_id, stage="conform"), SEGMENT_FAMILY
    )
    selected = apply_rules(pl.DataFrame(parsed, schema=_PARSED_SCHEMA), [segment_rule])
    laterals = selected.frame.to_dicts()
    for batch in selected.quarantined:
        counts[batch.reason_code] = counts.get(batch.reason_code, 0) + _quarantine(
            connection,
            batch.frame,
            spec,
            manifest_id=manifest_id,
            reason_code=batch.reason_code,
            stage="conform",
            rule_id=batch.rule_id,
        )

    per_well: dict[str, list[str]] = {}
    for row in laterals:
        per_well.setdefault(row["api10"], []).append(row["linekey"])
    multi = {api10: keys for api10, keys in per_well.items() if len(keys) > 1}
    counts[str(multilateral.spec["reason_code"])] += _quarantine(
        connection,
        pl.DataFrame(
            [
                {"api10": api10, "lateral_count": len(keys), "linekeys": ",".join(sorted(keys))}
                for api10, keys in sorted(multi.items())
            ]
        ),
        spec,
        manifest_id=manifest_id,
        reason_code=str(multilateral.spec["reason_code"]),
        stage="validate",
        rule_id=multilateral.rule_id,
    )

    known = _known_api10s(connection, per_well.keys())
    kept = [row for row in laterals if row["api10"] in known]
    orphans = [row for row in laterals if row["api10"] not in known]
    counts["orphan_fk"] += _quarantine(
        connection,
        pl.DataFrame(orphans),
        spec,
        manifest_id=manifest_id,
        reason_code="orphan_fk",
        stage="join",
    )

    output = OutputSpec(
        store="postgis", dataset=spec.canonical_table, partition={"manifest_id": manifest_id}
    )
    with derive(
        "canonical.promote",
        output=output,
        params={
            "layer": spec.layer,
            "length_method": method.method,
            "compute_epsg": method.compute_epsg,
            "length_expression": directive.spec.get("length_expression"),
        },
        inputs=[
            InputRef(kind="derivation", ref_id=parse_derivation_id),
            InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage),
        ],
        rules=[directive.rule_id, datum.rule_id, multilateral.rule_id, segment_rule.rule_id],
    ) as context:
        context.set_rows(len(kept))
        context.set_output_hash(
            hash_payload(json_ready({"geom_keys": sorted(row["linekey"] for row in kept)}))
        )

    derivation_id = context.derivation_id
    source_datum = f"EPSG:{int(datum.spec['source_epsg'])}"
    with connection.cursor() as cursor:
        cursor.executemany(
            _INSERT_LATERAL,
            [
                {
                    "api10": row["api10"],
                    "geom_key": row["linekey"],
                    "source_row_ordinal": row["source_row_ordinal"],
                    "source_datum": source_datum,
                    "transform_rule_id": datum.rule_id,
                    "manifest_id": manifest_id,
                    "derivation_id": derivation_id,
                }
                for row in kept
            ],
        )
    _open_vintage(connection, spec, manifest_id, vintage, derivation_id, staged_rows, len(kept))

    return LoadResult(
        layer=spec.layer,
        source_id=spec.source_id,
        manifest_id=manifest_id,
        parse_derivation_id=parse_derivation_id,
        promote_derivation_id=derivation_id,
        staged_rows=staged_rows,
        promoted_rows=len(kept),
        quarantined=counts,
        compute_epsg=method.compute_epsg,
        length_rule_id=method.rule_id,
        length_stats=_length_stats(connection, derivation_id, method),
        multi_lateral_rate=len(multi) / len(per_well) if per_well else None,
    )


def _known_api10s(connection: psycopg.Connection, wanted: Iterable[str]) -> set[str]:
    candidates = list(wanted)
    if not candidates:
        return set()
    with connection.cursor() as cursor:
        cursor.execute(
            "select distinct api10 from canonical.wells where api10 = any(%s)", (candidates,)
        )
        return {row[0] for row in cursor.fetchall()}


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


_UNITS_KEYED = """
with keyed as (
    select source_row_ordinal, mapsymbol, formation, caseno, orderno, dssize,
           'ndsu_' || coalesce(caseno, '0') || '_' || coalesce(orderno, '0') || '_'
               || substr(md5(ST_AsBinary(geom)), 1, 10) as spacing_unit_id,
           row_number() over (
               partition by 'ndsu_' || coalesce(caseno, '0') || '_' || coalesce(orderno, '0')
                   || '_' || substr(md5(ST_AsBinary(geom)), 1, 10)
               order by source_row_ordinal) as occurrence
      from staging.nd_gis_spacing_units
     where manifest_id = %(manifest_id)s and geom is not null
)
"""

_INSERT_UNITS = (
    _UNITS_KEYED
    + """
insert into canonical.spacing_units (
    spacing_unit_id, state, label, formation_reported, case_no, order_no, ds_size_acres, geom,
    source_manifest_id, derivation_id)
select keyed.spacing_unit_id, 'ND', keyed.mapsymbol, keyed.formation, keyed.caseno, keyed.orderno,
       nullif(keyed.dssize, '')::numeric, staged.geom, %(manifest_id)s, %(derivation_id)s
  from keyed
  join staging.nd_gis_spacing_units staged
    on staged.manifest_id = %(manifest_id)s
   and staged.source_row_ordinal = keyed.source_row_ordinal
 where keyed.occurrence = 1
on conflict (spacing_unit_id) do nothing
"""
)

_DUPLICATE_UNITS = (
    _UNITS_KEYED
    + "select source_row_ordinal, spacing_unit_id, mapsymbol from keyed where occurrence > 1"
)


def _promote_spacing_units(
    connection: psycopg.Connection,
    spec: LayerSpec,
    *,
    manifest_id: str,
    vintage: date,
    parse_derivation_id: str,
    staged_rows: int,
    datum: ConformanceRule,
) -> LoadResult:
    counts = dict.fromkeys(spec.reason_codes, 0)
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_DUPLICATE_UNITS, {"manifest_id": manifest_id})
        duplicates = cursor.fetchall()
    counts["duplicate_row"] += _quarantine(
        connection,
        pl.DataFrame(duplicates),
        spec,
        manifest_id=manifest_id,
        reason_code="duplicate_row",
        stage="conform",
    )

    output = OutputSpec(
        store="postgis", dataset=spec.canonical_table, partition={"manifest_id": manifest_id}
    )
    with derive(
        "canonical.promote",
        output=output,
        params={"layer": spec.layer, "storage_epsg": int(datum.spec["target_epsg"])},
        inputs=[
            InputRef(kind="derivation", ref_id=parse_derivation_id),
            InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage),
        ],
    ) as context:
        promoted = staged_rows - len(duplicates)
        context.set_rows(promoted)
        context.set_output_hash(hash_payload({"manifest_id": manifest_id, "rows": promoted}))

    derivation_id = context.derivation_id
    with connection.cursor() as cursor:
        cursor.execute(
            _INSERT_UNITS, {"manifest_id": manifest_id, "derivation_id": derivation_id}
        )
        inserted = cursor.rowcount
    _open_vintage(connection, spec, manifest_id, vintage, derivation_id, staged_rows, inserted)

    return LoadResult(
        layer=spec.layer,
        source_id=spec.source_id,
        manifest_id=manifest_id,
        parse_derivation_id=parse_derivation_id,
        promote_derivation_id=derivation_id,
        staged_rows=staged_rows,
        promoted_rows=inserted,
        quarantined=counts,
    )


_SURVEYS_SELECT = """
select source_row_ordinal, api_wellno, well_sub,
       surveytype                              as station_type,
       nullif(measdpth, '')::double precision   as measured_depth_ft,
       nullif(tvd, '')::double precision        as true_vertical_depth_ft,
       nullif(inclinatio, '')::double precision as inclination_deg,
       nullif(azimuth, '')::double precision    as azimuth_deg,
       nullif(coordns, '')::double precision    as ns_offset_ft,
       coordnsdir                              as ns_offset_dir,
       nullif(coordew, '')::double precision    as ew_offset_ft,
       coordewdir                              as ew_offset_dir,
       ST_X(geom)                              as longitude,
       ST_Y(geom)                              as latitude
  from staging.nd_gis_directionals
 where manifest_id = %s and geom is not null
 order by source_row_ordinal
"""

_SURVEYS_SCHEMA = {
    "source_row_ordinal": pl.Int32,
    "api_wellno": pl.String,
    "well_sub": pl.String,
    "station_type": pl.String,
    "measured_depth_ft": pl.Float64,
    "true_vertical_depth_ft": pl.Float64,
    "inclination_deg": pl.Float64,
    "azimuth_deg": pl.Float64,
    "ns_offset_ft": pl.Float64,
    "ns_offset_dir": pl.String,
    "ew_offset_ft": pl.Float64,
    "ew_offset_dir": pl.String,
    "longitude": pl.Float64,
    "latitude": pl.Float64,
}

# The identity columns cr_nd_survey_api_identity_1 adds, declared so an empty layer still
# presents the columns the vocabulary rule maps, and then the column that rule writes.
_KEYED_SURVEY_SCHEMA = {**_SURVEYS_SCHEMA, "api14": pl.String, "api10": pl.String}
_ADMITTED_SURVEY_SCHEMA = {**_KEYED_SURVEY_SCHEMA, "segment_kind": pl.String}

_INSERT_STATION = """
insert into canonical.well_survey_stations (
    api10, api14, wellbore_segment, segment_kind, station_ordinal, measured_depth_ft,
    true_vertical_depth_ft, inclination_deg, azimuth_deg, ns_offset_ft, ns_offset_dir,
    ew_offset_ft, ew_offset_dir, station_type, geom, source_datum, transform_rule_id,
    source_manifest_id, derivation_id)
values (%(api10)s, %(api14)s, %(wellbore_segment)s, %(segment_kind)s, %(station_ordinal)s,
        %(measured_depth_ft)s, %(true_vertical_depth_ft)s, %(inclination_deg)s, %(azimuth_deg)s,
        %(ns_offset_ft)s, %(ns_offset_dir)s, %(ew_offset_ft)s, %(ew_offset_dir)s,
        %(station_type)s,
        ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), %(storage_epsg)s),
        %(source_datum)s, %(transform_rule_id)s, %(manifest_id)s, %(derivation_id)s)
on conflict (api10, wellbore_segment, station_ordinal) do nothing
"""

_INSERT_TRACE = """
insert into canonical.well_spatial (
    api10, geom_type, geom_key, geom, source_datum, transform_rule_id, source_manifest_id,
    derivation_id)
values (%(api10)s, %(geom_type)s, %(geom_key)s,
        ST_SetSRID(ST_GeomFromText(%(wkt)s), %(storage_epsg)s),
        %(source_datum)s, %(transform_rule_id)s, %(manifest_id)s, %(derivation_id)s)
on conflict (api10, geom_type, geom_key) do nothing
"""


def keyed_stations(
    frame: pl.DataFrame, rule: ConformanceRule
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split on identity: the slice and the digit count are the rule's, not this function's."""
    digits = int(rule.spec["digits"])
    start, stop = (int(bound) for bound in rule.spec["api10_slice"])
    keyed: list[dict[str, Any]] = []
    unkeyed: list[dict[str, Any]] = []
    for row in frame.iter_rows(named=True):
        api14 = (row["api_wellno"] or "").strip()
        if len(api14) != digits or not api14.isdigit():
            unkeyed.append(row)
            continue
        keyed.append({**row, "api14": api14, "api10": api14[start:stop]})
    return keyed, unkeyed


# What a rule may ask for when a measurement leaves its bound. `null_field` withholds the
# value and promotes the position; `drop_row` rejects the whole station. Which one applies is
# the rule row's decision — see withheld_measurements.
FIELD_ACTIONS = ("null_field", "drop_row")


def withheld_measurements(
    stations: Sequence[Mapping[str, Any]], rule: ConformanceRule
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply the rule's declared `field_action` to every measurement outside its bound.

    What happens to a row that breaks a bound is read from the rule row, not decided here:
    `null_field` withholds the value and keeps the surveyed position, `drop_row` rejects the
    station. Under `cr_nd_survey_station_range_1` the action is `null_field`, because ND
    computed the published position itself and a 437-degree azimuth is no evidence against the
    coordinate beside it — but that reasoning lives in the rule's rationale, and changing the
    decision has to be a new rule row rather than an edit here.

    Each reject carries the action and the disposition it was filed under, so the ledger can
    tell a withheld value from a lost row without joining back to the registry.
    """
    bounds = list(rule.spec["bounds"])
    action = str(rule.spec.get("field_action", ""))
    if action not in FIELD_ACTIONS:
        raise RuleSpecError(
            f"{rule.rule_id}: field_action {action!r} is not one of {', '.join(FIELD_ACTIONS)}"
        )
    filed_as = {"field_action": action}
    if "disposition" in rule.spec:
        filed_as["disposition"] = str(rule.spec["disposition"])

    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for station in stations:
        row = dict(station)
        broke_a_bound = False
        for bound in bounds:
            field = str(bound["field"])
            value = row.get(field)
            ceiling = row.get(str(bound["max_field"])) if "max_field" in bound else bound.get("max")
            floor = bound.get("min")
            if value is None:
                continue
            if not ((floor is not None and value < floor) or
                    (ceiling is not None and value > ceiling)):
                continue
            broke_a_bound = True
            rejected.append(
                {
                    "api10": row["api10"],
                    "api14": row["api14"],
                    "wellbore_segment": row["well_sub"],
                    "source_row_ordinal": row["source_row_ordinal"],
                    "field": field,
                    "value": value,
                    "admissible": _bound_text(field, bound, floor, ceiling),
                    **filed_as,
                }
            )
            if action == "null_field":
                row[field] = None
        if broke_a_bound and action == "drop_row":
            continue
        kept.append(row)
    return kept, rejected


def _bound_text(field: str, bound: Mapping[str, Any], floor: Any, ceiling: Any) -> str:
    if "max_field" in bound:
        return f"{field} <= {bound['max_field']} ({ceiling})"
    return f"{floor} <= {field} <= {ceiling} {bound.get('unit', '')}".strip()


def survey_trace_wkt(stations: Sequence[Mapping[str, Any]]) -> str:
    """The LineString through the stations in the order they are given."""
    vertices = ", ".join(f"{row['longitude']!r} {row['latitude']!r}" for row in stations)
    return f"LINESTRING({vertices})"


def ordered_segments(
    stations: Sequence[Mapping[str, Any]], rule: ConformanceRule
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Group into `(api14, well_sub)` segments and order each one the way the rule says.

    A station with no measured depth has no place in that order, so it is returned as a reject
    rather than parked at whichever end a null sorts to.
    """
    order_by = str(rule.spec["order_by"])
    tie_break = str(rule.spec["tie_break"])
    first_ordinal = int(rule.spec["ordinal_from"])
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    unorderable: list[dict[str, Any]] = []
    for station in stations:
        if station[order_by] is None:
            unorderable.append(dict(station))
            continue
        grouped.setdefault((station["api14"], station["well_sub"]), []).append(dict(station))

    segments = []
    for (api14, well_sub), rows in sorted(grouped.items()):
        rows.sort(key=lambda row: (row[order_by], row[tie_break]))
        for ordinal, row in enumerate(rows, start=first_ordinal):
            row["station_ordinal"] = ordinal
        segments.append(
            {
                "api10": rows[0]["api10"],
                "api14": api14,
                "wellbore_segment": well_sub,
                "segment_kind": rows[0]["segment_kind"],
                "geom_key": f"{api14}_{well_sub}",
                "station_count": len(rows),
                "stations": rows,
            }
        )
    return segments, unorderable


def _promote_surveys(
    connection: psycopg.Connection,
    spec: LayerSpec,
    *,
    manifest_id: str,
    vintage: date,
    parse_derivation_id: str,
    staged_rows: int,
    datum: ConformanceRule,
) -> LoadResult:
    identity = _rule(connection, spec.source_id, "cr_nd_survey_api_identity_1")
    ordering = _rule(connection, spec.source_id, "cr_nd_survey_station_order_1")
    ranges = _rule(connection, spec.source_id, "cr_nd_survey_station_range_1")
    minimum = _rule(connection, spec.source_id, "cr_nd_survey_min_stations_1")
    azimuth = _rule(connection, spec.source_id, "cr_nd_survey_azimuth_reference_1")
    segment_rule = rule_for_family(
        load_rules(connection, source_id=spec.source_id, stage="conform"), SURVEY_SEGMENT_FAMILY
    )

    frame = _staging_frame(connection, _SURVEYS_SELECT, manifest_id, _SURVEYS_SCHEMA)
    counts = dict.fromkeys(spec.reason_codes, 0)

    keyed, unkeyed = keyed_stations(frame, identity)
    counts[str(identity.spec["reason_code"])] += _quarantine(
        connection,
        pl.DataFrame(unkeyed, schema=_SURVEYS_SCHEMA),
        spec,
        manifest_id=manifest_id,
        reason_code=str(identity.spec["reason_code"]),
        stage="parse",
        rule_id=identity.rule_id,
    )

    selected = apply_rules(pl.DataFrame(keyed, schema=_KEYED_SURVEY_SCHEMA), [segment_rule])
    for batch in selected.quarantined:
        counts[batch.reason_code] = counts.get(batch.reason_code, 0) + _quarantine(
            connection,
            batch.frame,
            spec,
            manifest_id=manifest_id,
            reason_code=batch.reason_code,
            stage="conform",
            rule_id=batch.rule_id,
        )

    admitted, rejected_values = withheld_measurements(selected.frame.to_dicts(), ranges)
    counts[str(ranges.spec["reason_code"])] += _quarantine(
        connection,
        pl.DataFrame(rejected_values),
        spec,
        manifest_id=manifest_id,
        reason_code=str(ranges.spec["reason_code"]),
        stage="validate",
        rule_id=ranges.rule_id,
    )

    segments, unorderable = ordered_segments(admitted, ordering)
    counts[str(ordering.spec["reason_code"])] += _quarantine(
        connection,
        pl.DataFrame(unorderable, schema=_ADMITTED_SURVEY_SCHEMA),
        spec,
        manifest_id=manifest_id,
        reason_code=str(ordering.spec["reason_code"]),
        stage="conform",
        rule_id=ordering.rule_id,
    )

    sized = apply_rules(
        pl.DataFrame([_segment_payload(s) for s in segments], schema=_SEGMENT_SCHEMA), [minimum]
    )
    traceable_keys = set(sized.frame["geom_key"].to_list())
    traceable = [segment for segment in segments if segment["geom_key"] in traceable_keys]
    for batch in sized.quarantined:
        counts[batch.reason_code] = counts.get(batch.reason_code, 0) + _quarantine(
            connection,
            batch.frame,
            spec,
            manifest_id=manifest_id,
            reason_code=batch.reason_code,
            stage="validate",
            rule_id=batch.rule_id,
        )

    known = _known_api10s(connection, {segment["api10"] for segment in traceable})
    kept = [segment for segment in traceable if segment["api10"] in known]
    counts["orphan_fk"] += _quarantine(
        connection,
        pl.DataFrame(
            [_segment_payload(s) for s in traceable if s["api10"] not in known]
        ),
        spec,
        manifest_id=manifest_id,
        reason_code="orphan_fk",
        stage="join",
    )

    storage_epsg = int(datum.spec["target_epsg"])
    source_datum = f"EPSG:{int(datum.spec['source_epsg'])}"
    stations = [station for segment in kept for station in segment["stations"]]

    output = OutputSpec(
        store="postgis", dataset=spec.canonical_table, partition={"manifest_id": manifest_id}
    )
    with derive(
        "canonical.promote",
        output=output,
        params={
            "layer": spec.layer,
            "storage_epsg": storage_epsg,
            "source_datum": source_datum,
            "geom_type": SURVEY_TRACE_GEOM_TYPE,
            "station_grain": "api10 + wellbore_segment + station_ordinal",
        },
        inputs=[
            InputRef(kind="derivation", ref_id=parse_derivation_id),
            InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage),
        ],
        rules=sorted(
            {
                identity.rule_id, segment_rule.rule_id, ordering.rule_id, ranges.rule_id,
                minimum.rule_id, azimuth.rule_id, datum.rule_id,
            }
        ),
    ) as context:
        context.set_rows(len(kept))
        context.set_output_hash(
            hash_payload(
                json_ready(
                    {
                        "geom_keys": sorted(segment["geom_key"] for segment in kept),
                        "stations": len(stations),
                    }
                )
            )
        )

    derivation_id = context.derivation_id
    shared = {
        "storage_epsg": storage_epsg,
        "source_datum": source_datum,
        "transform_rule_id": datum.rule_id,
        "manifest_id": manifest_id,
        "derivation_id": derivation_id,
    }
    with connection.cursor() as cursor:
        cursor.executemany(
            _INSERT_STATION,
            [
                {
                    **shared,
                    **{key: station[key] for key in _STATION_COLUMNS},
                    "wellbore_segment": segment["wellbore_segment"],
                    "api14": segment["api14"],
                }
                for segment in kept
                for station in segment["stations"]
            ],
        )
        cursor.executemany(
            _INSERT_TRACE,
            [
                {
                    **shared,
                    "api10": segment["api10"],
                    "geom_type": SURVEY_TRACE_GEOM_TYPE,
                    "geom_key": segment["geom_key"],
                    "wkt": survey_trace_wkt(segment["stations"]),
                }
                for segment in kept
            ],
        )
    _open_vintage(connection, spec, manifest_id, vintage, derivation_id, staged_rows, len(kept))

    return LoadResult(
        layer=spec.layer,
        source_id=spec.source_id,
        manifest_id=manifest_id,
        parse_derivation_id=parse_derivation_id,
        promote_derivation_id=derivation_id,
        staged_rows=staged_rows,
        promoted_rows=len(kept),
        quarantined=counts,
        station_rows=len(stations),
    )


_STATION_COLUMNS = (
    "api10", "segment_kind", "station_ordinal", "measured_depth_ft", "true_vertical_depth_ft",
    "inclination_deg", "azimuth_deg", "ns_offset_ft", "ns_offset_dir", "ew_offset_ft",
    "ew_offset_dir", "station_type", "longitude", "latitude",
)

_SEGMENT_SCHEMA = {
    "api10": pl.String,
    "api14": pl.String,
    "wellbore_segment": pl.String,
    "segment_kind": pl.String,
    "geom_key": pl.String,
    "station_count": pl.Int64,
}


def _segment_payload(segment: Mapping[str, Any]) -> dict[str, Any]:
    """What a held-back segment says about itself: never the station list, which is 1,167 rows
    at its longest and would blow the 8 KB quarantine payload cap into an `oversized` stub."""
    return {key: value for key, value in segment.items() if key != "stations"}


_PROMOTERS = {
    "wells": _promote_wells,
    "laterals": _promote_laterals,
    "spacing_units": _promote_spacing_units,
    "surveys": _promote_surveys,
}


def _open_vintage(
    connection: psycopg.Connection,
    spec: LayerSpec,
    manifest_id: str,
    vintage: date,
    derivation_id: str,
    examined: int,
    appended: int,
) -> None:
    # Accumulates onto the (source, day) ledger row so a same-day re-load of a revised
    # extract adds to the first pass instead of overwriting it (DR-78).
    record_vintage_day(
        connection,
        source_id=spec.source_id,
        vintage_date=vintage,
        manifest_ids=[manifest_id],
        opened_at=current_session().clock.now(),
        promotion_derivation_id=derivation_id,
        rows_examined=examined,
        rows_appended=appended,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load an ND DMR GIS layer into PostGIS.")
    parser.add_argument("--layer", choices=[*LAYERS, "all"], required=True)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--url", default=None, help="override the upstream URL (testing only)")
    parser.add_argument("--raw-root", default=None)
    parser.add_argument("--env-id", default=None, help="override the fingerprinted env id")
    parser.add_argument("--code-version", default=None)
    parser.add_argument(
        "--restage",
        action="store_true",
        help="re-parse and re-promote from the stored bytes after a rule or schema change",
    )
    arguments = parser.parse_args(argv)

    # Wells first: a lateral or a survey trace whose api10 has no well row is an orphan_fk.
    layers = list(LAYERS) if arguments.layer == "all" else [arguments.layer]
    with psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        with lineage_session(recorder=PostgresRecorder(connection), environment=environment):
            for layer in layers:
                result = load_layer(
                    connection,
                    layer,
                    url=arguments.url,
                    raw_root=arguments.raw_root,
                    restage=arguments.restage,
                )
                connection.commit()
                print(json.dumps(result.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
