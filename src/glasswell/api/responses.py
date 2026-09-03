"""The one way a router returns a body: through `attach_lineage`, inside the envelope.

No router constructs a bare dict. That is what makes the naked-number walker a property
of the application rather than a habit of whoever wrote the handler.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

import psycopg
from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import ExplainFlags
from glasswell.lineage.envelope import (
    EXPLAIN_BLOCK,
    ExplainInliner,
    InlinedExplain,
    attach_lineage,
)
from glasswell.lineage.errors import InvalidSelector, LineageUnresolved
from glasswell.lineage.explain import PostgresGraph, resolve_chain_from, to_json


class FigureModel(BaseModel):
    """SB-07 §9.1(a): the only shape a served scalar takes."""

    model_config = ConfigDict(extra="forbid")

    value: str = Field(description="Decimal as a string; a float round-trip is not reproducible.")
    unit: str = Field(description="Unit of the value. Mandatory on every figure (A-13).")
    basis: str | None = Field(
        default=None, description="Liquids basis, e.g. oil+condensate. Mandatory on liquids."
    )
    granularity: str | None = Field(
        default=None, description="well_observed or lease_allocated (DIR-3)."
    )
    report_vintage: date | None = Field(
        default=None, description="Knowledge time the value was reported at (DIR-2)."
    )
    d: str = Field(description="Derivation handle; resolve it at /v1/explain.")


class AsOfModel(BaseModel):
    requested: str = Field(description="What the caller asked for; `latest` when unspecified.")
    resolved: date | None = Field(description="The concrete vintage actually served.")


class MetaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(description="ULID for this request; echoed in every problem body.")
    as_of: AsOfModel = Field(description="Requested and resolved vintage (SB-04 §2.5).")
    source_freshness: dict[str, Any] = Field(
        default_factory=dict, description="Per-source retrieval vintage and state."
    )
    labels: dict[str, str] = Field(
        default_factory=dict, description="JSON Pointer to glossary term_id (DIR-8)."
    )
    next_cursor: str | None = Field(
        default=None, description="Opaque cursor for the next page; null at the end."
    )
    warnings: list[dict[str, Any]] = Field(
        default_factory=list, description="Structured warnings: code, detail, optional pointer."
    )
    deprecations: list[dict[str, Any]] = Field(
        default_factory=list, description="Deprecations in force for this operation."
    )
    status_classes: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "The canonical well-status class domain, served once by /v1/jurisdictions and"
            " omitted everywhere else. Each row carries the class, its label, colour, glyph,"
            " zoom floor, legend order, whether it is the absence class, its jurisdiction-"
            "neutral note and the rule that declared it. It sits in `meta` because the domain"
            " is not a jurisdiction and `data` is a bare array of jurisdictions."
        ),
    )


class LinksModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    self_link: str | None = Field(
        default=None, alias="self", description="Canonical path of this response."
    )
    next: str | None = Field(default=None, description="Next page, or null at the end.")
    explain: str | None = Field(
        default=None, description="Pre-built /v1/explain call for every handle in the body."
    )


class EnvelopeModel[DataT](BaseModel):
    """SB-04 §2.2. `data` is the payload itself — a collection is the array, not `{items}`."""

    model_config = ConfigDict(populate_by_name=True)

    data: DataT
    meta: MetaModel
    links: LinksModel
    explain: dict[str, Any] | None = Field(
        default=None,
        alias=EXPLAIN_BLOCK,
        description=(
            "Present only when `?explain=true` was sent: one SB-07 §9.3 chain per derivation"
            " handle in this response, keyed by the handle itself. It sits beside `data`"
            " rather than inside it because it is keyed by handle, not by pointer, and"
            " because the flag must add nothing to the payload it explains (SB-07 §9.2)."
        ),
    )


def inline_for(
    connection: psycopg.Connection, flags: ExplainFlags
) -> ExplainInliner | None:
    """The §9.2 resolver, or None when the caller did not ask.

    One graph object for the whole response, and one handle's failure is that handle's: an
    optional diagnostic that can 404 a working figure would change the response, which is the
    single thing §9.2 says the flag never does.
    """
    if not flags.explain:
        return None

    def inline(handles: Sequence[str]) -> InlinedExplain:
        graph = PostgresGraph(connection)
        chains: dict[str, Any] = {}
        unresolved: dict[str, str] = {}
        for handle in handles:
            try:
                chains[handle] = to_json(
                    resolve_chain_from(graph, handle, depth=flags.explain_depth)
                )
            except LineageUnresolved as stopped:
                unresolved[handle] = stopped.reason
            except InvalidSelector:
                unresolved[handle] = "invalid_selector"
        return InlinedExplain(chains=chains, unresolved=unresolved)

    return inline


def enveloped(
    request: Request,
    data: Any,
    *,
    as_of: date | None = None,
    as_of_requested: str = "latest",
    labels: Mapping[str, str] | None = None,
    source_freshness: Mapping[str, Any] | None = None,
    next_cursor: str | None = None,
    links: Mapping[str, str | None] | None = None,
    warnings: Sequence[Mapping[str, Any] | str] = (),
    status_code: int = 200,
    explain: ExplainInliner | None = None,
    extra_handles: Sequence[str] = (),
    status_classes: Sequence[Mapping[str, Any]] | None = None,
) -> JSONResponse:
    resolved_links = {"self": request.url.path, **dict(links or {})}
    envelope = attach_lineage(
        data,
        as_of=as_of,
        request_id=request.state.request_id,
        links=resolved_links,
        labels=labels,
        source_freshness=source_freshness,
        next_cursor=next_cursor,
        as_of_requested=as_of_requested,
        warnings=warnings,
        explain=explain,
        extra_handles=extra_handles,
        status_classes=status_classes,
    )
    return JSONResponse(envelope.to_dict(), status_code=status_code)


def source_freshness(rows: Sequence[Mapping[str, Any]], *, today: date) -> dict[str, Any]:
    """Per-source `retrieval_vintage`, `declared_vintage` and state (bp:544)."""
    return {
        row["source_id"]: {
            "retrieval_vintage": row["retrieval_vintage"],
            "declared_vintage": row["declared_vintage"],
            "state": freshness_state(row["retrieval_vintage"], today=today),
        }
        for row in rows
    }


STALE_AFTER_DAYS = 45
# A registered source with no manifest has not gone stale — nobody has fetched it yet. The
# distinction is the endpoint's whole job: `stale` is a defect, `pending` is a plan.
PENDING = "pending"


def freshness_state(retrieval_vintage: date | None, *, today: date) -> str:
    if retrieval_vintage is None:
        return PENDING
    return "current" if (today - retrieval_vintage).days <= STALE_AFTER_DAYS else "stale"


def month_label(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None
