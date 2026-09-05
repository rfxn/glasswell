"""One tile-mart engine, driven by a registration and a profile row.

Marts read canonical only (blueprint §3.0.1) and are rebuilt rather than appended, so every
refresh is `delete` + `insert … select` in the caller's transaction. What differs between
jurisdictions is not the lifecycle -- that half was byte-identical in four modules -- but the
head: three distinct params key sets, four distinct rule lists, and per-regulator selects. All
of it is inside the content address, so every one of those differences is carried verbatim by
`MartProfile` rather than unified, and `scripts/mart-address-diff.sh` is what holds them to it.

The registry decides behaviour, the profile decides citation, and the two never mix. Which
basin governs a compute CRS, which source measures a lateral and whether a lateral is served at
all are `lineage.jurisdiction_rules` decisions read here for behaviour; the rules a refresh
*cites* are the profile's list plus the compute-CRS rule that actually shaped the figure.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date

import psycopg

from glasswell.absence import BLANK_IS_ABSENT_RULE_ID, absent_if_blank
from glasswell.db.dsn import add_dsn_argument, resolve_dsn
from glasswell.ingest.base import resolve_environment
from glasswell.lengths import LengthMethod, resolve_length_method
from glasswell.lineage.audit import emit
from glasswell.lineage.capture import current_session, derive, lineage_session
from glasswell.lineage.errors import LineageError
from glasswell.lineage.jurisdictions import Jurisdiction, load_jurisdictions
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.serialization import hash_payload
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.tiles import (
    CO_LAYERS,
    MT_LAYERS,
    ND_LAYERS,
    NM_LAYERS,
    TX_LAYERS,
    TileLayer,
    install_tile_functions,
)
from glasswell.status_resolution import resolved_status, resolver_join
from glasswell.units import METRES_PER_FOOT

# The registry decisions this engine reads. `length_scope` present means the figure is withheld
# and that rule is cited in its place; `length_source` names which source's compute-CRS rule
# measures it, directly or through the basin `basin_scope` registers.
LENGTH_SCOPE = "length_scope"
LENGTH_SOURCE = "length_source"

# The one value the geometry_class column ever takes. Spelled once so the mart, the tile
# property and the test that holds them equal cannot drift into two vocabularies.
MAP_STICK = "map_stick"

_LENGTH_PLACEHOLDER = "{length_metres}"


class MartProfileError(LineageError):
    """A profile and the registration it is refreshed under disagree about serving a length."""


@dataclass(frozen=True, slots=True)
class _Projection:
    table: str
    columns: tuple[str, ...]
    select: str


@dataclass(frozen=True, slots=True)
class MartProfile:
    """Everything a jurisdiction's tile refresh does not share with its neighbours."""

    jurisdiction_code: str
    dataset: str
    layers: tuple[TileLayer, ...]
    projections: tuple[_Projection, ...]
    cte_columns: tuple[str, ...]
    params_extra: tuple[tuple[str, object], ...]
    rule_ids: tuple[str, ...]
    emit_extra: tuple[tuple[str, object], ...]

    @property
    def serves_a_length(self) -> bool:
        return any(_LENGTH_PLACEHOLDER in p.select for p in self.projections)


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


# `state_code` is on the geometry, not only on the header: a geometry whose api10 carries no
# well row still tiles, unstyled, rather than disappearing between canonical and the map, while
# another jurisdiction's geometry is not in this mart at all. Without the predicate the first
# refresh after a second jurisdiction landed would have swept its rows in under this one's
# layer and its own subtitle -- latent, and it would have surfaced on a night nobody deployed.
_WELLS_AS_OF = """
with wells_as_of as (
    select distinct on (api10) api10, {cte_columns}
      from canonical.wells
     where state_code = %(state_code)s
       and (%(as_of)s::date is null or effective_from <= %(as_of)s::date)
     order by api10, effective_from desc, created_at desc)
"""

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

_RULE_SPEC = "select spec from lineage.conformance_rules where rule_id = %(rule_id)s"

_ND_LATERALS = """
select s.api10,
       s.geom_key as linekey,
       w.operator_name_reported as operator_name,
       w.status_canonical,
       extract(year from w.spud_date)::int as spud_year,
       {length_metres}::numeric / %(metres_per_foot)s as lateral_length_ft_exact,
       round({length_metres}::numeric / %(metres_per_foot)s, 2)::float8 as lateral_length_ft,
       s.geom_type as geometry_provenance,
       s.geom
  from canonical.well_spatial s
  left join wells_as_of w on w.api10 = s.api10
 where s.geom_type = 'lateral' and left(s.api10, 2) = %(state_code)s
"""

_ND_WELLS = """
select s.api10,
       w.operator_name_reported as operator_name,
       w.status_canonical,
       extract(year from w.spud_date)::int as spud_year,
       w.well_type_reported,
       s.geom_type as geometry_provenance,
       s.geom
  from canonical.well_spatial s
  left join wells_as_of w on w.api10 = s.api10
 where s.geom_type = 'surface' and left(s.api10, 2) = %(state_code)s
"""

# An inner join on the stations, not a left one: a trace is written in the same transaction as
# the stations it was assembled from, so a trace with no station row is a broken promotion and
# must fail visibly here rather than tile as a line with no station count under it.
#
# No length column, on purpose. The trace is the plan view of a three-dimensional path, so
# ST_Length over it measures horizontal travel and would read as hole length. The deepest
# station's measured depth is what the source filed, so that is what is published.
_ND_SURVEY_TRACES = """
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

_TX_LATERALS = """
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

_TX_WELLS = """
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

# New Mexico resolves status_canonical at read time: canonical.wells carries null on every New
# Mexico row and the serving path reads the same view, so the tile and the well card cannot
# disagree (cr_nm_wellhistory_status_vocab_2).
_NM_WELLS = f"""
select s.api10,
       w.operator_name_reported as operator_name,
       {resolved_status("w")} as status_canonical,
       w.status_reported,
       w.well_type_reported,
       w.county_code_at_permit as county_code,
       extract(year from w.spud_date)::int as spud_year,
       s.geom
  from canonical.well_spatial s
  left join wells_as_of w on w.api10 = s.api10
 {resolver_join("w")}
 where s.geom_type = 'surface' and left(s.api10, 2) = %(state_code)s
"""

# The four source-reported text columns are read under cr_co_wells_shp_blank_is_absent_1: the
# 1,172 headers promoted with an empty Well_Class cannot be restated, and the tile has to agree
# with the well card and the legend about the same well.
_CO_WELLS = f"""
select s.api10,
       {absent_if_blank("w.operator_name_reported")} as operator_name,
       {resolved_status("w")} as status_canonical,
       {absent_if_blank("w.status_reported")} as status_reported,
       {absent_if_blank("w.well_type_reported")} as well_type_reported,
       {absent_if_blank("w.county_code_at_permit")} as county_code,
       extract(year from w.spud_date)::int as spud_year,
       s.location_qualifier as loc_qual_class,
       s.geom_type as geometry_provenance,
       s.geom
  from canonical.well_spatial s
  left join wells_as_of w on w.api10 = s.api10
 {resolver_join("w")}
 where s.geom_type = 'surface' and left(s.api10, 2) = %(state_code)s
"""

_MT_WELLS = """
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

# geometry_class on every feature, because cr_mt_paths_geometry_class_1 requires the map-stick
# distinction to be stated wherever the geometry is served and a column is the only form of that
# statement a tile client cannot fail to receive.
_MT_PATHS = """
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


MART_PROFILES: tuple[MartProfile, ...] = (
    MartProfile(
        jurisdiction_code="ND",
        dataset="marts.nd_tiles",
        layers=ND_LAYERS,
        projections=(
            _Projection(
                table="nd_laterals_tile",
                columns=(
                    "api10", "linekey", "operator_name", "status_canonical", "spud_year",
                    "lateral_length_ft_exact", "lateral_length_ft", "geometry_provenance",
                    "geom",
                ),
                select=_ND_LATERALS,
            ),
            _Projection(
                table="nd_wells_tile",
                columns=(
                    "api10", "operator_name", "status_canonical", "spud_year",
                    "well_type_reported", "geometry_provenance", "geom",
                ),
                select=_ND_WELLS,
            ),
            _Projection(
                table="nd_survey_traces_tile",
                columns=(
                    "api10", "trace_key", "operator_name", "status_canonical", "spud_year",
                    "wellbore_segment", "segment_kind", "station_count",
                    "deepest_station_md_ft", "deepest_station_tvd_ft", "geometry_provenance",
                    "geom",
                ),
                select=_ND_SURVEY_TRACES,
            ),
        ),
        cte_columns=(
            "operator_name_reported", "status_canonical", "spud_date", "well_type_reported",
        ),
        params_extra=(),
        # M1-3: geom_type is served verbatim as geometry_provenance on every ND layer (R8).
        rule_ids=("cr_nd_datum_1", "cr_nd_geometry_provenance_1"),
        emit_extra=(),
    ),
    MartProfile(
        jurisdiction_code="TX",
        dataset="marts.tx_tiles",
        layers=TX_LAYERS,
        projections=(
            _Projection(
                table="tx_laterals_tile",
                columns=(
                    "api10", "geom_key", "operator_name", "status_canonical", "county_code",
                    "lateral_length_ft_exact", "lateral_length_ft", "geom",
                ),
                select=_TX_LATERALS,
            ),
            _Projection(
                table="tx_wells_tile",
                columns=(
                    "api10", "operator_name", "status_canonical", "well_type_reported",
                    "county_code", "geom",
                ),
                select=_TX_WELLS,
            ),
        ),
        cte_columns=(
            "operator_name_reported", "status_canonical", "well_type_reported",
            "county_code_at_permit",
        ),
        params_extra=(),
        rule_ids=("cr_tx_nad27_1",),
        emit_extra=(("state", "TX"),),
    ),
    MartProfile(
        jurisdiction_code="NM",
        dataset="marts.nm_tiles",
        layers=NM_LAYERS,
        projections=(
            _Projection(
                table="nm_wells_tile",
                columns=(
                    "api10", "operator_name", "status_canonical", "status_reported",
                    "well_type_reported", "county_code", "spud_year", "geom",
                ),
                select=_NM_WELLS,
            ),
        ),
        # state_code is in the spine select because resolver_join joins on it: every read-time
        # jurisdiction needs the column, and Colorado is the second.
        cte_columns=(
            "state_code", "operator_name_reported", "status_canonical", "status_reported",
            "well_type_reported", "county_code_at_permit", "spud_date",
        ),
        params_extra=(("geometry_scope", "surface_only"),),
        rule_ids=(
            "cr_nm_wellhistory_datum_1",
            "cr_nm_wellhistory_geometry_provenance_1",
            "cr_nm_wellhistory_geometry_scope_1",
            "cr_nm_wellhistory_status_vocab_2",
        ),
        emit_extra=(("state", "NM"), ("geometry_scope", "surface_only")),
    ),
    MartProfile(
        jurisdiction_code="CO",
        dataset="marts.co_tiles",
        layers=CO_LAYERS,
        projections=(
            _Projection(
                table="co_wells_tile",
                columns=(
                    "api10", "operator_name", "status_canonical", "status_reported",
                    "well_type_reported", "county_code", "spud_year", "loc_qual_class",
                    "geometry_provenance", "geom",
                ),
                select=_CO_WELLS,
            ),
        ),
        # state_code for the same reason New Mexico carries it: resolver_join joins on it, and
        # Colorado is the second jurisdiction whose status class is resolved at read time.
        cte_columns=(
            "state_code", "operator_name_reported", "status_canonical", "status_reported",
            "well_type_reported", "county_code_at_permit", "spud_date",
        ),
        params_extra=(("geometry_scope", "surface_only"),),
        rule_ids=(
            "cr_co_wells_datum_1",
            "cr_co_wells_geometry_provenance_1",
            "cr_co_wells_geometry_scope_1",
            "cr_co_wells_location_qualifier_1",
            "cr_co_wells_source_selection_1",
            "cr_co_wells_status_vocab_1",
            BLANK_IS_ABSENT_RULE_ID,
        ),
        emit_extra=(("state", "CO"), ("geometry_scope", "surface_only")),
    ),
    MartProfile(
        jurisdiction_code="MT",
        dataset="marts.mt_tiles",
        layers=MT_LAYERS,
        projections=(
            _Projection(
                table="mt_wells_tile",
                columns=(
                    "api10", "operator_name", "status_canonical", "status_reported",
                    "well_type_reported", "completion_year", "geom",
                ),
                select=_MT_WELLS,
            ),
            _Projection(
                table="mt_paths_tile",
                columns=(
                    "api10", "geom_key", "operator_name", "status_canonical", "geometry_class",
                    "vertex_count", "geom",
                ),
                select=_MT_PATHS,
            ),
        ),
        cte_columns=(
            "operator_name_reported", "status_canonical", "status_reported",
            "well_type_reported", "completion_date",
        ),
        # `basin: None` beside a jurisdiction that has one and carries no such key is an
        # asymmetry preserved verbatim, because the derivation address depends on it.
        params_extra=(("basin", None), ("geometry_class", MAP_STICK), ("length_served", False)),
        rule_ids=(
            "cr_mt_basin_scope_1",
            "cr_mt_gis_datum_1",
            "cr_mt_paths_datum_1",
            "cr_mt_paths_geometry_class_1",
            "cr_mt_paths_coverage_1",
            "cr_mt_paths_subkey_1",
            "cr_mt_gis_status_vocab_1",
        ),
        emit_extra=(("state", "MT"), ("basin", None), ("geometry_class", MAP_STICK)),
    ),
)

PROFILE_BY_CODE: Mapping[str, MartProfile] = {p.jurisdiction_code: p for p in MART_PROFILES}


def profile_for(jurisdiction_code: str) -> MartProfile:
    profile = PROFILE_BY_CODE.get(jurisdiction_code)
    if profile is None:
        registered = ", ".join(sorted(PROFILE_BY_CODE))
        raise MartProfileError(
            f"{jurisdiction_code} has no tile-mart profile; registered: {registered}"
        )
    return profile


def length_binding_error(profile: MartProfile, length_scope_rule: str | None) -> str | None:
    """The binding a `{length_metres}` placeholder creates, refused rather than discovered.

    Registering a withholding rule for a jurisdiction whose profile publishes a length would
    otherwise leave the placeholder unfilled and raise a KeyError inside the refresh; the
    contrapositive is the same statement, so one check covers both directions.
    """
    if profile.serves_a_length and length_scope_rule is not None:
        return (
            f"{profile.jurisdiction_code} registers {length_scope_rule} for {LENGTH_SCOPE},"
            " which withholds the figure, but its profile publishes a length column"
        )
    return None


def _rule_spec(connection: psycopg.Connection, rule_id: str) -> Mapping[str, object]:
    with connection.cursor() as cursor:
        cursor.execute(_RULE_SPEC, {"rule_id": rule_id})
        row = cursor.fetchone()
    if row is None:
        raise MartProfileError(f"{rule_id} is registered but not seeded")
    return row[0]


def _length_method(
    connection: psycopg.Connection, profile: MartProfile, registration: Jurisdiction
) -> LengthMethod | None:
    """The method the jurisdiction's own decisions resolve to, or None where none is served."""
    withheld = registration.rule(LENGTH_SCOPE)
    problem = length_binding_error(profile, withheld)
    if problem is not None:
        raise MartProfileError(problem)
    if withheld is not None or not profile.serves_a_length:
        return None
    source_rule = registration.rule(LENGTH_SOURCE)
    if source_rule is None:
        raise MartProfileError(
            f"{profile.jurisdiction_code} publishes a length column and registers no"
            f" {LENGTH_SOURCE} rule, so the figure would carry no rule of its own to cite"
        )
    spec = _rule_spec(connection, source_rule)
    return resolve_length_method(
        connection,
        source_id=spec.get("source_id"),
        basin=spec.get("basin"),
    )


def _projections(profile: MartProfile, method: LengthMethod | None) -> tuple[_Projection, ...]:
    """The spine CTE prepended, and the length expression filled from the active rule."""
    cte = _WELLS_AS_OF.format(cte_columns=", ".join(profile.cte_columns))
    metres = method.metres_sql("s.geom") if method is not None else None
    return tuple(
        replace(
            projection,
            select=cte
            + (
                projection.select.format(length_metres=metres)
                if _LENGTH_PLACEHOLDER in projection.select
                else projection.select
            ),
        )
        for projection in profile.projections
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


def _canonical_inputs(connection: psycopg.Connection, state_code: str) -> list[InputRef]:
    with connection.cursor() as cursor:
        cursor.execute(_INPUT_DERIVATIONS, {"state_code": state_code})
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


def refresh_for(
    connection: psycopg.Connection, jurisdiction_code: str, *, as_of: date | None = None
) -> MartRefresh:
    """Rebuild one jurisdiction's tile marts from canonical under one content-addressed id."""
    profile = profile_for(jurisdiction_code)
    registration = load_jurisdictions(connection).by_code.get(jurisdiction_code)
    if registration is None:
        raise MartProfileError(f"{jurisdiction_code} resolves to no registration")
    state_code = str(registration.identity_prefix)

    method = _length_method(connection, profile, registration)
    projections = _projections(profile, method)
    parameters: dict[str, object] = {
        "as_of": as_of,
        "state_code": state_code,
        "metres_per_foot": METRES_PER_FOOT,
        **dict(profile.params_extra),
    }
    measured = {p.table: _measure(connection, p, parameters) for p in projections}

    method_params: dict[str, object] = (
        {"length_method": method.method, "compute_epsg": method.compute_epsg}
        if method is not None
        else {}
    )
    with derive(
        "mart.refresh",
        output=OutputSpec(
            store="postgis",
            dataset=profile.dataset,
            partition={"state": profile.jurisdiction_code},
            schema_version="1",
        ),
        params={
            "as_of": as_of.isoformat() if as_of else None,
            **method_params,
            "state_code": state_code,
            **dict(profile.params_extra),
            "layers": [layer.name for layer in profile.layers],
        },
        inputs=_canonical_inputs(connection, state_code),
        rules=[*([method.rule_id] if method is not None else []), *profile.rule_ids],
    ) as context:
        context.set_rows(sum(rows for rows, _ in measured.values()))
        context.set_output_hash(hash_payload({table: d for table, (_, d) in measured.items()}))

    # The id is content-addressed and only exists once the block closes, so the rows carrying it
    # are written after it -- one transaction, the same shape as the ingest promotions.
    for projection in projections:
        _rewrite(connection, projection, {**parameters, "derivation_id": context.derivation_id})
    install_tile_functions(connection)

    row_counts = {table: rows for table, (rows, _) in measured.items()}
    method_payload: dict[str, object] = (
        {"length_method": method.method, "length_rule_id": method.rule_id}
        if method is not None
        else {}
    )
    session = current_session()
    emit(
        connection,
        "mart.refreshed",
        subject_type="derivation",
        subject_id=context.derivation_id,
        payload={"row_counts": row_counts, **method_payload, **dict(profile.emit_extra)},
        correlation_id=session.correlation_id,
        occurred_at=session.clock.now(),
    )
    return MartRefresh(
        derivation_id=context.derivation_id,
        row_counts=row_counts,
        layers=tuple(layer.name for layer in profile.layers),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh one jurisdiction's tile marts.")
    add_dsn_argument(parser)
    parser.add_argument("--jurisdiction", required=True, help="registered code, e.g. ND")
    parser.add_argument("--as-of", default=None, help="knowledge-time cut, YYYY-MM-DD")
    parser.add_argument("--env-id", default=None, help="override the fingerprinted env id")
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)
    arguments.dsn = resolve_dsn(arguments.dsn)
    as_of = date.fromisoformat(arguments.as_of) if arguments.as_of else None

    with psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        with lineage_session(recorder=PostgresRecorder(connection), environment=environment):
            report = refresh_for(connection, arguments.jurisdiction, as_of=as_of)
        connection.commit()
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
