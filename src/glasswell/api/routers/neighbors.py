"""Indexed current-snapshot physical neighbours for one North Dakota well."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import Connection, Cursor, ExplainEffect, rows
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import (
    EXAMPLE_API10,
    GLOSSARY_KEY,
    dataset,
    not_a_figure,
    request_example,
    semantics,
)
from glasswell.api.pagination import (
    DEFAULT_LIMIT,
    SPINE_LIMIT_CAP,
    decode_cursor,
    encode_cursor,
    next_link,
    page,
    query_fingerprint,
)
from glasswell.api.responses import EnvelopeModel, FigureModel, enveloped, inline_for, iso
from glasswell.api.routers.wells import API10_PATTERN
from glasswell.lineage.envelope import figure
from glasswell.lineage.ids import format_handle, format_selector
from glasswell.marts.neighbors import MAX_RADIUS_FT
from glasswell.units import METRES_PER_FOOT

router = APIRouter(tags=["wells"])

DEFAULT_RADIUS_FT = 5280
LIMIT_CAP = SPINE_LIMIT_CAP
DISTANCE_SCALE_FT = Decimal("0.01")

_SUBJECT = """
select api10, completion_date, formation_id, formation_group, formation_status,
       formation_pools, formation_month, lateral_component_count, snapshot_vintage,
       derivation_id
  from marts.nd_neighbor_subjects
 where api10 = %(api10)s
"""

_COVERAGE = """
select count(*)::integer as spatial_candidates,
       count(*) filter (where neighbor.completion_date is null)::integer
           as missing_completion_anchor,
       count(*) filter (where neighbor.completion_date >= %(at_date)s)::integer
           as on_or_after_cut,
       count(*) filter (where neighbor.formation_status = 'conflict')::integer
           as formation_conflicts,
       count(*) filter (where neighbor.formation_status in
           ('pool_unavailable', 'alias_unavailable', 'below_confidence'))::integer
           as formation_unavailable,
       count(*) filter (
           where neighbor.completion_date < %(at_date)s
             and (%(formation_id)s::text is null
                  or (neighbor.formation_status = 'mapped'
                      and neighbor.formation_id = %(formation_id)s)))::integer as eligible
  from marts.nd_neighbor_edges edge
  join marts.nd_neighbor_subjects neighbor on neighbor.api10 = edge.neighbor_api10
 where edge.api10 = %(api10)s
   and edge.distance_m <= %(radius_m)s
   and edge.snapshot_vintage = %(snapshot_vintage)s
   and edge.derivation_id = %(derivation_id)s
   and neighbor.snapshot_vintage = %(snapshot_vintage)s
   and neighbor.derivation_id = %(derivation_id)s
"""

_NEIGHBORS = """
select edge.neighbor_api10 as api10, edge.distance_m, edge.distance_epsg,
       edge.subject_geom_key, edge.neighbor_geom_key, edge.snapshot_vintage,
       edge.derivation_id, neighbor.completion_date, neighbor.formation_id,
       neighbor.formation_group, neighbor.formation_status, neighbor.formation_pools,
       neighbor.formation_month
  from marts.nd_neighbor_edges edge
  join marts.nd_neighbor_subjects neighbor on neighbor.api10 = edge.neighbor_api10
 where edge.api10 = %(api10)s
   and edge.distance_m <= %(radius_m)s
   and edge.snapshot_vintage = %(snapshot_vintage)s
   and edge.derivation_id = %(derivation_id)s
   and neighbor.snapshot_vintage = %(snapshot_vintage)s
   and neighbor.derivation_id = %(derivation_id)s
   and neighbor.completion_date < %(at_date)s
   and (%(formation_id)s::text is null
        or (neighbor.formation_status = 'mapped'
            and neighbor.formation_id = %(formation_id)s))
"""


class WinningGeometry(BaseModel):
    subject_geom_key: str = Field(description="Subject component on the minimum-distance pair.")
    neighbor_geom_key: str = Field(description="Neighbour component on that same pair.")


class NeighborWell(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    neighbor_api10: str = Field(
        description="Ten-digit API number of the physical neighbour.",
        json_schema_extra={
            GLOSSARY_KEY: "gt_api_10_api_12_api_14",
            **not_a_figure(
                "API-10 identifier on a physical-neighbour row, not a measurement."
            ),
        },
    )
    distance_ft: FigureModel = Field(
        description="Minimum lateral-component distance, measured in the stated projected CRS."
    )
    distance_crs: str = Field(
        description="Pair-local projected CRS used for this edge: EPSG:32613 or EPSG:32614."
    )
    completion_date: date = Field(
        description=(
            "Earliest current FracFocus hydraulic-fracturing job-end anchor. Never spud or"
            " first production."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_completion_event"},
    )
    formation_id: str | None = Field(
        max_length=64,
        description="Canonical formation when the earliest observed pool maps without conflict.",
        json_schema_extra={GLOSSARY_KEY: "gt_formation"},
    )
    formation_group: str | None = Field(
        description="Peer group from the same reviewed source-scoped alias row.",
        json_schema_extra={GLOSSARY_KEY: "gt_formation"},
    )
    formation_status: Literal[
        "mapped", "pool_unavailable", "alias_unavailable", "below_confidence", "conflict"
    ] = Field(description="Explicit mapping outcome; unavailable geology is never inferred.")
    formation_pools: list[str] = Field(
        description="Every nonblank ND MPR pool present in the earliest observed source month."
    )
    formation_month: date | None = Field(
        description="Earliest source month that reported a nonblank ND MPR pool."
    )
    winning_geometry: WinningGeometry
    lineage: dict[str, str] = Field(
        alias="_lineage",
        description="Field path to an exact persisted subject or edge selector.",
    )


class NeighborCoverage(BaseModel):
    spatial_candidates: FigureModel = Field(
        description="Persisted neighbours inside the requested radius before eligibility cuts."
    )
    missing_completion_anchor: FigureModel = Field(
        description="Spatial candidates excluded because no source completion anchor exists."
    )
    on_or_after_cut: FigureModel = Field(
        description="Candidates excluded because completion was equal to or after at_date."
    )
    formation_conflicts: FigureModel = Field(
        description="Candidates whose earliest pool set maps to conflicting formations."
    )
    formation_unavailable: FigureModel = Field(
        description="Candidates with missing pools, aliases, or sub-threshold aliases."
    )
    eligible: FigureModel = Field(
        description="Candidates left after date and optional exact-formation filtering."
    )
    returned: FigureModel = Field(description="Eligible neighbours returned on this page.")


class WellNeighbors(BaseModel):
    api10: str = Field(
        description="Ten-digit API number of the subject well.",
        json_schema_extra={
            GLOSSARY_KEY: "gt_api_10_api_12_api_14",
            **not_a_figure(
                "Identifier. A 10-digit API number is an identity string, not a measurement."
            ),
        },
    )
    at_date: date = Field(description="Strict event-time cut used for neighbour eligibility.")
    at_date_source: Literal["subject_completion_anchor", "caller_supplied"] = Field(
        description="Whether the cut came from FracFocus or the caller."
    )
    geometry_scope: Literal["current_only"] = Field(
        description=(
            "Canonical geometry is not effective-dated; historical geometry is not fabricated."
        )
    )
    snapshot_vintage: date = Field(description="Current mart snapshot this response is pinned to.")
    distance_method: str = Field(
        description=(
            "Minimum over every promoted lateral-component pair; EPSG:5070 finds candidates and"
            " pair-local UTM measures the persisted distance."
        )
    )
    relation: Literal["physical_neighbours_not_model_analogs"] = Field(
        description="These are spatial neighbours, not similarity-ranked model analogs."
    )
    coverage: NeighborCoverage
    neighbors: list[NeighborWell] = Field(description="Eligible neighbours in distance order.")


@router.get(
    "/wells/{api10}/neighbors",
    operation_id="get_well_neighbors",
    summary="Physical neighbours of one North Dakota well",
    description=(
        "Current-snapshot physical neighbours, not model analogs. The mart measures the minimum"
        " projected distance over every promoted lateral component pair, retaining the exact"
        " winning geometry keys. Surface points, vertical traces and sidetracks never enter."
        " Eligibility is strictly completion_date < at_date; equality is co-development and is"
        " excluded. Completion is the earliest current FracFocus job-end anchor, never spud or"
        " first production. Missing completion and formation context remains counted and"
        " explicit. API reads are indexed scalar joins over the persisted mart with no spatial"
        " work. Because canonical geometry is current-only, as_of may only pin the current mart"
        " snapshot."
    ),
    response_model=EnvelopeModel[WellNeighbors],
    openapi_extra={
        **request_example(path={"api10": EXAMPLE_API10}),
        **dataset(
            id="neighbors",
            title="Physical neighbours (per well)",
            group="wells",
            collection_pointer="/neighbors",
            anchors=["/api10", "/at_date", "/snapshot_vintage"],
            row_id=["/neighbor_api10"],
            facets=["radius_ft", "formation_id", "at_date", "as_of"],
            columns={
                "default": [
                    "/neighbor_api10",
                    "/distance_ft",
                    "/completion_date",
                    "/formation_id",
                    "/formation_group",
                    "/formation_status",
                ],
                "sort": "/distance_ft",
            },
            intro="nb_dataset_neighbors",
            order=14,
        ),
        **semantics(
            radius_ft={
                "so": (
                    "Filters the persisted 26,400-foot edge mart. Values above the mart radius"
                    " are refused rather than presented as a complete search."
                )
            },
            formation_id={
                "glossary": "gt_formation",
                "so": (
                    "Matches an exact canonical formation only after every earliest-month pool"
                    " maps at confidence 0.800 or higher without conflict."
                ),
            },
            at_date={
                "glossary": "gt_completion_event",
                "so": (
                    "Uses event time only and keeps strictly earlier completions. It never"
                    " changes the current knowledge snapshot or falls back to spud."
                ),
            },
            as_of={
                "glossary": "gt_knowledge_time",
                "so": (
                    "Pins the one current mart snapshot. Any other date is refused because"
                    " canonical well geometry has no effective-dated history."
                ),
            },
            cursor={"so": "Pins the snapshot and continues the distance/API-10 total order."},
            limit={"so": f"Returns {LIMIT_CAP} neighbours at most; larger pages are refused."},
            explain={
                "glossary": "gt_derivation_handle",
                "so": "Inlines exact persisted subject and edge selectors where requested.",
            },
            explain_depth={
                "glossary": "gt_derivation_handle",
                "so": "Three levels reaches the canonical promotions and source manifests.",
            },
        ),
    },
    responses=problem_responses(
        "not_found",
        "validation_failed",
        "cursor_malformed",
        "cursor_query_mismatch",
        "service_degraded",
    ),
)
def get_well_neighbors(
    request: Request,
    connection: Connection,
    api10: Annotated[str, Path(description="Ten-digit API well number.", pattern=API10_PATTERN)],
    explain: ExplainEffect,
    radius_ft: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_RADIUS_FT,
            description="Search radius in feet, from 1 through the 26,400-foot mart cap.",
        ),
    ] = DEFAULT_RADIUS_FT,
    formation_id: Annotated[
        str | None,
        Query(
            pattern=r"^[a-z0-9_]+$",
            max_length=64,
            description="Exact canonical formation; unavailable/conflicting rows never match.",
        ),
    ] = None,
    at_date: Annotated[
        date | None,
        Query(description="Event-time cut; only neighbours completed strictly before it qualify."),
    ] = None,
    as_of: Annotated[
        date | None,
        Query(
            description=(
                "Exact current mart snapshot. Any other date is refused because canonical"
                " geometry is not effective-dated."
            )
        ),
    ] = None,
    cursor: Cursor = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=LIMIT_CAP,
            description=f"Page size, {DEFAULT_LIMIT} by default, {LIMIT_CAP} at most.",
        ),
    ] = DEFAULT_LIMIT,
) -> JSONResponse:
    subject_rows = rows(connection, _SUBJECT, {"api10": api10})
    if not subject_rows:
        raise ProblemError(
            "not_found", detail=f"no current ND lateral-neighbour subject for {api10}"
        )
    subject = subject_rows[0]
    snapshot_vintage = subject["snapshot_vintage"]
    if as_of is not None and as_of != snapshot_vintage:
        raise _current_only_error(as_of, snapshot_vintage)

    resolved_at_date = at_date or subject["completion_date"]
    if resolved_at_date is None:
        raise ProblemError(
            "validation_failed",
            detail="this subject has no source completion anchor; supply at_date explicitly",
            errors=[
                {
                    "pointer": "/query/at_date",
                    "code": "completion_anchor_required",
                    "detail": "no earliest current FracFocus job-end anchor is available",
                }
            ],
        )
    at_date_source = "caller_supplied" if at_date is not None else "subject_completion_anchor"
    link_filters = {
        "radius_ft": radius_ft,
        "formation_id": formation_id,
        "at_date": at_date,
        "as_of": as_of,
    }
    fingerprint = query_fingerprint(
        {
            "api10": api10,
            "radius_ft": radius_ft,
            "formation_id": formation_id,
            "at_date": resolved_at_date,
            "as_of": snapshot_vintage,
            "derivation_id": subject["derivation_id"],
        }
    )
    after_distance: Decimal | None = None
    after_api10: str | None = None
    if cursor is not None:
        decoded = decode_cursor(cursor, fingerprint=fingerprint)
        if decoded.as_of != snapshot_vintage.isoformat():
            raise _current_only_error(
                date.fromisoformat(decoded.as_of) if decoded.as_of else None,
                snapshot_vintage,
            )
        try:
            after_distance = Decimal(decoded.key)
        except InvalidOperation:
            raise ProblemError(
                "cursor_malformed", detail="cursor distance is not numeric"
            ) from None
        after_api10 = decoded.tiebreak

    parameters: dict[str, object] = {
        "api10": api10,
        "radius_m": Decimal(radius_ft) * METRES_PER_FOOT,
        "formation_id": formation_id,
        "at_date": resolved_at_date,
        "snapshot_vintage": snapshot_vintage,
        "derivation_id": subject["derivation_id"],
        "limit": limit + 1,
    }
    statement = _NEIGHBORS
    if after_distance is not None:
        statement += (
            " and (edge.distance_m > %(after_distance)s"
            " or (edge.distance_m = %(after_distance)s"
            " and edge.neighbor_api10 > %(after_api10)s))"
        )
        parameters |= {"after_distance": after_distance, "after_api10": after_api10}
    statement += " order by edge.distance_m, edge.neighbor_api10 limit %(limit)s"

    found = rows(connection, statement, parameters)
    items, has_more = page(found, limit)
    coverage = rows(connection, _COVERAGE, parameters)[0]
    current_subject = rows(connection, _SUBJECT, {"api10": api10})
    if (
        not current_subject
        or current_subject[0]["snapshot_vintage"] != snapshot_vintage
        or current_subject[0]["derivation_id"] != subject["derivation_id"]
    ):
        raise ProblemError(
            "service_degraded",
            detail="the neighbour mart changed during this request; retry on the new snapshot",
        )
    next_cursor = (
        encode_cursor(
            key=items[-1]["distance_m"],
            tiebreak=items[-1]["api10"],
            as_of=snapshot_vintage,
            fingerprint=fingerprint,
        )
        if has_more and items
        else None
    )
    response_items = [_neighbor(api10, row) for row in items]
    derivation_id = subject["derivation_id"]
    coverage_selector = [
        ("api10", api10),
        ("radius_m", str(parameters["radius_m"])),
        ("at_date", resolved_at_date.isoformat()),
    ]
    if formation_id is not None:
        coverage_selector.append(("formation_id", formation_id))
    warnings = _warnings(coverage)
    return enveloped(
        request,
        {
            "api10": api10,
            "at_date": iso(resolved_at_date),
            "at_date_source": at_date_source,
            "geometry_scope": "current_only",
            "snapshot_vintage": iso(snapshot_vintage),
            "distance_method": (
                "EPSG:5070 indexed candidate discovery; minimum component-pair distance in"
                " pair-midpoint UTM 13N or 14N"
            ),
            "relation": "physical_neighbours_not_model_analogs",
            "coverage": {
                **{
                    key: _count_figure(
                        value,
                        derivation_id,
                        format_selector([*coverage_selector, ("metric", key)]),
                    )
                    for key, value in coverage.items()
                },
                "returned": _count_figure(
                    len(response_items),
                    derivation_id,
                    format_selector(
                        [
                            *coverage_selector,
                            ("metric", "returned"),
                            ("limit", str(limit)),
                            *(
                                [
                                    ("after_distance_m", str(after_distance)),
                                    ("after_api10", str(after_api10)),
                                ]
                                if after_distance is not None and after_api10 is not None
                                else []
                            ),
                        ]
                    ),
                ),
            },
            "neighbors": response_items,
        },
        as_of=snapshot_vintage,
        as_of_requested=iso(as_of) or "latest",
        labels={
            "/api10": "gt_api_10_api_12_api_14",
            "/at_date": "gt_completion_event",
            "/snapshot_vintage": "gt_knowledge_time",
            "/neighbors/*/neighbor_api10": "gt_api_10_api_12_api_14",
            "/neighbors/*/completion_date": "gt_completion_event",
            "/neighbors/*/formation_id": "gt_formation",
            "/neighbors/*/formation_group": "gt_formation",
        },
        next_cursor=next_cursor,
        links={
            "well": f"/v1/wells/{api10}",
            "next": next_link(
                f"/v1/wells/{api10}/neighbors",
                link_filters | {"limit": limit},
                next_cursor,
            )
            if next_cursor
            else None,
        },
        warnings=warnings,
        explain=inline_for(connection, explain),
    )


def _neighbor(subject_api10: str, row: dict[str, object]) -> dict[str, object]:
    edge_selector = f"api10={subject_api10}&neighbor_api10={row['api10']}"
    subject_selector = f"api10={row['api10']}"
    derivation_id = str(row["derivation_id"])
    distance_ft = (Decimal(row["distance_m"]) / METRES_PER_FOOT).quantize(
        DISTANCE_SCALE_FT, rounding=ROUND_HALF_UP
    )
    lineage = {
        "distance_crs": format_handle(
            derivation_id, f"{edge_selector}&col=distance_epsg"
        ),
        "completion_date": format_handle(
            derivation_id, f"{subject_selector}&col=completion_date"
        ),
        "formation_status": format_handle(
            derivation_id, f"{subject_selector}&col=formation_status"
        ),
        "formation_pools": format_handle(
            derivation_id, f"{subject_selector}&col=formation_pools"
        ),
        "winning_geometry.subject_geom_key": format_handle(
            derivation_id, f"{edge_selector}&col=subject_geom_key"
        ),
        "winning_geometry.neighbor_geom_key": format_handle(
            derivation_id, f"{edge_selector}&col=neighbor_geom_key"
        ),
    }
    if row["formation_id"] is not None:
        lineage["formation_id"] = format_handle(
            derivation_id, f"{subject_selector}&col=formation_id"
        )
    if row["formation_group"] is not None:
        lineage["formation_group"] = format_handle(
            derivation_id, f"{subject_selector}&col=formation_group"
        )
    if row["formation_month"] is not None:
        lineage["formation_month"] = format_handle(
            derivation_id, f"{subject_selector}&col=formation_month"
        )
    return {
        "neighbor_api10": row["api10"],
        "distance_ft": figure(
            str(distance_ft),
            unit="ft",
            derivation=derivation_id,
            selector=f"{edge_selector}&col=distance_m",
        ),
        "distance_crs": f"EPSG:{row['distance_epsg']}",
        "completion_date": iso(row["completion_date"]),
        "formation_id": row["formation_id"],
        "formation_group": row["formation_group"],
        "formation_status": row["formation_status"],
        "formation_pools": row["formation_pools"],
        "formation_month": iso(row["formation_month"]),
        "winning_geometry": {
            "subject_geom_key": row["subject_geom_key"],
            "neighbor_geom_key": row["neighbor_geom_key"],
        },
        "_lineage": lineage,
    }


def _count_figure(value: object, derivation_id: str, selector: str):
    return figure(str(value), unit="wells", derivation=derivation_id, selector=selector)


def _current_only_error(requested: date | None, current: date) -> ProblemError:
    rendered = requested.isoformat() if requested is not None else "none"
    return ProblemError(
        "validation_failed",
        detail=(
            f"neighbor geometry is current-only at {current.isoformat()}; requested {rendered}"
        ),
        errors=[
            {
                "pointer": "/query/as_of",
                "code": "current_only_geometry",
                "detail": current.isoformat(),
            }
        ],
    )


def _warnings(coverage: dict[str, int]) -> list[dict[str, str]]:
    warnings = []
    if coverage["missing_completion_anchor"]:
        warnings.append(
            {
                "code": "neighbor_completion_unavailable",
                "detail": (
                    f"{coverage['missing_completion_anchor']} spatial candidates have no current"
                    " FracFocus job-end anchor and were excluded without a proxy."
                ),
                "pointer": "/coverage/missing_completion_anchor",
            }
        )
    missing_formation = coverage["formation_conflicts"] + coverage["formation_unavailable"]
    if missing_formation:
        warnings.append(
            {
                "code": "neighbor_formation_incomplete",
                "detail": (
                    f"{missing_formation} spatial candidates have unavailable or conflicting"
                    " earliest-pool formation context; no formation was inferred."
                ),
                "pointer": "/coverage/formation_unavailable",
            }
        )
    return warnings
