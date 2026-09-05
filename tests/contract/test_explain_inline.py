"""DR-63: `?explain=true` on the figure-bearing GETs (SB-07 §9.2).

§9.2's GET row: *"Response gains `_explain: {handle: chain}` for every handle it contains.
Default depth 3, max 8."* and *"`?explain=true` never changes the values in a response — only
adds `_explain`."* Both halves are asserted here, the second as byte identity rather than as
value identity, because a cached or replayed comparison is what the sentence exists to protect.

`_explain` sits beside `data`, not inside it: §9.2 says *response*, §9.1(b)'s sidecars say
*resource*, and the map is keyed by handle — a string carrying `#`, `&` and `=` — where a
sidecar is keyed by dotted pointer. Keeping it out of `data` also keeps the R6 walker's
population exactly the served figures rather than admitting graph bookkeeping into it.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl

import psycopg
import pytest
from fastapi.testclient import TestClient
from httpx import Response

from glasswell.api.errors import TYPE_BASE
from glasswell.api.examples import (
    EXAMPLE_API10,
    EXAMPLE_BBOX,
    EXAMPLE_DERIVATION_ID,
    EXAMPLE_MANIFEST_ID,
    EXAMPLE_PUBLICATION_ID,
    EXAMPLE_VINTAGE_ID,
)
from glasswell.lineage.envelope import InlinedExplain, attach_lineage, figure
from glasswell.lineage.explain import DEFAULT_DEPTH, MAX_DEPTH
from glasswell.lineage.vintages import open_vintage
from tests.contract.test_naked_numbers import naked_numbers
from tests.support.seed import seed_derivation, seed_production

# OTHER_API10S[2]: seeded as a well by the base fixture, with no production rows of its own.
POOL_WELL = "3305300003"
POOLS = ("BIRDBEAR", "DUPEROW")
MONTHS = (date(2026, 6, 1), date(2026, 7, 1))


def _seed_pools(connection: psycopg.Connection) -> None:
    """A well that filed two pools across two months.

    Also the ND per-point form: the point handles differ by month, so the column carries a
    handle per point rather than one per series.
    """
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


def _prepare(name: str, connection: psycopg.Connection) -> None:
    """The rows a surface needs before it carries a handle at all."""
    seed = SEEDS.get(name)
    if seed is not None:
        seed(connection)


# Every handle-carrying GET: the three §9.2 reached first (a header, a series, an aggregate),
# then the spine surfaces the convergence brought in — a sidecar page, a sidecar record and a
# record whose subject is itself a derivation. Pools carry handles only when a well filed in
# more than one pool, which this fixture's wells did not — test_explain_inline_pools.py seeds
# that arm.
SURFACES: tuple[tuple[str, dict[str, Any]], ...] = (
    ("get_well", {"url": f"/v1/wells/{EXAMPLE_API10}", "params": {}}),
    (
        "get_well_completions",
        {"url": f"/v1/wells/{EXAMPLE_API10}/completions", "params": {}},
    ),
    ("get_well_production", {"url": f"/v1/wells/{EXAMPLE_API10}/production", "params": {}}),
    (
        "get_well_status_summary",
        {"url": "/v1/wells/status-summary", "params": {"bbox": EXAMPLE_BBOX}},
    ),
    ("get_derivation", {"url": f"/v1/derivations/{EXAMPLE_DERIVATION_ID}", "params": {}}),
    ("list_vintages", {"url": "/v1/vintages", "params": {}}),
    ("get_vintage", {"url": f"/v1/vintages/{EXAMPLE_VINTAGE_ID}", "params": {}}),
    ("get_well_type_curve", {"url": f"/v1/wells/{EXAMPLE_API10}/type-curve", "params": {}}),
    ("list_type_curves", {"url": "/v1/type-curves", "params": {}}),
    (
        "get_modeling_publication",
        {"url": f"/v1/modeling/publications/{EXAMPLE_PUBLICATION_ID}", "params": {}},
    ),
    (
        "get_well_production_pools",
        {"url": f"/v1/wells/{POOL_WELL}/production/pools", "params": {}},
    ),
)
SURFACE_IDS = [name for name, _ in SURFACES]
# A surface whose handle-bearing arm is unreachable on the base fixture states what it needs
# here. Pools is the only one: the fixture's wells filed in one pool each, so the collection
# is empty for them and every property below would pass on data it does not represent.
SEEDS = {"get_well_production_pools": _seed_pools}

# The frozen paths the two parameters are declared on — every SURFACES row plus pools, whose
# fixture arm lives in its own module.
DECLARED_PATHS = (
    "/v1/wells/{api10}",
    "/v1/wells/{api10}/completions",
    "/v1/wells/{api10}/production",
    "/v1/wells/status-summary",
    "/v1/wells/{api10}/production/pools",
    "/v1/derivations/{derivation_id}",
    "/v1/vintages",
    "/v1/vintages/{vintage_id}",
    "/v1/modeling/publications",
    "/v1/modeling/publications/{publication_id}",
    "/v1/wells/{api10}/type-curve",
    "/v1/type-curves",
)


def _call(client: TestClient, call: dict[str, Any], **extra: Any) -> Response:
    response = client.get(call["url"], params={**call["params"], **extra})
    assert response.status_code == 200, response.text
    return response


def _normalised(response: Response) -> bytes:
    """The bytes, with the one field that is a new ULID on every request pinned."""
    request_id = response.json()["meta"]["request_id"]
    return response.content.replace(request_id.encode(), b"<request_id>")


def _without_explain(response: Response) -> bytes:
    body = json.loads(response.content)
    del body["_explain"]
    request_id = body["meta"]["request_id"]
    # starlette's own rendering, so what is compared is bytes and not a normalised form.
    rendered = json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return rendered.encode("utf-8").replace(request_id.encode(), b"<request_id>")


@pytest.mark.parametrize(("name", "call"), SURFACES, ids=SURFACE_IDS)
def test_the_flag_absent_and_the_flag_false_are_the_same_bytes(
    client: TestClient, seeded: psycopg.Connection, name: str, call: dict[str, Any]
) -> None:
    """The additive guarantee, at byte level: a client that never sends the parameter cannot
    tell it was added."""
    _prepare(name, seeded)
    absent = _call(client, call)
    explicitly_off = _call(client, call, explain="false")

    assert _normalised(absent) == _normalised(explicitly_off)
    assert "_explain" not in absent.json()
    assert set(absent.json()) == {"data", "meta", "links"}


@pytest.mark.parametrize(("name", "call"), SURFACES, ids=SURFACE_IDS)
def test_explain_true_adds_the_block_and_moves_nothing_else(
    client: TestClient, seeded: psycopg.Connection, name: str, call: dict[str, Any]
) -> None:
    """§9.2: *never changes the values in a response — only adds `_explain`*. Strip the block
    back off and the bytes are the bytes of the request that never asked for it."""
    _prepare(name, seeded)
    plain = _call(client, call)
    explained = _call(client, call, explain="true")

    assert set(explained.json()) == {"data", "meta", "links", "_explain"}
    assert _without_explain(explained) == _normalised(plain)


@pytest.mark.parametrize(("name", "call"), SURFACES, ids=SURFACE_IDS)
def test_the_inlined_chain_is_what_explain_returns_for_that_handle(
    client: TestClient, seeded: psycopg.Connection, name: str, call: dict[str, Any]
) -> None:
    """Equality, not shape. One resolver, reached two ways — a second traversal that merely
    looked similar is the failure this asserts against."""
    _prepare(name, seeded)
    inlined = _call(client, call, explain="true").json()["_explain"]

    assert inlined
    for handle, chain in inlined.items():
        served = client.get(
            "/v1/explain", params={"h": handle, "depth": str(DEFAULT_DEPTH)}
        )
        assert served.status_code == 200, handle
        assert chain == served.json()["data"]["chains"][0]


@pytest.mark.parametrize(("name", "call"), SURFACES, ids=SURFACE_IDS)
def test_the_inlined_set_is_the_set_links_explain_names(
    client: TestClient, seeded: psycopg.Connection, name: str, call: dict[str, Any]
) -> None:
    """One answer to "which handles will you resolve for me", not two that can disagree
    (§3.6.2). `_explain` is `links.explain` already called."""
    _prepare(name, seeded)
    body = _call(client, call, explain="true").json()
    linked = [
        value for key, value in parse_qsl(body["links"]["explain"].split("?", 1)[1]) if key == "h"
    ]

    assert set(body["_explain"]) == set(linked)


@pytest.mark.parametrize(("name", "call"), SURFACES, ids=SURFACE_IDS)
def test_the_depth_the_caller_asked_for_is_the_depth_it_resolved_at(
    client: TestClient, seeded: psycopg.Connection, name: str, call: dict[str, Any]
) -> None:
    _prepare(name, seeded)
    inlined = _call(client, call, explain="true", explain_depth=1).json()["_explain"]

    assert inlined
    for handle, chain in inlined.items():
        served = client.get("/v1/explain", params={"h": handle, "depth": "1"})
        assert chain == served.json()["data"]["chains"][0]


def test_the_default_depth_is_three(client: TestClient) -> None:
    """§9.2 names the default; the document has to say the same number the code uses."""
    document = client.get("/openapi.json").json()
    parameter = next(
        item
        for item in document["paths"]["/v1/wells/{api10}"]["get"]["parameters"]
        if item["name"] == "explain_depth"
    )

    assert parameter["schema"]["default"] == DEFAULT_DEPTH == 3
    assert parameter["schema"]["maximum"] == MAX_DEPTH == 8


@pytest.mark.parametrize("depth", ["9", "0", "-1", "full"])
def test_a_depth_outside_the_declared_range_is_refused_not_clamped(
    client: TestClient, depth: str
) -> None:
    """SB-04 §2.3: over the cap is 422. `full` is `/v1/explain`'s own grammar, not this one —
    an inlining flag that quietly meant eight would be a cap nobody declared."""
    response = client.get(
        f"/v1/wells/{EXAMPLE_API10}", params={"explain": "true", "explain_depth": depth}
    )

    assert response.status_code == 422
    assert response.json()["type"] == f"{TYPE_BASE}/validation_failed"
    assert any(item["pointer"].endswith("/explain_depth") for item in response.json()["errors"])


def test_the_pools_surface_carries_a_handle_per_point(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The ND per-point form: a handle per pool per month, not one per series."""
    _seed_pools(seeded)
    inlined = _call(client, dict(SURFACES[-1][1]), explain="true").json()["_explain"]

    assert len(inlined) == len(POOLS) * len(MONTHS)


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


def test_a_response_carrying_no_handle_gains_an_empty_block_and_not_a_missing_one(
    client: TestClient,
) -> None:
    """Absent would be indistinguishable from "the flag did nothing"; empty is a statement."""
    body = client.get(
        "/v1/wells/status-summary", params={"bbox": "-1,-1,-0.9,-0.9", "explain": "true"}
    ).json()

    assert body["data"]["statuses"] == []
    assert body["_explain"] == {}


@pytest.mark.parametrize(("name", "call"), SURFACES, ids=SURFACE_IDS)
def test_nothing_is_truncated_quietly_at_this_scale(
    client: TestClient, seeded: psycopg.Connection, name: str, call: dict[str, Any]
) -> None:
    """The fixture is inside the cap, so no bound is claimed. The over-cap arm is the
    integration tier's, where a population big enough to cross it can be seeded."""
    _prepare(name, seeded)
    body = _call(client, call, explain="true").json()
    codes = {item["code"] for item in body["meta"]["warnings"]}

    assert "explain_inline_truncated" not in codes


@pytest.mark.parametrize("scope", ["guest", "agent"])
def test_the_flag_is_reachable_by_every_principal_the_host_endpoint_is(
    client: TestClient, guest_client: TestClient, agent_client: TestClient, scope: str
) -> None:
    """DR-63 adds no gate of its own: a parameter with its own auth answer would be a second,
    undeclared access rule on a surface the matrix already covers."""
    caller = {"guest": guest_client, "agent": agent_client}[scope]

    response = caller.get(f"/v1/wells/{EXAMPLE_API10}", params={"explain": "true"})

    assert response.status_code == 200
    assert response.json()["_explain"]


def test_the_document_declares_the_parameters_on_every_surface_that_takes_them(
    client: TestClient,
) -> None:
    document = client.get("/openapi.json").json()

    for path in DECLARED_PATHS:
        names = {item["name"] for item in document["paths"][path]["get"]["parameters"]}
        assert {"explain", "explain_depth"} <= names, path


def test_every_new_parameter_carries_its_semantics(client: TestClient) -> None:
    """A-8: the C9 pane renders WHAT from the description, WHY and SEE from the bound term,
    and SO from here. A parameter with no entry renders as unannotated, which is a real state
    but not one a parameter added on purpose should be in."""
    document = client.get("/openapi.json").json()
    annotated: dict[str, set[str]] = {}
    for path in DECLARED_PATHS:
        operation = document["paths"][path]["get"]
        annotated[path] = set(operation.get("x-glasswell-semantics", {}))

    for path, names in annotated.items():
        assert {"explain", "explain_depth"} <= names, path

    explain_semantics = document["paths"]["/v1/explain"]["get"]["x-glasswell-semantics"]
    assert {"h", "depth", "format"} <= set(explain_semantics)


@pytest.mark.parametrize(("name", "call"), SURFACES, ids=SURFACE_IDS)
def test_the_block_stays_outside_the_population_the_r6_walker_reads(
    client: TestClient, seeded: psycopg.Connection, name: str, call: dict[str, Any]
) -> None:
    """The placement is load-bearing, not convenient.

    A chain carries a graph depth, a recorded row count and a manifest byte length, and none of
    the three is a served figure — they are exempted at `/chains/*/...` on /v1/explain's own
    response. Inside `data` they would need the same exemptions again under every host surface,
    and allowlist breadth is precisely what turns the R6 gate into decoration (A-2's minimality
    rule). The second assertion is what stops this from being a claim: it shows the walker does
    call those numbers naked, so `data` staying clean is a consequence of where the block sits.
    """
    _prepare(name, seeded)
    body = _call(client, call, explain="true").json()
    data = body["data"] if isinstance(body["data"], dict) else {"rows": body["data"]}

    assert naked_numbers(body["data"]) == []
    assert naked_numbers({**data, "_explain": body["_explain"]}), (
        "the chain carries no number the walker objects to, so this proves nothing"
    )


def test_a_handle_that_does_not_resolve_is_named_rather_than_dropped() -> None:
    """R6 says every served handle resolves; when one does not, the honest answer is to say
    which and why. Failing the whole request would let an optional diagnostic flag take down
    a working figure, which §9.2 forbids in the same breath as it adds the block."""
    figure_object = figure("1", unit="ft", derivation="drv_gone", selector="col=x")

    envelope = attach_lineage(
        {"length_ft": figure_object},
        as_of=None,
        request_id="01TEST",
        explain=lambda handles: InlinedExplain(
            chains={}, unresolved=dict.fromkeys(handles, "derivation_swept")
        ),
    )
    body = envelope.to_dict()
    warning = next(
        item for item in body["meta"]["warnings"] if item["code"] == "explain_unresolved"
    )

    assert body["_explain"] == {}
    assert figure_object.handle in warning["detail"]
    assert "derivation_swept" in warning["detail"]
    assert body["data"]["length_ft"]["value"] == "1"


def test_the_converged_link_is_the_link_the_router_used_to_author(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """gate-apix ADV-1's fix must not move the published link: the envelope now builds what
    `/v1/derivations/{id}` and the vintages pair hand-built, byte for byte. The page link is
    asserted against the page's own promotions rather than pinned to the one seeded handle,
    and a second promotion is seeded mid-test so the assertion is proven to survive fixture
    growth instead of depending on it (RN-2)."""
    derivation = client.get(f"/v1/derivations/{EXAMPLE_DERIVATION_ID}").json()
    vintage = client.get(f"/v1/vintages/{EXAMPLE_VINTAGE_ID}").json()

    expected = f"/v1/explain?h={EXAMPLE_DERIVATION_ID}&depth=full"
    assert derivation["links"]["explain"] == expected
    assert vintage["links"]["explain"] == expected

    def page_link_built_by_hand() -> str:
        page = client.get("/v1/vintages").json()
        promotions = [row["promotion_derivation_id"] for row in page["data"]]
        distinct = list(dict.fromkeys(handle for handle in promotions if handle))
        assert distinct, "the page must carry at least one promotion handle"
        hand_built = "/v1/explain?" + "&".join(f"h={handle}" for handle in distinct)
        assert page["links"]["explain"] == f"{hand_built}&depth=full"
        return page["links"]["explain"]

    assert page_link_built_by_hand() == expected

    second = seed_derivation(seeded, partition={"source_id": "tx_pdq_dsv"})
    open_vintage(
        seeded,
        source_id="tx_pdq_dsv",
        vintage_date=date(2026, 8, 3),
        manifest_ids=[],
        opened_at=datetime(2026, 8, 3, 5, 2, 11, tzinfo=UTC),
        promotion_derivation_id=second,
        rows_examined=5,
        rows_appended=5,
    )

    grown = page_link_built_by_hand()
    assert second != EXAMPLE_DERIVATION_ID
    assert f"h={second}" in grown
    assert f"h={EXAMPLE_DERIVATION_ID}" in grown


def test_a_vintage_with_no_promotion_inlines_nothing_and_links_nothing(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """No handle, no carrier: the link is null and the block is empty, and neither invents a
    handle the record does not carry."""
    open_vintage(
        seeded,
        source_id="tx_pdq_dsv",
        vintage_date=date(2026, 8, 2),
        manifest_ids=[],
        opened_at=datetime(2026, 8, 2, 5, 2, 11, tzinfo=UTC),
        promotion_derivation_id=None,
        rows_examined=7,
        rows_appended=3,
    )

    body = client.get(
        "/v1/vintages/vin_tx_pdq_dsv_2026-08-02", params={"explain": "true"}
    ).json()

    assert "_lineage" not in body["data"]
    assert body["links"]["explain"] is None
    assert body["_explain"] == {}


def test_the_envelope_schema_publishes_the_optional_block(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    envelopes = [
        name for name in document["components"]["schemas"] if name.startswith("EnvelopeModel")
    ]

    assert envelopes
    assert all(
        "_explain" in document["components"]["schemas"][name]["properties"] for name in envelopes
    )
    assert all(
        "_explain" not in document["components"]["schemas"][name].get("required", ())
        for name in envelopes
    )
