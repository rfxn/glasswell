"""DR-63 against populations the contract fixture cannot hold: a deep chain, and an over-cap one.

The contract fixture's chain is one hop (promote ← manifest) and its responses carry three
handles, so neither `explain_depth` nor the inline bound is observable there. Both are seeded
here — a gate that is green on data it does not represent is this stack's first anti-pattern.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import parse_qsl

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.explain import MAX_HANDLES
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.store import PostgresRecorder
from glasswell.seed import seed_all
from tests.support.seed import seed_manifest, seed_well, seed_well_spatial

VINTAGE = date(2026, 8, 1)
SUMMARY = "/v1/wells/status-summary"
WIDE = "-180,-90,180,90"
LATITUDE = 47.5

# Enough classes and jurisdictions that the box produces more counts than /v1/explain accepts
# handles in one call, which is the only way the inline bound is reachable at all.
ND_POPULATION: tuple[tuple[str, str | None], ...] = (
    ("3305300001", "active"),
    ("3305300002", "plugged"),
    ("3305300003", "dry"),
    ("3305300004", "inactive"),
    ("3305300005", "service"),
    ("3305300006", None),
)
TX_POPULATION: tuple[tuple[str, str | None], ...] = (
    ("4200300001", "active"),
    ("4200300002", "plugged"),
    ("4200300003", "dry"),
    ("4200300004", "inactive"),
    ("4200300005", "service"),
    ("4200300006", None),
)


@pytest.fixture
def deep_chain(db: psycopg.Connection, lineage_env: Any) -> tuple[str, str]:
    """mart ← promote ← parse ← manifest: four levels, so depth 1, 2 and 3 differ."""
    manifest_id = seed_manifest(db, sha256="a" * 64)
    with lineage_session(
        recorder=PostgresRecorder(db), environment=lineage_env, correlation_id="run_inline"
    ):
        with derive(
            "mart.refresh",
            output=OutputSpec(store="postgres", dataset="marts.well_card"),
            params={"basin": "williston"},
        ) as mart:
            with derive(
                "canonical.promote",
                output=OutputSpec(store="postgres", dataset="canonical.production_monthly"),
                params={"month_convention": "production_month"},
                rules=("cr_nd_units_1",),
            ) as promote:
                with derive(
                    "stage.parse",
                    output=OutputSpec(store="postgres", dataset="staging.nd_mpr_oil"),
                    params={"sheet": "Oil"},
                    inputs=[InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=VINTAGE)],
                ) as parse:
                    parse.set_output_hash("b" * 64)
                promote.set_output_hash("c" * 64)
            mart.set_output_hash("d" * 64)
    db.commit()
    return mart.derivation_id, manifest_id


@pytest.fixture
def crowded(db: psycopg.Connection) -> psycopg.Connection:
    """Two jurisdictions, six status classes each, all inside one box."""
    seed_all(db)
    manifest = seed_manifest(db, sha256="c" * 64, source_id="nd_gis_wells", source_key="wells.zip")
    for index, (api10, status) in enumerate(ND_POPULATION):
        seed_well(db, api10=api10, manifest_id=manifest, status_canonical=status)
        seed_well_spatial(
            db,
            api10=api10,
            geom_type="surface",
            wkt=f"POINT({-103.9 + index / 10} {LATITUDE})",
            manifest_id=manifest,
        )
    for index, (api10, status) in enumerate(TX_POPULATION):
        seed_well(
            db,
            api10=api10,
            manifest_id=manifest,
            state_code="42",
            basin="permian",
            status_canonical=status,
        )
        seed_well_spatial(
            db,
            api10=api10,
            geom_type="surface",
            wkt=f"POINT({-102.5 + index / 10} 32.3)",
            manifest_id=manifest,
        )
    db.commit()
    return db


def _explained(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get(SUMMARY, params={"bbox": WIDE, "explain": "true", **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_shallower_depth_inlines_a_shorter_chain_and_says_it_is_truncated(
    deep_chain: tuple[str, str], api_client: TestClient
) -> None:
    """§9.2's depth is the chain walk's depth, and the inlined chain reports its own stop."""
    root, manifest_id = deep_chain

    shallow = api_client.get("/v1/explain", params={"h": root, "depth": "1"}).json()
    full = api_client.get("/v1/explain", params={"h": root, "depth": "full"}).json()

    assert shallow["data"]["chains"][0]["truncated"] is True
    assert shallow["data"]["chains"][0]["terminals"] == []
    assert full["data"]["chains"][0]["truncated"] is False
    assert full["data"]["chains"][0]["terminals"] == [manifest_id]
    assert len(full["data"]["chains"][0]["nodes"]) == 4


def test_the_inlined_depth_is_the_depth_the_caller_named(
    crowded: psycopg.Connection, api_client: TestClient
) -> None:
    at_one = _explained(api_client, explain_depth=1)["_explain"]
    at_eight = _explained(api_client, explain_depth=8)["_explain"]

    assert set(at_one) == set(at_eight)
    for handle, chain in at_one.items():
        served = api_client.get("/v1/explain", params={"h": handle, "depth": "1"})
        assert chain == served.json()["data"]["chains"][0]
    for handle, chain in at_eight.items():
        served = api_client.get("/v1/explain", params={"h": handle, "depth": "8"})
        assert chain == served.json()["data"]["chains"][0]


def test_the_bound_is_stated_with_exact_counts_and_never_silently(
    crowded: psycopg.Connection, api_client: TestClient
) -> None:
    """The `explain_link_truncated` precedent (DR-33 / the C6 pane rule): an exact count, never
    an ellipsis, and a route that still works for everything left out."""
    body = _explained(api_client)
    carried = _handles(body["data"])

    assert len(carried) > MAX_HANDLES
    warning = next(
        item for item in body["meta"]["warnings"] if item["code"] == "explain_inline_truncated"
    )
    assert len(body["_explain"]) == MAX_HANDLES
    assert warning["detail"].startswith(
        f"This response carries {len(carried)} handles and _explain inlines the first"
        f" {MAX_HANDLES}, so {len(carried) - MAX_HANDLES} are absent from it."
    )


def test_everything_the_bound_left_out_still_resolves_one_at_a_time(
    crowded: psycopg.Connection, api_client: TestClient
) -> None:
    body = _explained(api_client)
    omitted = sorted(_handles(body["data"]) - set(body["_explain"]))

    assert omitted
    for handle in omitted:
        resolved = api_client.get("/v1/explain", params={"h": handle, "depth": "full"})
        assert resolved.status_code == 200, handle


def test_the_inlined_set_matches_the_link_even_when_both_are_bounded(
    crowded: psycopg.Connection, api_client: TestClient
) -> None:
    """Two carriers of the same fact must not disagree (§3.6.2). Over the cap is exactly where
    they would, because each would otherwise choose its own first twenty."""
    body = _explained(api_client)
    linked = [
        value for key, value in parse_qsl(body["links"]["explain"].split("?", 1)[1]) if key == "h"
    ]

    assert set(body["_explain"]) == set(linked)


def test_a_bounded_response_is_byte_identical_without_the_flag(
    crowded: psycopg.Connection, api_client: TestClient
) -> None:
    """The bound adds a warning to `meta`, so this is the case where "only adds `_explain`"
    is most at risk of being false."""
    plain = api_client.get(SUMMARY, params={"bbox": WIDE})
    explained = api_client.get(SUMMARY, params={"bbox": WIDE, "explain": "false"})

    assert plain.status_code == 200
    assert _pinned(plain) == _pinned(explained)
    assert "explain_inline_truncated" not in _pinned(plain).decode()


def _pinned(response: Any) -> bytes:
    return response.content.replace(
        response.json()["meta"]["request_id"].encode(), b"<request_id>"
    )


def _handles(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        if isinstance(node.get("d"), str):
            found.add(node["d"])
        for key, value in node.items():
            if key == "_lineage" and isinstance(value, dict):
                found.update(str(handle) for handle in value.values())
            else:
                found |= _handles(value)
    elif isinstance(node, list):
        for value in node:
            found |= _handles(value)
    return found
