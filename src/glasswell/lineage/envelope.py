"""The response envelope: SB-04 §2.2 outside, SB-07 §9.1 lineage carriage inside `data`.

SB-04 errata E-01 settles the two-mechanism conflict: figure objects and the
`_lineage`/`_units`/`_basis` sidecars are the only representation of a handle. There is no
`meta.derivations` and no `meta.units` — a second map of the same fact can disagree with the
first, and SB-07 §10's naked-number harness walks the in-band form.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import parse_qsl, quote, urlsplit

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
EXPLAIN_BLOCK = "_explain"


@dataclass(frozen=True, slots=True)
class InlinedExplain:
    """What a resolver hands back for SB-07 §9.2: the chains, and what would not resolve."""

    chains: Mapping[str, Any] = field(default_factory=dict)
    unresolved: Mapping[str, str] = field(default_factory=dict)


ExplainInliner = Callable[[Sequence[str]], InlinedExplain]


def collect_handles(data: Any) -> list[str]:
    """Every handle `attach_lineage` would find in `data`, in walk order, duplicates kept.

    The one walker: a router that counts handles with its own walk can disagree with the
    selection that builds `links.explain` about truncation (gate-apiconv §9.2).
    """
    handles: list[str] = []
    _walk(data, "", None, handles)
    return handles


def distinct_handles(handles: Sequence[str]) -> list[str]:
    """The response's handle set, deduplicated in first-appearance order.

    The one definition of "how many handles does this response carry" — a caller that counts
    them any other way can disagree with the selection about whether anything was left out.
    """
    return list(dict.fromkeys(handles))


def inline_handles(handles: Sequence[str]) -> list[str]:
    """The handles one `/v1/explain` call carries, in first-appearance order (SB-07 §9.4).

    `links.explain` and `_explain` both draw from here so the response cannot advertise one
    set of resolvable handles in the link and a different set in the block.
    """
    return distinct_handles(handles)[:MAX_HANDLES]


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
    # The canonical status class domain, served once by the registry collection rather than
    # repeated inside every jurisdiction row. It is not a jurisdiction, so it cannot be an
    # element of `data`; every other operation omits the key entirely.
    status_classes: Sequence[Mapping[str, Any]] | None = None


class Envelope(Frozen):
    data: Any
    meta: EnvelopeMeta
    links: Mapping[str, str | None]
    handles: Sequence[str] = ()
    explain: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        meta = self.meta.model_dump()
        # Omitted rather than served as null on every other operation: a key that is always
        # there and always empty is one the contract snapshot carries for ever.
        if meta.get("status_classes") is None:
            meta.pop("status_classes", None)
        body = json_ready({"data": self.data, "meta": meta, "links": dict(self.links)})
        if self.explain is not None:
            body[EXPLAIN_BLOCK] = json_ready(dict(self.explain))
        return body


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
        body: dict[str, Any] = {}
        for key, value in node.items():
            name = str(key)
            if name == LINEAGE_SIDECAR and isinstance(value, Mapping):
                # A sidecar the router wrote itself: its handles are the response's too.
                handles.extend(str(handle) for handle in value.values())
                body[name] = dict(value)
                continue
            body[name] = _walk(value, _join(path, name, sidecars), host, handles)
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
    explain: ExplainInliner | None = None,
    extra_handles: Sequence[str] = (),
    status_classes: Sequence[Mapping[str, Any]] | None = None,
) -> Envelope:
    """Serialize every figure and series in `data` and wrap it in the SB-04 §2.2 envelope.

    `explain` is SB-07 §9.2: given a resolver, the envelope gains `_explain` beside `data` and
    nothing inside `data` moves. Absent, the response is the byte it was before the flag existed.
    `extra_handles` is for a response whose subject is itself a derivation: the record spells no
    figure, so the walk finds nothing, but the handle is still the response's to advertise.
    """
    supplied = dict(links or {})
    if _names_handles(supplied.get("explain")):
        # One carrier: a router-authored link and inline_handles() were shown to disagree
        # (gate-apix ADV-1). Pass extra_handles and let the envelope build the link.
        raise ValueError(
            "links.explain is envelope-authored, from the same selection _explain inlines;"
            " pass the handles via data or extra_handles, never a hand-built link"
        )
    handles: list[str] = []
    body = _walk(data, "", None, handles)
    handles.extend(extra_handles)
    resolved_links = {"self": None, "next": None, "explain": None, **supplied}
    if handles:
        # A handle-less template (`/v1/explain?h=`, the service index's) may pass through,
        # but where the response carries handles the envelope's own link is the only carrier.
        resolved_links["explain"] = _explain_link(handles)
    collected = [_warning(item) for item in warnings]
    inlined = None
    if explain is not None:
        selected = inline_handles(handles)
        resolved = explain(selected)
        inlined = dict(resolved.chains)
        collected.extend(_explain_warnings(handles, selected, resolved))
    return Envelope(
        data=body,
        meta=EnvelopeMeta(
            request_id=request_id,
            as_of=AsOf(requested=as_of_requested, resolved=as_of),
            source_freshness=dict(source_freshness or {}),
            labels=dict(labels or {}),
            next_cursor=next_cursor,
            warnings=collected,
            deprecations=list(deprecations),
            status_classes=status_classes,
        ),
        links=resolved_links,
        handles=handles,
        explain=inlined,
    )


def _explain_warnings(
    handles: Sequence[str], selected: Sequence[str], resolved: InlinedExplain
) -> list[Mapping[str, Any]]:
    """What `_explain` did not carry, with the count rather than an ellipsis."""
    unique = distinct_handles(handles)
    found: list[Mapping[str, Any]] = []
    if len(unique) > len(selected):
        found.append(
            {
                "code": "explain_inline_truncated",
                "detail": (
                    f"This response carries {len(unique)} handles and _explain inlines the"
                    f" first {MAX_HANDLES}, so {len(unique) - MAX_HANDLES} are absent from it."
                    " Every figure still resolves on its own: read the figure's `d` and call"
                    " /v1/explain?h=<d>&depth=full. The cap is /v1/explain's own"
                    " (SB-07 §9.4), not this operation's."
                ),
                "pointer": f"/{EXPLAIN_BLOCK}",
            }
        )
    invalid = {
        handle: reason
        for handle, reason in resolved.unresolved.items()
        if reason == "invalid_selector"
    }
    if invalid:
        named = "; ".join(sorted(invalid))
        found.append(
            {
                "code": "explain_invalid_selector",
                "detail": (
                    f"{len(invalid)} of {len(selected)} handles failed selector-output"
                    f" validation and are absent from _explain: {named}. The response values"
                    " are unchanged; call /v1/explain with the handle for the strict refusal."
                ),
                "pointer": f"/{EXPLAIN_BLOCK}",
            }
        )
    unresolved = {
        handle: reason
        for handle, reason in resolved.unresolved.items()
        if reason != "invalid_selector"
    }
    if unresolved:
        named = "; ".join(
            f"{handle} ({reason})" for handle, reason in sorted(unresolved.items())
        )
        found.append(
            {
                "code": "explain_unresolved",
                "detail": (
                    f"{len(unresolved)} of {len(selected)} handles did not resolve and"
                    f" are absent from _explain: {named}. The response's values are unaffected;"
                    " a handle that will not resolve is a lineage defect, not a serving one."
                ),
                "pointer": f"/{EXPLAIN_BLOCK}",
            }
        )
    return found


def _warning(item: Mapping[str, Any] | str) -> Mapping[str, Any]:
    return {"code": "warning", "detail": item} if isinstance(item, str) else dict(item)


def _names_handles(link: str | None) -> bool:
    """Whether a supplied explain link claims a handle set — the thing only the envelope may
    author. Query and fragment both count (`#h=` smuggling); a bare template claims nothing."""
    if link is None:
        return False
    parts = urlsplit(link)
    pairs = parse_qsl(parts.query, keep_blank_values=True) + parse_qsl(
        parts.fragment, keep_blank_values=True
    )
    return any(value for key, value in pairs if key == "h")


def _explain_link(handles: Sequence[str]) -> str:
    """SB-04 §2.2: the S9 one-call path, pre-built so no client assembles it.

    Cell handles carry `#`, so the value is percent-encoded: unencoded, a client following
    the link verbatim sends the selector and `depth` as a fragment the server never receives.
    """
    query = "&".join(f"h={quote(handle, safe='')}" for handle in inline_handles(handles))
    return f"/v1/explain?{query}&depth=full"
