"""The well spine: the collection the map lists and the header the card renders."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import (
    AsOf,
    Connection,
    Cursor,
    ExplainEffect,
    Principal,
    WellsLimit,
    jurisdictions,
    rows,
)
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import (
    EXAMPLE_API10,
    EXAMPLE_BBOX,
    GLOSSARY_KEY,
    dataset,
    not_a_figure,
    request_example,
    semantics,
)
from glasswell.api.pagination import (
    DEFAULT_LIMIT,
    decode_cursor,
    encode_cursor,
    next_link,
    page,
    query_fingerprint,
)
from glasswell.api.provenance import register_response_figures
from glasswell.api.rate_limit import consume_rate_limit
from glasswell.api.responses import EnvelopeModel, FigureModel, enveloped, inline_for, iso
from glasswell.api.routers.facets import StateTerm, state_set
from glasswell.lengths import (
    STORAGE_EPSG,
    LengthRuleUnregistered,
    resolve_length_method,
)
from glasswell.lineage.conformance import (
    LeaseReportingRule,
    lease_reporting_rule,
    pool_grain_rule,
)
from glasswell.lineage.envelope import Figure, collect_handles, distinct_handles, figure
from glasswell.lineage.explain import MAX_HANDLES
from glasswell.lineage.ids import format_handle
from glasswell.lineage.jurisdictions import NEIGHBORS_SCOPE, JurisdictionRegistry
from glasswell.lineage.selector_registry import identity_selector_term
from glasswell.marts.cumulatives import (
    LIQUIDS_BASIS,
    MART_STREAMS,
    STATE_API_PREFIXES,
)
from glasswell.marts.producing import (
    PRODUCING_CLASSES,
    PRODUCING_RULE_IDS,
    UNKNOWN,
    ProducingPolicy,
    ProducingPolicyError,
    anchor_month,
    class_expression,
    load_producing_policy,
    producing_params,
    window_start,
)
from glasswell.marts.tiles import TILE_BUFFER, TILE_EXTENT, TILE_MAX_ZOOM, WEB_MERCATOR
from glasswell.marts.vintage_cohorts import (
    COHORT_RULE,
    POPULATION_SCOPE_DETAIL,
    SPACING_ASSUMPTION_REASON,
    SUPPORT_SCALE_NOTE,
    cohort_rollup,
    load_cohort_policy,
)
from glasswell.modeling.served import (
    UnregisteredArtifact,
    resolve_pinned_control,
    subject_origins,
)

# The decision name and the two clock classes are the rule's own, spelled once in the
# module that defines the rule: a second spelling here is how a decision name drifts.
from glasswell.seed.conformance_status_history import (
    LOAD_STAMP,
    SOURCE_VALID_TIME,
    STATUS_HISTORY,
)
from glasswell.status_resolution import resolved_status, resolver_join
from glasswell.units import metres_to_feet

router = APIRouter(tags=["wells"])

BBOX_DEGREE_CAP = 4.0
STATUS_SUMMARY_REQUESTS_PER_MINUTE = 30
API10_PATTERN = r"^\d{10}$"
# Not API10_PATTERN: §5.3 freezes that one on the path, and the spine lookup also takes the
# API-14 literal a reader is as likely to be holding.
API_IDENTITY_PATTERN = r"^\d{10}(?:\d{4})?$"
BBOX_PARTS = 4
LON_LIMIT = 180.0
LAT_LIMIT = 90.0
COUNT_UNIT = "wells"

# R8: every per-jurisdiction decision this router serves is a row in lineage.jurisdiction_rules
# resolved at the request's knowledge cut, never a map in this module. status_vocabulary,
# geometry_provenance and length_scope are decisions; whether the neighbour mart holds subjects
# is the neighbors_available column. An unregistered prefix yields a null rule, which is an
# answer; a registry that resolves nothing is service_degraded.
STATUS_VOCABULARY = "status_vocabulary"
GEOMETRY_PROVENANCE = "geometry_provenance"
LENGTH_SCOPE = "length_scope"
# Served in the figure's place where a jurisdiction registers a length_scope rule: the length
# resolver answers nd_gis_horizontals_line for a well with no basin, so serving a length there
# would put a rule about North Dakota geometry on a Montana map stick.
LENGTH_NOT_SERVED = "not_served"
# A registry gap, not a decision: no rule withholds this length, none computes it either. The
# distinction matters on the wire because a withheld figure names the rule that withheld it and
# this one has none to name.
LENGTH_SCOPE_UNREGISTERED = "length_scope_unregistered"
# `neighbors_available` is the registration: this jurisdiction has laterals to offer. The
# neighbour mart's *measured domain* is a second decision, and a registration outside it is
# excluded from the mart -- so the card is told why rather than shown an empty frame.
NEIGHBORS_NOT_COVERED = "neighbors_domain_not_covered"

# The cohort key is an identifier for a group, not a measurement about it. Byte-equal to the
# non_figure_allowlist.yml entry that covers /cohorts/*/cohort_year (test_not_a_figure.py).
COHORT_YEAR_REASON = (
    "Cohort key. The year that identifies a cohort of wells; an identifier for the group, not"
    " a quantity measured about it. Which year it is - spud or completion anchor - is stated"
    " by cohort_basis and ruled by cohort_key_rule."
)
POPULATION_STATE_REASON = (
    "API state prefix naming what this population covers; an identifier, not a quantity. Same"
    " class as /state_code."
)
COHORT_STREAM_COLUMNS = dict(zip(MART_STREAMS, ("oil_bbl", "gas_mcf", "water_bbl"), strict=True))
COHORT_STREAM_UNITS = {"liquid": "bbl", "gas": "mcf", "water": "bbl"}
COHORT_STREAM_BASIS = {"liquid": LIQUIDS_BASIS, "gas": None, "water": "water"}

WELL_LABELS = {
    "/api10": "gt_api_10_api_12_api_14",
    "/status_vocabulary_rule": "gt_conformance_rule",
    # The Identity section's own rows. `identity.ts` sources every term id from these
    # pointers, so a field with no pointer here can never highlight, whatever the glossary
    # seeds (gate M3).
    "/status_reported": "gt_well_status",
    "/status_canonical": "gt_well_status",
    "/well_type_reported": "gt_well_type",
    "/jurisdiction_name": "gt_jurisdiction",
    "/regulator_name": "gt_regulator",
    "/geometry_provenance_rule": "gt_geometry_provenance",
    "/basin_context/basin_name": "gt_basin",
    "/basin_context/play_name": "gt_play",
    # The scope label is not the basin: pointing both at gt_basin taught the confusion §6.1
    # exists to name (gate N2).
    "/basin_context/basin_label_filed": "gt_scope_label",
    "/basin_context/rule_id": "gt_conformance_rule",
    "/land_unit_label": "gt_land_unit",
    "/confidential_flag": "gt_confidential_well",
    "/lateral_length_ft": "gt_wellbore",
    "/total_depth_ft": "gt_wellbore",
}

STATUS_SUMMARY_LABELS = {
    "/statuses": "gt_well_status",
    "/unmapped_wells": "gt_well_status",
    "/vocabulary_rules": "gt_conformance_rule",
    "/producing": "gt_conformance_rule",
    "/producing_rules": "gt_conformance_rule",
    "/producing_window/liquids_basis": "gt_stream",
}

_PRODUCING_CLASS = class_expression(api10="ranked.api10", state_code="ranked.state_code")

# The guard is not decoration: with the definition unregistered the classifier would answer
# `unknown` for every well, which reads as a fact about the wells rather than about the
# registry. Short-circuiting to NULL is what lets the response say it does not know.
_PRODUCING_COLUMN = f"case when %(producing_registered)s::boolean then {_PRODUCING_CLASS} end"

_COLUMNS = (
    "api10, api14, state_code, county_code_at_permit, ndic_file_no, operator_name_reported,"
    " operator_id, well_name,"
    f" {resolved_status('ranked')} as status_canonical,"
    " status_reported, well_type_reported, spud_date,"
    " confidential_flag, basin, land_unit_label, total_depth_ft, completion_date,"
    " effective_from, source_manifest_id, derivation_id,"
    " greatest(effective_from, manifest_vintage,"
    "          coalesce(derivation_vintage, manifest_vintage)) as available_on,"
    " (select coalesce(array_agg(distinct s.geom_type order by s.geom_type), '{}'::text[])"
    "    from canonical.well_spatial s"
    "    join lineage.manifests sm on sm.manifest_id = s.source_manifest_id"
    "    join lineage.derivations sd on sd.derivation_id = s.derivation_id"
    "   where s.api10 = ranked.api10"
    "     and (%(as_of)s::date is null or sm.fetch_vintage <= %(as_of)s::date)"
    "     and (%(as_of)s::date is null or sd.created_vintage is null"
    "          or sd.created_vintage <= %(as_of)s::date)) as geometry_provenance"
)

_SPINE = """
with ranked as (
    select w.*, m.fetch_vintage as manifest_vintage,
           d.created_vintage as derivation_vintage,
           row_number() over (
               partition by w.api10 order by w.effective_from desc, w.created_at desc) as rn
      from canonical.wells w
      join lineage.manifests m on m.manifest_id = w.source_manifest_id
      join lineage.derivations d on d.derivation_id = w.derivation_id
     where (%(as_of)s::date is null or w.effective_from <= %(as_of)s::date)
       and (%(as_of)s::date is null or m.fetch_vintage <= %(as_of)s::date)
       and (%(as_of)s::date is null or d.created_vintage is null
            or d.created_vintage <= %(as_of)s::date))
select {columns}
  from ranked
{resolver}
 where rn = 1
"""

# Two projections of one spine. `/v1/wells` and the well card class each row; the production
# routes read the same spine and bind none of the producing parameters, so widening the shared
# constant would break them at query time rather than here.
RANKED_WELLS = _SPINE.format(columns=_COLUMNS, resolver=resolver_join("ranked"))
RANKED_WELLS_PRODUCING = _SPINE.format(
    columns=f"{_COLUMNS}, {_PRODUCING_COLUMN} as producing", resolver=resolver_join("ranked")
)

# The basin block, read from the mart the rules decided rather than recomputed here. One row
# per well by construction, so a well with no row is a pipeline state -- the mart has not been
# refreshed since the well landed -- and never a silent null basin.
_BASIN_CONTEXT = """
select basin_name, basin_class, basin_overlap, play_name, play_class, basin_label_filed,
       label_class, label_agrees, boundary_vintage, geometry_basis, rule_id, derivation_id
  from marts.well_basin_context
 where api10 = %(api10)s
"""

# Every line the Basin section draws, and the mart column each one reads. R6: a served answer a
# reader cannot resolve to the run that produced it is untraceable, and untraceable equals
# wrong -- the rule does not stop at numbers, and `outside_published_boundaries` is an answer.
_BASIN_LINEAGE_COLUMNS = (
    "basin_name",
    "basin_class",
    "play_name",
    "play_class",
    "basin_label_filed",
    "label_class",
    "label_agrees",
    "boundary_vintage",
    "geometry_basis",
    "basin_overlap",
)

# Every effective-dated header the well carries, newest first, with the class resolved through
# the one shared resolver rather than through a second mapping written here. No view and no
# DDL: `canonical.wells` is already indexed on (api10, effective_from) and this is a scalar
# join onto it. The axis is `status_reported` -- what the regulator filed -- because
# `status_canonical` is glasswell's own mapping and a history over it would show a rule edit
# as if the regulator had changed its mind (the jurisdiction's status_history rule).
_STATUS_HISTORY = """
select w.effective_from, w.status_reported,
       {resolved} as status_canonical,
       greatest(m.fetch_vintage, coalesce(d.created_vintage, m.fetch_vintage)) as available_on
  from canonical.wells w
  join lineage.manifests m on m.manifest_id = w.source_manifest_id
  join lineage.derivations d on d.derivation_id = w.derivation_id
{resolver}
 where w.api10 = %(api10)s
   and (%(as_of)s::date is null or w.effective_from <= %(as_of)s::date)
   and (%(as_of)s::date is null or m.fetch_vintage <= %(as_of)s::date)
   and (%(as_of)s::date is null or d.created_vintage is null
        or d.created_vintage <= %(as_of)s::date)
 order by w.effective_from desc, w.created_at desc
"""

STATUS_HISTORY_SQL = _STATUS_HISTORY.format(
    resolved=resolved_status("w"), resolver=resolver_join("w")
)

# Ten rows and a count of the rest: 248 New Mexico wells carry more than ten headers and the
# fullest carries 15, so the cap is what keeps a readable answer readable and the count is what
# stops a short list reading as a short life. (15,590 is the population's distinct filed dates,
# which is a different number about a different thing.)
STATUS_HISTORY_CAP = 10

# `tiled` asks the tile pipeline's own question of the deepest published zoom: a geometry that
# ST_AsMVTGeom drops there is on no tile at any zoom, while the card still serves its length.
_SPATIAL = f"""
select s.geom_type, s.geom_key, s.derivation_id, s.source_datum, s.source_manifest_id,
       greatest(m.fetch_vintage, coalesce(d.created_vintage, m.fetch_vintage)) as available_on,
       {{length_metres}} as length_m,
       case when st_geometrytype(geom) = 'ST_Point' then st_x(geom) end as lon,
       case when st_geometrytype(geom) = 'ST_Point' then st_y(geom) end as lat,
       st_asmvtgeom(
           st_transform(geom, {WEB_MERCATOR}),
           st_tileenvelope(
               {TILE_MAX_ZOOM},
               floor((st_x(st_centroid(geom)) + 180) / 360 * (2 ^ {TILE_MAX_ZOOM}))::int,
               floor((1 - asinh(tan(radians(st_y(st_centroid(geom)))))
                        / pi()) / 2 * (2 ^ {TILE_MAX_ZOOM}))::int),
           {TILE_EXTENT}, {TILE_BUFFER}, true) is not null as tiled
  from canonical.well_spatial s
  join lineage.manifests m on m.manifest_id = s.source_manifest_id
  join lineage.derivations d on d.derivation_id = s.derivation_id
 where s.api10 = %(api10)s
   and (%(as_of)s::date is null or m.fetch_vintage <= %(as_of)s::date)
   and (%(as_of)s::date is null or d.created_vintage is null
        or d.created_vintage <= %(as_of)s::date)
 order by s.geom_type, s.geom_key
"""

# The box narrows first and the spine is resolved over what it returned: `in_view` is an
# index-answerable predicate on well_spatial_geom_idx, and `distinct on` then picks one row per
# api10 in it. The left join is what keeps a promoted geometry whose api10 never reached the
# spine visible — it groups as `no_well_row` and is disclosed, never silently dropped and never
# folded into the no-status class, which is a different fact.
#
# `in_view` is referenced exactly once on purpose. A second reference makes PostgreSQL
# materialise the CTE, which erases its row estimate; measured at 2,000 seeded wells, the
# estimate fell to 1, the planner chose a nested loop with a join filter, and a 501-well box
# cost 125,250 filter comparisons and 28 ms — quadratic in the wells in view, on the small
# boxes the map spends its life in. Inlined, the same box is 3 ms. See work-output/wss-status.md.
STATUS_SUMMARY_SQL = f"""
with in_view as (
    select distinct api10
      from canonical.well_spatial
     where st_intersects(geom,
                         st_makeenvelope(%(minx)s, %(miny)s, %(maxx)s, %(maxy)s, 4326))),
     latest as (
    select distinct on (v.api10)
           v.api10, {resolved_status("w")} as status_canonical, w.basin, w.state_code,
           w.well_type_reported, w.derivation_id, w.effective_from
      from in_view v
      left join canonical.wells w
             on w.api10 = v.api10
            and (%(as_of)s::date is null or w.effective_from <= %(as_of)s::date)
     {resolver_join("w")}
     order by v.api10, w.effective_from desc nulls last, w.created_at desc nulls last),
     classed as (
    select ranked.*,
           case when %(producing_registered)s::boolean then {_PRODUCING_CLASS} end as producing
      from latest ranked)
select basin, state_code, status_canonical, well_type_reported, producing,
       derivation_id is null as no_well_row,
       count(*) as wells, max(derivation_id) as derivation_id,
       array_remove(array_agg(distinct derivation_id), null) as derivation_ids,
       max(effective_from) as effective_from
  from classed
 group by 1, 2, 3, 4, 5, 6
"""

# The geometry population itself, classed. Counts wells, not geometry rows; spine-free on
# purpose — geometry is not effective-dated, and an orphan still draws on the map (its
# absence from the status classes is already the geometry_without_a_well_row warning).
PROVENANCE_SUMMARY_SQL = """
select geom_type as geometry_provenance, count(distinct api10) as wells,
       max(derivation_id) as derivation_id,
       array_remove(array_agg(distinct derivation_id), null) as derivation_ids
  from canonical.well_spatial
 where st_intersects(geom,
                     st_makeenvelope(%(minx)s, %(miny)s, %(maxx)s, %(maxy)s, 4326))
 group by 1
"""

_STORAGE_CRS = """
select storage_epsg, effective_from
 from lineage.crs_registry
 where basin = %(basin)s
   and effective_from <= coalesce(%(as_of)s::date, current_date)
   and published_vintage <= greatest(
       coalesce(%(as_of)s::date, current_date),
       coalesce((select min(baseline.published_vintage)
                   from lineage.crs_registry baseline
                  where baseline.basin = %(basin)s),
                coalesce(%(as_of)s::date, current_date)))
 order by effective_from desc, published_vintage desc
 limit 1
"""

# A3-F3: a well whose only horizontal trace was held back reads as a well with no lateral at
# all unless the card says otherwise. Indexed on (source_id, row_payload->>'api10') in 016.
_HELD_BACK_GEOMETRY = """
select reason_code, rule_id, count(*) as rows,
       max(m.fetch_vintage) as available_on,
       string_agg(distinct row_payload ->> 'segment', ', ' order by row_payload ->> 'segment')
           as segments
  from lineage.quarantine_rows q
  join lineage.manifests m on m.manifest_id = q.first_seen_manifest_id
 where q.source_id = 'nd_gis_horizontals_line'
   and q.row_payload ->> 'api10' = %(api10)s
   and (q.state = 'open'
        or (q.released_at_vintage is not null
            and %(as_of)s::date is not null
            and q.released_at_vintage > %(as_of)s::date))
   and (%(as_of)s::date is null or m.fetch_vintage <= %(as_of)s::date)
 group by reason_code, rule_id
 order by reason_code
"""

_HELD_BACK_GEOMETRY_VINTAGE = """
select max(greatest(m.fetch_vintage,
                    coalesce(q.released_at_vintage, m.fetch_vintage))) as available_on
  from lineage.quarantine_rows q
  join lineage.manifests m on m.manifest_id = q.first_seen_manifest_id
 where q.source_id = 'nd_gis_horizontals_line'
   and q.row_payload ->> 'api10' = %(api10)s
   and (%(as_of)s::date is null
        or greatest(m.fetch_vintage,
                    coalesce(q.released_at_vintage, m.fetch_vintage)) <= %(as_of)s::date)
"""


class WellSummary(BaseModel):
    api10: str = Field(
        description="Ten-digit API well number.",
        json_schema_extra={
            GLOSSARY_KEY: "gt_api_10_api_12_api_14",
            **not_a_figure("Identifier, in a collection item."),
        },
    )
    well_name: str | None = Field(
        description="Well name as reported by the operator.",
        json_schema_extra={GLOSSARY_KEY: "gt_well_name"},
    )
    operator_name_reported: str | None = Field(
        description="Operator name exactly as reported.",
        json_schema_extra={GLOSSARY_KEY: "gt_operator_of_record"},
    )
    status_canonical: str | None = Field(
        description=(
            "Status mapped through the source's own status vocabulary rule, one per"
            " jurisdiction and named beside it in status_vocabulary_rule. Null where the"
            " source reported no status at all, or where its vocabulary maps that code to"
            " nothing — two different absences, and the rule says which."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_well_status"},
    )
    status_vocabulary_rule: str | None = Field(
        description=(
            "The conformance rule that decided status_canonical for this well's jurisdiction,"
            " resolvable at /v1/conformance/{rule_id}. Named on the row because the class is"
            " not always written by the promotion: New Mexico's is resolved at read time from"
            " the registry, so the row's own derivation cites the superseded rule and would"
            " send a reader to a decision that did not produce this value. Null where no rule"
            " is registered for the state."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )
    county_code_at_permit: str | None = Field(
        description="County code recorded at permit.",
        json_schema_extra={
            GLOSSARY_KEY: "gt_county_at_permit",
            **not_a_figure("County code, in a collection item."),
        },
    )
    land_unit_label: str | None = Field(description="PLSS land unit label.", json_schema_extra={
        GLOSSARY_KEY: "gt_land_unit"})
    spud_date: date | None = Field(
        description="Spud date as reported.",
        json_schema_extra={GLOSSARY_KEY: "gt_spud_date"},
    )
    confidential_flag: bool = Field(description="Whether the regulator withholds this well.",
                                    json_schema_extra={GLOSSARY_KEY: "gt_confidential_well"})
    effective_from: date = Field(description="Effective date of this well row (M13).",
                                 json_schema_extra={GLOSSARY_KEY: "gt_effective_date"})
    geometry_provenance: list[str] = Field(
        description=(
            "Distinct provenance classes of this well's recorded geometry, alphabetical —"
            " canonical geom_type served verbatim under the jurisdiction's geometry"
            " provenance rule: surface, bottomhole, lateral or survey_trace. Empty where no"
            " geometry is recorded."
        ),
    )
    producing: str | None = Field(
        description=(
            "Whether the well is producing on the evidence held, which is a different fact"
            " from its status: `producing` where a positive oil or gas month was filed inside"
            " the window, `not_producing` where the well filed but no such month, and"
            " `unknown` where it filed nothing, where the regulator withheld the months, where"
            " the jurisdiction reports at the lease, or where it reports below the well and"
            " nothing rolls up — the last two are both jurisdictions with no well-level series"
            " to evaluate, and the rule that says which is served as a warning beside the"
            " figure rather than left for the reader to guess."
            " Defined by cr_producing_window_1, cr_producing_streams_1 and"
            " cr_producing_evidence_1; liquids are oil plus condensate. Null where the"
            " definition is not registered, which is disclosed as a warning."
        ),
    )
    links: dict[str, str] = Field(description="Sub-resource paths for this well.")


class Geometry(BaseModel):
    geom_type: str = Field(description="surface, bottomhole or lateral.")
    geom_key: str = Field(description="Key of the geometry row within the well.")
    source_datum: str = Field(description="Datum the source published, before transform.",
                              json_schema_extra={GLOSSARY_KEY: "gt_datum"})


class SurfacePoint(BaseModel):
    lon: float = Field(
        description="Longitude in the storage CRS (EPSG:4326).",
        json_schema_extra=not_a_figure(
            "Geometry, not a figure. Storage CRS is EPSG:4326 and is stated alongside."
        ),
    )
    lat: float = Field(
        description="Latitude in the storage CRS (EPSG:4326).",
        json_schema_extra=not_a_figure(
            "Geometry, not a figure. Storage CRS is EPSG:4326 and is stated alongside."
        ),
    )


class WellDetail(WellSummary):
    # api10 and county_code_at_permit are redeclared, not inherited: the record and the
    # collection item are exempted by different allowlist entries, and an inherited Field
    # would publish the collection item's cross-reference on the record too.
    api10: str = Field(
        description="Ten-digit API well number.",
        json_schema_extra={
            GLOSSARY_KEY: "gt_api_10_api_12_api_14",
            **not_a_figure(
                "Identifier. A 10-digit API number is an identity string, not a measurement."
            ),
        },
    )
    county_code_at_permit: str | None = Field(
        description="County code recorded at permit.",
        json_schema_extra={
            GLOSSARY_KEY: "gt_county_at_permit",
            **not_a_figure("County code as reported at permit; an identifier, not a quantity."),
        },
    )
    api14: str | None = Field(
        description="Fourteen-digit API number where known.",
        json_schema_extra=not_a_figure("Identifier. The completion-level API number."),
    )
    state_code: str | None = Field(
        description="State code as reported.",
        json_schema_extra=not_a_figure(
            "FIPS-style state code carried as reported; an identifier, not a quantity."
        ),
    )
    ndic_file_no: str | None = Field(
        description="NDIC file number for the well.",
        json_schema_extra=not_a_figure(
            "The NDIC file number is the regulator's identifier for the well."
        ),
    )
    status_reported: str | None = Field(description="Status code exactly as the source wrote it.")
    well_type_reported: str | None = Field(description="Well type exactly as reported.")
    basin: str | None = Field(description="Basin the well is assigned to.")
    lateral_count: int = Field(
        description="Lateral geometries recorded for this well.",
        json_schema_extra=not_a_figure("A count of geometry rows, not a measured quantity."),
    )
    lateral_length_ft: FigureModel | None = Field(
        description=(
            "Total lateral length, projected into the basin compute CRS. Null where a"
            " conformance rule withholds it; length_method then reads not_served."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_wellbore"},
    )
    compute_crs: str | None = Field(
        description=(
            "CRS the length computation is defined on. Zone-free while length_method is"
            " geodesic, which is why it reads as the storage CRS. Null where no length is"
            " served, because no computation was defined."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_crs_compute_crs"},
    )
    length_method: str = Field(
        description=(
            "How lateral length was measured, from the compute-CRS rule the well's basin names:"
            " geodesic on the WGS84 ellipsoid, or projected into a named CRS. Reads not_served"
            " where a conformance rule withholds the length; links.length_rule names it."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_crs_compute_crs"},
    )
    storage_crs: str = Field(description="CRS geometry is stored in; always EPSG:4326.")
    total_depth_ft: FigureModel | None = Field(
        description="Total wellbore depth as the regulator reported it, with its handle.",
        json_schema_extra={GLOSSARY_KEY: "gt_wellbore"},
    )
    completion_date: date | None = Field(
        description="Most recent completion date on file; not a spud and not first production."
    )
    geometry: list[Geometry] = Field(description="Geometry rows held for this well.")
    surface_point: SurfacePoint | None = Field(description="Surface hole location, if recorded.")
    neighbors_reason: str | None = Field(
        description="Why no neighbour context is offered, where the jurisdiction registers"
        " laterals but the neighbour mart's measured domain does not reach it. Null where"
        " neighbours are served and where none were ever registered."
    )
    type_curve_scope: TypeCurveScope = Field(
        description="Whether a published peer control covers this well, and what it is scoped"
        " to. Served for every well: the section's absence sentence is the publication's own"
        " scope, and a client writing that sentence would be writing a basin name into the"
        " card."
    )
    basin_context: BasinContext | None = Field(
        description="The published boundary answer for this well. Null only where the mart has"
        " not been refreshed since the well landed, which is a pipeline state and not a fact"
        " about the well."
    )
    jurisdiction_name: str | None = Field(
        description="The registered name of the jurisdiction this well is filed with."
    )
    regulator_name: str | None = Field(
        description="The regulator that holds the record, as the registry names it."
    )
    regulator_url: str | None = Field(
        description="The regulator's portal, which is a portal root and not this well's own"
        " record: no per-well URL template is registered for any jurisdiction yet, so a link"
        " labelled as the record for this well would be a lie the size of one click."
    )
    geometry_provenance_rule: str | None = Field(
        description="The rule that says what this jurisdiction's geometry means. Null where"
        " the jurisdiction registers no geometry_provenance decision, which is a registry gap"
        " to be stated rather than another jurisdiction's rule to be inherited."
    )


class TypeCurveScope(BaseModel):
    """What the published control covers, and whether this well is one of its test subjects."""

    model_config = ConfigDict(extra="forbid")

    published: bool = Field(description="Whether any accepted publication is servable at all.")
    held_out: bool = Field(
        description="Whether this well is a test subject of the pinned split set. Only a"
        " held-out subject gets links.type_curve: a control fitted on the well it is compared"
        " against measures its own training data."
    )
    basin: str | None = Field(description="The basin the publication is scoped to.")
    publication_id: str | None = Field(description="The accepted publication in force.")
    eval_vintage: str | None = Field(description="The evaluation vintage it was accepted at.")
    split_set_id: str | None = Field(description="The split set the subject list comes from.")
    detail: str | None = Field(
        description="Why this well has no control, in served words. Null where it has one."
    )


class BasinContext(BaseModel):
    """The published boundary a well's geometry falls in, beside the label the ingest wrote."""

    model_config = ConfigDict(extra="forbid")

    basin_name: str | None = Field(
        description="The published basin polygon the answering geometry falls in."
    )
    basin_class: str = Field(
        description="in_published_boundary, outside_published_boundaries, or no_geometry."
        " Outside is an answer about the boundary set, not a gap: it says the publisher draws"
        " no basin here."
    )
    basin_overlap: int = Field(
        description="How many published basin polygons contain the answering geometry.",
        json_schema_extra=not_a_figure(
            "How many published basin polygons contain this well's answering geometry. A count"
            " of boundary rows, served so a reader can see where the publisher's own polygons"
            " overlap; not a measured petroleum quantity."
        ),
    )
    play_name: list[str] = Field(
        description="Every play polygon the geometry falls in. Plural because plays stack."
    )
    play_class: str = Field(description="plays, or no_play_at_this_location.")
    basin_label_filed: str | None = Field(
        description="The `basin` string on the well row, kept and labelled as what it is: a"
        " scope label from the ingest, not a geological finding."
    )
    label_class: str = Field(
        description="agrees, disagrees, not_labelled, or no_label_to_compare."
    )
    label_agrees: bool | None = Field(
        description="Whether the filed label and the polygon answer agree. Null where there is"
        " nothing to compare."
    )
    boundary_vintage: str | None = Field(description="The boundary row's published vintage.")
    geometry_basis: str = Field(
        description="Which geometry answered: surface, lateral_midpoint, bottomhole, or"
        " no_geometry. Stated because a long lateral can cross a boundary and saying which end"
        " was asked is the difference between a fact and an accident."
    )
    rule_id: str | None = Field(
        description="The basin_context rule that decided this row, where one is registered."
    )
    lineage: dict[str, str] = Field(
        alias="_lineage",
        description="Field path to the derivation handle of the mart run that answered it.",
    )


class StatusHistoryRow(BaseModel):
    """One effective-dated header, as the regulator filed it."""

    model_config = ConfigDict(extra="forbid")

    effective_from: str = Field(
        description="The date this header took effect, on whichever clock basis.clock names."
    )
    status_reported: str | None = Field(description="The status code exactly as filed.")
    status_canonical: str | None = Field(
        description="The class as glasswell maps this code today. Not historical: it is a"
        " read-time join against today's registry, so a superseded vocabulary rule changes"
        " every row at once. Null where no registered vocabulary maps the code."
    )
    status_rule_id: str | None = Field(
        description="The mapping rule that produced the class on this row."
    )


class StatusHistoryBasis(BaseModel):
    """Which clock the dates beside these codes are on, and what follows from that."""

    model_config = ConfigDict(extra="forbid")

    clock: str = Field(
        description="source_valid_time where effective_from is the regulator's own stamp;"
        " load_stamp where it is the vintage of the extract glasswell pulled."
    )
    served: bool = Field(
        description="False on a load stamp: the rows would be a log of when glasswell looked."
    )
    rule_id: str | None = Field(
        description="The rule that decided the clock, where the jurisdiction registers one."
    )
    status_vocabulary_rule: str | None = Field(
        description="The jurisdiction's own status vocabulary rule, which is what an absence"
        " is stated by."
    )
    class_column_label: str = Field(
        description="What the class column is, said in the words it must be headed with."
    )
    class_column_is_historical: bool = Field(
        description="Always false in this release; resolution under the rule clock is next."
    )
    detail: str = Field(description="The decision in one served sentence.")


class StatusHistoryCap(BaseModel):
    """What the cap kept and what it held back, so a short list is never read as a short life."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(
        description="The cap this response was cut at.",
        json_schema_extra=not_a_figure(
            "The cut a status history was taken at. A property of the response, not of the"
            " well: New Mexico holds 15,590 distinct filed effective dates across its"
            " population and its fullest single well carries 15 of them, 248 wells carry more"
            " than ten, and ten is a readable answer with the remainder counted beside it."
        ),
    )
    returned: int = Field(
        description="Rows this response carries.",
        json_schema_extra=not_a_figure("How many status-history rows this response carries."),
    )
    total: int = Field(
        description="Effective-dated headers the well carries at this vintage, whether or not"
        " a history is served for its jurisdiction.",
        json_schema_extra=not_a_figure(
            "How many effective-dated headers the well carries at this vintage. Served so a"
            " short list is never read as a short life; a count of rows in this response's own"
            " population, not a measured petroleum quantity."
        ),
    )
    withheld: int = Field(
        description="Rows the cap held back. Never rows nobody has.",
        json_schema_extra=not_a_figure(
            "Status-history rows the cap held back. Never rows nobody has."
        ),
    )


class WellStatusHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api10: str = Field(
        description="Ten-digit API well number.",
        json_schema_extra={
            GLOSSARY_KEY: "gt_api_10_api_12_api_14",
            **not_a_figure(
                "Identifier. A 10-digit API number is an identity string, not a measurement."
            ),
        },
    )
    state_code: str | None = Field(
        description="API state prefix; an identifier, not a count.",
        json_schema_extra=not_a_figure(
            "FIPS-style state code carried as reported; an identifier, not a quantity."
        ),
    )
    basis: StatusHistoryBasis = Field(description="Which clock these dates are on.")
    history: list[StatusHistoryRow] = Field(
        description="Newest first, capped; `cap` says how many rows the cap held back."
    )
    cap: StatusHistoryCap = Field(description="What the cap kept and what it held back.")


def _neighbours(
    registry: JurisdictionRegistry, state_code: str | None
) -> tuple[bool, str | None, str | None]:
    """Whether the neighbour mart holds subjects here, and the rule or the reason.

    Two registrations, not one. `neighbors_available` says the jurisdiction has laterals to
    offer; a serving `neighbors_scope` rule says the mart's measured envelope and zone set
    reach it. The second missing is a reason the reader gets, not a blank frame.
    """
    row = registry.at_prefix(state_code)
    if row is None or not row.neighbors_available:
        return False, None, None
    rule = row.rule(NEIGHBORS_SCOPE)
    if rule is None:
        return False, None, NEIGHBORS_NOT_COVERED
    return True, rule, None


def _summary(row: dict[str, Any], registry: JurisdictionRegistry) -> dict[str, Any]:
    return {
        "api10": row["api10"],
        "well_name": row["well_name"],
        "operator_name_reported": row["operator_name_reported"],
        "status_canonical": row["status_canonical"],
        # The rule that decided the class, not the one the row's derivation happens to cite:
        # for New Mexico those differ, because the class is a read-time join and the promotion
        # still cites the rule that refuses the mapping.
        "status_vocabulary_rule": registry.rule_for(row["state_code"], STATUS_VOCABULARY),
        "county_code_at_permit": row["county_code_at_permit"],
        "land_unit_label": row["land_unit_label"],
        "spud_date": iso(row["spud_date"]),
        "confidential_flag": row["confidential_flag"],
        "effective_from": iso(row["effective_from"]),
        "geometry_provenance": row["geometry_provenance"],
        "producing": row["producing"],
        "links": {
            "self": f"/v1/wells/{row['api10']}",
            "production": f"/v1/wells/{row['api10']}/production",
        },
    }


def pending_allocation(rule: LeaseReportingRule) -> dict[str, Any]:
    """DIR-3 made visible: a lease-reporting state has no observed well-level series, and an
    empty chart would say the opposite of what is true. The rule is named so a reader can
    resolve it at /v1/conformance."""
    return {
        "code": "production_pending_allocation",
        "detail": (
            f"This well's regulator reports production at the {rule['reporting_level']}"
            f" ({rule['rule_id']}), so no well-level series has been observed. A well-level"
            " figure would be an allocation artifact, and allocation is not served yet; the"
            " well-to-lease keys it will need are already recorded."
        ),
        "pointer": "/production",
    }


def reported_at_pool_grain(rule: LeaseReportingRule) -> dict[str, Any]:
    """DIR-3 one grain the other way from `pending_allocation`.

    A well whose regulator files per completion pool and rolls nothing up has no well-level
    series to be absent from, so `producing` is `unknown` — but it filed, and the three causes
    the field enumerated before this did not include the one that applies. The rule is named so
    a reader can resolve it at /v1/conformance."""
    return {
        "code": "production_reported_at_pool_grain",
        "detail": (
            f"This well's regulator files production at the {rule['reporting_level']} and"
            f" glasswell performs no rollup to the well ({rule['rule_id']}), so no well-level"
            " series has been observed and `producing` is unknown for that reason rather than"
            " because nothing was filed. The pool series is served separately."
        ),
        "pointer": "/producing",
        # On the warning rather than only inside the sentence: a client that had to parse the
        # rule id out of prose is a client that will parse it wrong once.
        "rule_id": rule["rule_id"],
    }


def _held_back_geometry(
    connection, api10: str, *, as_of: date | None = None
) -> tuple[list[dict[str, Any]], list[date]]:
    """Say what the horizontals layer held back for this well, and under which rule."""
    warnings = []
    available_on = []
    for row in rows(connection, _HELD_BACK_GEOMETRY, {"api10": api10, "as_of": as_of}):
        available_on.append(row["available_on"])
        segments = f" ({row['segments']})" if row["segments"] else ""
        warnings.append(
            {
                "code": "geometry_not_promoted",
                "detail": (
                    f"{row['rows']} horizontal geometry rows for this well{segments} were not"
                    f" promoted: {row['reason_code']} under {row['rule_id']}."
                    " They are in /v1/quarantine with their payloads."
                ),
                "pointer": "/geometry",
            }
        )
    context = rows(
        connection, _HELD_BACK_GEOMETRY_VINTAGE, {"api10": api10, "as_of": as_of}
    )[0]
    if context["available_on"] is not None:
        available_on.append(context["available_on"])
    return warnings, available_on


_UNREGISTERED_PRODUCING: dict[str, Any] = {
    "producing_registered": False,
    "producing_streams": [],
    "producing_evidence": [],
    "producing_window_start": None,
    "producing_lease_states": [],
}


def _producing(connection) -> tuple[ProducingPolicy | None, dict[str, Any]]:
    """The policy and everything the class expression binds, resolved once per request.

    The definition is rows, so a registry without them is a state the response describes
    rather than one it crashes on — and rather than one it papers over with a window nobody
    wrote down (R8).
    """
    try:
        policy = load_producing_policy(connection)
    except ProducingPolicyError:
        return None, dict(_UNREGISTERED_PRODUCING)
    return policy, producing_params(connection, policy) | {"producing_registered": True}


def _producing_unregistered(pointer: str) -> dict[str, Any]:
    return {
        "code": "producing_definition_unregistered",
        # Missing rows and an unreadable spec both land here, so the text names the outcome
        # rather than asserting which of the two it was.
        "detail": (
            "The producing classes are not served: this registry does not supply a usable"
            f" {', '.join(PRODUCING_RULE_IDS)} — the rows are absent, not yet in effect, or"
            " carry a spec that could not be read. Whether a well is producing is a definition"
            " with a rationale and an effective date, and without those rows there is nothing"
            " to answer from."
        ),
        "pointer": pointer,
    }


def _type_curve_scope(connection: Any, api10: str) -> dict[str, Any]:
    """Whether a peer control exists for this well, and what it is scoped to.

    Served for every well rather than only for a subject: the section's absence sentence is
    the publication's own scope -- its basin, its evaluation vintage, its split set -- and a
    client that had to say why the section is missing would be writing a `williston` literal
    into the card (N-18). `held_out` decides `links.type_curve` and nothing else does.
    """
    try:
        pin = resolve_pinned_control(connection)
    except UnregisteredArtifact as error:
        return {
            "published": False,
            "held_out": False,
            "basin": None,
            "publication_id": None,
            "eval_vintage": None,
            "split_set_id": None,
            "detail": str(error),
        }
    try:
        instances = subject_origins(pin, api10=api10)
    except UnregisteredArtifact as error:
        return {
            "published": True,
            "held_out": False,
            "basin": pin.basin,
            "publication_id": pin.publication_id,
            "eval_vintage": pin.eval_vintage.isoformat(),
            "split_set_id": pin.split_set_id,
            "detail": str(error),
        }
    return {
        "published": True,
        "held_out": bool(instances),
        "basin": pin.basin,
        "publication_id": pin.publication_id,
        "eval_vintage": pin.eval_vintage.isoformat(),
        "split_set_id": pin.split_set_id,
        "detail": (
            None
            if instances
            else (
                f"The published control is scoped to {pin.basin} and this well is not a test"
                f" subject of split set {pin.split_set_id} at evaluation vintage"
                f" {pin.eval_vintage.isoformat()}. A control fitted on a well it is then"
                " compared against would be measuring its own training data."
            )
        ),
    }


def _basin_block(context: list[dict], api10: str) -> dict[str, Any] | None:
    """The mart's row for this well, with a handle on every line it serves.

    The mart writes a content-addressed derivation on every refresh and the row carries it, so
    each line resolves to the run that produced it, the boundary file it read and the rule it
    was decided under. Absent where the mart has not been refreshed since the well landed,
    which is a pipeline state and not a fact about the well.
    """
    if not context:
        return None
    block = dict(context[0])
    derivation = str(block.pop("derivation_id"))
    selector = identity_selector_term("api10", api10)
    block["_lineage"] = {
        column: format_handle(derivation, f"{selector}&col={column}")
        for column in _BASIN_LINEAGE_COLUMNS
    }
    return block


def _bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if raw is None:
        return None
    parts = raw.split(",")
    if len(parts) != 4:
        raise ProblemError(
            "validation_failed",
            detail="bbox must be minx,miny,maxx,maxy in WGS84",
            errors=[{"pointer": "/query/bbox", "code": "bbox_shape", "detail": "four numbers"}],
        )
    try:
        minx, miny, maxx, maxy = (float(part) for part in parts)
    except ValueError:
        raise ProblemError(
            "validation_failed",
            detail="bbox coordinates must be numbers",
            errors=[{"pointer": "/query/bbox", "code": "bbox_number", "detail": raw}],
        ) from None
    if maxx - minx > BBOX_DEGREE_CAP or maxy - miny > BBOX_DEGREE_CAP:
        raise ProblemError(
            "validation_failed",
            detail=f"bbox is capped at {BBOX_DEGREE_CAP}x{BBOX_DEGREE_CAP} degrees",
            errors=[{"pointer": "/query/bbox", "code": "bbox_cap", "detail": raw}],
        )
    return minx, miny, maxx, maxy


@router.get(
    "/wells",
    operation_id="list_wells",
    summary="List wells",
    description=(
        "The well spine as of a knowledge-time cut, ordered by API-10. Rows are"
        " effective-dated: a status change appends a row rather than updating one, so a"
        " past `as_of` returns the well as it was described then. Filters compose; the"
        " bounding box is a WGS84 envelope capped at four degrees a side."
        " It does not return production — see /v1/wells/{api10}/production."
    ),
    response_model=EnvelopeModel[list[WellSummary]],
    openapi_extra={
        **request_example(query={"limit": 5}),
        **dataset(
            id="wells",
            title="Wells",
            group="wells",
            collection_pointer="",
            row_id=["/api10"],
            detail_operation="get_well",
            # `/producing` is a facet but not yet a default column: the explorer's grid
            # fixture is recorded from a served build, and this branch cannot re-record it,
            # so declaring the column would name one no recorded row carries.
            # `well_type` is here because a "Wells by well type" bucket narrows the grid by it:
            # an applied filter the dataset does not declare renders no chip and cannot be
            # cleared on its own. `geometry_provenance` is here for the same reason: the map
            # legend now counts the classes /v1/wells/status-summary serves, and a reader
            # crossing from one of those counts into the grid arrives on that filter.
            facets=[
                "api10",
                "status",
                "producing",
                "well_type",
                "geometry_provenance",
                "operator",
                "county",
                "state",
                "bbox",
                "q",
            ],
            columns={
                "default": [
                    "/api10",
                    "/well_name",
                    "/operator_name_reported",
                    "/status_canonical",
                    "/county_code_at_permit",
                    "/spud_date",
                ],
                "sort": "/api10",
            },
            intro="nb_dataset_wells",
            order=10,
        ),
        **semantics(
            api10={
                "glossary": "gt_api_10_api_12_api_14",
                "so": (
                    "Resolves the identity spine, exactly: one well or none, never a partial"
                    " match, so a leading fragment of an API number is not a search. It also"
                    " takes the fourteen-digit literal, matched against the API-14 canonical"
                    " recorded for the well rather than trimmed to ten here — which digits of"
                    " an API-14 make the API-10 is an identity rule's declaration, not a"
                    " search behaviour, so a completion this deployment never recorded answers"
                    " with an empty page instead of with a guess. Use `q` to read a list of"
                    " names; use this to name a well."
                ),
            },
            as_of={
                "glossary": "gt_knowledge_time",
                "so": (
                    "Reads the spine as it stood on that knowledge date. A well permitted"
                    " afterwards is absent, and one whose operator changed since answers with"
                    " the older name. It does not filter on when a well was drilled — it"
                    " chooses which version of every row you are looking at."
                ),
            },
            cursor={
                "so": (
                    "Pins the page to the api10 order and to the filters that opened it. Change"
                    " a filter and the cursor is refused rather than quietly re-scoped, so a"
                    " resumed page is the same population you started paging through."
                ),
            },
            limit={
                "so": (
                    "Caps this collection at 1000 a page — higher than the kitchen collections,"
                    " because a wells page is what the map draws. Ask for more and the request"
                    " is rejected rather than trimmed, so a page is never quietly short."
                ),
            },
            status={
                "glossary": "gt_well_status",
                "so": (
                    "Filters on the canonical value rather than the code the state published,"
                    " so `active` here means every source's version of active. What becomes of"
                    " a code the vocabulary does not map is the jurisdiction's own rule: North"
                    " Dakota, Texas and Montana quarantine it out of the spine, New Mexico"
                    " passes it through unclassed. Either way it matches no status here — but"
                    " a passed-through well is still served and still drawn."
                ),
            },
            operator={
                "glossary": "gt_operator_of_record",
                "so": (
                    "Substring-matches the reported spelling. A company that files under"
                    " several spellings needs several searches, and a parent's subsidiaries do"
                    " not roll up — that join is a conformance rule, not a search behaviour."
                ),
            },
            county={
                "glossary": "gt_county_at_permit",
                "so": (
                    "Matches the county on the permit, which is fixed inside the API number and"
                    " never restated. A lateral that produces in the next county still answers"
                    " to the county it was permitted in."
                ),
            },
            state={
                "glossary": "gt_api_10_api_12_api_14",
                "so": (
                    "Matches the API state codes exactly — the first two digits of every"
                    " API-10 in the answer. A set, not one code: repeat it, comma-separate the"
                    " codes, or send `all`, which is evaluated per request — it is every"
                    " jurisdiction the registry holds at the moment you ask, so a link"
                    " carrying it returns a wider population once a further jurisdiction"
                    " registers. A traversal does not widen under way: the cursor is"
                    " fingerprinted over the codes `all` resolved to, so a registration"
                    " between two pages is refused rather than folded in. It is what scopes a"
                    " `/v1/wells/facets` bucket"
                    " link to the jurisdictions the bucket was counted in; without it a county"
                    " or status filter returns every jurisdiction that happens to share the"
                    " code, and with only one it answers a combined bucket with one state's"
                    " rows."
                ),
            },
            well_type={
                "so": (
                    "Matches the well type code exactly as the regulator filed it — SWD, WI,"
                    " OG — with no decode and no classing, the same verbatim code the well"
                    " record serves. Which codes make up a class is a conformance rule's"
                    " declaration (cr_nd_well_type_disposal_1 for ND injection), so scoping"
                    " the spine to a class means asking for each code the rule names."
                ),
            },
            geometry_provenance={
                "so": (
                    "Matches the provenance class of the well's recorded geometry — surface,"
                    " bottomhole, lateral or survey_trace — verbatim, with no decode: the"
                    " same canonical geom_type the tiles serve as geometry_provenance under"
                    " the jurisdiction's provenance rule. A well matches when any of its"
                    " geometry"
                    " carries the class, and the payload column lists every class it carries,"
                    " so a match still shows what else the well holds."
                ),
            },
            producing={
                "glossary": "gt_conformance_rule",
                "so": (
                    "Scopes the spine by whether a well is actually producing, which is not"
                    " what its status says. `active` is the regulator's word about a permit;"
                    " this is a reading of the production filings, and the two disagree in"
                    " both directions — on the 2026-08 load 896 wells North Dakota calls"
                    " inactive filed a positive hydrocarbon month inside the window, and 437"
                    " it calls active filed nothing but zeros. Combine it with `status` to ask"
                    " the Active-Producing question specifically. `unknown` is a real answer"
                    " and not a residue: it is where the well filed nothing, where the"
                    " regulator withheld the months, and where the jurisdiction reports at the"
                    " lease so no well-level series exists at all. A value outside the three"
                    " is refused rather than returning an empty page, because the vocabulary"
                    " is closed — cr_producing_window_1, cr_producing_streams_1 and"
                    " cr_producing_evidence_1 define it, and they are what a supersession"
                    " would change."
                ),
            },
            bbox={
                "glossary": "gt_crs_compute_crs",
                "so": (
                    "WGS84 degrees, rejected above four a side. It matches a well any of whose"
                    " recorded geometry — surface, bottomhole or lateral — overlaps the box, so"
                    " a lateral clipping one corner is a hit and a surface hole outside it is"
                    " not a miss."
                ),
            },
            q={
                "glossary": "gt_well_name",
                "so": (
                    "Substring-matches the name the operator filed. Names repeat across"
                    " operators and change with the lease, so this narrows a list to read; it"
                    " does not identify a well. Use api10 for that."
                ),
            },
        ),
    },
    responses=problem_responses(
        "validation_failed", "cursor_malformed", "cursor_query_mismatch", "service_degraded"
    ),
)
def list_wells(
    request: Request,
    connection: Connection,
    as_of: AsOf = None,
    cursor: Cursor = None,
    limit: WellsLimit = DEFAULT_LIMIT,
    api10: Annotated[
        str | None,
        Query(
            description=(
                "Ten-digit API well number, or the fourteen-digit literal recorded for it."
                " Matched whole, never as a fragment."
            ),
            pattern=API_IDENTITY_PATTERN,
        ),
    ] = None,
    status: Annotated[
        str | None, Query(description="Canonical status, e.g. active or plugged.")
    ] = None,
    operator: Annotated[
        str | None, Query(description="Case-insensitive substring of the reported operator.")
    ] = None,
    county: Annotated[
        str | None, Query(description="County code as recorded at permit.")
    ] = None,
    # Added for `/v1/wells/facets`: a facet bucket is counted within a set of jurisdictions, so
    # the link it publishes has to narrow to that set or it answers with a different
    # population. Without it `?county=003` returns Texas county 003 and North Dakota county 003
    # together; with only one code it answers a two-state bucket with one state's rows.
    state: Annotated[
        list[StateTerm] | None,
        Query(
            description=(
                "API state codes, e.g. 33 for North Dakota. Repeat the parameter"
                " (`?state=33&state=42`), comma-separate the codes (`?state=33,42`), or send"
                " `all` for every registered jurisdiction. Matched exactly."
            ),
        ),
    ] = None,
    well_type: Annotated[
        str | None,
        Query(description="Well type code exactly as the source reported it, e.g. SWD."),
    ] = None,
    geometry_provenance: Annotated[
        str | None,
        Query(
            description=(
                "Provenance class of the well's recorded geometry, verbatim, e.g. lateral"
                " or survey_trace."
            )
        ),
    ] = None,
    producing: Annotated[
        str | None,
        Query(description="producing, not_producing or unknown — the class, not the status."),
    ] = None,
    bbox: Annotated[
        str | None, Query(description="minx,miny,maxx,maxy in WGS84; capped at 4 degrees.")
    ] = None,
    q: Annotated[str | None, Query(description="Case-insensitive substring of well name.")] = None,
) -> JSONResponse:
    # Normalised before the fingerprint, so `?state=33,42` and `?state=42&state=33` are one
    # query rather than three cursors that refuse each other's pages. `all` is resolved here
    # too, and against the registry rather than left as the word: it is evaluated per request,
    # so a jurisdiction registering mid-traversal would otherwise hand the reader a second page
    # from a larger population than the first, under a cursor whose fingerprint said `all`
    # either way. Resolved, the registration invalidates the cursor instead, which is the
    # refusal cursor_query_mismatch exists to make.
    registry = jurisdictions(connection)
    requested = state_set(state) if state is not None else ()
    if state is None:
        scoped_states = None
    elif requested is None:
        scoped_states = sorted(registry.by_prefix)
    else:
        scoped_states = list(requested)
    filters = {
        "as_of": as_of,
        "api10": api10,
        "status": status,
        "operator": operator,
        "county": county,
        "state": scoped_states,
        "well_type": well_type,
        "geometry_provenance": geometry_provenance,
        "producing": producing,
        "bbox": bbox,
        "q": q,
    }
    if producing is not None and producing not in PRODUCING_CLASSES:
        raise ProblemError(
            "validation_failed",
            detail=f"producing must be one of {', '.join(PRODUCING_CLASSES)}",
            errors=[
                {
                    "pointer": "/query/producing",
                    "code": "producing_class_unknown",
                    "detail": (
                        f"{producing!r} is not a producing class; the classes are"
                        f" {', '.join(PRODUCING_CLASSES)}, defined by"
                        f" {', '.join(PRODUCING_RULE_IDS)}"
                    ),
                }
            ],
        )
    fingerprint = query_fingerprint(filters)
    envelope = _bbox(bbox)
    policy, producing_bindings = _producing(connection)
    if producing is not None and policy is None:
        raise ProblemError(
            "service_degraded",
            detail=(
                "the producing definition is not registered, so the spine cannot be scoped by"
                f" it; {', '.join(PRODUCING_RULE_IDS)} are missing from the rule registry"
            ),
        )
    params: dict[str, Any] = {"as_of": as_of, "limit": limit + 1, **producing_bindings}
    clauses = [RANKED_WELLS_PRODUCING]
    if api10 is not None:
        # The two literal lengths are disjoint, so one bound value needs no branch here.
        clauses.append("and (api10 = %(api10)s or api14 = %(api10)s)")
        params["api10"] = api10
    if status is not None:
        clauses.append(f"and {resolved_status('ranked')} = %(status)s")
        params["status"] = status
    if operator is not None:
        clauses.append("and operator_name_reported ilike '%%' || %(operator)s || '%%'")
        params["operator"] = operator
    if county is not None:
        clauses.append("and county_code_at_permit = %(county)s")
        params["county"] = county
    if state is not None:
        clauses.append("and state_code = any(%(state)s)")
        params["state"] = scoped_states
    if well_type is not None:
        clauses.append("and well_type_reported = %(well_type)s")
        params["well_type"] = well_type
    if geometry_provenance is not None:
        clauses.append(
            "and exists (select 1 from canonical.well_spatial s"
            " join lineage.manifests sm on sm.manifest_id = s.source_manifest_id"
            " join lineage.derivations sd on sd.derivation_id = s.derivation_id"
            " where s.api10 = ranked.api10"
            " and s.geom_type = %(geometry_provenance)s"
            " and (%(as_of)s::date is null or sm.fetch_vintage <= %(as_of)s::date)"
            " and (%(as_of)s::date is null or sd.created_vintage is null"
            "      or sd.created_vintage <= %(as_of)s::date))"
        )
        params["geometry_provenance"] = geometry_provenance
    if producing is not None:
        clauses.append(f"and {_PRODUCING_CLASS} = %(producing)s")
        params["producing"] = producing
    if q is not None:
        clauses.append("and well_name ilike '%%' || %(q)s || '%%'")
        params["q"] = q
    if envelope is not None:
        clauses.append(
            "and exists (select 1 from canonical.well_spatial s"
            " join lineage.manifests sm on sm.manifest_id = s.source_manifest_id"
            " join lineage.derivations sd on sd.derivation_id = s.derivation_id"
            " where s.api10 = ranked.api10"
            " and s.geom && st_makeenvelope(%(minx)s, %(miny)s, %(maxx)s, %(maxy)s, 4326)"
            " and (%(as_of)s::date is null or sm.fetch_vintage <= %(as_of)s::date)"
            " and (%(as_of)s::date is null or sd.created_vintage is null"
            "      or sd.created_vintage <= %(as_of)s::date))"
        )
        params |= dict(zip(("minx", "miny", "maxx", "maxy"), envelope, strict=True))
    if cursor is not None:
        params["after"] = decode_cursor(cursor, fingerprint=fingerprint).key
        clauses.append("and api10 > %(after)s")
    clauses.append("order by api10 limit %(limit)s")

    found = rows(connection, "\n".join(clauses), params)
    items, has_more = page(found, limit)
    next_cursor = (
        encode_cursor(
            key=items[-1]["api10"],
            tiebreak=items[-1]["api10"],
            as_of=as_of,
            fingerprint=fingerprint,
        )
        if has_more and items
        else None
    )
    return enveloped(
        request,
        [_summary(row, registry) for row in items],
        as_of=as_of,
        as_of_requested=iso(as_of) or "latest",
        next_cursor=next_cursor,
        links={
            "next": next_link("/v1/wells", filters | {"limit": limit}, next_cursor)
            if next_cursor
            else None
        },
    )


class StatusCount(BaseModel):
    status: str = Field(
        description=(
            "Canonical status the wells in this bucket carry. Never null: a well the source"
            " reported no status for is counted in `unmapped_wells`, not here."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_well_status"},
    )
    wells: FigureModel = Field(
        description="Wells in this class inside the box, with the handle the count resolves by."
    )


class BasinStatusCounts(BaseModel):
    basin: str | None = Field(description="Basin the wells are assigned to; null where none is.")
    state_code: str | None = Field(
        description="API state code the wells were promoted under — 33 in ND, 42 in TX.",
        json_schema_extra=not_a_figure(
            "API state code on a per-basin summary row; an identifier, not a quantity."
        ),
    )
    status_vocabulary_rule: str | None = Field(
        description=(
            "Conformance rule that mapped this jurisdiction's reported codes onto the canonical"
            " vocabulary. Null where no rule is registered for the state, which is disclosed as"
            " a warning rather than answered with another state's rule."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )
    wells: FigureModel = Field(description="Wells in this basin inside the box.")
    unmapped_wells: FigureModel | None = Field(
        description="Wells here whose source reported no status; absent when there are none."
    )
    statuses: list[StatusCount] = Field(description="One entry per class present, largest first.")


class ProvenanceCount(BaseModel):
    geometry_provenance: str = Field(
        description=(
            "Provenance class, verbatim canonical geom_type under the jurisdiction's"
            " provenance rule: surface, bottomhole, lateral or survey_trace."
        ),
    )
    wells: FigureModel = Field(
        description="Wells in the box with recorded geometry of this class, with its handle."
    )


class WellTypeCount(BaseModel):
    well_type_reported: str = Field(
        description="Well type code exactly as the source filed it — no decode, no classing."
    )
    wells: FigureModel = Field(description="Wells filed under this code inside the box.")


class ProducingCount(BaseModel):
    producing: str = Field(
        description="producing, not_producing or unknown, as the producing rules define them.",
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )
    wells: FigureModel = Field(
        description="Wells of this class inside the box, with the handle the count resolves by."
    )


class ProducingWindow(BaseModel):
    months: int = Field(
        description="How many months the window spans, from cr_producing_window_1.",
        json_schema_extra=not_a_figure(
            "Length of the producing window in months, read from cr_producing_window_1. A"
            " parameter of the classing, not an observation it stands behind."
        ),
    )
    from_: str = Field(
        alias="from",
        description="First production month the window admits, inclusive.",
    )
    to: str = Field(description="Newest production month anybody has filed; the window's anchor.")
    streams: list[str] = Field(
        description="Streams that count as producing, from cr_producing_streams_1. Water is"
        " excluded: it is a byproduct, not evidence of a hydrocarbon well."
    )
    liquids_basis: str = Field(
        description=(
            "What the liquids figure behind these classes is composed of. ND reports oil plus"
            " condensate as one column (cr_nd_liquids_policy_1), and the basis is stated here"
            " because it is stated wherever one of these numbers appears."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_stream"},
    )


class WellStatusSummary(BaseModel):
    bbox: str = Field(
        description="The box the counts were taken over, normalised to minx,miny,maxx,maxy."
    )
    wells: FigureModel | None = Field(
        description=(
            "Every well in the box, mapped and unmapped together. Null when the box holds none —"
            " a class no well is in has no count, and neither does an empty box."
        )
    )
    unmapped_wells: FigureModel | None = Field(
        description=(
            "Wells whose source reported no status at all. Its own bucket, never added to a"
            " class — an absence is not a value, and in the 2026-08-20 Texas load 65,685 wells"
            " are in it, which is more than any single class it could have been folded into."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_well_status"},
    )
    statuses: list[StatusCount] = Field(
        description="One entry per canonical class present in the box, largest first."
    )
    basins: list[BasinStatusCounts] = Field(
        description="The same counts split by basin and jurisdiction, ordered by basin."
    )
    geometry_provenance: list[ProvenanceCount] = Field(
        description=(
            "Wells in the box per provenance class of their recorded geometry, largest"
            " first. Classes overlap — a well with a surface hole and a lateral is in both —"
            " so these do not sum to `wells`. Counted over the geometry itself, which is not"
            " effective-dated, so a geometry whose well row is absent at the vintage still"
            " counts here and is disclosed by the orphan warning."
        ),
    )
    well_types: list[WellTypeCount] = Field(
        description=(
            "Wells per reported well type code, verbatim, largest first. A well whose"
            " source reported no type is in no row here — absent, not zero — and is still"
            " counted in `wells`."
        ),
    )
    producing: list[ProducingCount] = Field(
        description=(
            "The same box classed by whether each well is actually producing, largest first."
            " Disjoint and exhaustive over the wells with a spine row, so unlike the"
            " provenance classes these do sum to `wells`. A well the regulator calls active"
            " can be in any of the three: the classes are asked of the production filings, not"
            " of the status. Absent entirely where the definition is not registered."
        ),
    )
    producing_window: ProducingWindow | None = Field(
        description=(
            "The window the classes were judged over and the streams that counted, so a"
            " producing number is never read without the definition that produced it. Null"
            " where the definition is not registered or no production has been loaded."
        ),
    )
    producing_rules: list[str] = Field(
        description="The rules that define producing here; each one is linked.",
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )
    vocabulary_rules: list[str] = Field(
        description="Every status vocabulary rule that shaped these counts; each one is linked.",
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )


def _selector_term(name: str, value: str | None) -> str:
    return f"{name}_null=1" if value is None else identity_selector_term(name, value)


def _refuse_bbox(code: str, detail: str, raw: str) -> ProblemError:
    return ProblemError(
        "validation_failed",
        detail=detail,
        errors=[{"pointer": "/query/bbox", "code": code, "detail": raw}],
    )


def _status_bbox(raw: str) -> tuple[float, float, float, float]:
    """The summary's own box: no degree cap, and every way it can be wrong is named.

    `/v1/wells` caps its box at four degrees because it pages rows; this one returns at most a
    row per class per basin however wide the box is, and a cap here would recreate the defect
    it exists to fix — a legend that stops answering as the viewport grows.
    """
    parts = raw.split(",")
    if len(parts) != BBOX_PARTS:
        raise _refuse_bbox("bbox_shape", "bbox must be minx,miny,maxx,maxy in WGS84", raw)
    try:
        minx, miny, maxx, maxy = (float(part) for part in parts)
    except ValueError:
        raise _refuse_bbox("bbox_number", "bbox coordinates must be numbers", raw) from None
    if not (-LON_LIMIT <= minx <= LON_LIMIT and -LON_LIMIT <= maxx <= LON_LIMIT):
        raise _refuse_bbox("bbox_range", f"longitudes must be within ±{LON_LIMIT:g}", raw)
    if not (-LAT_LIMIT <= miny <= LAT_LIMIT and -LAT_LIMIT <= maxy <= LAT_LIMIT):
        raise _refuse_bbox("bbox_range", f"latitudes must be within ±{LAT_LIMIT:g}", raw)
    if minx > maxx or miny > maxy:
        raise _refuse_bbox(
            "bbox_order",
            "bbox must read minx,miny,maxx,maxy; a box that crosses the antimeridian is two"
            " boxes and is asked for as two requests",
            raw,
        )
    return minx, miny, maxx, maxy


def _rendered_bbox(envelope: tuple[float, float, float, float], separator: str) -> str:
    """The box, rendered so it names the box the query ran over — everywhere it identifies it.

    `repr` is the shortest string that round-trips to the same float; `%g` is six significant
    digits, which at a three-digit longitude is three decimals, about 76 m. Under `%g` two
    viewports 0.0003 degrees apart collapsed to one echo and one derivation handle while
    disagreeing on the count, and links.wells named a box that returned no rows under a
    summary reporting one (gate-wss BLOCK-1). The selector charset (SB-07 §2.1) admits `.`,
    `-`, `+` and `e`, so a repr is selector-safe; NaN and infinity never reach here because
    the range guard rejects them first.
    """
    return separator.join(repr(value) for value in envelope)


def _count(found: list[dict[str, Any]], *, selector: str) -> Figure | None:
    """Absent, not zero: a class the box does not contain has no count and no derivation."""
    if not found:
        return None
    return figure(
        str(sum(row["wells"] for row in found)),
        unit=COUNT_UNIT,
        derivation=max(row["derivation_id"] for row in found),
        selector=selector,
    )


def _classes(found: list[dict[str, Any]], *, box: str, scope: str = "") -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in found:
        if row["status_canonical"] is not None:
            grouped.setdefault(row["status_canonical"], []).append(row)
    ordered = sorted(
        grouped.items(), key=lambda item: (-sum(row["wells"] for row in item[1]), item[0])
    )
    return [
        {
            "status": status,
            "wells": _count(
                group,
                selector=f"col=wells&{_selector_term('status', status)}{scope}&bbox={box}",
            ),
        }
        for status, group in ordered
    ]


def _provenance_classes(found: list[dict[str, Any]], *, box: str) -> list[dict[str, Any]]:
    ordered = sorted(found, key=lambda row: (-row["wells"], row["geometry_provenance"]))
    return [
        {
            "geometry_provenance": row["geometry_provenance"],
            "wells": figure(
                str(row["wells"]),
                unit=COUNT_UNIT,
                derivation=row["derivation_id"],
                selector=(
                    f"col=wells&{_selector_term('geometry_provenance', row['geometry_provenance'])}"
                    f"&bbox={box}"
                ),
            ),
        }
        for row in ordered
    ]


def _well_types(found: list[dict[str, Any]], *, box: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in found:
        if row["well_type_reported"] is not None:
            grouped.setdefault(row["well_type_reported"], []).append(row)
    ordered = sorted(
        grouped.items(), key=lambda item: (-sum(row["wells"] for row in item[1]), item[0])
    )
    return [
        {
            "well_type_reported": code,
            "wells": _count(
                group, selector=f"col=wells&{_selector_term('well_type', code)}&bbox={box}"
            ),
        }
        for code, group in ordered
    ]


def _producing_classes(found: list[dict[str, Any]], *, box: str) -> list[dict[str, Any]]:
    """Ordered by the vocabulary, not by size: the three classes read as a scale, and a legend
    that reshuffles them between viewports is harder to read than one that does not."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in found:
        if row["producing"] is not None:
            grouped.setdefault(row["producing"], []).append(row)
    return [
        {
            "producing": name,
            "wells": _count(grouped[name], selector=f"col=wells&producing={name}&bbox={box}"),
        }
        for name in PRODUCING_CLASSES
        if name in grouped
    ]


def _producing_window(
    connection, policy: ProducingPolicy | None
) -> dict[str, Any] | None:
    if policy is None:
        return None
    anchor = anchor_month(connection, policy)
    start = window_start(anchor, policy)
    if anchor is None or start is None:
        return None
    return {
        "months": policy.window_months,
        "from": iso(start),
        "to": iso(anchor),
        "streams": list(policy.streams),
        "liquids_basis": policy.liquids_basis,
    }


def _basins(
    found: list[dict[str, Any]], *, box: str, registry: JurisdictionRegistry
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str | None, str | None], list[dict[str, Any]]] = {}
    for row in found:
        grouped.setdefault((row["basin"], row["state_code"]), []).append(row)
    summaries = []
    for (basin, state_code), group in sorted(
        grouped.items(), key=lambda item: (item[0][0] or "", item[0][1] or "")
    ):
        scope = f"&{_selector_term('basin', basin)}&{_selector_term('state', state_code)}"
        summaries.append(
            {
                "basin": basin,
                "state_code": state_code,
                "status_vocabulary_rule": registry.rule_for(state_code, STATUS_VOCABULARY),
                "wells": _count(group, selector=f"col=wells{scope}&bbox={box}"),
                "unmapped_wells": _count(
                    [row for row in group if row["status_canonical"] is None],
                    selector=f"col=unmapped_wells{scope}&bbox={box}",
                ),
                "statuses": _classes(group, box=box, scope=scope),
            }
        )
    return summaries


def _summary_labels(basins: list[dict[str, Any]]) -> dict[str, str]:
    """One key per basin actually present: `web/src/api/envelope.ts` looks a pointer up by
    exact match, so a `/basins/*/…` key resolves for nobody (the same rule as _pool_labels)."""
    return STATUS_SUMMARY_LABELS | {
        pointer: term
        for index in range(len(basins))
        for pointer, term in (
            (f"/basins/{index}/statuses", "gt_well_status"),
            (f"/basins/{index}/unmapped_wells", "gt_well_status"),
            (f"/basins/{index}/status_vocabulary_rule", "gt_conformance_rule"),
        )
    }


def _handles(node: Any) -> int:
    """How many handles `links.explain` is being asked to carry, counted by the walk that
    builds it — a count taken any other way can disagree with the link about truncation."""
    return len(distinct_handles(collect_handles(node)))


def _summary_warnings(
    counted: list[dict[str, Any]],
    *,
    orphans: int,
    states: list[str],
    handles: int,
    producing_registered: bool,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if not producing_registered:
        warnings.append(_producing_unregistered("/producing"))
    if handles > MAX_HANDLES:
        warnings.append(
            {
                "code": "explain_link_truncated",
                "detail": (
                    f"This box produced {handles} counts and links.explain carries the first"
                    f" {MAX_HANDLES} handles, so {handles - MAX_HANDLES} are absent from it."
                    " Every count still resolves on its own: read the count's `d` and call"
                    " /v1/explain?h=<d>&depth=full. The cap is /v1/explain's own"
                    " (SB-07 §9.4), not this operation's."
                ),
                "pointer": "/basins",
            }
        )
    if orphans:
        subject, verb, pronoun = (
            ("geometry", "has", "it is") if orphans == 1 else ("geometries", "have", "they are")
        )
        warnings.append(
            {
                "code": "geometry_without_a_well_row",
                "detail": (
                    f"{orphans} {subject} in this box {verb} no well row at this vintage, so"
                    f" {pronoun} in no class and in no total here. That is not a well with no"
                    " status — a different fact, counted in unmapped_wells — and the geometry"
                    " still draws on the map."
                ),
                "pointer": "/wells",
            }
        )
    if len({row["derivation_id"] for row in counted}) > 1:
        warnings.append(
            {
                "code": "aggregate_spans_derivations",
                "detail": (
                    "More than one derivation promoted the wells in this box. Every count is"
                    " over rows the box selected, and its response derivation cites every"
                    " contributing promotion; links.explain resolves the complete input set."
                ),
                "pointer": "/wells",
            }
        )
    if states:
        warnings.append(
            {
                "code": "status_vocabulary_unregistered",
                "detail": (
                    f"No status vocabulary rule is registered for state code(s)"
                    f" {', '.join(states)}, so their rows name none. The counts are the"
                    " canonical values as promoted; the rule that produced them is not"
                    " citable here until it is registered (R8)."
                ),
                "pointer": "/basins",
            }
        )
    return warnings


@router.get(
    "/wells/status-summary",
    operation_id="get_well_status_summary",
    summary="Well status counts for a box",
    description=(
        "How many wells of each canonical status have geometry inside a bounding box, as of a"
        " knowledge-time cut. This is the count a map legend states, asked of the data rather"
        " than of what a renderer drew: a tile pyramid thins points as it zooms out and a"
        " symbology withdraws its low-salience classes, so a count taken from drawn features"
        " falls exactly as the viewed area grows. This one does not move with zoom, with"
        " styling or with which tiles have arrived."
        " The population is wells whose recorded geometry — surface, bottomhole or lateral —"
        " intersects the box, which is the same population `/v1/wells?bbox=` pages, and a well"
        " with no geometry at all is in no viewport and in no count here. The box is closed:"
        " a well exactly on the edge is inside it. There is no degree cap, because the answer"
        " is bounded by the status vocabulary rather than by the population; `links.wells` is"
        " published only where the box is inside the collection's own four-degree cap."
        " Every count is a figure with a derivation handle over the rows it counted, so a"
        " legend number resolves at /v1/explain to the government file the statuses came from."
        " The box a handle names is the box the query ran over, at full precision — two"
        " viewports a metre apart are two handles. Because each distinct box persists exact"
        " response evidence, this operation is capped"
        " at 30 requests per principal per UTC minute. Where a box produces more counts than"
        " /v1/explain accepts handles in one call, `links.explain` carries as many as it can"
        " and a warning says exactly how many it left out; each count still resolves alone."
        " A class no well in the box carries is absent rather than zero. Wells whose source"
        " reported no status are their own bucket, `unmapped_wells`, and are never added to a"
        " class — in the 2026-08-20 Texas load 65,685 wells are in it, which is more than any"
        " class it could have been folded into. Counts are split per basin with the vocabulary"
        " rule that mapped that jurisdiction's codes, because a status class means what its"
        " rule says it means and the rules travel with the counts. The same box is classed two"
        " more ways: per provenance of the recorded geometry — canonical geom_type verbatim,"
        " under the jurisdiction's classing rule — and per reported well type code, verbatim."
        " Both are"
        " figures with handles, so a coverage statement — how many wells are traced, how many"
        " filed under a disposal code — derives from this endpoint rather than from a pinned"
        " constant. Provenance classes overlap where a well holds several geometry kinds, and"
        " they are counted over the geometry itself, which is not effective-dated, so they do"
        " not move with as_of. It does not return the wells themselves — see /v1/wells."
    ),
    response_model=EnvelopeModel[WellStatusSummary],
    openapi_extra={
        **request_example(query={"bbox": EXAMPLE_BBOX}),
        **semantics(
            bbox={
                "glossary": "gt_crs_compute_crs",
                "so": (
                    "WGS84 degrees, and the only scope this endpoint has — it is required, so a"
                    " count always says which box it is a count of. It matches a well any of"
                    " whose recorded geometry overlaps the box, so a lateral crossing one corner"
                    " is counted while its surface hole sits outside. Uncapped, unlike the"
                    " collection's: a whole-state box is the case the endpoint exists for."
                ),
            },
            as_of={
                "glossary": "gt_knowledge_time",
                "so": (
                    "Counts the classes as they were described on that knowledge date, not the"
                    " wells drilled by then. A status restatement appends a row, so an earlier"
                    " as_of returns the earlier class and the totals move between them; a well"
                    " whose spine row is later than the date is counted in no class and"
                    " disclosed as geometry without a well row."
                ),
            },
            explain={
                "glossary": "gt_derivation_handle",
                "so": (
                    "Inlines the chain behind every count under `_explain`, which is the one"
                    " surface where following each `d` by hand is impractical: a wide box"
                    " produces a count per class per basin, and each is a separate call."
                    " Where there are more counts than one /v1/explain call carries handles,"
                    " the response says how many it left out rather than trimming quietly."
                ),
            },
            explain_depth={
                "glossary": "gt_derivation_handle",
                "so": (
                    "A count resolves to the status promotion and the file the statuses came"
                    " from, so three levels reaches the manifest here. Raising it costs one"
                    " graph read per level per count, which on this operation is the widest"
                    " multiplier on the surface."
                ),
            },
        ),
    },
    responses=problem_responses("validation_failed", "rate_limited", "service_degraded"),
)
def get_well_status_summary(
    request: Request,
    connection: Connection,
    principal: Principal,
    bbox: Annotated[
        str, Query(description="minx,miny,maxx,maxy in WGS84. Required; there is no cap.")
    ],
    explain: ExplainEffect,
    as_of: AsOf = None,
) -> JSONResponse:
    envelope = _status_bbox(bbox)
    consume_rate_limit(
        connection,
        principal,
        operation="get_well_status_summary",
        limit=STATUS_SUMMARY_REQUESTS_PER_MINUTE,
    )
    registry = jurisdictions(connection)
    policy, producing_bindings = _producing(connection)
    found = rows(
        connection,
        STATUS_SUMMARY_SQL,
        dict(zip(("minx", "miny", "maxx", "maxy"), envelope, strict=True))
        | {"as_of": as_of}
        | producing_bindings,
    )
    counted = [row for row in found if not row["no_well_row"]]
    orphans = sum(row["wells"] for row in found if row["no_well_row"])
    classed = rows(
        connection,
        PROVENANCE_SUMMARY_SQL,
        dict(zip(("minx", "miny", "maxx", "maxy"), envelope, strict=True)),
    )
    box = _rendered_bbox(envelope, ",")
    selector_box = _rendered_bbox(envelope, ":")
    basins = _basins(counted, box=selector_box, registry=registry)
    unregistered = sorted(
        {
            row["state_code"] or "unassigned"
            for row in counted
            if not registry.rule_for(row["state_code"], STATUS_VOCABULARY)
        }
    )
    rules = sorted({rule for row in basins if (rule := row["status_vocabulary_rule"])})
    # One provenance rule per state actually in the box: geom_type is served verbatim, but the
    # row that legislates that is per source, so a two-state box cites two.
    # Only what is registered. Texas has no geometry-provenance rule, and the ND default it
    # used to inherit put a rule about North Dakota geometry on a Texas box (R-4).
    provenance_rules = sorted(
        {
            rule
            for row in counted
            if (rule := registry.rule_for(row["state_code"], GEOMETRY_PROVENANCE))
        }
    ) if classed else []
    response_rules = sorted({*rules, *provenance_rules})
    data = {
        "bbox": box,
        "wells": _count(counted, selector=f"col=wells&bbox={selector_box}"),
        "unmapped_wells": _count(
            [row for row in counted if row["status_canonical"] is None],
            selector=f"col=unmapped_wells&bbox={selector_box}",
        ),
        "statuses": _classes(counted, box=selector_box),
        "basins": basins,
        "geometry_provenance": _provenance_classes(classed, box=selector_box),
        "well_types": _well_types(counted, box=selector_box),
        "producing": _producing_classes(counted, box=selector_box),
        "producing_window": _producing_window(connection, policy),
        "producing_rules": sorted(PRODUCING_RULE_IDS) if policy else [],
        "vocabulary_rules": rules,
    }
    data = register_response_figures(
        connection,
        data,
        dataset="api.well_status_summary",
        operation_id="get_well_status_summary",
        locator=request.url.path,
        partition={"bbox": selector_box, "as_of": iso(as_of) or "latest"},
        input_derivations=[
            derivation_id
            for row in [*counted, *classed]
            for derivation_id in row["derivation_ids"]
        ],
        correlation_id=request.state.request_id,
        rule_ids=response_rules,
    )
    links = {rule: f"/v1/conformance/{rule}" for rule in rules}
    links |= {rule: f"/v1/conformance/{rule}" for rule in provenance_rules}
    if policy:
        links |= {rule: f"/v1/conformance/{rule}" for rule in PRODUCING_RULE_IDS}
    minx, miny, maxx, maxy = envelope
    if maxx - minx <= BBOX_DEGREE_CAP and maxy - miny <= BBOX_DEGREE_CAP:
        links["wells"] = f"/v1/wells?bbox={box}"
    return enveloped(
        request,
        data,
        as_of=max((row["effective_from"] for row in counted), default=None),
        as_of_requested=iso(as_of) or "latest",
        labels=_summary_labels(basins),
        warnings=_summary_warnings(
            counted,
            orphans=orphans,
            states=unregistered,
            handles=_handles(data),
            producing_registered=policy is not None,
        ),
        links=links,
        explain=inline_for(connection, explain),
    )


class CohortTotals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oil_bbl: FigureModel | None = Field(
        description="Cohort liquids total; null where no well in the cohort filed one.",
        json_schema_extra={GLOSSARY_KEY: "gt_liquids_policy"},
    )
    gas_mcf: FigureModel | None = Field(
        description="Cohort gas total.", json_schema_extra={GLOSSARY_KEY: "gt_stream"}
    )
    water_bbl: FigureModel | None = Field(
        description="Cohort produced-water total.",
        json_schema_extra={GLOSSARY_KEY: "gt_stream"},
    )


class VintageCohort(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cohort_year: int | None = Field(
        description="The year that identifies this cohort; null for the no-key cohort.",
        json_schema_extra=not_a_figure(COHORT_YEAR_REASON),
    )
    cohort_key_semantics: str = Field(
        description="spud_year, or no_spud_date where the regulator published none."
    )
    wells: FigureModel = Field(
        description="Wells in the cohort.",
        json_schema_extra={GLOSSARY_KEY: "gt_vintage_well_vintage"},
    )
    wells_with_a_filed_month: FigureModel = Field(
        description=(
            "Wells in the cohort whose record admits at least one month into these totals, per"
            " cr_nd_vintage_cohort_1's support_measure. Not the producing classification of"
            " cr_producing_window_1, which asks whether a well is producing now."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_cumulative_production"},
    )
    cumulative: CohortTotals = Field(description="Cohort totals per stream.")


class PopulationScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    states_served: list[str] = Field(
        description="API state prefixes in this population.",
        json_schema_extra=not_a_figure(POPULATION_STATE_REASON),
    )
    basin_complete: bool = Field(description="Whether the population spans the whole basin.")
    detail: str = Field(description="What the truncation means for a basin-level reading.")


class SpacingAssumption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applies: bool = Field(description="Whether a spacing assumption underlies these figures.")
    reason: str = Field(description="Why it does or does not apply (Protocol 4D).")


class SupportDistribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scale: str = Field(description="Which support scale the bands are, and why this one.")
    classes: dict[str, int] = Field(description="How many cohorts fall in each support band.")


class WellVintageCohorts(BaseModel):
    cohort_basis: str = Field(description="Which year the cohort key is, per its rule.")
    cohort_key_rule: str = Field(
        description="The conformance rule that chose the key.",
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )
    snapshot_vintage: date = Field(
        description="Knowledge vintage of the cumulative mart the totals were read from.",
        json_schema_extra={GLOSSARY_KEY: "gt_report_vintage"},
    )
    spud_dates_read_at: date | None = Field(
        description="Knowledge vintage the cohort key itself was read at.",
        json_schema_extra={GLOSSARY_KEY: "gt_report_vintage"},
    )
    population_scope: PopulationScope = Field(description="What this population does not cover.")
    spacing_assumption: SpacingAssumption = Field(description="Protocol 4D, stated not omitted.")
    support_distribution: SupportDistribution = Field(
        description="Protocol 4D's support statement, on the cohort scale."
    )
    cohorts: list[VintageCohort] = Field(description="One entry per cohort, oldest first.")


@router.get(
    "/wells/vintage-cohorts",
    operation_id="get_well_vintage_cohorts",
    summary="Wells and cumulative volume by vintage cohort",
    description=(
        "Drilled wells and their cumulative volumes, grouped by the year that identifies the"
        " cohort. Which year that is — the spud year or the completion-anchor year — is not a"
        " query's choice to make: of the ND wells carrying both dates, 47 percent fall in"
        " different years, so the two are different charts. The key is committed as"
        " cr_nd_vintage_cohort_1 with its measured rationale and its effective date, read here"
        " at serve time, and the response names the rule so a reader can resolve why."
        " Wells the regulator published no key for are their own cohort with cohort_year null,"
        " never folded into a year and never dropped: on the deployed instance that is 6,970 ND"
        " wells, of which 49 have production, so the cohort is large in count and small in"
        " volume and the response says both."
        " Protocol 4D is stated rather than assumed: a vintage cohort is a population of"
        " drilled wells and not a set of admissible slots, so spacing_assumption.applies is"
        " false with its reason, and support_distribution says how many wells stand behind each"
        " cohort's figures on a scale cut for cohorts rather than for PLSS sections. The count"
        " it is cut on is wells_with_a_filed_month, which cr_nd_vintage_cohort_1 defines and"
        " which is deliberately not the producing classification served on /v1/wells."
        " The population is North Dakota. The Williston basin is not, so population_scope says"
        " so inside `data` rather than only in a warning a copied payload would lose."
    ),
    response_model=EnvelopeModel[WellVintageCohorts],
    openapi_extra={
        **request_example(),
        **dataset(
            id="vintage_cohorts",
            title="Vintage cohorts",
            group="wells",
            collection_pointer="/cohorts",
            anchors=["/cohort_basis", "/cohort_key_rule", "/snapshot_vintage"],
            row_id=["/cohort_year"],
            facets=[],
            columns={
                "default": [
                    "/cohort_year",
                    "/cohort_key_semantics",
                    "/wells",
                    "/wells_with_a_filed_month",
                    "/cumulative/oil_bbl",
                    "/cumulative/gas_mcf",
                ],
                "sort": "/cohort_year",
            },
            intro="nb_dataset_vintage_cohorts",
            order=17,
        ),
        **semantics(
            explain={
                "glossary": "gt_derivation_handle",
                "so": (
                    "Every cohort carries a well count, a producing-well count and up to three"
                    " totals, so a full basin's cohorts produce more handles than one"
                    " /v1/explain call takes; the response says how many it left out rather"
                    " than trimming quietly, and each figure still resolves alone."
                ),
            },
            explain_depth={
                "glossary": "gt_derivation_handle",
                "so": (
                    "A cohort total resolves through the cumulative mart to every promotion"
                    " that fed it, so the chain is one hop longer than a per-well figure's."
                ),
            },
        ),
    },
    responses=problem_responses("service_degraded"),
)
def get_well_vintage_cohorts(
    request: Request,
    connection: Connection,
    explain: ExplainEffect,
) -> JSONResponse:
    policy = load_cohort_policy(connection)
    cohorts, population = cohort_rollup(connection, policy)
    snapshot = population["snapshot_vintage"]
    if snapshot is None:
        # An empty cumulative mart is a state of this system, not a fact about North Dakota.
        # Serving the rollup anyway would put `snapshot_vintage: null` against a schema that
        # declares it a required date, and an empty `cohorts` would read as "ND has none".
        # The per-well sibling refuses by name in the same state, for the same reason.
        raise ProblemError(
            "service_degraded",
            detail=(
                "marts.well_cumulatives holds no rows, so there is no snapshot vintage to"
                " state these cohorts at and no population to roll up. Run the cumulatives"
                " refresh (python -m glasswell.marts.cumulatives); deploy.sh does this at"
                " step 6d. This is not a statement that no cohort exists."
            ),
        )
    data: dict[str, Any] = {
        "cohort_basis": policy.cohort_key,
        "cohort_key_rule": COHORT_RULE,
        "snapshot_vintage": snapshot,
        "spud_dates_read_at": population["spud_dates_read_at"],
        "population_scope": {
            "states_served": list(STATE_API_PREFIXES),
            "basin_complete": False,
            "detail": POPULATION_SCOPE_DETAIL,
        },
        "spacing_assumption": {"applies": False, "reason": SPACING_ASSUMPTION_REASON},
        "support_distribution": {
            "scale": SUPPORT_SCALE_NOTE,
            "classes": population["support_distribution"],
        },
        "cohorts": [
            _cohort(row, snapshot=snapshot, derivation=population["derivation_ids"][0])
            for row in cohorts
        ],
    }
    data = register_response_figures(
        connection,
        data,
        dataset="api.well_vintage_cohorts",
        operation_id="get_well_vintage_cohorts",
        locator=request.url.path,
        partition={"cohort_basis": policy.cohort_key, "as_of": iso(snapshot) or "latest"},
        input_derivations=population["derivation_ids"],
        correlation_id=request.state.request_id,
        rule_ids=[COHORT_RULE, "cr_nd_null_semantics_1", "cr_nd_liquids_policy_1"],
    )
    return enveloped(
        request,
        data,
        as_of=snapshot,
        as_of_requested="latest",
        labels=_cohort_labels(cohorts),
        warnings=_cohort_warnings(data, cohorts),
        links={
            COHORT_RULE: f"/v1/conformance/{COHORT_RULE}",
            "wells": "/v1/wells",
        },
        explain=inline_for(connection, explain),
    )


def _cohort(row: dict[str, Any], *, snapshot: date, derivation: str) -> dict[str, Any]:
    """The mart derivation is the figure's until register_response_figures rebinds every one
    of them to the request's own; a figure has to carry one to be built at all."""
    key = row["cohort_year"] if row["cohort_year"] is not None else row["cohort_key_semantics"]
    return {
        "cohort_year": row["cohort_year"],
        "cohort_key_semantics": row["cohort_key_semantics"],
        "wells": figure(
            str(row["wells"]),
            unit=COUNT_UNIT,
            derivation=derivation,
            selector=f"cohort={key}&col=wells",
        ),
        "wells_with_a_filed_month": figure(
            str(row["wells_with_a_filed_month"]),
            unit=COUNT_UNIT,
            derivation=derivation,
            selector=f"cohort={key}&col=wells_with_a_filed_month",
        ),
        "cumulative": {
            COHORT_STREAM_COLUMNS[stream]: (
                None
                if value is None
                else figure(
                    str(Decimal(value)),
                    unit=COHORT_STREAM_UNITS[stream],
                    derivation=derivation,
                    selector=f"cohort={key}&col={COHORT_STREAM_COLUMNS[stream]}",
                    granularity="well_observed",
                    basis=COHORT_STREAM_BASIS[stream],
                    report_vintage=snapshot,
                )
            )
            for stream, value in row["totals"].items()
        },
    }


def _cohort_labels(cohorts: list[dict[str, Any]]) -> dict[str, str]:
    """One key per cohort present: `web/src/api/envelope.ts` looks a pointer up by exact
    match, so a `/cohorts/*/...` key resolves for nobody (the same rule as _pool_labels)."""
    labels = {
        "/cohort_basis": "gt_vintage_well_vintage",
        "/cohort_key_rule": "gt_conformance_rule",
        "/snapshot_vintage": "gt_report_vintage",
        "/spud_dates_read_at": "gt_spud_date",
    }
    for index in range(len(cohorts)):
        labels |= {
            f"/cohorts/{index}/cohort_year": "gt_vintage_well_vintage",
            f"/cohorts/{index}/cohort_key_semantics": "gt_spud_date",
            f"/cohorts/{index}/wells": "gt_vintage_well_vintage",
            f"/cohorts/{index}/wells_with_a_filed_month": "gt_cumulative_production",
            f"/cohorts/{index}/cumulative/oil_bbl": "gt_liquids_policy",
            f"/cohorts/{index}/cumulative/gas_mcf": "gt_stream",
            f"/cohorts/{index}/cumulative/water_bbl": "gt_stream",
        }
    return labels


def _cohort_warnings(data: Any, cohorts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = [
        {
            "code": "population_state_truncated",
            "detail": POPULATION_SCOPE_DETAIL,
            "pointer": "/cohorts",
        }
    ]
    handles = _handles(data)
    if handles > MAX_HANDLES:
        warnings.append(
            {
                "code": "explain_link_truncated",
                "detail": (
                    f"These {len(cohorts)} cohorts produced {handles} figures and links.explain"
                    f" carries the first {MAX_HANDLES} handles, so {handles - MAX_HANDLES} are"
                    " absent from it. Every figure still resolves on its own: read the figure's"
                    " `d` and call /v1/explain?h=<d>&depth=full. The cap is /v1/explain's own"
                    " (SB-07 §9.4), not this operation's."
                ),
                "pointer": "/cohorts",
            }
        )
    return warnings


CLASS_COLUMN_LABEL = "class as glasswell maps this code today"

SERVED_DETAIL = (
    "The dates beside these codes are the regulator's own: a new header appears when the"
    " regulator restamped the status, not when glasswell pulled. The class column is a"
    " read-time join against today's registry and is not historical, so a superseded"
    " vocabulary rule changes every row at once; each row names the rule that produced its"
    " class so the reader can see which."
)

# Named rather than "this jurisdiction": §2.3 asks a North Dakota well to say North Dakota
# files a snapshot, and the name is a registered field one row above it on the same record.
def absent_detail(jurisdiction_name: str | None) -> str:
    subject = jurisdiction_name or "This jurisdiction"
    return (
        f"{subject} files a snapshot: the effective_from beside a filed code is the vintage of"
        " the extract glasswell pulled, not a date the regulator stamped, so there is no"
        " status history to serve here and an empty list would read as a well that never"
        " changed rather than as a history nobody captured. The current status and the rule"
        " that maps it are on the well record."
    )

STATUS_HISTORY_LABELS = {
    "/api10": "gt_api_10_api_12_api_14",
    "/basis/rule_id": "gt_conformance_rule",
    "/basis/status_vocabulary_rule": "gt_conformance_rule",
    "/history/status_reported": "gt_well_status",
    "/history/status_canonical": "gt_well_status",
    "/history/status_rule_id": "gt_conformance_rule",
    "/history/effective_from": "gt_effective_date",
}


@router.get(
    "/wells/{api10}/history",
    operation_id="get_well_status_history",
    summary="Status history for one well",
    description=(
        "Every effective-dated header this well carries, newest first, over the status code"
        " the regulator filed. Not over the canonical class: a canonical class is glasswell's"
        " own mapping decision and can be superseded by a rule, so a history over it would"
        " show a rule edit as if the regulator had changed its mind, and it would be empty"
        " everywhere — zero wells in the spine carry more than one distinct canonical class,"
        " while 31,707 carry a changed filed code."
        " Whether there is a history at all is a property of the jurisdiction's clock, not of"
        " the well: where effective_from is the regulator's own valid time a new header means"
        " the regulator restamped the status, and where it is the vintage of the extract"
        " glasswell pulled it means only that glasswell looked again. Each jurisdiction's own"
        " status_history rule records which of the two its headers are on, and that"
        " registration is the only thing that emits links.history on the well record."
        " A 200 with an empty history and basis.served false is therefore the honest answer for"
        " a load-stamp jurisdiction: it says no history was captured, which an empty list on"
        " its own cannot tell apart from a well that never changed."
        " The class column is labelled rather than claimed. It is resolved through the one"
        " shared read-time resolver — the same join the tile mart, the facets and the well"
        " record use, so no two surfaces can answer differently — and it is today's mapping"
        " applied to a historical code, which is what its label says."
    ),
    response_model=EnvelopeModel[WellStatusHistory],
    openapi_extra={
        **request_example(path={"api10": EXAMPLE_API10}),
        **semantics(
            as_of={
                "glossary": "gt_report_vintage",
                "so": (
                    "Walks the knowledge axis: a header promoted after the date asked for is"
                    " not in the answer, so a reader can see the history as it stood."
                ),
            },
        ),
    },
    responses=problem_responses("not_found", "validation_failed", "service_degraded"),
)
def get_well_status_history(
    request: Request,
    connection: Connection,
    api10: Annotated[str, Path(description="Ten-digit API well number.", pattern=API10_PATTERN)],
    as_of: AsOf = None,
) -> JSONResponse:
    registry = jurisdictions(connection)
    found = rows(connection, STATUS_HISTORY_SQL, {"api10": api10, "as_of": as_of})
    if not found:
        raise ProblemError("not_found", detail=f"no well {api10} at this vintage")

    state_code = api10[:2]
    history_rule = registry.rule_for(state_code, STATUS_HISTORY)
    vocabulary_rule = registry.rule_for(state_code, STATUS_VOCABULARY)
    served = history_rule is not None
    kept = found[: STATUS_HISTORY_CAP] if served else []
    resolved_as_of = max(row["available_on"] for row in found)
    data = {
        "api10": api10,
        "state_code": state_code,
        "basis": {
            "clock": SOURCE_VALID_TIME if served else LOAD_STAMP,
            "served": served,
            "rule_id": history_rule,
            "status_vocabulary_rule": vocabulary_rule,
            "class_column_label": CLASS_COLUMN_LABEL,
            "class_column_is_historical": False,
            "detail": (
                SERVED_DETAIL if served else absent_detail(registry.name_for(state_code))
            ),
        },
        "history": [
            {
                "effective_from": iso(row["effective_from"]),
                "status_reported": row["status_reported"],
                "status_canonical": row["status_canonical"],
                # The same rule on every row of one well, and on the row rather than only in
                # the basis: a reader who copies one row keeps what produced its class.
                "status_rule_id": vocabulary_rule if row["status_canonical"] else None,
            }
            for row in kept
        ],
        "cap": {
            "limit": STATUS_HISTORY_CAP,
            "returned": len(kept),
            # Counted honestly whether or not a history is served: the field is scoped to the
            # well, and answering 0 for a well that carries two headers was the one false
            # number in the block. `basis.served` carries the refusal, and `withheld` stays 0
            # because the cap held nothing back -- the rule did.
            "total": len(found),
            "withheld": max(0, len(found) - len(kept)) if served else 0,
        },
    }
    return enveloped(
        request,
        data,
        as_of=resolved_as_of,
        as_of_requested=iso(as_of) or "latest",
        labels=STATUS_HISTORY_LABELS,
        links={
            "self": f"/v1/wells/{api10}/history",
            "well": f"/v1/wells/{api10}",
            **({"history_rule": f"/v1/conformance/{history_rule}"} if history_rule else {}),
            **(
                {"status_rule": f"/v1/conformance/{vocabulary_rule}"}
                if vocabulary_rule
                else {}
            ),
        },
    )


@router.get(
    "/wells/{api10}",
    operation_id="get_well",
    summary="One well header",
    description=(
        "Header, resolved status, land unit and geometry references for one well, plus the"
        " lateral count and total lateral length. Length is computed live from"
        " canonical.well_spatial in the basin's compute CRS — never from a stored degree"
        " length, and never from a mart this slice cannot exercise. It does not include"
        " production, forecasts or economics."
    ),
    response_model=EnvelopeModel[WellDetail],
    openapi_extra={
        **request_example(path={"api10": EXAMPLE_API10}),
        **semantics(
            explain={
                "glossary": "gt_derivation_handle",
                "so": (
                    "Resolves this header's figures — the lateral length and the total depth —"
                    " to the geometry rows and the checksummed file behind them, in the"
                    " request that served them. It is the `d` on each figure, already followed."
                ),
            },
            explain_depth={
                "glossary": "gt_derivation_handle",
                "so": (
                    "A header figure is one promotion away from its manifest, so the default"
                    " three already terminates here. Depth matters on figures whose chain runs"
                    " through a mart, and an inlined chain that stopped short says so itself."
                ),
            },
        ),
    },
    responses=problem_responses("not_found", "validation_failed", "service_degraded"),
)
def get_well(
    request: Request,
    connection: Connection,
    api10: Annotated[str, Path(description="Ten-digit API well number.", pattern=API10_PATTERN)],
    explain: ExplainEffect,
    as_of: AsOf = None,
) -> JSONResponse:
    registry = jurisdictions(connection)
    policy, producing_bindings = _producing(connection)
    found = rows(
        connection,
        RANKED_WELLS_PRODUCING + " and api10 = %(api10)s",
        {"as_of": as_of, "api10": api10, **producing_bindings},
    )
    if not found:
        raise ProblemError("not_found", detail=f"no well {api10} at this vintage")
    row = found[0]

    crs = rows(connection, _STORAGE_CRS, {"basin": row["basin"], "as_of": as_of})
    storage_epsg = crs[0]["storage_epsg"] if crs else STORAGE_EPSG
    status_vocabulary_rule = registry.rule_for(row["state_code"], STATUS_VOCABULARY)
    jurisdiction = registry.at_prefix(row["state_code"])
    # Registered only where the header's effective_from is the regulator's own valid time, so
    # the link's presence is the answer to "is there a history here" and the card can know it
    # without asking. The jurisdiction's status_history rule is the only thing that emits it.
    history_rule = registry.rule_for(row["state_code"], STATUS_HISTORY)
    length_scope_rule = registry.rule_for(row["state_code"], LENGTH_SCOPE)
    neighbours_served, neighbours_rule, neighbours_reason = _neighbours(
        registry, row["state_code"]
    )
    # The basin's own rule, so a TX length's handle resolves to a rule about TX geometry. Not
    # resolved at all where a rule withholds the length: the resolver's no-basin default is
    # North Dakota's, and reading it would put that rule id on the response either way.
    length_unregistered = False
    method = None
    if not length_scope_rule:
        try:
            method = resolve_length_method(
                connection,
                basin=row["basin"],
                valid_at=as_of,
                knowledge_at=as_of,
            )
        except LengthRuleUnregistered:
            length_unregistered = True
    warnings: list[dict[str, Any]] = []
    if policy is None:
        warnings.append(_producing_unregistered("/producing"))
    lease_reported = lease_reporting_rule(
        connection,
        row["state_code"],
        valid_at=as_of,
        knowledge_at=as_of,
    )
    if lease_reported:
        warnings.append(pending_allocation(lease_reported))
    pool_grain = pool_grain_rule(
        connection, row["state_code"], valid_at=as_of, knowledge_at=as_of
    )
    if pool_grain and row["producing"] == UNKNOWN:
        warnings.append(reported_at_pool_grain(pool_grain))
    geometry = rows(
        connection,
        # No method, no metres: `length_m` is what the withheld figure would have been summed
        # from, so it must not be computed under a rule the response does not cite.
        _SPATIAL.format(
            length_metres="null::double precision" if method is None else method.metres_sql()
        ),
        {"api10": api10, "as_of": as_of},
    )

    held_back_warnings, held_back_vintages = _held_back_geometry(
        connection, api10, as_of=as_of
    )
    warnings.extend(held_back_warnings)
    resolved_vintages = [row["available_on"]]
    if method is not None:
        resolved_vintages.append(method.effective_from)
    resolved_vintages.extend(item["available_on"] for item in geometry)
    resolved_vintages.extend(held_back_vintages)
    if crs:
        resolved_vintages.append(crs[0]["effective_from"])
    if lease_reported:
        resolved_vintages.append(lease_reported["effective_from"])
    resolved_as_of = max(resolved_vintages)
    laterals = [item for item in geometry if item["geom_type"] == "lateral"]
    untiled = [item["geom_key"] for item in laterals if not item["tiled"]]
    if untiled:
        warnings.append(
            {
                "code": "below_tile_resolution",
                "detail": (
                    f"{len(untiled)} lateral geometries are below the resolution of the"
                    f" deepest published zoom (z{TILE_MAX_ZOOM}) and render on no tile"
                    + ("; their length is still served here" if method else "")
                ),
                "pointer": "/geometry",
            }
        )
    length_figure = None
    if laterals and length_unregistered:
        warnings.append(
            {
                "code": LENGTH_SCOPE_UNREGISTERED,
                "detail": (
                    f"{len(laterals)} geometries are held for this well and no length rule is"
                    " registered for its basin, so no length is served; this is a registry gap"
                    " rather than a fact about the well"
                ),
                "pointer": "/lateral_length_ft",
            }
        )
    elif laterals and length_scope_rule:
        warnings.append(
            {
                "code": "length_not_served",
                "detail": (
                    f"{len(laterals)} geometries are held for this well and no length is served"
                    f" for them; {length_scope_rule} is the rule that withholds it"
                ),
                "pointer": "/lateral_length_ft",
                "rule_id": length_scope_rule,
            }
        )
    elif laterals:
        metres = sum(Decimal(str(item["length_m"])) for item in laterals)
        derivations = {item["derivation_id"] for item in laterals}
        if len(derivations) > 1:
            warnings.append(
                {
                    "code": "aggregate_spans_derivations",
                    "detail": (
                        f"{len(derivations)} derivations contributed; the response derivation"
                        " cites every contributing derivation"
                    ),
                    "pointer": "/lateral_length_ft",
                }
            )
        # Round-final: the sum is converted once, and the serving edge is the only quantize.
        length_figure = figure(
            str(metres_to_feet(metres).quantize(Decimal("0.01"))),
            unit="ft",
            derivation=sorted(derivations)[-1],
            selector=f"api10={api10}&col=lateral_length_ft",
        )
        length_figure = register_response_figures(
            connection,
            length_figure,
            dataset="api.well_detail",
            operation_id="get_well",
            locator=request.url.path,
            partition={"api10": api10, "as_of": resolved_as_of.isoformat()},
            input_derivations=sorted(derivations),
            correlation_id=request.state.request_id,
            rule_ids=[method.rule_id],
        )

    basin_context = _basin_block(rows(connection, _BASIN_CONTEXT, {"api10": api10}), api10)
    type_curve_scope = _type_curve_scope(connection, api10)

    point = next((item for item in geometry if item["lon"] is not None), None)
    data = _summary(row, registry) | {
        "api14": row["api14"],
        "state_code": row["state_code"],
        "ndic_file_no": row["ndic_file_no"],
        "status_reported": row["status_reported"],
        "well_type_reported": row["well_type_reported"],
        "basin": row["basin"],
        "lateral_count": len(laterals),
        "lateral_length_ft": length_figure,
        "total_depth_ft": (
            figure(
                str(Decimal(str(row["total_depth_ft"])).quantize(Decimal("0.1"))),
                unit="ft",
                derivation=row["derivation_id"],
                selector=(
                    f"api10={api10}&effective_from={row['effective_from']:%Y-%m-%d}"
                    "&col=total_depth_ft"
                ),
            )
            if row["total_depth_ft"] is not None
            else None
        ),
        "completion_date": iso(row["completion_date"]),
        "compute_crs": None if method is None else method.compute_crs,
        "length_method": LENGTH_NOT_SERVED if method is None else method.method,
        "storage_crs": f"EPSG:{storage_epsg}",
        "geometry": [
            {
                "geom_type": item["geom_type"],
                "geom_key": item["geom_key"],
                "source_datum": item["source_datum"],
            }
            for item in geometry
        ],
        "surface_point": {"lon": point["lon"], "lat": point["lat"]} if point else None,
        "neighbors_reason": neighbours_reason,
        # The polygon answer beside the ingest scope label, with their agreement marked. Null
        # only where the mart has not been refreshed since the well landed.
        "basin_context": basin_context,
        # Whether a peer control exists for this well and what it is scoped to, so the card
        # knows the section exists without asking and its absence sentence is served.
        "type_curve_scope": type_curve_scope,
        # Whose well it is, read off the registry rather than written in the client: a Montana
        # disposal well's hover said "as ND filed it" for exactly as long as the client held
        # the answer. The portal is a portal, and the field says so in its own description.
        "jurisdiction_name": jurisdiction.name if jurisdiction else None,
        "regulator_name": jurisdiction.regulator_name if jurisdiction else None,
        "regulator_url": jurisdiction.regulator_url if jurisdiction else None,
        # Null for Texas today, which is a registry gap the card states rather than a reason to
        # inherit North Dakota's rule.
        "geometry_provenance_rule": registry.rule_for(row["state_code"], GEOMETRY_PROVENANCE),
    }
    return enveloped(
        request,
        data,
        as_of=resolved_as_of,
        as_of_requested=iso(as_of) or "latest",
        labels=WELL_LABELS,
        warnings=warnings,
        links={
            "completions": f"/v1/wells/{api10}/completions",
            # Absent outside the cumulative mart's states, so a card offered the link never
            # reads a 404 as "this well produced nothing" — the two are different facts.
            **(
                {"cumulatives": f"/v1/wells/{api10}/cumulatives"}
                if row["state_code"] in STATE_API_PREFIXES
                else {}
            ),
            "formations": "/v1/formations",
            **(
                {"neighbors": f"/v1/wells/{api10}/neighbors"}
                if neighbours_served and laterals
                else {}
            ),
            # The decision behind the section, reachable from the response rather than only
            # implied by the link's absence.
            **(
                {"neighbors_rule": f"/v1/conformance/{neighbours_rule}"}
                if neighbours_rule
                else {}
            ),
            "production": f"/v1/wells/{api10}/production",
            **(
                {"reporting_rule": f"/v1/conformance/{lease_reported['rule_id']}"}
                if lease_reported
                else {}
            ),
            # The absence of a figure is itself a decision, so it is reachable from the
            # response rather than only stated in a warning string.
            **(
                {"length_rule": f"/v1/conformance/{length_scope_rule}"}
                if length_scope_rule
                else {}
            ),
            **({"history": f"/v1/wells/{api10}/history"} if history_rule else {}),
            **(
                {"history_rule": f"/v1/conformance/{history_rule}"} if history_rule else {}
            ),
            **(
                {"status_rule": f"/v1/conformance/{status_vocabulary_rule}"}
                if status_vocabulary_rule
                else {}
            ),
            # Emitted from the held-out fact and from nothing else: the section renders when
            # the link is present, which is what stops a card offering a control fitted on the
            # well it is being compared against.
            **(
                {"type_curve": f"/v1/wells/{api10}/type-curve"}
                if type_curve_scope["held_out"]
                else {}
            ),
        },
        explain=inline_for(connection, explain),
    )
