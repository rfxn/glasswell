"""DR-64: `GET /v1/explain?format=dot`, the graph export SB-07 §9.4 declares.

§9.4's request row reads `format=json|dot`. `json` shipped in P0 and `dot` did not, so the
published `Literal["json"]` said "Only json ships in this slice" while the endpoint's own
spec row named two. This closes the second half.

The body is checked against the DOT grammar (`dotgrammar.py`), never against a substring: a
truncated graph, an unbalanced brace and an unterminated label all contain the word `digraph`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from glasswell.api.errors import TYPE_BASE
from glasswell.api.examples import EXAMPLE_API10, EXAMPLE_DERIVATION_ID, EXAMPLE_MANIFEST_ID
from glasswell.lineage.explain import DOT_MEDIA_TYPE
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


def test_the_document_publishes_both_formats_and_the_graphviz_media_type(
    client: TestClient,
) -> None:
    operation = client.get("/openapi.json").json()["paths"]["/v1/explain"]["get"]
    parameter = next(item for item in operation["parameters"] if item["name"] == "format")

    assert set(parameter["schema"]["enum"]) == {"json", "dot"}
    assert DOT_MEDIA_TYPE in operation["responses"]["200"]["content"]
