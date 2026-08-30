"""What the modeling layer is pinned to: the accepted P3 publications, and what one accepts."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import Connection, Cursor, ExplainEffect, SpineLimit
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import (
    EXAMPLE_PUBLICATION_ID,
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
from glasswell.api.provenance import register_response_figures
from glasswell.api.responses import EnvelopeModel, FigureModel, enveloped, inline_for, iso
from glasswell.lineage.envelope import figure
from glasswell.modeling import served

router = APIRouter(tags=["kitchen"])

PUBLICATION_PATTERN = r"^p3pub_[0-9a-f]{32}$"
INSTANCE_UNIT = "subject_instances"
SHARE_UNIT = "share"
CONTROL_RULES = (
    "cr_tc_publication_scope_1",
    "cr_tc_peer_ladder_1",
    "cr_tc_quantile_convention_1",
)
PUBLICATION_LABELS = {
    "/versions/type_curve": "gt_type_curve",
    "/split_set_id": "gt_split_set",
    "/coverage/support/fallback_by_level": "gt_peer_ladder",
    "/coverage/support/test_subject_instances": "gt_training_support",
}


class PublicationVersions(BaseModel):
    feature: str = Field(description="Feature-set version the publication was built from.")
    model_dataset: str = Field(description="Model-ready dataset version.")
    type_curve: str = Field(
        description="Type-curve control version.",
        json_schema_extra={GLOSSARY_KEY: "gt_type_curve"},
    )


class ModelingPublication(BaseModel):
    publication_id: str = Field(
        description="Content address of the acceptance receipt.",
        json_schema_extra={GLOSSARY_KEY: "gt_recipe"},
    )
    basin: str = Field(
        description="Basin the publication covers.",
        json_schema_extra={GLOSSARY_KEY: "gt_basin"},
    )
    eval_vintage: date = Field(
        description="Evaluation vintage the control was pinned to.",
        json_schema_extra={GLOSSARY_KEY: "gt_knowledge_time"},
    )
    vintage_basis: str = Field(description="How the evaluation vintage was reconstructed.")
    versions: PublicationVersions = Field(description="The three semantic versions pinned.")
    split_set_id: str = Field(
        description="Content-addressed identity of the split bundle.",
        json_schema_extra={GLOSSARY_KEY: "gt_split_set"},
    )
    code_version: str = Field(
        description="Build stamp of the code that produced the artifacts.",
        json_schema_extra={GLOSSARY_KEY: "gt_determinism_class"},
    )
    environment_id: str = Field(description="Pinned environment identity of the build.")
    created_at: str = Field(description="When the receipt was written.")
    accepted: bool = Field(
        description="Always true: a receipt exists only for a publication that passed the gate."
    )


class PublicationSplit(BaseModel):
    origin: date = Field(description="Rolling origin of the persisted temporal split.")
    horizon_months: int = Field(
        description="Months of history the split holds out.",
        json_schema_extra=not_a_figure(
            "Horizon of a persisted temporal split, read from the split object. A parameter of"
            " the split set, not an observation it stands behind."
        ),
    )
    split_id: str = Field(description="Identity of the split object.")
    sha256: str = Field(description="Content address of the persisted split.")


class AcceptanceGate(BaseModel):
    observed: FigureModel = Field(description="The measured share, with its handle.")
    minimum: str | None = Field(default=None, description="Floor the gate required.")
    maximum: str | None = Field(default=None, description="Ceiling the gate allowed.")
    status: str = Field(description="pass or fail, as recorded when the artifact was built.")


class PublicationCoverage(BaseModel):
    acceptance: dict[str, AcceptanceGate] = Field(
        description="The gates the publication had to clear, with their thresholds."
    )
    support: dict[str, Any] = Field(
        description="Protocol 4D's support distribution: peer-ladder rungs and reason mentions."
    )
    control_contract: dict[str, Any] = Field(
        description="The build parameters compiled into the control, served verbatim."
    )


class ModelingPublicationDetail(ModelingPublication):
    derivations: dict[str, str] = Field(description="The three pinned derivation ids.")
    recipes: dict[str, str] = Field(description="The three recipes that produced them.")
    baseline: dict[str, str] = Field(description="The sealed baseline the gate pinned.")
    environment: dict[str, str] = Field(description="Environment identity of the build.")
    artifact_sha256: dict[str, str] = Field(
        description="Content addresses of the published artifacts."
    )
    rows: dict[str, int] = Field(
        description="Rows each artifact recorded when it was written."
    )
    splits: list[PublicationSplit] = Field(description="Every persisted split in the bundle.")
    coverage: PublicationCoverage = Field(description="Acceptance and support, from the artifact.")
    supersedes: str | None = Field(
        description="The publication this one displaced, still addressable by id."
    )


def _row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "publication_id": record["publication_id"],
        "basin": record["basin"],
        "eval_vintage": iso(record["eval_vintage"]),
        "vintage_basis": record["vintage_basis"],
        "versions": {
            "feature": record["feature_version"],
            "model_dataset": record["model_dataset_version"],
            "type_curve": record["control_version"],
        },
        "split_set_id": record["split_set_id"],
        "code_version": record["code_version"],
        "environment_id": record["environment_id"],
        "created_at": record["created_at"].isoformat(),
        "accepted": True,
    }


@router.get(
    "/modeling/publications",
    operation_id="list_modeling_publications",
    summary="List modeling publications",
    description=(
        "Every accepted P3 publication receipt: the three semantic versions it pinned, the"
        " split set it was built on, and the environment that built it. A receipt exists only"
        " for a publication that cleared the gate, so `accepted` is always true and the"
        " absence of a row is the only negative answer this collection gives. The receipt is"
        " what makes a served type-curve figure traceable — nothing else on this API decides"
        " which artifact is servable."
    ),
    response_model=EnvelopeModel[list[ModelingPublication]],
    openapi_extra={
        **request_example(query={"limit": 5}),
        **dataset(
            id="modeling_publications",
            title="Modeling publications",
            group="kitchen",
            collection_pointer="",
            row_id=["/publication_id"],
            detail_operation="get_modeling_publication",
            facets=["basin"],
            columns={
                "default": [
                    "/publication_id",
                    "/basin",
                    "/eval_vintage",
                    "/versions/type_curve",
                    "/split_set_id",
                    "/code_version",
                ],
                "sort": "/publication_id",
            },
            intro="nb_dataset_modeling_publications",
            order=25,
        ),
        **semantics(
            basin={
                "glossary": "gt_basin",
                "so": (
                    "Narrows to one basin's publication history. Each basin is published on its"
                    " own cadence, so a mixed list orders by evaluation vintage across basins"
                    " and reads as a single history that never happened."
                ),
            },
            limit={
                "so": (
                    "Capped at 200. Publications are rare by construction — one per accepted"
                    " rebuild — so a long page here means the context was republished more"
                    " often than it was read, which is itself the finding."
                ),
            },
            cursor={
                "so": (
                    "Pins the page to publication-id order and to the basin filter that opened"
                    " it. Receipts are append-only, so what was on page two stays there."
                ),
            },
            explain={
                "glossary": "gt_derivation_handle",
                "so": (
                    "The list carries no figures — every value on it is an identity — so"
                    " `explain` returns an empty block here. The detail is where the"
                    " acceptance and support numbers live."
                ),
            },
            explain_depth={
                "glossary": "gt_derivation_handle",
                "so": "No effect on this operation; the list has no handles to walk.",
            },
        ),
    },
    responses=problem_responses(
        "validation_failed", "cursor_malformed", "cursor_query_mismatch", "service_degraded"
    ),
)
def list_modeling_publications(
    request: Request,
    connection: Connection,
    explain: ExplainEffect,
    cursor: Cursor = None,
    limit: SpineLimit = DEFAULT_LIMIT,
    basin: Annotated[str | None, Query(description="Filter to one basin.")] = None,
) -> JSONResponse:
    basin = basin or None  # `?basin=` is an unset filter, not a basin nothing matches
    fingerprint = query_fingerprint({"basin": basin})
    decoded = decode_cursor(cursor, fingerprint=fingerprint) if cursor is not None else None
    receipts = [
        record
        for record in served.accepted_publications(connection, basin=basin)
        if decoded is None or str(record["publication_id"]) > decoded.key
    ]
    receipts.sort(key=lambda record: str(record["publication_id"]))
    items, has_more = page(receipts, limit)
    next_cursor = (
        encode_cursor(
            key=str(items[-1]["publication_id"]),
            tiebreak=str(items[-1]["publication_id"]),
            as_of=items[-1]["eval_vintage"],
            fingerprint=fingerprint,
        )
        if has_more and items
        else None
    )
    return enveloped(
        request,
        [_row(record) for record in items],
        as_of=max((record["eval_vintage"] for record in items), default=None),
        next_cursor=next_cursor,
        links={
            "next": next_link(
                "/v1/modeling/publications", {"basin": basin, "limit": limit}, next_cursor
            )
            if next_cursor
            else None
        },
        explain=inline_for(connection, explain),
    )


@router.get(
    "/modeling/publications/{publication_id}",
    operation_id="get_modeling_publication",
    summary="One modeling publication",
    description=(
        "The whole acceptance receipt for one publication, plus the coverage document the"
        " control artifact was written with: which peer-ladder rung produced how many subject"
        " instances, which `control_unavailable` reasons were mentioned and how often, and the"
        " two acceptance gates with the thresholds they had to clear. Every figure here"
        " carries a handle minted against the pinned control derivation, so the numbers"
        " describing the artifact resolve to the artifact."
        " The filesystem location of the artifact is deliberately not served: a path is"
        " deployment information. `artifact_sha256` addresses the same bytes without it."
        " When a later publication supersedes this one the response says so and links it;"
        " both stay addressable, because a republication is a restatement, not an edit."
    ),
    response_model=EnvelopeModel[ModelingPublicationDetail],
    openapi_extra={
        **request_example(path={"publication_id": EXAMPLE_PUBLICATION_ID}),
        **semantics(
            publication_id={
                "glossary": "gt_recipe",
                "so": (
                    "A content address over the receipt document, so it names one immutable"
                    " acceptance and cannot be reused by a later build."
                ),
            },
            explain={
                "glossary": "gt_derivation_handle",
                "so": (
                    "Inlines the chain behind every acceptance and support figure. Each one"
                    " resolves to the pinned typecurve.build derivation, which is how the"
                    " coverage numbers are checkable against the artifact they describe."
                ),
            },
            explain_depth={
                "glossary": "gt_derivation_handle",
                "so": (
                    "Three reaches the control derivation and its immediate inputs. The"
                    " control's own chain is deeper than the default; raise it to eight to"
                    " walk through to the terminal manifests."
                ),
            },
        ),
    },
    responses=problem_responses(
        "not_found", "unregistered_artifact", "validation_failed", "service_degraded"
    ),
)
def get_modeling_publication(
    request: Request,
    connection: Connection,
    explain: ExplainEffect,
    publication_id: Annotated[
        str, Path(description="Publication receipt id.", pattern=PUBLICATION_PATTERN)
    ],
) -> JSONResponse:
    known = {
        str(record["publication_id"]): record
        for record in served.accepted_publications(connection)
    }
    if publication_id not in known:
        raise ProblemError("not_found", detail=f"no modeling publication {publication_id}")
    try:
        pin = served.resolve_pinned_control(connection, publication_id=publication_id)
        coverage = served.control_coverage(pin)
    except served.UnregisteredArtifact as error:
        raise ProblemError("unregistered_artifact", detail=str(error)) from error

    document = pin.receipt
    counts = coverage.get("counts", {})
    acceptance = coverage.get("acceptance", {})
    data = _row(known[publication_id]) | {
        "derivations": dict(document["derivations"]),
        "recipes": dict(document["recipes"]),
        "baseline": {key: str(value) for key, value in document["baseline"].items()},
        "environment": {key: str(value) for key, value in document["environment"].items()},
        "artifact_sha256": dict(document["artifact_sha256"]),
        "rows": dict(document["rows"]),
        "splits": [
            {
                "origin": item["origin"],
                "horizon_months": item["horizon_months"],
                "split_id": item["split_id"],
                "sha256": item["sha256"],
            }
            for item in document["splits"]
        ],
        "coverage": {
            "acceptance": {
                name: _gate(pin, name, block)
                for name, block in sorted(acceptance.items())
                if isinstance(block, dict) and "observed" in block
            },
            "support": {
                "fallback_by_level": {
                    level: _instances(pin, f"level={level}&col=fallback_by_level", count)
                    for level, count in sorted(
                        counts.get("fallback_by_level", {}).items()
                    )
                },
                "control_unavailable_reason_mentions": {
                    reason: _instances(
                        pin, f"col=unavailable_reason_mentions&reason={reason}", count
                    )
                    for reason, count in sorted(
                        counts.get("control_unavailable_reason_mentions", {}).items()
                    )
                },
                "test_subject_instances": _instances(
                    pin, "col=test_subject_instances", counts.get("test_subject_instances", 0)
                ),
                "subject_stream_instances": _instances(
                    pin,
                    "col=subject_stream_instances",
                    counts.get("subject_stream_instances", 0),
                ),
            },
            "control_contract": dict(coverage.get("control_contract", {})),
        },
        "supersedes": pin.superseded[0] if pin.superseded else None,
    }
    data = register_response_figures(
        connection,
        data,
        dataset=served.PUBLICATION_DATASET,
        operation_id="get_modeling_publication",
        locator=request.url.path,
        partition={"publication_id": publication_id},
        input_derivations=[
            pin.control_derivation_id,
            pin.model_dataset_derivation_id,
            pin.feature_derivation_id,
        ],
        correlation_id=request.state.request_id,
        rule_ids=list(CONTROL_RULES),
    )
    links: dict[str, str | None] = {
        "type_curves": "/v1/type-curves",
        **{rule: f"/v1/conformance/{rule}" for rule in CONTROL_RULES},
    }
    if pin.superseded:
        links["supersedes"] = f"/v1/modeling/publications/{pin.superseded[0]}"
    return enveloped(
        request,
        data,
        as_of=pin.eval_vintage,
        labels=PUBLICATION_LABELS,
        links=links,
        warnings=publication_warnings(pin, pointer="/publication_id"),
        explain=inline_for(connection, explain),
    )


def _instances(pin: served.PinnedControl, selector: str, count: Any) -> Any:
    return figure(
        str(int(count)),
        unit=INSTANCE_UNIT,
        derivation=pin.control_derivation_id,
        selector=f"publication_id={pin.publication_id}&{selector}",
    )


def _gate(pin: served.PinnedControl, name: str, block: dict[str, Any]) -> dict[str, Any]:
    return {
        "observed": figure(
            str(block["observed"]),
            unit=SHARE_UNIT,
            derivation=pin.control_derivation_id,
            selector=f"publication_id={pin.publication_id}&col=gate_observed&gate={name}",
        ),
        "minimum": block.get("minimum"),
        "maximum": block.get("maximum"),
        "status": str(block.get("status", "")),
    }


def publication_warnings(pin: served.PinnedControl, *, pointer: str) -> list[dict[str, str]]:
    """A republication restates every number, so both directions of the move are announced."""
    if pin.publication_id != pin.in_force:
        detail = (
            f"{pin.publication_id} is no longer the publication in force; {pin.in_force} is."
            " Both stay addressable, because a republication is a restatement and not an edit."
        )
    elif pin.superseded:
        detail = (
            f"{pin.publication_id} restates {pin.superseded[0]}. The prior publication is still"
            f" served under its own id — pass ?publication={pin.superseded[0]} to read the"
            " numbers a handle minted before this republication resolves to."
        )
    else:
        return []
    return [{"code": "publication_superseded", "detail": detail, "pointer": pointer}]
