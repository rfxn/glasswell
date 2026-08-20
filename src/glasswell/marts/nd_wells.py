"""The ND tile marts: narrow projections of canonical, rebuilt inside one `mart.refresh`.

Marts read canonical only (blueprint §3.0.1) and are rebuilt rather than appended, so every
refresh is `delete` + `insert … select` in the caller's transaction.
"""

from __future__ import annotations

import argparse
import json
import platform
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import psycopg

from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.conformance import load_rules
from glasswell.lineage.models import DeriveEnvironment, InputRef, OutputSpec
from glasswell.lineage.serialization import hash_payload
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.tiles import TILE_LAYERS, install_tile_functions
from glasswell.units import METRES_PER_FOOT

COMPUTE_CRS_RULE = "cr_nd_compute_crs_1"
COMPUTE_CRS_SOURCE = "nd_gis_horizontals_line"
DATUM_RULE = "cr_nd_datum_1"

_WELLS_AS_OF = """
with wells_as_of as (
    select distinct on (api10) api10, operator_name_reported, status_canonical, spud_date
      from canonical.wells
     where %(as_of)s::date is null or effective_from <= %(as_of)s::date
     order by api10, effective_from desc, created_at desc)
"""

# Left join: a lateral whose api10 has no well row still tiles, unstyled, rather than
# disappearing between canonical and the map.
_LATERALS_SELECT = (
    _WELLS_AS_OF
    + """
select s.api10,
       s.geom_key as linekey,
       w.operator_name_reported as operator_name,
       w.status_canonical,
       extract(year from w.spud_date)::int as spud_year,
       ST_Length(ST_Transform(s.geom, %(compute_epsg)s))::numeric
           / %(metres_per_foot)s as lateral_length_ft,
       s.geom
  from canonical.well_spatial s
  left join wells_as_of w on w.api10 = s.api10
 where s.geom_type = 'lateral'
"""
)

_WELLS_SELECT = (
    _WELLS_AS_OF
    + """
select s.api10,
       w.operator_name_reported as operator_name,
       w.status_canonical,
       extract(year from w.spud_date)::int as spud_year,
       s.geom
  from canonical.well_spatial s
  left join wells_as_of w on w.api10 = s.api10
 where s.geom_type = 'surface'
"""
)

# Spacing units never restate, so the tile source is a view: current for free, no refresh cost.
_SPACING_UNITS_VIEW = """
create or replace view marts.nd_spacing_units_tile as
select spacing_unit_id, label, formation_reported, ds_size_acres, derivation_id, geom
  from canonical.spacing_units
"""

_INPUT_DERIVATIONS = """
select derivation_id, created_vintage
  from lineage.derivations
 where derivation_id in (select derivation_id from canonical.well_spatial
                          union select derivation_id from canonical.wells)
 order by derivation_id
"""


@dataclass(frozen=True, slots=True)
class _Projection:
    table: str
    columns: tuple[str, ...]
    select: str


_PROJECTIONS: tuple[_Projection, ...] = (
    _Projection(
        table="nd_laterals_tile",
        columns=(
            "api10",
            "linekey",
            "operator_name",
            "status_canonical",
            "spud_year",
            "lateral_length_ft",
            "geom",
        ),
        select=_LATERALS_SELECT,
    ),
    _Projection(
        table="nd_wells_tile",
        columns=("api10", "operator_name", "status_canonical", "spud_year", "geom"),
        select=_WELLS_SELECT,
    ),
)


@dataclass(frozen=True, slots=True)
class MartRefresh:
    derivation_id: str
    row_counts: Mapping[str, int]
    layers: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "derivation_id": self.derivation_id,
            "row_counts": dict(self.row_counts),
            "layers": list(self.layers),
        }


def refresh_all(connection: psycopg.Connection, *, as_of: date | None = None) -> MartRefresh:
    """Rebuild every ND tile mart from canonical under one content-addressed derivation."""
    compute_epsg = _compute_epsg(connection)
    parameters: dict[str, object] = {
        "as_of": as_of,
        "compute_epsg": compute_epsg,
        "metres_per_foot": METRES_PER_FOOT,
    }
    with connection.cursor() as cursor:
        cursor.execute(_SPACING_UNITS_VIEW)
    measured = {p.table: _measure(connection, p, parameters) for p in _PROJECTIONS}

    with derive(
        "mart.refresh",
        output=OutputSpec(
            store="postgis", dataset="marts.nd_tiles", partition={"state": "ND"}, schema_version="1"
        ),
        params={
            "as_of": as_of.isoformat() if as_of else None,
            "compute_epsg": compute_epsg,
            "layers": [layer.name for layer in TILE_LAYERS],
        },
        inputs=_canonical_inputs(connection),
        rules=[COMPUTE_CRS_RULE, DATUM_RULE],
    ) as context:
        context.set_rows(sum(rows for rows, _ in measured.values()))
        context.set_output_hash(hash_payload({table: d for table, (_, d) in measured.items()}))

    # The id is content-addressed and only exists once the block closes, so the rows carrying it
    # are written after it — one transaction, the same shape as the ingest promotions.
    for projection in _PROJECTIONS:
        _rewrite(connection, projection, {**parameters, "derivation_id": context.derivation_id})
    install_tile_functions(connection)

    return MartRefresh(
        derivation_id=context.derivation_id,
        row_counts={table: rows for table, (rows, _) in measured.items()},
        layers=tuple(layer.name for layer in TILE_LAYERS),
    )


def _compute_epsg(connection: psycopg.Connection) -> int:
    for rule in load_rules(connection, source_id=COMPUTE_CRS_SOURCE):
        if rule.rule_id == COMPUTE_CRS_RULE:
            return int(rule.spec["compute_epsg"])
    raise LookupError(f"{COMPUTE_CRS_RULE} is not seeded, so the compute CRS is not knowable")


def _measure(
    connection: psycopg.Connection, projection: _Projection, parameters: Mapping[str, object]
) -> tuple[int, str]:
    """Row count and content digest of what the refresh is about to write."""
    with connection.cursor() as cursor:
        cursor.execute(
            "select count(*), coalesce(md5(string_agg(digest, ',' order by digest)), '')"
            f"  from (select md5(p::text) as digest from ({projection.select}) p) fingerprint",
            parameters,
        )
        rows, digest = cursor.fetchone()
    return rows, digest


def _canonical_inputs(connection: psycopg.Connection) -> list[InputRef]:
    with connection.cursor() as cursor:
        cursor.execute(_INPUT_DERIVATIONS)
        return [
            InputRef(kind="derivation", ref_id=derivation_id, as_of_vintage=vintage)
            for derivation_id, vintage in cursor.fetchall()
        ]


def _rewrite(
    connection: psycopg.Connection, projection: _Projection, parameters: Mapping[str, object]
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(f"delete from marts.{projection.table}")
        cursor.execute(
            f"insert into marts.{projection.table} ({', '.join(projection.columns)},"
            f" derivation_id) select p.*, %(derivation_id)s from ({projection.select}) p",
            parameters,
        )


def _ensure_environment(connection: psycopg.Connection, env_id: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.environments (env_id, python_version, threads)"
            " values (%s, %s, 1) on conflict (env_id) do nothing",
            (env_id, platform.python_version()),
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the ND tile marts from canonical.")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--as-of", default=None, help="knowledge-time cut, YYYY-MM-DD")
    parser.add_argument("--env-id", default="env_cli")
    parser.add_argument("--code-version", default="glasswell:cli")
    arguments = parser.parse_args(argv)
    as_of = date.fromisoformat(arguments.as_of) if arguments.as_of else None

    with psycopg.connect(arguments.dsn) as connection:
        _ensure_environment(connection, arguments.env_id)
        environment = DeriveEnvironment(
            code_version=arguments.code_version, code_dirty=False, env_id=arguments.env_id
        )
        with lineage_session(recorder=PostgresRecorder(connection), environment=environment):
            report = refresh_all(connection, as_of=as_of)
        connection.commit()
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
