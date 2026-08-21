"""The TX tile marts: narrow projections of canonical, rebuilt inside one `mart.refresh`.

The same shape as the ND marts — read canonical only, rebuild rather than append, one
content-addressed derivation per refresh — with the TX length rule resolved from the basin
registry so a served TX length cites a TX rule.
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
from glasswell.marts.tiles import TX_LAYERS, install_tile_functions
from glasswell.units import METRES_PER_FOOT

BASIN = "permian"
STATE_CODE = "42"
DATUM_RULE = "cr_tx_nad27_1"

_WELLS_AS_OF = """
with wells_as_of as (
    select distinct on (api10) api10, operator_name_reported, status_canonical,
           well_type_reported, county_code_at_permit
      from canonical.wells
     where state_code = %(state_code)s
       and (%(as_of)s::date is null or effective_from <= %(as_of)s::date)
     order by api10, effective_from desc, created_at desc)
"""

# Left join, and the state filter is on the geometry: a TX geometry whose api10 carries no well
# row still tiles, unstyled, rather than disappearing between canonical and the map — while an
# ND geometry, which has no TX well row by construction, is not in this mart at all.
_LATERALS_SELECT = (
    _WELLS_AS_OF
    + """
select s.api10,
       s.geom_key,
       w.operator_name_reported as operator_name,
       w.status_canonical,
       w.county_code_at_permit as county_code,
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
       w.well_type_reported,
       w.county_code_at_permit as county_code,
       s.geom
  from canonical.well_spatial s
  left join wells_as_of w on w.api10 = s.api10
 where s.geom_type = 'surface' and left(s.api10, 2) = %(state_code)s
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
        table="tx_laterals_tile",
        columns=(
            "api10", "geom_key", "operator_name", "status_canonical", "county_code",
            "lateral_length_ft_exact", "lateral_length_ft", "geom",
        ),
        select=_LATERALS_SELECT,
    ),
    _Projection(
        table="tx_wells_tile",
        columns=(
            "api10", "operator_name", "status_canonical", "well_type_reported", "county_code",
            "geom",
        ),
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
    """Rebuild every TX tile mart from canonical under one content-addressed derivation."""
    method = resolve_length_method(connection, basin=BASIN)
    projections = _projections(method)
    parameters: dict[str, object] = {
        "as_of": as_of,
        "metres_per_foot": METRES_PER_FOOT,
        "state_code": STATE_CODE,
    }
    measured = {p.table: _measure(connection, p, parameters) for p in projections}

    with derive(
        "mart.refresh",
        output=OutputSpec(
            store="postgis", dataset="marts.tx_tiles", partition={"state": "TX"}, schema_version="1"
        ),
        params={
            "as_of": as_of.isoformat() if as_of else None,
            "length_method": method.method,
            "compute_epsg": method.compute_epsg,
            "layers": [layer.name for layer in TX_LAYERS],
        },
        inputs=_canonical_inputs(connection),
        rules=[method.rule_id, DATUM_RULE],
    ) as context:
        context.set_rows(sum(rows for rows, _ in measured.values()))
        context.set_output_hash(hash_payload({table: d for table, (_, d) in measured.items()}))

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
            "state": "TX",
        },
        correlation_id=session.correlation_id,
        occurred_at=session.clock.now(),
    )
    return MartRefresh(
        derivation_id=context.derivation_id,
        row_counts={table: rows for table, (rows, _) in measured.items()},
        layers=tuple(layer.name for layer in TX_LAYERS),
    )


def _projections(method: LengthMethod) -> tuple[_Projection, ...]:
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
    parser = argparse.ArgumentParser(description="Refresh the TX tile marts from canonical.")
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
