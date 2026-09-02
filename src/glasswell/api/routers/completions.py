"""Source-observed completion events and completion-pool context for one well."""

from __future__ import annotations

import base64
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

import psycopg
from fastapi import APIRouter, Path, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import AsOf, Connection, ExplainEffect, rows, today
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import (
    EXAMPLE_API10,
    GLOSSARY_KEY,
    dataset,
    not_a_figure,
    request_example,
    semantics,
)
from glasswell.api.provenance import register_response_figures
from glasswell.api.responses import EnvelopeModel, FigureModel, enveloped, inline_for, iso
from glasswell.api.routers.health import source_health_data
from glasswell.api.routers.wells import API10_PATTERN, RANKED_WELLS
from glasswell.lengths import resolve_length_method
from glasswell.lineage.conformance import load_rules, rule_for_family
from glasswell.lineage.envelope import figure
from glasswell.lineage.ids import format_handle
from glasswell.units import metres_to_feet

router = APIRouter(tags=["wells"])

FRACFOCUS_SOURCE_ID = "fracfocus_csv"
UNITS_RULE_ID = "cr_ff_base_water_units_1"
PROMOTE_RULE_ID = "cr_ff_design_promote_1"
INTENSITY_FAMILY = "cr_ff_fluid_intensity"
# A registry gap is not a fact about the source. wells.py:97-100 draws the same distinction for
# the producing classification: answering with a source-shaped label would read as a statement
# about the well rather than about the registry.
INTENSITY_RULE_UNREGISTERED = "intensity_rule_unregistered"
# The source-side absences the quotient inherits verbatim. A withheld numerator makes a
# withheld quotient; reporting it as no_report would say the operator disclosed nothing when
# the regulator is what held it back — the conflation cr_nd_null_semantics_1 exists to refuse.
ABSENT_VOLUME_SEMANTICS = ("no_report", "withheld")


@dataclass(frozen=True, slots=True)
class IntensityPolicy:
    min_lateral_ft: Decimal
    max_gal_per_ft: Decimal
    rule_id: str


_SELECTOR_SAFE = re.compile(r"\A[A-Za-z0-9_.:+-]+\Z")

_ANCHORS = """
with ranked as (
    select a.*, m.fetch_vintage as manifest_vintage,
           d.created_vintage as derivation_vintage,
           row_number() over (
               partition by a.disclosure_id, a.source_id
               order by a.report_vintage desc, a.derivation_id desc) as vintage_rank
      from canonical.well_completion_anchors a
      join lineage.manifests m on m.manifest_id = a.source_manifest_id
      join lineage.derivations d on d.derivation_id = a.derivation_id
     where a.api10 = %(api10)s
       and (%(as_of)s::date is null or a.report_vintage <= %(as_of)s::date)
       and (%(as_of)s::date is null or m.fetch_vintage <= %(as_of)s::date)
       and (%(as_of)s::date is null or d.created_vintage is null
            or d.created_vintage <= %(as_of)s::date)
)
select disclosure_id, job_start_date, completion_date, anchor_kind, source_id,
       report_vintage, derivation_id,
       greatest(report_vintage, manifest_vintage,
                coalesce(derivation_vintage, manifest_vintage)) as available_on
  from ranked
 where vintage_rank = 1
 order by completion_date, disclosure_id
"""

_COMPLETION_POOLS = """
with ranked as (
    select c.*, m.fetch_vintage as manifest_vintage,
           d.created_vintage as derivation_vintage,
           row_number() over (
               partition by c.completion_key, c.source_id, c.production_month,
                            coalesce(c.pod_id, '')
               order by c.report_vintage desc, c.effective_from desc nulls last,
                        c.derivation_id desc) as vintage_rank
      from canonical.well_completions c
      join lineage.manifests m on m.manifest_id = c.source_manifest_id
      join lineage.derivations d on d.derivation_id = c.derivation_id
     where c.api10 = %(api10)s
       and (%(as_of)s::date is null or c.report_vintage <= %(as_of)s::date)
       and (%(as_of)s::date is null or c.effective_from is null
            or c.effective_from <= %(as_of)s::date)
       and (%(as_of)s::date is null or m.fetch_vintage <= %(as_of)s::date)
       and (%(as_of)s::date is null or d.created_vintage is null
            or d.created_vintage <= %(as_of)s::date)
), current_rows as (
    select * from ranked where vintage_rank = 1
)
select c.completion_key, c.well_completion_pool, c.pool_reported, c.source_id,
       c.production_month, c.effective_from, c.pod_id, c.report_vintage, c.derivation_id,
       greatest(c.report_vintage, c.manifest_vintage,
                coalesce(c.derivation_vintage, c.manifest_vintage)) as available_on,
       alias.formation, alias.formation_group, alias.formation_effective_from,
       alias.formation_created_vintage
  from current_rows c
  left join lateral (
      select a.formation, a.formation_group, a.effective_from as formation_effective_from,
             a.created_vintage as formation_created_vintage
        from lineage.formation_aliases a
       where a.formation_raw = c.pool_reported
         and (a.source_id = c.source_id or a.source_id is null)
         and a.effective_from <= %(as_of)s::date
         and a.created_vintage is not null
         and a.created_vintage <= %(as_of)s::date
       order by (a.source_id = c.source_id) desc nulls last,
                a.effective_from desc, a.formation
       limit 1
  ) alias on true
 order by c.completion_key, c.source_id, c.well_completion_pool,
          c.production_month nulls last, c.effective_from nulls last, c.pod_id nulls first
"""

_VINTAGE_BOUNDS = """
select min(available_on) as earliest
  from (
        select greatest(a.report_vintage, m.fetch_vintage,
                        coalesce(d.created_vintage, m.fetch_vintage)) as available_on
          from canonical.well_completion_anchors a
          join lineage.manifests m on m.manifest_id = a.source_manifest_id
          join lineage.derivations d on d.derivation_id = a.derivation_id
         where a.api10 = %(api10)s
        union all
        select greatest(c.report_vintage, m.fetch_vintage,
                        coalesce(d.created_vintage, m.fetch_vintage)) as available_on
          from canonical.well_completions c
          join lineage.manifests m on m.manifest_id = c.source_manifest_id
          join lineage.derivations d on d.derivation_id = c.derivation_id
         where c.api10 = %(api10)s
       ) observations
"""

_DESIGN = """
with ranked as (
    select d.*, m.fetch_vintage as manifest_vintage,
           v.created_vintage as derivation_vintage,
           row_number() over (
               partition by d.disclosure_id, d.source_id
               order by d.report_vintage desc, d.derivation_id desc) as vintage_rank
      from canonical.well_completion_design d
      join lineage.manifests m on m.manifest_id = d.source_manifest_id
      join lineage.derivations v on v.derivation_id = d.derivation_id
     where d.api10 = %(api10)s
       and (%(as_of)s::date is null or d.report_vintage <= %(as_of)s::date)
       and (%(as_of)s::date is null or m.fetch_vintage <= %(as_of)s::date)
       and (%(as_of)s::date is null or v.created_vintage is null
            or v.created_vintage <= %(as_of)s::date)
)
select disclosure_id, base_water_volume, base_water_unit, base_water_null_semantics,
       source_id, report_vintage, derivation_id,
       greatest(report_vintage, manifest_vintage,
                coalesce(derivation_vintage, manifest_vintage)) as available_on
  from ranked
 where vintage_rank = 1
 order by report_vintage desc, disclosure_id
"""

# Computed live from canonical geometry under the basin's own length rule, never read from a
# mart: wells.py:1511-1514 states the card's length is measured here, and two paths measuring
# one geometry differently is what glasswell.lengths exists to prevent.
_LATERALS = """
select s.geom_key, s.derivation_id, {length_metres} as length_m
  from canonical.well_spatial s
  join lineage.manifests m on m.manifest_id = s.source_manifest_id
  join lineage.derivations d on d.derivation_id = s.derivation_id
 where s.api10 = %(api10)s
   and s.geom_type = 'lateral'
   and (%(as_of)s::date is null or m.fetch_vintage <= %(as_of)s::date)
   and (%(as_of)s::date is null or d.created_vintage is null
        or d.created_vintage <= %(as_of)s::date)
 order by s.geom_key
"""

_SOURCE_COVERAGE = """
select source_id, min(available_on) as earliest_available_on,
       array_agg(distinct collection order by collection) as collections
  from (
        select a.source_id, 'events' as collection,
               greatest(a.report_vintage, m.fetch_vintage,
                        coalesce(d.created_vintage, m.fetch_vintage)) as available_on
          from canonical.well_completion_anchors a
          join lineage.manifests m on m.manifest_id = a.source_manifest_id
          join lineage.derivations d on d.derivation_id = a.derivation_id
         where a.api10 = %(api10)s
        union all
        select c.source_id, 'pools' as collection,
               greatest(c.report_vintage, m.fetch_vintage,
                        coalesce(d.created_vintage, m.fetch_vintage)) as available_on
          from canonical.well_completions c
          join lineage.manifests m on m.manifest_id = c.source_manifest_id
          join lineage.derivations d on d.derivation_id = c.derivation_id
         where c.api10 = %(api10)s
       ) observations
 group by source_id
 order by source_id
"""

class CompletionEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(description="Source-issued disclosure id for this event.")
    event_kind: str = Field(
        description=(
            "Source event kind; currently hydraulic_frac_job_end, never a spud-date proxy."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_completion_event"},
    )
    job_start_date: date | None = Field(description="Source-reported job start date, if present.")
    completion_date: date = Field(
        description="Source-reported hydraulic-fracturing job end date.",
        json_schema_extra={GLOSSARY_KEY: "gt_completion_event"},
    )
    source_id: str = Field(
        description="Source that reported the event.",
        json_schema_extra={GLOSSARY_KEY: "gt_source"},
    )
    report_vintage: date = Field(
        description="Knowledge vintage of this event observation.",
        json_schema_extra={GLOSSARY_KEY: "gt_report_vintage"},
    )
    lineage: dict[str, str] = Field(
        alias="_lineage", description="Dotted event-field path to derivation handle."
    )


class CompletionPool(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    completion_key: str = Field(description="Source-conformed completion entity key.")
    well_completion_pool: str = Field(
        description="Well-completion-pool identity carried by production.",
        json_schema_extra={GLOSSARY_KEY: "gt_pool"},
    )
    pool_reported: str | None = Field(
        description="Pool label exactly as the regulator reported it.",
        json_schema_extra={GLOSSARY_KEY: "gt_pool"},
    )
    formation: str | None = Field(
        description="Canonical formation from the source-scoped alias registry.",
        json_schema_extra={GLOSSARY_KEY: "gt_formation"},
    )
    formation_group: str | None = Field(
        description="Benchmark peer group from the same formation alias row.",
        json_schema_extra={GLOSSARY_KEY: "gt_formation"},
    )
    formation_null_semantics: Literal["mapped", "pool_not_reported", "alias_unavailable"] = Field(
        description="Why formation fields are populated or null; absence is never inferred."
    )
    source_id: str = Field(
        description="Source that reported the completion-pool entity.",
        json_schema_extra={GLOSSARY_KEY: "gt_source"},
    )
    first_production_month: date | None = Field(
        description="First source month carrying this pool entity; null on effective-dated rows.",
        json_schema_extra={GLOSSARY_KEY: "gt_production_month"},
    )
    last_production_month: date | None = Field(
        description="Latest source month carrying this pool entity; null on effective-dated rows.",
        json_schema_extra={GLOSSARY_KEY: "gt_production_month"},
    )
    effective_from: date | None = Field(
        description="Latest effective date for a dimension-grain completion row."
    )
    latest_report_vintage: date = Field(
        description="Latest knowledge vintage contributing to this summary.",
        json_schema_extra={GLOSSARY_KEY: "gt_report_vintage"},
    )
    lineage: dict[str, str] = Field(
        alias="_lineage", description="Dotted summary-field path to source derivation handle."
    )


class CompletionDesign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disclosure_id: str = Field(description="Source-issued disclosure the design was read from.")
    base_water_volume: FigureModel | None = Field(
        description="Disclosed total base water volume; null where the source filed none.",
        json_schema_extra={GLOSSARY_KEY: "gt_fluid_intensity"},
    )
    base_water_null_semantics: str = Field(
        description=(
            "reported, reported_zero, no_report or withheld for the disclosed volume — the"
            " same four classes canonical keeps apart, never collapsed into one absence."
        )
    )
    lateral_length_ft: FigureModel | None = Field(
        description="Summed lateral, measured live under the basin's length rule.",
        json_schema_extra={GLOSSARY_KEY: "gt_wellbore"},
    )
    fluid_intensity: FigureModel | None = Field(
        description="Base fluid per lateral foot; null with a stated reason, never a zero.",
        json_schema_extra={GLOSSARY_KEY: "gt_fluid_intensity"},
    )
    intensity_null_semantics: str = Field(
        description=(
            "reported, or why no intensity is served. An absent numerator is reported as the"
            " source classified it — no_report where nothing was disclosed, withheld where the"
            " regulator held it back — and the divisor and the result have their own reasons:"
            " lateral_length_unavailable, lateral_length_implausible, intensity_out_of_range."
            " intensity_rule_unregistered means cr_ff_fluid_intensity is not registered: a gap"
            " in the registry, not a fact about the source."
        )
    )
    source_id: str = Field(
        description="Source that disclosed the design.",
        json_schema_extra={GLOSSARY_KEY: "gt_source"},
    )
    report_vintage: date = Field(
        description="Knowledge vintage of the disclosure.",
        json_schema_extra={GLOSSARY_KEY: "gt_report_vintage"},
    )


class WellCompletions(BaseModel):
    api10: str = Field(
        description="Ten-digit API well number.",
        json_schema_extra=not_a_figure(
            "Identifier. A 10-digit API number is an identity string, not a measurement."
        ),
    )
    design_availability: str = Field(
        description=(
            "Whether this release promotes completion design at all. It is a statement about"
            " the release, not about this well: per-well absence is `design: null` with"
            " `design_null_semantics`."
        )
    )
    design: CompletionDesign | None = Field(
        description="Promoted completion design for this well; null where none was disclosed."
    )
    design_null_semantics: str = Field(
        description="reported where a disclosure was promoted, no_report where none exists."
    )
    events: list[CompletionEvent] = Field(
        description="Source-observed completion events, independent of pool assignments."
    )
    pools: list[CompletionPool] = Field(
        description="Source-observed completion-pool entities, independent of events."
    )


@router.get(
    "/wells/{api10}/completions",
    operation_id="get_well_completions",
    summary="Completion context for one well",
    description=(
        "Two independent source collections for one well: completion events from canonical"
        " FracFocus anchors, and regulator completion-pool entities with source-scoped formation"
        " aliases. The API does not join an event to a pool because no canonical key proves that"
        " relationship. A missing formation says whether the pool was absent or the alias was"
        " unavailable. `as_of` constrains wells, events, completion rows, manifests,"
        " derivations, and knowledge-vintaged aliases together."
        " This release promotes completion design, so `design_availability` reads `promoted`:"
        " that is a statement about the release, not about this well. The disclosed base water"
        " volume is served in US gallons under cr_ff_base_water_units_1, and fluid intensity is"
        " computed at request time as that volume over the well's summed lateral, measured live"
        " in the basin's own compute CRS. cr_ff_fluid_intensity_1 declares the minimum divisor"
        " the division is defensible over and the ceiling above which the result is withdrawn:"
        " no ND well has a summed lateral of exactly zero, so a divide-by-zero guard would fire"
        " on nothing while a 0.24 ft divisor would serve tens of millions of gallons per foot as"
        " a handled figure. Where either bound is crossed, or the geometry or the disclosure is"
        " missing, the intensity is null with the reason named in"
        " `design.intensity_null_semantics` - never a zero and never an infinity. FracFocus"
        " disclosure is voluntary, so a well with none gets `design: null` and"
        " `design_null_semantics` no_report, with the measured registry coverage in a warning."
    ),
    response_model=EnvelopeModel[WellCompletions],
    openapi_extra={
        **request_example(path={"api10": EXAMPLE_API10}),
        **dataset(
            id="completions",
            title="Completion pools (per well)",
            group="wells",
            collection_pointer="/pools",
            anchors=["/api10", "/design_availability", "/design_null_semantics"],
            row_id=["/completion_key", "/source_id", "/well_completion_pool"],
            facets=["as_of"],
            columns={
                "default": [
                    "/well_completion_pool",
                    "/pool_reported",
                    "/formation",
                    "/formation_group",
                    "/first_production_month",
                    "/last_production_month",
                ],
                "sort": "/first_production_month",
            },
            intro="nb_dataset_completions",
            order=13,
        ),
        **semantics(
            as_of={
                "glossary": "gt_report_vintage",
                "so": (
                    "Holds both event observations and pool-to-formation mappings to what was"
                    " knowable on the requested date. An unvintaged alias is excluded from an"
                    " historical read rather than leaked backward. A source whose first"
                    " captured context is later remains visible in freshness and an explicit"
                    " coverage warning."
                ),
            },
            explain={
                "glossary": "gt_derivation_handle",
                "so": (
                    "Inlines the source chain for each event and the first, latest, and"
                    " effective observations behind each completion-pool summary."
                ),
            },
            explain_depth={
                "glossary": "gt_derivation_handle",
                "so": "Three levels reaches the promotion and its source manifest.",
            },
        ),
    },
    responses=problem_responses(
        "not_found", "validation_failed", "as_of_out_of_range", "service_degraded"
    ),
)
def get_well_completions(
    request: Request,
    connection: Connection,
    api10: Annotated[str, Path(description="Ten-digit API well number.", pattern=API10_PATTERN)],
    explain: ExplainEffect,
    as_of: AsOf = None,
) -> JSONResponse:
    effective_as_of = as_of or today()
    params = {"api10": api10, "as_of": effective_as_of}
    found_wells = rows(connection, RANKED_WELLS + " and api10 = %(api10)s", params)
    if not found_wells:
        raise ProblemError("not_found", detail=f"no well {api10} at this vintage")
    well = found_wells[0]

    bounds = rows(connection, _VINTAGE_BOUNDS, {"api10": api10})[0]
    if as_of is not None and bounds["earliest"] is not None and as_of < bounds["earliest"]:
        raise ProblemError(
            "as_of_out_of_range",
            detail=(
                f"as_of {as_of.isoformat()} precedes the earliest captured completion vintage"
                f" {bounds['earliest'].isoformat()} for this well"
            ),
        )

    coverage = rows(connection, _SOURCE_COVERAGE, {"api10": api10})
    anchor_rows = rows(connection, _ANCHORS, params)
    pool_rows = rows(connection, _COMPLETION_POOLS, params)
    anchors = [_event(row) for row in anchor_rows]
    pools = _pools(pool_rows)
    vintages = [row["available_on"] for row in anchor_rows]
    vintages.extend(row["available_on"] for row in pool_rows)
    vintages.extend(
        row["formation_created_vintage"]
        for row in pool_rows
        if row["formation_created_vintage"] is not None
    )
    source_ids = [row["source_id"] for row in coverage]
    warnings = _coverage_warnings(coverage, as_of=effective_as_of)

    design_rows = rows(connection, _DESIGN, params)
    policy, policy_warnings = _intensity_policy(connection)
    warnings.extend(policy_warnings)
    method = resolve_length_method(
        connection, basin=well["basin"], valid_at=as_of, knowledge_at=as_of
    )
    laterals = rows(
        connection, _LATERALS.format(length_metres=method.metres_sql("s.geom")), params
    )
    design, design_warnings, design_rules = _design(
        connection,
        request,
        api10=api10,
        found=design_rows,
        laterals=laterals,
        policy=policy,
        method=method,
        as_of=effective_as_of,
    )
    warnings.extend(design_warnings)
    if design_rows:
        vintages.extend(row["available_on"] for row in design_rows)
        source_ids = sorted({*source_ids, *(row["source_id"] for row in design_rows)})
    return enveloped(
        request,
        {
            "api10": api10,
            "design_availability": "promoted",
            "design": design,
            "design_null_semantics": "reported" if design else "no_report",
            "events": anchors,
            "pools": pools,
        },
        as_of=max(vintages, default=well["available_on"]),
        as_of_requested=iso(as_of) or "latest",
        labels=_labels(anchors, pools),
        source_freshness=_freshness(connection, source_ids),
        warnings=warnings,
        links={
            "well": f"/v1/wells/{api10}",
            "production": f"/v1/wells/{api10}/production",
            "formations": "/v1/formations",
            **{rule: f"/v1/conformance/{rule}" for rule in design_rules},
        },
        explain=inline_for(connection, explain),
    )


def _intensity_or_reason(
    volume_gal: Decimal | None,
    lateral_ft: Decimal | None,
    policy: IntensityPolicy | None,
    volume_semantics: str,
) -> tuple[Decimal | None, str]:
    """With no registered rule there are no bounds to apply, and saying so is the only honest
    answer: no_report here would report a registry gap as a source that disclosed nothing."""
    if policy is None:
        return None, INTENSITY_RULE_UNREGISTERED
    return _fluid_intensity(volume_gal, lateral_ft, policy, volume_semantics)


def _fluid_intensity(
    volume_gal: Decimal | None,
    lateral_ft: Decimal | None,
    policy: IntensityPolicy,
    volume_semantics: str,
) -> tuple[Decimal | None, str]:
    """cr_ff_fluid_intensity_1's executor: a value, or a reason — never a number with neither.

    An absent numerator is classified by the semantics the promotion recorded, not by the
    nullness of the value: a withheld volume and an undisclosed one are two different facts,
    and the quotient inherits the distinction rather than collapsing it back into one.

    `volume_semantics` is required rather than defaulted: a default of "no_report" is the
    collapse this signature exists to prevent, held one omitted argument away, and the failure
    would be a declared member returned for the wrong reason — which the vocabulary guard in
    tests/unit/test_fluid_intensity.py cannot see.
    """
    if volume_gal is None:
        absent = volume_semantics in ABSENT_VOLUME_SEMANTICS
        return None, (volume_semantics if absent else "no_report")
    if lateral_ft is None:
        return None, "lateral_length_unavailable"
    if lateral_ft < policy.min_lateral_ft:
        return None, "lateral_length_implausible"
    intensity = volume_gal / lateral_ft
    if intensity > policy.max_gal_per_ft:
        return None, "intensity_out_of_range"
    return intensity, "reported"


def _intensity_policy(
    connection: psycopg.Connection,
) -> tuple[IntensityPolicy | None, list[dict[str, Any]]]:
    """R8: the bounds are a row, so an unregistered rule withdraws the figure with a warning
    rather than letting a default decide what a plausible completion is."""
    try:
        rule = rule_for_family(
            load_rules(connection, source_id=FRACFOCUS_SOURCE_ID, stage="conform"),
            INTENSITY_FAMILY,
        )
    except LookupError:
        return None, [
            {
                "code": "intensity_rule_unregistered",
                "detail": (
                    f"No rule in family {INTENSITY_FAMILY} is registered, so the divisor floor"
                    " and the result ceiling are undefined and no fluid intensity is served."
                    " The disclosed volume is unaffected; this is a registry gap, not a fact"
                    " about the well."
                ),
                "pointer": "/design/fluid_intensity",
            }
        ]
    return (
        IntensityPolicy(
            min_lateral_ft=Decimal(str(rule.spec["min_lateral_ft"])),
            max_gal_per_ft=Decimal(str(rule.spec["max_gal_per_ft"])),
            rule_id=rule.rule_id,
        ),
        [],
    )


def _design(
    connection: psycopg.Connection,
    request: Request,
    *,
    api10: str,
    found: list[dict[str, Any]],
    laterals: list[dict[str, Any]],
    policy: IntensityPolicy | None,
    method: Any,
    as_of: date,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str]]:
    warnings: list[dict[str, Any]] = [_design_coverage_warning()]
    if not found:
        return None, warnings, [UNITS_RULE_ID]
    row = found[0]
    if len(found) > 1:
        warnings.append(
            {
                "code": "multiple_design_disclosures",
                "detail": (
                    f"{len(found)} FracFocus disclosures cover this API-10 and they are not"
                    f" summed: the newest, {row['disclosure_id']}, is served and the rest stay"
                    " inspectable in canonical. A pad-level filing added to a well-level one"
                    " would inflate the intensity of both."
                ),
                "pointer": "/design",
            }
        )
    metres = sum(
        (Decimal(str(item["length_m"])) for item in laterals), start=Decimal(0)
    )
    lateral_ft = metres_to_feet(metres) if laterals else None
    volume = row["base_water_volume"]
    intensity, semantics = _intensity_or_reason(
        volume, lateral_ft, policy, row["base_water_null_semantics"]
    )
    computed: dict[str, Any] = {
        "lateral_length_ft": (
            figure(
                str(lateral_ft.quantize(Decimal("0.01"))),
                unit="ft",
                derivation=sorted({item["derivation_id"] for item in laterals})[-1],
                selector=f"api10={api10}&col=lateral_length_ft",
            )
            if lateral_ft is not None
            else None
        ),
        "fluid_intensity": (
            figure(
                str(intensity.quantize(Decimal("0.01"))),
                unit="gal/ft",
                derivation=row["derivation_id"],
                selector=f"api10={api10}&col=fluid_intensity",
            )
            if intensity is not None
            else None
        ),
    }
    rule_ids = [UNITS_RULE_ID, PROMOTE_RULE_ID, method.rule_id]
    if policy:
        rule_ids.append(policy.rule_id)
    if any(computed.values()):
        computed = register_response_figures(
            connection,
            computed,
            dataset="api.well_completions",
            operation_id="get_well_completions",
            locator=request.url.path,
            partition={"api10": api10, "as_of": as_of.isoformat()},
            input_derivations=sorted(
                {row["derivation_id"], *(item["derivation_id"] for item in laterals)}
            ),
            correlation_id=request.state.request_id,
            rule_ids=rule_ids,
        )
    design = {
        "disclosure_id": row["disclosure_id"],
        "base_water_volume": (
            figure(
                str(volume),
                unit=row["base_water_unit"],
                derivation=row["derivation_id"],
                selector=(
                    f"{_selector_term('disclosure_id', row['disclosure_id'])}"
                    "&col=base_water_volume"
                ),
            )
            if volume is not None
            else None
        ),
        "base_water_null_semantics": row["base_water_null_semantics"],
        "intensity_null_semantics": semantics,
        "source_id": row["source_id"],
        "report_vintage": iso(row["report_vintage"]),
        **computed,
    }
    return design, warnings, sorted({*rule_ids} - {method.rule_id})


def _design_coverage_warning() -> dict[str, Any]:
    """FracFocus disclosure is voluntary, so absence is a fact about the registry."""
    return {
        "code": "design_coverage_partial",
        "detail": (
            "FracFocus disclosure is voluntary and its coverage is partial. Measured on the"
            " deployed instance 2026-08-30, 15,684 of the 22,263 ND wells with a lateral"
            " geometry (70.5 percent) carry a disclosed base water volume; the remaining 29.5"
            " percent have no disclosure at all, so a null design here is a fact about the"
            " registry rather than about the well."
        ),
        "pointer": "/design",
    }


def _event(row: dict[str, Any]) -> dict[str, Any]:
    selector = _selector_term("disclosure_id", row["disclosure_id"])
    lineage = {
        "completion_date": format_handle(row["derivation_id"], f"{selector}&col=completion_date")
    }
    if row["job_start_date"] is not None:
        lineage["job_start_date"] = format_handle(
            row["derivation_id"], f"{selector}&col=job_start_date"
        )
    return {
        "event_id": row["disclosure_id"],
        "event_kind": row["anchor_kind"],
        "job_start_date": iso(row["job_start_date"]),
        "completion_date": iso(row["completion_date"]),
        "source_id": row["source_id"],
        "report_vintage": iso(row["report_vintage"]),
        "_lineage": lineage,
    }


def _pools(found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in found:
        key = (
            row["completion_key"],
            row["source_id"],
            row["well_completion_pool"],
        )
        grouped.setdefault(key, []).append(row)

    pools = []
    for key in sorted(grouped):
        completion_key, source_id, well_completion_pool = key
        observations = grouped[key]
        months = [row for row in observations if row["production_month"] is not None]
        effective = [row for row in observations if row["effective_from"] is not None]
        first = min(months, key=_month_observation_order) if months else None
        last = max(months, key=_month_observation_order) if months else None
        latest = max(observations, key=_observation_order)
        pool_reported = latest["pool_reported"]
        formation = latest["formation"]
        formation_group = latest["formation_group"]
        latest_effective = (
            max(effective, key=_effective_observation_order)
            if effective
            else None
        )
        lineage = _pool_lineage(
            completion_key,
            first=first,
            last=last,
            effective=latest_effective,
            latest=latest,
        )
        pools.append(
            {
                "completion_key": completion_key,
                "well_completion_pool": well_completion_pool,
                "pool_reported": pool_reported,
                "formation": formation,
                "formation_group": formation_group,
                "formation_null_semantics": (
                    "pool_not_reported"
                    if pool_reported is None
                    else "mapped"
                    if formation is not None
                    else "alias_unavailable"
                ),
                "source_id": source_id,
                "first_production_month": iso(first["production_month"]) if first else None,
                "last_production_month": iso(last["production_month"]) if last else None,
                "effective_from": iso(latest_effective["effective_from"])
                if latest_effective
                else None,
                "latest_report_vintage": iso(latest["report_vintage"]),
                "_lineage": lineage,
            }
        )
    return pools


def _pool_lineage(
    completion_key: str,
    *,
    first: dict[str, Any] | None,
    last: dict[str, Any] | None,
    effective: dict[str, Any] | None,
    latest: dict[str, Any],
) -> dict[str, str]:
    lineage = {
        "pool_reported": _pool_handle(latest, completion_key, "pool_reported"),
        "latest_report_vintage": _pool_handle(latest, completion_key, "report_vintage"),
    }
    if first:
        lineage["first_production_month"] = _pool_handle(first, completion_key, "production_month")
    if last:
        lineage["last_production_month"] = _pool_handle(last, completion_key, "production_month")
    if effective:
        lineage["effective_from"] = _pool_handle(effective, completion_key, "effective_from")
    return lineage


def _pool_handle(row: dict[str, Any], completion_key: str, column: str) -> str:
    selector = f"{_selector_term('completion_key', completion_key)}&col={column}"
    if row["production_month"] is not None:
        selector += f"&pm={row['production_month']:%Y-%m}"
    elif row["effective_from"] is not None:
        selector += f"&effective_from={row['effective_from']:%Y-%m-%d}"
    if row["pod_id"] is not None:
        selector += f"&{_selector_term('pod_id', row['pod_id'])}"
    return format_handle(
        row["derivation_id"],
        selector,
    )


def _observation_order(row: dict[str, Any]) -> tuple[date, date, str, str]:
    observed_on = row["effective_from"] or row["production_month"] or date.min
    return row["report_vintage"], observed_on, row["derivation_id"], row["pod_id"] or ""


def _month_observation_order(row: dict[str, Any]) -> tuple[date, date, str, str]:
    return (
        row["production_month"],
        row["report_vintage"],
        row["derivation_id"],
        row["pod_id"] or "",
    )


def _effective_observation_order(row: dict[str, Any]) -> tuple[date, date, str, str]:
    return (
        row["effective_from"],
        row["report_vintage"],
        row["derivation_id"],
        row["pod_id"] or "",
    )


def _selector_term(name: str, value: str) -> str:
    if _SELECTOR_SAFE.fullmatch(value):
        return f"{name}={value}"
    encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{name}_b64={encoded}"


def _freshness(connection: Any, source_ids: list[str]) -> dict[str, Any]:
    if not source_ids:
        return {}
    _, freshness = source_health_data(
        connection,
        observed_at=datetime.now(UTC),
        source_ids=source_ids,
    )
    return freshness


def _coverage_warnings(
    coverage: Iterable[dict[str, Any]], *, as_of: date | None
) -> list[dict[str, str]]:
    if as_of is None:
        return []
    return [
        {
            "code": "source_history_unavailable",
            "detail": (
                f"{row['source_id']} has captured {', '.join(row['collections'])} for this well,"
                f" but its first available observation is"
                f" {row['earliest_available_on'].isoformat()}, after the requested cut."
            ),
            "pointer": "/" + row["collections"][0],
        }
        for row in coverage
        if row["earliest_available_on"] > as_of
    ]


def _labels(events: Iterable[dict[str, Any]], pools: Iterable[dict[str, Any]]) -> dict[str, str]:
    labels = {
        "/api10": "gt_api_10_api_12_api_14",
        "/design/base_water_volume": "gt_fluid_intensity",
        "/design/fluid_intensity": "gt_fluid_intensity",
        "/design/lateral_length_ft": "gt_wellbore",
        "/design/report_vintage": "gt_report_vintage",
        "/design/source_id": "gt_source",
    }
    for index, _ in enumerate(events):
        labels[f"/events/{index}/event_kind"] = "gt_completion_event"
        labels[f"/events/{index}/completion_date"] = "gt_completion_event"
        labels[f"/events/{index}/source_id"] = "gt_source"
        labels[f"/events/{index}/report_vintage"] = "gt_report_vintage"
    for index, _ in enumerate(pools):
        labels[f"/pools/{index}/well_completion_pool"] = "gt_pool"
        labels[f"/pools/{index}/pool_reported"] = "gt_pool"
        labels[f"/pools/{index}/formation"] = "gt_formation"
        labels[f"/pools/{index}/formation_group"] = "gt_formation"
        labels[f"/pools/{index}/source_id"] = "gt_source"
        labels[f"/pools/{index}/first_production_month"] = "gt_production_month"
        labels[f"/pools/{index}/last_production_month"] = "gt_production_month"
        labels[f"/pools/{index}/latest_report_vintage"] = "gt_report_vintage"
    return labels
