"""Quarantine: rejected rows are served with their reason, never dropped (bp:133)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import Connection, Cursor, SpineLimit, rows
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import (
    CONTENT_ADDRESS_NOTE,
    EXAMPLE_QUARANTINE_ID,
    GLOSSARY_KEY,
    dataset,
    not_a_figure,
    request_example,
)
from glasswell.api.pagination import (
    DEFAULT_LIMIT,
    decode_cursor,
    encode_cursor,
    next_link,
    page,
    query_fingerprint,
)
from glasswell.api.responses import EnvelopeModel, enveloped, iso

router = APIRouter(tags=["quality"])

QUARANTINE_LABELS = {"/reason_code": "gt_quarantine", "/state": "gt_quarantine"}

_COLUMNS = (
    "quarantine_id, row_fingerprint, source_id, staging_table, stage, reason_code, rule_id,"
    " first_seen_at, first_seen_manifest_id, last_seen_at, last_seen_manifest_id,"
    " occurrence_count, state, released_by_rule_id, released_at, release_derivation_id, notes"
)

_ROWS = f"""
select {_COLUMNS}
  from lineage.quarantine_rows
 where true
"""

_ROW_DETAIL = f"""
select {_COLUMNS}, row_payload
  from lineage.quarantine_rows
 where quarantine_id = %(quarantine_id)s
"""

_SUMMARY = """
select {group_by} as key, count(*) as count
  from lineage.quarantine_rows
 where (%(source_id)s::text is null or source_id = %(source_id)s)
   and (%(state)s::text is null or state = %(state)s)
 group by {group_by}
 order by count(*) desc, {group_by}
"""


class QuarantineRow(BaseModel):
    quarantine_id: str = Field(description="Stable id of the quarantined row.")
    row_fingerprint: str = Field(description="Fingerprint that dedupes it across re-pulls.")
    source_id: str = Field(description="Source the row came from.")
    staging_table: str = Field(description="Staging table it was read from.")
    stage: str = Field(description="Pipeline stage that rejected it.")
    reason_code: str = Field(
        description="Why it was rejected (SB-07 §8.2).",
        json_schema_extra={GLOSSARY_KEY: "gt_quarantine"},
    )
    rule_id: str | None = Field(description="Conformance rule that rejected it.")
    first_seen_at: datetime = Field(description="When it was first rejected.")
    first_seen_manifest_id: str = Field(description="Manifest it was first seen in.")
    last_seen_at: datetime = Field(description="When it was last re-presented.")
    last_seen_manifest_id: str = Field(description="Manifest it was last seen in.")
    occurrence_count: int = Field(
        description="How many fetches have re-presented it.",
        json_schema_extra=not_a_figure("Occurrence counter, in a collection item."),
    )
    state: str = Field(description="open, released, accepted_loss or superseded.")
    released_by_rule_id: str | None = Field(description="Rule that released it, if any.")
    released_at: datetime | None = Field(description="When it was released.")
    release_derivation_id: str | None = Field(description="Derivation that released it.")
    notes: str | None = Field(description="Operator note, where one was left.")


class QuarantineDetail(QuarantineRow):
    # Redeclared, not inherited: the record and the collection item are exempted by different
    # allowlist entries, and one Field can only publish one reason.
    occurrence_count: int = Field(
        description="How many fetches have re-presented it.",
        json_schema_extra=not_a_figure(
            "How many fetches re-presented this rejected row (SB-07 §8.1)."
        ),
    )
    row_payload: dict[str, Any] = Field(
        description="The rejected source row, verbatim. It is evidence, not a served figure."
    )


class SummaryGroup(BaseModel):
    key: str = Field(description="Group key: a reason code or a stage.")
    count: int = Field(
        description="Rows in this group.",
        json_schema_extra=not_a_figure("Row count per group."),
    )
    share: float = Field(
        description="Group count over the filtered total.",
        json_schema_extra=not_a_figure(
            "Count divided by count; it carries no unit and no vintage."
        ),
    )


class QuarantineSummary(BaseModel):
    total: int = Field(
        description="Rows matching the filters.",
        json_schema_extra=not_a_figure(
            "Row count of the quarantine population being summarised."
        ),
    )
    group_by: str = Field(description="Dimension the shares are computed over.")
    groups: list[SummaryGroup] = Field(description="One row per group, largest first.")


def _row(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row) | {
        "first_seen_at": iso(row["first_seen_at"]),
        "last_seen_at": iso(row["last_seen_at"]),
        "released_at": iso(row["released_at"]),
    }


@router.get(
    "/quarantine",
    operation_id="list_quarantine",
    summary="List quarantined rows",
    description=(
        "Rows a conformance rule rejected, with the reason, the rule, how many fetches"
        " have re-presented them and their lifecycle state. Nothing is dropped silently:"
        " an empty quarantine means the rules are not firing, not that the data is clean."
    ),
    response_model=EnvelopeModel[list[QuarantineRow]],
    openapi_extra={
        **request_example(query={"limit": 5}),
        **dataset(
            id="quarantine",
            title="Quarantine",
            group="kitchen",
            collection_pointer="",
            row_id=["/quarantine_id"],
            detail_operation="get_quarantine_row",
            summary_operation="get_quarantine_summary",
            facets=["source_id", "reason_code", "rule_id", "state", "stage"],
            columns={
                "default": [
                    "/quarantine_id",
                    "/reason_code",
                    "/rule_id",
                    "/state",
                    "/stage",
                    "/occurrence_count",
                    "/last_seen_at",
                ],
                "hidden": ["/row_fingerprint", "/notes"],
                "hidden_reason": {
                    "/row_fingerprint": (
                        "A content address over the rejected row's bytes, useful for joining"
                        " two fetches of the same row and unreadable as a column."
                    ),
                    "/notes": (
                        "Free text a reviewer left on release; empty on almost every row and"
                        " not a dimension anything is filtered by."
                    ),
                },
                "sort": "/last_seen_at",
            },
            intro="nb_dataset_quarantine",
            order=20,
        ),
    },
    responses=problem_responses(
        "validation_failed", "cursor_malformed", "cursor_query_mismatch", "service_degraded"
    ),
)
def list_quarantine(
    request: Request,
    connection: Connection,
    cursor: Cursor = None,
    limit: SpineLimit = DEFAULT_LIMIT,
    source_id: Annotated[str | None, Query(description="Filter to one source.")] = None,
    reason_code: Annotated[str | None, Query(description="Filter to one reason code.")] = None,
    rule_id: Annotated[str | None, Query(description="Filter to one rejecting rule.")] = None,
    state: Annotated[
        Literal["open", "released", "accepted_loss", "superseded"] | None,
        Query(description="Filter to one lifecycle state."),
    ] = None,
    stage: Annotated[
        Literal["parse", "validate", "conform", "join"] | None,
        Query(description="Filter to one pipeline stage."),
    ] = None,
) -> JSONResponse:
    filters = {
        "source_id": source_id,
        "reason_code": reason_code,
        "rule_id": rule_id,
        "state": state,
        "stage": stage,
    }
    fingerprint = query_fingerprint(filters)
    params: dict[str, Any] = {"limit": limit + 1}
    clauses = [_ROWS]
    for name, value in filters.items():
        if value is not None:
            clauses.append(f"and {name} = %({name})s")
            params[name] = value
    if cursor is not None:
        decoded = decode_cursor(cursor, fingerprint=fingerprint)
        clauses.append("and (last_seen_at, quarantine_id) < (%(after_key)s, %(after_id)s)")
        params |= {"after_key": decoded.key, "after_id": decoded.tiebreak}
    clauses.append("order by last_seen_at desc, quarantine_id desc limit %(limit)s")

    found = rows(connection, "\n".join(clauses), params)
    items, has_more = page(found, limit)
    next_cursor = (
        encode_cursor(
            key=items[-1]["last_seen_at"],
            tiebreak=items[-1]["quarantine_id"],
            as_of=None,
            fingerprint=fingerprint,
        )
        if has_more and items
        else None
    )
    return enveloped(
        request,
        [_row(row) for row in items],
        next_cursor=next_cursor,
        labels=QUARANTINE_LABELS,
        links={
            "next": next_link("/v1/quarantine", filters | {"limit": limit}, next_cursor)
            if next_cursor
            else None
        },
    )


@router.get(
    "/quarantine/summary",
    operation_id="get_quarantine_summary",
    summary="Quarantine shares",
    description=(
        "Counts and shares by reason code or by stage — the scorecard view of what the"
        " rules are rejecting. Declared before /quarantine/{quarantine_id} so `summary` is"
        " not matched as an id."
    ),
    response_model=EnvelopeModel[QuarantineSummary],
    openapi_extra=request_example(query={"group_by": "reason_code"}),
    responses=problem_responses("validation_failed", "service_degraded"),
)
def get_quarantine_summary(
    request: Request,
    connection: Connection,
    group_by: Annotated[
        Literal["reason_code", "stage"], Query(description="Dimension to group by.")
    ] = "reason_code",
    source_id: Annotated[str | None, Query(description="Filter to one source.")] = None,
    state: Annotated[str | None, Query(description="Filter to one lifecycle state.")] = None,
) -> JSONResponse:
    found = rows(
        connection,
        _SUMMARY.format(group_by=group_by),
        {"source_id": source_id, "state": state},
    )
    total = sum(row["count"] for row in found)
    data = {
        "total": total,
        "group_by": group_by,
        "groups": [
            {
                "key": row["key"],
                "count": row["count"],
                "share": round(row["count"] / total, 6) if total else 0.0,
            }
            for row in found
        ],
    }
    return enveloped(request, data, labels={"/groups": "gt_quarantine"})


@router.get(
    "/quarantine/{quarantine_id}",
    operation_id="get_quarantine_row",
    summary="One quarantined row",
    description=(
        "The rejected row itself, served verbatim alongside the rule that rejected it and"
        " the manifests it was first and last seen in. Re-processing always re-reads the"
        " manifest, never this payload, so the payload is evidence rather than input."
        + CONTENT_ADDRESS_NOTE
    ),
    response_model=EnvelopeModel[QuarantineDetail],
    openapi_extra=request_example(path={"quarantine_id": EXAMPLE_QUARANTINE_ID}),
    responses=problem_responses("not_found", "service_degraded"),
)
def get_quarantine_row(
    request: Request,
    connection: Connection,
    quarantine_id: Annotated[str, Path(description="Quarantined row id.")],
) -> JSONResponse:
    found = rows(connection, _ROW_DETAIL, {"quarantine_id": quarantine_id})
    if not found:
        raise ProblemError("not_found", detail=f"no quarantined row {quarantine_id}")
    return enveloped(request, _row(found[0]), labels=QUARANTINE_LABELS)
