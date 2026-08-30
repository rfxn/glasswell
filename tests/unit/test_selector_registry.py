from __future__ import annotations

from typing import Any

import pytest

from glasswell.lineage.errors import InvalidSelector
from glasswell.lineage.explain import PostgresGraph
from glasswell.lineage.selector_registry import (
    COMPLETION_ANCHOR_PROFILE,
    COMPLETION_DESIGN_PROFILE,
    COMPLETION_POOL_PROFILE,
    RESPONSE_PROFILE,
    WELL_CUMULATIVE_PROFILE,
    _profile_matches,
    identity_selector_term,
    validate_selector,
)
from glasswell.lineage.serialization import hash_payload


class NoDatabase:
    def cursor(self):
        raise AssertionError("invalid selector reached the database")


class RegistryCursor:
    def __init__(self, connection: RegistryConnection) -> None:
        self.connection = connection
        self.statement = ""

    def __enter__(self) -> RegistryCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, statement: str, parameters: object) -> None:
        self.connection.queries += 1
        self.statement = statement

    def fetchall(self) -> list[tuple[Any, ...]]:
        if "response_selector_outputs" in self.statement:
            return list(self.connection.outputs.items())
        return [(RESPONSE_PROFILE,)]


class RegistryConnection:
    def __init__(self, outputs: dict[str, dict[str, str]] | None = None) -> None:
        self.queries = 0
        self.outputs = outputs or {}

    def cursor(self) -> RegistryCursor:
        return RegistryCursor(self)


def derivation(**overrides: Any) -> dict[str, Any]:
    return {
        "derivation_id": "drv_selector01",
        "operation": "canonical.promote",
        "output_dataset": "canonical.production_monthly",
        "output_sha256": "0" * 64,
        "params": {},
        **overrides,
    }


@pytest.mark.parametrize(
    "encoded",
    [
        "8J+YgA",
        "/w",
        "Zg=",
        "Zh",
    ],
    ids=["standard-plus", "standard-slash", "padding", "noncanonical-trailing-bits"],
)
def test_identity_base64_is_canonical_unpadded_urlsafe_only(encoded: str) -> None:
    selector = f"completion_key_b64={encoded}&col=pool_reported&pm=2026-01"

    with pytest.raises(InvalidSelector):
        validate_selector(
            NoDatabase(),  # type: ignore[arg-type]
            derivation(),
            selector,
            handle=f"drv_selector01#{selector}",
            profiles=(COMPLETION_POOL_PROFILE,),
        )


@pytest.mark.parametrize(
    "time_terms",
    ["", "&pm=2026-01&effective_from=2026-01-01"],
    ids=["neither", "both"],
)
def test_completion_pool_time_identity_is_xor(time_terms: str) -> None:
    selector = f"completion_key=3305301234:bakken&col=pool_reported{time_terms}"

    with pytest.raises(InvalidSelector, match="exactly one time key"):
        validate_selector(
            NoDatabase(),  # type: ignore[arg-type]
            derivation(),
            selector,
            handle=f"drv_selector01#{selector}",
            profiles=(COMPLETION_POOL_PROFILE,),
        )


def test_an_unknown_registry_profile_fails_closed() -> None:
    selector = "api10=3305301234&col=oil_bbl"

    with pytest.raises(InvalidSelector, match="unknown profiles"):
        validate_selector(
            NoDatabase(),  # type: ignore[arg-type]
            derivation(),
            selector,
            handle=f"drv_selector01#{selector}",
            profiles=("future_profile_without_code",),
        )


def test_response_selector_matches_exact_recorded_evidence_in_any_term_order() -> None:
    selector = "bbox=-104.0:47.5:-103.0:48.5&col=wells&status=active"
    outputs = {
        selector: {"value": "12", "unit": "wells"},
    }
    row = derivation(
        operation="api.respond",
        output_dataset="api.well_status_summary",
        output_sha256=hash_payload(outputs),
        params={"operation_id": "get_well_status_summary"},
    )

    validate_selector(
        NoDatabase(),  # type: ignore[arg-type]
        row,
        "status=active&col=wells&bbox=-104.0:47.5:-103.0:48.5",
        handle="drv_selector01#status=active&col=wells&bbox=-104.0:47.5:-103.0:48.5",
        profiles=(RESPONSE_PROFILE,),
        response_outputs=outputs,
    )

    with pytest.raises(InvalidSelector, match="does not name"):
        validate_selector(
            NoDatabase(),  # type: ignore[arg-type]
            row,
            "status=active&col=wells&bbox=-104.0:47.5:-103.0:48.5&basin=williston",
            handle="drv_selector01#status=active&col=wells",
            profiles=(RESPONSE_PROFILE,),
            response_outputs=outputs,
        )


def test_identity_rendering_never_collapses_distinct_unsafe_values() -> None:
    first = identity_selector_term("status", "A B")
    second = identity_selector_term("status", "A?B")

    assert first != second
    assert first.startswith("status_b64=")
    assert second.startswith("status_b64=")
    encoded = [term.split("=", 1)[1] for term in (first, second)]
    assert all(character not in "".join(encoded) for character in "+/=")


def test_one_graph_loads_a_profile_once_for_many_handles() -> None:
    selector = "api10=3305301234&col=lateral_length_ft"
    outputs = {selector: {"value": "5280.00", "unit": "ft"}}
    row = derivation(
        operation="api.respond",
        output_dataset="api.well_detail",
        output_sha256=hash_payload(outputs),
        params={"operation_id": "get_well"},
    )
    connection = RegistryConnection(outputs)
    graph = PostgresGraph(connection)  # type: ignore[arg-type]

    for _ in range(20):
        graph.validate_selector(row, selector, handle=f"drv_selector01#{selector}")

    assert connection.queries == 2


@pytest.mark.parametrize(
    "selector",
    [
        "disclosure_id=ff-0001&col=tvd",
        "disclosure_id=ff-0001&col=base_water_volume&extra=1",
        "col=base_water_volume",
    ],
    ids=["column-outside-the-set", "unexpected-term", "no-identity"],
)
def test_a_completion_design_selector_is_refused_outside_its_grammar(selector: str) -> None:
    with pytest.raises(InvalidSelector):
        validate_selector(
            NoDatabase(),  # type: ignore[arg-type]
            derivation(output_dataset="canonical.well_completion_design"),
            selector,
            handle=f"drv_selector01#{selector}",
            profiles=(COMPLETION_DESIGN_PROFILE,),
        )


def test_the_anchor_and_design_profiles_never_compete_for_one_lookup() -> None:
    """Identical predicates, different output datasets: the registry keys them apart.

    Written because the next reader of `_profile_matches` sees two identical branches and
    assumes a bug; `validate_selector` requires exactly one match, so a lookup that could
    register both would raise.
    """
    terms = {"disclosure_id": "ff-0001", "col": "base_water_volume"}

    assert _profile_matches(COMPLETION_ANCHOR_PROFILE, terms)
    assert _profile_matches(COMPLETION_DESIGN_PROFILE, terms)
    with pytest.raises(InvalidSelector, match="no unique registered selector profile"):
        validate_selector(
            NoDatabase(),  # type: ignore[arg-type]
            derivation(output_dataset="canonical.well_completion_design"),
            "disclosure_id=ff-0001&col=base_water_volume",
            handle="drv_selector01#disclosure_id=ff-0001&col=base_water_volume",
            profiles=(COMPLETION_ANCHOR_PROFILE, COMPLETION_DESIGN_PROFILE),
        )


@pytest.mark.parametrize(
    "selector",
    [
        "api10=3305310451&stream=oil&col=cum_volume",
        "api10=3305310451&stream=liquid&col=months_reported",
        "api10=330531045&stream=liquid&col=cum_volume",
        "api10=3305310451&stream=liquid&col=cum_volume&pm=2026-01",
    ],
    ids=["stream-outside-the-mart", "column-outside-the-set", "short-api10", "unexpected-term"],
)
def test_a_well_cumulative_selector_is_refused_outside_its_grammar(selector: str) -> None:
    with pytest.raises(InvalidSelector):
        validate_selector(
            NoDatabase(),  # type: ignore[arg-type]
            derivation(operation="mart.refresh", output_dataset="marts.well_cumulatives"),
            selector,
            handle=f"drv_selector01#{selector}",
            profiles=(WELL_CUMULATIVE_PROFILE,),
        )


def test_a_well_cumulative_selector_needs_its_stream_to_match_the_profile() -> None:
    """The mart is keyed (api10, stream), so an api10-only selector names three rows."""
    assert not _profile_matches(WELL_CUMULATIVE_PROFILE, {"api10": "3305310451"})
    assert _profile_matches(WELL_CUMULATIVE_PROFILE, {"api10": "3305310451", "stream": "liquid"})
