"""The pinned tcv1.0 control, served per test subject. Backward-looking, never a forecast."""

from __future__ import annotations

from datetime import date
from enum import IntEnum
from typing import Annotated, Any, Literal

import polars as pl
from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import Connection, Cursor, ExplainEffect, Principal, SpineLimit
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
    decode_cursor,
    encode_cursor,
    next_link,
    page,
    query_fingerprint,
)
from glasswell.api.provenance import register_response_figures
from glasswell.api.rate_limit import consume_rate_limit
from glasswell.api.responses import EnvelopeModel, FigureModel, enveloped, inline_for, iso
from glasswell.api.routers.modeling import PUBLICATION_PATTERN, publication_warnings
from glasswell.api.routers.wells import API10_PATTERN
from glasswell.lineage.envelope import figure, series
from glasswell.modeling import served
from glasswell.modeling.type_curve import QUANTILE_CONVENTION, TC_MIN_N

router = APIRouter(tags=["wells"])

COUNT_UNIT = "wells"
LIQUIDS_BASIS = "oil+condensate"
RELATION = "control_type_curve_not_a_forecast"
QUANTILE_COLUMNS = (
    "monthly_p10",
    "monthly_p50",
    "monthly_p90",
    "cumulative_p10",
    "cumulative_p50",
    "cumulative_p90",
)
COUNT_COLUMNS = ("peer_count", "cumulative_peer_count")
UNITS = {
    ("oil", "typecurve_absolute"): "bbl",
    ("oil", "typecurve_per_kft"): "bbl/kft",
    ("gas", "typecurve_absolute"): "mcf",
    ("gas", "typecurve_per_kft"): "mcf/kft",
    ("water", "typecurve_absolute"): "bbl",
    ("water", "typecurve_per_kft"): "bbl/kft",
}
BASIS = {"oil": LIQUIDS_BASIS, "gas": None, "water": None}
CURVE_RULES = (
    "cr_tc_publication_scope_1",
    "cr_tc_peer_ladder_1",
    "cr_tc_normalization_1",
    "cr_tc_quantile_convention_1",
)
CURVE_LABELS = {
    "/fallback_level": "gt_peer_ladder",
    "/quantile_convention": "gt_quantile_convention",
    "/split_set_id": "gt_split_set",
    "/control_version": "gt_type_curve",
    "/cumulative_at_horizon": "gt_cum12_cum24",
    "/series/peer_count": "gt_training_support",
}

class TypeCurveHorizon(IntEnum):
    """A query parameter arrives as text, and Literal[int] does not coerce it."""

    twelve = 12
    twenty_four = 24


Stream = Literal["oil", "gas", "water"]
Normalization = Literal["typecurve_absolute", "typecurve_per_kft"]
Outcome = Literal["available", "control_unavailable"]


class AvailableOrigin(BaseModel):
    origin: date = Field(description="Rolling origin of a split this subject appears in.")
    horizon_months: int = Field(
        description="Horizon of that split.",
        json_schema_extra=not_a_figure(
            "Horizon of another persisted split for this subject, offered for navigation."
        ),
    )
    split_id: str = Field(description="Identity of that split object.")


class CumulativeBand(BaseModel):
    p10: FigureModel = Field(description="Low case at the horizon, statistical-ascending.")
    p50: FigureModel = Field(description="Median case at the horizon.")
    p90: FigureModel = Field(description="High case at the horizon.")


class TypeCurveSeries(BaseModel):
    month_index: list[int] = Field(
        description="Producing-month index, one to the split's horizon.",
        json_schema_extra=not_a_figure(
            "Producing-month index, the axis the curve is plotted against. It is the row key,"
            " not a value."
        ),
    )
    monthly_p10: list[float | None] = Field(description="Monthly low case.")
    monthly_p50: list[float | None] = Field(description="Monthly median case.")
    monthly_p90: list[float | None] = Field(description="Monthly high case.")
    cumulative_p10: list[float | None] = Field(description="Cumulative low case.")
    cumulative_p50: list[float | None] = Field(description="Cumulative median case.")
    cumulative_p90: list[float | None] = Field(description="Cumulative high case.")
    peer_count: list[int | None] = Field(description="Peers behind each monthly quantile.")
    cumulative_peer_count: list[int | None] = Field(
        description="Peers behind each cumulative quantile."
    )


class WellTypeCurve(BaseModel):
    api10: str = Field(
        description="Ten-digit API well number of the control subject.",
        json_schema_extra={
            GLOSSARY_KEY: "gt_api_10_api_12_api_14",
            **not_a_figure(
                "Identifier. A 10-digit API number is an identity string, not a measurement."
            ),
        },
    )
    outcome: Outcome = Field(
        description=(
            "available, or control_unavailable when the peer ladder terminated without a"
            " comparison set. Always present: an unavailable control is a stated value, never"
            " an absent one."
        )
    )
    relation: Literal["control_type_curve_not_a_forecast"] = Field(
        description="What these numbers are: a backward-looking peer aggregate."
    )
    publication_id: str = Field(description="Accepted publication the artifact was read from.")
    control_version: str = Field(
        description="Type-curve control version.",
        json_schema_extra={GLOSSARY_KEY: "gt_type_curve"},
    )
    dataset_version: str = Field(description="Model-ready dataset version.")
    feature_version: str = Field(description="Feature-set version.")
    split_set_id: str = Field(
        description="Content-addressed split bundle.",
        json_schema_extra={GLOSSARY_KEY: "gt_split_set"},
    )
    split_id: str = Field(description="The split that produced this instance.")
    split_sha256: str = Field(description="Content address of that split object.")
    origin: date = Field(description="Rolling origin of the split.")
    knowledge_cutoff: date = Field(
        description="Knowledge cut the split was built under.",
        json_schema_extra={GLOSSARY_KEY: "gt_knowledge_time"},
    )
    eval_vintage: date = Field(description="Evaluation vintage the control was pinned to.")
    horizon_months: int = Field(
        description="Months the curve runs to.",
        json_schema_extra=not_a_figure(
            "Horizon of the persisted temporal split this control was built on. A parameter of"
            " the split, not an observation the control stands behind."
        ),
    )
    stream: Stream = Field(
        description="Served stream.", json_schema_extra={GLOSSARY_KEY: "gt_stream"}
    )
    normalization: Normalization = Field(description="Which normalisation arm was served.")
    quantile_convention: str = Field(
        description="statistical_ascending: p10 is the low case.",
        json_schema_extra={GLOSSARY_KEY: "gt_quantile_convention"},
    )
    fallback_level: str = Field(
        description="The peer-ladder rung that produced this curve.",
        json_schema_extra={GLOSSARY_KEY: "gt_peer_ladder"},
    )
    control_unavailable_reasons: list[str] = Field(
        description="Why the ladder terminated, served verbatim. Empty when it did not."
    )
    peer_set_id: str | None = Field(description="Identity of the peer set, when one was found.")
    formation_group: str | None = Field(
        description="Formation group of the subject.",
        json_schema_extra={GLOSSARY_KEY: "gt_formation"},
    )
    area: str | None = Field(
        description="Area bucket of the subject.",
        json_schema_extra=not_a_figure(
            "Area bucket the subject falls in, a label the peer ladder groups by. A zero-padded"
            " code, not a measurement."
        ),
    )
    lateral_length_bucket: str | None = Field(description="Lateral-length bucket of the subject.")
    subject_lateral_length_ft: FigureModel | None = Field(
        description="The subject's own lateral length, which the per-kft arm rescales by."
    )
    cumulative_at_horizon: CumulativeBand | None = Field(
        description="The cum12 or cum24 band; null when the control did not resolve.",
        json_schema_extra={GLOSSARY_KEY: "gt_cum12_cum24"},
    )
    available_origins: list[AvailableOrigin] = Field(
        description="Every split instance the control holds for this subject."
    )
    series: TypeCurveSeries = Field(description="The month-indexed curve.")


@router.get(
    "/wells/{api10}/type-curve",
    operation_id="get_well_type_curve",
    summary="Type-curve control for one well",
    description=(
        "The pinned `tcv1.0` control for one held-out test subject: monthly and cumulative"
        " p10/p50/p90 curves indexed to the split's horizon, the peer-ladder rung that produced"
        " them, and the number of peers standing behind every month."
        " Quantiles are **statistical-ascending** — p10 is the low case — which is the opposite"
        " of the reserves convention in which P10 is the high case; `quantile_convention` says"
        " so on every response and `cr_tc_quantile_convention_1` records the decision."
        " `typecurve_per_kft` is the peer quantile per thousand lateral feet rescaled to this"
        " subject's own lateral length, so it is a length-adjusted volume rather than a rate"
        " per thousand feet (`cr_tc_normalization_1`)."
        " When the ladder terminated without a comparison set the answer is still a 200:"
        " `outcome` reads `control_unavailable`, the reasons are named, and the figure slots"
        " are present and null with their handles intact, so the absence resolves to the rung"
        " that produced it rather than to a value that does not exist."
        " This is a backward-looking aggregate over a held-out arm — `relation` says so — and"
        " it is not a forecast, a reserve or an EUR."
        " There is no `as_of`: the control is pinned to one evaluation vintage and has no"
        " effective-dated history, so offering one would imply a history that does not exist."
        " Use `publication` to read a prior publication's numbers instead."
        " A warm read of the artifact costs 10-13 ms; `explain=true&explain_depth=8` walks a"
        " chain roughly nine hundred derivations wide and is the expensive request here."
    ),
    response_model=EnvelopeModel[WellTypeCurve],
    openapi_extra={
        **request_example(
            path={"api10": EXAMPLE_API10}, query={"stream": "oil", "horizon": 24}
        ),
        **semantics(
            stream={
                "glossary": "gt_stream",
                "so": (
                    "One stream per request, on purpose: three at once is twenty handles, which"
                    " is exactly the inline-explain cap and a boundary nobody should sit on."
                ),
            },
            normalization={
                "so": (
                    "typecurve_absolute is the peer quantile as produced; typecurve_per_kft is"
                    " that quantile taken per thousand lateral feet and then rescaled to this"
                    " subject's length. The arms differ by the subject's lateral length in kft,"
                    " so reading one as the other is a factor-of-ten error on the Bakken."
                ),
            },
            horizon={
                "so": (
                    "Selects which persisted split answers, 12 or 24 months. It is not a window"
                    " on one curve: the two horizons are different splits with different"
                    " held-out arms, so their numbers are not two views of one thing."
                ),
            },
            origin={
                "glossary": "gt_knowledge_time",
                "so": (
                    "Selects the rolling origin. Omit it for the most recent origin this"
                    " subject has at the requested horizon; available_origins lists them all."
                ),
            },
            publication={
                "glossary": "gt_recipe",
                "so": (
                    "Pins the answer to one accepted publication. After a republication the"
                    " numbers move, and this is how a handle minted before it is reconciled"
                    " against one minted after — both stay served, neither is edited."
                ),
            },
            explain={
                "glossary": "gt_derivation_handle",
                "so": (
                    "Inlines the chain behind all twelve handles. Each resolves through the"
                    " api.respond derivation to the pinned typecurve.build derivation, whose"
                    " output partition carries the split set and whose output hash is the"
                    " artifact's, which is what makes the served curve traceable to its bytes."
                ),
            },
            explain_depth={
                "glossary": "gt_derivation_handle",
                "so": (
                    "Three is enough to reach the control derivation and its split hashes,"
                    " which sit at level one. The control's own chain runs deeper than that, so"
                    " the inlined block reports truncated until you raise this to eight."
                ),
            },
        ),
    },
    responses=problem_responses(
        "not_found", "unregistered_artifact", "validation_failed", "service_degraded"
    ),
)
def get_well_type_curve(
    request: Request,
    connection: Connection,
    explain: ExplainEffect,
    api10: Annotated[
        str, Path(description="Ten-digit API well number.", pattern=API10_PATTERN)
    ],
    stream: Annotated[Stream, Query(description="Served stream.")] = "oil",
    normalization: Annotated[
        Normalization, Query(description="Normalisation arm.")
    ] = "typecurve_absolute",
    horizon: Annotated[
        TypeCurveHorizon, Query(description="Split horizon in months.")
    ] = TypeCurveHorizon.twenty_four,
    origin: Annotated[date | None, Query(description="Rolling origin of the split.")] = None,
    publication: Annotated[
        str | None,
        Query(description="Pin to one publication.", pattern=PUBLICATION_PATTERN),
    ] = None,
) -> JSONResponse:
    pin = _pin(connection, publication)
    try:
        instances = served.subject_origins(pin, api10=api10)
    except served.UnregisteredArtifact as error:
        raise ProblemError("unregistered_artifact", detail=str(error)) from error
    if not instances:
        raise ProblemError(
            "not_found",
            detail=(
                f"{api10} is not a test subject of {pin.split_set_id} at eval vintage"
                f" {pin.eval_vintage.isoformat()}"
            ),
        )
    horizon_months = int(horizon)
    at_horizon = [item for item in instances if item[1] == horizon_months]
    resolved_origin = origin or (at_horizon[-1][0] if at_horizon else None)
    if resolved_origin is None or (resolved_origin, horizon_months) not in {
        (item[0], item[1]) for item in instances
    }:
        offered = ", ".join(
            f"{item[0].isoformat()}/{item[1]}m" for item in instances
        )
        raise ProblemError(
            "not_found",
            detail=(
                f"{api10} has no control instance at origin"
                f" {(origin or resolved_origin or '-')} and horizon {horizon_months}m;"
                f" it has {offered}"
            ),
        )
    try:
        frame = served.subject_frame(
            pin,
            api10=api10,
            stream=stream,
            normalization=normalization,
            origin=resolved_origin,
            horizon_months=horizon_months,
        )
    except served.UnregisteredArtifact as error:
        raise ProblemError("unregistered_artifact", detail=str(error)) from error
    if frame.is_empty():
        raise ProblemError(
            "not_found",
            detail=(
                f"{api10} has no {stream} control at"
                f" {resolved_origin.isoformat()}/{horizon_months}m"
            ),
        )

    head = frame.row(0, named=True)
    unit = UNITS[(stream, normalization)]
    basis = BASIS[stream]
    unavailable = head["fallback_level"] == "control_unavailable"
    reasons = served.reasons(head["control_unavailable_reasons"])
    key = (
        f"api10={api10}&split_id={head['split_id']}&stream={stream}"
        f"&normalization={normalization}"
    )
    data: dict[str, Any] = {
        "api10": api10,
        "outcome": "control_unavailable" if unavailable else "available",
        "relation": RELATION,
        "publication_id": pin.publication_id,
        "control_version": pin.control_version,
        "dataset_version": pin.dataset_version,
        "feature_version": pin.feature_version,
        "split_set_id": pin.split_set_id,
        "split_id": head["split_id"],
        "split_sha256": head["split_sha256"],
        "origin": iso(head["origin"]),
        "knowledge_cutoff": iso(head["knowledge_cutoff"]),
        "eval_vintage": iso(head["eval_vintage"]),
        "horizon_months": int(head["horizon_months"]),
        "stream": stream,
        "normalization": normalization,
        "quantile_convention": head["quantile_convention"] or QUANTILE_CONVENTION,
        "fallback_level": head["fallback_level"],
        "control_unavailable_reasons": list(reasons),
        "peer_set_id": head["peer_set_id"],
        "formation_group": head["formation_group"],
        "area": head["area"],
        "lateral_length_bucket": head["lateral_length_bucket"],
        "subject_lateral_length_ft": (
            figure(
                served.decimal_text(head["subject_lateral_length_ft"]),
                unit="ft",
                derivation=pin.control_derivation_id,
                selector=f"{key}&col=subject_lateral_length_ft",
            )
            if head["subject_lateral_length_ft"] is not None
            else None
        ),
        "cumulative_at_horizon": _band(frame, pin, key=key, unit=unit, basis=basis),
        "available_origins": [
            {
                "origin": item[0].isoformat(),
                "horizon_months": item[1],
                "split_id": item[2],
            }
            for item in instances
        ],
        "series": {
            "month_index": [int(value) for value in frame["month_index"]],
            **{
                column: series(
                    [served.decimal_text(value) for value in frame[column]],
                    unit=unit,
                    derivation=pin.control_derivation_id,
                    selector=f"{key}&col={column}",
                    basis=basis,
                )
                for column in QUANTILE_COLUMNS
            },
            **{
                column: series(
                    [None if value is None else int(value) for value in frame[column]],
                    unit=COUNT_UNIT,
                    derivation=pin.control_derivation_id,
                    selector=f"{key}&col={column}",
                )
                for column in COUNT_COLUMNS
            },
        },
    }
    rules = [*CURVE_RULES, *(["cr_tc_unavailable_vocab_1"] if unavailable else [])]
    data = register_response_figures(
        connection,
        data,
        dataset=served.TYPE_CURVE_DATASET,
        operation_id="get_well_type_curve",
        locator=request.url.path,
        partition={
            "api10": api10,
            "split_id": str(head["split_id"]),
            "stream": stream,
            "normalization": normalization,
            "publication_id": pin.publication_id,
        },
        input_derivations=[
            pin.control_derivation_id,
            pin.model_dataset_derivation_id,
            pin.feature_derivation_id,
        ],
        correlation_id=request.state.request_id,
        rule_ids=rules,
    )
    other_arm = (
        "typecurve_per_kft"
        if normalization == "typecurve_absolute"
        else "typecurve_absolute"
    )
    return enveloped(
        request,
        data,
        as_of=pin.eval_vintage,
        labels=CURVE_LABELS,
        warnings=_warnings(pin, head=head, frame=frame, unavailable=unavailable, reasons=reasons),
        links={
            "well": f"/v1/wells/{api10}",
            "publication": f"/v1/modeling/publications/{pin.publication_id}",
            f"normalization_{other_arm}": (
                f"/v1/wells/{api10}/type-curve?stream={stream}&horizon={horizon_months}"
                f"&normalization={other_arm}"
            ),
            **{rule: f"/v1/conformance/{rule}" for rule in rules},
        },
        explain=inline_for(connection, explain),
    )


def _pin(connection: Any, publication: str | None) -> served.PinnedControl:
    try:
        return served.resolve_pinned_control(connection, publication_id=publication)
    except served.UnregisteredArtifact as error:
        raise ProblemError("unregistered_artifact", detail=str(error)) from error


def _band(
    frame: pl.DataFrame,
    pin: served.PinnedControl,
    *,
    key: str,
    unit: str,
    basis: str | None,
) -> dict[str, Any] | None:
    """The cum12 or cum24 value: the cumulative row at the horizon, as three addressable
    figures. Null as a whole object when the control did not resolve, because a figure's
    value is not nullable."""
    last = frame.row(frame.height - 1, named=True)
    if any(last[f"cumulative_p{level}"] is None for level in ("10", "50", "90")):
        return None
    return {
        f"p{level}": figure(
            served.decimal_text(last[f"cumulative_p{level}"]),
            unit=unit,
            derivation=pin.control_derivation_id,
            selector=f"{key}&col=cumulative_at_horizon_p{level}",
            basis=basis,
        )
        for level in ("10", "50", "90")
    }


def _warnings(
    pin: served.PinnedControl,
    *,
    head: dict[str, Any],
    frame: pl.DataFrame,
    unavailable: bool,
    reasons: tuple[str, ...],
) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    if unavailable:
        found.append(
            {
                "code": "control_unavailable",
                "detail": (
                    "The peer ladder terminated without a comparison set for this subject:"
                    f" {', '.join(reasons) or 'no reason was recorded'}. The figure slots are"
                    " served with null values so the absence is addressable."
                ),
                "pointer": "/outcome",
            }
        )
    elif head["fallback_level"] != "formation_area_length":
        found.append(
            {
                "code": "control_fallback_rung",
                "detail": (
                    f"The peers behind this curve are a {head['fallback_level']} set, not the"
                    " first rung: the comparison is broader than formation, area and length"
                    " together. cr_tc_peer_ladder_1 records the ladder."
                ),
                "pointer": "/fallback_level",
            }
        )
    floor = min(
        (int(value) for value in frame["peer_count"] if value is not None),
        default=None,
    )
    if not unavailable and floor is not None and floor < TC_MIN_N:
        found.append(
            {
                "code": "control_peer_floor",
                "detail": (
                    f"At least one month rests on {floor} peers, under the {TC_MIN_N} the"
                    " ladder requires for a rung. The rung was taken on a wider month."
                ),
                "pointer": "/series/peer_count",
            }
        )
    return [*found, *publication_warnings(pin, pointer="/publication_id")]


class TypeCurveIndexSeries(BaseModel):
    api10: list[str] = Field(
        description="Subject of each control instance on this page — the row axis.",
        json_schema_extra={
            GLOSSARY_KEY: "gt_api_10_api_12_api_14",
            **not_a_figure("Identifier, on the row axis of an aligned-array page."),
        },
    )
    origin: list[date] = Field(
        description="Rolling origin of each instance's split.",
        json_schema_extra={GLOSSARY_KEY: "gt_vintage_well_vintage"},
    )
    split_id: list[str] = Field(
        description="Split that produced each instance.",
        json_schema_extra={GLOSSARY_KEY: "gt_split_set"},
    )
    fallback_level: list[str] = Field(
        description="Peer-ladder rung each instance resolved to.",
        json_schema_extra={GLOSSARY_KEY: "gt_peer_ladder"},
    )
    control_unavailable_reasons: list[list[str]] = Field(
        description="Why the ladder terminated, per instance. Empty where it did not."
    )
    formation_group: list[str | None] = Field(
        description="Formation group of each subject.",
        json_schema_extra={GLOSSARY_KEY: "gt_formation"},
    )
    area: list[str | None] = Field(
        description="Area bucket of each subject.",
        json_schema_extra=not_a_figure("Area bucket, in an aligned-array page."),
    )
    lateral_length_bucket: list[str | None] = Field(
        description="Lateral-length bucket of each subject."
    )
    peer_count: list[int | None] = Field(
        description="Peers behind the monthly quantile at the horizon.",
        json_schema_extra={GLOSSARY_KEY: "gt_training_support"},
    )
    cumulative_peer_count: list[int | None] = Field(
        description="Peers behind the cumulative quantile at the horizon.",
        json_schema_extra={GLOSSARY_KEY: "gt_training_support"},
    )


class TypeCurveIndex(BaseModel):
    publication_id: str = Field(description="Accepted publication this page was read from.")
    stream: Stream = Field(description="Served stream.")
    normalization: Normalization = Field(description="Normalisation arm in force.")
    horizon_months: int = Field(
        description="Horizon the page reports at.",
        json_schema_extra=not_a_figure(
            "Horizon of the persisted temporal split this control was built on. A parameter of"
            " the split, not an observation the control stands behind."
        ),
    )
    origin_requested: date | None = Field(
        description="Origin filter in force, when one was supplied. The per-row origin is in"
        " the series; this is the facet, and it is named apart so the two cannot be read as"
        " one pointer."
    )
    relation: Literal["control_type_curve_not_a_forecast"] = Field(
        description="What these rows describe: a backward-looking peer aggregate."
    )
    quantile_convention: str = Field(
        description="statistical_ascending, the convention every detail curve is served under.",
        json_schema_extra={GLOSSARY_KEY: "gt_quantile_convention"},
    )
    series: TypeCurveIndexSeries = Field(description="One page of aligned per-instance arrays.")


# Keyed by the response pointer `grid/rows.ts::responsePointerFor` composes: the axis and the
# projected figures are series-namespace, every other column resolves element-relative.
INDEX_LABELS = {
    "/series/api10": "gt_api_10_api_12_api_14",
    "/series/peer_count": "gt_training_support",
    "/origin": "gt_vintage_well_vintage",
    "/split_id": "gt_split_set",
    "/fallback_level": "gt_peer_ladder",
    "/control_unavailable_reasons": "gt_peer_ladder",
    "/formation_group": "gt_formation",
}
INDEX_RULES = (
    "cr_tc_publication_scope_1",
    "cr_tc_peer_ladder_1",
    "cr_tc_unavailable_vocab_1",
)
TYPE_CURVE_INDEX_REQUESTS_PER_MINUTE = 30


@router.get(
    "/type-curves",
    operation_id="list_type_curves",
    summary="Browse the control population",
    description=(
        "The pinned control's test subjects at their horizon, one row per subject instance,"
        " with the peer-ladder rung that produced it, the `control_unavailable` reasons where"
        " the ladder terminated, and the peer support behind both the monthly and the"
        " cumulative quantile."
        " Volumes are deliberately absent here: a rollup states its support distribution and"
        " the assumption in force and sends the reader to the detail for the number, which is"
        " `/v1/wells/{api10}/type-curve`."
        " Subjects whose control did not resolve are listed with their reasons rather than"
        " dropped, so the served population is the whole test population and a coverage number"
        " taken off this page is not quietly short by the unavailable share."
        " The two support columns are page-level series: one page mints two evidence rows"
        " rather than two per subject, and the page key is part of the response derivation's"
        " identity so page one and page two are different derivations rather than one"
        " derivation with two disagreeing answers."
    ),
    response_model=EnvelopeModel[TypeCurveIndex],
    openapi_extra={
        **request_example(query={"stream": "oil", "limit": 5}),
        **dataset(
            id="type_curves",
            title="Type curves (control)",
            group="wells",
            collection_pointer="",
            series_pointer="/series",
            # Only the two real figures are projected columns. `grid/columns.ts::classify`
            # types every pointer in this list as a figure unconditionally, so a label
            # declared here renders as a number with no handle and wears the naked-number
            # badge. The label arrays stay in `/series` and `grid/rows.ts::cellFor` still
            # resolves them per row, which is how `production` carries its own labels.
            row_projection={
                "axis": "/api10",
                "columns": ["/peer_count", "/cumulative_peer_count"],
                "suffixes": [],
            },
            anchors=["/publication_id", "/horizon_months", "/quantile_convention"],
            # Composite on purpose: a row is one subject at one origin, and api10 alone is
            # not unique when the origin facet is open. It also keeps the explorer's api10
            # hop pointed at the well rather than at its type curve.
            row_id=["/api10", "/origin"],
            detail_operation="get_well_type_curve",
            facets=[
                "stream",
                "normalization",
                "horizon",
                "origin",
                "fallback_level",
                "formation_group",
            ],
            columns={
                "default": [
                    "/api10",
                    "/origin",
                    "/fallback_level",
                    "/control_unavailable_reasons",
                    "/formation_group",
                    "/split_id",
                    "/peer_count",
                ],
                "sort": "/api10",
            },
            intro="nb_dataset_type_curves",
            order=15,
        ),
        **semantics(
            stream={
                "glossary": "gt_stream",
                "so": (
                    "The population is the same wells whichever stream you ask for; what"
                    " changes is which stream's peer support stands behind them, and a subject"
                    " can be well supported in oil and thin in gas."
                ),
            },
            normalization={
                "so": (
                    "Carried so the page says which arm the detail link will open in. The"
                    " support counts are the same on both arms; the volumes, which live on the"
                    " detail, are not."
                ),
            },
            horizon={
                "so": (
                    "Selects which persisted split the page reports, 12 or 24 months. The two"
                    " horizons hold out different wells, so their populations are not"
                    " subsets of one another."
                ),
            },
            origin={
                "glossary": "gt_vintage_well_vintage",
                "so": (
                    "Narrows to one rolling origin. Omit it and a subject appears once per"
                    " origin it was held out at, which is the honest shape: those are separate"
                    " evaluations, not repeats of one."
                ),
            },
            fallback_level={
                "glossary": "gt_peer_ladder",
                "so": (
                    "The audit filter. Narrowing to formation_basin or control_unavailable"
                    " lists exactly the subjects whose comparison set was weakest, which is the"
                    " population a coverage claim is most likely to be wrong about."
                ),
            },
            formation_group={
                "glossary": "gt_formation",
                "so": (
                    "Narrows to one formation group, which is the first rung of the peer"
                    " ladder and therefore the coarsest honest way to compare two subjects."
                ),
            },
            publication={
                "glossary": "gt_recipe",
                "so": (
                    "Pins the page to one accepted publication. A cursor carries the"
                    " publication it was opened under, so a republication invalidates the"
                    " cursor rather than silently paging across two populations."
                ),
            },
            limit={
                "so": (
                    "Capped at 200. The control's test arm is thousands of subject instances,"
                    " so this collection is paged rather than counted in one call."
                ),
            },
            cursor={
                "so": (
                    "Pins the page to API-10 order, to the facet set that opened it and to the"
                    " publication in force. The page key is also part of the response"
                    " derivation's identity, so page two carries its own evidence."
                ),
            },
            explain={
                "glossary": "gt_derivation_handle",
                "so": (
                    "Two handles per page, one per support column, each resolving to the"
                    " pinned control derivation. The per-subject volumes are on the detail, so"
                    " this stays two chains however long the page is."
                ),
            },
            explain_depth={
                "glossary": "gt_derivation_handle",
                "so": (
                    "Three reaches the control derivation and its split hashes. Raise it to"
                    " eight for the terminal manifests."
                ),
            },
        ),
    },
    responses=problem_responses(
        "not_found",
        "unregistered_artifact",
        "validation_failed",
        "cursor_malformed",
        "cursor_query_mismatch",
        "rate_limited",
        "service_degraded",
    ),
)
def list_type_curves(
    request: Request,
    connection: Connection,
    principal: Principal,
    explain: ExplainEffect,
    cursor: Cursor = None,
    limit: SpineLimit = DEFAULT_LIMIT,
    stream: Annotated[Stream, Query(description="Served stream.")] = "oil",
    normalization: Annotated[
        Normalization, Query(description="Normalisation arm.")
    ] = "typecurve_absolute",
    horizon: Annotated[
        TypeCurveHorizon, Query(description="Split horizon in months.")
    ] = TypeCurveHorizon.twenty_four,
    origin: Annotated[date | None, Query(description="Filter to one rolling origin.")] = None,
    fallback_level: Annotated[
        str | None, Query(description="Filter to one peer-ladder rung.")
    ] = None,
    formation_group: Annotated[
        str | None, Query(description="Filter to one formation group.")
    ] = None,
    publication: Annotated[
        str | None,
        Query(description="Pin to one publication.", pattern=PUBLICATION_PATTERN),
    ] = None,
) -> JSONResponse:
    consume_rate_limit(
        connection,
        principal,
        operation="list_type_curves",
        limit=TYPE_CURVE_INDEX_REQUESTS_PER_MINUTE,
    )
    # Normalised once, here, and never again: `?fallback_level=` binds to "", which is falsy
    # but not None. Guarding the partition and the selector on truthiness while filtering on
    # `is not None` made the empty arm mint one derivation id for two different pages, and a
    # derivation row is immutable — a single read-scope request poisoned the default page for
    # good. The three sites can only agree if the value reaching them is already one thing.
    fallback_level = fallback_level or None
    formation_group = formation_group or None
    pin = _pin(connection, publication)
    horizon_months = int(horizon)
    facets = {
        "stream": stream,
        "normalization": normalization,
        "horizon": horizon_months,
        "origin": origin,
        "fallback_level": fallback_level,
        "formation_group": formation_group,
        "publication_id": pin.publication_id,
    }
    fingerprint = query_fingerprint(facets)
    decoded = decode_cursor(cursor, fingerprint=fingerprint) if cursor is not None else None
    after_api10 = decoded.key if decoded is not None else None
    # A row is (subject, origin), so the cursor is too. The tiebreak was encoded and never
    # read, which dropped the remaining origins of any subject a page boundary landed inside.
    after_origin = (
        date.fromisoformat(decoded.tiebreak)
        if decoded is not None and decoded.tiebreak
        else None
    )
    try:
        found = served.index_page(
            pin,
            stream=stream,
            normalization=normalization,
            horizon_months=horizon_months,
            origin=origin,
            fallback_level=fallback_level,
            formation_group=formation_group,
            after_api10=after_api10,
            after_origin=after_origin,
            limit=limit,
        )
    except served.UnregisteredArtifact as error:
        raise ProblemError("unregistered_artifact", detail=str(error)) from error
    items, has_more = page(list(found.iter_rows(named=True)), limit)
    next_cursor = (
        encode_cursor(
            key=str(items[-1]["subject_api10"]),
            tiebreak=items[-1]["origin"].isoformat(),
            as_of=pin.eval_vintage,
            fingerprint=fingerprint,
        )
        if has_more and items
        else None
    )
    selector_facets = "".join(
        f"&{name}={value}"
        for name, value in (
            ("origin", origin.isoformat() if origin else None),
            ("fallback_level", fallback_level),
            ("formation_group", formation_group),
            ("after_api10", after_api10),
            ("after_origin", after_origin.isoformat() if after_origin else None),
        )
        if value
    )
    key = (
        f"publication_id={pin.publication_id}&stream={stream}"
        f"&normalization={normalization}&horizon={horizon_months}&limit={limit}"
        f"{selector_facets}"
    )
    data: dict[str, Any] = {
        "publication_id": pin.publication_id,
        "stream": stream,
        "normalization": normalization,
        "horizon_months": horizon_months,
        "origin_requested": iso(origin),
        "relation": RELATION,
        "quantile_convention": QUANTILE_CONVENTION,
        "series": {
            "api10": [str(row["subject_api10"]) for row in items],
            "origin": [iso(row["origin"]) for row in items],
            "split_id": [str(row["split_id"]) for row in items],
            "fallback_level": [str(row["fallback_level"]) for row in items],
            "control_unavailable_reasons": [
                list(served.reasons(row["control_unavailable_reasons"])) for row in items
            ],
            "formation_group": [row["formation_group"] for row in items],
            "area": [row["area"] for row in items],
            "lateral_length_bucket": [row["lateral_length_bucket"] for row in items],
            **{
                column: series(
                    [None if row[column] is None else int(row[column]) for row in items],
                    unit=COUNT_UNIT,
                    derivation=pin.control_derivation_id,
                    selector=f"{key}&col={column}",
                )
                for column in COUNT_COLUMNS
            },
        },
    }
    # The page key belongs in the partition: derivation_id addresses the output spec, params
    # are fixed to the operation id, and the partition is the only caller-controlled
    # discriminator. Without it page one and page two mint one id with two disagreeing arrays.
    partition = {
        "publication_id": pin.publication_id,
        "stream": stream,
        "normalization": normalization,
        "horizon": str(horizon_months),
        "limit": str(limit),
        **({"origin": origin.isoformat()} if origin else {}),
        **({"fallback_level": fallback_level} if fallback_level else {}),
        **({"formation_group": formation_group} if formation_group else {}),
        **({"after_api10": after_api10} if after_api10 else {}),
        **({"after_origin": after_origin.isoformat()} if after_origin else {}),
    }
    data = register_response_figures(
        connection,
        data,
        dataset=served.TYPE_CURVE_INDEX_DATASET,
        operation_id="list_type_curves",
        locator=request.url.path,
        partition=partition,
        input_derivations=[
            pin.control_derivation_id,
            pin.model_dataset_derivation_id,
            pin.feature_derivation_id,
        ],
        correlation_id=request.state.request_id,
        rule_ids=list(INDEX_RULES),
    )
    query = {
        "stream": stream,
        "normalization": normalization,
        "horizon": horizon_months,
        "origin": iso(origin),
        "fallback_level": fallback_level,
        "formation_group": formation_group,
        "publication": publication,
        "limit": limit,
    }
    return enveloped(
        request,
        data,
        as_of=pin.eval_vintage,
        labels=INDEX_LABELS,
        next_cursor=next_cursor,
        warnings=publication_warnings(pin, pointer="/publication_id"),
        links={
            "publication": f"/v1/modeling/publications/{pin.publication_id}",
            **{rule: f"/v1/conformance/{rule}" for rule in INDEX_RULES},
            "next": next_link("/v1/type-curves", query, next_cursor) if next_cursor else None,
        },
        explain=inline_for(connection, explain),
    )
