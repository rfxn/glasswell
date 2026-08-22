"""The ND tile marts: narrow projections of canonical, rebuilt inside one `mart.refresh`.

Marts read canonical only (blueprint §3.0.1) and are rebuilt rather than appended, so every
refresh is `delete` + `insert … select` in the caller's transaction.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date

import psycopg

from glasswell.ingest.base import resolve_environment
from glasswell.lengths import LengthMethod, resolve_length_method
from glasswell.lineage.audit import emit
from glasswell.lineage.capture import current_session, derive, lineage_session
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.serialization import hash_payload
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.tiles import ND_LAYERS, install_tile_functions
from glasswell.units import METRES_PER_FOOT

DATUM_RULE = "cr_nd_datum_1"

STATE_CODE = "33"

_WELLS_AS_OF = """
with wells_as_of as (
    select distinct on (api10) api10, operator_name_reported, status_canonical, spud_date
      from canonical.wells
     where state_code = %(state_code)s
       and (%(as_of)s::date is null or effective_from <= %(as_of)s::date)
     order by api10, effective_from desc, created_at desc)
"""

# Left join and a state predicate on the *geometry*: a lateral whose api10 has no well row
# still tiles, unstyled, rather than disappearing between canonical and the map — but a well
# from another state is not this mart's, and canonical.well_spatial holds every state.
#
# Without the predicate this select was `where geom_type = 'lateral'` and nothing else, so the
# first ND refresh after another jurisdiction landed would have swept its rows in: 355,550 TX
# wells into nd_wells_tile and 69,920 arcs into nd_laterals_tile, drawn a second time under
# ND's own layer and its "43,817 points" subtitle. Latent, and it would have surfaced on a
# night when nobody deployed anything.
_LATERALS_SELECT = (
    _WELLS_AS_OF
    + """
select s.api10,
       s.geom_key as linekey,
       w.operator_name_reported as operator_name,
       w.status_canonical,
       extract(year from w.spud_date)::int as spud_year,
       {length_metres}::numeric / %(metres_per_foot)s as lateral_length_ft_exact,
       round({length_metres}::numeric / %(metres_per_foot)s, 2)::float8 as lateral_length_ft,
       s.geom
  from canonical.well_spatial s
  left join wells_as_of w on w.api10 = s.api10
 where s.geom_type = 'lateral' and left(s.api10, 2) = %(state_code)s
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
 where s.geom_type = 'surface' and left(s.api10, 2) = %(state_code)s
"""
)

# An inner join on the stations, not a left one: a trace is written in the same transaction as
# the stations it was assembled from, so a trace with no station row is a broken promotion and
# must fail visibly here rather than tile as a line with no station count under it.
#
# No length column, on purpose. The trace is the plan view of a three-dimensional path, so
# ST_Length over it measures horizontal travel and would read as hole length. The deepest
# station's measured depth is what the source filed, so that is what is published.
_SURVEY_TRACES_SELECT = (
    _WELLS_AS_OF
    + """
select s.api10,
       s.geom_key as trace_key,
       w.operator_name_reported as operator_name,
       w.status_canonical,
       extract(year from w.spud_date)::int as spud_year,
       station.wellbore_segment,
       station.segment_kind,
       station.station_count,
       station.deepest_station_md_ft,
       station.deepest_station_tvd_ft,
       s.geom_type as geometry_provenance,
       s.geom
  from canonical.well_spatial s
  left join wells_as_of w on w.api10 = s.api10
  join (select api10, api14, wellbore_segment, segment_kind,
               count(*)::int as station_count,
               max(measured_depth_ft) as deepest_station_md_ft,
               max(true_vertical_depth_ft) as deepest_station_tvd_ft
          from canonical.well_survey_stations
         group by api10, api14, wellbore_segment, segment_kind) station
    on station.api10 = s.api10
   and s.geom_key = station.api14 || '_' || station.wellbore_segment
 where s.geom_type = 'survey_trace' and left(s.api10, 2) = %(state_code)s
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
 where derivation_id in (
    select derivation_id from canonical.well_spatial where left(api10, 2) = %(state_code)s
     union
    select derivation_id from canonical.wells where state_code = %(state_code)s)
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
            "lateral_length_ft_exact",
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
    _Projection(
        table="nd_survey_traces_tile",
        columns=(
            "api10",
            "trace_key",
            "operator_name",
            "status_canonical",
            "spud_year",
            "wellbore_segment",
            "segment_kind",
            "station_count",
            "deepest_station_md_ft",
            "deepest_station_tvd_ft",
            "geometry_provenance",
            "geom",
        ),
        select=_SURVEY_TRACES_SELECT,
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
    method = resolve_length_method(connection)
    projections = _projections(method)
    parameters: dict[str, object] = {
        "as_of": as_of,
        "metres_per_foot": METRES_PER_FOOT,
        "state_code": STATE_CODE,
    }
    with connection.cursor() as cursor:
        cursor.execute(_SPACING_UNITS_VIEW)
    measured = {p.table: _measure(connection, p, parameters) for p in projections}

    with derive(
        "mart.refresh",
        output=OutputSpec(
            store="postgis", dataset="marts.nd_tiles", partition={"state": "ND"}, schema_version="1"
        ),
        params={
            "as_of": as_of.isoformat() if as_of else None,
            "length_method": method.method,
            "compute_epsg": method.compute_epsg,
            "state_code": STATE_CODE,
            "layers": [layer.name for layer in ND_LAYERS],
        },
        inputs=_canonical_inputs(connection),
        rules=[method.rule_id, DATUM_RULE],
    ) as context:
        context.set_rows(sum(rows for rows, _ in measured.values()))
        context.set_output_hash(hash_payload({table: d for table, (_, d) in measured.items()}))

    # The id is content-addressed and only exists once the block closes, so the rows carrying it
    # are written after it — one transaction, the same shape as the ingest promotions.
    for projection in projections:
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
            "length_method": method.method,
            "length_rule_id": method.rule_id,
        },
        correlation_id=session.correlation_id,
        occurred_at=session.clock.now(),
    )
    return MartRefresh(
        derivation_id=context.derivation_id,
        row_counts={table: rows for table, (rows, _) in measured.items()},
        layers=tuple(layer.name for layer in ND_LAYERS),
    )


def _projections(method: LengthMethod) -> tuple[_Projection, ...]:
    """The length expression is the active rule's, resolved once per refresh."""
    metres = method.metres_sql("s.geom")
    return tuple(
        replace(projection, select=projection.select.format(length_metres=metres))
        if "{length_metres}" in projection.select
        else projection
        for projection in _PROJECTIONS
    )


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
    parser = argparse.ArgumentParser(description="Refresh the ND tile marts from canonical.")
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
