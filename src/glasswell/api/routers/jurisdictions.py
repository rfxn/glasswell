"""The jurisdiction registry as a served collection: who is registered, and on what authority.

Not `/v1/states`. `state` is already SB-04's lifecycle word and a frozen query parameter meaning
the API prefix, reference collections are the canonical noun plural, and a province is not a
state. The row carries every decision the serving path reads, so a reader can check what the
map and the well card were told rather than inferring it from what they drew.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import AsOf, Connection, Cursor, ExplainEffect, jurisdictions, rows
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
from glasswell.api.provenance import register_response_figures
from glasswell.api.responses import EnvelopeModel, FigureModel, enveloped, inline_for, iso
from glasswell.lineage.envelope import figure
from glasswell.lineage.jurisdictions import Jurisdiction

router = APIRouter(tags=["vocabulary"])

JURISDICTION_LIMIT_CAP = 200
COUNT_UNIT = "wells"
TOTAL_STATUS_KEY = "*total*"

_PUBLICATION_BOUNDS = """
select min(published_at) as earliest, max(published_at) as latest
  from lineage.jurisdictions
"""

# The latest measurement at or before the knowledge cut, per jurisdiction. A count is absent
# until a refresh has produced one; there is no live count(*) fallback, because two numbers
# with one name is worse than one number with a date beside it (R-3).
_WELL_COUNTS = """
with latest as (
    select jurisdiction_code, max(measured_on) as measured_on
      from lineage.jurisdiction_well_counts
     where %(as_of)s::date is null or measured_on <= %(as_of)s::date
     group by jurisdiction_code
)
select c.jurisdiction_code, c.measured_on, c.status_canonical, c.status_key, c.well_count,
       c.derivation_id
  from lineage.jurisdiction_well_counts c
  join latest on latest.jurisdiction_code = c.jurisdiction_code
             and latest.measured_on = c.measured_on
 order by c.jurisdiction_code, c.status_key
"""

JurisdictionLimit = Annotated[
    int,
    Query(
        ge=1,
        le=JURISDICTION_LIMIT_CAP,
        description=(
            f"Page size, {DEFAULT_LIMIT} by default, {JURISDICTION_LIMIT_CAP} at most."
        ),
    ),
]


class Regulator(BaseModel):
    name: str = Field(description="The agency that files the data glasswell ingests.")
    url: str = Field(description="Where that agency publishes it.")


class Identity(BaseModel):
    scheme: str = Field(
        description="`api10` or `uwi`: which well identifier this jurisdiction is keyed by.",
        json_schema_extra={GLOSSARY_KEY: "gt_identity_scheme"},
    )
    prefix: str | None = Field(
        description=(
            "The two leading digits of every API-10 in this jurisdiction, or null where the"
            " scheme is not API-10. These are API codes, not FIPS: 25 is Montana."
        ),
        json_schema_extra={
            **not_a_figure(
                "The two leading digits of every API-10 in a jurisdiction: an"
                " identifier's prefix, not a measured quantity."
            ),
            GLOSSARY_KEY: "gt_api_10_api_12_api_14",
        },
    )
    pattern: str | None = Field(
        description="The regular expression a well identifier in this jurisdiction matches.",
        json_schema_extra={GLOSSARY_KEY: "gt_api_10_api_12_api_14"},
    )
    is_unique: bool = Field(
        description=(
            "Whether the identifier is a well key here. False where a state reissues API-10s,"
            " which is a property of the key rather than of the scheme."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_identity_scheme"},
    )


class JurisdictionRule(BaseModel):
    decision: str = Field(description="What this rule decides for this jurisdiction.")
    rule_id: str = Field(
        description="The conformance rule, resolvable at /v1/conformance/{rule_id}.",
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )
    serving: bool = Field(
        description=(
            "Whether this is the rule the serving path reads. A decision may register more"
            " than one rule — Montana files inventory at two grains — and exactly one serves."
        )
    )
    note: str | None = Field(description="Why a registered rule is not the serving one.")


class MapPresentation(BaseModel):
    wells_tile_layer_id: str | None = Field(
        description="The published tile layer the `Wells` family draws for this jurisdiction."
    )
    colour: str | None = Field(description="The swatch colour that layer is drawn with.")


class Capabilities(BaseModel):
    neighbors: bool = Field(description="Whether the neighbour mart holds subjects here.")
    land_grid_state: bool = Field(description="Whether the PLSS land grid covers this state.")
    land_grid_scope: bool = Field(
        description="Whether land metrics are scoped to it. A state in the grid is always"
        " in scope; the reverse does not hold."
    )


class JurisdictionStatusCount(BaseModel):
    status_canonical: str = Field(
        description="The canonical well status this count is for.",
        json_schema_extra={GLOSSARY_KEY: "gt_well_status"},
    )
    wells: FigureModel = Field(description="Wells measured in that status, with its handle.")


class JurisdictionRow(BaseModel):
    jurisdiction_code: str = Field(
        description="The registry's own code for the jurisdiction, e.g. ND.",
        json_schema_extra={GLOSSARY_KEY: "gt_jurisdiction"},
    )
    name: str = Field(
        description="The jurisdiction's name, served rather than mapped again in the client.",
        json_schema_extra={GLOSSARY_KEY: "gt_jurisdiction"},
    )
    level: str = Field(
        description="`state` or `province`.",
        json_schema_extra={GLOSSARY_KEY: "gt_jurisdiction"},
    )
    regulator: Regulator = Field(
        description="Whose filings this jurisdiction is served from.",
        json_schema_extra={GLOSSARY_KEY: "gt_regulator"},
    )
    identity: Identity = Field(description="How a well is identified here.")
    source_ids: list[str] = Field(
        description="Every registered source carrying this jurisdiction's coverage.",
        json_schema_extra={GLOSSARY_KEY: "gt_source"},
    )
    rules: list[JurisdictionRule] = Field(
        description="Every conformance rule registered for this jurisdiction, by decision.",
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )
    liquids_basis: str | None = Field(
        description=(
            "What a liquid barrel means here, carried beside every liquids figure served for"
            " this jurisdiction. Null where no liquids policy is registered."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_liquids_policy"},
    )
    map: MapPresentation = Field(description="How this jurisdiction is drawn.")
    capabilities: Capabilities = Field(description="What is built for it, not what is planned.")
    well_count: FigureModel | None = Field(
        description=(
            "Wells measured in this jurisdiction at `measured_on`, with its handle. Absent"
            " until a refresh has produced one, and never served as zero in its place."
        )
    )
    well_counts_by_status: list[JurisdictionStatusCount] = Field(
        description="The same measurement broken out by canonical status."
    )
    measured_on: str | None = Field(
        description="The date the counts were measured. Absent when they are."
    )
    effective_from: str = Field(
        description="Valid time: the date this registration takes effect from.",
        json_schema_extra={GLOSSARY_KEY: "gt_knowledge_time"},
    )
    published_at: str = Field(
        description="Knowledge time: the date glasswell published this registration.",
        json_schema_extra={GLOSSARY_KEY: "gt_knowledge_time"},
    )


def _counts(connection, as_of: date | None) -> dict[str, list[dict[str, Any]]]:
    measured: dict[str, list[dict[str, Any]]] = {}
    for row in rows(connection, _WELL_COUNTS, {"as_of": as_of}):
        measured.setdefault(row["jurisdiction_code"], []).append(row)
    return measured


def _count_figure(row: dict[str, Any], code: str) -> Any:
    selector = f"jurisdiction={code}"
    if row["status_canonical"] is not None:
        selector += f"&status={row['status_canonical']}"
    return figure(
        str(row["well_count"]),
        unit=COUNT_UNIT,
        derivation=row["derivation_id"],
        selector=selector,
    )


def _row(registration: Jurisdiction, measured: list[dict[str, Any]]) -> dict[str, Any]:
    code = registration.jurisdiction_code
    total = next((row for row in measured if row["status_key"] == TOTAL_STATUS_KEY), None)
    classed = [row for row in measured if row["status_key"] != TOTAL_STATUS_KEY]
    return {
        "jurisdiction_code": code,
        "name": registration.name,
        "level": registration.level,
        "regulator": {
            "name": registration.regulator_name,
            "url": registration.regulator_url,
        },
        "identity": {
            "scheme": registration.identity_scheme,
            "prefix": registration.identity_prefix,
            "pattern": registration.identity_pattern,
            "is_unique": registration.identity_is_unique,
        },
        "source_ids": list(registration.source_ids),
        "rules": [
            {
                "decision": rule.decision,
                "rule_id": rule.rule_id,
                "serving": rule.serving,
                "note": rule.note,
            }
            for rule in registration.rules
        ],
        "liquids_basis": registration.liquids_basis,
        "map": {
            "wells_tile_layer_id": registration.wells_tile_layer_id,
            "colour": registration.map_colour,
        },
        "capabilities": {
            "neighbors": registration.neighbors_available,
            "land_grid_state": registration.land_grid_state,
            "land_grid_scope": registration.land_grid_scope,
        },
        "well_count": _count_figure(total, code) if total else None,
        "well_counts_by_status": [
            {
                "status_canonical": row["status_canonical"],
                "wells": _count_figure(row, code),
            }
            for row in classed
        ],
        "measured_on": iso(measured[0]["measured_on"]) if measured else None,
        "effective_from": iso(registration.effective_from),
        "published_at": iso(registration.published_at),
    }


@router.get(
    "/jurisdictions",
    operation_id="list_jurisdictions",
    summary="List registered jurisdictions",
    description=(
        "Every jurisdiction glasswell serves, with the regulator it is served from, the"
        " identity scheme its wells are keyed by, the conformance rules that decide its"
        " status vocabulary, geometry provenance, liquids policy and production grain, and"
        " the wells last measured in it. Registrations are append-only under two clocks:"
        " `as_of` is the knowledge cut, so a registration published after it is not served"
        " under it. Counts are absent until a refresh has produced them and are never served"
        " as zero in their place. This is a registry of registrations, not of reserves."
    ),
    response_model=EnvelopeModel[list[JurisdictionRow]],
    openapi_extra={
        **request_example(query={"level": "state", "limit": 5}),
        **dataset(
            id="jurisdictions",
            title="Jurisdictions",
            group="vocabulary",
            collection_pointer="",
            row_id=["/jurisdiction_code"],
            facets=["level"],
            columns={
                "default": [
                    "/jurisdiction_code",
                    "/name",
                    "/level",
                    "/regulator",
                    "/identity",
                    "/well_count",
                    "/measured_on",
                ],
                "sort": "/jurisdiction_code",
            },
            intro="nb_dataset_jurisdictions",
            order=42,
        ),
        **semantics(
            as_of={
                "glossary": "gt_knowledge_time",
                "so": (
                    "Serves the registration published at or before the cut, and the"
                    " measurement measured at or before it. A correction published later is"
                    " not visible under an earlier cut, which is what a static current-state"
                    " view could not honour."
                ),
            },
            cursor={
                "so": (
                    "Pins the page to jurisdiction code, the filters that opened it, and both"
                    " clocks, so a registration appended mid-traversal cannot shift it."
                ),
            },
            limit={
                "so": (
                    f"Capped at {JURISDICTION_LIMIT_CAP}; the default remains {DEFAULT_LIMIT}."
                    " The registry is small, and it is a page rather than a dump so that it"
                    " stays one when a fifth jurisdiction registers."
                ),
            },
            level={
                "glossary": "gt_jurisdiction",
                "so": (
                    "Filters to `state` or `province`. A province is not a state, which is"
                    " why this collection is not /v1/states."
                )
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
def list_jurisdictions(
    request: Request,
    connection: Connection,
    explain: ExplainEffect,
    cursor: Cursor = None,
    limit: JurisdictionLimit = DEFAULT_LIMIT,
    as_of: AsOf = None,
    level: Annotated[
        str | None, Query(description="Filter to one registration level.")
    ] = None,
) -> JSONResponse:
    filters = {"as_of": as_of, "level": level}
    fingerprint = query_fingerprint(filters)
    decoded = decode_cursor(cursor, fingerprint=fingerprint) if cursor is not None else None
    bounds = rows(connection, _PUBLICATION_BOUNDS, {})[0]
    if as_of is not None and bounds["earliest"] is not None and as_of < bounds["earliest"]:
        raise ProblemError(
            "as_of_out_of_range",
            detail=(
                f"as_of {as_of.isoformat()} precedes the earliest jurisdiction registration"
                f" {bounds['earliest'].isoformat()}, so no registration was published yet"
            ),
        )
    cursor_as_of = date.fromisoformat(decoded.as_of) if decoded and decoded.as_of else None
    if decoded is not None and cursor_as_of is None:
        raise ProblemError(
            "cursor_malformed", detail="jurisdiction cursor does not pin a knowledge cut"
        )
    if as_of is not None and cursor_as_of is not None and cursor_as_of != as_of:
        raise ProblemError(
            "cursor_query_mismatch",
            detail="this cursor was minted against a different as_of cut",
        )

    registry = jurisdictions(connection, as_of)
    measured = _counts(connection, as_of)
    resolved = [row for row in registry if level is None or row.level == level]
    if decoded is not None:
        resolved = [row for row in resolved if row.jurisdiction_code > decoded.key]
    items, has_more = page(
        [_row(row, measured.get(row.jurisdiction_code, [])) for row in resolved[: limit + 1]],
        limit,
    )
    items = register_response_figures(
        connection,
        items,
        dataset="api.jurisdictions",
        operation_id="list_jurisdictions",
        locator=request.url.path,
        partition={
            "as_of": iso(as_of) or "latest",
            "level": level or "all",
            "limit": str(limit),
        },
        input_derivations=sorted(
            {row["derivation_id"] for group in measured.values() for row in group}
        ),
        correlation_id=request.state.request_id,
        rule_ids=sorted({rule["rule_id"] for row in items for rule in row["rules"]}),
    )
    next_cursor = (
        encode_cursor(
            key=items[-1]["jurisdiction_code"],
            tiebreak="",
            as_of=registry.knowledge_as_of,
            fingerprint=fingerprint,
            valid_as_of=registry.valid_as_of,
        )
        if has_more and items
        else None
    )
    labels = {
        pointer: term
        for index, _ in enumerate(items)
        for pointer, term in {
            f"/{index}/jurisdiction_code": "gt_jurisdiction",
            f"/{index}/name": "gt_jurisdiction",
            f"/{index}/regulator": "gt_regulator",
            f"/{index}/identity/scheme": "gt_identity_scheme",
            f"/{index}/source_ids": "gt_source",
            f"/{index}/rules": "gt_conformance_rule",
            f"/{index}/liquids_basis": "gt_liquids_policy",
            f"/{index}/well_count": "gt_well_status",
        }.items()
    }
    return enveloped(
        request,
        items,
        as_of=registry.knowledge_as_of,
        as_of_requested=iso(as_of) or "latest",
        labels=labels,
        next_cursor=next_cursor,
        links={
            "next": next_link("/v1/jurisdictions", filters | {"limit": limit}, next_cursor)
            if next_cursor
            else None
        },
        explain=inline_for(connection, explain),
    )
