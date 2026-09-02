"""Deterministic current-snapshot ND physical-neighbour mart.

Spatial work happens only here. The API reads the persisted scalar edge table through its
``(api10, distance_m, neighbor_api10)`` index and never transforms geometry at serve time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import psycopg
from psycopg.pq import TransactionStatus

from glasswell.db.dsn import add_dsn_argument, resolve_dsn
from glasswell.ingest.base import resolve_environment
from glasswell.lineage.audit import emit
from glasswell.lineage.capture import current_session, derive, lineage_session
from glasswell.lineage.jurisdictions import (
    NEIGHBORS_SCOPE,
    JurisdictionRegistry,
    load_jurisdictions,
)
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.serialization import canonical_json, hash_payload
from glasswell.lineage.store import PostgresRecorder
from glasswell.seed.jurisdictions import JURISDICTIONS
from glasswell.units import METRES_PER_FOOT

# North Dakota and Montana today. The mart is multi-state because the ND/MT line runs through
# the Williston: an ND well within 26,400 ft of the border has offsets on the Montana side, and
# a subject set scoped to one state truncates its neighbour list without saying so. Which
# jurisdictions the mart holds subjects for is the registry's `neighbors_available` column, not
# a tuple here — NM is absent because neither NM source ships a lateral, and that is a fact
# about the registration rather than about this module.
STATE_CODES: tuple[str, ...] = tuple(
    str(row["identity_prefix"]) for row in JURISDICTIONS if row["neighbors_available"]
)
# Whether the mart's *measured* domain reaches a registration is a second decision, and it was
# two pairs of float constants and a four-element tuple bound to nothing. A jurisdiction
# registered neighbours-available outside either bound was picked up as a subject, counted as
# an outlier, and aborted the whole monthly run with a message beginning "ND neighbour geometry
# falls outside" while reporting another state's well.
# Registration order, so the subject list this feeds -- a derivation param -- is byte-identical
# for the resident pair. Anything registered later sorts after it, by code.
_REGISTRATION_ORDER = tuple(str(row["identity_prefix"]) for row in JURISDICTIONS)
FORMATION_SOURCE_ID = "nd_mpr_xlsx"
COMPLETION_SOURCE_ID = "fracfocus_csv"
MIN_ALIAS_CONFIDENCE = Decimal("0.800")
MAX_RADIUS_FT = 26400
MAX_RADIUS_M = Decimal(MAX_RADIUS_FT) * METRES_PER_FOOT
CANDIDATE_EPSG = 5070
UTM_BOUNDARY_LONGITUDE = Decimal("-102")
WEST_EPSG = 32613
EAST_EPSG = 32614
# The zone is computed from the pair-local midpoint, not chosen from a pair. Over the ND
# rectangle the formula reproduces the previous boundary rule at -102 exactly, so ND distances
# are unchanged; Montana reaches UTM 11N, and a zone outside this set fails the mart CHECK
# loudly rather than being measured nine degrees off its central meridian.
UTM_EPSG_BASE = 32600
SUPPORTED_ZONE_EPSGS = (32611, 32612, 32613, 32614)
# Montana's western edge is 116.05W and North Dakota's eastern is 96.5W. The longitude floor
# also has to clear the discovery radius west of the ND/MT line: an ND lateral on the border
# needs candidates out to about -104.16, so -104.15 was already too tight for ND alone.
SUPPORTED_LONGITUDE_MIN = Decimal("-116.10")
SUPPORTED_LONGITUDE_MAX = Decimal("-96.50")
# The same measurement on the other axis, and it had no rationale beside it at all: Montana's
# southern edge is 44.36N and the 49th parallel is the international boundary both states end
# at. The floor clears the discovery radius south of Montana's line and the ceiling clears the
# border by a pad, so a subject on either edge still finds its offsets. 066's CHECK restates
# the longitude pair; the test that holds the two spellings equal is what stops one being
# widened alone.
SUPPORTED_LATITUDE_MIN = Decimal("44.30")
SUPPORTED_LATITUDE_MAX = Decimal("49.05")
# EPSG:5070 is equal-area rather than equidistant. A two-percent discovery pad prevents its
# local scale distortion from dropping a true edge; the pair-local UTM measurement below is
# still the only value admitted to the persisted 26,400-foot mart.
CANDIDATE_PAD = Decimal("1.02")
ADVISORY_LOCK_ID = 7_029_563_500_272_080_021

def utm_zone_epsg(longitude: float) -> int:
    """The zone a longitude falls in. The SQL in _EDGES computes the same expression.

    Kept here so the test suite has one definition to import rather than a second copy that
    can drift: a reimplementation in a test is how a zone rule and its proof stop agreeing.
    """
    return UTM_EPSG_BASE + int((longitude + 180) // 6) + 1


RULES = (
    "cr_nd_geometry_provenance_1",
    "cr_nd_neighbor_context_1",
    "cr_nd_neighbor_distance_1",
    "cr_ff_completion_anchor_1",
    "cr_nd_formation_group_1",
)

_COMPONENTS = f"""
create temporary table gw_nd_neighbor_components on commit drop as
select s.api10, s.geom_key, st_force2d(s.geom) as geom,
       st_transform(st_force2d(s.geom), {CANDIDATE_EPSG}) as candidate_geom
 from canonical.well_spatial s
 where s.geom_type = 'lateral'
   and left(s.api10, 2) = any(%(state_codes)s)
"""

_SUBJECTS = """
create temporary table gw_nd_neighbor_subjects on commit drop as
with component_counts as (
    select api10, count(*)::integer as lateral_component_count
      from gw_nd_neighbor_components
     group by api10
), completion_anchors as (
    select a.api10, min(a.completion_date) as completion_date
      from canonical.well_completion_anchors_latest a
      join component_counts c on c.api10 = a.api10
     where a.source_id = %(completion_source_id)s
       and a.anchor_kind = 'hydraulic_frac_job_end'
     group by a.api10
), current_pool_rows as (
    select c.api10, c.production_month, btrim(c.pool_reported) as pool_reported
      from canonical.well_completions_latest c
      join component_counts components on components.api10 = c.api10
     where c.source_id = %(formation_source_id)s
       and nullif(btrim(c.pool_reported), '') is not null
), first_months as (
    select api10, min(production_month) as formation_month
      from current_pool_rows
     group by api10
), first_pools as (
    select distinct p.api10, m.formation_month, p.pool_reported
      from current_pool_rows p
      join first_months m
        on m.api10 = p.api10 and m.formation_month = p.production_month
), alias_ranked as (
    select p.api10, p.formation_month, p.pool_reported,
           a.formation_raw, a.formation, a.formation_group, a.confidence,
           row_number() over (
               partition by p.api10, p.pool_reported
               order by a.effective_from desc nulls last,
                        a.created_vintage desc nulls last,
                        a.formation, a.formation_group) as alias_rank
      from first_pools p
      left join lineage.formation_aliases a
        on a.formation_raw = p.pool_reported
       and a.source_id = %(formation_source_id)s
       and a.effective_from <= %(snapshot_vintage)s::date
       and a.created_vintage is not null
       and a.created_vintage <= %(snapshot_vintage)s::date
), current_aliases as (
    select * from alias_ranked where alias_rank = 1
), pool_summary as (
    select api10, min(formation_month) as formation_month,
           array_agg(pool_reported order by pool_reported) as formation_pools,
           count(*)::integer as pool_count,
           count(*) filter (where formation_raw is not null)::integer as alias_count,
           count(*) filter (where confidence >= %(min_confidence)s)::integer
               as qualified_count,
           count(distinct formation) filter (where confidence >= %(min_confidence)s)::integer
               as formation_count,
           count(distinct formation_group)
               filter (where confidence >= %(min_confidence)s)::integer as group_count,
           min(formation) filter (where confidence >= %(min_confidence)s) as formation_id,
           min(formation_group) filter (where confidence >= %(min_confidence)s)
               as formation_group
      from current_aliases
     group by api10
), classified as (
    select c.api10, a.completion_date, c.lateral_component_count,
           coalesce(p.formation_pools, '{}'::text[]) as formation_pools,
           p.formation_month,
           case
             when p.api10 is null then 'pool_unavailable'
             when p.alias_count <> p.pool_count then 'alias_unavailable'
             when p.qualified_count <> p.pool_count then 'below_confidence'
             when p.formation_count <> 1 or p.group_count <> 1 then 'conflict'
             else 'mapped'
           end as formation_status,
           p.formation_id, p.formation_group
      from component_counts c
      left join completion_anchors a on a.api10 = c.api10
      left join pool_summary p on p.api10 = c.api10
)
select api10, completion_date,
       case when formation_status = 'mapped' then formation_id end as formation_id,
       case when formation_status = 'mapped' then formation_group end as formation_group,
       formation_status, formation_pools, formation_month, lateral_component_count,
       %(snapshot_vintage)s::date as snapshot_vintage
  from classified
"""

_EDGES = f"""
create temporary table gw_nd_neighbor_edges on commit drop as
with candidate_pairs as (
    select subject.api10, neighbor.api10 as neighbor_api10,
           subject.geom_key as subject_geom_key,
           neighbor.geom_key as neighbor_geom_key,
           subject.geom as subject_geom, neighbor.geom as neighbor_geom,
           {UTM_EPSG_BASE} + floor((st_x(st_transform(st_lineinterpolatepoint(
               st_shortestline(subject.candidate_geom, neighbor.candidate_geom), 0.5), 4326))
               + 180) / 6)::int + 1 as distance_epsg
      from gw_nd_neighbor_components subject
      join gw_nd_neighbor_components neighbor
        on subject.api10 < neighbor.api10
       and st_dwithin(
               subject.candidate_geom,
               neighbor.candidate_geom,
               %(candidate_radius_m)s)
), measured as (
    select api10, neighbor_api10, subject_geom_key, neighbor_geom_key, distance_epsg,
           st_distance(
               st_transform(subject_geom, distance_epsg),
               st_transform(neighbor_geom, distance_epsg)) as distance_m
      from candidate_pairs
), winners as (
    select distinct on (api10, neighbor_api10)
           api10, neighbor_api10, distance_m, distance_epsg,
           subject_geom_key, neighbor_geom_key
      from measured
     where distance_m <= %(max_radius_m)s
     order by api10, neighbor_api10, distance_m, subject_geom_key, neighbor_geom_key
), directed as (
    select api10, neighbor_api10, distance_m, distance_epsg,
           subject_geom_key, neighbor_geom_key
      from winners
    union all
    select neighbor_api10, api10, distance_m, distance_epsg,
           neighbor_geom_key, subject_geom_key
      from winners
)
select api10, neighbor_api10, round(distance_m::numeric, 3) as distance_m,
       distance_epsg, subject_geom_key, neighbor_geom_key,
       %(snapshot_vintage)s::date as snapshot_vintage
  from directed
"""

_INPUT_DERIVATIONS = """
with lateral_apis as (
    select distinct api10
      from canonical.well_spatial
     where geom_type = 'lateral' and left(api10, 2) = any(%(state_codes)s)
), identifiers as (
    select s.derivation_id
      from canonical.well_spatial s
     where s.geom_type = 'lateral' and left(s.api10, 2) = any(%(state_codes)s)
    union
    select a.derivation_id
      from canonical.well_completion_anchors_latest a
      join lateral_apis l on l.api10 = a.api10
     where a.source_id = %(completion_source_id)s
    union
    select c.derivation_id
      from canonical.well_completions_latest c
      join lateral_apis l on l.api10 = c.api10
     where c.source_id = %(formation_source_id)s
)
select d.derivation_id, d.created_vintage
  from lineage.derivations d
  join identifiers i on i.derivation_id = d.derivation_id
 order by d.derivation_id
"""

_ALIAS_VINTAGE = """
select max(created_vintage)
  from lineage.formation_aliases
 where source_id = %(formation_source_id)s
   and created_vintage is not null
"""

_OUTSIDE_SUPPORTED_DOMAIN = """
select left(api10, 2) as state_code, count(*), min(api10 || ':' || geom_key)
  from canonical.well_spatial
 where geom_type = 'lateral'
   and left(api10, 2) = any(%(state_codes)s)
   and not st_coveredby(
       st_force2d(geom),
       st_makeenvelope(
           %(longitude_min)s, %(latitude_min)s,
           %(longitude_max)s, %(latitude_max)s, 4326))
 group by 1
 order by 1
"""

_ALIAS_IDENTITY = """
with ranked as (
    select formation_raw, formation, formation_group, confidence, effective_from,
           created_vintage,
           row_number() over (
               partition by formation_raw
               order by effective_from desc nulls last, created_vintage desc nulls last,
                        formation, formation_group) as alias_rank
      from lineage.formation_aliases
     where source_id = %(formation_source_id)s
       and effective_from <= %(snapshot_vintage)s::date
       and created_vintage is not null
       and created_vintage <= %(snapshot_vintage)s::date
)
select formation_raw, formation, formation_group, confidence, effective_from, created_vintage
  from ranked
 where alias_rank = 1
 order by formation_raw
"""

_SUBJECT_DIGEST = """
select api10, completion_date, formation_id, formation_group, formation_status,
       formation_pools, formation_month, lateral_component_count, snapshot_vintage
  from gw_nd_neighbor_subjects
 order by api10
"""

_EDGE_DIGEST = """
select api10, neighbor_api10, distance_m, distance_epsg,
       subject_geom_key, neighbor_geom_key, snapshot_vintage
  from gw_nd_neighbor_edges
 order by api10, neighbor_api10
"""

_RESIDENT_SUBJECT_DIGEST = """
select api10, completion_date, formation_id, formation_group, formation_status,
       formation_pools, formation_month, lateral_component_count, snapshot_vintage
  from marts.nd_neighbor_subjects
 order by api10
"""

_RESIDENT_EDGE_DIGEST = """
select api10, neighbor_api10, distance_m, distance_epsg,
       subject_geom_key, neighbor_geom_key, snapshot_vintage
  from marts.nd_neighbor_edges
 order by api10, neighbor_api10
"""


@dataclass(frozen=True, slots=True)
class NeighborRefresh:
    derivation_id: str
    snapshot_vintage: date
    subject_rows: int
    edge_rows: int
    changed: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "derivation_id": self.derivation_id,
            "snapshot_vintage": self.snapshot_vintage.isoformat(),
            "subject_rows": self.subject_rows,
            "edge_rows": self.edge_rows,
            "changed": self.changed,
        }


def subject_prefixes(registry: JurisdictionRegistry) -> tuple[str, ...]:
    """The registered subjects whose domain this mart's measurement actually reaches.

    `neighbors_available` says a registration has laterals to offer; a serving `neighbors_scope`
    rule says the envelope and the UTM zone set this mart measured cover it. One without the
    other is an exclusion with a reason, never an outlier that stops the run.
    """
    covered = [
        row.identity_prefix
        for row in registry
        if row.neighbors_available
        and row.identity_prefix is not None
        and row.rule(NEIGHBORS_SCOPE) is not None
    ]
    return tuple(
        sorted(
            covered,
            key=lambda prefix: (
                _REGISTRATION_ORDER.index(prefix)
                if prefix in _REGISTRATION_ORDER
                else len(_REGISTRATION_ORDER),
                prefix,
            ),
        )
    )


def excluded_prefixes(registry: JurisdictionRegistry) -> tuple[str, ...]:
    """Registered neighbours-available jurisdictions the measured domain does not reach."""
    covered = set(subject_prefixes(registry))
    return tuple(
        sorted(
            row.identity_prefix
            for row in registry
            if row.neighbors_available
            and row.identity_prefix is not None
            and row.identity_prefix not in covered
        )
    )


def refresh_neighbors(connection: psycopg.Connection) -> NeighborRefresh:
    """Atomically rebuild directed ND neighbour subjects and edges from canonical inputs."""
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise RuntimeError("neighbor refresh requires an idle connection")
    with connection.cursor() as cursor:
        cursor.execute("set transaction isolation level repeatable read")
        cursor.execute("select pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_ID,))
        cursor.execute("select current_setting('transaction_isolation')")
        if cursor.fetchone()[0] != "repeatable read":
            raise RuntimeError("neighbor refresh requires repeatable read")

    registry = load_jurisdictions(connection)
    subjects = subject_prefixes(registry)
    excluded = excluded_prefixes(registry)
    inputs = _inputs(connection, subjects)
    snapshot_vintage = max(
        (item.as_of_vintage for item in inputs if item.as_of_vintage is not None),
        default=current_session().vintage,
    )
    parameters = {
        "state_codes": list(subjects),
        "completion_source_id": COMPLETION_SOURCE_ID,
        "formation_source_id": FORMATION_SOURCE_ID,
        "min_confidence": MIN_ALIAS_CONFIDENCE,
        "snapshot_vintage": snapshot_vintage,
        "max_radius_m": MAX_RADIUS_M,
        "candidate_radius_m": MAX_RADIUS_M * CANDIDATE_PAD,
        "longitude_min": SUPPORTED_LONGITUDE_MIN,
        "longitude_max": SUPPORTED_LONGITUDE_MAX,
        "latitude_min": SUPPORTED_LATITUDE_MIN,
        "latitude_max": SUPPORTED_LATITUDE_MAX,
    }
    with connection.cursor() as cursor:
        cursor.execute(_OUTSIDE_SUPPORTED_DOMAIN, parameters)
        outside = cursor.fetchall()
    if outside:
        # Named, and per jurisdiction. A registration with a serving neighbors_scope rule whose
        # geometry still leaves the envelope is a measurement that has stopped being true, and
        # the message has to say whose geometry it found rather than North Dakota's by habit.
        found = "; ".join(
            f"{registry.name_for(state_code) or state_code}: {count} component(s),"
            f" first {first}"
            for state_code, count, first in outside
        )
        raise RuntimeError(
            "neighbour geometry falls outside the measured candidate-CRS domain: " + found
        )
    _materialize(connection, parameters)
    subject_rows, subject_digest = _digest(connection, _SUBJECT_DIGEST)
    edge_rows, edge_digest = _digest(connection, _EDGE_DIGEST)

    with derive(
        "mart.refresh",
        output=OutputSpec(
            store="postgis",
            dataset="marts.nd_neighbors",
            partition={"state": "ND", "snapshot_vintage": snapshot_vintage.isoformat()},
            schema_version="1",
        ),
        params={
            "state_codes": list(subjects),
            "geometry_scope": "current_only",
            "geometry_type": "lateral",
            "candidate_epsg": CANDIDATE_EPSG,
            "candidate_pad": str(CANDIDATE_PAD),
            "supported_domain": {
                "longitude": [str(SUPPORTED_LONGITUDE_MIN), str(SUPPORTED_LONGITUDE_MAX)],
                "latitude": [str(SUPPORTED_LATITUDE_MIN), str(SUPPORTED_LATITUDE_MAX)],
            },
            "distance_epsg_policy": {
                "utm_epsg_base": UTM_EPSG_BASE,
                "supported_zone_epsgs": list(SUPPORTED_ZONE_EPSGS),
                "zone_formula": "32600 + floor((midpoint_longitude + 180) / 6) + 1",
                "selection": "candidate_crs_shortest_line_midpoint",
            },
            "max_radius_ft": MAX_RADIUS_FT,
            "completion_policy": "earliest_current_fracfocus_job_end",
            "formation_policy": "earliest_nonblank_nd_mpr_pool_set",
            "formation_alias_scope": "source_scoped_only_no_legacy_fallback",
            "formation_conflict_policy": "distinct_exact_formation_or_group_is_conflict",
            "formation_min_confidence": str(MIN_ALIAS_CONFIDENCE),
        },
        inputs=inputs,
        rules=RULES,
        ttl_class="ephemeral",
    ) as context:
        context.set_rows(subject_rows + edge_rows)
        context.set_output_hash(
            hash_payload(
                {
                    "subjects": {"rows": subject_rows, "sha256": subject_digest},
                    "edges": {"rows": edge_rows, "sha256": edge_digest},
                }
            )
        )

    changed = not _already_current(
        connection,
        derivation_id=context.derivation_id,
        snapshot_vintage=snapshot_vintage,
        subject_rows=subject_rows,
        subject_digest=subject_digest,
        edge_rows=edge_rows,
        edge_digest=edge_digest,
    )
    if changed:
        _replace(connection, context.derivation_id)

    session = current_session()
    emit(
        connection,
        "mart.refreshed",
        subject_type="derivation",
        subject_id=context.derivation_id,
        payload={
            "dataset": "marts.nd_neighbors",
            "snapshot_vintage": snapshot_vintage.isoformat(),
            "subject_rows": subject_rows,
            "edge_rows": edge_rows,
            "changed": changed,
            # Only when there is something to say: an empty key on every run would change what
            # a reader of lineage.audit_events sees for a mart that excluded nothing.
            **(
                {"excluded_jurisdictions": list(excluded)}
                if excluded
                else {}
            ),
        },
        correlation_id=session.correlation_id,
        occurred_at=session.clock.now(),
    )
    return NeighborRefresh(
        derivation_id=context.derivation_id,
        snapshot_vintage=snapshot_vintage,
        subject_rows=subject_rows,
        edge_rows=edge_rows,
        changed=changed,
    )


def _inputs(connection: psycopg.Connection, subjects: Sequence[str]) -> list[InputRef]:
    params = {
        "state_codes": list(subjects),
        "completion_source_id": COMPLETION_SOURCE_ID,
        "formation_source_id": FORMATION_SOURCE_ID,
    }
    with connection.cursor() as cursor:
        cursor.execute(_INPUT_DERIVATIONS, params)
        inputs = [
            InputRef(kind="derivation", ref_id=identifier, as_of_vintage=vintage)
            for identifier, vintage in cursor.fetchall()
        ]
        cursor.execute(_ALIAS_VINTAGE, params)
        alias_vintage = cursor.fetchone()[0]
    snapshot_vintage = max(
        (
            *(item.as_of_vintage for item in inputs if item.as_of_vintage is not None),
            *(value for value in (alias_vintage, current_session().vintage) if value is not None),
        )
    )
    _, alias_digest = _digest(
        connection,
        _ALIAS_IDENTITY,
        {**params, "snapshot_vintage": snapshot_vintage},
    )
    inputs.append(
        InputRef(
            kind="external",
            ref_id=f"lineage.formation_aliases:sha256:{alias_digest}",
            selector=f"source_id={FORMATION_SOURCE_ID}",
            as_of_vintage=snapshot_vintage,
            role="crosswalk",
        )
    )
    return inputs


def _materialize(connection: psycopg.Connection, parameters: dict[str, object]) -> None:
    with connection.cursor() as cursor:
        cursor.execute("drop table if exists pg_temp.gw_nd_neighbor_edges")
        cursor.execute("drop table if exists pg_temp.gw_nd_neighbor_subjects")
        cursor.execute("drop table if exists pg_temp.gw_nd_neighbor_components")
        cursor.execute(_COMPONENTS, parameters)
        cursor.execute(
            "create index gw_nd_neighbor_components_candidate_idx"
            " on gw_nd_neighbor_components using gist (candidate_geom)"
        )
        cursor.execute("analyze gw_nd_neighbor_components")
        cursor.execute(_SUBJECTS, parameters)
        cursor.execute("alter table gw_nd_neighbor_subjects add primary key (api10)")
        cursor.execute(_EDGES, parameters)
        cursor.execute(
            "alter table gw_nd_neighbor_edges add primary key (api10, neighbor_api10)"
        )
        cursor.execute(
            "create index gw_nd_neighbor_edges_page_idx"
            " on gw_nd_neighbor_edges (api10, distance_m, neighbor_api10)"
        )


def _digest(
    connection: psycopg.Connection,
    statement: str,
    parameters: dict[str, object] | None = None,
) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    with connection.cursor() as cursor:
        cursor.execute(statement, parameters)
        for row in cursor:
            digest.update(canonical_json(row))
            digest.update(b"\n")
            count += 1
    return count, digest.hexdigest()


def resident_content_identity(
    connection: psycopg.Connection,
) -> tuple[int, str, int, str]:
    """Return the exact persisted subject and edge identities used by the mart recorder."""
    subject_rows, subject_digest = _digest(connection, _RESIDENT_SUBJECT_DIGEST)
    edge_rows, edge_digest = _digest(connection, _RESIDENT_EDGE_DIGEST)
    return subject_rows, subject_digest, edge_rows, edge_digest


def _already_current(
    connection: psycopg.Connection,
    *,
    derivation_id: str,
    snapshot_vintage: date,
    subject_rows: int,
    subject_digest: str,
    edge_rows: int,
    edge_digest: str,
) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "select count(*), count(*) filter (where derivation_id = %s"
            " and snapshot_vintage = %s) from marts.nd_neighbor_subjects",
            (derivation_id, snapshot_vintage),
        )
        actual_subjects, matching_subjects = cursor.fetchone()
        cursor.execute(
            "select count(*), count(*) filter (where derivation_id = %s"
            " and snapshot_vintage = %s) from marts.nd_neighbor_edges",
            (derivation_id, snapshot_vintage),
        )
        actual_edges, matching_edges = cursor.fetchone()
    if not (
        actual_subjects == matching_subjects == subject_rows
        and actual_edges == matching_edges == edge_rows
    ):
        return False
    (
        resident_subject_rows,
        resident_subject_digest,
        resident_edge_rows,
        resident_edge_digest,
    ) = resident_content_identity(connection)
    return (
        resident_subject_rows == subject_rows
        and resident_subject_digest == subject_digest
        and resident_edge_rows == edge_rows
        and resident_edge_digest == edge_digest
    )


def _replace(connection: psycopg.Connection, derivation_id: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("delete from marts.nd_neighbor_edges")
        cursor.execute("delete from marts.nd_neighbor_subjects")
        cursor.execute(
            "insert into marts.nd_neighbor_subjects"
            " (api10, completion_date, formation_id, formation_group, formation_status,"
            " formation_pools, formation_month, lateral_component_count, snapshot_vintage,"
            " derivation_id)"
            " select api10, completion_date, formation_id, formation_group, formation_status,"
            " formation_pools, formation_month, lateral_component_count, snapshot_vintage, %s"
            " from gw_nd_neighbor_subjects order by api10",
            (derivation_id,),
        )
        cursor.execute(
            "insert into marts.nd_neighbor_edges"
            " (api10, neighbor_api10, distance_m, distance_epsg, subject_geom_key,"
            " neighbor_geom_key, snapshot_vintage, derivation_id)"
            " select api10, neighbor_api10, distance_m, distance_epsg, subject_geom_key,"
            " neighbor_geom_key, snapshot_vintage, %s"
            " from gw_nd_neighbor_edges order by api10, neighbor_api10",
            (derivation_id,),
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh current ND physical neighbours.")
    add_dsn_argument(parser)
    parser.add_argument("--env-id", default=None, help="override the fingerprinted env id")
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)
    arguments.dsn = resolve_dsn(arguments.dsn)

    with psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        connection.commit()
        with lineage_session(recorder=PostgresRecorder(connection), environment=environment):
            report = refresh_neighbors(connection)
        connection.commit()
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
