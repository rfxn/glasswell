"""The Montana tile marts: a point layer and a path layer, rebuilt inside one `mart.refresh`.

The same shape as the ND, TX and NM marts — reads canonical only, rebuilds rather than appends,
one content-addressed derivation per refresh.

Two Montana decisions shape what is projected, and both are registry rows rather than choices
made here. `basin` is absent because cr_mt_basin_scope_1 leaves every Montana well untagged —
Bakken is the fifth formation in the state at 4.6% — and a `williston` label would put a Madison
well into the type-curve peer ladder. No path length is served because
`lengths.resolve_length_method` is keyed by basin, so an untagged state has no registered
method, and a length carrying another basin's compute CRS is a naked number wearing a borrowed
rule. The paths carry `geometry_class` and `vertex_count` instead: cr_mt_paths_geometry_class_1
requires the map-stick distinction to be stated wherever the geometry is served, and a column on
every feature is the only form of that statement a tile client cannot fail to receive.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import psycopg

from glasswell.ingest.base import resolve_environment
from glasswell.lineage.audit import emit
from glasswell.lineage.capture import current_session, derive, lineage_session
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.serialization import hash_payload
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.tiles import MT_LAYERS, install_tile_functions

STATE_CODE = "25"
BASIN_RULE = "cr_mt_basin_scope_1"
DATUM_RULE = "cr_mt_gis_datum_1"
PATHS_DATUM_RULE = "cr_mt_paths_datum_1"
GEOMETRY_CLASS_RULE = "cr_mt_paths_geometry_class_1"
PATH_COVERAGE_RULE = "cr_mt_paths_coverage_1"
PATH_SUBKEY_RULE = "cr_mt_paths_subkey_1"
STATUS_RULE = "cr_mt_gis_status_vocab_1"

# The one value the geometry_class column ever takes. Spelled once, here, so the mart, the
# tile property and the test that holds them equal cannot drift into two vocabularies.
MAP_STICK = "map_stick"

_WELLS_AS_OF = """
with wells_as_of as (
    select distinct on (api10) api10, operator_name_reported, status_canonical, status_reported,
           well_type_reported, completion_date
      from canonical.wells
     where state_code = %(state_code)s
       and (%(as_of)s::date is null or effective_from <= %(as_of)s::date)
     order by api10, effective_from desc, created_at desc)
"""

# Left join, and the state filter is on the geometry: a Montana geometry whose api10 carries no
# well row still tiles, unstyled, rather than disappearing between canonical and the map. That
# is the normal case here rather than an edge — the six unpromoted MBOGC statuses quarantine
# under cr_mt_gis_status_vocab_1, so 1,400 surface points have a location and no header.
_WELLS_SELECT = (
    _WELLS_AS_OF
    + """
select s.api10,
       w.operator_name_reported as operator_name,
       w.status_canonical,
       w.status_reported,
       w.well_type_reported,
       extract(year from w.completion_date)::int as completion_year,
       s.geom
  from canonical.well_spatial s
  left join wells_as_of w on w.api10 = s.api10
 where s.geom_type = 'surface' and left(s.api10, 2) = %(state_code)s
"""
)

_PATHS_SELECT = (
    _WELLS_AS_OF
    + """
select s.api10,
       s.geom_key,
       w.operator_name_reported as operator_name,
       w.status_canonical,
       %(geometry_class)s as geometry_class,
       st_npoints(s.geom) as vertex_count,
       s.geom
  from canonical.well_spatial s
  left join wells_as_of w on w.api10 = s.api10
 where s.geom_type = 'lateral' and left(s.api10, 2) = %(state_code)s
"""
)

_INPUT_DERIVATIONS = """
select d.derivation_id, d.created_vintage
  from lineage.derivations d
 where d.derivation_id in (
    select derivation_id from canonical.well_spatial
     where left(api10, 2) = %(state_code)s
    union
    select derivation_id from canonical.wells where state_code = %(state_code)s)
 order by d.derivation_id
"""


@dataclass(frozen=True, slots=True)
class _Projection:
    table: str
    columns: tuple[str, ...]
    select: str


_PROJECTIONS: tuple[_Projection, ...] = (
    _Projection(
        table="mt_wells_tile",
        columns=(
            "api10", "operator_name", "status_canonical", "status_reported",
            "well_type_reported", "completion_year", "geom",
        ),
        select=_WELLS_SELECT,
    ),
    _Projection(
        table="mt_paths_tile",
        columns=(
            "api10", "geom_key", "operator_name", "status_canonical", "geometry_class",
            "vertex_count", "geom",
        ),
        select=_PATHS_SELECT,
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
    """Rebuild every MT tile mart from canonical under one content-addressed derivation."""
    parameters: dict[str, object] = {
        "as_of": as_of,
        "state_code": STATE_CODE,
        "geometry_class": MAP_STICK,
    }
    measured = {p.table: _measure(connection, p, parameters) for p in _PROJECTIONS}

    with derive(
        "mart.refresh",
        output=OutputSpec(
            store="postgis",
            dataset="marts.mt_tiles",
            partition={"state": "MT"},
            schema_version="1",
        ),
        params={
            "as_of": as_of.isoformat() if as_of else None,
            "state_code": STATE_CODE,
            "basin": None,
            "geometry_class": MAP_STICK,
            "length_served": False,
            "layers": [layer.name for layer in MT_LAYERS],
        },
        inputs=_canonical_inputs(connection),
        rules=[
            BASIN_RULE, DATUM_RULE, PATHS_DATUM_RULE, GEOMETRY_CLASS_RULE,
            PATH_COVERAGE_RULE, PATH_SUBKEY_RULE, STATUS_RULE,
        ],
    ) as context:
        context.set_rows(sum(rows for rows, _ in measured.values()))
        context.set_output_hash(hash_payload({table: d for table, (_, d) in measured.items()}))

    for projection in _PROJECTIONS:
        _rewrite(connection, projection, {**parameters, "derivation_id": context.derivation_id})
    install_tile_functions(connection)

    session = current_session()
    emit(
        connection,
        "mart.refreshed",
        subject_type="derivation",
        subject_id=context.derivation_id,
        payload={
            "row_counts": {table: rows for table, (rows, _) in measured.items()},
            "state": "MT",
            "basin": None,
            "geometry_class": MAP_STICK,
        },
        correlation_id=session.correlation_id,
        occurred_at=session.clock.now(),
    )
    return MartRefresh(
        derivation_id=context.derivation_id,
        row_counts={table: rows for table, (rows, _) in measured.items()},
        layers=tuple(layer.name for layer in MT_LAYERS),
    )


def _measure(
    connection: psycopg.Connection, projection: _Projection, parameters: Mapping[str, object]
) -> tuple[int, str]:
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
        cursor.execute(_INPUT_DERIVATIONS, {"state_code": STATE_CODE})
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the MT tile marts from canonical.")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--as-of", default=None, help="knowledge-time cut, YYYY-MM-DD")
    parser.add_argument("--env-id", default=None, help="override the fingerprinted env id")
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)
    as_of = date.fromisoformat(arguments.as_of) if arguments.as_of else None

    with psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        with lineage_session(recorder=PostgresRecorder(connection), environment=environment):
            report = refresh_all(connection, as_of=as_of)
        connection.commit()
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
