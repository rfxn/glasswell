"""SB-07 §9.4 remounted under /v1: explain, derivations, manifests.

The handlers are the spine's. This module supplies transport, paging and the envelope
and adds no lineage logic of its own — a second chain resolver would be a review failure.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path as PathType
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse, Response

from glasswell.api.deps import AsOf, Connection, Cursor, Principal, SpineLimit, rows
from glasswell.api.errors import ProblemError, problem_responses, removed_query_parameters
from glasswell.api.examples import (
    CONTENT_ADDRESS_NOTE,
    EXAMPLE_DERIVATION_ID,
    EXAMPLE_MANIFEST_ID,
    EXAMPLE_VINTAGE_ID,
    VINTAGE_ID_NOTE,
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
from glasswell.api.principal import Principal as ResolvedPrincipal
from glasswell.api.responses import EnvelopeModel, enveloped, iso
from glasswell.lineage.envelope import LINEAGE_SIDECAR, _explain_link
from glasswell.lineage.explain import MAX_DEPTH, MAX_HANDLES, resolve_chains, to_json
from glasswell.lineage.fetch import resolve_raw_root
from glasswell.lineage.ids import format_handle

router = APIRouter(tags=["lineage"])

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]")

_DERIVATION = """
select derivation_id, operation, output_store, output_dataset, output_partition, output_locator,
       output_sha256, output_rows, output_schema_version, params, params_hash, code_version,
       code_dirty, env_id, model_id, recipe_id, created_vintage, created_at, duration_ms,
       correlation_id, status, determinism_class, ttl_class
  from lineage.derivations
 where derivation_id = %(derivation_id)s
"""

_INPUTS = """
select ord, kind, ref_id, selector, as_of_vintage, role
  from lineage.derivation_inputs
 where derivation_id = %(derivation_id)s
 order by ord
"""

_RULES = """
select dr.rule_id, dr.applied_rows, cr.rule_kind, cr.rule_family
  from lineage.derivation_rules dr
  left join lineage.conformance_rules cr on cr.rule_id = dr.rule_id
 where dr.derivation_id = %(derivation_id)s
 order by dr.rule_id
"""

_MANIFEST_COLUMNS = (
    "manifest_id, source_id, source_key, sha256, bytes, acquisition_url, acquisition_method,"
    " fetched_at, fetch_vintage, media_type, decompressed_inventory, supersedes_manifest_id,"
    " storage_uri, license_note, redistributable, fetch_derivation_id"
)

_MANIFESTS = f"""
select {_MANIFEST_COLUMNS},
       (select m2.manifest_id from lineage.manifests m2
         where m2.supersedes_manifest_id = m.manifest_id) as superseded_by
  from lineage.manifests m
 where true
"""

_VINTAGE_COLUMNS = (
    "vintage_id, source_id, vintage_date, manifest_ids, opened_at, promotion_derivation_id,"
    " rows_examined, rows_appended, months_touched, restatement_summary"
)

_VINTAGES = f"""
select {_VINTAGE_COLUMNS}
  from lineage.vintages
 where true
"""

_DERIVATION_COLLECTION = """
select derivation_id, operation, output_store, output_dataset, output_rows, code_version,
       created_vintage, created_at, status, determinism_class, recipe_id, model_id
  from lineage.derivations
 where true
"""


class ChainNode(BaseModel):
    """One node of a chain: a derivation, a manifest, or a cited rule/model reference."""

    model_config = {"extra": "allow"}

    id: str = Field(description="Node id: a derivation id, a manifest id, or a reference.")
    type: Literal["derivation", "manifest", "rule", "model", "external"] = Field(
        description="What kind of node this is; terminals are manifests."
    )
    explanation: str = Field(description="One sentence the lineage drawer renders verbatim.")


class ChainEdge(BaseModel):
    from_: str = Field(alias="from", description="Node the edge starts at.")
    to: str = Field(description="Node the edge points at.")
    role: str = Field(description="primary, crosswalk, validator, calibration or grid.")
    as_of_vintage: date | None = Field(description="Vintage the input was read at.")


class Chain(BaseModel):
    handle: str = Field(description="The handle that was resolved.")
    root: str = Field(description="Derivation the handle addresses.")
    depth: int = Field(
        description="Levels walked from the root.",
        json_schema_extra=not_a_figure("Graph depth of the resolved chain, not data."),
    )
    truncated: bool = Field(description="True when the walk stopped before the terminals.")
    as_of_vintage: date | None = Field(description="Knowledge time of the root derivation.")
    nodes: list[ChainNode] = Field(description="Every node reached, root first.")
    edges: list[ChainEdge] = Field(description="Edges between the nodes.")
    terminals: list[str] = Field(description="Manifest ids the chain ends at.")
    recipe: str | None = Field(description="Recipe id, where the derivation recorded one.")
    warnings: list[str] = Field(description="Why a walk stopped short, where it did.")


class Chains(BaseModel):
    chains: list[Chain] = Field(description="One chain per requested handle, in request order.")


class DerivationOutput(BaseModel):
    store: str = Field(description="Where the output was written.")
    dataset: str = Field(description="Dataset the derivation produced.")
    partition: dict[str, str] = Field(description="Partition keys of the output.")
    sha256: str | None = Field(description="Hash of the output artifact, where taken.")
    rows: int | None = Field(
        description="Rows written.",
        json_schema_extra=not_a_figure(
            "Row count a derivation recorded when it wrote its output."
        ),
    )
    locator: str = Field(description="Where the artifact lives, when it is a file.")


class DerivationInput(BaseModel):
    ord: int = Field(
        description="Ordinal position of the input.",
        json_schema_extra=not_a_figure("Ordinal position of a derivation input."),
    )
    kind: str = Field(description="derivation, manifest, rule, model or external.")
    ref_id: str = Field(description="Id of the referenced object.")
    selector: str | None = Field(description="Selector narrowing the input.")
    as_of_vintage: date | None = Field(description="Vintage the input was read at.")
    role: str = Field(description="Role the input played.")


class DerivationRule(BaseModel):
    rule_id: str = Field(description="Conformance rule cited by this derivation.")
    applied_rows: int | None = Field(
        description="Rows the rule touched.",
        json_schema_extra=not_a_figure(
            "How many rows a conformance rule touched during that derivation."
        ),
    )
    rule_kind: str | None = Field(description="Kind of the cited rule.")
    rule_family: str | None = Field(description="Family the rule belongs to.")


class Derivation(BaseModel):
    derivation_id: str = Field(description="Content address of the derivation spec.")
    operation: str = Field(description="Operation that ran.")
    output: DerivationOutput = Field(description="What it produced.")
    params_hash: str = Field(description="Hash of the parameters.")
    params: dict[str, Any] = Field(description="Parameters exactly as recorded.")
    code_version: str = Field(description="Code version that produced it.")
    code_dirty: bool = Field(description="Whether the tree was dirty at capture time.")
    env_id: str = Field(description="Pinned environment id.")
    model_id: str | None = Field(description="Model, where one was used.")
    recipe_id: str | None = Field(description="Recipe, where one was recorded.")
    created_vintage: date | None = Field(description="Knowledge time, not wall clock.")
    created_at: datetime = Field(description="When the derivation ran.")
    duration_ms: int = Field(
        description="How long it took.",
        json_schema_extra=not_a_figure("Wall-clock cost of the recorded derivation."),
    )
    correlation_id: str = Field(description="Run correlation id.")
    status: str = Field(description="ok or failed.")
    determinism_class: str = Field(description="D1, D2 or D3.")
    inputs: list[DerivationInput] | None = Field(
        default=None, description="Present when include=inputs."
    )
    rules: list[DerivationRule] | None = Field(
        default=None, description="Present when include=rules."
    )


class Manifest(BaseModel):
    manifest_id: str = Field(description="Content address of the fetched bytes.")
    source_id: str = Field(description="Source registry id.")
    source_key: str = Field(description="Key of the artifact within the source.")
    sha256: str = Field(description="Hash of the bytes as fetched.")
    bytes: int = Field(
        description="Byte length of the artifact.",
        json_schema_extra=not_a_figure(
            "Byte length of the fetched artifact, recorded on the manifest."
        ),
    )
    acquisition_url: str = Field(description="Exact URL the bytes came from.")
    acquisition_method: str = Field(description="How it was acquired.")
    fetched_at: datetime = Field(description="When it was fetched.")
    fetch_vintage: date = Field(description="Self-stamped knowledge-time label (DIR-9).")
    media_type: str | None = Field(description="Media type, where the server declared one.")
    decompressed_inventory: list[dict[str, Any]] = Field(description="Members of an archive.")
    supersedes: str | None = Field(description="Manifest this one replaced.")
    superseded_by: str | None = Field(description="Manifest that replaced this one.")
    storage_uri: str | None = Field(
        description="Absolute path of the raw-zone copy on the serving host; owner scope only."
    )
    license_note: str | None = Field(description="Licensing note recorded for the source.")
    redistributable: bool = Field(description="Whether the bytes may be re-served.")
    fetch_derivation_id: str | None = Field(description="Derivation that recorded the fetch.")


class Vintage(BaseModel):
    vintage_id: str = Field(description="Id of the (source, vintage) promotion.")
    source_id: str = Field(description="Source the vintage was promoted from.")
    vintage_date: date = Field(description="Knowledge-time label of the promotion (DIR-9).")
    manifest_ids: list[str] = Field(description="Manifests the promotion read.")
    opened_at: datetime = Field(description="When the vintage was opened.")
    promotion_derivation_id: str | None = Field(description="Derivation that promoted it.")
    rows_examined: int = Field(description="Rows read during the promotion.")
    rows_appended: int = Field(description="Rows appended; a restatement appends (DIR-2).")
    months_touched: list[str] = Field(description="Production months the promotion covered.")
    restatement_summary: dict[str, Any] = Field(
        description="Per-reason counts of values this vintage restated."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        alias="_lineage",
        description=(
            "Dotted path to the handle of the derivation that promoted this vintage"
            " (SB-07 §9.1b). Absent where no derivation did."
        ),
    )


class DerivationSummary(BaseModel):
    derivation_id: str = Field(description="Content address of the derivation spec.")
    operation: str = Field(description="Operation that ran.")
    output_store: str = Field(description="Where the output was written.")
    output_dataset: str = Field(description="Dataset it produced.")
    output_rows: int | None = Field(
        description="Rows written.",
        json_schema_extra=not_a_figure(
            "Rows a derivation recorded when it wrote its output, in the derivation"
            " collection. Same class as /output/rows on the expanded record."
        ),
    )
    code_version: str = Field(description="Code version that produced it.")
    created_vintage: date | None = Field(description="Knowledge time, not wall clock.")
    created_at: datetime = Field(description="When the derivation ran.")
    status: str = Field(description="ok or failed.")
    determinism_class: str = Field(description="D1, D2 or D3.")
    recipe_id: str | None = Field(description="Recipe, where one was recorded.")
    model_id: str | None = Field(description="Model, where one was used.")


def _depth(raw: str) -> int | Literal["full"]:
    if raw == "full":
        return "full"
    try:
        value = int(raw)
    except ValueError:
        raise ProblemError(
            "validation_failed",
            detail="depth must be an integer or 'full'",
            errors=[{"pointer": "/query/depth", "code": "depth_format", "detail": raw}],
        ) from None
    if value < 1 or value > MAX_DEPTH:
        raise ProblemError(
            "validation_failed",
            detail=f"depth must be between 1 and {MAX_DEPTH}",
            errors=[{"pointer": "/query/depth", "code": "depth_cap", "detail": raw}],
        )
    return value


@router.get(
    "/explain",
    operation_id="get_explain",
    summary="Resolve handles to their lineage chains",
    description=(
        "Walks each handle back through the derivation graph to the manifests it came"
        " from, returning nodes, edges, terminals and a one-sentence explanation per node."
        " This is the call that turns a number on a chart into a checksummed government"
        " file. Up to twenty handles per request and eight levels deep; both caps are"
        " refused rather than clamped. A handle that cannot be resolved returns"
        " `lineage_unresolved` naming the last node that did resolve — never a bare 404."
        + CONTENT_ADDRESS_NOTE
    ),
    response_model=EnvelopeModel[Chains],
    openapi_extra=request_example(query={"h": [EXAMPLE_DERIVATION_ID], "depth": "full"}),
    responses=problem_responses(
        "lineage_unresolved", "selector_ambiguous", "validation_failed", "service_degraded"
    ),
    dependencies=[
        Depends(removed_query_parameters(ref="use h, which is repeatable 1 to 20 per request"))
    ],
)
def get_explain(
    request: Request,
    connection: Connection,
    h: Annotated[
        list[str],
        Query(description=f"Derivation handle; repeatable, 1 to {MAX_HANDLES} per request."),
    ],
    depth: Annotated[
        str, Query(description=f"Levels to walk: an integer up to {MAX_DEPTH}, or 'full'.")
    ] = "3",
    format: Annotated[
        Literal["json"], Query(description="Response format. Only json ships in this slice.")
    ] = "json",
) -> JSONResponse:
    if len(h) > MAX_HANDLES:
        raise ProblemError(
            "validation_failed",
            detail=f"at most {MAX_HANDLES} handles per request, not {len(h)}",
            errors=[{"pointer": "/query/h", "code": "handle_cap", "detail": str(len(h))}],
        )
    chains = resolve_chains(connection, h, depth=_depth(depth))
    return enveloped(request, {"chains": [to_json(chain) for chain in chains]})


@router.get(
    "/derivations/{derivation_id}",
    operation_id="get_derivation",
    summary="One derivation record",
    description=(
        "The recorded derivation: what ran, on what inputs, under which code version and"
        " conformance rules, and what it produced. Ask for `include=inputs` and"
        " `include=rules` to expand them. Derivation ids are content addresses, so this"
        " record is immutable."
        + CONTENT_ADDRESS_NOTE
    ),
    response_model=EnvelopeModel[Derivation],
    openapi_extra=request_example(
        path={"derivation_id": EXAMPLE_DERIVATION_ID}, query={"include": ["inputs", "rules"]}
    ),
    responses=problem_responses("not_found", "validation_failed", "service_degraded"),
)
def get_derivation(
    request: Request,
    connection: Connection,
    derivation_id: Annotated[str, Path(description="Content-addressed derivation id.")],
    include: Annotated[
        list[Literal["inputs", "rules"]] | None,
        Query(description="Expand the derivation's inputs or its cited rules; repeatable."),
    ] = None,
) -> JSONResponse:
    found = rows(connection, _DERIVATION, {"derivation_id": derivation_id})
    if not found:
        raise ProblemError("not_found", detail=f"no derivation {derivation_id}")
    row = found[0]
    data: dict[str, Any] = {
        "derivation_id": row["derivation_id"],
        "operation": row["operation"],
        "output": {
            "store": row["output_store"],
            "dataset": row["output_dataset"],
            "partition": row["output_partition"],
            "sha256": row["output_sha256"],
            "rows": row["output_rows"],
            "locator": row["output_locator"],
        },
        "params_hash": row["params_hash"],
        "params": row["params"],
        "code_version": row["code_version"],
        "code_dirty": row["code_dirty"],
        "env_id": row["env_id"],
        "model_id": row["model_id"],
        "recipe_id": row["recipe_id"],
        "created_vintage": iso(row["created_vintage"]),
        "created_at": iso(row["created_at"]),
        "duration_ms": row["duration_ms"],
        "correlation_id": row["correlation_id"],
        "status": row["status"],
        "determinism_class": row["determinism_class"],
    }
    expand = set(include or ())
    if "inputs" in expand:
        data["inputs"] = [
            {
                "ord": item["ord"],
                "kind": item["kind"],
                "ref_id": item["ref_id"],
                "selector": item["selector"],
                "as_of_vintage": iso(item["as_of_vintage"]),
                "role": item["role"],
            }
            for item in rows(connection, _INPUTS, {"derivation_id": derivation_id})
        ]
    if "rules" in expand:
        data["rules"] = rows(connection, _RULES, {"derivation_id": derivation_id})
    return enveloped(
        request,
        data,
        as_of=row["created_vintage"],
        links={"explain": f"/v1/explain?h={quote(derivation_id, safe='')}&depth=full"},
    )


def _manifest(row: dict[str, Any], *, principal: ResolvedPrincipal) -> dict[str, Any]:
    """DR-33: `storage_uri` is an absolute path on this host — deployment detail, owner only.

    Everything an auditor needs to verify the bytes independently (sha256, the exact
    acquisition URL, the method and the vintage) stays on the record for every principal.
    """
    return {
        "manifest_id": row["manifest_id"],
        "source_id": row["source_id"],
        "source_key": row["source_key"],
        "sha256": row["sha256"],
        "bytes": row["bytes"],
        "acquisition_url": row["acquisition_url"],
        "acquisition_method": row["acquisition_method"],
        "fetched_at": iso(row["fetched_at"]),
        "fetch_vintage": iso(row["fetch_vintage"]),
        "media_type": row["media_type"],
        "decompressed_inventory": row["decompressed_inventory"],
        "supersedes": row["supersedes_manifest_id"],
        "superseded_by": row["superseded_by"],
        "storage_uri": row["storage_uri"] if principal.scope == "owner" else None,
        "license_note": row["license_note"],
        "redistributable": row["redistributable"],
        "fetch_derivation_id": row["fetch_derivation_id"],
    }


@router.get(
    "/manifests",
    operation_id="list_manifests",
    summary="List raw-zone manifests",
    description=(
        "Every artifact this system has fetched, newest first, with its checksum and the"
        " exact URL it came from. `head_only` keeps the manifests nothing has superseded."
        " The bytes themselves are not served: the checksum plus the acquisition URL lets"
        " an auditor re-fetch from the regulator and hash it themselves (SB-07 §9.6)."
    ),
    response_model=EnvelopeModel[list[Manifest]],
    openapi_extra={
        **request_example(query={"limit": 5}),
        **dataset(
            id="manifests",
            title="Manifests",
            group="kitchen",
            collection_pointer="",
            row_id=["/manifest_id"],
            detail_operation="get_manifest",
            facets=["source_id", "source_key", "vintage_from", "vintage_to", "head_only"],
            columns={
                "default": [
                    "/manifest_id",
                    "/source_id",
                    "/source_key",
                    "/fetch_vintage",
                    "/bytes",
                    "/sha256",
                ],
                "hidden": ["/decompressed_inventory", "/license_note"],
                "hidden_reason": {
                    "/decompressed_inventory": "an archive's member list — rows, not a cell",
                    "/license_note": "long prose; the manifest detail is where it reads",
                },
                "sort": "/fetched_at",
            },
            intro="nb_dataset_manifests",
            order=22,
        ),
    },
    responses=problem_responses(
        "validation_failed", "cursor_malformed", "cursor_query_mismatch", "service_degraded"
    ),
)
def list_manifests(
    request: Request,
    connection: Connection,
    principal: Principal,
    cursor: Cursor = None,
    limit: SpineLimit = DEFAULT_LIMIT,
    as_of: AsOf = None,
    source_id: Annotated[str | None, Query(description="Filter to one source.")] = None,
    source_key: Annotated[str | None, Query(description="Filter to one source key.")] = None,
    vintage_from: Annotated[
        date | None, Query(description="Earliest fetch vintage to include.")
    ] = None,
    vintage_to: Annotated[
        date | None, Query(description="Latest fetch vintage to include.")
    ] = None,
    head_only: Annotated[
        bool, Query(description="Only manifests nothing supersedes.")
    ] = False,
) -> JSONResponse:
    filters = {
        "source_id": source_id,
        "source_key": source_key,
        "vintage_from": vintage_from,
        "vintage_to": vintage_to,
        "head_only": head_only or None,
        "as_of": as_of,
    }
    fingerprint = query_fingerprint(filters)
    params: dict[str, Any] = {"limit": limit + 1}
    clauses = [_MANIFESTS]
    if source_id is not None:
        clauses.append("and m.source_id = %(source_id)s")
        params["source_id"] = source_id
    if source_key is not None:
        clauses.append("and m.source_key = %(source_key)s")
        params["source_key"] = source_key
    if vintage_from is not None:
        clauses.append("and m.fetch_vintage >= %(vintage_from)s")
        params["vintage_from"] = vintage_from
    if vintage_to is not None:
        clauses.append("and m.fetch_vintage <= %(vintage_to)s")
        params["vintage_to"] = vintage_to
    if head_only:
        clauses.append(
            "and not exists (select 1 from lineage.manifests s"
            " where s.supersedes_manifest_id = m.manifest_id)"
        )
    if cursor is not None:
        decoded = decode_cursor(cursor, fingerprint=fingerprint)
        clauses.append("and (m.fetched_at, m.manifest_id) < (%(after_key)s, %(after_id)s)")
        params |= {"after_key": decoded.key, "after_id": decoded.tiebreak}
    clauses.append("order by m.fetched_at desc, m.manifest_id desc limit %(limit)s")

    found = rows(connection, "\n".join(clauses), params)
    items, has_more = page(found, limit)
    next_cursor = (
        encode_cursor(
            key=items[-1]["fetched_at"],
            tiebreak=items[-1]["manifest_id"],
            as_of=as_of,
            fingerprint=fingerprint,
        )
        if has_more and items
        else None
    )
    return enveloped(
        request,
        [_manifest(row, principal=principal) for row in items],
        as_of=as_of,
        as_of_requested=iso(as_of) or "latest",
        next_cursor=next_cursor,
        links={
            "next": next_link("/v1/manifests", filters | {"limit": limit}, next_cursor)
            if next_cursor
            else None
        },
    )


@router.get(
    "/manifests/{manifest_id}",
    operation_id="get_manifest",
    summary="One manifest",
    description=(
        "The terminal node of every lineage chain: the checksum, the byte length, the"
        " acquisition URL and method, the self-stamped fetch vintage, and the supersession"
        " links either side of it. Manifest ids are content addresses, so this record is"
        " immutable. The bytes are not served (SB-07 §9.6)."
        + CONTENT_ADDRESS_NOTE
    ),
    response_model=EnvelopeModel[Manifest],
    openapi_extra=request_example(path={"manifest_id": EXAMPLE_MANIFEST_ID}),
    responses=problem_responses("not_found", "service_degraded"),
)
def get_manifest(
    request: Request,
    connection: Connection,
    principal: Principal,
    manifest_id: Annotated[str, Path(description="Content-addressed manifest id.")],
) -> JSONResponse:
    found = rows(
        connection,
        _MANIFESTS + " and m.manifest_id = %(manifest_id)s",
        {"manifest_id": manifest_id},
    )
    if not found:
        raise ProblemError("not_found", detail=f"no manifest {manifest_id}")
    row = found[0]
    return enveloped(
        request,
        _manifest(row, principal=principal),
        as_of=row["fetch_vintage"],
        links={"source": f"/v1/manifests?source_id={row['source_id']}"},
    )


@router.get(
    "/derivations",
    operation_id="list_derivations",
    summary="List recorded derivations",
    description=(
        "Every derivation this system has recorded, newest first: what ran, what it"
        " produced and under which code version. Filter by `operation` or `status` to find"
        " the run behind a figure when you have the dataset but not the handle. Expand one"
        " with `GET /v1/derivations/{derivation_id}`."
    ),
    response_model=EnvelopeModel[list[DerivationSummary]],
    openapi_extra={
        **request_example(query={"limit": 5}),
        **dataset(
            id="derivations",
            title="Derivations",
            group="kitchen",
            collection_pointer="",
            row_id=["/derivation_id"],
            detail_operation="get_derivation",
            facets=["operation", "status"],
            columns={
                "default": [
                    "/derivation_id",
                    "/operation",
                    "/status",
                    "/output_dataset",
                    "/output_rows",
                    "/created_at",
                    "/determinism_class",
                ],
                "sort": "/created_at",
            },
            intro="nb_dataset_derivations",
            order=24,
        ),
    },
    responses=problem_responses(
        "validation_failed", "cursor_malformed", "cursor_query_mismatch", "service_degraded"
    ),
)
def list_derivations(
    request: Request,
    connection: Connection,
    cursor: Cursor = None,
    limit: SpineLimit = DEFAULT_LIMIT,
    operation: Annotated[str | None, Query(description="Filter to one operation.")] = None,
    status: Annotated[
        Literal["ok", "failed"] | None, Query(description="Filter to ok or failed runs.")
    ] = None,
) -> JSONResponse:
    filters = {"operation": operation, "status": status}
    fingerprint = query_fingerprint(filters)
    params: dict[str, Any] = {"limit": limit + 1}
    clauses = [_DERIVATION_COLLECTION]
    if operation is not None:
        clauses.append("and operation = %(operation)s")
        params["operation"] = operation
    if status is not None:
        clauses.append("and status = %(status)s")
        params["status"] = status
    if cursor is not None:
        decoded = decode_cursor(cursor, fingerprint=fingerprint)
        clauses.append("and (created_at, derivation_id) < (%(after_key)s, %(after_id)s)")
        params |= {"after_key": decoded.key, "after_id": decoded.tiebreak}
    clauses.append("order by created_at desc, derivation_id desc limit %(limit)s")

    found = rows(connection, "\n".join(clauses), params)
    items, has_more = page(found, limit)
    next_cursor = (
        encode_cursor(
            key=items[-1]["created_at"],
            tiebreak=items[-1]["derivation_id"],
            as_of=None,
            fingerprint=fingerprint,
        )
        if has_more and items
        else None
    )
    return enveloped(
        request,
        [
            {
                "derivation_id": row["derivation_id"],
                "operation": row["operation"],
                "output_store": row["output_store"],
                "output_dataset": row["output_dataset"],
                "output_rows": row["output_rows"],
                "code_version": row["code_version"],
                "created_vintage": iso(row["created_vintage"]),
                "created_at": iso(row["created_at"]),
                "status": row["status"],
                "determinism_class": row["determinism_class"],
                "recipe_id": row["recipe_id"],
                "model_id": row["model_id"],
            }
            for row in items
        ],
        next_cursor=next_cursor,
        links={
            "next": next_link("/v1/derivations", filters | {"limit": limit}, next_cursor)
            if next_cursor
            else None
        },
    )


# A-4. Branches, not leaves: the client resolves by longest prefix, so the entry written for
# `restatement_summary` covers every per-reason count a promotion adds under it.
_VINTAGE_SIDECAR: tuple[str, ...] = ("rows_examined", "rows_appended", "restatement_summary")


def _vintage(row: dict[str, Any]) -> dict[str, Any]:
    record = {
        "vintage_id": row["vintage_id"],
        "source_id": row["source_id"],
        "vintage_date": iso(row["vintage_date"]),
        "manifest_ids": list(row["manifest_ids"]),
        "opened_at": iso(row["opened_at"]),
        "promotion_derivation_id": row["promotion_derivation_id"],
        "rows_examined": row["rows_examined"],
        "rows_appended": row["rows_appended"],
        "months_touched": list(row["months_touched"]),
        "restatement_summary": dict(row["restatement_summary"]),
    }
    if row["promotion_derivation_id"] is not None:
        handle = format_handle(row["promotion_derivation_id"])
        record[LINEAGE_SIDECAR] = dict.fromkeys(_VINTAGE_SIDECAR, handle)
    return record


def _vintage_explain(records: list[dict[str, Any]]) -> str | None:
    """The S9 one-call path for a sidecar-carried page, read back off the sidecars so it
    cannot advertise a handle the records do not carry.

    `attach_lineage` builds this itself for figures and series; a sidecar the router wrote
    never reaches its walk, so the link is built here — from the spine's own function,
    which owns the percent-encoding and the `MAX_HANDLES` cap a hundred-row page needs.
    """
    found = [handle for record in records for handle in record.get(LINEAGE_SIDECAR, {}).values()]
    return _explain_link(found) if found else None


@router.get(
    "/vintages",
    operation_id="list_vintages",
    summary="List published vintages",
    description=(
        "One row per (source, knowledge time) promotion: what it read, how many rows it"
        " examined and appended, which months it touched, and what it restated. This is"
        " the index behind `as_of` — every vintage here is a value `as_of` can select."
    ),
    response_model=EnvelopeModel[list[Vintage]],
    openapi_extra={
        **request_example(query={"limit": 10}),
        # `source_id` is the only facet because it is the only query parameter besides `limit`:
        # this operation declares no `cursor`, and §3.6's uncursored form is the honest render.
        **dataset(
            id="vintages",
            title="Vintages",
            group="kitchen",
            collection_pointer="",
            row_id=["/vintage_id"],
            detail_operation="get_vintage",
            facets=["source_id"],
            columns={
                "default": [
                    "/vintage_id",
                    "/source_id",
                    "/vintage_date",
                    "/opened_at",
                    "/rows_examined",
                    "/rows_appended",
                ],
                "hidden": ["/months_touched", "/restatement_summary"],
                "hidden_reason": {
                    "/months_touched": "one entry per production month — rows, not a cell",
                    "/restatement_summary": "per-reason counts; the detail row renders the object",
                },
                "sort": "/vintage_date",
            },
            intro="nb_dataset_vintages",
            order=23,
        ),
    },
    responses=problem_responses("validation_failed", "service_degraded"),
)
def list_vintages(
    request: Request,
    connection: Connection,
    limit: SpineLimit = DEFAULT_LIMIT,
    source_id: Annotated[str | None, Query(description="Filter to one source.")] = None,
) -> JSONResponse:
    params: dict[str, Any] = {"limit": limit}
    clauses = [_VINTAGES]
    if source_id is not None:
        clauses.append("and source_id = %(source_id)s")
        params["source_id"] = source_id
    clauses.append("order by vintage_date desc, source_id limit %(limit)s")
    found = rows(connection, "\n".join(clauses), params)
    records = [_vintage(row) for row in found]
    return enveloped(request, records, links={"explain": _vintage_explain(records)})


@router.get(
    "/vintages/{vintage_id}",
    operation_id="get_vintage",
    summary="One published vintage",
    description=(
        "The promotion record `as_of` resolves to, including the manifests it read and its"
        " restatement summary. Vintages are append-only: a correction opens a new one."
        + VINTAGE_ID_NOTE
    ),
    response_model=EnvelopeModel[Vintage],
    openapi_extra=request_example(path={"vintage_id": EXAMPLE_VINTAGE_ID}),
    responses=problem_responses("not_found", "service_degraded"),
)
def get_vintage(
    request: Request,
    connection: Connection,
    vintage_id: Annotated[str, Path(description="Id of the (source, vintage) promotion.")],
) -> JSONResponse:
    found = rows(
        connection, _VINTAGES + " and vintage_id = %(vintage_id)s", {"vintage_id": vintage_id}
    )
    if not found:
        raise ProblemError("not_found", detail=f"no vintage {vintage_id}")
    row = found[0]
    record = _vintage(row)
    return enveloped(
        request,
        record,
        as_of=row["vintage_date"],
        links={
            "source": f"/v1/vintages?source_id={row['source_id']}",
            "explain": _vintage_explain([record]),
        },
    )


@router.get(
    "/manifests/{manifest_id}/bytes",
    operation_id="get_manifest_bytes",
    summary="Download the raw bytes",
    description=(
        "The archived copy of the fetched artifact, byte-identical to what was hashed."
        " Owner scope, unless the source's terms mark the artifact redistributable"
        " (SB-07 §9.6) — an auditor does not need our copy, because the checksum and the"
        " exact acquisition URL let them re-fetch from the regulator and hash it"
        " themselves, which is the stronger audit. `404` when this host does not hold the"
        " bytes; the record at `/v1/manifests/{manifest_id}` still resolves."
        + CONTENT_ADDRESS_NOTE
    ),
    response_class=Response,
    openapi_extra=request_example(path={"manifest_id": EXAMPLE_MANIFEST_ID}),
    responses=problem_responses("forbidden", "not_found", "service_degraded"),
)
def get_manifest_bytes(
    request: Request,
    connection: Connection,
    principal: Principal,
    manifest_id: Annotated[str, Path(description="Content-addressed manifest id.")],
) -> Response:
    found = rows(
        connection,
        _MANIFESTS + " and m.manifest_id = %(manifest_id)s",
        {"manifest_id": manifest_id},
    )
    if not found:
        raise ProblemError("not_found", detail=f"no manifest {manifest_id}")
    row = found[0]
    if principal.scope != "owner" and not row["redistributable"]:
        raise ProblemError(
            "forbidden",
            detail=(
                f"{row['source_id']} bytes are not marked redistributable; verify with the"
                f" sha256 and {row['acquisition_url']} instead"
            ),
        )
    payload = _payload_within_raw_zone(row["storage_uri"])
    if payload is None:
        raise ProblemError(
            "not_found", detail=f"this host holds no raw-zone copy for manifest {manifest_id}"
        )
    return Response(
        payload.read_bytes(),
        media_type=row["media_type"] or "application/octet-stream",
        headers={
            "ETag": f'"sha256:{row["sha256"]}"',
            "Content-Disposition": f'attachment; filename="{_download_name(row)}"',
        },
    )


def _payload_within_raw_zone(storage_uri: str) -> PathType | None:
    """`storage_uri` is a filesystem path from a table, so it is treated as untrusted input.

    Resolving before the containment check is what closes both traversal and a symlink
    planted inside the zone; a path that escapes is indistinguishable from a missing file.
    """
    if not storage_uri:
        return None
    root = resolve_raw_root().resolve()
    candidate = PathType(storage_uri).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate


def _download_name(row: dict[str, Any]) -> str:
    """Quoted into a header, so it carries no quote, control byte or path separator."""
    stem = PurePosixPath(row["source_key"]).name or row["manifest_id"]
    return _SAFE_FILENAME.sub("_", stem)[:100] or row["manifest_id"]
