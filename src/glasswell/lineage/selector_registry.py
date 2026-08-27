"""Dataset-specific selector cardinality checks for served figure handles."""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import psycopg

from glasswell.lineage.errors import InvalidSelector, LineageUnresolved
from glasswell.lineage.ids import parse_selector

NEIGHBOR_DATASET = "marts.nd_neighbors"
COMPLETION_ANCHOR_DATASET = "canonical.well_completion_anchors"
PRODUCTION_DATASET = "canonical.production_monthly"

_EDGE_COLUMNS = frozenset(
    {
        "distance_m",
        "distance_epsg",
        "subject_geom_key",
        "neighbor_geom_key",
        "snapshot_vintage",
    }
)
_SUBJECT_COLUMNS = frozenset(
    {
        "completion_date",
        "formation_id",
        "formation_group",
        "formation_status",
        "formation_pools",
        "formation_month",
        "lateral_component_count",
        "snapshot_vintage",
    }
)
_ANCHOR_COLUMNS = frozenset({"completion_date", "job_start_date"})
_COMPLETION_COLUMNS = frozenset(
    {"pool_reported", "report_vintage", "production_month", "effective_from"}
)
_NEIGHBOR_COVERAGE_METRICS = frozenset(
    {
        "spatial_candidates",
        "missing_completion_anchor",
        "on_or_after_cut",
        "formation_conflicts",
        "formation_unavailable",
        "eligible",
        "returned",
    }
)


def validate_selector(
    connection: psycopg.Connection,
    derivation: Mapping[str, Any],
    selector: str,
    *,
    handle: str,
) -> None:
    """Require a declared selector to identify one row/column for registered datasets."""
    pairs = parse_selector(selector)
    terms = dict(pairs)
    dataset = derivation["output_dataset"]
    if dataset == NEIGHBOR_DATASET:
        _validate_neighbor(connection, derivation, terms, handle=handle)
    elif dataset == COMPLETION_ANCHOR_DATASET and (
        "disclosure_id" in terms or "disclosure_id_b64" in terms
    ):
        _validate_completion_anchor(connection, derivation, terms, handle=handle)
    elif dataset == PRODUCTION_DATASET and (
        "completion_key" in terms or "completion_key_b64" in terms
    ):
        _validate_completion_pool(connection, derivation, terms, handle=handle)


def _validate_neighbor(
    connection: psycopg.Connection,
    derivation: Mapping[str, Any],
    terms: dict[str, str],
    *,
    handle: str,
) -> None:
    if "metric" in terms:
        _validate_neighbor_coverage(connection, derivation, terms, handle=handle)
        return
    column = terms.pop("col", None)
    if column is None:
        raise InvalidSelector(f"{NEIGHBOR_DATASET} selectors require col")

    if set(terms) == {"api10", "neighbor_api10"}:
        if column not in _EDGE_COLUMNS:
            raise InvalidSelector(f"{column!r} is not a selectable ND neighbour edge column")
        statement = (
            "select count(*) from marts.nd_neighbor_edges"
            " where derivation_id = %s and api10 = %s and neighbor_api10 = %s"
        )
        parameters = (derivation["derivation_id"], terms["api10"], terms["neighbor_api10"])
    elif set(terms) == {"api10"}:
        if column not in _SUBJECT_COLUMNS:
            raise InvalidSelector(f"{column!r} is not a selectable ND neighbour subject column")
        statement = (
            "select count(*) from marts.nd_neighbor_subjects"
            " where derivation_id = %s and api10 = %s"
        )
        parameters = (derivation["derivation_id"], terms["api10"])
    else:
        raise InvalidSelector(
            f"{NEIGHBOR_DATASET} selectors require api10 and optional neighbor_api10 plus col"
        )

    _require_one(connection, statement, parameters, derivation=derivation, handle=handle)


def _validate_neighbor_coverage(
    connection: psycopg.Connection,
    derivation: Mapping[str, Any],
    terms: dict[str, str],
    *,
    handle: str,
) -> None:
    metric = terms.pop("metric", None)
    if metric not in _NEIGHBOR_COVERAGE_METRICS:
        raise InvalidSelector(f"{metric!r} is not a selectable ND neighbour coverage metric")
    api10 = terms.pop("api10", "")
    radius_m = terms.pop("radius_m", "")
    at_date = terms.pop("at_date", "")
    formation_id = terms.pop("formation_id", None)
    limit = terms.pop("limit", None)
    after_distance = terms.pop("after_distance_m", None)
    after_api10 = terms.pop("after_api10", None)
    if terms or not re.fullmatch(r"33[0-9]{8}", api10):
        raise InvalidSelector("ND neighbour coverage selector has invalid keys or API-10")
    try:
        parsed_radius = Decimal(radius_m)
        parsed_date = date.fromisoformat(at_date)
    except (InvalidOperation, ValueError):
        raise InvalidSelector("ND neighbour coverage selector has invalid radius or date") from None
    if parsed_radius <= 0 or parsed_date.isoformat() != at_date:
        raise InvalidSelector("ND neighbour coverage selector has invalid radius or date")
    if formation_id is not None and not re.fullmatch(r"[a-z0-9_]{1,64}", formation_id):
        raise InvalidSelector("ND neighbour coverage selector has invalid formation_id")
    if metric == "returned":
        if limit is None or not limit.isdigit() or not 1 <= int(limit) <= 200:
            raise InvalidSelector("returned coverage selector requires a valid limit")
        if (after_distance is None) != (after_api10 is None):
            raise InvalidSelector("returned coverage selector has an incomplete cursor position")
        if after_distance is not None:
            try:
                Decimal(after_distance)
            except InvalidOperation:
                raise InvalidSelector("returned coverage selector has invalid distance") from None
            if re.fullmatch(r"33[0-9]{8}", str(after_api10)) is None:
                raise InvalidSelector("returned coverage selector has invalid API-10")
    elif limit is not None or after_distance is not None or after_api10 is not None:
        raise InvalidSelector("only returned coverage accepts page terms")
    _require_one(
        connection,
        "select count(*) from marts.nd_neighbor_subjects"
        " where derivation_id = %s and api10 = %s",
        (derivation["derivation_id"], api10),
        derivation=derivation,
        handle=handle,
    )


def _validate_completion_anchor(
    connection: psycopg.Connection,
    derivation: Mapping[str, Any],
    terms: dict[str, str],
    *,
    handle: str,
) -> None:
    column = terms.pop("col", None)
    if column not in _ANCHOR_COLUMNS:
        raise InvalidSelector(f"{column!r} is not a selectable completion-anchor column")
    disclosure_id = _identity(terms, "disclosure_id")
    if terms:
        raise InvalidSelector("completion-anchor selectors require disclosure_id plus col")
    _require_one(
        connection,
        "select count(*) from canonical.well_completion_anchors"
        " where derivation_id = %s and disclosure_id = %s",
        (derivation["derivation_id"], disclosure_id),
        derivation=derivation,
        handle=handle,
    )


def _validate_completion_pool(
    connection: psycopg.Connection,
    derivation: Mapping[str, Any],
    terms: dict[str, str],
    *,
    handle: str,
) -> None:
    column = terms.pop("col", None)
    if column not in _COMPLETION_COLUMNS:
        raise InvalidSelector(f"{column!r} is not a selectable completion-pool column")
    completion_key = _identity(terms, "completion_key")
    pod_id = _optional_identity(terms, "pod_id")
    production_month = terms.pop("pm", None)
    effective_from = terms.pop("effective_from", None)
    if production_month is not None and effective_from is not None:
        raise InvalidSelector("completion-pool selector cannot combine pm and effective_from")
    if terms:
        raise InvalidSelector(
            "completion-pool selectors require completion_key, col, one time key, and optional"
            " pod_id"
        )

    statement = (
        "select count(*) from canonical.well_completions"
        " where derivation_id = %s and completion_key = %s"
    )
    parameters: list[object] = [derivation["derivation_id"], completion_key]
    if production_month is not None:
        try:
            parsed_month = date.fromisoformat(f"{production_month}-01")
        except ValueError:
            raise InvalidSelector("pm must be YYYY-MM") from None
        if parsed_month.strftime("%Y-%m") != production_month:
            raise InvalidSelector("pm must be YYYY-MM")
        statement += " and production_month = %s"
        parameters.append(parsed_month)
    elif effective_from is not None:
        try:
            parsed_effective = date.fromisoformat(effective_from)
        except ValueError:
            raise InvalidSelector("effective_from must be YYYY-MM-DD") from None
        if parsed_effective.isoformat() != effective_from:
            raise InvalidSelector("effective_from must be YYYY-MM-DD")
        statement += " and effective_from = %s"
        parameters.append(parsed_effective)
    if pod_id is None:
        statement += " and pod_id is null"
    else:
        statement += " and pod_id = %s"
        parameters.append(pod_id)
    _require_one(
        connection,
        statement,
        tuple(parameters),
        derivation=derivation,
        handle=handle,
    )


def _identity(terms: dict[str, str], name: str) -> str:
    value = _optional_identity(terms, name)
    if value is None:
        raise InvalidSelector(f"selector requires {name} or {name}_b64")
    return value


def _optional_identity(terms: dict[str, str], name: str) -> str | None:
    plain = terms.pop(name, None)
    encoded = terms.pop(f"{name}_b64", None)
    if plain is not None and encoded is not None:
        raise InvalidSelector(f"selector cannot combine {name} and {name}_b64")
    if encoded is None:
        return plain
    if len(encoded) > 4096:
        raise InvalidSelector(f"{name}_b64 is too long")
    try:
        decoded = base64.b64decode(
            encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True
        ).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise InvalidSelector(f"{name}_b64 is not strict URL-safe base64 UTF-8") from None
    if not decoded or len(decoded) > 2048:
        raise InvalidSelector(f"decoded {name}_b64 has invalid length")
    return decoded


def _require_one(
    connection: psycopg.Connection,
    statement: str,
    parameters: tuple[object, ...],
    *,
    derivation: Mapping[str, Any],
    handle: str,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(statement, parameters)
        matches = int(cursor.fetchone()[0])
    if matches == 0:
        raise LineageUnresolved(
            handle,
            reason="unknown_id",
            last_resolved=derivation["derivation_id"],
        )
    if matches != 1:
        raise InvalidSelector(f"selector identifies {matches} rows; exactly one is required")
