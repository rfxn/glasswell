"""The well spine: the collection the map lists and the header the card renders."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import AsOf, Connection, Cursor, WellsLimit, rows
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import EXAMPLE_API10, GLOSSARY_KEY, request_example
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
from glasswell.lineage.envelope import figure
from glasswell.marts.tiles import TILE_BUFFER, TILE_EXTENT, TILE_MAX_ZOOM, WEB_MERCATOR
from glasswell.units import metres_to_feet

router = APIRouter(tags=["wells"])

BBOX_DEGREE_CAP = 4.0
API10_PATTERN = r"^\d{10}$"

WELL_LABELS = {
    "/api10": "gt_api_10_api_12_api_14",
    "/land_unit_label": "gt_land_unit",
    "/confidential_flag": "gt_confidential_well",
    "/lateral_length_ft": "gt_wellbore",
    "/total_depth_ft": "gt_wellbore",
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
    api10: str = Field(description="Ten-digit API well number.", json_schema_extra={
        GLOSSARY_KEY: "gt_api_10_api_12_api_14"})
    well_name: str | None = Field(description="Well name as reported by the operator.")
    operator_name_reported: str | None = Field(description="Operator name exactly as reported.")
    status_canonical: str | None = Field(
        description=(
            "Status mapped through the source's status vocabulary rule — cr_nd_status_vocab_1"
            " in North Dakota, cr_tx_status_vocab_1 in Texas. Null where the source reported"
            " no status at all, which is not the same as an unknown one."
        )
    )
    county_code_at_permit: str | None = Field(description="County code recorded at permit.")
    land_unit_label: str | None = Field(description="PLSS land unit label.", json_schema_extra={
        GLOSSARY_KEY: "gt_land_unit"})
    spud_date: date | None = Field(description="Spud date as reported.")
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
    lon: float = Field(description="Longitude in the storage CRS (EPSG:4326).")
    lat: float = Field(description="Latitude in the storage CRS (EPSG:4326).")


class WellDetail(WellSummary):
    api14: str | None = Field(description="Fourteen-digit API number where known.")
    state_code: str | None = Field(description="State code as reported.")
    ndic_file_no: str | None = Field(description="NDIC file number for the well.")
    status_reported: str | None = Field(description="Status code exactly as the source wrote it.")
    well_type_reported: str | None = Field(description="Well type exactly as reported.")
    basin: str | None = Field(description="Basin the well is assigned to.")
    lateral_count: int = Field(description="Lateral geometries recorded for this well.")
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
    openapi_extra=request_example(query={"limit": 5}),
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
