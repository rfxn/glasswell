"""Per-well cumulative oil, gas and water, served beside the record they are a total of."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Path, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import AsOf, Connection, ExplainEffect, rows
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
    FigureModel,
    enveloped,
    inline_for,
    iso,
    month_label,
)
from glasswell.api.routers.health import source_health_data
from glasswell.api.routers.wells import API10_PATTERN
from glasswell.lineage.envelope import collect_handles, distinct_handles, figure
from glasswell.lineage.explain import MAX_HANDLES
from glasswell.lineage.ids import format_handle
from glasswell.marts.cumulatives import (
    LIQUIDS_RULE,
    NEVER_REPORTED,
    NULL_SEMANTICS_RULE,
    ROLLUP_RULE,
    STATE_API_PREFIXES,
)

router = APIRouter(tags=["wells"])

# The mart's stream names on the wire, matching api/routers/production.py:51 so one well's
# two surfaces do not spell the same quantity differently.
STREAM_COLUMNS = {"liquid": "oil_bbl", "gas": "gas_mcf", "water": "water_bbl"}
COUNT_UNIT = "months"

_CUMULATIVES = """
select c.api10, c.state_code, c.stream, c.cum_volume, c.unit, c.basis, c.months_reported,
       c.months_reported_zero, c.months_no_report_stored, c.months_withheld_stored,
       c.months_absent, c.span_months, c.first_month, c.last_month, c.coverage_outcome,
       c.snapshot_vintage, c.derivation_id,
       coalesce(w.months_withheld, 0) as months_withheld_quarantined,
       coalesce(w.rule_ids, '{}'::text[]) as withholding_rule_ids
  from marts.well_cumulatives c
  left join marts.well_withholding w on w.api10 = c.api10
 where c.api10 = %(api10)s
"""

# Whether canonical already holds filings this snapshot has not absorbed. The comparison is on
# the knowledge axis, not the production axis: a later production month is only a divergence
# once a report vintage newer than the snapshot carries it.
_BEHIND_SERIES = """
select max(report_vintage) as latest_vintage,
       count(distinct production_month)
           filter (where report_vintage > %(snapshot)s) as later_months,
       max(production_month) filter (where report_vintage > %(snapshot)s) as latest_month
  from canonical.production_monthly_latest
 where api10 = %(api10)s and entity_type = 'well'
"""

_SOURCES = """
select distinct source_id
  from canonical.production_monthly_latest
 where api10 = %(api10)s and entity_type = 'well'
 order by source_id
"""

LABELS = {
    "/api10": "gt_api_10_api_12_api_14",
    "/granularity": "gt_granularity",
    "/snapshot_vintage": "gt_report_vintage",
    "/cumulative/oil_bbl": "gt_liquids_policy",
    "/cumulative/gas_mcf": "gt_stream",
    "/cumulative/water_bbl": "gt_stream",
    "/months_withheld": "gt_withheld",
    "/coverage": "gt_cumulative_production",
}


class StreamCoverage(BaseModel):
    """The record one total is taken over: four counts that add up to the span."""

    model_config = ConfigDict(extra="forbid")

    months_reported: int = Field(description="Months the source filed a value for.")
    months_reported_zero: int = Field(description="Months the source filed a zero for.")
    months_no_report: int = Field(
        description="Months with no filing: a stored no_report row, or no row at all."
    )
    months_withheld: int = Field(
        description="Months held back by the regulator, stored or quarantined."
    )
    span_months: int = Field(description="Months from the first filed month to the last.")
    first_month: str | None = Field(description="First month of the span, YYYY-MM.")
    last_month: str | None = Field(description="Last month of the span, YYYY-MM.")
    coverage_complete: bool = Field(
        description="False wherever a month of the span was not filed as a value or a zero."
    )


class CumulativeStreams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oil_bbl: FigureModel | None = Field(
        description="Cumulative liquids, oil plus condensate; null where none was filed.",
        json_schema_extra={GLOSSARY_KEY: "gt_liquids_policy"},
    )
    gas_mcf: FigureModel | None = Field(
        description="Cumulative gas; null where none was filed.",
        json_schema_extra={GLOSSARY_KEY: "gt_stream"},
    )
    water_bbl: FigureModel | None = Field(
        description="Cumulative produced water; null where none was filed.",
        json_schema_extra={GLOSSARY_KEY: "gt_stream"},
    )


class Coverage(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    oil_bbl: StreamCoverage
    gas_mcf: StreamCoverage
    water_bbl: StreamCoverage
    lineage: dict[str, str] = Field(
        alias="_lineage",
        description="Stream to derivation handle (SB-07 §9.1b); one handle per stream.",
    )
    units: dict[str, str] = Field(alias="_units", description="Stream to count unit.")


class WellCumulatives(BaseModel):
    api10: str = Field(
        description="Ten-digit API well number.",
        json_schema_extra=not_a_figure(
            "Identifier. A 10-digit API number is an identity string, not a measurement."
        ),
    )
    granularity: str = Field(
        description="well_observed; these are regulator filings summed, never allocated.",
        json_schema_extra={GLOSSARY_KEY: "gt_granularity"},
    )
    snapshot_vintage: date = Field(
        description="Knowledge vintage this mart snapshot was built at.",
        json_schema_extra={GLOSSARY_KEY: "gt_report_vintage"},
    )
    coverage_outcome: str = Field(
        description="observed, or never_reported where the well has filed nothing at all."
    )
    cumulative: CumulativeStreams | None = Field(
        description="The three totals; null where the well has never filed anything."
    )
    coverage: Coverage = Field(description="The month classes each total is taken over.")
    months_withheld: FigureModel = Field(
        description="Months the regulator withheld for this well, from the quarantine ledger.",
        json_schema_extra={GLOSSARY_KEY: "gt_withheld"},
    )


@router.get(
    "/wells/{api10}/cumulatives",
    operation_id="get_well_cumulatives",
    summary="Cumulative production for one well",
    description=(
        "Cumulative oil, gas and water for one well, served beside the record each total is"
        " taken over. A total on its own cannot say whether a zero is a filed zero or an"
        " absence, and it cannot say anything at all about a month the regulator withheld —"
        " those months never reach canonical, they are quarantined — so every figure here"
        " carries four month counts that add up to its span: months reported, months reported"
        " as zero, months with no report, and months withheld. Only a reported or a"
        " reported-zero month is admitted into the total; a no-report month and a withheld"
        " month are counted and excluded, never summed as zeros."
        " A well that has never filed anything returns 200 with a null cumulative and"
        " coverage_outcome never_reported, because the well exists and the honest answer is"
        " that nothing was ever filed for it — not a zero, and not a 404."
        " The totals are a mart snapshot, and every figure states the vintage it was built at."
        " The live monthly series at /v1/wells/{api10}/production can already hold filings this"
        " snapshot has not absorbed; where it does, this response says so and names both dates"
        " rather than leaving a reader to find the gap by arithmetic. Both are correct at the"
        " vintage each states."
        " The mart covers North Dakota, so a well outside it is refused by name rather than"
        " served an empty total that would read as no production."
    ),
    response_model=EnvelopeModel[WellCumulatives],
    openapi_extra={
        **request_example(path={"api10": EXAMPLE_API10}),
        **dataset(
            id="cumulatives",
            title="Cumulative production (per well)",
            group="wells",
            collection_pointer="",
            anchors=["/api10", "/granularity", "/snapshot_vintage"],
            # Composite on purpose: the row is this well's total at this snapshot, and two
            # snapshots are two rows. It also keeps /api10 the identity of exactly one
            # dataset, which is what the wells row-id ruling (UDM-SPEC §6.4) rests on.
            row_id=["/api10", "/snapshot_vintage"],
            facets=["as_of"],
            columns={
                "default": [
                    "/api10",
                    "/cumulative/oil_bbl",
                    "/cumulative/gas_mcf",
                    "/cumulative/water_bbl",
                    "/months_withheld",
                    "/snapshot_vintage",
                ],
                "sort": "/api10",
            },
            intro="nb_dataset_cumulatives",
            order=16,
        ),
        **semantics(
            as_of={
                "glossary": "gt_report_vintage",
                "so": (
                    "This surface is a snapshot rather than a live read, so as_of cannot walk"
                    " backwards through it: a date before the snapshot vintage is refused"
                    " rather than answered with a total the date never saw. Ask"
                    " /v1/wells/{api10}/production for a historical cut."
                ),
            },
            explain={
                "glossary": "gt_derivation_handle",
                "so": (
                    "Inlines the chain behind each total and behind the coverage counts. The"
                    " counts share one handle per stream, so the block stays inside"
                    " /v1/explain's cap however many months a well has filed."
                ),
            },
            explain_depth={
                "glossary": "gt_derivation_handle",
                "so": (
                    "A total resolves through the mart refresh to every promotion that fed it,"
                    " so the chain here is one hop longer than a live figure's."
                ),
            },
        ),
    },
    responses=problem_responses(
        "not_found", "validation_failed", "as_of_out_of_range", "service_degraded"
    ),
)
def get_well_cumulatives(
    request: Request,
    connection: Connection,
    api10: Annotated[str, Path(description="Ten-digit API well number.", pattern=API10_PATTERN)],
    explain: ExplainEffect,
    as_of: AsOf = None,
) -> JSONResponse:
    found = rows(connection, _CUMULATIVES, {"api10": api10})
    if not found:
        raise ProblemError(
            "not_found",
            detail=(
                f"no cumulative for {api10}. The cumulative mart covers state API prefix"
                f" {', '.join(STATE_API_PREFIXES)}; a well outside it has no total here, which"
                " is not the same fact as a well that produced nothing."
            ),
        )
    by_stream = {row["stream"]: row for row in found}
    anchor = found[0]
    snapshot = anchor["snapshot_vintage"]
    if as_of is not None and as_of < snapshot:
        raise ProblemError(
            "as_of_out_of_range",
            detail=(
                f"as_of {as_of.isoformat()} precedes this mart snapshot"
                f" {snapshot.isoformat()}; the snapshot is the earliest vintage it can answer"
                f" for. The live series at /v1/wells/{api10}/production reads earlier vintages."
            ),
        )

    outcome = anchor["coverage_outcome"]
    warnings: list[dict[str, Any]] = []
    data: dict[str, Any] = {
        "api10": api10,
        "granularity": "well_observed",
        "snapshot_vintage": snapshot,
        "coverage_outcome": outcome,
        "cumulative": _cumulative(by_stream, api10=api10, snapshot=snapshot),
        "coverage": _coverage(by_stream, api10=api10),
        "months_withheld": figure(
            str(anchor["months_withheld_quarantined"]),
            unit=COUNT_UNIT,
            derivation=anchor["derivation_id"],
            selector=f"api10={api10}&col=months_withheld",
        ),
    }
    warnings.extend(_withheld_warning(anchor))
    warnings.extend(_behind_series_warning(connection, api10, snapshot))
    if outcome == NEVER_REPORTED:
        warnings.append(
            {
                "code": "well_never_reported",
                "detail": (
                    "This well has no production filing of any class and no withheld month, so"
                    " it has no span to be a total over. The cumulative is null rather than"
                    " zero: a zero would say the well produced nothing, which nobody has"
                    " reported."
                ),
                "pointer": "/cumulative",
            }
        )
    data = register_response_figures(
        connection,
        data,
        dataset="api.well_cumulatives",
        operation_id="get_well_cumulatives",
        locator=request.url.path,
        partition={"api10": api10, "as_of": snapshot.isoformat()},
        input_derivations=sorted({row["derivation_id"] for row in found}),
        correlation_id=request.state.request_id,
        rule_ids=[NULL_SEMANTICS_RULE, LIQUIDS_RULE, ROLLUP_RULE],
    )
    warnings.extend(_truncation_warning(data))
    return enveloped(
        request,
        data,
        as_of=snapshot,
        as_of_requested=iso(as_of) or "latest",
        labels=LABELS,
        source_freshness=_freshness(connection, api10),
        warnings=warnings,
        links={
            "well": f"/v1/wells/{api10}",
            "production": f"/v1/wells/{api10}/production",
            NULL_SEMANTICS_RULE: f"/v1/conformance/{NULL_SEMANTICS_RULE}",
            LIQUIDS_RULE: f"/v1/conformance/{LIQUIDS_RULE}",
            **(
                {"quarantine": "/v1/quarantine?reason_code=confidential_withheld"}
                if anchor["months_withheld_quarantined"]
                else {}
            ),
        },
        explain=inline_for(connection, explain),
    )


def _cumulative(
    by_stream: dict[str, dict[str, Any]], *, api10: str, snapshot: date
) -> dict[str, Any] | None:
    """Null for a well that never filed; a null stream for one that filed no such stream."""
    if all(row["coverage_outcome"] == NEVER_REPORTED for row in by_stream.values()):
        return None
    totals: dict[str, Any] = {}
    for stream, column in STREAM_COLUMNS.items():
        row = by_stream.get(stream)
        totals[column] = (
            None
            if row is None or row["cum_volume"] is None
            else figure(
                str(Decimal(row["cum_volume"])),
                unit=row["unit"],
                derivation=row["derivation_id"],
                selector=f"api10={api10}&col={column}",
                granularity="well_observed",
                basis=row["basis"],
                report_vintage=snapshot,
            )
        )
    return totals


def _coverage(by_stream: dict[str, dict[str, Any]], *, api10: str) -> dict[str, Any]:
    """One handle per stream rather than one per count: five figures a stream would put a
    three-stream response over /v1/explain's cap on its own (SB-07 §9.1b)."""
    block: dict[str, Any] = {}
    lineage: dict[str, str] = {}
    units: dict[str, str] = {}
    for stream, column in STREAM_COLUMNS.items():
        row = by_stream[stream]
        no_report = row["months_no_report_stored"] + row["months_absent"]
        withheld = row["months_withheld_stored"] + row["months_withheld_quarantined"]
        block[column] = {
            "months_reported": row["months_reported"],
            "months_reported_zero": row["months_reported_zero"],
            "months_no_report": no_report,
            "months_withheld": withheld,
            "span_months": row["span_months"],
            "first_month": month_label(row["first_month"]) if row["first_month"] else None,
            "last_month": month_label(row["last_month"]) if row["last_month"] else None,
            "coverage_complete": no_report == 0 and withheld == 0,
        }
        lineage[column] = format_handle(
            row["derivation_id"], f"api10={api10}&stream={stream}&col=coverage"
        )
        units[column] = COUNT_UNIT
    return block | {"_lineage": lineage, "_units": units}


def _withheld_warning(anchor: dict[str, Any]) -> list[dict[str, Any]]:
    months = anchor["months_withheld_quarantined"]
    if not months:
        return []
    rules = ", ".join(anchor["withholding_rule_ids"]) or "an unattributed rule"
    return [
        {
            "code": "months_withheld",
            "detail": (
                f"{months} month(s) of this well's production are withheld by the regulator and"
                " have no canonical row to sum. They are counted here and excluded from every"
                f" total; the rows are in /v1/quarantine with their payloads, recorded by"
                f" {rules}. A total over a withheld record is a total over an incomplete one."
            ),
            "pointer": "/cumulative",
        }
    ]


def _behind_series_warning(
    connection: psycopg.Connection, api10: str, snapshot: date
) -> list[dict[str, Any]]:
    behind = rows(connection, _BEHIND_SERIES, {"api10": api10, "snapshot": snapshot})[0]
    if not behind["later_months"]:
        return []
    return [
        {
            "code": "cumulative_behind_series",
            "detail": (
                f"This cumulative is the {snapshot.isoformat()} mart snapshot. canonical holds"
                f" {behind['later_months']} month(s) filed at a later vintage, through"
                f" {month_label(behind['latest_month'])} at"
                f" {behind['latest_vintage'].isoformat()}, which the next refresh will absorb."
                f" The live monthly series at /v1/wells/{api10}/production is current; summing"
                " it will give a larger total. Both are correct at the vintage each states."
            ),
            "pointer": "/cumulative",
        }
    ]


def _truncation_warning(data: Any) -> list[dict[str, Any]]:
    handles = len(distinct_handles(collect_handles(data)))
    if handles <= MAX_HANDLES:
        return []
    return [
        {
            "code": "explain_link_truncated",
            "detail": (
                f"This response carries {handles} handles and links.explain carries the first"
                f" {MAX_HANDLES}, so {handles - MAX_HANDLES} are absent from it. Every figure"
                " still resolves on its own: read the figure's `d` and call"
                " /v1/explain?h=<d>&depth=full. The cap is /v1/explain's own (SB-07 §9.4), not"
                " this operation's."
            ),
            "pointer": "/coverage",
        }
    ]


def _freshness(connection: psycopg.Connection, api10: str) -> dict[str, Any]:
    source_ids = [row["source_id"] for row in rows(connection, _SOURCES, {"api10": api10})]
    if not source_ids:
        return {}
    _, freshness = source_health_data(
        connection, observed_at=datetime.now(UTC), source_ids=source_ids
    )
    return freshness
