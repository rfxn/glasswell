"""The conformance registry, served with its rationale and its evidence (R8, S11)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import Connection, Cursor, SpineLimit, rows
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import EXAMPLE_RULE_ID, GLOSSARY_KEY, dataset, request_example
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

RULE_LABELS = {"/rule_id": "gt_conformance_rule", "/spec": "gt_conformance_rule"}

_COLUMNS = (
    "rule_id, rule_family, supersedes_rule_id, source_id, stage, applies_to_fields, rule_kind,"
    " spec, rule, rationale, evidence_url, evidence_sha256, effective_from, effective_to,"
    " code_ref"
)

_RULES = f"""
select {_COLUMNS}
  from lineage.conformance_rules
 where true
"""

_APPLIED_BY = """
select dr.derivation_id, dr.applied_rows, d.operation, d.output_dataset, d.created_vintage
  from lineage.derivation_rules dr
  join lineage.derivations d on d.derivation_id = dr.derivation_id
 where dr.rule_id = %(rule_id)s
 order by dr.derivation_id
"""


class ConformanceRule(BaseModel):
    rule_id: str = Field(
        description="Registry id of the rule.",
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )
    rule_family: str = Field(description="Family the rule versions belong to.")
    supersedes_rule_id: str | None = Field(description="Rule version this one replaced.")
    source_id: str = Field(description="Source the rule applies to.")
    stage: str = Field(description="parse, validate, conform or join.")
    applies_to_fields: list[str] = Field(description="Fields the rule governs.")
    rule_kind: str = Field(description="Executor kind, or code_ref for a policy declaration.")
    spec: dict[str, Any] = Field(description="Executable specification, served verbatim.")
    rule: str = Field(description="The rule stated in one sentence.")
    rationale: str = Field(description="Why this decision was taken, in the author's words.")
    evidence_url: str | None = Field(description="Where the upstream evidence lives.")
    evidence_sha256: str | None = Field(description="Hash of the evidence artifact, if taken.")
    effective_from: date = Field(description="First day the rule applies.")
    effective_to: date | None = Field(description="Last day it applied, if superseded.")
    code_ref: str | None = Field(description="Symbol implementing the rule, for code_ref kinds.")


class AppliedBy(BaseModel):
    derivation_id: str = Field(description="Derivation that cited this rule.")
    applied_rows: int | None = Field(description="Rows the rule touched in that derivation.")
    operation: str = Field(description="Operation of the citing derivation.")
    output_dataset: str = Field(description="Dataset the citing derivation produced.")
    created_vintage: date | None = Field(description="Knowledge time of that derivation.")


class ConformanceRuleDetail(ConformanceRule):
    applied_by: list[AppliedBy] | None = Field(
        default=None, description="Present when include=applied_by."
    )


def _rule(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row) | {
        "effective_from": iso(row["effective_from"]),
        "effective_to": iso(row["effective_to"]),
    }


@router.get(
    "/conformance",
    operation_id="list_conformance_rules",
    summary="List conformance rules",
    description=(
        "Every mapping, unit, datum and validity decision the pipeline applies, each with"
        " the rationale for taking it and a URL to the upstream evidence. Newest effective"
        " date first. Rules are append-only: a correction is a new rule that supersedes"
        " the old one, so a past decision stays readable."
    ),
    response_model=EnvelopeModel[list[ConformanceRule]],
    openapi_extra={
        **request_example(query={"limit": 5}),
        **dataset(
            id="conformance",
            title="Conformance rules",
            group="kitchen",
            collection_pointer="",
            row_id=["/rule_id"],
            detail_operation="get_conformance_rule",
            facets=["source_id", "kind", "family", "stage", "field", "effective_at"],
            columns={
                "default": [
                    "/rule_id",
                    "/source_id",
                    "/rule_kind",
                    "/rule_family",
                    "/stage",
                    "/effective_from",
                    "/rationale",
                ],
                "sort": "/effective_from",
            },
            intro="nb_dataset_conformance",
            order=21,
        ),
    },
    responses=problem_responses(
        "validation_failed", "cursor_malformed", "cursor_query_mismatch", "service_degraded"
    ),
)
def list_conformance_rules(
    request: Request,
    connection: Connection,
    cursor: Cursor = None,
    limit: SpineLimit = DEFAULT_LIMIT,
    source_id: Annotated[str | None, Query(description="Filter to one source.")] = None,
    kind: Annotated[str | None, Query(description="Filter to one rule kind.")] = None,
    family: Annotated[str | None, Query(description="Filter to one rule family.")] = None,
    stage: Annotated[str | None, Query(description="Filter to one pipeline stage.")] = None,
    field: Annotated[str | None, Query(description="Rules governing this field.")] = None,
    effective_at: Annotated[
        date | None, Query(description="Rules in force on this date.")
    ] = None,
) -> JSONResponse:
    filters = {
        "source_id": source_id,
        "kind": kind,
        "family": family,
        "stage": stage,
        "field": field,
        "effective_at": effective_at,
    }
    fingerprint = query_fingerprint(filters)
    params: dict[str, Any] = {"limit": limit + 1}
    clauses = [_RULES]
    if source_id is not None:
        clauses.append("and source_id = %(source_id)s")
        params["source_id"] = source_id
    if kind is not None:
        clauses.append("and rule_kind = %(kind)s")
        params["kind"] = kind
    if family is not None:
        clauses.append("and rule_family = %(family)s")
        params["family"] = family
    if stage is not None:
        clauses.append("and stage = %(stage)s")
        params["stage"] = stage
    if field is not None:
        clauses.append("and %(field)s = any(applies_to_fields)")
        params["field"] = field
    if effective_at is not None:
        clauses.append(
            "and effective_from <= %(effective_at)s"
            " and (effective_to is null or effective_to >= %(effective_at)s)"
        )
        params["effective_at"] = effective_at
    if cursor is not None:
        decoded = decode_cursor(cursor, fingerprint=fingerprint)
        clauses.append("and (effective_from, rule_id) < (%(after_key)s, %(after_id)s)")
        params |= {"after_key": decoded.key, "after_id": decoded.tiebreak}
    clauses.append("order by effective_from desc, rule_id desc limit %(limit)s")

    found = rows(connection, "\n".join(clauses), params)
    items, has_more = page(found, limit)
    next_cursor = (
        encode_cursor(
            key=items[-1]["effective_from"],
            tiebreak=items[-1]["rule_id"],
            as_of=None,
            fingerprint=fingerprint,
        )
        if has_more and items
        else None
    )
    return enveloped(
        request,
        [_rule(row) for row in items],
        next_cursor=next_cursor,
        links={
            "next": next_link("/v1/conformance", filters | {"limit": limit}, next_cursor)
            if next_cursor
            else None
        },
    )


@router.get(
    "/conformance/{rule_id}",
    operation_id="get_conformance_rule",
    summary="One conformance rule",
    description=(
        "The rule, its executable spec, why it exists and the evidence behind it. Ask for"
        " `include=applied_by` to get the reverse index: which derivations cited this rule"
        " and how many rows each applied it to. Rules are immutable once written."
    ),
    response_model=EnvelopeModel[ConformanceRuleDetail],
    openapi_extra=request_example(
        path={"rule_id": EXAMPLE_RULE_ID}, query={"include": "applied_by"}
    ),
    responses=problem_responses("not_found", "validation_failed", "service_degraded"),
)
def get_conformance_rule(
    request: Request,
    connection: Connection,
    rule_id: Annotated[str, Path(description="Conformance rule id.")],
    include: Annotated[
        str | None, Query(description="Set to applied_by for the reverse index.")
    ] = None,
) -> JSONResponse:
    found = rows(connection, _RULES + " and rule_id = %(rule_id)s", {"rule_id": rule_id})
    if not found:
        raise ProblemError("not_found", detail=f"no conformance rule {rule_id}")
    data = _rule(found[0])
    if include == "applied_by":
        data["applied_by"] = [
            dict(row) | {"created_vintage": iso(row["created_vintage"])}
            for row in rows(connection, _APPLIED_BY, {"rule_id": rule_id})
        ]
    return enveloped(request, data, labels=RULE_LABELS)
