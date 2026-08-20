"""The glossary (DIR-8): definitions are data, and the highlighter reads an index, not markup."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import Connection, Cursor, SpineLimit, rows
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import EXAMPLE_TERM_ID, request_example
from glasswell.api.pagination import (
    DEFAULT_LIMIT,
    decode_cursor,
    encode_cursor,
    next_link,
    page,
    query_fingerprint,
)
from glasswell.api.responses import EnvelopeModel, enveloped, iso
from glasswell.lineage.serialization import hash_payload

router = APIRouter(tags=["glossary"])

INDEX_PREFIX = "gix_"

# Where a term is bound to an API field, so /v1/glossary/{term} can answer "where does
# this appear". Generated from the label maps the routers already publish.
APPEARS_IN: dict[str, tuple[str, ...]] = {
    "gt_api_10_api_12_api_14": ("/v1/wells/{api10}#/api10",),
    "gt_land_unit": ("/v1/wells/{api10}#/land_unit_label",),
    "gt_confidential_well": ("/v1/wells/{api10}#/confidential_flag",),
    "gt_wellbore": ("/v1/wells/{api10}#/lateral_length_ft",),
    "gt_effective_date": ("/v1/wells#/effective_from",),
    "gt_crs_compute_crs": ("/v1/wells/{api10}#/compute_crs",),
    "gt_datum": ("/v1/wells/{api10}#/geometry/source_datum",),
    "gt_granularity": ("/v1/wells/{api10}/production#/granularity",),
    "gt_report_vintage": ("/v1/wells/{api10}/production#/series/oil_bbl_report_vintage",),
    "gt_liquids_policy": ("/v1/wells/{api10}/production#/series/oil_bbl",),
    "gt_withheld": ("/v1/wells/{api10}/production#/series/oil_bbl_null_semantics",),
    "gt_stream": ("/v1/wells/{api10}/production#/series/gas_mcf",),
    "gt_conformance_rule": ("/v1/conformance/{rule_id}#/rule_id",),
    "gt_quarantine": ("/v1/quarantine#/reason_code",),
}

_COLUMNS = (
    "term_id, term, aliases, short_definition, expanded_definition, domain_tags,"
    " related_terms, source_refs, first_surfaced_in, effective_from, highlightable"
)

_TERMS = f"""
select {_COLUMNS}
  from canonical.glossary_terms
 where true
"""

_INDEX = f"""
select {_COLUMNS}
  from canonical.glossary_terms
 order by term collate "C"
"""


class GlossaryTerm(BaseModel):
    term_id: str = Field(description="Stable id; this is what meta.labels points at.")
    term: str = Field(description="Surface form of the term.")
    aliases: list[str] = Field(description="Other spellings that resolve to this term.")
    short_definition: str = Field(description="One-line definition for a hover.")
    domain_tags: list[str] = Field(description="Domains the term belongs to.")
    highlightable: bool = Field(
        description="False for ordinary words: reachable, but never auto-highlighted (M7)."
    )


class TermSite(BaseModel):
    kind: str = Field(description="Where it appears: api_field, ui_label, chart_axis.")
    ref: str = Field(description="Path and JSON Pointer of the field that carries the term.")


class GlossaryTermDetail(GlossaryTerm):
    expanded_definition: str = Field(description="The long form the drawer renders.")
    related_terms: list[str] = Field(description="Terms worth reading next.")
    source_refs: list[str] = Field(description="Where the definition came from.")
    first_surfaced_in: str | None = Field(description="Where the term first appeared.")
    effective_from: date = Field(description="When this definition took effect.")
    appears_in: list[TermSite] = Field(description="API fields that carry this term.")


class IndexEntry(BaseModel):
    surface: str = Field(description="Lower-cased surface form to match on.")
    term_id: str = Field(description="Term the surface form resolves to.")
    n_words: int = Field(description="Word count, so the client builds its trie in one pass.")


class GlossaryIndex(BaseModel):
    index_version: str = Field(description="Content address of the term rows it was built from.")
    entries: list[IndexEntry] = Field(description="Surface forms, longest-match first.")
    stopwords: list[str] = Field(description="Glossary terms excluded from auto-highlighting.")


def _term(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "term_id": row["term_id"],
        "term": row["term"],
        "aliases": row["aliases"],
        "short_definition": row["short_definition"],
        "domain_tags": row["domain_tags"],
        "highlightable": row["highlightable"],
    }


@router.get(
    "/glossary",
    operation_id="list_glossary_terms",
    summary="List glossary terms",
    description=(
        "Every term the product uses, alphabetically, with its short definition and its"
        " aliases. `q` matches the term and its aliases. The glossary is data promoted"
        " through the same rules as everything else, not markup embedded in views."
    ),
    response_model=EnvelopeModel[list[GlossaryTerm]],
    openapi_extra=request_example(query={"limit": 5}),
    responses=problem_responses(
        "validation_failed", "cursor_malformed", "cursor_query_mismatch", "service_degraded"
    ),
)
def list_glossary_terms(
    request: Request,
    connection: Connection,
    cursor: Cursor = None,
    limit: SpineLimit = DEFAULT_LIMIT,
    q: Annotated[str | None, Query(description="Match a term or one of its aliases.")] = None,
    domain_tag: Annotated[str | None, Query(description="Filter to one domain tag.")] = None,
) -> JSONResponse:
    filters = {"q": q, "domain_tag": domain_tag}
    fingerprint = query_fingerprint(filters)
    params: dict[str, Any] = {"limit": limit + 1}
    clauses = [_TERMS]
    if q is not None:
        clauses.append(
            "and (term ilike '%%' || %(q)s || '%%'"
            " or exists (select 1 from unnest(aliases) alias where alias ilike %(q)s))"
        )
        params["q"] = q
    if domain_tag is not None:
        clauses.append("and %(domain_tag)s = any(domain_tags)")
        params["domain_tag"] = domain_tag
    if cursor is not None:
        decoded = decode_cursor(cursor, fingerprint=fingerprint)
        # Collation is pinned so the cursor comparison and the sort agree on one order.
        clauses.append('and (term collate "C", term_id) > (%(after_key)s, %(after_id)s)')
        params |= {"after_key": decoded.key, "after_id": decoded.tiebreak}
    clauses.append('order by term collate "C", term_id limit %(limit)s')

    found = rows(connection, "\n".join(clauses), params)
    items, has_more = page(found, limit)
    next_cursor = (
        encode_cursor(
            key=items[-1]["term"],
            tiebreak=items[-1]["term_id"],
            as_of=None,
            fingerprint=fingerprint,
        )
        if has_more and items
        else None
    )
    return enveloped(
        request,
        [_term(row) for row in items],
        next_cursor=next_cursor,
        links={
            "next": next_link("/v1/glossary", filters | {"limit": limit}, next_cursor)
            if next_cursor
            else None
        },
    )


@router.get(
    "/glossary/index",
    operation_id="get_glossary_index",
    summary="Term index for the highlighter",
    description=(
        "The compact artifact the UI highlighter consumes: pre-lowercased surface forms"
        " expanded from terms and aliases, each with its word count, plus the stopword"
        " list. Terms flagged non-highlightable are served as stopwords so a glossary"
        " containing ordinary words does not underline every third word on the page."
        " Declared before /glossary/{term} so `index` is not matched as a term."
    ),
    response_model=EnvelopeModel[GlossaryIndex],
    openapi_extra=request_example(),
    responses=problem_responses("service_degraded"),
)
def get_glossary_index(request: Request, connection: Connection) -> JSONResponse:
    found = rows(connection, _INDEX)
    entries: list[dict[str, Any]] = []
    stopwords: list[str] = []
    for row in found:
        surfaces = [row["term"], *row["aliases"]]
        if not row["highlightable"]:
            stopwords.extend(sorted({surface.lower() for surface in surfaces}))
            continue
        for surface in sorted({surface.lower() for surface in surfaces}):
            entries.append(
                {"surface": surface, "term_id": row["term_id"], "n_words": len(surface.split())}
            )
    entries.sort(key=lambda entry: (-entry["n_words"], entry["surface"]))
    data = {
        "index_version": INDEX_PREFIX + hash_payload([row["term_id"] for row in found])[:12],
        "entries": entries,
        "stopwords": sorted(set(stopwords)),
    }
    return enveloped(request, data)


@router.get(
    "/glossary/{term}",
    operation_id="get_glossary_term",
    summary="One glossary term",
    description=(
        "Accepts either the `gt_*` id or the surface form, case-folded: an agent holding a"
        " meta.labels value has an id and a human typing a URL has a word. Returns the"
        " expanded definition, related terms, the sources the definition came from, and"
        " the API fields that carry the term."
    ),
    response_model=EnvelopeModel[GlossaryTermDetail],
    openapi_extra=request_example(path={"term": EXAMPLE_TERM_ID}),
    responses=problem_responses("not_found", "service_degraded"),
)
def get_glossary_term(
    request: Request,
    connection: Connection,
    term: Annotated[str, Path(description="Term id (gt_*) or the surface form.")],
) -> JSONResponse:
    found = rows(
        connection,
        _TERMS + " and (term_id = %(term)s or lower(term) = lower(%(term)s))",
        {"term": term},
    )
    if not found:
        raise ProblemError("not_found", detail=f"no glossary term {term!r}")
    row = found[0]
    data = _term(row) | {
        "expanded_definition": row["expanded_definition"],
        "related_terms": row["related_terms"],
        "source_refs": row["source_refs"],
        "first_surfaced_in": row["first_surfaced_in"],
        "effective_from": iso(row["effective_from"]),
        "appears_in": [
            {"kind": "api_field", "ref": reference}
            for reference in APPEARS_IN.get(row["term_id"], ())
        ],
    }
    return enveloped(request, data)
