"""Load the ND PLSS land grid from the BLM national CadNSDI NAD83 service (M1-4).

Both layers arrive through arcgis_rest_paginate (SB-01 §1.2.1): one ordered walk, one
checksummed newline-delimited artifact, one manifest. The ND scope, the publisher choice and
the datum transform are conformance rows, read here and never restated.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import psycopg
from psycopg.rows import dict_row
from shapely.geometry import shape

from glasswell.ingest.arcgis import arcgis_rest_paginate
from glasswell.ingest.base import record_vintage_day, resolve_environment
from glasswell.lineage import (
    ConformanceRule,
    InputRef,
    OutputSpec,
    PostgresRecorder,
    current_session,
    derive,
    lineage_session,
    load_rules,
    quarantine,
)
from glasswell.lineage.fetch_attempts import durable_fetch_attempts
from glasswell.lineage.serialization import hash_payload

SERVICE_URL = (
    "https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI_NAD83/MapServer"
)
RULE_SOURCE = "blm_plss_sections"
SCOPE_RULE_ID = "cr_blm_plss_scope_1"
PUBLISHER_RULE_ID = "cr_blm_plss_publisher_1"
STATE = "ND"


class SchemaDrift(ValueError):
    """The service no longer carries a property the staging table declares."""


class DatumMismatch(ValueError):
    """The service's recorded spatial reference disagrees with the conformance registry."""


@dataclass(frozen=True, slots=True)
class LayerSpec:
    layer: str
    source_id: str
    source_key: str
    layer_id: int
    unit_type: str
    staging_table: str
    columns: tuple[str, ...]
    reason_codes: tuple[str, ...]


LAYERS: Mapping[str, LayerSpec] = {
    "townships": LayerSpec(
        layer="townships",
        source_id="blm_plss_townships",
        source_key="nd_townships.geojsonl",
        layer_id=1,
        unit_type="township",
        staging_table="staging.blm_plss_townships",
        columns=(
            "plssid", "twnshpno", "twnshpdir", "rangeno", "rangedir", "twnshplab", "prinmer",
            "survtyp",
        ),
        reason_codes=("parse_error", "key_incomplete", "duplicate_row", "key_collision"),
    ),
    "sections": LayerSpec(
        layer="sections",
        source_id="blm_plss_sections",
        source_key="nd_sections.geojsonl",
        layer_id=2,
        unit_type="section",
        staging_table="staging.blm_plss_sections",
        columns=("plssid", "frstdivid", "frstdivno", "frstdivlab", "frstdivtyp", "survtyp"),
        reason_codes=(
            "parse_error", "key_incomplete", "duplicate_row", "orphan_fk", "key_collision",
        ),
    ),
}

CANONICAL_TABLE = "canonical.land_units"


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "manifest_id": self.manifest_id,
            "staged_rows": self.staged_rows,
            "promoted_rows": self.promoted_rows,
            "quarantined": dict(self.quarantined),
            "unchanged": self.unchanged,
        }


def load_townships(connection: psycopg.Connection, **kwargs: Any) -> LoadResult:
    """Fetch the ND township slice, stage it, and promote to canonical.land_units."""
    return _load(connection, LAYERS["townships"], **kwargs)


def load_sections(connection: psycopg.Connection, **kwargs: Any) -> LoadResult:
    """Fetch the ND section slice, stage it, and promote under its parent townships."""
    return _load(connection, LAYERS["sections"], **kwargs)


def load_layer(connection: psycopg.Connection, layer: str, **kwargs: Any) -> LoadResult:
    return _load(connection, LAYERS[layer], **kwargs)


def _load(
    connection: psycopg.Connection,
    spec: LayerSpec,
    *,
    service_url: str = SERVICE_URL,
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
    page_size: int | None = None,
    page_delay_seconds: float | None = None,
    restage: bool = False,
) -> LoadResult:
    datum = _rule(connection, kind="datum_transform")
    scope = _rule(connection, rule_id=SCOPE_RULE_ID)
    source_epsg = int(datum.spec["source_epsg"])
    storage_epsg = int(datum.spec["target_epsg"])

    fetch_kwargs: dict[str, Any] = {}
    if page_delay_seconds is not None:
        fetch_kwargs["page_delay_seconds"] = page_delay_seconds
    fetched = arcgis_rest_paginate(
        connection,
        spec.source_id,
        spec.source_key,
        service_url=service_url,
        layer_id=spec.layer_id,
        where=str(scope.spec["where"]),
        raw_root=raw_root,
        client=client,
        page_size=page_size,
        rules=(SCOPE_RULE_ID, PUBLISHER_RULE_ID),
        **fetch_kwargs,
    )
    manifest = fetched.manifest
    recorded_sr = manifest.acquisition_params.get("out_sr")
    if recorded_sr is not None and int(recorded_sr) != source_epsg:
        raise DatumMismatch(
            f"{spec.source_key} recorded wkid {recorded_sr}; the registry declares"
            f" EPSG:{source_epsg}"
        )

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


def _rule(
    connection: psycopg.Connection, *, kind: str | None = None, rule_id: str | None = None
) -> ConformanceRule:
    """The scope and the datum belong to the registry; both are read here, never written."""
    for rule in load_rules(connection, source_id=RULE_SOURCE):
        if kind is not None and rule.rule_kind == kind:
            return rule
        if rule_id is not None and rule.rule_id == rule_id:
            return rule
    raise LookupError(f"no {kind or rule_id} rule is seeded for {RULE_SOURCE}")


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


def _features(payload_path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """One FeatureCollection per line (SB-01 §1.2.1); the ordinal is the walk order."""
    ordinal = 0
    with payload_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            collection = json.loads(line)
            for feature in collection.get("features", ()):
                yield ordinal, feature
                ordinal += 1


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
    for ordinal, feature in _features(payload_path):
        attributes = {
            key.lower(): value for key, value in (feature.get("properties") or {}).items()
        }
        missing = [column for column in spec.columns if column not in attributes]
        if missing:
            raise SchemaDrift(f"{spec.source_key} has no {', '.join(missing)} property")
        row: dict[str, Any] = {
            column: None if attributes[column] is None else str(attributes[column])
            for column in spec.columns
        }
        row["manifest_id"] = manifest_id
        row["source_row_ordinal"] = ordinal
        note = _unstorable(feature.get("geometry"))
        row["geom_wkt"] = None if note else shape(feature["geometry"]).wkt
        rows.append(row)
        if note:
            rejected.append(
                {key: value for key, value in row.items() if key != "geom_wkt"} | {"detail": note}
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


def _unstorable(geometry: Mapping[str, Any] | None) -> str | None:
    if not geometry:
        return "the source feature carries no geometry"
    kind = geometry.get("type")
    if kind not in ("Polygon", "MultiPolygon"):
        return f"{kind} does not fit the declared MultiPolygon column"
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


_TOWNSHIPS_KEYED = """
with keyed as (
    select source_row_ordinal, plssid, twnshpno, twnshpdir, rangeno, rangedir, twnshplab,
           prinmer, survtyp,
           row_number() over (partition by plssid order by source_row_ordinal) as occurrence
      from staging.blm_plss_townships
     where manifest_id = %(manifest_id)s and geom is not null
       and nullif(plssid, '') is not null
)
"""

_INSERT_TOWNSHIPS = (
    _TOWNSHIPS_KEYED
    + """
insert into canonical.land_units (
    land_unit_id, unit_type, state, plssid, label, township_no, township_dir, range_no,
    range_dir, principal_meridian, survey_type, geom, source_datum, transform_rule_id,
    source_manifest_id, derivation_id)
select keyed.plssid, 'township', %(state)s, keyed.plssid,
       coalesce(nullif(keyed.twnshplab, ''),
                keyed.twnshpno || keyed.twnshpdir || ' ' || keyed.rangeno || keyed.rangedir),
       keyed.twnshpno, keyed.twnshpdir, keyed.rangeno, keyed.rangedir, keyed.prinmer,
       keyed.survtyp, staged.geom, %(source_datum)s, %(transform_rule_id)s, %(manifest_id)s,
       %(derivation_id)s
  from keyed
  join staging.blm_plss_townships staged
    on staged.manifest_id = %(manifest_id)s
   and staged.source_row_ordinal = keyed.source_row_ordinal
 where keyed.occurrence = 1
on conflict (land_unit_id) do nothing
"""
)

_DUPLICATE_TOWNSHIPS = (
    _TOWNSHIPS_KEYED
    + "select source_row_ordinal, plssid, twnshplab from keyed where occurrence > 1"
)

_REFUSED_TOWNSHIPS = (
    _TOWNSHIPS_KEYED
    + "select source_row_ordinal, plssid, twnshplab from keyed where occurrence = 1"
)

_INCOMPLETE_TOWNSHIPS = """
select source_row_ordinal, twnshplab
  from staging.blm_plss_townships
 where manifest_id = %(manifest_id)s and geom is not null and nullif(plssid, '') is null
"""

_SECTIONS_KEYED = """
with keyed as (
    select source_row_ordinal, plssid, frstdivid, frstdivno, frstdivlab, frstdivtyp, survtyp,
           row_number() over (partition by frstdivid order by source_row_ordinal) as occurrence
      from staging.blm_plss_sections
     where manifest_id = %(manifest_id)s and geom is not null
       and nullif(frstdivid, '') is not null and nullif(plssid, '') is not null
)
"""

_INSERT_SECTIONS = (
    _SECTIONS_KEYED
    + """
insert into canonical.land_units (
    land_unit_id, unit_type, state, plssid, frstdivid, label, section_no, survey_type, geom,
    source_datum, transform_rule_id, source_manifest_id, derivation_id)
select keyed.frstdivid, 'section', %(state)s, keyed.plssid, keyed.frstdivid,
       coalesce(nullif(keyed.frstdivlab, ''), keyed.frstdivno, keyed.frstdivid),
       keyed.frstdivno, keyed.survtyp, staged.geom, %(source_datum)s, %(transform_rule_id)s,
       %(manifest_id)s, %(derivation_id)s
  from keyed
  join staging.blm_plss_sections staged
    on staged.manifest_id = %(manifest_id)s
   and staged.source_row_ordinal = keyed.source_row_ordinal
 where keyed.occurrence = 1
   and exists (select 1 from canonical.land_units township
                where township.land_unit_id = keyed.plssid
                  and township.unit_type = 'township')
on conflict (land_unit_id) do nothing
"""
)

_DUPLICATE_SECTIONS = (
    _SECTIONS_KEYED
    + "select source_row_ordinal, frstdivid, frstdivlab from keyed where occurrence > 1"
)

_REFUSED_SECTIONS = (
    _SECTIONS_KEYED
    + """
select source_row_ordinal, plssid, frstdivid, frstdivlab
  from keyed
 where occurrence = 1
   and exists (select 1 from canonical.land_units township
                where township.land_unit_id = keyed.plssid
                  and township.unit_type = 'township')
"""
)

_INCOMPLETE_SECTIONS = """
select source_row_ordinal, plssid, frstdivid, frstdivlab
  from staging.blm_plss_sections
 where manifest_id = %(manifest_id)s and geom is not null
   and (nullif(frstdivid, '') is null or nullif(plssid, '') is null)
"""

_ORPHAN_SECTIONS = (
    _SECTIONS_KEYED
    + """
select source_row_ordinal, plssid, frstdivid, frstdivlab
  from keyed
 where occurrence = 1
   and not exists (select 1 from canonical.land_units township
                    where township.land_unit_id = keyed.plssid
                      and township.unit_type = 'township')
"""
)


@dataclass(frozen=True, slots=True)
class _PromotionSql:
    insert: str
    duplicates: str
    incomplete: str
    # The rows the insert would attempt, for the DR-89 all-conflict quarantine.
    refused: str
    orphans: str | None = None


_PROMOTIONS: Mapping[str, _PromotionSql] = {
    "townships": _PromotionSql(
        insert=_INSERT_TOWNSHIPS,
        duplicates=_DUPLICATE_TOWNSHIPS,
        incomplete=_INCOMPLETE_TOWNSHIPS,
        refused=_REFUSED_TOWNSHIPS,
    ),
    "sections": _PromotionSql(
        insert=_INSERT_SECTIONS,
        duplicates=_DUPLICATE_SECTIONS,
        incomplete=_INCOMPLETE_SECTIONS,
        refused=_REFUSED_SECTIONS,
        orphans=_ORPHAN_SECTIONS,
    ),
}


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
    sql = _PROMOTIONS[spec.layer]
    counts = dict.fromkeys(spec.reason_codes, 0)
    parameters = {"manifest_id": manifest_id}
    held = 0
    for reason, statement, rule_id in (
        ("duplicate_row", sql.duplicates, None),
        ("key_incomplete", sql.incomplete, None),
        ("orphan_fk", sql.orphans, PUBLISHER_RULE_ID),
    ):
        if statement is None:
            continue
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

    output = OutputSpec(
        store="postgis", dataset=CANONICAL_TABLE, partition={"manifest_id": manifest_id}
    )
    with derive(
        "canonical.promote",
        output=output,
        params={
            "layer": spec.layer,
            "unit_type": spec.unit_type,
            "storage_epsg": int(datum.spec["target_epsg"]),
        },
        inputs=[
            InputRef(kind="derivation", ref_id=parse_derivation_id),
            InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage),
        ],
        rules=[datum.rule_id, SCOPE_RULE_ID, PUBLISHER_RULE_ID],
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
                "state": STATE,
                "source_datum": f"EPSG:{int(datum.spec['source_epsg'])}",
                "transform_rule_id": datum.rule_id,
                "derivation_id": derivation_id,
            },
        )
        inserted = max(cursor.rowcount, 0)
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
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load the ND PLSS land grid into PostGIS.")
    parser.add_argument("--layer", choices=[*LAYERS, "all"], required=True)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--service-url", default=SERVICE_URL)
    parser.add_argument("--raw-root", default=None)
    parser.add_argument("--env-id", default=None, help="override the fingerprinted env id")
    parser.add_argument("--code-version", default=None)
    parser.add_argument(
        "--restage",
        action="store_true",
        help="re-parse and re-promote from the stored bytes after a rule or schema change",
    )
    arguments = parser.parse_args(argv)

    # Townships first: a section whose plssid has no township row is an orphan_fk.
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
                    service_url=arguments.service_url,
                    raw_root=arguments.raw_root,
                    restage=arguments.restage,
                )
                connection.commit()
                print(json.dumps(result.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
