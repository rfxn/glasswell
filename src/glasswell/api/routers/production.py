"""Monthly production as SB-07 §9.1(b) sidecar series: one handle per column, vintages
per point, and the three null semantics kept apart."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Annotated, Any, Literal

import psycopg
from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import AsOf, Connection, rows, today
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import EXAMPLE_API10, GLOSSARY_KEY, request_example
from glasswell.api.responses import EnvelopeModel, enveloped, freshness_state, iso, month_label
from glasswell.api.routers.wells import API10_PATTERN, RANKED_WELLS, pending_allocation
from glasswell.lineage.conformance import lease_reporting_rule
from glasswell.lineage.envelope import series
from glasswell.lineage.ids import format_handle
from glasswell.lineage.vintages import select_production

router = APIRouter(tags=["wells"])

# cr_nd_liquids_policy_1 states the basis; its code_ref executor is unimplemented in this
# slice, so the string is pinned here and a contract test holds it to the seeded rule.
ND_LIQUIDS_BASIS = "oil+condensate"

# cr_nd_pool_rollup_1 legislates the sum a well figure carries when it filed in two pools. Its
# id is pinned here for the same reason as the basis above, and held to the seeded row and to
# glasswell.ingest.nd_mpr by test_pool_rollup_rule_is_the_one_the_promotion_used.
ROLLUP_RULE = "cr_nd_pool_rollup_1"

STREAM_COLUMNS = {"oil": "oil_bbl", "gas": "gas_mcf", "water": "water_bbl"}
STREAM_BASIS = {"oil": ND_LIQUIDS_BASIS, "water": "water", "gas": None}
MONTH_FORMAT = r"^\d{4}-\d{2}$"

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

_FRESHNESS = """
select source_id,
       max(fetch_vintage) as retrieval_vintage,
       (select max(v.vintage_date) from lineage.vintages v where v.source_id = m.source_id)
           as declared_vintage
  from lineage.manifests m
 where source_id = any(%(source_ids)s)
 group by source_id
"""


class ProductionSeries(BaseModel):
    """Parallel arrays: `pm` is the shared month axis and every column aligns to it."""

    model_config = ConfigDict(extra="forbid")

    pm: list[str] = Field(description="Production months, YYYY-MM, ascending.")
    oil_bbl: list[str | None] | None = Field(
        default=None, description="Oil volumes in bbl as decimal strings; null where no report."
    )
    oil_bbl_report_vintage: list[str | None] | None = Field(
        default=None, description="Report vintage used for each oil point."
    )
    oil_bbl_null_semantics: list[str] | None = Field(
        default=None,
        description=(
            "reported, reported_zero, no_report or withheld per point, plus"
            " multi_pool_pending where two filings share one pool label and no single row is"
            " the well's production."
        ),
    )
    oil_bbl_aggregation: list[str | None] | None = Field(
        default=None,
        description=(
            "sum_over_pools where the point is the exact sum of the well's pool rows under"
            " cr_nd_pool_rollup_1; null where the month is a single filing."
        ),
    )
    gas_mcf: list[str | None] | None = Field(default=None, description="Gas volumes in mcf.")
    gas_mcf_report_vintage: list[str | None] | None = Field(
        default=None, description="Report vintage used for each gas point."
    )
    gas_mcf_null_semantics: list[str] | None = Field(
        default=None, description="Null semantics per gas point; same vocabulary as oil."
    )
    gas_mcf_aggregation: list[str | None] | None = Field(
        default=None, description="Aggregation per gas point; same vocabulary as oil."
    )
    water_bbl: list[str | None] | None = Field(default=None, description="Water volumes in bbl.")
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

    api10: str = Field(description="Ten-digit API well number.")
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


def _labels(columns: list[str]) -> dict[str, str]:
    labels = {"/granularity": "gt_granularity", "/api10": "gt_api_10_api_12_api_14"}
    for column in columns:
        labels[f"/series/{column}"] = "gt_liquids_policy" if column == "oil_bbl" else "gt_stream"
        labels[f"/series/{column}_report_vintage"] = "gt_report_vintage"
        labels[f"/series/{column}_null_semantics"] = "gt_withheld"
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
        " withdrawn as multi_pool_pending instead. meta.warnings names every case with the"
        " rule that decided it."
        " GOR and water cut are deliberately not served in this slice."
    ),
    response_model=EnvelopeModel[Production],
    openapi_extra=request_example(path={"api10": EXAMPLE_API10}, query={"stream": ["oil"]}),
    responses=problem_responses(
        "not_found", "validation_failed", "as_of_out_of_range", "service_degraded"
    ),
)
def get_well_production(
    request: Request,
    connection: Connection,
    api10: Annotated[str, Path(description="Ten-digit API well number.", pattern=API10_PATTERN)],
    as_of: AsOf = None,
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

    observed = _rows_in_window(
        select_production(connection, as_of=as_of, api10=api10, entity_type="well"),
        requested=requested,
        window=window,
    )
    # A lease-reporting jurisdiction has no observed well-level series. An empty envelope here
    # reads as "nothing was produced"; the disclosure says what is actually true (DIR-3).
    lease_reported = lease_reporting_rule(connection, _state_code(connection, api10))

    withheld = _withheld_months(connection, api10, window, as_of)
    pending = _multi_pool_pending(connection, api10, window, as_of)
    months = sorted({row["production_month"] for row in observed} | set(withheld))
    payload: dict[str, Any] = {"pm": [month_label(month) for month in months]}
    warnings: list[dict[str, Any]] = _withheld_warning(withheld)
    if lease_reported:
        warnings.append(pending_allocation(lease_reported))
    columns: list[str] = []
    for name in STREAM_COLUMNS:
        if name not in requested:
            continue
        points = {row["production_month"]: row for row in observed if row["stream"] == name}
        if not points:
            continue
        column = STREAM_COLUMNS[name]
        columns.append(column)
        derivations = {row["derivation_id"] for row in points.values()}
        if len(derivations) > 1:
            warnings.append(
                {
                    "code": "series_spans_derivations",
                    "detail": (
                        f"{len(derivations)} derivations contributed to this column;"
                        " _lineage carries one handle per point"
                    ),
                    "pointer": f"/series/{column}",
                }
            )
        held = {month: row for (month, stream), row in pending.items() if stream == name}
        warnings.extend(_pending_warning(held, column))
        first = next(iter(points.values()))
        spans = len(derivations) > 1
        payload[column] = series(
            [None if month in held else _volume(points.get(month)) for month in months],
            unit=first["unit"],
            derivation=first["derivation_id"],
            selector=f"api10={api10}&col={column}",
            granularity=first["granularity"],
            basis=STREAM_BASIS[name],
            point_handles=(
                [
                    None
                    if month in held
                    else _point_handle(api10, column, month, points.get(month))
                    for month in months
                ]
                if spans
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
        warnings.extend(_aggregation_warning(points, column, api10=api10))

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
    if aggregated:
        links["pools"] = f"/v1/wells/{api10}/production/pools"
        links["aggregation_rule"] = f"/v1/conformance/{ROLLUP_RULE}"
    return enveloped(
        request,
        data,
        as_of=resolved,
        as_of_requested=iso(as_of) or "latest",
        labels=_labels(columns),
        source_freshness=_freshness(connection, source_ids),
        warnings=warnings,
        links=links,
    )


class PoolProduction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    well_completion_pool: str = Field(description="Pool the operator filed this series under.")
    entity_key: str = Field(description="S-E entity key of this completion: api10:pool.")
    streams: list[str] = Field(description="Streams present for this pool.")
    series: ProductionSeries = Field(description="The parallel arrays for this pool alone.")


class ProductionPools(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    api10: str = Field(description="Ten-digit API well number.")
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
    openapi_extra=request_example(path={"api10": EXAMPLE_API10}),
    responses=problem_responses(
        "not_found", "validation_failed", "as_of_out_of_range", "service_degraded"
    ),
)
def get_well_production_pools(
    request: Request,
    connection: Connection,
    api10: Annotated[str, Path(description="Ten-digit API well number.", pattern=API10_PATTERN)],
    as_of: AsOf = None,
    stream: Annotated[
        list[Literal["oil", "gas", "water"]] | None,
        Query(description="Stream to include; repeatable. Defaults to oil, gas and water."),
    ] = None,
) -> JSONResponse:
    existence = {"as_of": None, "api10": api10}
    if not rows(connection, RANKED_WELLS + " and api10 = %(api10)s", existence):
        raise ProblemError("not_found", detail=f"no well {api10}")
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
                selector=f"entity_key={entity_key}&col={column}",
                granularity=first["granularity"],
                basis=STREAM_BASIS[name],
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
        labels={"/granularity": "gt_granularity", "/api10": "gt_api_10_api_12_api_14"},
        source_freshness=_freshness(connection, source_ids),
        links={
            "well": f"/v1/wells/{api10}",
            "production": f"/v1/wells/{api10}/production",
            "aggregation_rule": f"/v1/conformance/{ROLLUP_RULE}",
        },
    )


def _pool_handle(
    entity_key: str, column: str, month: date, row: dict[str, Any] | None
) -> str | None:
    if row is None:
        return None
    return format_handle(
        row["derivation_id"], f"entity_key={entity_key}&col={column}&pm={month:%Y-%m}"
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
    points: Mapping[date, dict[str, Any]], column: str, *, api10: str
) -> list[dict[str, Any]]:
    """DIR-3: a summed figure says it is summed, names the rule, and offers the breakdown."""
    summed = sorted(month for month, row in points.items() if row["aggregation"] is not None)
    if not summed:
        return []
    months = ", ".join(month_label(month) for month in summed)
    return [
        {
            "code": "pools_aggregated",
            "detail": (
                f"{months}: this API-10 filed in more than one pool, and the value served is"
                f" the exact sum of those pool rows under {ROLLUP_RULE}. Days produced are the"
                " maximum over the pools, never their sum. The per-pool breakdown is at"
                f" /v1/wells/{api10}/production/pools and the rule is at"
                f" /v1/conformance/{ROLLUP_RULE}."
            ),
            "pointer": f"/series/{column}",
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


def _point_handle(api10: str, column: str, month: date, row: dict[str, Any] | None) -> str | None:
    """D3: the point's own promotion, addressed by the month it reports (SB-07 §9.3)."""
    if row is None:
        return None
    return format_handle(row["derivation_id"], f"api10={api10}&col={column}&pm={month:%Y-%m}")


def _freshness(connection: psycopg.Connection, source_ids: list[str]) -> dict[str, Any]:
    if not source_ids:
        return {}
    now = today()
    return {
        row["source_id"]: {
            "retrieval_vintage": iso(row["retrieval_vintage"]),
            "declared_vintage": iso(row["declared_vintage"]),
            "state": freshness_state(row["retrieval_vintage"], today=now),
        }
        for row in rows(connection, _FRESHNESS, {"source_ids": source_ids})
    }
