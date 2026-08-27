"""Canonical formations aggregated from the source-scoped alias registry."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import AsOf, Connection, Cursor, rows, today
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import GLOSSARY_KEY, dataset, not_a_figure, request_example, semantics
from glasswell.api.pagination import (
    DEFAULT_LIMIT,
    decode_cursor,
    encode_cursor,
    next_link,
    page,
    query_fingerprint,
)
from glasswell.api.responses import EnvelopeModel, enveloped, iso

router = APIRouter(tags=["vocabulary"])

FORMATION_LIMIT_CAP = 500
SOURCE_BASINS = {"nd_mpr_xlsx": "williston"}
_SOURCE_BASIN_SQL = (
    "case "
    + " ".join(
        f"when source_id = '{source_id}' then '{basin}'"
        for source_id, basin in sorted(SOURCE_BASINS.items())
    )
    + " end"
)

_FORMATIONS_PREFIX = f"""
with ranked as (
    select a.*,
           row_number() over (
               partition by a.formation_raw, coalesce(a.source_id, '')
               order by a.effective_from desc, a.formation) as version_rank
     from lineage.formation_aliases a
     where a.created_vintage is not null
       and a.created_vintage <= %(knowledge_as_of)s::date
       and a.effective_from <= %(valid_as_of)s::date
), current_aliases as (
    select * from ranked where version_rank = 1
), scoped as (
    select a.*, {_SOURCE_BASIN_SQL} as basin
      from current_aliases a
     where true
"""

_VINTAGE_BOUNDS = """
select min(created_vintage) as earliest, max(created_vintage) as latest,
       max(created_vintage) filter (
           where %(as_of)s::date is null or created_vintage <= %(as_of)s::date
       ) as resolved
  from lineage.formation_aliases
 where created_vintage is not null
"""

_FORMATIONS_AGGREGATE = """
), canonical_formations as (
    select formation,
           array_agg(distinct formation_group order by formation_group)
               filter (where formation_group is not null) as formation_groups,
           array_agg(distinct basin order by basin)
               filter (where basin is not null) as basins,
           count(distinct formation_raw)::integer as alias_count,
           array_agg(distinct formation_raw order by formation_raw) as aliases,
           array_agg(distinct source_id order by source_id)
               filter (where source_id is not null) as source_ids
      from scoped
     group by formation
)
select formation, coalesce(formation_groups, '{}') as formation_groups,
       coalesce(basins, '{}') as basins, alias_count, aliases,
       coalesce(source_ids, '{}') as source_ids
  from canonical_formations
 where true
"""

FormationLimit = Annotated[
    int,
    Query(
        ge=1,
        le=FORMATION_LIMIT_CAP,
        description=(f"Page size, {DEFAULT_LIMIT} by default, {FORMATION_LIMIT_CAP} at most."),
    ),
]


class Formation(BaseModel):
    formation: str = Field(
        description="Lossless canonical formation name and stable collection identity.",
        json_schema_extra={GLOSSARY_KEY: "gt_formation"},
    )
    formation_groups: list[str] = Field(
        description="Reviewed benchmark peer groups carried by this formation's aliases.",
        json_schema_extra={GLOSSARY_KEY: "gt_formation"},
    )
    basins: list[str] = Field(
        description="Basins explicitly registered for the contributing source namespaces.",
        json_schema_extra={GLOSSARY_KEY: "gt_basin"},
    )
    alias_count: int = Field(
        description="Distinct current reported labels resolving to this formation.",
        json_schema_extra={
            **not_a_figure(
                "Reference-row cardinality, not a measured or modelled petroleum figure."
            ),
            GLOSSARY_KEY: "gt_formation_alias",
        },
    )
    aliases: list[str] = Field(
        description="Current source-reported labels resolving to this formation.",
        json_schema_extra={GLOSSARY_KEY: "gt_formation_alias"},
    )
    source_ids: list[str] = Field(
        description="Source namespaces contributing the current aliases.",
        json_schema_extra={GLOSSARY_KEY: "gt_source"},
    )


@router.get(
    "/formations",
    operation_id="list_formations",
    summary="List canonical formations",
    description=(
        "Canonical formations aggregated from the current row in each source-scoped alias"
        " history. Alias counts are distinct reported labels, not source-row counts. `q`"
        " matches either the canonical name or a current reported alias. Composite or"
        " sub-threshold labels remain in reviewed `__other__` peer groups; this route never"
        " invents a formation top or landing zone. Confidence is not served because the"
        " registry does not carry a derivation for that numeric score."
    ),
    response_model=EnvelopeModel[list[Formation]],
    openapi_extra={
        **request_example(query={"basin": "williston", "q": "bakken", "limit": 5}),
        **dataset(
            id="formations",
            title="Formations",
            group="vocabulary",
            collection_pointer="",
            row_id=["/formation"],
            facets=["basin", "q"],
            columns={
                "default": [
                    "/formation",
                    "/formation_groups",
                    "/basins",
                    "/alias_count",
                    "/aliases",
                    "/source_ids",
                ],
                "sort": "/formation",
            },
            intro="nb_dataset_formations",
            order=41,
        ),
        **semantics(
            as_of={
                "glossary": "gt_knowledge_time",
                "so": (
                    "Selects only alias decisions whose effective and knowledge dates are at"
                    " or before the cut. Legacy unvintaged aliases are excluded rather than"
                    " leaked backward."
                ),
            },
            cursor={
                "so": (
                    "Pins the page to byte-ordered canonical formation names, the filters"
                    " that opened it, a concrete alias knowledge date, and the valid-time"
                    " cut. Later-vintage ingestion and a date rollover cannot shift a"
                    " traversal."
                ),
            },
            limit={
                "so": (
                    "Capped at 500 as specified for this reference collection; the default"
                    " remains 100."
                ),
            },
            basin={
                "so": (
                    "Counts only aliases whose source namespace has an explicit basin"
                    " registration. Legacy unscoped aliases never pass a basin filter."
                )
            },
            q={
                "glossary": "gt_formation",
                "so": (
                    "Case-insensitive substring match across the canonical formation and its"
                    " current reported aliases; definitions and peer groups are not searched."
                ),
            },
        ),
    },
    responses=problem_responses(
        "validation_failed",
        "cursor_malformed",
        "cursor_query_mismatch",
        "as_of_out_of_range",
        "service_degraded",
    ),
)
def list_formations(
    request: Request,
    connection: Connection,
    cursor: Cursor = None,
    limit: FormationLimit = DEFAULT_LIMIT,
    as_of: AsOf = None,
    basin: Annotated[str | None, Query(description="Filter to one registered basin.")] = None,
    q: Annotated[
        str | None, Query(description="Match a canonical formation or reported alias.")
    ] = None,
) -> JSONResponse:
    filters = {"as_of": as_of, "basin": basin, "q": q}
    fingerprint = query_fingerprint(filters)
    decoded = decode_cursor(cursor, fingerprint=fingerprint) if cursor is not None else None
    cursor_as_of = date.fromisoformat(decoded.as_of) if decoded and decoded.as_of else None
    cursor_valid_as_of = (
        date.fromisoformat(decoded.valid_as_of) if decoded and decoded.valid_as_of else None
    )
    if decoded is not None and cursor_valid_as_of is None:
        raise ProblemError(
            "cursor_malformed", detail="formation cursor does not pin a valid-time cut"
        )
    valid_as_of = cursor_valid_as_of or as_of or today()
    bounds = rows(connection, _VINTAGE_BOUNDS, {"as_of": valid_as_of})[0]
    if decoded is not None and (
        cursor_as_of is None
        or (bounds["earliest"] is not None and cursor_as_of < bounds["earliest"])
        or (bounds["latest"] is not None and cursor_as_of > bounds["latest"])
    ):
        raise ProblemError(
            "cursor_malformed", detail="cursor as_of is outside the formation-alias history"
        )
    if as_of is not None and cursor_as_of is not None and cursor_as_of > as_of:
        raise ProblemError(
            "cursor_query_mismatch",
            detail="this cursor was minted against a different as_of cut",
        )
    if as_of is not None and cursor_valid_as_of is not None and cursor_valid_as_of != as_of:
        raise ProblemError(
            "cursor_query_mismatch",
            detail="this cursor was minted against a different valid-time cut",
        )
    if as_of is not None and bounds["earliest"] is not None and as_of < bounds["earliest"]:
        raise ProblemError(
            "as_of_out_of_range",
            detail=(
                f"as_of {as_of.isoformat()} precedes the earliest captured formation-alias"
                f" vintage {bounds['earliest'].isoformat()}"
            ),
        )
    knowledge_as_of = cursor_as_of or bounds["resolved"]
    params: dict[str, Any] = {
        "knowledge_as_of": knowledge_as_of,
        "valid_as_of": valid_as_of,
        "limit": limit + 1,
    }
    clauses = [_FORMATIONS_PREFIX]
    if basin is not None:
        params["source_ids"] = [
            source_id for source_id, source_basin in SOURCE_BASINS.items() if source_basin == basin
        ]
        clauses.append("and source_id = any(%(source_ids)s)")
    clauses.append(_FORMATIONS_AGGREGATE)
    if q is not None:
        clauses.append(
            "and (formation ilike '%%' || %(q)s || '%%'"
            " or exists (select 1 from unnest(aliases) alias_value"
            "             where alias_value ilike '%%' || %(q)s || '%%'))"
        )
        params["q"] = q
    if cursor is not None:
        assert decoded is not None
        clauses.append('and formation collate "C" > %(after_formation)s')
        params["after_formation"] = decoded.key
    clauses.append('order by formation collate "C" limit %(limit)s')

    found = rows(connection, "\n".join(clauses), params)
    for item in found:
        for field in ("formation_groups", "basins", "aliases", "source_ids"):
            item[field] = sorted(item[field])
    items, has_more = page(found, limit)
    next_cursor = (
        encode_cursor(
            key=items[-1]["formation"],
            tiebreak="",
            as_of=knowledge_as_of,
            fingerprint=fingerprint,
            valid_as_of=valid_as_of,
        )
        if has_more and items
        else None
    )
    labels = {
        pointer: term
        for index, _ in enumerate(items)
        for pointer, term in {
            f"/{index}/formation": "gt_formation",
            f"/{index}/formation_groups": "gt_formation",
            f"/{index}/basins": "gt_basin",
            f"/{index}/alias_count": "gt_formation_alias",
            f"/{index}/aliases": "gt_formation_alias",
            f"/{index}/source_ids": "gt_source",
        }.items()
    }
    return enveloped(
        request,
        items,
        as_of=knowledge_as_of,
        as_of_requested=iso(as_of) or "latest",
        labels=labels,
        next_cursor=next_cursor,
        links={
            "next": next_link("/v1/formations", filters | {"limit": limit}, next_cursor)
            if next_cursor
            else None
        },
    )
