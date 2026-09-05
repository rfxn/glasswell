"""Monthly production as SB-07 §9.1(b) sidecar series: one handle per column, vintages
per point, and the three null semantics kept apart."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

import psycopg
from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import AsOf, Connection, ExplainEffect, jurisdictions, rows
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
from glasswell.api.responses import (
    EnvelopeModel,
    enveloped,
    inline_for,
    iso,
    month_label,
)
from glasswell.api.routers.completions import FRACFOCUS_SOURCE_ID, INTENSITY_FAMILY
from glasswell.api.routers.wells import (
    API10_PATTERN,
    LENGTH_SCOPE,
    RANKED_WELLS,
    pending_allocation,
)
from glasswell.lengths import LengthRuleUnregistered, resolve_length_method
from glasswell.lineage.conformance import (
    allocated_series_rule,
    lease_reporting_rule,
    load_rules,
    rule_for_family,
)
from glasswell.lineage.envelope import series
from glasswell.lineage.ids import format_handle
from glasswell.lineage.jurisdictions import JurisdictionRegistry
from glasswell.lineage.selector_registry import identity_selector_term
from glasswell.lineage.vintages import select_production
from glasswell.marts.cumulatives import CUMULATIVES_SCOPE
from glasswell.marts.well_pool_rollup import ADMITTED_NULL_SEMANTICS, POOL_GRAIN_ENTITY
from glasswell.status.source_health import source_health_data
from glasswell.units import metres_to_feet

router = APIRouter(tags=["wells"])

# The liquids basis is mandatory on every served liquids figure (lineage/envelope.py), and it
# is a per-jurisdiction decision: North Dakota folds condensate into oil, New Mexico measured
# 3,398 condensate filings and ruled the opposite. Serving one state's policy on another
# state's barrel is the R8 failure the sidecar exists to prevent, so both the basis and the
# rule that decided it are read from the registration the API-10 prefix resolves to.
LIQUIDS_STREAM = "oil"
WATER_BASIS = "water"
PRODUCTION_GRAIN = "production_grain"
SUM_OVER_POOLS = "sum_over_pools"
WELL_OBSERVED = "well_observed"
POOL_GRAIN_LEVEL = "well_completion_pool"

STREAM_COLUMNS = {"oil": "oil_bbl", "gas": "gas_mcf", "water": "water_bbl"}

# The allocated mart folds oil and condensate into one liquid stream, so the wire column it
# fills is the one a reader already knows. Water has no column at all in a jurisdiction whose
# regulator publishes none, and the absence is stated rather than served as an empty array.
ALLOCATED_STREAM_COLUMNS = {"liquid": "oil_bbl", "gas": "gas_mcf"}
ALLOCATED_STREAM_OF = {"oil": "liquid", "gas": "gas"}
# The rollup mart's own vocabulary, water included: New Mexico's regulator publishes a water
# stream at pool grain and the sum carries it, which the allocated mart's jurisdiction does not.
ROLLUP_STREAM_COLUMNS = {"liquid": "oil_bbl", "gas": "gas_mcf", "water": "water_bbl"}
ROLLUP_STREAM_OF = {"oil": "liquid", "gas": "gas", "water": "water"}
ALLOCATION_MART = "marts.tx_allocated_production"


def stream_basis(stream: str, state_code: str | None, *, registry: JurisdictionRegistry):
    """The basis sidecar for one stream in one jurisdiction. Liquids carry a policy; water is
    water everywhere; gas carries none. An unregistered state gets no liquids basis rather than
    another state's."""
    if stream == WATER_BASIS:
        return WATER_BASIS
    if stream != LIQUIDS_STREAM:
        return None
    row = registry.at_prefix(state_code)
    return row.liquids_basis if row is not None else None


def rollup_rule(state_code: str | None, *, registry: JurisdictionRegistry) -> str | None:
    return registry.rule_for(state_code, PRODUCTION_GRAIN)


_ROLLUP_SPEC = """
select spec from lineage.conformance_rules where rule_id = %(rule_id)s
"""


def rollup_series_rule(
    connection: psycopg.Connection, state_code: str | None, *, registry: JurisdictionRegistry
) -> str | None:
    """The grain rule that registers a served rollup, or None where none does.

    Two reads and not one: the registration says which grain decision is serving, and the
    decision's own spec says whether glasswell sums the pool filings. A jurisdiction that files
    at pool grain and registers no rollup answers None here and keeps the panel.
    """
    rule_id = rollup_rule(state_code, registry=registry)
    if rule_id is None:
        return None
    found = rows(connection, _ROLLUP_SPEC, {"rule_id": rule_id})
    if not found or found[0]["spec"].get("served_rollup") != SUM_OVER_POOLS:
        return None
    return rule_id
MONTH_FORMAT = r"^\d{4}-\d{2}$"

# The summed per-well series: a well's shares for a month, added at request time. It is stored
# nowhere -- a dual-lease wellbore has two rows at the well grain and _require_one raises on
# them -- so this query is the only place the figure exists, and api.respond is the only
# address it has.
_ALLOCATED_SERIES = """
select production_month, stream, sum(volume) as volume, min(unit) as unit,
       min(basis) as basis, count(*) as shares,
       sum(eligible_wells) as eligible_wells,
       array_agg(distinct allocation_class order by allocation_class) as classes,
       array_agg(distinct granularity order by granularity) as granularities,
       array_agg(distinct lease_key order by lease_key) as lease_keys,
       min(allocation_model_id) as allocation_model_id,
       min(allocation_rule_id) as allocation_rule_id,
       min(error_rule_id) as error_rule_id,
       bool_or(incomplete_window) as incomplete_window,
       min(membership_vintage) as membership_vintage,
       min(snapshot_vintage) as snapshot_vintage,
       min(derivation_id) as derivation_id
  from marts.tx_allocated_production
 where api10 = %(api10)s
 group by production_month, stream
 order by production_month
"""


def allocated_rows(
    connection: psycopg.Connection, api10: str, requested: Sequence[str], window
) -> list[dict[str, Any]]:
    """One summed point per month and mart stream, filtered to the streams asked for."""
    wanted = {ALLOCATED_STREAM_OF[name] for name in requested if name in ALLOCATED_STREAM_OF}
    return [
        row
        for row in rows(connection, _ALLOCATED_SERIES, {"api10": api10})
        if row["stream"] in wanted and _in_window(row["production_month"], window)
    ]


def _in_window(month: date, window: tuple[date | None, date | None]) -> bool:
    first, last = window
    return (first is None or month >= first) and (last is None or month <= last)


def _dominant(values: Sequence[str]) -> str:
    """The class the scalar reports, when the array beside it is the authoritative answer."""
    return sorted(values, key=lambda value: (-values.count(value), value))[0]


_VINTAGE_BOUNDS = """
select min(report_vintage) as earliest, max(report_vintage) as latest
  from canonical.production_monthly
 where api10 = %(api10)s
"""

# A released row is not gone, it is released at a knowledge time. An as-of read from before
# that time has to see it the way that date saw it, or the replay manufactures a fact (DIR-2).
_OPEN_AS_OF = """
   and (state = 'open'
        or (released_at_vintage is not null
            and %(as_of)s::date is not null
            and released_at_vintage > %(as_of)s::date))
"""

# D2: a month the regulator withheld is not a gap. It has no canonical row to serve, so the
# ledger is where the axis learns it exists at all.
_WITHHELD_MONTHS = """
select distinct (row_payload ->> 'production_month')::date as production_month, rule_id
  from lineage.quarantine_rows
 where source_id = 'nd_mpr_xlsx'
   and reason_code = 'confidential_withheld'
   and row_payload ->> 'api10' = %(api10)s
   and row_payload ->> 'production_month' is not null
""" + _OPEN_AS_OF

# D1 residue: a well-month whose pool filings the rule could not decompose, or one that has
# not been re-promoted at the as_of being read. The promoted row is not the well's production
# and is not served as if it were.
_MULTI_POOL_PENDING = """
select (row_payload ->> 'production_month')::date as production_month,
       row_payload ->> 'stream_canonical' as stream,
       min(rule_id) as rule_id,
       count(*) as filings,
       sum(nullif(row_payload ->> 'volume', '')::numeric) as ledger_volume,
       min(nullif(row_payload ->> 'unit', '')) as unit
  from lineage.quarantine_rows
 where source_id = 'nd_mpr_xlsx'
   and reason_code = 'key_collision'
   and row_payload ->> 'api10' = %(api10)s
   and row_payload ->> 'production_month' is not null
""" + _OPEN_AS_OF + """
 group by 1, 2
"""

class ErrorBounds(BaseModel):
    """4F.5 as amended: a bound, or a served statement that no transferable one exists.

    `not_measured` names the study that will close it rather than omitting the field, which
    makes the absence a resolvable fact instead of a gap a reader has to notice. A band
    measured on another regulator's leases over a horizon nobody has shown to match would be
    a naked number with a decoration on it.
    """

    model_config = ConfigDict(extra="forbid")

    outcome: Literal["not_measured", "measured"] = Field(
        description="Whether a transferable bound has been measured for this model."
    )
    measured_by_rule: str | None = Field(
        default=None, description="The rule that measures it, whether or not it has yet."
    )
    bed: str | None = Field(default=None, description="The jurisdiction it was measured on.")
    error_lo: str | None = Field(default=None, description="Lower bound, once measured.")
    error_hi: str | None = Field(default=None, description="Upper bound, once measured.")


class AllocationBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str | None = Field(
        description="The versioned artifact that computed every share in this series."
    )
    rule_id: str = Field(description="The R8 decision that admits a well-level figure here.")
    leases: list[str] = Field(
        description=(
            "Every lease this wellbore carries. The served series is the sum of its shares;"
            " each share is separately addressable at alloc.apply with the lease key."
        )
    )
    membership_vintage: str | None = Field(
        description="The crosswalk snapshot the shares were resolved against."
    )
    incomplete_from: str | None = Field(
        default=None,
        description=(
            "The first month inside the regulator's completeness lag. Months from here on are"
            " systematically under-filed, and a reader sees a decline rather than an"
            " incompleteness unless the chart says so."
        ),
    )
    error_bounds: ErrorBounds = Field(description="Whether the method's error is measured.")


class ProductionSeries(BaseModel):
    """Parallel arrays: `pm` is the shared month axis and every column aligns to it."""

    model_config = ConfigDict(extra="forbid")

    pm: list[str] = Field(
        description="Production months, YYYY-MM, ascending.",
        json_schema_extra={GLOSSARY_KEY: "gt_production_month"},
    )
    oil_bbl: list[str | None] | None = Field(
        default=None,
        description="Oil volumes in bbl as decimal strings; null where no report.",
        json_schema_extra={GLOSSARY_KEY: "gt_liquids_policy"},
    )
    oil_bbl_report_vintage: list[str | None] | None = Field(
        default=None, description="Report vintage used for each oil point."
    )
    oil_bbl_null_semantics: list[str] | None = Field(
        default=None,
        description=(
            "reported, reported_zero, no_report or withheld per point, plus"
            " multi_pool_pending where two filings share one pool label and no single row is"
            " the well's production, and lease_reported where the filing is the lease's and"
            " the point is a share of it rather than a report about this well."
        ),
    )
    oil_bbl_aggregation: list[str | None] | None = Field(
        default=None,
        description=(
            "sum_over_pools where the point is the exact sum of the well's pool rows under"
            " cr_nd_pool_rollup_1; null where the month is a single filing."
        ),
    )
    gas_mcf: list[str | None] | None = Field(
        default=None,
        description="Gas volumes in mcf.",
        json_schema_extra={GLOSSARY_KEY: "gt_stream"},
    )
    gas_mcf_report_vintage: list[str | None] | None = Field(
        default=None, description="Report vintage used for each gas point."
    )
    gas_mcf_null_semantics: list[str] | None = Field(
        default=None, description="Null semantics per gas point; same vocabulary as oil."
    )
    gas_mcf_aggregation: list[str | None] | None = Field(
        default=None, description="Aggregation per gas point; same vocabulary as oil."
    )
    # Three arrays beside the existing ones, and not a change to the scalar: the additive-only
    # freeze forbids changing a field's type, and a lease that crossed one to two eligible
    # wells produces a series that is partly well_observed and partly lease_allocated, which
    # one scalar cannot say.
    oil_bbl_granularity_by_month: list[str | None] | None = Field(
        default=None,
        description=(
            "well_observed or lease_allocated per oil point. Authoritative: the scalar"
            " `granularity` reports the series' dominant class."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_granularity"},
    )
    oil_bbl_allocation_class_by_month: list[str | None] | None = Field(
        default=None,
        description=(
            "observed_gas_well, observed_single_well_lease, allocated_equal_share,"
            " allocated_after_status_change or excluded_after_plug per oil point."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_allocation_allocation_v0"},
    )
    oil_bbl_eligible_wells_by_month: list[int | None] | None = Field(
        default=None,
        description=(
            "How many wells the lease volume was divided among, per oil point; null where the"
            " point sums shares from more than one lease and no single division produced it."
        ),
        json_schema_extra=not_a_figure(
            "Divisor. The count of wells a share was computed over is part of the method, not"
            " a measured quantity of anything."
        ),
    )
    oil_bbl_shares_by_month: list[int | None] | None = Field(
        default=None,
        description=(
            "How many lease shares this oil point is the sum of. One for all but the wellbores"
            " that carry more than one lease record; each share is addressable with its lease"
            " key at alloc.apply."
        ),
        json_schema_extra=not_a_figure(
            "Cardinality. The count of lease records a point was summed over is part of the"
            " method, not a measured quantity of anything; each share carries its own handle."
        ),
    )
    gas_mcf_granularity_by_month: list[str | None] | None = Field(
        default=None, description="Granularity per gas point; same vocabulary as oil.",
        json_schema_extra={GLOSSARY_KEY: "gt_granularity"},
    )
    gas_mcf_allocation_class_by_month: list[str | None] | None = Field(
        default=None, description="Allocation class per gas point; same vocabulary as oil.",
        json_schema_extra={GLOSSARY_KEY: "gt_allocation_allocation_v0"},
    )
    gas_mcf_shares_by_month: list[int | None] | None = Field(
        default=None, description="Lease shares per gas point; same vocabulary as oil.",
        json_schema_extra=not_a_figure(
            "Cardinality. The count of lease records a point was summed over is part of the"
            " method, not a measured quantity of anything; each share carries its own handle."
        ),
    )
    gas_mcf_eligible_wells_by_month: list[int | None] | None = Field(
        default=None,
        description="Divisor per gas point; same meaning as oil.",
        json_schema_extra=not_a_figure(
            "Divisor. The count of wells a share was computed over is part of the method, not"
            " a measured quantity of anything."
        ),
    )
    water_bbl: list[str | None] | None = Field(
        default=None,
        description="Water volumes in bbl.",
        json_schema_extra={GLOSSARY_KEY: "gt_stream"},
    )
    water_bbl_report_vintage: list[str | None] | None = Field(
        default=None, description="Report vintage used for each water point."
    )
    water_bbl_null_semantics: list[str] | None = Field(
        default=None, description="Null semantics per water point; same vocabulary as oil."
    )
    water_bbl_aggregation: list[str | None] | None = Field(
        default=None, description="Aggregation per water point; same vocabulary as oil."
    )


class Production(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    api10: str = Field(
        description="Ten-digit API well number.",
        json_schema_extra=not_a_figure(
            "Identifier. A 10-digit API number is an identity string, not a measurement."
        ),
    )
    source_id: str | None = Field(description="Source the series was promoted from.")
    granularity: str = Field(
        description="well_observed for ND regulator reports; never silently allocated.",
        json_schema_extra={GLOSSARY_KEY: "gt_granularity"},
    )
    reporting_level: str = Field(
        description=(
            "The level the source reported at: well, or well_completion_pool where the well"
            " filed in more than one pool and the series is their disclosed sum."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_granularity"},
    )
    streams: list[str] = Field(description="Streams present in this response.")
    series: ProductionSeries = Field(description="The parallel arrays the chart consumes.")
    lineage: dict[str, str] = Field(
        alias="_lineage",
        description=(
            "Dotted path to derivation handle (SB-07 §9.1b). One entry per column while a"
            " column has one derivation; one entry per point (`series.oil_bbl.0`) once its"
            " months were promoted from different workbooks."
        ),
    )
    units: dict[str, str] = Field(alias="_units", description="Dotted column path to unit.")
    basis: dict[str, str] = Field(
        alias="_basis", description="Dotted column path to liquids basis, where one applies."
    )
    allocation: AllocationBlock | None = Field(
        default=None,
        description=(
            "Present only where the series is an allocation. It names the model that computed"
            " it, the rule that admits it, the leases the shares came from, the crosswalk"
            " vintage they were resolved against, and whether a transferable error bound has"
            " been measured."
        ),
    )


def _labels(columns: list[str]) -> dict[str, str]:
    labels = {"/granularity": "gt_granularity", "/api10": "gt_api_10_api_12_api_14"}
    for column in columns:
        labels[f"/series/{column}"] = "gt_liquids_policy" if column == "oil_bbl" else "gt_stream"
        labels[f"/series/{column}_report_vintage"] = "gt_report_vintage"
        labels[f"/series/{column}_null_semantics"] = "gt_withheld"
    return labels


def _pool_labels(pools: list[dict[str, Any]]) -> dict[str, str]:
    """One key per pool actually present, because the client's lookup is exact-match.

    A `/pools/*/series/oil_bbl` key resolves for nobody: `web/src/api/envelope.ts:54-56` reads
    `meta.labels[pointer]` with no glob and no prefix walk, and teaching it globs means editing
    a frozen file. The loop is bounded by the pools a well filed in — one or two — and runs
    where the assembled list already is.
    """
    labels = {"/granularity": "gt_granularity", "/api10": "gt_api_10_api_12_api_14"}
    for index, pool in enumerate(pools):
        labels[f"/pools/{index}/well_completion_pool"] = "gt_pool"
        columns = [STREAM_COLUMNS[stream] for stream in pool["streams"]]
        labels |= {
            f"/pools/{index}{pointer}": term
            for pointer, term in _labels(columns).items()
            if pointer.startswith("/series/")
        }
    return labels


def _months(raw: str | None, name: str) -> date | None:
    if raw is None:
        return None
    try:
        year, month = raw.split("-")
        return date(int(year), int(month), 1)
    except ValueError:
        raise ProblemError(
            "validation_failed",
            detail=f"{name} must be a production month as YYYY-MM",
            errors=[{"pointer": f"/query/{name}", "code": "month_format", "detail": raw}],
        ) from None


def _state_code(connection, api10: str) -> str | None:
    found = rows(connection, RANKED_WELLS + " and api10 = %(api10)s", {"as_of": None,
                                                                       "api10": api10})
    return found[0]["state_code"] if found else None


@router.get(
    "/wells/{api10}/production",
    operation_id="get_well_production",
    summary="Monthly production for one well",
    description=(
        "Monthly produced volumes for one well, in the SB-07 §9.1(b) sidecar form:"
        " derivation handles in `_lineage`, units in `_units`, the liquids basis"
        " in `_basis`, and per-point `report_vintage` and `null_semantics` arrays."
        " ND publishes one workbook a month, so a month is promoted by its own derivation:"
        " `_lineage` keys a handle per point (`series.oil_bbl.0`) whenever the points of a"
        " column disagree, and each handle explains to the file that carries that month."
        " It keys per point for the same reason where one promotion filed a month more than"
        " once: a restatement is a second row and never an edit, so that point's handle also"
        " names the report vintage (`&rv=`) it was read at."
        " In North Dakota these are well-level regulator reports, so `granularity` is"
        " `well_observed` — nothing here is allocated. A series never silently mixes"
        " vintages: `as_of` selects the greatest report vintage at or before the date and"
        " every point says which one it used. `null_semantics` keeps a reported zero, an"
        " absent report and a withheld value apart; they are never collapsed into a gap."
        " A month the regulator withheld rides the axis with a null value."
        " A well that filed in more than one pool is served the exact sum of its pool rows,"
        " never a serve-time sum: the point's handle resolves to the aggregation derivation"
        " over those rows, `*_aggregation` reads `sum_over_pools`, `reporting_level` reads"
        " `well_completion_pool`, and `links.pools` carries the per-pool breakdown. Where two"
        " filings share one pool label the rule cannot say which is the well, so that point is"
        " withdrawn as multi_pool_pending instead. Where the regulator filed no per-well number"
        " at all and its grain rule registers a served rollup, the series is read from"
        " glasswell's own rollup mart: every point carries the refresh that produced it and its"
        " own selector, a production_summed_over_pools warning names the rule, and as_of is"
        " refused rather than answered with today's sum, because the mart holds one snapshot"
        " per key while the pool filings under it are bitemporal. meta.warnings names every"
        " case with the rule that decided it."
        " GOR and water cut are deliberately not served in this slice."
    ),
    response_model=EnvelopeModel[Production],
    openapi_extra={
        **request_example(path={"api10": EXAMPLE_API10}, query={"stream": ["oil"]}),
        **dataset(
            id="production",
            title="Production (per well)",
            group="wells",
            collection_pointer="",
            series_pointer="/series",
            row_projection={
                "axis": "/pm",
                "columns": ["/oil_bbl", "/gas_mcf", "/water_bbl"],
                "suffixes": ["_report_vintage", "_null_semantics", "_aggregation"],
            },
            anchors=["/api10", "/granularity", "/reporting_level"],
            row_id=["/pm"],
            facets=["stream", "from", "to"],
            columns={
                "default": ["/pm", "/oil_bbl", "/gas_mcf", "/water_bbl", "/granularity"],
                "sort": "/pm",
            },
            intro="nb_dataset_production",
            order=11,
        ),
        **semantics(
            as_of={
                "glossary": "gt_report_vintage",
                "so": (
                    "Selects the vintage of every point in the series. Two requests a month"
                    " apart can return different volumes for the same production month, and"
                    " both are correct."
                ),
            },
            stream={
                "glossary": "gt_stream",
                "so": (
                    "Repeat it to ask for more than one; omit it and you get oil, gas and"
                    " water. Dropping a stream drops its column, never a month — the shared"
                    " axis is the same either way, which is what keeps two streams comparable"
                    " point for point."
                ),
            },
            **{
                "from": {
                    "glossary": "gt_production_month",
                    "so": (
                        "Windows on the production month, not on the report vintage, so it"
                        " changes which months you see and never which restatement of them you"
                        " get. Pair it with as_of to hold both still."
                    ),
                },
                "to": {
                    "glossary": "gt_production_month",
                    "so": (
                        "The window's inclusive end, on the same production-month axis. A month"
                        " nobody filed is absent from the axis rather than present as a zero —"
                        " a gap in the series is a gap in the record."
                    ),
                },
            },
            normalization={
                "glossary": "gt_lateral",
                "so": (
                    "Divides every point by this well's lateral length in thousands of feet"
                    " and serves the result in `<unit>/kft`, with the length and the method"
                    " that measured it on the basis and one handle per column resolving both"
                    " the production and the geometry. It is a served arm rather than a"
                    " client division because a number divided in a browser keeps the"
                    " handle of the number it was divided from, which is a naked figure"
                    " wearing someone else's papers."
                ),
            },
            explain={
                "glossary": "gt_derivation_handle",
                "so": (
                    "ND promotes one workbook a month, so `_lineage` here keys a handle per"
                    " point and the chart's provenance is dozens of separate calls. This"
                    " returns them with the series, so a month that looks wrong is one hop"
                    " from the workbook that reported it."
                ),
            },
            explain_depth={
                "glossary": "gt_derivation_handle",
                "so": (
                    "Every point's chain is walked to the same depth, so raising it multiplies"
                    " by the number of distinct handles rather than by the number of months."
                    " Three reaches the promotion and its manifest for an observed series."
                ),
            },
        ),
    },
    responses=problem_responses(
        "not_found", "validation_failed", "as_of_out_of_range", "as_of_not_supported",
        "service_degraded"
    ),
)
def get_well_production(
    request: Request,
    connection: Connection,
    api10: Annotated[str, Path(description="Ten-digit API well number.", pattern=API10_PATTERN)],
    explain: ExplainEffect,
    as_of: AsOf = None,
    normalization: Annotated[
        Literal["per_lateral_ft"] | None,
        Query(
            description=(
                "Divide every point by the well's lateral length in thousands of feet and"
                " serve the result in `<unit>/kft`. Refused with the rule that decided it"
                " where the jurisdiction withholds the length, where no lateral is held, or"
                " where no compute CRS is registered for the well's basin: a normalised"
                " figure whose divisor nobody can name is a naked number."
            )
        ),
    ] = None,
    stream: Annotated[
        list[Literal["oil", "gas", "water"]] | None,
        Query(description="Stream to include; repeatable. Defaults to oil, gas and water."),
    ] = None,
    from_month: Annotated[
        str | None,
        Query(alias="from", description="First production month, YYYY-MM.", pattern=MONTH_FORMAT),
    ] = None,
    to_month: Annotated[
        str | None,
        Query(alias="to", description="Last production month, YYYY-MM.", pattern=MONTH_FORMAT),
    ] = None,
) -> JSONResponse:
    existence = {"as_of": None, "api10": api10}
    if not rows(connection, RANKED_WELLS + " and api10 = %(api10)s", existence):
        raise ProblemError("not_found", detail=f"no well {api10}")
    requested = list(stream or STREAM_COLUMNS)
    window = (_months(from_month, "from"), _months(to_month, "to"))

    bounds = rows(connection, _VINTAGE_BOUNDS, {"api10": api10})[0]
    if as_of is not None and bounds["earliest"] is not None and as_of < bounds["earliest"]:
        raise ProblemError(
            "as_of_out_of_range",
            detail=(
                f"as_of {as_of.isoformat()} precedes the earliest captured vintage"
                f" {bounds['earliest'].isoformat()} for this well"
            ),
        )

    registry = jurisdictions(connection)
    state_code = _state_code(connection, api10)
    divisor = None
    if normalization == PER_LATERAL_FT:
        basin = rows(connection, _WELL_BASIN, {"api10": api10})
        divisor = _lateral_divisor(
            connection,
            api10,
            basin=basin[0]["basin"] if basin else None,
            state_code=state_code,
            registry=registry,
            as_of=as_of,
        )
    # A lease-reporting jurisdiction that serves a well-level figure anyway is serving an
    # allocation, and the series comes from the mart rather than from canonical -- which could
    # not hold it: 020_production_entity_key.sql:43-46 admits no lease_allocated row.
    # Resolved at the current cut and not at the caller's `as_of`. Whether this jurisdiction
    # serves an allocated series is a fact about the registry now; asking it as of 2020 would
    # answer "no rule was published yet" and quietly fall through to the observed arm, which
    # would serve an empty envelope reading as "nothing was produced".
    allocated_rule = allocated_series_rule(connection, state_code)
    if allocated_rule is not None:
        if as_of is not None:
            # The mart holds one snapshot per key, so an older as_of would return the current
            # allocation labelled with the caller's date -- and the back-projection makes the
            # two differ by the whole well set. A refusal is a served class, not a silence.
            model_rule = registry.rule_for(state_code, CUMULATIVES_SCOPE)
            raise ProblemError(
                "as_of_not_supported",
                detail=(
                    f"as_of is not supported on this well series: {allocated_rule['rule_id']}"
                    f" admits an allocated figure and {model_rule} records"
                    " as_of_supported: false, because the mart holds one snapshot per key --"
                    " so an older date would be answered with today's allocation. The lease"
                    " series it is computed from is bitemporal and answers as_of."
                ),
            )
        if divisor is not None:
            # The allocated series is a share of a lease's filing, and dividing a share by this
            # well's lateral would read as a per-foot rate for a number the well did not
            # measure. The arm is refused rather than answered wrong.
            raise _refuse_normalisation(
                "this jurisdiction serves an allocated series"
                f" ({allocated_rule['rule_id']}), and an allocated share divided by this"
                " well's lateral is not a per-foot rate anybody measured"
            )
        return _allocated_response(
            request,
            connection,
            api10=api10,
            requested=requested,
            window=window,
            registry=registry,
            state_code=state_code,
            rule=allocated_rule,
            explain=explain,
        )

    # Bound rather than inlined: the same rows answer two questions, and the second one is
    # whether this well has a well-level series at all. `observed` narrows them to the streams
    # and the months the request asked for; the pool-grain disclosure is about the well.
    all_well_rows = select_production(
        connection, as_of=as_of, api10=api10, entity_type="well"
    )
    observed = _rows_in_window(all_well_rows, requested=requested, window=window)
    # A jurisdiction that files below the well and registers a served rollup has no well-grain
    # filing to observe and a sum glasswell performs and discloses. The mart rows are read
    # unwindowed for the reason the pool-grain guard is: a narrow window over a well the mart
    # covers is an empty window, not a well nothing rolls up.
    summed_rule = rollup_series_rule(connection, state_code, registry=registry)
    if summed_rule is not None and not all_well_rows:
        summed = _rollup_rows(connection, api10)
        if summed:
            if divisor is not None:
                # The allocated arm's refusal, one grain the other way and for the same reason.
                # Not live while New Mexico holds surface points only, and live the day a
                # pool-grain jurisdiction with laterals registers a rollup -- which this design
                # advertises as a spec key rather than a module.
                raise _refuse_normalisation(
                    "this jurisdiction serves a series summed over its pool filings"
                    f" ({summed_rule}), and a sum over pool filings divided by this well's"
                    " lateral is not a per-foot rate anybody measured"
                )
            return _summed_response(
                request,
                connection,
                api10=api10,
                requested=requested,
                window=window,
                registry=registry,
                state_code=state_code,
                rule_id=summed_rule,
                summed=summed,
                as_of=as_of,
                explain=explain,
            )
    # A lease-reporting jurisdiction has no observed well-level series. An empty envelope here
    # reads as "nothing was produced"; the disclosure says what is actually true (DIR-3).
    lease_reported = lease_reporting_rule(
        connection,
        state_code,
        valid_at=as_of,
        knowledge_at=as_of,
    )

    withheld = _withheld_months(connection, api10, window, as_of)
    pending = _multi_pool_pending(connection, api10, window, as_of)
    months = sorted({row["production_month"] for row in observed} | set(withheld))
    payload: dict[str, Any] = {"pm": [month_label(month) for month in months]}
    warnings: list[dict[str, Any]] = _withheld_warning(withheld)
    if lease_reported:
        warnings.append(pending_allocation(lease_reported))
    warnings.extend(
        _pool_grain_warning(
            connection,
            api10,
            state_code,
            observed,
            as_of=as_of,
            registry=registry,
            has_well_rows=bool(all_well_rows),
        )
    )
    columns: list[str] = []
    point_outputs: dict[str, dict[str, Any]] = {}
    restated = _restated_points(connection, api10)
    for name in STREAM_COLUMNS:
        if name not in requested:
            continue
        points = {row["production_month"]: row for row in observed if row["stream"] == name}
        if not points:
            continue
        column = STREAM_COLUMNS[name]
        columns.append(column)
        policy = stream_basis(name, state_code, registry=registry)
        derivations = {row["derivation_id"] for row in points.values()}
        if len(derivations) > 1:
            warnings.append(
                {
                    "code": "series_spans_derivations",
                    "detail": (
                        f"{len(derivations)} derivations contributed to this column;"
                        + (
                            " _lineage carries one handle per point"
                            if divisor is None
                            else " the normalised column is one response derivation citing"
                            " every one of them, so _lineage carries that handle and each"
                            " point's month names its own evidence row"
                        )
                    ),
                    "pointer": f"/series/{column}",
                }
            )
        held = {month: row for (month, stream), row in pending.items() if stream == name}
        warnings.extend(_pending_warning(held, column))
        first = next(iter(points.values()))
        # A month one promotion filed twice is two rows under one derivation id, so `pm` alone
        # under-specifies it and the point's ⌾ answered 422 on a served figure (visual M5).
        refiled = {
            month
            for month, row in points.items()
            if (row["derivation_id"], name, month) in restated
        }
        spans = len(derivations) > 1
        drawn = [None if month in held else _volume(points.get(month)) for month in months]
        unit = first["unit"] if divisor is None else f"{first['unit']}/kft"
        if divisor is not None:
            drawn = [_normalise(value, divisor) for value in drawn]
            # A response series may not carry per-point handles (provenance.py refuses them),
            # so the divided points are evidence rows on the response derivation instead: the
            # chart addresses a point as `<column handle>&pm=<month>`, and that selector has
            # to name an output somebody recorded. Each row names the promotion it divided.
            for month, value in zip(months, drawn, strict=True):
                if value is None:
                    continue
                point_outputs[f"api10={api10}&col={column}&pm={month_label(month)}"] = {
                    "value": value,
                    "unit": unit,
                    "derivation": points[month]["derivation_id"],
                }
        payload[column] = series(
            drawn,
            unit=unit,
            derivation=first["derivation_id"],
            selector=f"api10={api10}&col={column}",
            granularity=first["granularity"],
            # The divisor joins the basis rather than replacing it: a per-foot oil figure still
            # has to say oil means oil plus condensate, and a per-foot figure whose length
            # method is not on the wire is a number a reader cannot reproduce.
            basis=(
                policy
                if divisor is None
                else " · ".join(
                    part
                    for part in (policy, f"per lateral foot · {divisor.feet} ft · {divisor.method}")
                    if part
                )
            ),
            point_handles=(
                [
                    None
                    if month in held
                    else _point_handle(
                        api10, column, month, points.get(month), restated=month in refiled
                    )
                    for month in months
                ]
                if spans and divisor is None
                else None
            ),
            # One derivation covers the column, so its handle stands and only the refiled
            # months need the longer selector. Overriding the whole column would hand the
            # legend's own ⌾ one month's chain.
            point_overrides=(
                {
                    index: str(
                        _point_handle(api10, column, month, points[month], restated=True)
                    )
                    for index, month in enumerate(months)
                    if month in refiled
                }
                if refiled and not spans and divisor is None
                else None
            ),
        )
        payload[f"{column}_report_vintage"] = [
            iso(points[month]["report_vintage"]) if month in points else None for month in months
        ]
        payload[f"{column}_null_semantics"] = [
            _point_semantics(month, point=points.get(month), held=held, withheld=withheld)
            for month in months
        ]
        payload[f"{column}_aggregation"] = [
            None if month in held else _point_aggregation(points.get(month))
            for month in months
        ]
        warnings.extend(
            _aggregation_warning(
                points, column, api10=api10, state_code=state_code, registry=registry
            )
        )

    source_ids = sorted({row["source_id"] for row in observed})
    resolved = max((row["report_vintage"] for row in observed), default=None)
    aggregated = any(row["aggregation"] is not None for row in observed)
    data = {
        "api10": api10,
        "source_id": source_ids[0] if source_ids else None,
        "granularity": next((row["granularity"] for row in observed), "well_observed"),
        "reporting_level": "well_completion_pool" if aggregated else "well",
        "streams": [name for name in requested if STREAM_COLUMNS[name] in columns],
        "series": payload,
    }
    links = {"well": f"/v1/wells/{api10}"}
    if lease_reported:
        links["reporting_rule"] = f"/v1/conformance/{lease_reported['rule_id']}"
    grain_rule = rollup_rule(state_code, registry=registry)
    if aggregated and grain_rule:
        links["pools"] = f"/v1/wells/{api10}/production/pools"
        links["aggregation_rule"] = f"/v1/conformance/{grain_rule}"
    # The pool-grain arm, on the predicate `_pool_grain_warning` already computed and with no
    # new query: a well whose regulator files per completion pool has a pool series and a rule
    # that decided there is no rollup, so the Pools section is gated on a link like every other
    # section rather than on the client recognising a warning code.
    if grain_rule and any(
        warning["code"] == "production_reported_at_pool_grain" for warning in warnings
    ):
        links["pools"] = f"/v1/wells/{api10}/production/pools"
        links["reporting_rule"] = f"/v1/conformance/{grain_rule}"
    # WC-P2-4: which rule decides whether this jurisdiction carries a per-well cumulative at
    # all. A client sentence about that absence would be a jurisdiction literal; the link is
    # the registry's own answer.
    cumulatives = registry.rule_for(state_code, CUMULATIVES_SCOPE)
    if cumulatives:
        links["cumulatives_rule"] = f"/v1/conformance/{cumulatives}"
    if divisor is not None:
        # The handle has to change with the number: a client-side division carrying the served
        # handle would be a naked number wearing someone else's papers. The response derivation
        # cites the production promotions AND the geometry promotions, so one chain resolves
        # both inputs -- which is the only version of this feature that survives "where did
        # that number come from".
        data = register_response_figures(
            connection,
            data,
            dataset="api.well_production",
            operation_id="get_well_production",
            locator=request.url.path,
            partition={
                "api10": api10,
                "normalization": PER_LATERAL_FT,
                "as_of": iso(resolved) or "latest",
            },
            input_derivations=sorted(
                {row["derivation_id"] for row in observed} | set(divisor.derivations)
            ),
            correlation_id=request.state.request_id,
            rule_ids=[divisor.rule_id, divisor.floor_rule_id],
            point_outputs=point_outputs,
        )
        links["length_rule"] = f"/v1/conformance/{divisor.rule_id}"
    return enveloped(
        request,
        data,
        as_of=resolved,
        as_of_requested=iso(as_of) or "latest",
        labels=_labels(columns),
        source_freshness=_freshness(connection, source_ids),
        warnings=warnings,
        links=links,
        explain=inline_for(connection, explain),
    )


PER_LATERAL_FT = "per_lateral_ft"

# The basin the compute CRS is chosen by, from the well's current row.
_WELL_BASIN = """
select basin from canonical.wells_latest where api10 = %(api10)s
"""

_LATERALS = """
select s.derivation_id, {length_metres} as length_m
  from canonical.well_spatial s
 where s.api10 = %(api10)s and s.geom_type = 'lateral'
"""


class LateralDivisor(BaseModel):
    """The lateral length a normalised point was divided by, and what produced it."""

    model_config = ConfigDict(extra="forbid")

    feet: Decimal
    derivations: tuple[str, ...]
    rule_id: str
    floor_rule_id: str
    method: str
    compute_crs: str


def _refuse_normalisation(detail: str) -> ProblemError:
    """One refusal shape: the reason and, where one exists, the rule that decided it."""
    return ProblemError("validation_failed", detail=detail)


def _lateral_floor(connection: psycopg.Connection) -> tuple[Decimal, str]:
    """R8: the floor is a row. cr_ff_fluid_intensity registers it for the same division and
    completions reads it at request time; this reads the same row rather than restating it."""
    try:
        rule = rule_for_family(
            load_rules(connection, source_id=FRACFOCUS_SOURCE_ID, stage="conform"),
            INTENSITY_FAMILY,
        )
    except LookupError:
        raise _refuse_normalisation(
            f"no rule in family {INTENSITY_FAMILY} is registered, so the lateral floor this"
            " division needs is undefined and no normalised figure is served: a registry gap,"
            " not a fact about the well"
        ) from None
    return Decimal(str(rule.spec["min_lateral_ft"])), rule.rule_id


def _lateral_divisor(
    connection: psycopg.Connection,
    api10: str,
    *,
    basin: str | None,
    state_code: str | None,
    registry: JurisdictionRegistry,
    as_of: date | None,
) -> LateralDivisor:
    """The well's lateral length, or a refusal naming the rule that withholds it.

    Every arm here is a jurisdiction the card must not offer the control on: New Mexico holds
    surface points only, Montana registers a length_scope rule, and a basin with no compute
    CRS has no length to divide by. The client hides the control from the same facts; this is
    what answers a caller who asks anyway.
    """
    withheld = registry.rule_for(state_code, LENGTH_SCOPE)
    if withheld:
        raise _refuse_normalisation(
            f"no lateral length is served for this jurisdiction: {withheld} withholds it, so"
            " there is no divisor to normalise by"
        )
    try:
        method = resolve_length_method(
            connection, basin=basin, valid_at=as_of, knowledge_at=as_of
        )
    except LengthRuleUnregistered:
        raise _refuse_normalisation(
            f"no compute CRS is registered for basin {basin!r}, so this well's lateral length"
            " is not served and cannot be a divisor"
        ) from None
    laterals = rows(
        connection,
        _LATERALS.format(length_metres=method.metres_sql("s.geom")),
        {"api10": api10},
    )
    if not laterals:
        raise _refuse_normalisation(
            "this well holds no lateral geometry, so there is no length to normalise by"
        )
    feet = metres_to_feet(
        sum((Decimal(str(row["length_m"])) for row in laterals), Decimal(0))
    ).quantize(Decimal("0.01"))
    floor, floor_rule = _lateral_floor(connection)
    if feet < floor:
        raise _refuse_normalisation(
            f"the lateral measures {feet} ft, below the {floor} ft floor {floor_rule}"
            " registers for this division: below it the divisor is a stub rather than a"
            " lateral"
        )
    return LateralDivisor(
        feet=feet,
        derivations=tuple(sorted({str(row["derivation_id"]) for row in laterals})),
        rule_id=method.rule_id,
        floor_rule_id=floor_rule,
        method=method.method,
        compute_crs=method.compute_crs,
    )


def _normalise(value: str | None, divisor: LateralDivisor) -> str | None:
    """Per thousand feet, quantised once at the serving edge like every other figure here.

    Values ride as strings for the reason every figure does: a float round-trip is not
    reproducible, and the division is where that would first bite.
    """
    if value is None:
        return None
    return str((Decimal(value) / (divisor.feet / Decimal(1000))).quantize(Decimal("0.001")))


def _allocated_response(
    request: Request,
    connection: psycopg.Connection,
    *,
    api10: str,
    requested: Sequence[str],
    window: tuple[date | None, date | None],
    registry: JurisdictionRegistry,
    state_code: str | None,
    rule: Mapping[str, Any],
    explain: Any,
) -> JSONResponse:
    """The allocated series, with every point saying that it is one.

    Three parallel arrays ride beside the existing `*_null_semantics` ones because the scalar
    `granularity` cannot describe a series that is partly observed and partly allocated: a
    lease that crossed one to two eligible wells produces exactly that, and the additive-only
    freeze forbids changing the scalar's type. The scalar keeps its value and says the array
    is authoritative.
    """
    points = allocated_rows(connection, api10, requested, window)
    if not points:
        return _allocation_not_built(
            request,
            connection,
            api10=api10,
            rule=rule,
            # The rule that computes the share, read from the registration rather than written
            # here: which rule a jurisdiction's shares are computed under is a mapping
            # decision, and one that lives in a serving module is stranded the day a
            # supersession moves it (gate-tx RV-3). The mart's own rows carry it where there
            # are rows; this is the arm that has none to read.
            model_rule=registry.rule_for(state_code, CUMULATIVES_SCOPE),
            explain=explain,
        )
    months = sorted({row["production_month"] for row in points})
    payload: dict[str, Any] = {"pm": [month_label(month) for month in months]}
    warnings: list[dict[str, Any]] = []
    columns: list[str] = []
    granularities: list[str] = []
    incomplete: list[str] = []
    # One evidence row per point the chart can address, because the chart addresses every one:
    # its handle button appends the month to the column selector, and a selector nobody
    # recorded resolves to an error panel rather than to the lease row (B1).
    point_outputs: dict[str, dict[str, Any]] = {}

    for mart_stream, column in ALLOCATED_STREAM_COLUMNS.items():
        by_month = {row["production_month"]: row for row in points if row["stream"] == mart_stream}
        if not by_month:
            continue
        columns.append(column)
        first = next(iter(by_month.values()))
        column_granularity = _dominant(
            [value for row in by_month.values() for value in row["granularities"]]
        )
        granularities.append(column_granularity)
        values = [
            _decimal(by_month[month]["volume"]) if month in by_month else None
            for month in months
        ]
        for month, value in zip(months, values, strict=True):
            point_outputs[f"api10={api10}&col={column}&pm={month_label(month)}"] = {
                "value": value,
                "unit": first["unit"],
            }
        payload[column] = series(
            values,
            unit=first["unit"],
            derivation=first["derivation_id"],
            selector=f"api10={api10}&col={column}",
            granularity=column_granularity,
            basis=first["basis"],
            allocation_model_id=first["allocation_model_id"],
        )
        payload[f"{column}_report_vintage"] = [
            iso(by_month[month]["snapshot_vintage"]) if month in by_month else None
            for month in months
        ]
        # The subject here is the lease-month, and saying so is the difference between a
        # filing and an observation of this well: `reported` beside a share says the well's
        # month was reported, three words from the mark that says it was computed (M1).
        payload[f"{column}_null_semantics"] = [
            "lease_reported" if month in by_month else None for month in months
        ]
        payload[f"{column}_aggregation"] = [None for _ in months]
        payload[f"{column}_granularity_by_month"] = [
            _dominant(by_month[month]["granularities"]) if month in by_month else None
            for month in months
        ]
        payload[f"{column}_allocation_class_by_month"] = [
            _dominant(by_month[month]["classes"]) if month in by_month else None
            for month in months
        ]
        payload[f"{column}_shares_by_month"] = [
            int(by_month[month]["shares"]) if month in by_month else None for month in months
        ]
        payload[f"{column}_eligible_wells_by_month"] = [
            _divisor(by_month[month]) if month in by_month else None for month in months
        ]
        if any(row["incomplete_window"] for row in by_month.values()):
            incomplete.append(column)

    first_incomplete = (
        min(row["production_month"] for row in points if row["incomplete_window"])
        if incomplete
        else None
    )
    if first_incomplete is not None:
        warnings.append(
            {
                "code": "production_incomplete_window",
                "detail": (
                    f"months from {month_label(first_incomplete)} are inside the"
                    f" completeness lag {rule['rule_id']} records; the regulator states"
                    " production records are substantially complete after about six months"
                ),
                "pointer": "/series",
            }
        )
    leases = sorted({key for row in points for key in row["lease_keys"]})
    if len(leases) > 1:
        warnings.append(
            {
                "code": "well_carries_more_than_one_lease",
                "detail": (
                    f"this wellbore is on {len(leases)} leases and the served series is the sum"
                    " of its shares; each share is separately addressable at alloc.apply"
                ),
                "pointer": "/series",
            }
        )

    error_rule = next((row["error_rule_id"] for row in points), None)
    data: dict[str, Any] = {
        "api10": api10,
        "source_id": None,
        "granularity": _dominant(granularities) if granularities else "lease_allocated",
        "reporting_level": "lease",
        "streams": [
            name for name in requested
            if ALLOCATED_STREAM_COLUMNS.get(ALLOCATED_STREAM_OF.get(name, "")) in columns
        ],
        "series": payload,
        "allocation": {
            "model_id": next((row["allocation_model_id"] for row in points), None),
            "rule_id": rule["rule_id"],
            "leases": leases,
            "membership_vintage": iso(
                next((row["membership_vintage"] for row in points), None)
            ),
            "incomplete_from": month_label(first_incomplete) if incomplete else None,
            # 4F.5 as P8 amends it: a served statement that no transferable bound exists,
            # naming the study that will close it, rather than a band measured on another
            # regulator's leases over a horizon nobody has shown to match.
            "error_bounds": {"outcome": "not_measured", "measured_by_rule": error_rule},
        },
    }
    # The summed per-well series is computed here and stored nowhere: a dual-lease wellbore has
    # two mart rows at the well grain, and _require_one raises on them. So the figure is
    # addressed the way every other request-computed one is -- at api.respond, under
    # response_output, with a persisted row per point -- and the mart's own derivation stays the
    # address of the per-lease shares it was summed from.
    data = register_response_figures(
        connection,
        data,
        dataset="api.tx_production",
        operation_id="get_well_production",
        locator=request.url.path,
        partition={"api10": api10, "streams": "+".join(sorted(requested))},
        input_derivations=sorted({row["derivation_id"] for row in points}),
        correlation_id=request.state.request_id,
        rule_ids=[rule["rule_id"], *([error_rule] if error_rule else [])],
        point_outputs=point_outputs,
    )
    # Two rules, two links, because they answer two questions: `allocation_rule` is the R8
    # decision that admits a well-level figure here at all, and the model rule is the one that
    # computed the share. The mart rows cite the second and the cumulative coverage block cites
    # the second, so a reader following only the first landed on the grain decision (H-19).
    model_rule = next((row["allocation_rule_id"] for row in points), None)
    links = {
        "well": f"/v1/wells/{api10}",
        "allocation_rule": f"/v1/conformance/{rule['rule_id']}",
    }
    if model_rule:
        links["allocation_model_rule"] = f"/v1/conformance/{model_rule}"
    if error_rule:
        links["error_bounds_rule"] = f"/v1/conformance/{error_rule}"
    return enveloped(
        request,
        data,
        as_of=next((row["snapshot_vintage"] for row in points), None),
        as_of_requested="latest",
        labels=_labels(columns),
        source_freshness=_freshness(connection, ["tx_pdq_dsv"]),
        warnings=warnings,
        links=links,
        explain=inline_for(connection, explain),
    )


_ROLLUP_SERIES = """
select production_month, stream, volume, unit, days_produced, pools_summed, derivation_id
  from marts.well_pool_rollup
 where api10 = %(api10)s
 order by production_month, stream
"""

# The filings the sum was taken over, for the two facts the mart does not carry: which source
# published them, and the vintage they were read at. Read from canonical rather than spelled,
# so a second pool-grain jurisdiction needs no entry anywhere.
_ROLLUP_FILINGS = """
select coalesce(array_agg(distinct source_id), '{}') as source_ids,
       max(report_vintage) as report_vintage
  from canonical.production_monthly
 where api10 = %(api10)s and entity_type = 'well_completion_pool'
"""

# The same filings per month and stream, for the two facts that are per point and were served
# as one scalar each: whether every filing under a summed month was an explicit zero, and the
# vintage that month was read at. The ranking window is the mart's own, so a restated month is
# described by the restatement the mart summed rather than beside it.
_ROLLUP_FILING_MONTHS = """
with ranked as (
    select p.production_month, p.stream, p.null_semantics, p.source_id, p.report_vintage,
           row_number() over (
               partition by p.entity_type, p.entity_key, p.production_month, p.stream,
                            p.source_id
               order by p.report_vintage desc) as vintage_rank
      from canonical.production_monthly p
     where p.api10 = %(api10)s and p.entity_type = %(entity_type)s
)
select production_month, stream,
       count(*) filter (where admitted) as admitted,
       bool_and(null_semantics = 'reported_zero') filter (where admitted) as all_zero,
       max(report_vintage) filter (where admitted) as report_vintage
  from (select production_month, stream, null_semantics, report_vintage,
               null_semantics = any(%(admitted)s) as admitted
          from ranked where vintage_rank = 1) rank_one
 group by production_month, stream
"""


def _rollup_rows(connection: psycopg.Connection, api10: str) -> list[dict[str, Any]]:
    return rows(connection, _ROLLUP_SERIES, {"api10": api10})


@dataclass(frozen=True)
class _FilingMonth:
    """What the pool filings under one summed month and stream say about it."""

    admitted: int
    all_zero: bool
    vintage: date | None


def _rollup_filing_months(
    connection: psycopg.Connection, api10: str
) -> dict[tuple[date, str], _FilingMonth]:
    read = rows(
        connection,
        _ROLLUP_FILING_MONTHS,
        {
            "api10": api10,
            "entity_type": POOL_GRAIN_ENTITY,
            "admitted": list(ADMITTED_NULL_SEMANTICS),
        },
    )
    return {
        (row["production_month"], row["stream"]): _FilingMonth(
            admitted=row["admitted"],
            all_zero=bool(row["all_zero"]),
            vintage=row["report_vintage"],
        )
        for row in read
        if row["stream"] in ROLLUP_STREAM_OF
    }


def _summed_semantics(filed: _FilingMonth | None, *, summed: bool) -> str:
    """The four states the card's legend advertises, on the summed arm too.

    A month with no mart row is not a hole in the axis: either its filings were all withheld,
    which is why the sum admits none of them, or the stream filed nothing that month. Serving
    null for both painted the band in the gas red with nothing in the key to read it by.
    """
    if not summed:
        if filed is None:
            return "no_report"
        return "withheld" if filed.admitted == 0 else "no_report"
    return "reported_zero" if filed is not None and filed.all_zero else "reported"


def summed_over_pools(api10: str, rule_id: str) -> dict[str, Any]:
    """The disclosure a summed series carries: what it is, and what it is not.

    It is deliberately not one of the codes `card.ts` replaces the chart with a panel for. The
    chart is drawn and this sentence sits above it, because the figure exists and what a reader
    needs is to know who computed it.
    """
    return {
        "code": "production_summed_over_pools",
        "detail": (
            f"This well's regulator files production per completion pool and filed no per-well"
            f" number, so the series is glasswell's exact sum of those filings ({rule_id}),"
            " disclosed as a sum and promoted into no canonical row. One derivation addresses"
            " the whole series rather than one per month, and each point carries its own"
            f" selector. The filings are at /v1/wells/{api10}/production/pools and the rule is"
            f" at /v1/conformance/{rule_id}."
        ),
        "pointer": "/series",
        "rule_id": rule_id,
    }


def _summed_response(
    request: Request,
    connection: psycopg.Connection,
    *,
    api10: str,
    requested: Sequence[str],
    window: tuple[date | None, date | None],
    registry: JurisdictionRegistry,
    state_code: str | None,
    rule_id: str,
    summed: Sequence[Mapping[str, Any]],
    as_of: date | None,
    explain: Any,
) -> JSONResponse:
    """The per-well series a pool-grain jurisdiction is served, read from the rollup mart.

    `as_of` is refused rather than answered, for the reason the allocated arm refuses it: the
    mart holds one snapshot per key, so an older date would be answered with today's sum
    wearing the caller's date. The pool filings underneath it are bitemporal and answer as_of.
    """
    if as_of is not None:
        raise ProblemError(
            "as_of_not_supported",
            detail=(
                f"as_of is not supported on this well series: {rule_id} admits a sum glasswell"
                " performs in marts.well_pool_rollup, which holds one snapshot per key, so an"
                " older date would be answered with today's sum. The pool filings it is summed"
                f" from are at /v1/wells/{api10}/production/pools and answer as_of."
            ),
        )
    wanted = {ROLLUP_STREAM_OF[name] for name in requested if name in ROLLUP_STREAM_OF}
    points = [
        row
        for row in summed
        if row["stream"] in wanted
        and (window[0] is None or row["production_month"] >= window[0])
        and (window[1] is None or row["production_month"] <= window[1])
    ]
    filings = rows(connection, _ROLLUP_FILINGS, {"api10": api10})[0]
    per_month = _rollup_filing_months(connection, api10)
    months = sorted({row["production_month"] for row in points})
    payload: dict[str, Any] = {"pm": [month_label(month) for month in months]}
    warnings: list[dict[str, Any]] = [summed_over_pools(api10, rule_id)]
    columns: list[str] = []

    for mart_stream, column in ROLLUP_STREAM_COLUMNS.items():
        by_month = {row["production_month"]: row for row in points if row["stream"] == mart_stream}
        if not by_month:
            continue
        columns.append(column)
        first = next(iter(by_month.values()))
        stream = next(name for name, value in ROLLUP_STREAM_OF.items() if value == mart_stream)
        payload[column] = series(
            [_decimal(by_month[month]["volume"]) if month in by_month else None
             for month in months],
            unit=first["unit"],
            derivation=first["derivation_id"],
            selector=f"api10={api10}&col={column}",
            # North Dakota's own composed token for the same arithmetic: its promotion sums
            # the pool filings into a well row and serves well_observed beside
            # aggregation = sum_over_pools. The vocabulary is the store's (M-5), so a fourth
            # token would have to be a canonical value no canonical row may carry.
            granularity=WELL_OBSERVED,
            basis=stream_basis(stream, state_code, registry=registry),
            # One derivation for the series and one selector per point: the handle is coarser
            # than a per-month promotion's and the address is not, so a point still resolves to
            # the refresh that produced it and to the filings that refresh read.
            point_handles=[
                format_handle(
                    by_month[month]["derivation_id"],
                    f"api10={api10}&col={column}&pm={month:%Y-%m}",
                )
                if month in by_month
                else None
                for month in months
            ],
        )
        payload[f"{column}_report_vintage"] = [
            iso(per_month[(month, stream)].vintage) if month in by_month else None
            for month in months
        ]
        payload[f"{column}_null_semantics"] = [
            _summed_semantics(per_month.get((month, stream)), summed=month in by_month)
            for month in months
        ]
        payload[f"{column}_aggregation"] = [
            SUM_OVER_POOLS if month in by_month else None for month in months
        ]

    data: dict[str, Any] = {
        "api10": api10,
        "source_id": (filings["source_ids"] or [None])[0],
        "granularity": WELL_OBSERVED,
        # The level the source reported at, which is what the field's own description says: the
        # OCD filed per completion pool and the series is their disclosed sum.
        "reporting_level": POOL_GRAIN_LEVEL,
        "streams": [
            name for name in requested
            if ROLLUP_STREAM_COLUMNS.get(ROLLUP_STREAM_OF.get(name, "")) in columns
        ],
        "series": payload,
    }
    links = {
        "well": f"/v1/wells/{api10}",
        "pools": f"/v1/wells/{api10}/production/pools",
        "aggregation_rule": f"/v1/conformance/{rule_id}",
    }
    cumulatives = registry.rule_for(state_code, CUMULATIVES_SCOPE)
    if cumulatives:
        links["cumulatives_rule"] = f"/v1/conformance/{cumulatives}"
    return enveloped(
        request,
        data,
        as_of=filings["report_vintage"],
        as_of_requested="latest",
        labels=_labels(columns),
        source_freshness=_freshness(connection, sorted(filings["source_ids"] or [])),
        warnings=warnings,
        links=links,
        explain=inline_for(connection, explain),
    )


def pending_allocation_detail(grain_rule: str, model_rule: str | None) -> str:
    """The disclosure's sentence, guarded the way the link beside it is guarded.

    `model_rule` is read from the registration's cumulative scope, a different lookup from the
    grain decision that routed the well here, so a registration carrying the second and not the
    first resolves None -- and an interpolated None served "None is the rule that computes it"
    (gate-tx D-1).
    """
    computes = (
        f" {model_rule} is the rule"
        " that computes it; the lease volumes it splits are promoted at their"
        " native grain and are served as the lease's own."
        if model_rule
        else " The lease volumes are promoted at their native grain and are served as the"
        " lease's own."
    )
    return (
        "This well's regulator reports production at the lease"
        f" ({grain_rule}), and the allocated mart holds no rows on this"
        " instance, so no well-level figure is served rather than an empty series"
        " that would read as nothing produced." + computes
    )


def _allocation_not_built(
    request: Request,
    connection: psycopg.Connection,
    *,
    api10: str,
    rule: Mapping[str, Any],
    model_rule: str | None,
    explain: Any,
) -> JSONResponse:
    """The disclosure an instance owes while its allocated mart is empty.

    Between `make deploy` and the end of the manual load the mart holds nothing, and the
    allocated arm served 200 with an empty series, `granularity: lease_allocated`, a null
    model id and a null `measured_by_rule` -- an envelope that reads as "nothing was
    produced", which is the exact outcome the disclosure below exists to prevent, and an
    absence served without naming the rule that closes it, which 4F.5 as amended forbids
    (gate-tx H-10).
    """
    data: dict[str, Any] = {
        "api10": api10,
        "source_id": None,
        # The grain the regulator files at, which is what is true when nothing is computed
        # yet. Claiming `lease_allocated` would describe a share that does not exist.
        "granularity": "lease_reported",
        "reporting_level": "lease",
        "streams": [],
        "series": {"pm": []},
        "allocation": None,
    }
    return enveloped(
        request,
        data,
        as_of=None,
        as_of_requested="latest",
        labels=_labels([]),
        source_freshness=_freshness(connection, ["tx_pdq_dsv"]),
        warnings=[
            {
                "code": "production_pending_allocation",
                "detail": pending_allocation_detail(rule["rule_id"], model_rule),
                "pointer": "/production",
            }
        ],
        links={
            "well": f"/v1/wells/{api10}",
            "allocation_rule": f"/v1/conformance/{rule['rule_id']}",
            **(
                {"allocation_model_rule": f"/v1/conformance/{model_rule}"}
                if model_rule
                else {}
            ),
        },
        explain=inline_for(connection, explain),
    )


def _decimal(value: Any) -> str | None:
    """Decimal strings, as the observed arm serves them: a float would round a barrel away."""
    return None if value is None else str(Decimal(value))


def _divisor(row: Mapping[str, Any]) -> int | None:
    """The wells this month's volume was divided among, or None where no one division made it.

    A wellbore on two leases sums two shares, and summing their divisors states a division
    that never happened -- 3 wells and 1 well reported as "over 4 wells" (M2). The per-lease
    divisor is on each share's own `lk` handle, which is where a divided figure is addressed.
    """
    return int(row["eligible_wells"]) if int(row["shares"]) == 1 else None


class PoolProduction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    well_completion_pool: str = Field(
        description="Pool the operator filed this series under.",
        json_schema_extra={GLOSSARY_KEY: "gt_pool"},
    )
    entity_key: str = Field(description="S-E entity key of this completion: api10:pool.")
    streams: list[str] = Field(description="Streams present for this pool.")
    series: ProductionSeries = Field(description="The parallel arrays for this pool alone.")


class ProductionPools(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    api10: str = Field(
        description="Ten-digit API well number.",
        json_schema_extra=not_a_figure(
            "Identifier. A 10-digit API number is an identity string, not a measurement."
        ),
    )
    granularity: str = Field(
        description="well_observed; a pool filing is an observation, not an allocation.",
        json_schema_extra={GLOSSARY_KEY: "gt_granularity"},
    )
    reporting_level: str = Field(description="well_completion_pool for every row here.")
    pools: list[PoolProduction] = Field(description="One entry per pool the well filed in.")
    lineage: dict[str, str] = Field(
        alias="_lineage", description="Dotted path to derivation handle (SB-07 §9.1b)."
    )
    units: dict[str, str] = Field(alias="_units", description="Dotted column path to unit.")
    basis: dict[str, str] = Field(
        alias="_basis", description="Dotted column path to liquids basis, where one applies."
    )


@router.get(
    "/wells/{api10}/production/pools",
    operation_id="get_well_production_pools",
    summary="Per-pool production for one well",
    description=(
        "The pool rows behind a well series. A well completed in two pools files one row per"
        " pool per month, and each is a first-class `well_completion_pool` entity under the"
        " S-E key; `/v1/wells/{api10}/production` serves their sum with the aggregation"
        " disclosed, and this sub-resource serves the rows that sum was taken over. A well"
        " that filed in exactly one pool has no breakdown to give and returns an empty list —"
        " its own series already is the pool's."
    ),
    response_model=EnvelopeModel[ProductionPools],
    openapi_extra={
        **request_example(path={"api10": EXAMPLE_API10}),
        **dataset(
            id="production_pools",
            title="Production by pool",
            group="wells",
            collection_pointer="/pools",
            series_pointer="/series",
            row_projection={
                "axis": "/pm",
                "columns": ["/oil_bbl", "/gas_mcf", "/water_bbl"],
                # No `_aggregation`: a pool row is a filing, not a sum over pools, so this
                # operation never emits one and a declared column would render empty forever.
                "suffixes": ["_report_vintage", "_null_semantics"],
            },
            anchors=["/api10", "/granularity", "/reporting_level"],
            row_id=["/well_completion_pool", "/pm"],
            facets=["stream"],
            columns={
                "default": [
                    "/well_completion_pool",
                    "/pm",
                    "/oil_bbl",
                    "/gas_mcf",
                    "/water_bbl",
                    "/granularity",
                ],
                "sort": "/well_completion_pool",
            },
            intro="nb_dataset_production_pools",
            order=12,
        ),
        **semantics(
            as_of={
                "glossary": "gt_report_vintage",
                "so": (
                    "Selects the vintage each pool row is read at. A restatement can move one"
                    " pool's month and leave the other's alone, so pools that do not add up to"
                    " the well's series are usually two vintages being compared rather than an"
                    " arithmetic error."
                ),
            },
            stream={
                "glossary": "gt_stream",
                "so": (
                    "Filters the columns inside every pool at once — there is no way to ask for"
                    " oil from one pool and gas from another. A pool that filed nothing for the"
                    " requested stream keeps its row and loses the column."
                ),
            },
            explain={
                "glossary": "gt_derivation_handle",
                "so": (
                    "Inlines the chain behind every pool column under `_explain`. ND files one"
                    " workbook per month, so a pool column can carry a handle per point rather"
                    " than one per series; where the response holds more handles than one"
                    " /v1/explain call carries, it says how many it left out rather than"
                    " trimming quietly."
                ),
            },
            explain_depth={
                "glossary": "gt_derivation_handle",
                "so": (
                    "A pool point resolves to its month's promotion and that month's workbook,"
                    " so three levels reaches the manifest. The cost multiplies per pool, per"
                    " stream and — under per-point handles — per month, so this is the surface"
                    " where a shallower depth pays."
                ),
            },
        ),
    },
    responses=problem_responses(
        "not_found", "validation_failed", "as_of_out_of_range", "service_degraded"
    ),
)
def get_well_production_pools(
    request: Request,
    connection: Connection,
    api10: Annotated[str, Path(description="Ten-digit API well number.", pattern=API10_PATTERN)],
    explain: ExplainEffect,
    as_of: AsOf = None,
    stream: Annotated[
        list[Literal["oil", "gas", "water"]] | None,
        Query(description="Stream to include; repeatable. Defaults to oil, gas and water."),
    ] = None,
) -> JSONResponse:
    existence = {"as_of": None, "api10": api10}
    if not rows(connection, RANKED_WELLS + " and api10 = %(api10)s", existence):
        raise ProblemError("not_found", detail=f"no well {api10}")
    registry = jurisdictions(connection)
    state_code = _state_code(connection, api10)
    requested = list(stream or STREAM_COLUMNS)
    observed = _rows_in_window(
        select_production(
            connection, as_of=as_of, api10=api10, entity_type="well_completion_pool"
        ),
        requested=requested,
        window=(None, None),
    )

    pools: list[dict[str, Any]] = []
    for pool in sorted({row["well_completion_pool"] for row in observed}):
        rows_for_pool = [row for row in observed if row["well_completion_pool"] == pool]
        months = sorted({row["production_month"] for row in rows_for_pool})
        payload: dict[str, Any] = {"pm": [month_label(month) for month in months]}
        present: list[str] = []
        for name in STREAM_COLUMNS:
            points = {
                row["production_month"]: row
                for row in rows_for_pool
                if row["stream"] == name
            }
            if not points:
                continue
            column = STREAM_COLUMNS[name]
            present.append(name)
            first = next(iter(points.values()))
            entity_key = first["entity_key"]
            handles = [
                _pool_handle(entity_key, column, month, points.get(month)) for month in months
            ]
            payload[column] = series(
                [_volume(points.get(month)) for month in months],
                unit=first["unit"],
                derivation=first["derivation_id"],
                selector=f"{identity_selector_term('entity_key', entity_key)}&col={column}",
                granularity=first["granularity"],
                basis=stream_basis(name, state_code, registry=registry),
                point_handles=handles if len(set(handles)) > 1 else None,
            )
            payload[f"{column}_report_vintage"] = [
                iso(points[month]["report_vintage"]) if month in points else None
                for month in months
            ]
            payload[f"{column}_null_semantics"] = [
                _point_semantics(month, point=points.get(month), held={}, withheld={})
                for month in months
            ]
        pools.append(
            {
                "well_completion_pool": pool,
                "entity_key": next(row["entity_key"] for row in rows_for_pool),
                "streams": present,
                "series": payload,
            }
        )

    source_ids = sorted({row["source_id"] for row in observed})
    return enveloped(
        request,
        {
            "api10": api10,
            "granularity": "well_observed",
            "reporting_level": "well_completion_pool",
            "pools": pools,
        },
        as_of=max((row["report_vintage"] for row in observed), default=None),
        as_of_requested=iso(as_of) or "latest",
        labels=_pool_labels(pools),
        source_freshness=_freshness(connection, source_ids),
        links={
            "well": f"/v1/wells/{api10}",
            "production": f"/v1/wells/{api10}/production",
            **(
                {"aggregation_rule": f"/v1/conformance/{grain}"}
                if (grain := rollup_rule(state_code, registry=registry))
                else {}
            ),
        },
        explain=inline_for(connection, explain),
    )


def _pool_handle(
    entity_key: str, column: str, month: date, row: dict[str, Any] | None
) -> str | None:
    if row is None:
        return None
    return format_handle(
        row["derivation_id"],
        f"{identity_selector_term('entity_key', entity_key)}&col={column}&pm={month:%Y-%m}",
    )


def _rows_in_window(
    found: list[dict[str, Any]],
    *,
    requested: list[str],
    window: tuple[date | None, date | None],
) -> list[dict[str, Any]]:
    return [
        row
        for row in found
        if row["stream"] in requested
        and (window[0] is None or row["production_month"] >= window[0])
        and (window[1] is None or row["production_month"] <= window[1])
    ]


def _point_semantics(
    month: date,
    *,
    point: dict[str, Any] | None,
    held: dict[date, dict[str, Any]],
    withheld: dict[date, str],
) -> str:
    """Why this point reads as it does: three regulator facts plus one serving state."""
    if month in held:
        return "multi_pool_pending"
    if point is None:
        return "withheld" if month in withheld else "no_report"
    return point["null_semantics"]


def _point_aggregation(point: dict[str, Any] | None) -> str | None:
    return None if point is None else point["aggregation"]


def _aggregation_warning(
    points: Mapping[date, dict[str, Any]],
    column: str,
    *,
    api10: str,
    state_code: str | None,
    registry: JurisdictionRegistry,
) -> list[dict[str, Any]]:
    """DIR-3: a summed figure says it is summed, names the rule, and offers the breakdown."""
    summed = sorted(month for month, row in points.items() if row["aggregation"] is not None)
    rule = rollup_rule(state_code, registry=registry)
    if not summed or not rule:
        return []
    months = ", ".join(month_label(month) for month in summed)
    return [
        {
            "code": "pools_aggregated",
            "detail": (
                f"{months}: this API-10 filed in more than one pool, and the value served is"
                f" the exact sum of those pool rows under {rule}. Days produced are the"
                " maximum over the pools, never their sum. The per-pool breakdown is at"
                f" /v1/wells/{api10}/production/pools and the rule is at"
                f" /v1/conformance/{rule}."
            ),
            "pointer": f"/series/{column}",
        }
    ]


_POOL_GRAIN_ROWS = """
select count(*) from canonical.production_monthly
 where api10 = %(api10)s and entity_type = 'well_completion_pool'
   and (%(as_of)s::date is null or report_vintage <= %(as_of)s::date)
"""


def _pool_grain_warning(
    connection,
    api10: str,
    state_code: str | None,
    observed: Sequence[Mapping[str, Any]],
    *,
    as_of: date | None,
    registry: JurisdictionRegistry,
    has_well_rows: bool,
) -> list[dict[str, Any]]:
    """An empty well-level series over a well that filed at pool grain is not "no production".

    New Mexico promotes only well_completion_pool rows and rolls nothing up to the well, so
    without this the card would render an empty chart for a producing well — the same DIR-3
    failure `pending_allocation` exists to prevent one jurisdiction upstream. The rule that
    decided it is named so the reader can resolve it.

    `has_well_rows` is the whole of what this is really asking. `observed` is windowed and the
    pool-row count is not, so a narrow window emptied one while the other stayed positive and a
    North Dakota well with 408 well-grain rows was told that its regulator files per completion
    pool and glasswell performs no rollup. It has a well-level series; the request asked about
    twelve months it does not cover.
    """
    rule = rollup_rule(state_code, registry=registry)
    if observed or has_well_rows or not rule:
        return []
    if not rows(connection, _POOL_GRAIN_ROWS, {"api10": api10, "as_of": as_of})[0]["count"]:
        return []
    return [
        {
            "code": "production_reported_at_pool_grain",
            "detail": (
                f"This well's regulator files production per completion pool and glasswell"
                f" performs no rollup to the well ({rule}), so no well-level series has been"
                f" observed. The pool series is at /v1/wells/{api10}/production/pools and the"
                f" rule is at /v1/conformance/{rule}."
            ),
            "pointer": "/series",
        }
    ]


def _pending_warning(held: dict[date, dict[str, Any]], column: str) -> list[dict[str, Any]]:
    """D1: say which months are withdrawn, how much the ledger holds, and under which rule."""
    if not held:
        return []
    months = ", ".join(month_label(month) for month in sorted(held))
    filings = sum(row["filings"] for row in held.values())
    volume = sum(row["ledger_volume"] or 0 for row in held.values())
    unit = next((row["unit"] for row in held.values() if row["unit"]), "")
    rules = ", ".join(sorted({str(row["rule_id"]) for row in held.values()}))
    return [
        {
            "code": "multi_pool_pending",
            "detail": (
                f"{months}: this API-10 filed in more than one pool, so no single row is the"
                f" well's production. {filings} further pool filing(s) holding {volume} {unit}"
                f" are quarantined as key_collision under {rules}; the promoted row is withheld"
                " here rather than served as the well. The payloads are in /v1/quarantine."
            ),
            "pointer": f"/series/{column}",
        }
    ]


def _multi_pool_pending(
    connection: psycopg.Connection,
    api10: str,
    window: tuple[date | None, date | None],
    as_of: date | None,
) -> dict[tuple[date, str], dict[str, Any]]:
    return {
        (row["production_month"], row["stream"]): row
        for row in rows(connection, _MULTI_POOL_PENDING, {"api10": api10, "as_of": as_of})
        if (window[0] is None or row["production_month"] >= window[0])
        and (window[1] is None or row["production_month"] <= window[1])
    }


def _withheld_warning(withheld: dict[date, str]) -> list[dict[str, Any]]:
    if not withheld:
        return []
    months = ", ".join(month_label(month) for month in sorted(withheld))
    rules = ", ".join(sorted(set(withheld.values())))
    return [
        {
            "code": "months_withheld",
            "detail": (
                f"{len(withheld)} month(s) are withheld by the regulator and ride the axis with"
                f" a null value: {months}. Recorded by {rules}; the rows are in /v1/quarantine"
                " with their payloads."
            ),
            "pointer": "/series/pm",
        }
    ]


def _withheld_months(
    connection: psycopg.Connection,
    api10: str,
    window: tuple[date | None, date | None],
    as_of: date | None,
) -> dict[date, str]:
    """Months the ledger holds as withheld, mapped to the rule that recorded the withholding."""
    return {
        row["production_month"]: row["rule_id"] or "an unattributed rule"
        for row in rows(connection, _WITHHELD_MONTHS, {"api10": api10, "as_of": as_of})
        if (window[0] is None or row["production_month"] >= window[0])
        and (window[1] is None or row["production_month"] <= window[1])
    }


def _volume(row: dict[str, Any] | None) -> str | None:
    return None if row is None else str(row["volume"])


def _point_handle(
    api10: str,
    column: str,
    month: date,
    row: dict[str, Any] | None,
    *,
    restated: bool = False,
) -> str | None:
    """D3: the point's own promotion, addressed by the month it reports (SB-07 §9.3).

    `restated` adds the report vintage, which is the rest of the row's key where one promotion
    filed the month more than once: without it the selector identifies two rows and refuses.
    """
    if row is None:
        return None
    selector = f"api10={api10}&col={column}&pm={month:%Y-%m}"
    if restated:
        selector += f"&rv={row['report_vintage']:%Y-%m-%d}"
    return format_handle(row["derivation_id"], selector)


_RESTATED_POINTS = """
select derivation_id, stream, production_month
  from canonical.production_monthly
 where entity_type = 'well' and api10 = %(api10)s and entity_key = %(api10)s
 group by derivation_id, stream, production_month
having count(*) > 1
"""


def _restated_points(
    connection: psycopg.Connection, api10: str
) -> set[tuple[str, str, date]]:
    """Every (promotion, stream, month) a selector of `api10&col&pm` would answer twice."""
    with connection.cursor() as cursor:
        cursor.execute(_RESTATED_POINTS, {"api10": api10})
        return {(row[0], row[1], row[2]) for row in cursor.fetchall()}


def _freshness(connection: psycopg.Connection, source_ids: list[str]) -> dict[str, Any]:
    if not source_ids:
        return {}
    _, freshness = source_health_data(
        connection,
        observed_at=datetime.now(UTC),
        source_ids=source_ids,
    )
    return freshness
