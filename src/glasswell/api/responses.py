"""The one way a router returns a body: through `attach_lineage`, inside the envelope.

No router constructs a bare dict. That is what makes the naked-number walker a property
of the application rather than a habit of whoever wrote the handler.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from glasswell.lineage.envelope import attach_lineage


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

    data: DataT
    meta: MetaModel
    links: LinksModel


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


def freshness_state(retrieval_vintage: date | None, *, today: date) -> str:
    if retrieval_vintage is None:
        return "never_fetched"
    return "current" if (today - retrieval_vintage).days <= STALE_AFTER_DAYS else "stale"


def month_label(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None
