"""Monthly production as SB-07 §9.1(b) sidecar series: one handle per column, vintages
per point, and the three null semantics kept apart."""

from __future__ import annotations

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
from glasswell.api.routers.wells import API10_PATTERN, RANKED_WELLS
from glasswell.lineage.envelope import series
from glasswell.lineage.ids import format_handle
from glasswell.lineage.vintages import select_production

router = APIRouter(tags=["wells"])

# cr_nd_liquids_policy_1 states the basis; its code_ref executor is unimplemented in this
# slice, so the string is pinned here and a contract test holds it to the seeded rule.
ND_LIQUIDS_BASIS = "oil+condensate"

STREAM_COLUMNS = {"oil": "oil_bbl", "gas": "gas_mcf", "water": "water_bbl"}
STREAM_BASIS = {"oil": ND_LIQUIDS_BASIS, "water": "water", "gas": None}
MONTH_FORMAT = r"^\d{4}-\d{2}$"

_NULL_SEMANTICS = """
select production_month, stream, source_id, report_vintage, null_semantics
  from canonical.production_monthly
 where api10 = %(api10)s
"""

_VINTAGE_BOUNDS = """
select min(report_vintage) as earliest, max(report_vintage) as latest
  from canonical.production_monthly
 where api10 = %(api10)s
"""

# D2: a month the regulator withheld is not a gap. It has no canonical row to serve, so the
# ledger is where the axis learns it exists at all.
_WITHHELD_MONTHS = """
select distinct (row_payload ->> 'production_month')::date as production_month, rule_id
  from lineage.quarantine_rows
 where source_id = 'nd_mpr_xlsx'
   and reason_code = 'confidential_withheld'
   and state = 'open'
   and row_payload ->> 'api10' = %(api10)s
   and row_payload ->> 'production_month' is not null
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
        default=None, description="reported, reported_zero, no_report or withheld, per point."
    )
    gas_mcf: list[str | None] | None = Field(default=None, description="Gas volumes in mcf.")
    gas_mcf_report_vintage: list[str | None] | None = Field(
        default=None, description="Report vintage used for each gas point."
    )
    gas_mcf_null_semantics: list[str] | None = Field(
        default=None, description="Null semantics per gas point."
    )
    water_bbl: list[str | None] | None = Field(default=None, description="Water volumes in bbl.")
    water_bbl_report_vintage: list[str | None] | None = Field(
        default=None, description="Report vintage used for each water point."
    )
    water_bbl_null_semantics: list[str] | None = Field(
        default=None, description="Null semantics per water point."
    )


class Production(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    api10: str = Field(description="Ten-digit API well number.")
    source_id: str | None = Field(description="Source the series was promoted from.")
    granularity: str = Field(
        description="well_observed for ND regulator reports; never silently allocated.",
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

    observed = [
        row
        for row in select_production(connection, as_of=as_of, api10=api10)
        if row["stream"] in requested
        and (window[0] is None or row["production_month"] >= window[0])
        and (window[1] is None or row["production_month"] <= window[1])
    ]
    semantics = {
        (row["production_month"], row["stream"], row["source_id"], row["report_vintage"]):
            row["null_semantics"]
        for row in rows(connection, _NULL_SEMANTICS, {"api10": api10})
    }

    withheld = _withheld_months(connection, api10, window)
    months = sorted({row["production_month"] for row in observed} | set(withheld))
    payload: dict[str, Any] = {"pm": [month_label(month) for month in months]}
    warnings: list[dict[str, Any]] = _withheld_warning(withheld)
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
        first = next(iter(points.values()))
        spans = len(derivations) > 1
        payload[column] = series(
            [_volume(points.get(month)) for month in months],
            unit=first["unit"],
            derivation=first["derivation_id"],
            selector=f"api10={api10}&col={column}",
            granularity=first["granularity"],
            basis=STREAM_BASIS[name],
            point_handles=(
                [_point_handle(api10, column, month, points.get(month)) for month in months]
                if spans
                else None
            ),
        )
        payload[f"{column}_report_vintage"] = [
            iso(points[month]["report_vintage"]) if month in points else None for month in months
        ]
        payload[f"{column}_null_semantics"] = [
            semantics.get(
                (
                    month,
                    name,
                    points[month]["source_id"],
                    points[month]["report_vintage"],
                ),
                "reported",
            )
            if month in points
            else ("withheld" if month in withheld else "no_report")
            for month in months
        ]

    source_ids = sorted({row["source_id"] for row in observed})
    resolved = max((row["report_vintage"] for row in observed), default=None)
    data = {
        "api10": api10,
        "source_id": source_ids[0] if source_ids else None,
        "granularity": next((row["granularity"] for row in observed), "well_observed"),
        "streams": [name for name in requested if STREAM_COLUMNS[name] in columns],
        "series": payload,
    }
    return enveloped(
        request,
        data,
        as_of=resolved,
        as_of_requested=iso(as_of) or "latest",
        labels=_labels(columns),
        source_freshness=_freshness(connection, source_ids),
        warnings=warnings,
        links={"well": f"/v1/wells/{api10}"},
    )


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
    connection: psycopg.Connection, api10: str, window: tuple[date | None, date | None]
) -> dict[date, str]:
    """Months the ledger holds as withheld, mapped to the rule that recorded the withholding."""
    return {
        row["production_month"]: row["rule_id"] or "an unattributed rule"
        for row in rows(connection, _WITHHELD_MONTHS, {"api10": api10})
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
