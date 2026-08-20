"""The response envelope: SB-04 §2.2 outside, SB-07 §9.1 lineage carriage inside `data`.

SB-04 errata E-01 settles the two-mechanism conflict: figure objects and the
`_lineage`/`_units`/`_basis` sidecars are the only representation of a handle. There is no
`meta.derivations` and no `meta.units` — a second map of the same fact can disagree with the
first, and SB-07 §10's naked-number harness walks the in-band form.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any
from urllib.parse import quote

from pydantic import Field

from glasswell.lineage.explain import MAX_HANDLES
from glasswell.lineage.ids import format_handle, parse_handle, parse_selector
from glasswell.lineage.models import Frozen
from glasswell.lineage.serialization import json_ready

# S-B's composed token, not R5's granularity field: (observed, well) -> well_observed,
# (observed, lease) -> lease_reported, (allocated, well) -> lease_allocated. Migration 012
# holds the same three, and a canonical row the store admits must serialize (M-5).
GRANULARITIES: tuple[str, ...] = ("well_observed", "lease_reported", "lease_allocated")

# A figure carries no stream, so its unit is what says the liquids policy must be stated.
LIQUID_UNITS: frozenset[str] = frozenset({"bbl", "bbl/d", "bbl/mo", "stb"})

ENVELOPE_META_KEYS: tuple[str, ...] = (
    "request_id",
    "as_of",
    "source_freshness",
    "labels",
    "next_cursor",
    "warnings",
    "deprecations",
)

LINEAGE_SIDECAR = "_lineage"
UNITS_SIDECAR = "_units"
BASIS_SIDECAR = "_basis"


class Figure(Frozen):
    """One addressable scalar: SB-07 §9.1(a)."""

    value: Any
    unit: str
    derivation: str
    selector: str | None = None
    granularity: str | None = None
    basis: str | None = None
    report_vintage: date | None = None
    allocation_model_id: str | None = None

    @property
    def handle(self) -> str:
        return format_handle(self.derivation, self.selector)

    def to_wire(self) -> dict[str, Any]:
        wire: dict[str, Any] = {"value": self.value, "unit": self.unit}
        if self.basis is not None:
            wire["basis"] = self.basis
        if self.granularity is not None:
            wire["granularity"] = self.granularity
        if self.report_vintage is not None:
            wire["report_vintage"] = self.report_vintage
        if self.allocation_model_id is not None:
            wire["allocation_model_id"] = self.allocation_model_id
        wire["d"] = self.handle
        return wire


class Series(Frozen):
    """A dense series under one handle, carried by sidecar: SB-07 §9.1(b).

    `point_handles` is the §9.1(b) exception the ND MPR forces: one workbook per month means
    one promote derivation per point, and a single column handle would resolve to a file that
    does not contain most of the column. Set it only when the points genuinely disagree.
    """

    values: Sequence[Any]
    unit: str
    derivation: str
    selector: str | None = None
    granularity: str | None = None
    basis: str | None = None
    point_handles: Sequence[str | None] | None = None

    @property
    def handle(self) -> str:
        return format_handle(self.derivation, self.selector)

    @property
    def handles(self) -> list[str]:
        if self.point_handles is None:
            return [self.handle]
        return [handle for handle in self.point_handles if handle]


class AsOf(Frozen):
    requested: str = "latest"
    resolved: date | None = None


class EnvelopeMeta(Frozen):
    request_id: str
    as_of: AsOf
    source_freshness: Mapping[str, Any] = Field(default_factory=dict)
    labels: Mapping[str, str] = Field(default_factory=dict)
    next_cursor: str | None = None
    warnings: Sequence[Mapping[str, Any]] = ()
    deprecations: Sequence[Mapping[str, Any]] = ()


class Envelope(Frozen):
    data: Any
    meta: EnvelopeMeta
    links: Mapping[str, str | None]
    handles: Sequence[str] = ()

    def to_dict(self) -> dict[str, Any]:
        return json_ready(
            {"data": self.data, "meta": self.meta.model_dump(), "links": dict(self.links)}
        )


def _validate(
    unit: str, granularity: str | None, basis: str | None, allocation_model_id: str | None
) -> None:
    if not unit:
        raise ValueError("unit is mandatory on every figure (SB-07 §9.1, A-13)")
    if granularity is not None and granularity not in GRANULARITIES:
        raise ValueError(f"granularity must be one of {GRANULARITIES}, not {granularity!r} (DIR-3)")
    if granularity is not None and unit in LIQUID_UNITS and basis is None:
        raise ValueError(f"basis is mandatory on a liquids figure in {unit} (bp:258)")
    if granularity == "lease_allocated" and allocation_model_id is None:
        raise ValueError("allocation_model_id is mandatory on a lease_allocated figure (DIR-3)")


def figure(
    value: Any,
    *,
    unit: str,
    derivation: str,
    selector: str | None = None,
    granularity: str | None = None,
    basis: str | None = None,
    report_vintage: date | None = None,
    allocation_model_id: str | None = None,
) -> Figure:
    """The only way to put a scalar in an API response."""
    if report_vintage is not None and granularity is None:
        raise ValueError("granularity is mandatory on a production-derived figure (DIR-3)")
    _validate(unit, granularity, basis, allocation_model_id)
    if selector is not None:
        parse_selector(selector)
    return Figure(
        value=value,
        unit=unit,
        derivation=derivation,
        selector=selector,
        granularity=granularity,
        basis=basis,
        report_vintage=report_vintage,
        allocation_model_id=allocation_model_id,
    )


def series(
    values: Sequence[Any],
    *,
    unit: str,
    derivation: str,
    selector: str | None = None,
    granularity: str | None = None,
    basis: str | None = None,
    point_handles: Sequence[str | None] | None = None,
) -> Series:
    """A dense series: one handle for the column, per-point vintages ride alongside it."""
    _validate(unit, granularity, basis, None)
    if selector is not None:
        parse_selector(selector)
    if point_handles is not None:
        if len(point_handles) != len(values):
            raise ValueError("point_handles must align one-to-one with the series values")
        for handle in point_handles:
            if handle is not None:
                parse_handle(handle)
    return Series(
        values=list(values),
        unit=unit,
        derivation=derivation,
        selector=selector,
        granularity=granularity,
        basis=basis,
        point_handles=None if point_handles is None else list(point_handles),
    )


class _Sidecars:
    def __init__(self) -> None:
        self.lineage: dict[str, str] = {}
        self.units: dict[str, str] = {}
        self.basis: dict[str, str] = {}

    def record(self, path: str, node: Series) -> None:
        if node.point_handles is None:
            self.lineage[path] = node.handle
        else:
            for index, handle in enumerate(node.point_handles):
                if handle is not None:
                    self.lineage[f"{path}.{index}"] = handle
        self.units[path] = node.unit
        if node.basis is not None:
            self.basis[path] = node.basis

    def apply(self, body: dict[str, Any]) -> dict[str, Any]:
        if self.lineage:
            body[LINEAGE_SIDECAR] = self.lineage
            body[UNITS_SIDECAR] = self.units
        if self.basis:
            body[BASIS_SIDECAR] = self.basis
        return body


def _walk(node: Any, path: str, sidecars: _Sidecars | None, handles: list[str]) -> Any:
    """`sidecars` collects for the enclosing object; `path` is dotted, relative to it."""
    if isinstance(node, Figure):
        handles.append(node.handle)
        return node.to_wire()
    if isinstance(node, Series):
        handles.extend(node.handles)
        if sidecars is not None:
            sidecars.record(path, node)
        return list(node.values)
    if isinstance(node, Mapping):
        # Sidecars hang off the outermost object of a branch; a list has no key to hold them.
        host = sidecars or _Sidecars()
        body = {
            str(key): _walk(value, _join(path, str(key), sidecars), host, handles)
            for key, value in node.items()
        }
        return body if sidecars is not None else host.apply(body)
    if isinstance(node, (list, tuple)):
        return [
            _walk(value, _join(path, str(index), sidecars), sidecars, handles)
            for index, value in enumerate(node)
        ]
    return node


def _join(path: str, token: str, sidecars: _Sidecars | None) -> str:
    return f"{path}.{token}" if sidecars is not None and path else token


def attach_lineage(
    data: Any,
    *,
    as_of: date | None,
    request_id: str,
    links: Mapping[str, str] | None = None,
    warnings: Sequence[Mapping[str, Any] | str] = (),
    labels: Mapping[str, str] | None = None,
    source_freshness: Mapping[str, Any] | None = None,
    next_cursor: str | None = None,
    as_of_requested: str = "latest",
    deprecations: Sequence[Mapping[str, Any]] = (),
) -> Envelope:
    """Serialize every figure and series in `data` and wrap it in the SB-04 §2.2 envelope."""
    handles: list[str] = []
    body = _walk(data, "", None, handles)
    resolved_links = {"self": None, "next": None, "explain": None, **dict(links or {})}
    if resolved_links["explain"] is None and handles:
        resolved_links["explain"] = _explain_link(handles)
    return Envelope(
        data=body,
        meta=EnvelopeMeta(
            request_id=request_id,
            as_of=AsOf(requested=as_of_requested, resolved=as_of),
            source_freshness=dict(source_freshness or {}),
            labels=dict(labels or {}),
            next_cursor=next_cursor,
            warnings=[_warning(item) for item in warnings],
            deprecations=list(deprecations),
        ),
        links=resolved_links,
        handles=handles,
    )


def _warning(item: Mapping[str, Any] | str) -> Mapping[str, Any]:
    return {"code": "warning", "detail": item} if isinstance(item, str) else dict(item)


def _explain_link(handles: Sequence[str]) -> str:
    """SB-04 §2.2: the S9 one-call path, pre-built so no client assembles it.

    Cell handles carry `#`, so the value is percent-encoded: unencoded, a client following
    the link verbatim sends the selector and `depth` as a fragment the server never receives.
    """
    unique = list(dict.fromkeys(handles))[:MAX_HANDLES]
    query = "&".join(f"h={quote(handle, safe='')}" for handle in unique)
    return f"/v1/explain?{query}&depth=full"
