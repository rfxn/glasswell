"""The conformance registry, served with its rationale and its evidence (R8, S11)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import Connection, Cursor, SpineLimit, rows, today
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import (
    EXAMPLE_RULE_ID,
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
from glasswell.api.responses import EnvelopeModel, enveloped, iso

router = APIRouter(tags=["quality"])

RULE_LABELS = {"/rule_id": "gt_conformance_rule", "/spec": "gt_conformance_rule"}

_COLUMNS = (
    "rule_id, rule_family, supersedes_rule_id, source_id, stage, applies_to_fields, rule_kind,"
    " spec, rule, rationale, evidence_url, evidence_sha256, effective_from, effective_to,"
    " published_vintage, code_ref"
)

_RULES = f"""
select {_COLUMNS}
  from lineage.conformance_rules r
 where true
"""

_APPLIED_BY = """
select dr.derivation_id, dr.applied_rows, d.operation, d.output_dataset, d.created_vintage
  from lineage.derivation_rules dr
 join lineage.derivations d on d.derivation_id = dr.derivation_id
 where dr.rule_id = %(rule_id)s
   and d.created_at < (%(as_of)s::date + interval '1 day')
 order by dr.derivation_id
"""


class ConformanceRule(BaseModel):
    rule_id: str = Field(
        description="Registry id of the rule.",
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )
    rule_family: str = Field(description="Family the rule versions belong to.")
    supersedes_rule_id: str | None = Field(description="Rule version this one replaced.")
    source_id: str = Field(
        description="Source the rule applies to.",
        json_schema_extra={GLOSSARY_KEY: "gt_source"},
    )
    stage: str = Field(
        description="parse, validate, conform or join.",
        json_schema_extra={GLOSSARY_KEY: "gt_pipeline_stage"},
    )
    applies_to_fields: list[str] = Field(description="Fields the rule governs.")
    rule_kind: str = Field(
        description="Executor kind, or code_ref for a policy declaration.",
        json_schema_extra={GLOSSARY_KEY: "gt_rule_kind"},
    )
    spec: dict[str, Any] = Field(description="Executable specification, served verbatim.")
    rule: str = Field(description="The rule stated in one sentence.")
    rationale: str = Field(description="Why this decision was taken, in the author's words.")
    evidence_url: str | None = Field(description="Where the upstream evidence lives.")
    evidence_sha256: str | None = Field(description="Hash of the evidence artifact, if taken.")
    published_vintage: date = Field(
        description="First repository vintage in which this immutable rule was published."
    )
    effective_from: date = Field(
        description="First day the rule applies.",
        json_schema_extra={GLOSSARY_KEY: "gt_effective_date"},
    )
    effective_to: date | None = Field(description="Exclusive valid-time upper bound, if any.")
    code_ref: str | None = Field(description="Symbol implementing the rule, for code_ref kinds.")


class AppliedBy(BaseModel):
    derivation_id: str = Field(description="Derivation that cited this rule.")
    applied_rows: int | None = Field(
        description="Rows the rule touched in that derivation.",
        json_schema_extra=not_a_figure(
            "Reverse index of rows touched, per citing derivation."
        ),
    )
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
        "published_vintage": iso(row["published_vintage"]),
    }


@router.get(
    "/conformance",
    operation_id="list_conformance_rules",
    summary="List conformance rules",
    description=(
        "Every mapping, unit, datum and validity decision the pipeline applies, each with"
        " the rationale for taking it and a URL to the upstream evidence. `as_of` is the"
        " knowledge clock; `valid_at` is the independent date on which the rule applies."
        " When `valid_at` is supplied, eligibility is resolved on both clocks before"
        " supersession. Omit it to read every rule version known at `as_of`; rules are"
        " append-only, so a past decision remains readable."
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
            facets=["source_id", "kind", "family", "stage", "field", "as_of", "valid_at"],
            columns={
                "default": [
                    "/rule_id",
                    "/source_id",
                    "/rule_kind",
                    "/rule_family",
                    "/stage",
                    "/published_vintage",
                    "/effective_from",
                ],
                "sort": "/effective_from",
            },
            intro="nb_dataset_conformance",
            order=21,
        ),
        **semantics(
            cursor={
                "so": (
                    "Pins the page to a newest-effective-first ordering and to the filters that"
                    " opened it. Rules are append-only, so a cursor here holds in a way a"
                    " quarantine cursor does not — what was on page two is still on page two."
                ),
            },
            limit={
                "so": (
                    "Capped at 200. The registry is small on purpose: if paging this collection"
                    " is laborious, the mapping policy has grown faster than anyone is reading"
                    " it, which is itself the finding."
                ),
            },
            source_id={
                "glossary": "gt_source",
                "so": (
                    "Every rule is declared against exactly one source, so this is the whole"
                    " mapping policy for one regulator file, on one page, in the author's own"
                    " words."
                ),
            },
            kind={
                "glossary": "gt_rule_kind",
                "so": (
                    "Narrows to one executor. Filtering to code_ref is the honest audit: it"
                    " lists every decision recorded as a row but carried out by code, which is"
                    " the set most likely to drift from what the row says."
                ),
            },
            family={
                "glossary": "gt_conformance_rule",
                "so": (
                    "Groups a rule with the versions it superseded. The family is the history"
                    " of one decision; a rule_id is a single version of it, so only the family"
                    " shows you what changed and when."
                ),
            },
            stage={
                "glossary": "gt_pipeline_stage",
                "so": (
                    "Narrows to one stage of the pipeline, which decides when a rule runs and"
                    " therefore which quarantine reasons it can produce."
                ),
            },
            field={
                "so": (
                    "Lists every rule that governs one field. Before trusting a column, this is"
                    " the parameter that says what was done to it — and an empty answer means"
                    " nothing was, which is also worth knowing."
                ),
            },
            as_of={
                "so": (
                    "Knowledge time: rules published after this date do not exist for the"
                    " request, even when their effective date was backdated. Omit it for the"
                    " current known registry; cursors pin the resolved date."
                ),
            },
            valid_at={
                "glossary": "gt_effective_date",
                "so": (
                    "Valid time: asks which rules apply to source facts on this date. It is"
                    " independent of as_of, so a rule learned later cannot leak into a"
                    " retrospective decision merely because it was backdated. Omit it to"
                    " return the known immutable version history without resolving"
                    " supersession."
                ),
            },
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
    as_of: Annotated[
        date | None, Query(description="Rules known by this publication date.")
    ] = None,
    valid_at: Annotated[
        date | None, Query(description="Rules valid for source facts on this date.")
    ] = None,
    effective_at: Annotated[
        date | None,
        Query(description="Deprecated alias for valid_at.", deprecated=True),
    ] = None,
) -> JSONResponse:
    if valid_at is not None and effective_at is not None and valid_at != effective_at:
        raise ProblemError(
            "validation_failed",
            detail="valid_at and its deprecated effective_at alias disagree",
        )
    requested_valid_at = valid_at or effective_at
    filters = {
        "source_id": source_id,
        "kind": kind,
        "family": family,
        "stage": stage,
        "field": field,
        "as_of": as_of,
        "valid_at": requested_valid_at,
    }
    fingerprint = query_fingerprint(filters)
    decoded = decode_cursor(cursor, fingerprint=fingerprint) if cursor is not None else None
    cursor_as_of = date.fromisoformat(decoded.as_of) if decoded and decoded.as_of else None
    cursor_valid_at = (
        date.fromisoformat(decoded.valid_as_of) if decoded and decoded.valid_as_of else None
    )
    if decoded is not None and cursor_as_of is None:
        raise ProblemError(
            "cursor_malformed", detail="conformance cursor does not pin its knowledge cut"
        )
    if decoded is not None and ((cursor_valid_at is None) != (requested_valid_at is None)):
        raise ProblemError(
            "cursor_malformed",
            detail="conformance cursor does not match the requested valid-time cut",
        )
    knowledge_at = cursor_as_of or as_of or today()
    effective_cut = cursor_valid_at or requested_valid_at
    params: dict[str, Any] = {
        "as_of": knowledge_at,
        "limit": limit + 1,
    }
    clauses = [_RULES]
    clauses.append("and r.published_vintage <= %(as_of)s")
    if effective_cut is not None:
        params["valid_at"] = effective_cut
        clauses.append(
            "and r.effective_from <= %(valid_at)s"
            " and (r.effective_to is null or r.effective_to > %(valid_at)s)"
        )
        clauses.append(
            "and not exists (select 1 from lineage.conformance_rules successor"
            " where successor.supersedes_rule_id = r.rule_id"
            " and successor.published_vintage <= %(as_of)s"
            " and successor.effective_from <= %(valid_at)s"
            " and (successor.effective_to is null or successor.effective_to > %(valid_at)s))"
        )
    if source_id is not None:
        clauses.append("and r.source_id = %(source_id)s")
        params["source_id"] = source_id
    if kind is not None:
        clauses.append("and r.rule_kind = %(kind)s")
        params["kind"] = kind
    if family is not None:
        clauses.append("and r.rule_family = %(family)s")
        params["family"] = family
    if stage is not None:
        clauses.append("and r.stage = %(stage)s")
        params["stage"] = stage
    if field is not None:
        clauses.append("and %(field)s = any(r.applies_to_fields)")
        params["field"] = field
    if decoded is not None:
        clauses.append("and (r.effective_from, r.rule_id) < (%(after_key)s, %(after_id)s)")
        params |= {"after_key": decoded.key, "after_id": decoded.tiebreak}
    clauses.append("order by r.effective_from desc, r.rule_id desc limit %(limit)s")

    found = rows(connection, "\n".join(clauses), params)
    items, has_more = page(found, limit)
    next_cursor = (
        encode_cursor(
            key=items[-1]["effective_from"],
            tiebreak=items[-1]["rule_id"],
            as_of=knowledge_at,
            fingerprint=fingerprint,
            valid_as_of=effective_cut,
        )
        if has_more and items
        else None
    )
    return enveloped(
        request,
        [_rule(row) for row in items],
        as_of=knowledge_at,
        as_of_requested=iso(as_of) or "latest",
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
        "The rule, its executable spec, why it exists and the evidence behind it at the"
        " requested knowledge cut. Supply `valid_at` to require valid-time eligibility and"
        " resolve supersession; omit it to retrieve any known immutable version. Ask for"
        " `include=applied_by` to get the"
        " reverse index: which eligible derivations cited this rule and how many rows each"
        " applied it to. Rules are immutable once written."
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
    as_of: Annotated[
        date | None, Query(description="Rule and derivations known by this publication date.")
    ] = None,
    valid_at: Annotated[
        date | None, Query(description="Require the rule to be valid on this date.")
    ] = None,
    effective_at: Annotated[
        date | None,
        Query(description="Deprecated alias for valid_at.", deprecated=True),
    ] = None,
) -> JSONResponse:
    if valid_at is not None and effective_at is not None and valid_at != effective_at:
        raise ProblemError(
            "validation_failed",
            detail="valid_at and its deprecated effective_at alias disagree",
        )
    knowledge_at = as_of or today()
    effective_cut = valid_at or effective_at
    params = {
        "rule_id": rule_id,
        "as_of": knowledge_at,
    }
    statement = (
        _RULES
        + " and r.rule_id = %(rule_id)s"
        + " and r.published_vintage <= %(as_of)s"
    )
    if effective_cut is not None:
        params["valid_at"] = effective_cut
        statement += (
            " and r.effective_from <= %(valid_at)s"
            " and (r.effective_to is null or r.effective_to > %(valid_at)s)"
            " and not exists (select 1 from lineage.conformance_rules successor"
            " where successor.supersedes_rule_id = r.rule_id"
            " and successor.published_vintage <= %(as_of)s"
            " and successor.effective_from <= %(valid_at)s"
            " and (successor.effective_to is null"
            "      or successor.effective_to > %(valid_at)s))"
        )
    found = rows(connection, statement, params)
    if not found:
        raise ProblemError("not_found", detail=f"no conformance rule {rule_id}")
    data = _rule(found[0])
    if include == "applied_by":
        data["applied_by"] = [
            dict(row) | {"created_vintage": iso(row["created_vintage"])}
            for row in rows(
                connection,
                _APPLIED_BY,
                {"rule_id": rule_id, "as_of": knowledge_at},
            )
        ]
    return enveloped(
        request,
        data,
        as_of=knowledge_at,
        as_of_requested=iso(as_of) or "latest",
        labels=RULE_LABELS,
    )
