"""The New Mexico tile mart: a point layer, rebuilt inside one `mart.refresh`.

The same shape as the ND and TX marts — reads canonical only, rebuilds rather than appends, one
content-addressed derivation per refresh. There is no `nm_laterals` projection because there is
no New Mexico lateral: `cr_nm_wellhistory_geometry_scope_1` records that neither in-scope source
ships one, and a layer the map could draw would imply a producing footprint nobody filed.

`status_canonical` is null for every New Mexico well and is carried anyway, beside the reported
letter. `cr_nm_wellhistory_status_vocab_1` is why: the OCD publishes no codebook for its status
letters, so the map shows the well unstyled rather than inventing a class for it.
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
from glasswell.marts.tiles import NM_LAYERS, install_tile_functions

STATE_CODE = "30"
DATUM_RULE = "cr_nm_wellhistory_datum_1"
PROVENANCE_RULE = "cr_nm_wellhistory_geometry_provenance_1"
SCOPE_RULE = "cr_nm_wellhistory_geometry_scope_1"
STATUS_RULE = "cr_nm_wellhistory_status_vocab_1"
TILE_TABLE = "nm_wells_tile"

_WELLS_AS_OF = """
with wells_as_of as (
    select distinct on (api10) api10, operator_name_reported, status_canonical, status_reported,
           well_type_reported, county_code_at_permit, spud_date
      from canonical.wells
     where state_code = %(state_code)s
       and (%(as_of)s::date is null or effective_from <= %(as_of)s::date)
     order by api10, effective_from desc, created_at desc)
"""

# Left join, and the state filter is on the geometry: a New Mexico geometry whose api10 carries
# no well row still tiles, unstyled, rather than disappearing between canonical and the map —
# while an ND or TX geometry is not in this mart at all.
_WELLS_SELECT = (
    _WELLS_AS_OF
    + """
select s.api10,
       w.operator_name_reported as operator_name,
       w.status_canonical,
       w.status_reported,
       w.well_type_reported,
       w.county_code_at_permit as county_code,
       extract(year from w.spud_date)::int as spud_year,
       s.geom
  from canonical.well_spatial s
  left join wells_as_of w on w.api10 = s.api10
 where s.geom_type = 'surface' and left(s.api10, 2) = %(state_code)s
"""
)

_COLUMNS: tuple[str, ...] = (
    "api10",
    "operator_name",
    "status_canonical",
    "status_reported",
    "well_type_reported",
    "county_code",
    "spud_year",
    "geom",
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
    """Rebuild the NM tile mart from canonical under one content-addressed derivation."""
    parameters: dict[str, object] = {"as_of": as_of, "state_code": STATE_CODE}
    rows, digest = _measure(connection, parameters)

    with derive(
        "mart.refresh",
        output=OutputSpec(
            store="postgis",
            dataset="marts.nm_tiles",
            partition={"state": "NM"},
            schema_version="1",
        ),
        params={
            "as_of": as_of.isoformat() if as_of else None,
            "state_code": STATE_CODE,
            "geometry_scope": "surface_only",
            "layers": [layer.name for layer in NM_LAYERS],
        },
        inputs=_canonical_inputs(connection),
        rules=[DATUM_RULE, PROVENANCE_RULE, SCOPE_RULE, STATUS_RULE],
    ) as context:
        context.set_rows(rows)
        context.set_output_hash(hash_payload({TILE_TABLE: digest}))

    _rewrite(connection, {**parameters, "derivation_id": context.derivation_id})
    install_tile_functions(connection)

    session = current_session()
    emit(
        connection,
        "mart.refreshed",
        subject_type="derivation",
        subject_id=context.derivation_id,
        payload={"row_counts": {TILE_TABLE: rows}, "state": "NM", "geometry_scope": "surface_only"},
        correlation_id=session.correlation_id,
        occurred_at=session.clock.now(),
    )
    return MartRefresh(
        derivation_id=context.derivation_id,
        row_counts={TILE_TABLE: rows},
        layers=tuple(layer.name for layer in NM_LAYERS),
    )


def _measure(
    connection: psycopg.Connection, parameters: Mapping[str, object]
) -> tuple[int, str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select count(*), coalesce(md5(string_agg(digest, ',' order by digest)), '')"
            f"  from (select md5(p::text) as digest from ({_WELLS_SELECT}) p) fingerprint",
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


def _rewrite(connection: psycopg.Connection, parameters: Mapping[str, object]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(f"delete from marts.{TILE_TABLE}")
        cursor.execute(
            f"insert into marts.{TILE_TABLE} ({', '.join(_COLUMNS)}, derivation_id)"
            f" select p.*, %(derivation_id)s from ({_WELLS_SELECT}) p",
            parameters,
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the NM tile mart from canonical.")
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
