"""`?explain=true` on `/v1/wells/{api10}/production/pools` (SB-07 §9.2).

The base fixture's wells filed in one pool each, so the collection this operation serves is
empty there and the flag's handle-bearing arm is unreachable — a gate green on data it does
not represent. This module seeds a well that filed two pools across two months, which also
exercises the ND per-point form: the point handles differ by month, so the column carries a
handle per point rather than one per series.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl

import psycopg
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10, EXAMPLE_DERIVATION_ID, EXAMPLE_MANIFEST_ID
from glasswell.lineage.explain import DEFAULT_DEPTH
from tests.contract.test_explain_inline import _call, _normalised, _without_explain
from tests.support.seed import seed_production

# OTHER_API10S[2]: seeded as a well by the base fixture, with no production rows of its own.
POOL_WELL = "3305300003"
POOLS = ("BIRDBEAR", "DUPEROW")
MONTHS = (date(2026, 6, 1), date(2026, 7, 1))
CALL: dict[str, Any] = {"url": f"/v1/wells/{POOL_WELL}/production/pools", "params": {}}


def _seed_pools(connection: psycopg.Connection) -> None:
    for ordinal, pool in enumerate(POOLS):
        for month in MONTHS:
            seed_production(
                connection,
                api10=POOL_WELL,
                production_month=month,
                report_vintage=date(2026, 8, 1),
                volume=Decimal(1000 * (ordinal + 1) + month.month),
                manifest_id=EXAMPLE_MANIFEST_ID,
                derivation_id=EXAMPLE_DERIVATION_ID,
                stream="oil",
                entity_type="well_completion_pool",
                entity_key=f"{POOL_WELL}:{pool}",
                reporting_level="well_completion_pool",
                well_completion_pool=pool,
            )


def test_the_flag_absent_and_the_flag_false_are_the_same_bytes(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    _seed_pools(seeded)
    absent = _call(client, CALL)
    explicitly_off = _call(client, CALL, explain="false")

    assert _normalised(absent) == _normalised(explicitly_off)
    assert "_explain" not in absent.json()


def test_explain_true_adds_the_block_and_moves_nothing_else(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    _seed_pools(seeded)
    plain = _call(client, CALL)
    explained = _call(client, CALL, explain="true")

    assert set(explained.json()) == {"data", "meta", "links", "_explain"}
    assert _without_explain(explained) == _normalised(plain)


def test_the_inlined_chain_is_what_explain_returns_for_that_handle(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """Per-point handles included: every month's handle resolves to the same chain the
    resolver serves for it, not a lookalike."""
    _seed_pools(seeded)
    inlined = _call(client, CALL, explain="true").json()["_explain"]

    assert len(inlined) == len(POOLS) * len(MONTHS)
    for handle, chain in inlined.items():
        served = client.get("/v1/explain", params={"h": handle, "depth": str(DEFAULT_DEPTH)})
        assert served.status_code == 200, handle
        assert chain == served.json()["data"]["chains"][0]


def test_the_inlined_set_is_the_set_links_explain_names(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    _seed_pools(seeded)
    body = _call(client, CALL, explain="true").json()
    linked = [
        value for key, value in parse_qsl(body["links"]["explain"].split("?", 1)[1]) if key == "h"
    ]

    assert set(body["_explain"]) == set(linked)


def test_a_well_with_no_breakdown_gains_an_empty_block_and_not_a_missing_one(
    client: TestClient,
) -> None:
    """The base fixture's example well filed in one pool, so this operation's list is empty
    for it — and `{}` states the flag ran, where absent would be indistinguishable from a
    surface that never honoured it."""
    body = client.get(
        f"/v1/wells/{EXAMPLE_API10}/production/pools", params={"explain": "true"}
    ).json()

    assert body["data"]["pools"] == []
    assert body["_explain"] == {}
