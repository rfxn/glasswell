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
from glasswell.lineage.ids import format_selector, parse_selector
from glasswell.lineage.jurisdictions import (
    NEIGHBORS_SCOPE,
    JurisdictionRegistry,
    load_jurisdictions,
)
from glasswell.lineage.serialization import hash_payload

NEIGHBOR_DATASET = "marts.nd_neighbors"

PRODUCTION_PROFILE = "production_series"
COMPLETION_POOL_PROFILE = "completion_pool"
COMPLETION_ANCHOR_PROFILE = "completion_anchor"
COMPLETION_DESIGN_PROFILE = "completion_design"
WELL_PROFILE = "well"
WELL_CUMULATIVE_PROFILE = "well_cumulative"
BASIN_CONTEXT_PROFILE = "basin_context"
NEIGHBOR_PROFILE = "nd_neighbor"
RESPONSE_PROFILE = "response_output"

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
_PRODUCTION_COLUMNS = {"oil_bbl": "oil", "gas_mcf": "gas", "water_bbl": "water"}
_WELL_COLUMNS = frozenset({"total_depth_ft"})
# Every column of the basin block the card renders as a line of its own. The classes are here
# with the values they class: `outside_published_boundaries` is an answer, and an answer a
# reader cannot resolve to the run that produced it is the naked number rule's own case.
_BASIN_CONTEXT_COLUMNS = frozenset(
    {
        "basin_name",
        "basin_class",
        "play_name",
        "play_class",
        "basin_label_filed",
        "label_class",
        "label_agrees",
        "boundary_vintage",
        "geometry_basis",
        "basin_overlap",
    }
)
_COMPLETION_DESIGN_COLUMNS = frozenset({"base_water_volume"})
_CUMULATIVE_COLUMNS = frozenset({"cum_volume", "coverage"})
_CUMULATIVE_STREAMS = frozenset({"liquid", "gas", "water"})
_KNOWN_PROFILES = frozenset(
    {
        PRODUCTION_PROFILE,
        COMPLETION_POOL_PROFILE,
        COMPLETION_ANCHOR_PROFILE,
        COMPLETION_DESIGN_PROFILE,
        WELL_PROFILE,
        WELL_CUMULATIVE_PROFILE,
        BASIN_CONTEXT_PROFILE,
        NEIGHBOR_PROFILE,
        RESPONSE_PROFILE,
    }
)
_PLAIN_IDENTITY = re.compile(r"\A[A-Za-z0-9_.:+-]+\Z")


def validate_selector(
    connection: psycopg.Connection,
    derivation: Mapping[str, Any],
    selector: str,
    *,
    handle: str,
    profiles: tuple[str, ...] | None = None,
    response_outputs: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    """Require a registered selector profile to prove the addressed output."""
    pairs = parse_selector(selector)
    terms = dict(pairs)
    registered = profiles
    if registered is None:
        registered = _registered_profiles(connection, derivation)
    unknown = sorted(set(registered) - _KNOWN_PROFILES)
    if unknown:
        raise InvalidSelector(f"selector registry contains unknown profiles: {unknown}")
    matching = [profile for profile in registered if _profile_matches(profile, terms)]
    if len(matching) != 1:
        raise InvalidSelector(
            f"no unique registered selector profile accepts {selector!r} for"
            f" {derivation['operation']} -> {derivation['output_dataset']}"
        )

    profile = matching[0]
    if profile == NEIGHBOR_PROFILE:
        _validate_neighbor(connection, derivation, terms, handle=handle)
    elif profile == COMPLETION_ANCHOR_PROFILE:
        _validate_completion_anchor(connection, derivation, terms, handle=handle)
    elif profile == COMPLETION_DESIGN_PROFILE:
        _validate_completion_design(connection, derivation, terms, handle=handle)
    elif profile == WELL_CUMULATIVE_PROFILE:
        _validate_well_cumulative(connection, derivation, terms, handle=handle)
    elif profile == COMPLETION_POOL_PROFILE:
        _validate_completion_pool(connection, derivation, terms, handle=handle)
    elif profile == PRODUCTION_PROFILE:
        _validate_production(connection, derivation, terms, handle=handle)
    elif profile == WELL_PROFILE:
        _validate_well(connection, derivation, terms, handle=handle)
    elif profile == BASIN_CONTEXT_PROFILE:
        _validate_basin_context(connection, derivation, terms, handle=handle)
    else:
        _validate_response_output(connection, derivation, pairs, outputs=response_outputs)


def _registered_profiles(
    connection: psycopg.Connection, derivation: Mapping[str, Any]
) -> tuple[str, ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select selector_profile from lineage.selector_output_registry"
            " where operation = %s and output_dataset = %s order by selector_profile",
            (derivation["operation"], derivation["output_dataset"]),
        )
        return tuple(row[0] for row in cursor.fetchall())


def _profile_matches(profile: str, terms: Mapping[str, str]) -> bool:
    keys = set(terms)
    if profile == NEIGHBOR_PROFILE:
        return "api10" in keys
    # The anchor and design predicates are identical on purpose: both address one FracFocus
    # disclosure, and profiles are looked up per (operation, output_dataset), which are
    # different tables. They can never both be registered for one lookup.
    if profile in (COMPLETION_ANCHOR_PROFILE, COMPLETION_DESIGN_PROFILE):
        return bool(keys & {"disclosure_id", "disclosure_id_b64"})
    if profile == WELL_CUMULATIVE_PROFILE:
        return bool(keys & {"api10", "api10_b64"}) and "stream" in keys
    if profile == COMPLETION_POOL_PROFILE:
        return bool(keys & {"completion_key", "completion_key_b64"})
    if profile == PRODUCTION_PROFILE:
        return bool(keys & {"api10", "api10_b64", "entity_key", "entity_key_b64"})
    if profile in (WELL_PROFILE, BASIN_CONTEXT_PROFILE):
        return "api10" in keys or "api10_b64" in keys
    return profile == RESPONSE_PROFILE


def identity_selector_term(name: str, value: str) -> str:
    """Render an identity without lossy substitution or padded/standard base64."""
    if _PLAIN_IDENTITY.fullmatch(value):
        return f"{name}={value}"
    encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{name}_b64={encoded}"


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


def neighbor_api10_pattern(registry: JurisdictionRegistry) -> str:
    """The API-10 shape a neighbour selector may carry, built from the registrations.

    It was a two-prefix alternation literal: a fourth spelling of a set already written down in
    the mart, in the migration CHECK and in the registry, and one the add-a-state gate could not
    see, because its generic rule needs the quote immediately before the digits and an
    alternation group puts a parenthesis there. A registry argument rather than a module-scope
    read, because `lineage/` importing `glasswell.seed` would be a new dependency edge.
    """
    prefixes = sorted(
        row.identity_prefix
        for row in registry
        if row.neighbors_available
        and row.identity_prefix is not None
        and row.rule(NEIGHBORS_SCOPE) is not None
    )
    if not prefixes:
        raise InvalidSelector(
            f"{NEIGHBOR_DATASET} holds subjects for no registered jurisdiction"
        )
    return f"({'|'.join(prefixes)})[0-9]{{8}}"


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
    api10_pattern = neighbor_api10_pattern(load_jurisdictions(connection))
    if terms or not re.fullmatch(api10_pattern, api10):
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
            if re.fullmatch(api10_pattern, str(after_api10)) is None:
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


def _validate_completion_design(
    connection: psycopg.Connection,
    derivation: Mapping[str, Any],
    terms: dict[str, str],
    *,
    handle: str,
) -> None:
    column = terms.pop("col", None)
    if column not in _COMPLETION_DESIGN_COLUMNS:
        raise InvalidSelector(f"{column!r} is not a selectable completion-design column")
    disclosure_id = _identity(terms, "disclosure_id")
    if terms:
        raise InvalidSelector("completion-design selectors require disclosure_id plus col")
    _require_one(
        connection,
        "select count(*) from canonical.well_completion_design"
        " where derivation_id = %s and disclosure_id = %s",
        (derivation["derivation_id"], disclosure_id),
        derivation=derivation,
        handle=handle,
    )


def _validate_well_cumulative(
    connection: psycopg.Connection,
    derivation: Mapping[str, Any],
    terms: dict[str, str],
    *,
    handle: str,
) -> None:
    column = terms.pop("col", None)
    if column not in _CUMULATIVE_COLUMNS:
        raise InvalidSelector(f"{column!r} is not a selectable well-cumulative column")
    stream = terms.pop("stream", None)
    if stream not in _CUMULATIVE_STREAMS:
        raise InvalidSelector(f"{stream!r} is not a well-cumulative stream")
    api10 = _identity(terms, "api10")
    if re.fullmatch(r"[0-9]{10}", api10) is None or terms:
        raise InvalidSelector("well-cumulative selectors require api10, stream and col")
    _require_one(
        connection,
        "select count(*) from marts.well_cumulatives"
        " where derivation_id = %s and api10 = %s and stream = %s",
        (derivation["derivation_id"], api10, stream),
        derivation=derivation,
        handle=handle,
    )


def _validate_production(
    connection: psycopg.Connection,
    derivation: Mapping[str, Any],
    terms: dict[str, str],
    *,
    handle: str,
) -> None:
    column = terms.pop("col", None)
    stream = _PRODUCTION_COLUMNS.get(str(column))
    if stream is None:
        raise InvalidSelector(f"{column!r} is not a selectable production column")
    api10 = _optional_identity(terms, "api10")
    entity_key = _optional_identity(terms, "entity_key")
    if (api10 is None) == (entity_key is None):
        raise InvalidSelector("production selectors require exactly one entity identity")
    production_month = terms.pop("pm", None)
    if terms:
        raise InvalidSelector(
            "production selectors require one entity identity, col, and optional pm"
        )

    statement = (
        "select count(*) from canonical.production_monthly"
        " where derivation_id = %s and stream = %s"
    )
    parameters: list[object] = [derivation["derivation_id"], stream]
    if api10 is not None:
        if re.fullmatch(r"[0-9]{10}", api10) is None:
            raise InvalidSelector("api10 must be exactly ten digits")
        statement += " and entity_type = 'well' and api10 = %s and entity_key = %s"
        parameters.extend((api10, api10))
    else:
        statement += " and entity_type = 'well_completion_pool' and entity_key = %s"
        parameters.append(entity_key)
    if production_month is not None:
        parsed_month = _month(production_month)
        statement += " and production_month = %s"
        parameters.append(parsed_month)
        _require_one(
            connection,
            statement,
            tuple(parameters),
            derivation=derivation,
            handle=handle,
        )
        return
    _require_any(
        connection,
        statement,
        tuple(parameters),
        derivation=derivation,
        handle=handle,
    )


def _validate_well(
    connection: psycopg.Connection,
    derivation: Mapping[str, Any],
    terms: dict[str, str],
    *,
    handle: str,
) -> None:
    column = terms.pop("col", None)
    if column not in _WELL_COLUMNS:
        raise InvalidSelector(f"{column!r} is not a selectable well column")
    api10 = _identity(terms, "api10")
    effective_from = terms.pop("effective_from", None)
    try:
        parsed_effective = date.fromisoformat(str(effective_from))
    except ValueError:
        raise InvalidSelector("well selectors require an ISO effective_from") from None
    if (
        re.fullmatch(r"[0-9]{10}", api10) is None
        or parsed_effective.isoformat() != effective_from
        or terms
    ):
        raise InvalidSelector("well selectors require api10, effective_from, and col")
    _require_one(
        connection,
        "select count(*) from canonical.wells"
        " where derivation_id = %s and api10 = %s and effective_from = %s"
        " and total_depth_ft is not null",
        (derivation["derivation_id"], api10, parsed_effective),
        derivation=derivation,
        handle=handle,
    )


def _validate_basin_context(
    connection: psycopg.Connection,
    derivation: Mapping[str, Any],
    terms: dict[str, str],
    *,
    handle: str,
) -> None:
    column = terms.pop("col", None)
    if column not in _BASIN_CONTEXT_COLUMNS:
        raise InvalidSelector(f"{column!r} is not a selectable basin-context column")
    api10 = _identity(terms, "api10")
    if re.fullmatch(r"[0-9]{10}", api10) is None or terms:
        raise InvalidSelector("basin-context selectors require api10 and col")
    _require_one(
        connection,
        "select count(*) from marts.well_basin_context"
        " where derivation_id = %s and api10 = %s",
        (derivation["derivation_id"], api10),
        derivation=derivation,
        handle=handle,
    )


def _validate_response_output(
    connection: psycopg.Connection,
    derivation: Mapping[str, Any],
    pairs: tuple[tuple[str, str], ...],
    *,
    outputs: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    recorded = outputs
    if recorded is None:
        with connection.cursor() as cursor:
            cursor.execute(
                "select selector, evidence from lineage.response_selector_outputs"
                " where derivation_id = %s order by selector",
                (derivation["derivation_id"],),
            )
            recorded = {row[0]: row[1] for row in cursor.fetchall()}
    if not recorded:
        raise InvalidSelector("API-response derivation has no selector output evidence")
    expected_hash = hash_payload(recorded)
    if derivation.get("output_sha256") != expected_hash:
        raise InvalidSelector("API-response selector output evidence does not match its hash")
    selector = format_selector(sorted(pairs))
    if selector not in recorded:
        raise InvalidSelector("selector does not name an output recorded by the API response")


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
    if (production_month is None) == (effective_from is None):
        raise InvalidSelector("completion-pool selector requires exactly one time key")
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
        parsed_month = _month(production_month)
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
    if not encoded or re.fullmatch(r"[A-Za-z0-9_-]+", encoded) is None:
        raise InvalidSelector(f"{name}_b64 is not unpadded URL-safe base64")
    try:
        decoded = base64.b64decode(
            encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True
        ).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise InvalidSelector(f"{name}_b64 is not strict URL-safe base64 UTF-8") from None
    if not decoded or len(decoded) > 2048:
        raise InvalidSelector(f"decoded {name}_b64 has invalid length")
    canonical = base64.urlsafe_b64encode(decoded.encode("utf-8")).decode("ascii").rstrip("=")
    if canonical != encoded:
        raise InvalidSelector(f"{name}_b64 is not canonical unpadded URL-safe base64")
    return decoded


def _month(value: str) -> date:
    try:
        parsed = date.fromisoformat(f"{value}-01")
    except ValueError:
        raise InvalidSelector("pm must be YYYY-MM") from None
    if parsed.strftime("%Y-%m") != value:
        raise InvalidSelector("pm must be YYYY-MM")
    return parsed


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


def _require_any(
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
