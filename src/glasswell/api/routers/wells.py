"""The well spine: the collection the map lists and the header the card renders."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import AsOf, Connection, Cursor, WellsLimit, rows
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import (
    EXAMPLE_API10,
    EXAMPLE_BBOX,
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
from glasswell.api.responses import EnvelopeModel, FigureModel, enveloped, iso
from glasswell.lengths import STORAGE_EPSG, resolve_length_method
from glasswell.lineage.conformance import lease_reporting_rule
from glasswell.lineage.envelope import Figure, figure
from glasswell.lineage.explain import MAX_HANDLES
from glasswell.marts.tiles import TILE_BUFFER, TILE_EXTENT, TILE_MAX_ZOOM, WEB_MERCATOR
from glasswell.units import metres_to_feet

router = APIRouter(tags=["wells"])

BBOX_DEGREE_CAP = 4.0
API10_PATTERN = r"^\d{10}$"
BBOX_PARTS = 4
LON_LIMIT = 180.0
LAT_LIMIT = 90.0
COUNT_UNIT = "wells"

# R8: a count grouped by status_canonical is a count of one conformance rule's output, so the
# summary names the rule per jurisdiction rather than implying one vocabulary spans both. The
# registry has no state-code edge to walk — a vocab_map row is keyed by source — so the pairing
# is pinned here for the same reason as production.ROLLUP_RULE, and
# test_well_status_summary.py holds every id to a seeded registry row.
STATUS_VOCABULARY_RULES = {"33": "cr_nd_status_vocab_1", "42": "cr_tx_status_vocab_1"}

# SB-07 §2.1 fixes the selector charset. A status outside it would raise at serve time, which
# is a 500 on data the conformance rules are supposed to have already refused.
_NOT_SELECTOR_SAFE = re.compile(r"[^A-Za-z0-9_.:+-]")

WELL_LABELS = {
    "/api10": "gt_api_10_api_12_api_14",
    "/land_unit_label": "gt_land_unit",
    "/confidential_flag": "gt_confidential_well",
    "/lateral_length_ft": "gt_wellbore",
    "/total_depth_ft": "gt_wellbore",
}

STATUS_SUMMARY_LABELS = {
    "/statuses": "gt_well_status",
    "/unmapped_wells": "gt_well_status",
    "/vocabulary_rules": "gt_conformance_rule",
}

_COLUMNS = (
    "api10, api14, state_code, county_code_at_permit, ndic_file_no, operator_name_reported,"
    " operator_id, well_name, status_canonical, status_reported, well_type_reported, spud_date,"
    " confidential_flag, basin, land_unit_label, total_depth_ft, completion_date,"
    " effective_from, source_manifest_id, derivation_id"
)

RANKED_WELLS = f"""
with ranked as (
    select w.*, row_number() over (
               partition by w.api10 order by w.effective_from desc, w.created_at desc) as rn
      from canonical.wells w
     where (%(as_of)s::date is null or w.effective_from <= %(as_of)s::date))
select {_COLUMNS}
  from ranked
 where rn = 1
"""

# `tiled` asks the tile pipeline's own question of the deepest published zoom: a geometry that
# ST_AsMVTGeom drops there is on no tile at any zoom, while the card still serves its length.
_SPATIAL = f"""
select geom_type, geom_key, derivation_id, source_datum, source_manifest_id,
       {{length_metres}} as length_m,
       case when st_geometrytype(geom) = 'ST_Point' then st_x(geom) end as lon,
       case when st_geometrytype(geom) = 'ST_Point' then st_y(geom) end as lat,
       st_asmvtgeom(
           st_transform(geom, {WEB_MERCATOR}),
           st_tileenvelope(
               {TILE_MAX_ZOOM},
               floor((st_x(st_centroid(geom)) + 180) / 360 * (2 ^ {TILE_MAX_ZOOM}))::int,
               floor((1 - asinh(tan(radians(st_y(st_centroid(geom)))))
                        / pi()) / 2 * (2 ^ {TILE_MAX_ZOOM}))::int),
           {TILE_EXTENT}, {TILE_BUFFER}, true) is not null as tiled
  from canonical.well_spatial
 where api10 = %(api10)s
 order by geom_type, geom_key
"""

# The box narrows first and the spine is resolved over what it returned: `in_view` is an
# index-answerable predicate on well_spatial_geom_idx, and `distinct on` then picks one row per
# api10 in it. The left join is what keeps a promoted geometry whose api10 never reached the
# spine visible — it groups as `no_well_row` and is disclosed, never silently dropped and never
# folded into the no-status class, which is a different fact.
#
# `in_view` is referenced exactly once on purpose. A second reference makes PostgreSQL
# materialise the CTE, which erases its row estimate; measured at 2,000 seeded wells, the
# estimate fell to 1, the planner chose a nested loop with a join filter, and a 501-well box
# cost 125,250 filter comparisons and 28 ms — quadratic in the wells in view, on the small
# boxes the map spends its life in. Inlined, the same box is 3 ms. See work-output/wss-status.md.
STATUS_SUMMARY_SQL = """
with in_view as (
    select distinct api10
      from canonical.well_spatial
     where st_intersects(geom,
                         st_makeenvelope(%(minx)s, %(miny)s, %(maxx)s, %(maxy)s, 4326))),
     latest as (
    select distinct on (v.api10)
           v.api10, w.status_canonical, w.basin, w.state_code, w.derivation_id, w.effective_from
      from in_view v
      left join canonical.wells w
             on w.api10 = v.api10
            and (%(as_of)s::date is null or w.effective_from <= %(as_of)s::date)
     order by v.api10, w.effective_from desc nulls last, w.created_at desc nulls last)
select basin, state_code, status_canonical, derivation_id is null as no_well_row,
       count(*) as wells, max(derivation_id) as derivation_id,
       max(effective_from) as effective_from
  from latest
 group by 1, 2, 3, 4
"""

_STORAGE_CRS = """
select storage_epsg
  from lineage.crs_registry
 where basin = %(basin)s
 order by effective_from desc
 limit 1
"""

# A3-F3: a well whose only horizontal trace was held back reads as a well with no lateral at
# all unless the card says otherwise. Indexed on (source_id, row_payload->>'api10') in 016.
_HELD_BACK_GEOMETRY = """
select reason_code, rule_id, count(*) as rows,
       string_agg(distinct row_payload ->> 'segment', ', ' order by row_payload ->> 'segment')
           as segments
  from lineage.quarantine_rows
 where source_id = 'nd_gis_horizontals_line'
   and row_payload ->> 'api10' = %(api10)s
   and state = 'open'
 group by reason_code, rule_id
 order by reason_code
"""


class WellSummary(BaseModel):
    api10: str = Field(
        description="Ten-digit API well number.",
        json_schema_extra={
            GLOSSARY_KEY: "gt_api_10_api_12_api_14",
            **not_a_figure("Identifier, in a collection item."),
        },
    )
    well_name: str | None = Field(
        description="Well name as reported by the operator.",
        json_schema_extra={GLOSSARY_KEY: "gt_well_name"},
    )
    operator_name_reported: str | None = Field(
        description="Operator name exactly as reported.",
        json_schema_extra={GLOSSARY_KEY: "gt_operator_of_record"},
    )
    status_canonical: str | None = Field(
        description=(
            "Status mapped through the source's status vocabulary rule — cr_nd_status_vocab_1"
            " in North Dakota, cr_tx_status_vocab_1 in Texas. Null where the source reported"
            " no status at all, which is not the same as an unknown one."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_well_status"},
    )
    county_code_at_permit: str | None = Field(
        description="County code recorded at permit.",
        json_schema_extra={
            GLOSSARY_KEY: "gt_county_at_permit",
            **not_a_figure("County code, in a collection item."),
        },
    )
    land_unit_label: str | None = Field(description="PLSS land unit label.", json_schema_extra={
        GLOSSARY_KEY: "gt_land_unit"})
    spud_date: date | None = Field(
        description="Spud date as reported.",
        json_schema_extra={GLOSSARY_KEY: "gt_spud_date"},
    )
    confidential_flag: bool = Field(description="Whether the regulator withholds this well.",
                                    json_schema_extra={GLOSSARY_KEY: "gt_confidential_well"})
    effective_from: date = Field(description="Effective date of this well row (M13).",
                                 json_schema_extra={GLOSSARY_KEY: "gt_effective_date"})
    links: dict[str, str] = Field(description="Sub-resource paths for this well.")


class Geometry(BaseModel):
    geom_type: str = Field(description="surface, bottomhole or lateral.")
    geom_key: str = Field(description="Key of the geometry row within the well.")
    source_datum: str = Field(description="Datum the source published, before transform.",
                              json_schema_extra={GLOSSARY_KEY: "gt_datum"})


class SurfacePoint(BaseModel):
    lon: float = Field(
        description="Longitude in the storage CRS (EPSG:4326).",
        json_schema_extra=not_a_figure(
            "Geometry, not a figure. Storage CRS is EPSG:4326 and is stated alongside."
        ),
    )
    lat: float = Field(
        description="Latitude in the storage CRS (EPSG:4326).",
        json_schema_extra=not_a_figure(
            "Geometry, not a figure. Storage CRS is EPSG:4326 and is stated alongside."
        ),
    )


class WellDetail(WellSummary):
    # api10 and county_code_at_permit are redeclared, not inherited: the record and the
    # collection item are exempted by different allowlist entries, and an inherited Field
    # would publish the collection item's cross-reference on the record too.
    api10: str = Field(
        description="Ten-digit API well number.",
        json_schema_extra={
            GLOSSARY_KEY: "gt_api_10_api_12_api_14",
            **not_a_figure(
                "Identifier. A 10-digit API number is an identity string, not a measurement."
            ),
        },
    )
    county_code_at_permit: str | None = Field(
        description="County code recorded at permit.",
        json_schema_extra={
            GLOSSARY_KEY: "gt_county_at_permit",
            **not_a_figure("County code as reported at permit; an identifier, not a quantity."),
        },
    )
    api14: str | None = Field(
        description="Fourteen-digit API number where known.",
        json_schema_extra=not_a_figure("Identifier. The completion-level API number."),
    )
    state_code: str | None = Field(
        description="State code as reported.",
        json_schema_extra=not_a_figure(
            "FIPS-style state code carried as reported; an identifier, not a quantity."
        ),
    )
    ndic_file_no: str | None = Field(
        description="NDIC file number for the well.",
        json_schema_extra=not_a_figure(
            "The NDIC file number is the regulator's identifier for the well."
        ),
    )
    status_reported: str | None = Field(description="Status code exactly as the source wrote it.")
    well_type_reported: str | None = Field(description="Well type exactly as reported.")
    basin: str | None = Field(description="Basin the well is assigned to.")
    lateral_count: int = Field(
        description="Lateral geometries recorded for this well.",
        json_schema_extra=not_a_figure("A count of geometry rows, not a measured quantity."),
    )
    lateral_length_ft: FigureModel | None = Field(
        description="Total lateral length, projected into the basin compute CRS.",
        json_schema_extra={GLOSSARY_KEY: "gt_wellbore"},
    )
    compute_crs: str | None = Field(
        description=(
            "CRS the length computation is defined on. Zone-free while length_method is"
            " geodesic, which is why it reads as the storage CRS."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_crs_compute_crs"},
    )
    length_method: str = Field(
        description=(
            "How lateral length was measured, from the compute-CRS rule the well's basin names:"
            " geodesic on the WGS84 ellipsoid, or projected into a named CRS."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_crs_compute_crs"},
    )
    storage_crs: str = Field(description="CRS geometry is stored in; always EPSG:4326.")
    total_depth_ft: FigureModel | None = Field(
        description="Total wellbore depth as the regulator reported it, with its handle.",
        json_schema_extra={GLOSSARY_KEY: "gt_wellbore"},
    )
    completion_date: date | None = Field(
        description="Most recent completion date on file; not a spud and not first production."
    )
    geometry: list[Geometry] = Field(description="Geometry rows held for this well.")
    surface_point: SurfacePoint | None = Field(description="Surface hole location, if recorded.")


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "api10": row["api10"],
        "well_name": row["well_name"],
        "operator_name_reported": row["operator_name_reported"],
        "status_canonical": row["status_canonical"],
        "county_code_at_permit": row["county_code_at_permit"],
        "land_unit_label": row["land_unit_label"],
        "spud_date": iso(row["spud_date"]),
        "confidential_flag": row["confidential_flag"],
        "effective_from": iso(row["effective_from"]),
        "links": {
            "self": f"/v1/wells/{row['api10']}",
            "production": f"/v1/wells/{row['api10']}/production",
        },
    }


def pending_allocation(rule: dict[str, str]) -> dict[str, Any]:
    """DIR-3 made visible: a lease-reporting state has no observed well-level series, and an
    empty chart would say the opposite of what is true. The rule is named so a reader can
    resolve it at /v1/conformance."""
    return {
        "code": "production_pending_allocation",
        "detail": (
            f"This well's regulator reports production at the {rule['reporting_level']}"
            f" ({rule['rule_id']}), so no well-level series has been observed. A well-level"
            " figure would be an allocation artifact, and allocation is not served yet; the"
            " well-to-lease keys it will need are already recorded."
        ),
        "pointer": "/production",
    }


def _held_back_geometry(connection, api10: str) -> list[dict[str, Any]]:
    """Say what the horizontals layer held back for this well, and under which rule."""
    warnings = []
    for row in rows(connection, _HELD_BACK_GEOMETRY, {"api10": api10}):
        segments = f" ({row['segments']})" if row["segments"] else ""
        warnings.append(
            {
                "code": "geometry_not_promoted",
                "detail": (
                    f"{row['rows']} horizontal geometry rows for this well{segments} were not"
                    f" promoted: {row['reason_code']} under {row['rule_id']}."
                    " They are in /v1/quarantine with their payloads."
                ),
                "pointer": "/geometry",
            }
        )
    return warnings


def _bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if raw is None:
        return None
    parts = raw.split(",")
    if len(parts) != 4:
        raise ProblemError(
            "validation_failed",
            detail="bbox must be minx,miny,maxx,maxy in WGS84",
            errors=[{"pointer": "/query/bbox", "code": "bbox_shape", "detail": "four numbers"}],
        )
    try:
        minx, miny, maxx, maxy = (float(part) for part in parts)
    except ValueError:
        raise ProblemError(
            "validation_failed",
            detail="bbox coordinates must be numbers",
            errors=[{"pointer": "/query/bbox", "code": "bbox_number", "detail": raw}],
        ) from None
    if maxx - minx > BBOX_DEGREE_CAP or maxy - miny > BBOX_DEGREE_CAP:
        raise ProblemError(
            "validation_failed",
            detail=f"bbox is capped at {BBOX_DEGREE_CAP}x{BBOX_DEGREE_CAP} degrees",
            errors=[{"pointer": "/query/bbox", "code": "bbox_cap", "detail": raw}],
        )
    return minx, miny, maxx, maxy


@router.get(
    "/wells",
    operation_id="list_wells",
    summary="List wells",
    description=(
        "The well spine as of a knowledge-time cut, ordered by API-10. Rows are"
        " effective-dated: a status change appends a row rather than updating one, so a"
        " past `as_of` returns the well as it was described then. Filters compose; the"
        " bounding box is a WGS84 envelope capped at four degrees a side."
        " It does not return production — see /v1/wells/{api10}/production."
    ),
    response_model=EnvelopeModel[list[WellSummary]],
    openapi_extra={
        **request_example(query={"limit": 5}),
        **dataset(
            id="wells",
            title="Wells",
            group="wells",
            collection_pointer="",
            row_id=["/api10"],
            detail_operation="get_well",
            facets=["status", "operator", "county", "bbox", "q"],
            columns={
                "default": [
                    "/api10",
                    "/well_name",
                    "/operator_name_reported",
                    "/status_canonical",
                    "/county_code_at_permit",
                    "/spud_date",
                ],
                "sort": "/api10",
            },
            intro="nb_dataset_wells",
            order=10,
        ),
        **semantics(
            as_of={
                "glossary": "gt_knowledge_time",
                "so": (
                    "Reads the spine as it stood on that knowledge date. A well permitted"
                    " afterwards is absent, and one whose operator changed since answers with"
                    " the older name. It does not filter on when a well was drilled — it"
                    " chooses which version of every row you are looking at."
                ),
            },
            cursor={
                "so": (
                    "Pins the page to the api10 order and to the filters that opened it. Change"
                    " a filter and the cursor is refused rather than quietly re-scoped, so a"
                    " resumed page is the same population you started paging through."
                ),
            },
            limit={
                "so": (
                    "Caps this collection at 1000 a page — higher than the kitchen collections,"
                    " because a wells page is what the map draws. Ask for more and the request"
                    " is rejected rather than trimmed, so a page is never quietly short."
                ),
            },
            status={
                "glossary": "gt_well_status",
                "so": (
                    "Filters on the canonical value rather than the code the state published,"
                    " so `active` here means every source's version of active. A reported code"
                    " with no mapping is quarantined, so it matches no status at all."
                ),
            },
            operator={
                "glossary": "gt_operator_of_record",
                "so": (
                    "Substring-matches the reported spelling. A company that files under"
                    " several spellings needs several searches, and a parent's subsidiaries do"
                    " not roll up — that join is a conformance rule, not a search behaviour."
                ),
            },
            county={
                "glossary": "gt_county_at_permit",
                "so": (
                    "Matches the county on the permit, which is fixed inside the API number and"
                    " never restated. A lateral that produces in the next county still answers"
                    " to the county it was permitted in."
                ),
            },
            bbox={
                "glossary": "gt_crs_compute_crs",
                "so": (
                    "WGS84 degrees, rejected above four a side. It matches a well any of whose"
                    " recorded geometry — surface, bottomhole or lateral — overlaps the box, so"
                    " a lateral clipping one corner is a hit and a surface hole outside it is"
                    " not a miss."
                ),
            },
            q={
                "glossary": "gt_well_name",
                "so": (
                    "Substring-matches the name the operator filed. Names repeat across"
                    " operators and change with the lease, so this narrows a list to read; it"
                    " does not identify a well. Use api10 for that."
                ),
            },
        ),
    },
    responses=problem_responses(
        "validation_failed", "cursor_malformed", "cursor_query_mismatch", "service_degraded"
    ),
)
def list_wells(
    request: Request,
    connection: Connection,
    as_of: AsOf = None,
    cursor: Cursor = None,
    limit: WellsLimit = DEFAULT_LIMIT,
    status: Annotated[
        str | None, Query(description="Canonical status, e.g. active or plugged.")
    ] = None,
    operator: Annotated[
        str | None, Query(description="Case-insensitive substring of the reported operator.")
    ] = None,
    county: Annotated[
        str | None, Query(description="County code as recorded at permit.")
    ] = None,
    bbox: Annotated[
        str | None, Query(description="minx,miny,maxx,maxy in WGS84; capped at 4 degrees.")
    ] = None,
    q: Annotated[str | None, Query(description="Case-insensitive substring of well name.")] = None,
) -> JSONResponse:
    filters = {
        "as_of": as_of,
        "status": status,
        "operator": operator,
        "county": county,
        "bbox": bbox,
        "q": q,
    }
    fingerprint = query_fingerprint(filters)
    envelope = _bbox(bbox)
    params: dict[str, Any] = {"as_of": as_of, "limit": limit + 1}
    clauses = [RANKED_WELLS]
    if status is not None:
        clauses.append("and status_canonical = %(status)s")
        params["status"] = status
    if operator is not None:
        clauses.append("and operator_name_reported ilike '%%' || %(operator)s || '%%'")
        params["operator"] = operator
    if county is not None:
        clauses.append("and county_code_at_permit = %(county)s")
        params["county"] = county
    if q is not None:
        clauses.append("and well_name ilike '%%' || %(q)s || '%%'")
        params["q"] = q
    if envelope is not None:
        clauses.append(
            "and exists (select 1 from canonical.well_spatial s where s.api10 = ranked.api10"
            " and s.geom && st_makeenvelope(%(minx)s, %(miny)s, %(maxx)s, %(maxy)s, 4326))"
        )
        params |= dict(zip(("minx", "miny", "maxx", "maxy"), envelope, strict=True))
    if cursor is not None:
        params["after"] = decode_cursor(cursor, fingerprint=fingerprint).key
        clauses.append("and api10 > %(after)s")
    clauses.append("order by api10 limit %(limit)s")

    found = rows(connection, "\n".join(clauses), params)
    items, has_more = page(found, limit)
    next_cursor = (
        encode_cursor(
            key=items[-1]["api10"],
            tiebreak=items[-1]["api10"],
            as_of=as_of,
            fingerprint=fingerprint,
        )
        if has_more and items
        else None
    )
    return enveloped(
        request,
        [_summary(row) for row in items],
        as_of=as_of,
        as_of_requested=iso(as_of) or "latest",
        next_cursor=next_cursor,
        links={
            "next": next_link("/v1/wells", filters | {"limit": limit}, next_cursor)
            if next_cursor
            else None
        },
    )


class StatusCount(BaseModel):
    status: str = Field(
        description=(
            "Canonical status the wells in this bucket carry. Never null: a well the source"
            " reported no status for is counted in `unmapped_wells`, not here."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_well_status"},
    )
    wells: FigureModel = Field(
        description="Wells in this class inside the box, with the handle the count resolves by."
    )


class BasinStatusCounts(BaseModel):
    basin: str | None = Field(description="Basin the wells are assigned to; null where none is.")
    state_code: str | None = Field(
        description="API state code the wells were promoted under — 33 in ND, 42 in TX.",
        json_schema_extra=not_a_figure(
            "API state code on a per-basin summary row; an identifier, not a quantity."
        ),
    )
    status_vocabulary_rule: str | None = Field(
        description=(
            "Conformance rule that mapped this jurisdiction's reported codes onto the canonical"
            " vocabulary. Null where no rule is registered for the state, which is disclosed as"
            " a warning rather than answered with another state's rule."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )
    wells: FigureModel = Field(description="Wells in this basin inside the box.")
    unmapped_wells: FigureModel | None = Field(
        description="Wells here whose source reported no status; absent when there are none."
    )
    statuses: list[StatusCount] = Field(description="One entry per class present, largest first.")


class WellStatusSummary(BaseModel):
    bbox: str = Field(
        description="The box the counts were taken over, normalised to minx,miny,maxx,maxy."
    )
    wells: FigureModel | None = Field(
        description=(
            "Every well in the box, mapped and unmapped together. Null when the box holds none —"
            " a class no well is in has no count, and neither does an empty box."
        )
    )
    unmapped_wells: FigureModel | None = Field(
        description=(
            "Wells whose source reported no status at all. Its own bucket, never added to a"
            " class — an absence is not a value, and in the 2026-08-20 Texas load 65,685 wells"
            " are in it, which is more than any single class it could have been folded into."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_well_status"},
    )
    statuses: list[StatusCount] = Field(
        description="One entry per canonical class present in the box, largest first."
    )
    basins: list[BasinStatusCounts] = Field(
        description="The same counts split by basin and jurisdiction, ordered by basin."
    )
    vocabulary_rules: list[str] = Field(
        description="Every status vocabulary rule that shaped these counts; each one is linked.",
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )


def _token(value: str | None) -> str:
    return _NOT_SELECTOR_SAFE.sub("_", value) if value else "unassigned"


def _refuse_bbox(code: str, detail: str, raw: str) -> ProblemError:
    return ProblemError(
        "validation_failed",
        detail=detail,
        errors=[{"pointer": "/query/bbox", "code": code, "detail": raw}],
    )


def _status_bbox(raw: str) -> tuple[float, float, float, float]:
    """The summary's own box: no degree cap, and every way it can be wrong is named.

    `/v1/wells` caps its box at four degrees because it pages rows; this one returns at most a
    row per class per basin however wide the box is, and a cap here would recreate the defect
    it exists to fix — a legend that stops answering as the viewport grows.
    """
    parts = raw.split(",")
    if len(parts) != BBOX_PARTS:
        raise _refuse_bbox("bbox_shape", "bbox must be minx,miny,maxx,maxy in WGS84", raw)
    try:
        minx, miny, maxx, maxy = (float(part) for part in parts)
    except ValueError:
        raise _refuse_bbox("bbox_number", "bbox coordinates must be numbers", raw) from None
    if not (-LON_LIMIT <= minx <= LON_LIMIT and -LON_LIMIT <= maxx <= LON_LIMIT):
        raise _refuse_bbox("bbox_range", f"longitudes must be within ±{LON_LIMIT:g}", raw)
    if not (-LAT_LIMIT <= miny <= LAT_LIMIT and -LAT_LIMIT <= maxy <= LAT_LIMIT):
        raise _refuse_bbox("bbox_range", f"latitudes must be within ±{LAT_LIMIT:g}", raw)
    if minx > maxx or miny > maxy:
        raise _refuse_bbox(
            "bbox_order",
            "bbox must read minx,miny,maxx,maxy; a box that crosses the antimeridian is two"
            " boxes and is asked for as two requests",
            raw,
        )
    return minx, miny, maxx, maxy


def _rendered_bbox(envelope: tuple[float, float, float, float], separator: str) -> str:
    """The box, rendered so it names the box the query ran over — everywhere it identifies it.

    `repr` is the shortest string that round-trips to the same float; `%g` is six significant
    digits, which at a three-digit longitude is three decimals, about 76 m. Under `%g` two
    viewports 0.0003 degrees apart collapsed to one echo and one derivation handle while
    disagreeing on the count, and links.wells named a box that returned no rows under a
    summary reporting one (gate-wss BLOCK-1). The selector charset (SB-07 §2.1) admits `.`,
    `-`, `+` and `e`, so a repr is selector-safe; NaN and infinity never reach here because
    the range guard rejects them first.
    """
    return separator.join(repr(value) for value in envelope)


def _count(found: list[dict[str, Any]], *, selector: str) -> Figure | None:
    """Absent, not zero: a class the box does not contain has no count and no derivation."""
    if not found:
        return None
    return figure(
        str(sum(row["wells"] for row in found)),
        unit=COUNT_UNIT,
        derivation=max(row["derivation_id"] for row in found),
        selector=selector,
    )


def _classes(found: list[dict[str, Any]], *, box: str, scope: str = "") -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in found:
        if row["status_canonical"] is not None:
            grouped.setdefault(row["status_canonical"], []).append(row)
    ordered = sorted(
        grouped.items(), key=lambda item: (-sum(row["wells"] for row in item[1]), item[0])
    )
    return [
        {
            "status": status,
            "wells": _count(
                group, selector=f"col=wells&status={_token(status)}{scope}&bbox={box}"
            ),
        }
        for status, group in ordered
    ]


def _basins(found: list[dict[str, Any]], *, box: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str | None, str | None], list[dict[str, Any]]] = {}
    for row in found:
        grouped.setdefault((row["basin"], row["state_code"]), []).append(row)
    summaries = []
    for (basin, state_code), group in sorted(
        grouped.items(), key=lambda item: (item[0][0] or "", item[0][1] or "")
    ):
        scope = f"&basin={_token(basin)}&state={_token(state_code)}"
        summaries.append(
            {
                "basin": basin,
                "state_code": state_code,
                "status_vocabulary_rule": STATUS_VOCABULARY_RULES.get(state_code or ""),
                "wells": _count(group, selector=f"col=wells{scope}&bbox={box}"),
                "unmapped_wells": _count(
                    [row for row in group if row["status_canonical"] is None],
                    selector=f"col=unmapped_wells{scope}&bbox={box}",
                ),
                "statuses": _classes(group, box=box, scope=scope),
            }
        )
    return summaries


def _summary_labels(basins: list[dict[str, Any]]) -> dict[str, str]:
    """One key per basin actually present: `web/src/api/envelope.ts` looks a pointer up by
    exact match, so a `/basins/*/…` key resolves for nobody (the same rule as _pool_labels)."""
    return STATUS_SUMMARY_LABELS | {
        pointer: term
        for index in range(len(basins))
        for pointer, term in (
            (f"/basins/{index}/statuses", "gt_well_status"),
            (f"/basins/{index}/unmapped_wells", "gt_well_status"),
            (f"/basins/{index}/status_vocabulary_rule", "gt_conformance_rule"),
        )
    }


def _handles(node: Any) -> int:
    """How many handles `links.explain` is being asked to carry, counted the way it counts."""
    if isinstance(node, Figure):
        return 1
    if isinstance(node, dict):
        return sum(_handles(value) for value in node.values())
    if isinstance(node, list):
        return sum(_handles(value) for value in node)
    return 0


def _summary_warnings(
    counted: list[dict[str, Any]], *, orphans: int, states: list[str], handles: int
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if handles > MAX_HANDLES:
        warnings.append(
            {
                "code": "explain_link_truncated",
                "detail": (
                    f"This box produced {handles} counts and links.explain carries the first"
                    f" {MAX_HANDLES} handles, so {handles - MAX_HANDLES} are absent from it."
                    " Every count still resolves on its own: read the count's `d` and call"
                    " /v1/explain?h=<d>&depth=full. The cap is /v1/explain's own"
                    " (SB-07 §9.4), not this operation's."
                ),
                "pointer": "/basins",
            }
        )
    if orphans:
        subject, verb, pronoun = (
            ("geometry", "has", "it is") if orphans == 1 else ("geometries", "have", "they are")
        )
        warnings.append(
            {
                "code": "geometry_without_a_well_row",
                "detail": (
                    f"{orphans} {subject} in this box {verb} no well row at this vintage, so"
                    f" {pronoun} in no class and in no total here. That is not a well with no"
                    " status — a different fact, counted in unmapped_wells — and the geometry"
                    " still draws on the map."
                ),
                "pointer": "/wells",
            }
        )
    if len({row["derivation_id"] for row in counted}) > 1:
        warnings.append(
            {
                "code": "aggregate_spans_derivations",
                "detail": (
                    "More than one derivation promoted the wells in this box. Every count is"
                    " over rows the box selected, and its handle names one of the derivations"
                    " those rows came from; links.explain resolves what each handle names."
                ),
                "pointer": "/wells",
            }
        )
    if states:
        warnings.append(
            {
                "code": "status_vocabulary_unregistered",
                "detail": (
                    f"No status vocabulary rule is registered for state code(s)"
                    f" {', '.join(states)}, so their rows name none. The counts are the"
                    " canonical values as promoted; the rule that produced them is not"
                    " citable here until it is registered (R8)."
                ),
                "pointer": "/basins",
            }
        )
    return warnings


@router.get(
    "/wells/status-summary",
    operation_id="get_well_status_summary",
    summary="Well status counts for a box",
    description=(
        "How many wells of each canonical status have geometry inside a bounding box, as of a"
        " knowledge-time cut. This is the count a map legend states, asked of the data rather"
        " than of what a renderer drew: a tile pyramid thins points as it zooms out and a"
        " symbology withdraws its low-salience classes, so a count taken from drawn features"
        " falls exactly as the viewed area grows. This one does not move with zoom, with"
        " styling or with which tiles have arrived."
        " The population is wells whose recorded geometry — surface, bottomhole or lateral —"
        " intersects the box, which is the same population `/v1/wells?bbox=` pages, and a well"
        " with no geometry at all is in no viewport and in no count here. The box is closed:"
        " a well exactly on the edge is inside it. There is no degree cap, because the answer"
        " is bounded by the status vocabulary rather than by the population; `links.wells` is"
        " published only where the box is inside the collection's own four-degree cap."
        " Every count is a figure with a derivation handle over the rows it counted, so a"
        " legend number resolves at /v1/explain to the government file the statuses came from."
        " The box a handle names is the box the query ran over, at full precision — two"
        " viewports a metre apart are two handles. Where a box produces more counts than"
        " /v1/explain accepts handles in one call, `links.explain` carries as many as it can"
        " and a warning says exactly how many it left out; each count still resolves alone."
        " A class no well in the box carries is absent rather than zero. Wells whose source"
        " reported no status are their own bucket, `unmapped_wells`, and are never added to a"
        " class — in the 2026-08-20 Texas load 65,685 wells are in it, which is more than any"
        " class it could have been folded into. Counts are split per basin with the vocabulary"
        " rule that mapped that jurisdiction's codes (cr_nd_status_vocab_1 in North Dakota,"
        " cr_tx_status_vocab_1 in Texas), because a status class means what its rule says it"
        " means. It does not return the wells themselves — see /v1/wells."
    ),
    response_model=EnvelopeModel[WellStatusSummary],
    openapi_extra={
        **request_example(query={"bbox": EXAMPLE_BBOX}),
        **semantics(
            bbox={
                "glossary": "gt_crs_compute_crs",
                "so": (
                    "WGS84 degrees, and the only scope this endpoint has — it is required, so a"
                    " count always says which box it is a count of. It matches a well any of"
                    " whose recorded geometry overlaps the box, so a lateral crossing one corner"
                    " is counted while its surface hole sits outside. Uncapped, unlike the"
                    " collection's: a whole-state box is the case the endpoint exists for."
                ),
            },
            as_of={
                "glossary": "gt_knowledge_time",
                "so": (
                    "Counts the classes as they were described on that knowledge date, not the"
                    " wells drilled by then. A status restatement appends a row, so an earlier"
                    " as_of returns the earlier class and the totals move between them; a well"
                    " whose spine row is later than the date is counted in no class and"
                    " disclosed as geometry without a well row."
                ),
            },
        ),
    },
    responses=problem_responses("validation_failed", "service_degraded"),
)
def get_well_status_summary(
    request: Request,
    connection: Connection,
    bbox: Annotated[
        str, Query(description="minx,miny,maxx,maxy in WGS84. Required; there is no cap.")
    ],
    as_of: AsOf = None,
) -> JSONResponse:
    envelope = _status_bbox(bbox)
    found = rows(
        connection,
        STATUS_SUMMARY_SQL,
        dict(zip(("minx", "miny", "maxx", "maxy"), envelope, strict=True)) | {"as_of": as_of},
    )
    counted = [row for row in found if not row["no_well_row"]]
    orphans = sum(row["wells"] for row in found if row["no_well_row"])
    box = _rendered_bbox(envelope, ",")
    selector_box = _rendered_bbox(envelope, ":")
    basins = _basins(counted, box=selector_box)
    unregistered = sorted(
        {
            row["state_code"] or "unassigned"
            for row in counted
            if not STATUS_VOCABULARY_RULES.get(row["state_code"] or "")
        }
    )
    rules = sorted({rule for row in basins if (rule := row["status_vocabulary_rule"])})
    data = {
        "bbox": box,
        "wells": _count(counted, selector=f"col=wells&bbox={selector_box}"),
        "unmapped_wells": _count(
            [row for row in counted if row["status_canonical"] is None],
            selector=f"col=unmapped_wells&bbox={selector_box}",
        ),
        "statuses": _classes(counted, box=selector_box),
        "basins": basins,
        "vocabulary_rules": rules,
    }
    links = {rule: f"/v1/conformance/{rule}" for rule in rules}
    minx, miny, maxx, maxy = envelope
    if maxx - minx <= BBOX_DEGREE_CAP and maxy - miny <= BBOX_DEGREE_CAP:
        links["wells"] = f"/v1/wells?bbox={box}"
    return enveloped(
        request,
        data,
        as_of=max((row["effective_from"] for row in counted), default=None),
        as_of_requested=iso(as_of) or "latest",
        labels=_summary_labels(basins),
        warnings=_summary_warnings(
            counted, orphans=orphans, states=unregistered, handles=_handles(data)
        ),
        links=links,
    )


@router.get(
    "/wells/{api10}",
    operation_id="get_well",
    summary="One well header",
    description=(
        "Header, resolved status, land unit and geometry references for one well, plus the"
        " lateral count and total lateral length. Length is computed live from"
        " canonical.well_spatial in the basin's compute CRS — never from a stored degree"
        " length, and never from a mart this slice cannot exercise. It does not include"
        " production, forecasts or economics."
    ),
    response_model=EnvelopeModel[WellDetail],
    openapi_extra=request_example(path={"api10": EXAMPLE_API10}),
    responses=problem_responses("not_found", "validation_failed", "service_degraded"),
)
def get_well(
    request: Request,
    connection: Connection,
    api10: Annotated[str, Path(description="Ten-digit API well number.", pattern=API10_PATTERN)],
    as_of: AsOf = None,
) -> JSONResponse:
    found = rows(
        connection,
        RANKED_WELLS + " and api10 = %(api10)s",
        {"as_of": as_of, "api10": api10},
    )
    if not found:
        raise ProblemError("not_found", detail=f"no well {api10} at this vintage")
    row = found[0]

    crs = rows(connection, _STORAGE_CRS, {"basin": row["basin"] or "williston"})
    storage_epsg = crs[0]["storage_epsg"] if crs else STORAGE_EPSG
    # The basin's own rule, so a TX length's handle resolves to a rule about TX geometry.
    method = resolve_length_method(connection, basin=row["basin"])
    warnings: list[dict[str, Any]] = []
    lease_reported = lease_reporting_rule(connection, row["state_code"])
    if lease_reported:
        warnings.append(pending_allocation(lease_reported))
    geometry = rows(
        connection,
        _SPATIAL.format(length_metres=method.metres_sql()),
        {"api10": api10},
    )

    warnings.extend(_held_back_geometry(connection, api10))
    laterals = [item for item in geometry if item["geom_type"] == "lateral"]
    untiled = [item["geom_key"] for item in laterals if not item["tiled"]]
    if untiled:
        warnings.append(
            {
                "code": "below_tile_resolution",
                "detail": (
                    f"{len(untiled)} lateral geometries are below the resolution of the"
                    f" deepest published zoom (z{TILE_MAX_ZOOM}) and render on no tile;"
                    " their length is still served here"
                ),
                "pointer": "/geometry",
            }
        )
    length_figure = None
    if laterals:
        metres = sum(Decimal(str(item["length_m"])) for item in laterals)
        derivations = {item["derivation_id"] for item in laterals}
        if len(derivations) > 1:
            warnings.append(
                {
                    "code": "aggregate_spans_derivations",
                    "detail": f"{len(derivations)} derivations contributed; the handle names one",
                    "pointer": "/lateral_length_ft",
                }
            )
        # Round-final: the sum is converted once, and the serving edge is the only quantize.
        length_figure = figure(
            str(metres_to_feet(metres).quantize(Decimal("0.01"))),
            unit="ft",
            derivation=sorted(derivations)[-1],
            selector=f"api10={api10}&col=lateral_length_ft",
        )

    point = next((item for item in geometry if item["lon"] is not None), None)
    data = _summary(row) | {
        "api14": row["api14"],
        "state_code": row["state_code"],
        "ndic_file_no": row["ndic_file_no"],
        "status_reported": row["status_reported"],
        "well_type_reported": row["well_type_reported"],
        "basin": row["basin"],
        "lateral_count": len(laterals),
        "lateral_length_ft": length_figure,
        "total_depth_ft": (
            figure(
                str(Decimal(str(row["total_depth_ft"])).quantize(Decimal("0.1"))),
                unit="ft",
                derivation=row["derivation_id"],
                selector=f"api10={api10}&col=total_depth_ft",
            )
            if row["total_depth_ft"] is not None
            else None
        ),
        "completion_date": iso(row["completion_date"]),
        "compute_crs": method.compute_crs,
        "length_method": method.method,
        "storage_crs": f"EPSG:{storage_epsg}",
        "geometry": [
            {
                "geom_type": item["geom_type"],
                "geom_key": item["geom_key"],
                "source_datum": item["source_datum"],
            }
            for item in geometry
        ],
        "surface_point": {"lon": point["lon"], "lat": point["lat"]} if point else None,
    }
    return enveloped(
        request,
        data,
        as_of=row["effective_from"],
        as_of_requested=iso(as_of) or "latest",
        labels=WELL_LABELS,
        warnings=warnings,
        links={
            "production": f"/v1/wells/{api10}/production",
            **(
                {"reporting_rule": f"/v1/conformance/{lease_reported['rule_id']}"}
                if lease_reported
                else {}
            ),
        },
    )
