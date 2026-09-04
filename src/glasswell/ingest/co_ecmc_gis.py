"""The three ECMC GIS archives into staging, on the datum each one ships.

One module, three layers, because ECMC republishes all three within seconds of each other and
a job that pulled them separately would be three jobs claiming one cadence. The layer is
selected by the archive's own stem, and the datum is resolved from the shipped .prj rather than
declared here: `cr_co_wells_datum_1` says a projection that does not resolve is a refusal, and
records the code the archives ship so a silently re-projected file is caught rather than
re-plotted.

Staging is the terminus. No state code appears in this module.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import psycopg

from glasswell.db.dsn import add_dsn_argument, resolve_dsn
from glasswell.ingest.base import IngestRun, open_ingest_run, resolve_environment
from glasswell.ingest.shapefile import UnknownProjection, ZippedShapefile
from glasswell.lineage.capture import derive
from glasswell.lineage.conformance import load_rules, rule_for_family
from glasswell.lineage.fetch import fetch_raw
from glasswell.lineage.fetch_attempts import durable_fetch_attempts
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.serialization import hash_payload
from glasswell.seed.conformance_co import CO_GIS_MEMBERS

__rule_version__ = "1"

DOWNLOAD_ROOT = "https://ecmc.state.co.us/documents/data/downloads/gis"
MEDIA_TYPE = "application/zip"
DATUM_FAMILY = "cr_co_wells_datum"
SCOPE_FAMILY = "cr_co_wells_geometry_scope"
MEMBER_FAMILIES = {
    "co_ecmc_wells_shp": "cr_co_wells_shp_member",
    "co_ecmc_directional_bh": "cr_co_directional_bh_member",
    "co_ecmc_directional_lines": "cr_co_directional_lines_member",
}


@dataclass(frozen=True, slots=True)
class LayerSpec:
    name: str
    source_id: str
    source_key: str
    layer_suffix: str
    staging_table: str

    @property
    def url(self) -> str:
        return f"{DOWNLOAD_ROOT}/{self.source_key}"


WELLS = LayerSpec(
    name="wells",
    source_id="co_ecmc_wells_shp",
    source_key=CO_GIS_MEMBERS["co_ecmc_wells_shp"]["source_key"],
    layer_suffix=CO_GIS_MEMBERS["co_ecmc_wells_shp"]["member_stem"],
    staging_table="staging.co_ecmc_wells",
)
BOTTOMHOLE = LayerSpec(
    name="bottomhole",
    source_id="co_ecmc_directional_bh",
    source_key=CO_GIS_MEMBERS["co_ecmc_directional_bh"]["source_key"],
    layer_suffix=CO_GIS_MEMBERS["co_ecmc_directional_bh"]["member_stem"],
    staging_table="staging.co_ecmc_directional_bh",
)
LINES = LayerSpec(
    name="lines",
    source_id="co_ecmc_directional_lines",
    source_key=CO_GIS_MEMBERS["co_ecmc_directional_lines"]["source_key"],
    layer_suffix=CO_GIS_MEMBERS["co_ecmc_directional_lines"]["member_stem"],
    staging_table="staging.co_ecmc_directional_lines",
)
LAYERS: tuple[LayerSpec, ...] = (WELLS, BOTTOMHOLE, LINES)
BY_NAME = {layer.name: layer for layer in LAYERS}


@dataclass(frozen=True, slots=True)
class LayerReport:
    layer: str
    source_id: str
    manifest_id: str
    rows_staged: int
    source_epsg: int

    def to_dict(self) -> dict[str, object]:
        return {
            "layer": self.layer,
            "source_id": self.source_id,
            "manifest_id": self.manifest_id,
            "rows_staged": self.rows_staged,
            "source_epsg": self.source_epsg,
        }


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


def _already_staged(connection: psycopg.Connection, table: str, manifest_id: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"select count(*) from {table} where manifest_id = %s", (manifest_id,))
        return int(cursor.fetchone()[0])


def stage_layer(
    connection: psycopg.Connection,
    layer: LayerSpec,
    *,
    archive: Path,
    manifest_id: str,
    expected_epsg: int,
    storage_epsg: int,
) -> tuple[int, int]:
    """Stage one archive verbatim, transforming the shipped datum on the way in."""
    columns = _staging_columns(connection, layer.staging_table)
    quoted = ", ".join(
        f'"{name}"' for name in ("manifest_id", "source_row_ordinal", *columns, "geom")
    )
    placeholders = ", ".join(["%s"] * (len(columns) + 2))
    statement = (
        f"insert into {layer.staging_table} ({quoted})"
        f" values ({placeholders},"
        f" ST_Transform(ST_GeomFromText(%s, {{source_epsg}}), {storage_epsg}))"
    )
    rows: list[tuple[Any, ...]] = []
    with ZippedShapefile(archive, layer_suffix=layer.layer_suffix) as source:
        source_epsg = source.source_epsg
        if source_epsg != expected_epsg:
            raise UnknownProjection(
                f"{layer.source_key} ships EPSG:{source_epsg}; cr_co_wells_datum_1 records"
                f" EPSG:{expected_epsg}. A re-projected archive is a refusal, not a re-plot"
            )
        for entry in source:
            attributes = {key.lower(): value for key, value in entry.attributes.items()}
            rows.append(
                (
                    manifest_id,
                    entry.ordinal + 1,
                    *(
                        None if attributes.get(name) is None else str(attributes[name]).strip()
                        for name in columns
                    ),
                    None if entry.is_empty else entry.geometry.wkt,
                )
            )
    with connection.cursor() as cursor:
        cursor.executemany(statement.format(source_epsg=source_epsg), rows)
    return len(rows), source_epsg


def ingest_layer(
    run: IngestRun,
    layer: LayerSpec,
    *,
    url: str | None = None,
    client: httpx.Client | None = None,
) -> LayerReport:
    """Fetch one ECMC archive and stage its layer under the datum and scope rules."""
    connection = run.connection
    conform = load_rules(connection, source_id=WELLS.source_id, stage="conform", as_of=run.as_of)
    datum = rule_for_family(conform, DATUM_FAMILY)
    scope = rule_for_family(conform, SCOPE_FAMILY)
    member = rule_for_family(
        load_rules(connection, source_id=layer.source_id, stage="parse", as_of=run.as_of),
        MEMBER_FAMILIES[layer.source_id],
    )
    fetched = fetch_raw(
        connection,
        layer.source_id,
        layer.source_key,
        url=url or layer.url,
        raw_root=run.raw_root,
        client=client,
        media_type=MEDIA_TYPE,
        rules=[datum.rule_id, scope.rule_id],
    )
    manifest = fetched.manifest
    with derive(
        "stage.parse",
        output=OutputSpec(
            store="postgis",
            dataset=layer.staging_table,
            partition={"manifest_id": manifest.manifest_id},
        ),
        params={"source_key": layer.source_key, "layer_suffix": layer.layer_suffix},
        inputs=[
            InputRef(
                kind="manifest",
                ref_id=manifest.manifest_id,
                role="primary",
                as_of_vintage=manifest.fetch_vintage,
            )
        ],
        rules=[datum.rule_id, scope.rule_id, member.rule_id],
    ) as parsing:
        staged = _already_staged(connection, layer.staging_table, manifest.manifest_id)
        source_epsg = int(datum.spec["measured_source_epsg"])
        if not staged:
            staged, source_epsg = stage_layer(
                connection,
                layer,
                archive=fetched.payload_path,
                manifest_id=manifest.manifest_id,
                expected_epsg=int(datum.spec["measured_source_epsg"]),
                storage_epsg=int(datum.spec["storage_epsg"]),
            )
        parsing.set_rows(staged)
        parsing.set_output_hash(
            hash_payload({"rows": staged, "manifest_id": manifest.manifest_id})
        )
    return LayerReport(
        layer=layer.name,
        source_id=layer.source_id,
        manifest_id=manifest.manifest_id,
        rows_staged=staged,
        source_epsg=source_epsg,
    )


def selected(argument: str) -> tuple[LayerSpec, ...]:
    return LAYERS if argument == "all" else (BY_NAME[argument],)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stage the ECMC GIS archives. Staging is the terminus."
    )
    add_dsn_argument(parser)
    parser.add_argument("--layer", default="all", choices=[*BY_NAME, "all"])
    parser.add_argument("--raw-root", default=None)
    parser.add_argument("--env-id", default=None)
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)
    arguments.dsn = resolve_dsn(arguments.dsn)

    reports: list[dict[str, object]] = []
    with durable_fetch_attempts(arguments.dsn), psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        for layer in selected(arguments.layer):
            with open_ingest_run(
                connection,
                source_id=layer.source_id,
                raw_root=arguments.raw_root,
                environment=environment,
            ) as run:
                reports.append(ingest_layer(run, layer).to_dict())
            connection.commit()
    print(json.dumps(reports, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
