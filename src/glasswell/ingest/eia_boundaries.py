"""Load the EIA basin and play boundary archives into staging and canonical.

Two plain HTTPS zips, neither of them an ArcGIS service, so neither passes through the host
allowlist. The publisher choice, the basin/play distinction, the name link, the overlap policy,
the geometry repair and the area provenance are conformance rows, read here and never restated.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import psycopg
from psycopg.rows import dict_row

from glasswell.db.dsn import add_dsn_argument, resolve_dsn
from glasswell.ingest.base import record_vintage_day, resolve_environment
from glasswell.ingest.shapefile import ShapefileRecord, ZippedShapefile
from glasswell.lineage import (
    ConformanceRule,
    InputRef,
    OutputSpec,
    PostgresRecorder,
    current_session,
    derive,
    fetch_raw,
    lineage_session,
    load_rules,
    quarantine,
)
from glasswell.lineage.fetch_attempts import durable_fetch_attempts
from glasswell.lineage.serialization import hash_payload

BASINS_URL = "https://www.eia.gov/maps/map_data/SedimentaryBasins_US_EIA.zip"
PLAYS_URL = "https://www.eia.gov/maps/map_data/TightOil_ShaleGas_IndividualPlays_Lower48_EIA.zip"
RULE_SOURCE = "eia_shale_plays"
PUBLISHER_RULE_ID = "cr_eia_boundary_publisher_1"
TAXONOMY_RULE_ID = "cr_eia_boundary_taxonomy_1"
LINK_RULE_ID = "cr_eia_basin_link_1"
REPAIR_RULE_ID = "cr_eia_geometry_repair_1"
AREA_RULE_ID = "cr_eia_area_provenance_1"
DATUM_RULE_ID = "cr_eia_boundary_datum_1"

CANONICAL_TABLE = "canonical.basin_boundaries"
AREA_BASIS = "publisher_reported"
REPAIR_OPERATOR = "st_makevalid_collection_extract"


class SchemaDrift(ValueError):
    """The shipped DBF no longer carries a field the staging table declares."""


class DatumMismatch(ValueError):
    """The shipped .prj disagrees with the datum the conformance registry declares."""


class BasinLayerMissing(LookupError):
    """Plays promote against the basin layer; a null link must mean the name did not resolve."""


@dataclass(frozen=True, slots=True)
class LayerSpec:
    layer: str
    source_id: str
    source_key: str
    url: str
    staging_table: str
    boundary_kind: str
    # dbf field name (lowercased) -> staging column. Fields outside this map are not staged.
    fields: Mapping[str, str]
    optional_fields: tuple[str, ...]
    reason_codes: tuple[str, ...]
    # The archive ships several boundary shapefiles; the marker is the declaration of which
    # members are boundaries, where scanning every member would be an accident that holds.
    member_marker: str | None = None

    @property
    def columns(self) -> tuple[str, ...]:
        return ("source_layer", *self.fields.values())


LAYERS: Mapping[str, LayerSpec] = {
    "basins": LayerSpec(
        layer="basins",
        source_id="eia_sedimentary_basins",
        source_key="SedimentaryBasins_US_EIA.zip",
        url=BASINS_URL,
        staging_table="staging.eia_basins",
        boundary_kind="basin",
        fields={"name": "name", "area_sq_mi": "area_sq_mi", "area_sq_km": "area_sq_km"},
        optional_fields=(),
        reason_codes=(
            "parse_error", "key_incomplete", "duplicate_row", "invalid_geometry",
            "key_collision",
        ),
    ),
    "plays": LayerSpec(
        layer="plays",
        source_id="eia_shale_plays",
        source_key="TightOil_ShaleGas_IndividualPlays_Lower48_EIA.zip",
        url=PLAYS_URL,
        staging_table="staging.eia_plays",
        boundary_kind="play",
        fields={
            "shale_play": "shale_play",
            "basin": "basin",
            "subbasin": "sub_basin",
            "lithology": "lithology",
            "age_shale": "age_shale",
            "source": "source_label",
            "area_sq_mi": "area_sq_mi",
            "area_sq_km": "area_sq_km",
        },
        # Only Wolfcamp declares a sub-basin, so its absence is the publisher's shape and not
        # drift; every other field is required on every member.
        optional_fields=("subbasin",),
        reason_codes=(
            "parse_error", "key_incomplete", "duplicate_row", "invalid_geometry",
            "key_collision",
        ),
        member_marker="_boundary",
    ),
}


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
    repaired: int = 0
    unlinked: int = 0
    unchanged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "manifest_id": self.manifest_id,
            "staged_rows": self.staged_rows,
            "promoted_rows": self.promoted_rows,
            "quarantined": dict(self.quarantined),
            "repaired": self.repaired,
            "unlinked": self.unlinked,
            "unchanged": self.unchanged,
        }


def load_basins(connection: psycopg.Connection, **kwargs: Any) -> LoadResult:
    """Fetch the sedimentary basin outlines, stage them, and promote to canonical."""
    return _load(connection, LAYERS["basins"], **kwargs)


def load_plays(connection: psycopg.Connection, **kwargs: Any) -> LoadResult:
    """Fetch the play boundaries, stage them, and promote linked to their basins."""
    return _load(connection, LAYERS["plays"], **kwargs)


def load_layer(connection: psycopg.Connection, layer: str, **kwargs: Any) -> LoadResult:
    return _load(connection, LAYERS[layer], **kwargs)


def _load(
    connection: psycopg.Connection,
    spec: LayerSpec,
    *,
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
    restage: bool = False,
) -> LoadResult:
    datum = _rule(connection, DATUM_RULE_ID)
    source_epsg = int(datum.spec["source_epsg"])
    storage_epsg = int(datum.spec["target_epsg"])

    fetched = fetch_raw(
        connection,
        spec.source_id,
        spec.source_key,
        url=spec.url,
        raw_root=raw_root,
        client=client,
        media_type="application/zip",
        rules=(PUBLISHER_RULE_ID, DATUM_RULE_ID),
    )
    manifest = fetched.manifest
    if restage:
        _clear_staging(connection, spec, manifest.manifest_id)
    elif fetched.unchanged and _already_staged(connection, spec, manifest.manifest_id):
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
    result = _promote(
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


def _rule(connection: psycopg.Connection, rule_id: str) -> ConformanceRule:
    """Every classing decision belongs to the registry; they are read here, never written."""
    for rule in load_rules(connection, source_id=RULE_SOURCE):
        if rule.rule_id == rule_id:
            return rule
    raise LookupError(f"rule {rule_id} is not seeded for {RULE_SOURCE}")


def _already_staged(connection: psycopg.Connection, spec: LayerSpec, manifest_id: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            f"select 1 from {spec.staging_table} where manifest_id = %s limit 1",
            (manifest_id,),
        )
        return cursor.fetchone() is not None


def _owns_canonical(connection: psycopg.Connection, manifest_id: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            f"select 1 from {CANONICAL_TABLE} where source_manifest_id = %s limit 1",
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


def boundary_members(archive: Path, marker: str | None) -> tuple[str, ...]:
    """The shapefile stems a boundary archive publishes, in archive order."""
    with zipfile.ZipFile(archive) as bundle:
        stems = sorted(
            {name.rsplit(".", 1)[0] for name in bundle.namelist() if name.lower().endswith(".shp")}
        )
    if marker is None:
        return tuple(stems)
    selected = tuple(stem for stem in stems if marker in stem.lower())
    if not selected:
        raise SchemaDrift(f"{archive.name} publishes no shapefile whose stem holds {marker!r}")
    return selected


def _text(value: object) -> str | None:
    if value is None:
        return None
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
    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    ordinal = 0
    members = boundary_members(payload_path, spec.member_marker)
    for member in members:
        with ZippedShapefile(payload_path, layer_suffix=member) as layer:
            if layer.source_epsg != source_epsg:
                raise DatumMismatch(
                    f"{spec.source_key}:{member} ships EPSG:{layer.source_epsg}; the registry"
                    f" declares EPSG:{source_epsg}"
                )
            for record in layer:
                row, note = _staging_row(spec, member, record, manifest_id, ordinal)
                ordinal += 1
                rows.append(row)
                if note:
                    rejected.append(
                        {key: value for key, value in row.items() if key != "geom_wkt"}
                        | {"detail": note}
                    )

    geometry = (
        f"ST_Multi(ST_Transform(ST_GeomFromText(%(geom_wkt)s, {source_epsg}), {storage_epsg}))"
    )
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
        params={
            "layer": spec.layer,
            "source_key": spec.source_key,
            "source_epsg": source_epsg,
            "members": len(members),
        },
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


def _staging_row(
    spec: LayerSpec,
    member: str,
    record: ShapefileRecord,
    manifest_id: str,
    ordinal: int,
) -> tuple[dict[str, Any], str | None]:
    attributes = {key.lower(): value for key, value in record.attributes.items()}
    missing = [
        field
        for field in spec.fields
        if field not in attributes and field not in spec.optional_fields
    ]
    if missing:
        raise SchemaDrift(f"{spec.source_key}:{member} has no {', '.join(missing)} field")
    row: dict[str, Any] = {
        column: _text(attributes.get(field)) for field, column in spec.fields.items()
    }
    row["source_layer"] = member
    row["manifest_id"] = manifest_id
    row["source_row_ordinal"] = ordinal
    note = _unstorable(record)
    row["geom_wkt"] = None if note else record.geometry.wkt
    return row, note


def _unstorable(record: ShapefileRecord) -> str | None:
    if record.is_empty:
        return "the source record carries no geometry"
    shape = record.geometry.geom_type
    if shape not in ("Polygon", "MultiPolygon"):
        return f"{shape} does not fit the declared MultiPolygon column"
    return None


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


# The minted key cr_eia_boundary_publisher_1 declares. One home, in SQL, so the promotion and
# every quarantine mirror below derive the same id from the same expression.
_SLUG = "nullif(btrim(regexp_replace(lower({column}), '[^a-z0-9]+', '_', 'g'), '_'), '')"

# ST_MakeValid can return a collection, so the polygonal extract is part of the repair rather
# than a tidy-up after it (cr_eia_geometry_repair_1).
_REPAIRED = """
    case when ST_IsValid(staged.geom) then ST_Multi(staged.geom)
         else ST_Multi(ST_CollectionExtract(ST_MakeValid(staged.geom), 3)) end
"""

_BASINS_KEYED = f"""
with keyed as (
    select staged.source_row_ordinal, staged.source_layer, btrim(staged.name) as name,
           staged.area_sq_mi,
           'basin_' || {_SLUG.format(column='staged.name')} as boundary_id,
           ST_IsValid(staged.geom) as was_valid,
           ST_IsValidReason(staged.geom) as invalid_reason,
           {_REPAIRED} as geom,
           row_number() over (partition by {_SLUG.format(column='staged.name')}
                              order by staged.source_row_ordinal) as occurrence
      from staging.eia_basins staged
     where staged.manifest_id = %(manifest_id)s and staged.geom is not null
       and {_SLUG.format(column='staged.name')} is not null
),
admissible as (
    select * from keyed where occurrence = 1 and not ST_IsEmpty(geom)
)
"""

_INSERT_BASINS = (
    _BASINS_KEYED
    + """
insert into canonical.basin_boundaries (
    boundary_id, boundary_kind, name, area_sq_mi, area_basis, vintage_label, geometry_repair,
    geometry_repair_reason, geom, source_datum, transform_rule_id, source_manifest_id,
    derivation_id)
select admissible.boundary_id, 'basin', admissible.name,
       admissible.area_sq_mi::double precision, %(area_basis)s, admissible.source_layer,
       case when admissible.was_valid then null else %(repair_operator)s end,
       case when admissible.was_valid then null else admissible.invalid_reason end,
       admissible.geom, %(source_datum)s, %(transform_rule_id)s, %(manifest_id)s,
       %(derivation_id)s
  from admissible
on conflict (boundary_id) do nothing
"""
)

_PLAYS_KEYED = f"""
with keyed as (
    select staged.source_row_ordinal, staged.source_layer, btrim(staged.shale_play) as name,
           btrim(staged.basin) as basin_name, nullif(btrim(staged.sub_basin), '') as sub_basin,
           nullif(btrim(staged.lithology), '') as lithology,
           nullif(btrim(staged.age_shale), '') as age_shale, staged.area_sq_mi,
           'play_' || {_SLUG.format(column='staged.shale_play')}
                   || '_' || {_SLUG.format(column='staged.basin')} as boundary_id,
           ST_IsValid(staged.geom) as was_valid,
           ST_IsValidReason(staged.geom) as invalid_reason,
           {_REPAIRED} as geom,
           row_number() over (
               partition by {_SLUG.format(column='staged.shale_play')},
                            {_SLUG.format(column='staged.basin')}
               order by staged.source_row_ordinal) as occurrence
      from staging.eia_plays staged
     where staged.manifest_id = %(manifest_id)s and staged.geom is not null
       and {_SLUG.format(column='staged.shale_play')} is not null
       and {_SLUG.format(column='staged.basin')} is not null
),
admissible as (
    select * from keyed where occurrence = 1 and not ST_IsEmpty(geom)
),
linked as (
    select admissible.*, parent.boundary_id as basin_boundary_id
      from admissible
      left join canonical.basin_boundaries parent
        on parent.boundary_kind = 'basin'
       and lower(btrim(parent.name)) = lower(admissible.basin_name)
)
"""

_INSERT_PLAYS = (
    _PLAYS_KEYED
    + """
insert into canonical.basin_boundaries (
    boundary_id, boundary_kind, name, basin_name, basin_boundary_id, sub_basin, lithology,
    age_shale, area_sq_mi, area_basis, vintage_label, geometry_repair, geometry_repair_reason,
    geom, source_datum, transform_rule_id, source_manifest_id, derivation_id)
select linked.boundary_id, 'play', linked.name, linked.basin_name, linked.basin_boundary_id,
       linked.sub_basin, linked.lithology, linked.age_shale,
       linked.area_sq_mi::double precision, %(area_basis)s, linked.source_layer,
       case when linked.was_valid then null else %(repair_operator)s end,
       case when linked.was_valid then null else linked.invalid_reason end,
       linked.geom, %(source_datum)s, %(transform_rule_id)s, %(manifest_id)s, %(derivation_id)s
  from linked
on conflict (boundary_id) do nothing
"""
)

_DUPLICATE_BASINS = (
    _BASINS_KEYED + "select source_row_ordinal, boundary_id, name from keyed where occurrence > 1"
)
_DUPLICATE_PLAYS = (
    _PLAYS_KEYED
    + "select source_row_ordinal, boundary_id, name, basin_name from keyed where occurrence > 1"
)

_INCOMPLETE_BASINS = f"""
select source_row_ordinal, source_layer, name
  from staging.eia_basins
 where manifest_id = %(manifest_id)s and geom is not null
   and {_SLUG.format(column='name')} is null
"""
_INCOMPLETE_PLAYS = f"""
select source_row_ordinal, source_layer, shale_play, basin
  from staging.eia_plays
 where manifest_id = %(manifest_id)s and geom is not null
   and ({_SLUG.format(column='shale_play')} is null or {_SLUG.format(column='basin')} is null)
"""

# The repair evidence, mirroring the admission clause: every invalid feature is recorded, and
# the ones the repair rescued are released afterwards under REPAIR_RULE_ID.
_INVALID_BASINS = (
    _BASINS_KEYED
    + """
select source_row_ordinal, boundary_id, name, invalid_reason,
       not ST_IsEmpty(geom) as repaired
  from keyed
 where occurrence = 1 and not was_valid
"""
)
_INVALID_PLAYS = (
    _PLAYS_KEYED
    + """
select source_row_ordinal, boundary_id, name, basin_name, invalid_reason,
       not ST_IsEmpty(geom) as repaired
  from keyed
 where occurrence = 1 and not was_valid
"""
)

_REFUSED_BASINS = _BASINS_KEYED + "select source_row_ordinal, boundary_id, name from admissible"
_REFUSED_PLAYS = (
    _PLAYS_KEYED + "select source_row_ordinal, boundary_id, name, basin_name from linked"
)

_RELEASE_REPAIRED = """
update lineage.quarantine_rows
   set state = 'released', released_by_rule_id = %(rule_id)s, released_at = %(released_at)s,
       release_derivation_id = %(derivation_id)s
 where reason_code = 'invalid_geometry' and rule_id = %(rule_id)s
   and source_id = %(source_id)s and state = 'open'
   and row_payload ->> 'boundary_id' = any(%(boundary_ids)s)
"""


@dataclass(frozen=True, slots=True)
class _PromotionSql:
    insert: str
    duplicates: str
    incomplete: str
    invalid: str
    # The rows the insert would attempt, for the DR-89 all-conflict quarantine.
    refused: str


_PROMOTIONS: Mapping[str, _PromotionSql] = {
    "basins": _PromotionSql(
        insert=_INSERT_BASINS,
        duplicates=_DUPLICATE_BASINS,
        incomplete=_INCOMPLETE_BASINS,
        invalid=_INVALID_BASINS,
        refused=_REFUSED_BASINS,
    ),
    "plays": _PromotionSql(
        insert=_INSERT_PLAYS,
        duplicates=_DUPLICATE_PLAYS,
        incomplete=_INCOMPLETE_PLAYS,
        invalid=_INVALID_PLAYS,
        refused=_REFUSED_PLAYS,
    ),
}

_PROMOTION_RULES: Mapping[str, tuple[str, ...]] = {
    "basins": (DATUM_RULE_ID, PUBLISHER_RULE_ID, TAXONOMY_RULE_ID, REPAIR_RULE_ID, AREA_RULE_ID),
    "plays": (
        DATUM_RULE_ID, PUBLISHER_RULE_ID, TAXONOMY_RULE_ID, LINK_RULE_ID, REPAIR_RULE_ID,
        AREA_RULE_ID,
    ),
}


def _basin_layer_loaded(connection: psycopg.Connection) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            f"select 1 from {CANONICAL_TABLE} where boundary_kind = 'basin' limit 1"
        )
        return cursor.fetchone() is not None


def _promote(
    connection: psycopg.Connection,
    spec: LayerSpec,
    *,
    manifest_id: str,
    vintage: date,
    parse_derivation_id: str,
    staged_rows: int,
    datum: ConformanceRule,
) -> LoadResult:
    if spec.boundary_kind == "play" and not _basin_layer_loaded(connection):
        raise BasinLayerMissing(
            "load the basin layer before the plays: cr_eia_basin_link_1 requires a null"
            " basin_boundary_id to mean the name did not resolve"
        )

    sql = _PROMOTIONS[spec.layer]
    counts = dict.fromkeys(spec.reason_codes, 0)
    parameters = {"manifest_id": manifest_id}
    held = 0
    for reason, statement, rule_id in (
        ("duplicate_row", sql.duplicates, PUBLISHER_RULE_ID),
        ("key_incomplete", sql.incomplete, PUBLISHER_RULE_ID),
    ):
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(statement, parameters)
            offending = cursor.fetchall()
        counts[reason] += _quarantine(
            connection,
            pl.DataFrame(offending),
            spec,
            manifest_id=manifest_id,
            reason_code=reason,
            stage="conform",
            rule_id=rule_id,
        )
        held += len(offending)

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(sql.invalid, parameters)
        invalid = cursor.fetchall()
    counts["invalid_geometry"] += _quarantine(
        connection,
        pl.DataFrame(invalid),
        spec,
        manifest_id=manifest_id,
        reason_code="invalid_geometry",
        stage="conform",
        rule_id=REPAIR_RULE_ID,
    )
    unrepairable = [row for row in invalid if not row["repaired"]]
    held += len(unrepairable)

    output = OutputSpec(
        store="postgis", dataset=CANONICAL_TABLE, partition={"manifest_id": manifest_id}
    )
    with derive(
        "canonical.promote",
        output=output,
        params={
            "layer": spec.layer,
            "boundary_kind": spec.boundary_kind,
            "storage_epsg": int(datum.spec["target_epsg"]),
            "area_basis": AREA_BASIS,
            "repaired": len(invalid) - len(unrepairable),
            "unrepairable": len(unrepairable),
        },
        inputs=[
            InputRef(kind="derivation", ref_id=parse_derivation_id),
            InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage),
        ],
        rules=list(_PROMOTION_RULES[spec.layer]),
    ) as context:
        promotable = staged_rows - held
        context.set_rows(promotable)
        context.set_output_hash(hash_payload({"manifest_id": manifest_id, "rows": promotable}))

    derivation_id = context.derivation_id
    with connection.cursor() as cursor:
        cursor.execute(
            sql.insert,
            {
                **parameters,
                "area_basis": AREA_BASIS,
                "repair_operator": REPAIR_OPERATOR,
                "source_datum": f"EPSG:{int(datum.spec['source_epsg'])}",
                "transform_rule_id": datum.rule_id,
                "derivation_id": derivation_id,
            },
        )
        inserted = max(cursor.rowcount, 0)

    _release_repaired(connection, spec, invalid, derivation_id)

    # DR-89: an all-conflict revision owns nothing and must become a ledger fact, not a no-op.
    if promotable and not inserted and not _owns_canonical(connection, manifest_id):
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(sql.refused, parameters)
            refused = cursor.fetchall()
        counts["key_collision"] += _quarantine(
            connection,
            pl.DataFrame(refused),
            spec,
            manifest_id=manifest_id,
            reason_code="key_collision",
            stage="join",
        )

    record_vintage_day(
        connection,
        source_id=spec.source_id,
        vintage_date=vintage,
        manifest_ids=[manifest_id],
        opened_at=current_session().clock.now(),
        promotion_derivation_id=derivation_id,
        rows_examined=staged_rows,
        rows_appended=inserted,
    )

    return LoadResult(
        layer=spec.layer,
        source_id=spec.source_id,
        manifest_id=manifest_id,
        parse_derivation_id=parse_derivation_id,
        promote_derivation_id=derivation_id,
        staged_rows=staged_rows,
        promoted_rows=inserted,
        quarantined=counts,
        repaired=len(invalid) - len(unrepairable),
        unlinked=_unlinked(connection, manifest_id) if spec.boundary_kind == "play" else 0,
    )


def _release_repaired(
    connection: psycopg.Connection,
    spec: LayerSpec,
    invalid: Sequence[Mapping[str, Any]],
    derivation_id: str,
) -> None:
    """A repaired reject is released, not erased: the reason and the release both stay."""
    rescued = [str(row["boundary_id"]) for row in invalid if row["repaired"]]
    if not rescued:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            _RELEASE_REPAIRED,
            {
                "rule_id": REPAIR_RULE_ID,
                "released_at": current_session().clock.now(),
                "derivation_id": derivation_id,
                "source_id": spec.source_id,
                "boundary_ids": rescued,
            },
        )


def _unlinked(connection: psycopg.Connection, manifest_id: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            f"select count(*) from {CANONICAL_TABLE}"
            " where boundary_kind = 'play' and basin_boundary_id is null"
            "   and source_manifest_id = %s",
            (manifest_id,),
        )
        return int(cursor.fetchone()[0])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load the EIA basin and play boundaries into PostGIS."
    )
    parser.add_argument("--layer", choices=[*LAYERS, "all"], required=True)
    add_dsn_argument(parser)
    parser.add_argument("--raw-root", default=None)
    parser.add_argument("--env-id", default=None, help="override the fingerprinted env id")
    parser.add_argument("--code-version", default=None)
    parser.add_argument(
        "--restage",
        action="store_true",
        help="re-parse and re-promote from the stored bytes after a rule or schema change",
    )
    arguments = parser.parse_args(argv)
    arguments.dsn = resolve_dsn(arguments.dsn)

    # Basins first: a play whose Basin string resolves nothing must be an unresolved link and
    # never an unloaded basin layer (cr_eia_basin_link_1).
    layers = list(LAYERS) if arguments.layer == "all" else [arguments.layer]
    with durable_fetch_attempts(arguments.dsn), psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        with lineage_session(recorder=PostgresRecorder(connection), environment=environment):
            for layer in layers:
                result = load_layer(
                    connection,
                    layer,
                    raw_root=arguments.raw_root,
                    restage=arguments.restage,
                )
                connection.commit()
                print(json.dumps(result.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
