"""MBOGC GIS: surface points and well paths, staged then promoted to canonical geometry.

Two archives, each shipping a geographic layer and a NAD83 Montana StatePlane twin. The layer
is selected by stem under cr_mt_gis_layer_selection_1 rather than by archive order, and the DBF
is read as Windows-1252 under cr_mt_gis_encoding_1; both are registry decisions, not defaults.

Well paths are cartographic centrelines. They promote as `lateral` geometry because that is the
canonical class for a producing interval's trace, and cr_mt_paths_geometry_class_1 is what
stops anything downstream reading survey accuracy into a two-point line.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import psycopg

from glasswell.db.dsn import add_dsn_argument, resolve_dsn
from glasswell.identity import api10_identity
from glasswell.ingest.base import IngestRun, open_ingest_run, record_vintage_day
from glasswell.ingest.shapefile import ZippedShapefile
from glasswell.lineage.audit import emit
from glasswell.lineage.capture import derive
from glasswell.lineage.conformance import load_rules, rule_for_family
from glasswell.lineage.fetch import fetch_raw
from glasswell.lineage.fetch_attempts import durable_fetch_attempts
from glasswell.lineage.models import ConformanceRule, InputRef, OutputSpec
from glasswell.lineage.quarantine import quarantine
from glasswell.lineage.serialization import hash_payload

__rule_version__ = "1"

HOST = "https://bogfiles.dnrc.mt.gov"
MEDIA_TYPE = "application/zip"
DBF_ENCODING = "cp1252"
STATE_CODE = "25"
IDENTITY_FAMILY = "cr_mt_gis_api_identity"
DATUM_FAMILY = "cr_mt_gis_datum"
PATHS_DATUM_FAMILY = "cr_mt_paths_datum"
STATUS_RULE = "cr_mt_gis_status_vocab_1"

UNKNOWN_STATUS_REASON = "unknown_status"
IDENTITY_REASON = "parse_error"


@dataclass(frozen=True, slots=True)
class LayerSpec:
    source_id: str
    source_key: str
    url: str
    layer_suffix: str
    staging_table: str
    geom_type: str
    datum_family: str


WELLS = LayerSpec(
    source_id="mt_gis_wells",
    source_key="Wells.zip",
    url=f"{HOST}/GISData/WellSurface/Wells.zip",
    layer_suffix="wells",
    staging_table="staging.mt_gis_wells",
    geom_type="surface",
    datum_family=DATUM_FAMILY,
)
WELL_PATHS = LayerSpec(
    source_id="mt_gis_well_paths",
    source_key="WellPaths.zip",
    url=f"{HOST}/GISData/WellPaths/WellPaths.zip",
    layer_suffix="WellPaths",
    staging_table="staging.mt_gis_well_paths",
    geom_type="lateral",
    datum_family=PATHS_DATUM_FAMILY,
)
LAYERS = (WELLS, WELL_PATHS)


@dataclass(frozen=True, slots=True)
class LayerReport:
    source_key: str
    manifest_id: str
    staged_rows: int = 0
    spatial_rows: int = 0
    well_rows: int = 0
    unchanged: bool = False
    quarantined: Mapping[str, int] = field(default_factory=dict)
    parse_derivation_id: str | None = None
    promote_derivation_id: str | None = None


def _staging_columns(connection: psycopg.Connection, table: str) -> list[str]:
    schema, _, name = table.partition(".")
    with connection.cursor() as cursor:
        cursor.execute(
            "select column_name from information_schema.columns"
            " where table_schema = %s and table_name = %s"
            "   and column_name not in ('manifest_id', 'source_row_ordinal', 'ingested_at',"
            "                           'geom')"
            " order by ordinal_position",
            (schema, name),
        )
        return [row[0] for row in cursor.fetchall()]


def _datum_rule(rules: Sequence[ConformanceRule], family: str) -> ConformanceRule:
    """The transform belongs to the registry, so its EPSG pair is read, never written here."""
    return rule_for_family(rules, family)


def stage_layer(
    connection: psycopg.Connection,
    layer: LayerSpec,
    *,
    archive: Path,
    manifest_id: str,
    source_epsg: int,
    storage_epsg: int,
) -> int:
    """Stage one shapefile layer, transforming the shipped datum on the way in."""
    columns = _staging_columns(connection, layer.staging_table)
    quoted = ", ".join(
        f'"{name}"' for name in ("manifest_id", "source_row_ordinal", *columns, "geom")
    )
    placeholders = ", ".join(["%s"] * (len(columns) + 2))
    statement = (
        f"insert into {layer.staging_table} ({quoted})"
        f" values ({placeholders},"
        f" ST_Transform(ST_GeomFromText(%s, {source_epsg}), {storage_epsg}))"
    )
    rows: list[tuple[Any, ...]] = []
    with ZippedShapefile(
        archive, layer_suffix=layer.layer_suffix, encoding=DBF_ENCODING
    ) as source:
        if source.source_epsg != source_epsg:
            raise ValueError(
                f"{layer.source_key} ships EPSG:{source.source_epsg}; the registry declares"
                f" EPSG:{source_epsg}"
            )
        for entry in source:
            attributes = {key.lower(): value for key, value in entry.attributes.items()}
            rows.append(
                (
                    manifest_id,
                    entry.ordinal + 1,
                    *(
                        None if attributes.get(name) is None else str(attributes[name])
                        for name in columns
                    ),
                    None if entry.is_empty else entry.geometry.wkt,
                )
            )
    with connection.cursor() as cursor:
        cursor.executemany(statement, rows)
    return len(rows)


_INSERT_SPATIAL = """
insert into canonical.well_spatial (api10, geom_type, geom_key, geom, source_datum,
                                    transform_rule_id, source_manifest_id, derivation_id)
select %(api10)s, %(geom_type)s, %(geom_key)s, s.geom, %(source_datum)s,
       %(transform_rule_id)s, %(manifest_id)s, %(derivation_id)s
  from {table} s
 where s.manifest_id = %(manifest_id)s and s.source_row_ordinal = %(ordinal)s
   and s.geom is not null
on conflict (api10, geom_type, geom_key) do nothing
"""

_INSERT_WELL = """
insert into canonical.wells (api10, api14, state_code, operator_name_reported, well_name,
                             status_reported, status_canonical, well_type_reported,
                             completion_date, effective_from, source_manifest_id,
                             derivation_id)
values (%(api10)s, %(api14)s, %(state_code)s, %(operator)s, %(well_name)s,
        %(status_reported)s, %(status_canonical)s, %(well_type)s, %(completion_date)s,
        %(effective_from)s, %(manifest_id)s, %(derivation_id)s)
on conflict do nothing
"""


def _status_map(connection: psycopg.Connection) -> dict[str, str]:
    with connection.cursor() as cursor:
        cursor.execute("select status, status_canonical from lineage.mt_status_promoted_map")
        return dict(cursor.fetchall())


def _completion_date(value: str | None) -> date | None:
    if not value:
        return None
    parts = value.strip().split("/")
    if len(parts) != 3:
        return None
    try:
        month, day, year = (int(part) for part in parts)
        return date(year, month, day)
    except ValueError:
        return None


def _quarantine_rejects(
    run: IngestRun,
    layer: LayerSpec,
    *,
    manifest_id: str,
    rejected: Mapping[tuple[str, str, str], list[dict[str, Any]]],
    counts: dict[str, int],
) -> None:
    """Write every rejected row to the ledger. A counted reject that never lands there is a
    dropped row wearing a number, which is the one thing §3.4 forbids outright."""
    for (reason_code, rule_id, stage), rows in rejected.items():
        result = quarantine(
            run.connection,
            pl.DataFrame(rows, infer_schema_length=None),
            reason_code=reason_code,
            manifest_id=manifest_id,
            source_id=layer.source_id,
            staging_table=layer.staging_table,
            stage=stage,
            seen_at=run.session.clock.now(),
            rule_id=rule_id,
            correlation_id=run.session.correlation_id,
        )
        counts[reason_code] = (
            counts.get(reason_code, 0) + result.opened + result.reoccurred
        )


def promote_layer(
    run: IngestRun,
    layer: LayerSpec,
    *,
    manifest: Any,
    parse_derivation_id: str,
    datum: ConformanceRule,
    identity: Any,
    counts: dict[str, int],
) -> tuple[str, int, int]:
    """Promote one staged layer into canonical geometry, and headers for the point layer."""
    connection = run.connection
    columns = _staging_columns(connection, layer.staging_table)
    selection = ", ".join(f'"{name}"' for name in ("source_row_ordinal", *columns))
    with connection.cursor() as cursor:
        cursor.execute(
            f"select {selection} from {layer.staging_table}"
            f" where manifest_id = %s and geom is not null order by source_row_ordinal",
            (manifest.manifest_id,),
        )
        staged = [dict(zip(("source_row_ordinal", *columns), row, strict=True))
                  for row in cursor.fetchall()]

    statuses = _status_map(connection) if layer.geom_type == "surface" else {}
    source_datum = f"EPSG:{int(datum.spec['source_epsg'])}"

    geometry_rows: list[dict[str, Any]] = []
    header_rows: list[dict[str, Any]] = []
    rejected: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in staged:
        api10 = identity.normalize(row.get("api_wellno"))
        if api10 is None:
            rejected.setdefault((IDENTITY_REASON, identity.rule_id, "parse"), []).append(row)
            continue
        # cr_mt_paths_subkey_1: 875 wells carry more than one path, so a lateral is keyed by
        # its WellSub within the API-10. A point layer has one geometry per well.
        geom_key = (
            str(row.get("wellsub") or "LT01") if layer.geom_type == "lateral" else api10
        )
        geometry_rows.append(
            {
                "api10": api10,
                "geom_type": layer.geom_type,
                "geom_key": geom_key,
                "source_datum": source_datum,
                "transform_rule_id": datum.rule_id,
                "manifest_id": manifest.manifest_id,
                "ordinal": row["source_row_ordinal"],
            }
        )
        if layer.geom_type != "surface":
            continue
        reported = row.get("status")
        canonical = statuses.get(str(reported)) if reported is not None else None
        if canonical is None:
            rejected.setdefault((UNKNOWN_STATUS_REASON, STATUS_RULE, "conform"), []).append(row)
            continue
        header_rows.append(
            {
                "api10": api10,
                "api14": row.get("api_wellno"),
                "state_code": STATE_CODE,
                "operator": row.get("coname"),
                "well_name": row.get("well_nm"),
                "status_reported": reported,
                "status_canonical": canonical,
                "well_type": row.get("type"),
                "completion_date": _completion_date(row.get("completed")),
                "effective_from": run.as_of,
                "manifest_id": manifest.manifest_id,
            }
        )

    _quarantine_rejects(run, layer, manifest_id=manifest.manifest_id, rejected=rejected,
                        counts=counts)

    with derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgis",
            dataset="canonical.well_spatial",
            partition={"manifest_id": manifest.manifest_id, "geom_type": layer.geom_type},
        ),
        params={
            "source_key": layer.source_key,
            "layer_suffix": layer.layer_suffix,
            "geom_type": layer.geom_type,
            "state_code": STATE_CODE,
            "source_epsg": int(datum.spec["source_epsg"]),
            "storage_epsg": int(datum.spec["target_epsg"]),
            "dbf_encoding": DBF_ENCODING,
            # cr_mt_paths_geometry_class_1: the class is recorded on the derivation, so a
            # consumer reading provenance learns it from the ledger and not from a caveat.
            "is_directional_survey": False,
        },
        inputs=[
            InputRef(kind="derivation", ref_id=parse_derivation_id),
            InputRef(
                kind="manifest",
                ref_id=manifest.manifest_id,
                role="primary",
                as_of_vintage=manifest.fetch_vintage,
            ),
        ],
    ) as promotion:
        promotion.add_rule(datum.rule_id, applied_rows=len(staged))
        promotion.set_rows(len(geometry_rows))
        promotion.set_output_hash(
            hash_payload([(row["api10"], row["geom_key"]) for row in geometry_rows])
        )

    # After the block, never inside it: canonical.well_spatial has a foreign key to
    # lineage.derivations and derive() writes that row on exit.
    spatial = 0
    headers = 0
    with connection.cursor() as cursor:
        for row in geometry_rows:
            cursor.execute(
                _INSERT_SPATIAL.format(table=layer.staging_table),
                {**row, "derivation_id": promotion.derivation_id},
            )
            spatial += cursor.rowcount
        for row in header_rows:
            cursor.execute(
                _INSERT_WELL, {**row, "derivation_id": promotion.derivation_id}
            )
            headers += cursor.rowcount
    return promotion.derivation_id, spatial, headers


def ingest_layer(
    run: IngestRun,
    layer: LayerSpec,
    *,
    url: str | None = None,
    client: httpx.Client | None = None,
) -> LayerReport:
    """Fetch one MBOGC GIS archive, stage its declared layer, and promote it."""
    connection = run.connection
    fetched = fetch_raw(
        connection,
        layer.source_id,
        layer.source_key,
        url=url or layer.url,
        raw_root=run.raw_root,
        client=client,
        media_type=MEDIA_TYPE,
    )
    manifest = fetched.manifest
    parse_rules = load_rules(
        connection, source_id=layer.source_id, stage="parse", as_of=run.as_of
    )
    conform_rules = load_rules(
        connection, source_id=layer.source_id, stage="conform", as_of=run.as_of
    )
    datum = _datum_rule(conform_rules, layer.datum_family)
    identity = api10_identity(
        rule_for_family(
            parse_rules if layer.geom_type == "surface" else _identity_rules(connection, run),
            IDENTITY_FAMILY,
        )
    )

    counts: dict[str, int] = {}
    with derive(
        "stage.parse",
        output=OutputSpec(
            store="postgis",
            dataset=layer.staging_table,
            partition={"manifest_id": manifest.manifest_id},
        ),
        params={"source_key": layer.source_key, "layer_suffix": layer.layer_suffix,
                "dbf_encoding": DBF_ENCODING},
        inputs=[
            InputRef(
                kind="manifest",
                ref_id=manifest.manifest_id,
                role="primary",
                as_of_vintage=manifest.fetch_vintage,
            )
        ],
    ) as parsing:
        staged = _already_staged(connection, layer.staging_table, manifest.manifest_id)
        if not staged:
            staged = stage_layer(
                connection,
                layer,
                archive=fetched.payload_path,
                manifest_id=manifest.manifest_id,
                source_epsg=int(datum.spec["source_epsg"]),
                storage_epsg=int(datum.spec["target_epsg"]),
            )
        parsing.set_rows(staged)
        parsing.set_output_hash(hash_payload([layer.source_key, staged]))
        emit(
            connection,
            "staging.load_completed",
            subject_type="manifest",
            subject_id=manifest.manifest_id,
            payload={"table": layer.staging_table, "rows": staged},
            correlation_id=run.session.correlation_id,
            occurred_at=run.session.clock.now(),
        )

    promote_derivation_id, spatial, headers = promote_layer(
        run,
        layer,
        manifest=manifest,
        parse_derivation_id=parsing.derivation_id,
        datum=datum,
        identity=identity,
        counts=counts,
    )
    record_vintage_day(
        connection,
        source_id=layer.source_id,
        vintage_date=run.as_of,
        manifest_ids=[manifest.manifest_id],
        opened_at=run.session.clock.now(),
        promotion_derivation_id=promote_derivation_id,
        rows_examined=staged,
        rows_appended=spatial,
    )
    return LayerReport(
        source_key=layer.source_key,
        manifest_id=manifest.manifest_id,
        staged_rows=staged,
        spatial_rows=spatial,
        well_rows=headers,
        unchanged=fetched.unchanged,
        quarantined=counts,
        parse_derivation_id=parsing.derivation_id,
        promote_derivation_id=promote_derivation_id,
    )


def _identity_rules(connection: psycopg.Connection, run: IngestRun) -> list[ConformanceRule]:
    """The paths layer has no identity rule of its own; the point layer's slice is the spine."""
    return load_rules(connection, source_id=WELLS.source_id, stage="parse", as_of=run.as_of)


def _already_staged(connection: psycopg.Connection, table: str, manifest_id: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"select count(*) from {table} where manifest_id = %s", (manifest_id,))
        return int(cursor.fetchone()[0])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest the MBOGC GIS layers.")
    add_dsn_argument(parser)
    parser.add_argument("--raw-root")
    parser.add_argument(
        "--layer",
        action="append",
        choices=[layer.source_key for layer in LAYERS],
        help="ingest only this archive; repeatable",
    )
    arguments = parser.parse_args(argv)
    arguments.dsn = resolve_dsn(arguments.dsn)
    selected = [
        layer for layer in LAYERS if not arguments.layer or layer.source_key in arguments.layer
    ]

    reports: list[LayerReport] = []
    with durable_fetch_attempts(arguments.dsn), psycopg.connect(arguments.dsn) as connection:
        for layer in selected:
            with open_ingest_run(
                connection, source_id=layer.source_id, raw_root=arguments.raw_root
            ) as run:
                reports.append(ingest_layer(run, layer))
        connection.commit()
    for report in reports:
        print(
            f"{report.source_key}: staged {report.staged_rows}, geometry {report.spatial_rows},"
            f" headers {report.well_rows}, quarantined {dict(report.quarantined)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
