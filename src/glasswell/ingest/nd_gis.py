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

from glasswell.ingest.base import resolve_environment
from glasswell.ingest.shapefile import ShapefileRecord, ZippedShapefile
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
    open_vintage,
    quarantine,
)
from glasswell.lineage.serialization import hash_payload, json_ready
from glasswell.units import METRES_PER_FOOT

BASE_URL = "https://gis.dmr.nd.gov/downloads/oilgas/shapefile"
DATUM_RULE_SOURCE = "nd_gis_wells"
LAND_UNIT_RULE_ID = "cr_nd_land_unit_1"
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
        geometry_type="LineString",
        reason_codes=("parse_error", "unknown_vocab", "multi_wellbore_policy", "orphan_fk"),
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
    length_stats: Mapping[str, float] = field(default_factory=dict)
    multi_lateral_rate: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "manifest_id": self.manifest_id,
            "staged_rows": self.staged_rows,
            "promoted_rows": self.promoted_rows,
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
) -> LoadResult:
    """Fetch OGD_Horizontals_Line, stage it, and promote lateral centrelines."""
    return _load(connection, LAYERS["laterals"], url=url, raw_root=raw_root, client=client)


def load_spacing_units(
    connection: psycopg.Connection,
    *,
    url: str | None = None,
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
) -> LoadResult:
    """Fetch OGD_DrillingSpacingUnits, stage it, and promote canonical.spacing_units."""
    return _load(connection, LAYERS["spacing_units"], url=url, raw_root=raw_root, client=client)


def load_layer(connection: psycopg.Connection, layer: str, **kwargs: Any) -> LoadResult:
    return _load(connection, LAYERS[layer], **kwargs)


def _load(
    connection: psycopg.Connection,
    spec: LayerSpec,
    *,
    url: str | None = None,
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
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
    if _already_promoted(connection, spec, manifest.manifest_id):
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
    with ZippedShapefile(payload_path) as layer:
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
    if shape == declared or (declared.startswith("Multi") and f"Multi{shape}" == declared):
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
    rules = load_rules(connection, source_id=spec.source_id, stage="conform")
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
    directive = _rule(connection, spec.source_id, "cr_nd_compute_crs_1")
    multilateral = _rule(connection, spec.source_id, "cr_nd_multilateral_1")
    compute_epsg = int(directive.spec["compute_epsg"])
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

    laterals = [row for row in parsed if row["segment"] == "LAT"]
    others = [row for row in parsed if row["segment"] != "LAT"]
    # The layer also ships vertical holes and sidetracks; they stay in staging, and the
    # promotion measures them rather than promoting a vertical segment as a centreline.
    counts["unknown_vocab"] += _quarantine(
        connection,
        pl.DataFrame(others),
        spec,
        manifest_id=manifest_id,
        reason_code="unknown_vocab",
        stage="conform",
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
            "compute_epsg": compute_epsg,
            "length_expression": directive.spec.get("length_expression"),
        },
        inputs=[
            InputRef(kind="derivation", ref_id=parse_derivation_id),
            InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage),
        ],
        rules=[directive.rule_id, datum.rule_id, multilateral.rule_id],
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
        compute_epsg=compute_epsg,
        length_stats=_length_stats(connection, derivation_id, compute_epsg),
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
    connection: psycopg.Connection, derivation_id: str, compute_epsg: int
) -> dict[str, float]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select min(feet), percentile_cont(0.5) within group (order by feet), max(feet),"
            "       count(*)"
            "  from (select ST_Length(ST_Transform(geom, %s)) / %s as feet"
            "          from canonical.well_spatial"
            "         where derivation_id = %s and geom_type = 'lateral') lengths",
            (compute_epsg, float(METRES_PER_FOOT), derivation_id),
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


_PROMOTERS = {
    "wells": _promote_wells,
    "laterals": _promote_laterals,
    "spacing_units": _promote_spacing_units,
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
    open_vintage(
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
    arguments = parser.parse_args(argv)

    # Wells first: a lateral whose api10 has no well row quarantines as orphan_fk.
    layers = list(LAYERS) if arguments.layer == "all" else [arguments.layer]
    with psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        with lineage_session(recorder=PostgresRecorder(connection), environment=environment):
            for layer in layers:
                result = load_layer(
                    connection, layer, url=arguments.url, raw_root=arguments.raw_root
                )
                connection.commit()
                print(json.dumps(result.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
