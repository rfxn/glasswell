"""DR-64: `GET /v1/explain?format=dot`, the graph export SB-07 §9.4 declares.

§9.4's request row reads `format=json|dot`. `json` shipped in P0 and `dot` did not, so the
published `Literal["json"]` said "Only json ships in this slice" while the endpoint's own
spec row named two. This closes the second half.

The body is checked against the DOT grammar (`dotgrammar.py`), never against a substring: a
truncated graph, an unbalanced brace and an unterminated label all contain the word `digraph`.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from glasswell.api.errors import TYPE_BASE
from glasswell.api.examples import EXAMPLE_API10, EXAMPLE_DERIVATION_ID, EXAMPLE_MANIFEST_ID
from glasswell.lineage.explain import (
    DOT_MEDIA_TYPE,
    Chain,
    ChainEdge,
    ChainNode,
    to_dot,
)
from tests.contract.dotgrammar import parse


def a_production_handle(client: TestClient) -> str:
    return client.get(f"/v1/wells/{EXAMPLE_API10}/production").json()["data"]["_lineage"][
        "series.oil_bbl"
    ]


def dot(client: TestClient, **params: object) -> str:
    response = client.get("/v1/explain", params={"format": "dot", **params})
    assert response.status_code == 200, response.text
    return response.text


def json_chains(client: TestClient, **params: object) -> list[dict]:
    return client.get("/v1/explain", params=params).json()["data"]["chains"]


def test_the_export_is_valid_dot(client: TestClient) -> None:
    graph = parse(dot(client, h=a_production_handle(client), depth="full"))

    assert graph.directed is True
    assert graph.nodes


def test_it_is_served_as_graphviz_and_not_as_json(client: TestClient) -> None:
    response = client.get(
        "/v1/explain", params={"h": EXAMPLE_DERIVATION_ID, "format": "dot"}
    )

    assert response.headers["content-type"].startswith(DOT_MEDIA_TYPE)


def test_every_chain_node_reaches_the_graph_as_a_node(client: TestClient) -> None:
    """The two renderings answer to one resolution — the graph is not a second traversal."""
    handle = a_production_handle(client)
    chain = json_chains(client, h=handle, depth="full")[0]

    graph = parse(dot(client, h=handle, depth="full"))

    assert {node["id"] for node in chain["nodes"]} <= set(graph.nodes)
    assert graph.nodes[EXAMPLE_MANIFEST_ID]["type"] == "manifest"
    assert graph.nodes[chain["root"]]["type"] == "derivation"


def test_a_cited_conformance_rule_is_a_node_of_its_own(client: TestClient) -> None:
    """R8: the rule that shaped a derivation is part of the picture, not a field inside it."""
    handle = a_production_handle(client)
    chain = json_chains(client, h=handle, depth="full")[0]
    cited = {
        rule["rule_id"]
        for node in chain["nodes"]
        for rule in node.get("conformance_rules", ())
    }

    graph = parse(dot(client, h=handle, depth="full"))

    assert cited
    assert cited <= set(graph.nodes)
    assert all(graph.nodes[rule_id]["type"] == "rule" for rule_id in cited)


def test_every_edge_carries_the_role_the_chain_recorded(client: TestClient) -> None:
    handle = a_production_handle(client)
    chain = json_chains(client, h=handle, depth="full")[0]

    graph = parse(dot(client, h=handle, depth="full"))

    for edge in chain["edges"]:
        assert graph.edge(edge["from"], edge["to"])["role"] == edge["role"]
    assert all(attributes.get("role") for _, _, attributes in graph.edges)


def test_a_rule_edge_is_typed_as_a_rule_and_not_as_an_input(client: TestClient) -> None:
    handle = a_production_handle(client)
    chain = json_chains(client, h=handle, depth="full")[0]
    root = chain["root"]
    cited = sorted(
        rule["rule_id"]
        for node in chain["nodes"]
        if node["id"] == root
        for rule in node.get("conformance_rules", ())
    )

    graph = parse(dot(client, h=handle, depth="full"))

    assert cited
    assert all(graph.edge(root, rule_id)["role"] == "rule" for rule_id in cited)


def test_several_handles_render_into_one_graph(client: TestClient) -> None:
    handle = a_production_handle(client)

    graph = parse(_multi(client, [handle, EXAMPLE_DERIVATION_ID]))

    assert EXAMPLE_DERIVATION_ID in graph.nodes
    assert EXAMPLE_MANIFEST_ID in graph.nodes


def _multi(client: TestClient, handles: list[str]) -> str:
    response = client.get(
        "/v1/explain",
        params=[("h", handle) for handle in handles] + [("depth", "full"), ("format", "dot")],
    )
    assert response.status_code == 200, response.text
    return response.text


def test_the_handle_cap_is_the_same_cap_in_either_format(client: TestClient) -> None:
    response = client.get(
        "/v1/explain",
        params=[("h", EXAMPLE_DERIVATION_ID)] * 21 + [("format", "dot")],
    )

    assert response.status_code == 422
    assert response.json()["type"] == f"{TYPE_BASE}/validation_failed"


def test_the_depth_grammar_is_the_same_grammar_in_either_format(client: TestClient) -> None:
    over = client.get(
        "/v1/explain", params={"h": EXAMPLE_DERIVATION_ID, "depth": "9", "format": "dot"}
    )
    unreadable = client.get(
        "/v1/explain", params={"h": EXAMPLE_DERIVATION_ID, "depth": "deep", "format": "dot"}
    )

    assert over.status_code == 422
    assert unreadable.status_code == 422
    assert parse(dot(client, h=EXAMPLE_DERIVATION_ID, depth="1")).nodes


def test_an_unresolvable_handle_still_gets_the_spine_error_and_not_a_broken_graph(
    client: TestClient,
) -> None:
    response = client.get("/v1/explain", params={"h": "drv_nothinghere", "format": "dot"})

    assert response.status_code == 404
    assert response.json()["type"] == f"{TYPE_BASE}/lineage_unresolved"


def test_a_format_outside_the_declared_set_is_refused(client: TestClient) -> None:
    response = client.get(
        "/v1/explain", params={"h": EXAMPLE_DERIVATION_ID, "format": "svg"}
    )

    assert response.status_code == 422
    assert response.json()["type"] == f"{TYPE_BASE}/validation_failed"
    assert any(item["pointer"].endswith("/format") for item in response.json()["errors"])


HOSTILE_DATASET = 'marts."well_month"\\allocated'
HOSTILE_KEY = "PDQ\nDSV.zip"


def _hostile_chain() -> Chain:
    """A chain whose strings carry the three bytes that end a DOT id early.

    Nothing in the seeded fixture contains a quote, a backslash or a newline, so every
    assertion above would stay green with the escaping removed entirely. Dataset names,
    source keys and operator strings are regulator-supplied and none of the three is
    impossible in them — this is the arm that makes the escaping load-bearing (N-1).
    """
    return Chain(
        handle="h",
        root="drv_hostile",
        depth=1,
        truncated=False,
        as_of_vintage=date(2026, 8, 1),
        nodes=[
            ChainNode(
                id="drv_hostile",
                type="derivation",
                explanation="x.",
                attributes={
                    "operation": "alloc.apply",
                    "output": {"dataset": HOSTILE_DATASET},
                    "conformance_rules": [{"rule_id": "cr_tx_lease_key_1"}],
                },
            ),
            ChainNode(
                id="man_hostile",
                type="manifest",
                explanation="y.",
                attributes={"source_id": "tx_pdq_dsv", "source_key": HOSTILE_KEY},
            ),
        ],
        edges=[
            ChainEdge(
                source="drv_hostile",
                target="man_hostile",
                role="primary",
                as_of_vintage=date(2026, 8, 1),
            )
        ],
        terminals=["man_hostile"],
        recipe=None,
        warnings=[],
    )


def test_a_quote_or_a_backslash_in_a_label_does_not_end_the_id_early() -> None:
    graph = parse(to_dot([_hostile_chain()]))

    assert set(graph.nodes) == {"drv_hostile", "man_hostile", "cr_tx_lease_key_1"}
    assert graph.nodes["drv_hostile"]["label"] == f"alloc.apply\\n{HOSTILE_DATASET}"
    assert graph.edge("drv_hostile", "man_hostile")["as_of_vintage"] == "2026-08-01"


def test_a_newline_in_a_label_cannot_break_the_statement_it_sits_in() -> None:
    """A raw newline inside a quoted id is legal DOT but makes the body unreadable line by
    line; the language's own `\\n` is what a label break is written as."""
    body = to_dot([_hostile_chain()])

    assert parse(body).nodes["man_hostile"]["label"] == "tx_pdq_dsv\\nPDQ DSV.zip"
    assert len(body.splitlines()) == 8


def test_the_document_publishes_both_formats_and_the_graphviz_media_type(
    client: TestClient,
) -> None:
    operation = client.get("/openapi.json").json()["paths"]["/v1/explain"]["get"]
    parameter = next(item for item in operation["parameters"] if item["name"] == "format")

    assert set(parameter["schema"]["enum"]) == {"json", "dot"}
    assert DOT_MEDIA_TYPE in operation["responses"]["200"]["content"]
