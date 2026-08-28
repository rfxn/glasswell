from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

import pytest

from glasswell.lineage.errors import InvalidHandle, InvalidSelector, LineageUnresolved
from glasswell.lineage.explain import MAX_DEPTH, resolve_chain_from, to_json

ROOT = "drv_promote001"
PARSE = "drv_parse0001"
FETCH = "drv_fetch0001"
MANIFEST = "man_9c3f0000"

HANDLE = f"{ROOT}#api10=3305301234&pm=2024-03&col=oil_bbl"


def derivation_row(
    identifier: str,
    operation: str,
    *,
    dataset: str,
    rules: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    return {
        "derivation_id": identifier,
        "operation": operation,
        "output_store": "postgres",
        "output_dataset": dataset,
        "output_partition": {"source_id": "nd_mpr_xlsx", "production_month": "2024-03"},
        "output_locator": "",
        "output_sha256": "a" * 64,
        "output_rows": 41822,
        "code_version": "git:9f2c1ab",
        "params_hash": "b" * 64,
        "created_vintage": date(2026, 8, 1),
        "model_id": None,
        "recipe_id": "rcp_5h2k",
        "determinism_class": "D1",
        "status": "ok",
        "rules": list(rules),
    }


MANIFEST_ROW = {
    "manifest_id": MANIFEST,
    "source_id": "nd_mpr_xlsx",
    "source_key": "2026_03.xlsx",
    "sha256": "c" * 64,
    "bytes": 3812345,
    "fetched_at": datetime(2026, 8, 1, 5, 2, 11, tzinfo=UTC),
    "fetch_vintage": date(2026, 8, 1),
    "acquisition_method": "https_get",
    "acquisition_url": "https://www.dmr.nd.gov/oilgas/mpr/2026_03.xlsx",
    "supersedes_manifest_id": None,
    "redistributable": False,
}


class FakeGraph:
    """Canned lineage graph: the tier split keeps chain assembly database-free (DIR-10)."""

    def __init__(
        self,
        edges: Sequence[Mapping[str, Any]],
        derivations: Mapping[str, Mapping[str, Any]],
        manifests: Mapping[str, Mapping[str, Any]] | None = None,
        with_inputs: Sequence[str] = (),
    ) -> None:
        self._edges = list(edges)
        self._derivations = dict(derivations)
        self._manifests = dict({MANIFEST: MANIFEST_ROW} if manifests is None else manifests)
        self._with_inputs = set(with_inputs)

    def edges(self, root: str, depth: int) -> list[Mapping[str, Any]]:
        return [e for e in self._edges if e["level"] <= depth and self._reachable(e, root, depth)]

    def _reachable(self, edge: Mapping[str, Any], root: str, depth: int) -> bool:
        reachable = {root}
        for _ in range(depth):
            reachable |= {
                e["ref_id"]
                for e in self._edges
                if e["derivation_id"] in reachable and e["kind"] == "derivation"
            }
        return edge["derivation_id"] in reachable

    def derivations(self, ids: Sequence[str]) -> dict[str, Mapping[str, Any]]:
        return {i: self._derivations[i] for i in ids if i in self._derivations}

    def manifests(self, ids: Sequence[str]) -> dict[str, Mapping[str, Any]]:
        return {i: self._manifests[i] for i in ids if i in self._manifests}

    def with_inputs(self, ids: Sequence[str]) -> set[str]:
        return {i for i in ids if i in self._with_inputs}

    def validate_selector(
        self, derivation: Mapping[str, Any], selector: str, *, handle: str
    ) -> None:
        return None


def edge(parent: str, ref: str, kind: str, level: int, ordinal: int = 0) -> dict[str, Any]:
    return {
        "derivation_id": parent,
        "ord": ordinal,
        "kind": kind,
        "ref_id": ref,
        "selector": None,
        "as_of_vintage": date(2026, 8, 1),
        "role": "primary",
        "level": level,
    }


def nd_graph() -> FakeGraph:
    return FakeGraph(
        edges=[
            edge(ROOT, PARSE, "derivation", 1),
            edge(PARSE, FETCH, "derivation", 2),
            edge(FETCH, MANIFEST, "manifest", 3),
        ],
        derivations={
            ROOT: derivation_row(
                ROOT,
                "canonical.promote",
                dataset="canonical.production_monthly",
                rules=[
                    {"rule_id": "cr_nd_units_1", "family": "cr_nd_units", "kind": "unit_conform"}
                ],
            ),
            PARSE: derivation_row(PARSE, "stage.parse", dataset="staging.nd_mpr_oil"),
            FETCH: derivation_row(FETCH, "raw.fetch", dataset="raw.nd_mpr_xlsx"),
        },
    )


def test_a_chain_resolves_to_nodes_edges_and_terminal_manifests():
    chain = resolve_chain_from(nd_graph(), HANDLE, depth="full")
    assert chain.handle == HANDLE
    assert chain.root == ROOT
    assert [node.id for node in chain.nodes] == [ROOT, PARSE, FETCH, MANIFEST]
    assert [(e.source, e.target) for e in chain.edges] == [
        (ROOT, PARSE),
        (PARSE, FETCH),
        (FETCH, MANIFEST),
    ]
    assert chain.terminals == [MANIFEST]
    assert chain.truncated is False
    assert chain.as_of_vintage == date(2026, 8, 1)
    assert chain.recipe == "rcp_5h2k"


def test_every_terminal_node_is_a_manifest():
    chain = resolve_chain_from(nd_graph(), HANDLE, depth="full")
    types = {node.id: node.type for node in chain.nodes}
    assert [types[terminal] for terminal in chain.terminals] == ["manifest"]


def test_every_node_carries_a_rendered_explanation_for_the_drawer():
    chain = resolve_chain_from(nd_graph(), HANDLE, depth="full")
    for node in chain.nodes:
        assert node.explanation
    manifest_node = next(node for node in chain.nodes if node.type == "manifest")
    assert "2026_03.xlsx" in manifest_node.explanation
    promote_node = next(node for node in chain.nodes if node.id == ROOT)
    assert "cr_nd_units_1" in promote_node.explanation


def test_depth_is_capped_at_eight():
    chain = resolve_chain_from(nd_graph(), HANDLE, depth=20)
    assert chain.depth <= MAX_DEPTH
    assert any("depth" in warning for warning in chain.warnings)


def test_truncated_is_set_when_the_depth_cap_bites():
    graph = FakeGraph(
        edges=[edge(ROOT, PARSE, "derivation", 1)],
        derivations={
            ROOT: derivation_row(ROOT, "canonical.promote", dataset="canonical.production_monthly"),
            PARSE: derivation_row(PARSE, "stage.parse", dataset="staging.nd_mpr_oil"),
        },
        with_inputs=[PARSE],
    )
    chain = resolve_chain_from(graph, HANDLE, depth=1)
    assert chain.depth == 1
    assert chain.truncated is True
    assert chain.terminals == []


def test_an_unknown_root_raises_lineage_unresolved():
    with pytest.raises(LineageUnresolved) as caught:
        resolve_chain_from(nd_graph(), "drv_missing0#col=oil_bbl")
    assert caught.value.code == "lineage_unresolved"
    assert caught.value.handle == "drv_missing0#col=oil_bbl"
    assert caught.value.reason == "unknown_id"
    assert caught.value.last_resolved is None


def test_an_unresolvable_input_names_the_last_resolvable_node():
    graph = FakeGraph(
        edges=[edge(ROOT, PARSE, "derivation", 1)],
        derivations={
            ROOT: derivation_row(ROOT, "canonical.promote", dataset="canonical.production_monthly")
        },
    )
    with pytest.raises(LineageUnresolved) as caught:
        resolve_chain_from(graph, HANDLE)
    assert caught.value.last_resolved == ROOT
    assert caught.value.reason == "derivation_swept"


def test_a_malformed_handle_is_rejected_before_any_traversal():
    with pytest.raises(InvalidHandle):
        resolve_chain_from(nd_graph(), "select 1")


def test_a_selector_cannot_pass_when_the_graph_has_no_validator():
    graph = nd_graph()
    object.__setattr__(graph, "validate_selector", None)

    with pytest.raises(InvalidSelector, match="validation is unavailable"):
        resolve_chain_from(graph, HANDLE)


def test_a_depth_below_one_is_refused():
    with pytest.raises(ValueError, match="depth"):
        resolve_chain_from(nd_graph(), HANDLE, depth=0)


def test_a_missing_manifest_names_the_derivation_that_cited_it():
    graph = FakeGraph(
        edges=[edge(ROOT, MANIFEST, "manifest", 1)],
        derivations={
            ROOT: derivation_row(ROOT, "canonical.promote", dataset="canonical.production_monthly")
        },
        manifests={},
    )
    with pytest.raises(LineageUnresolved) as caught:
        resolve_chain_from(graph, HANDLE)
    assert caught.value.reason == "unknown_id"
    assert caught.value.last_resolved == ROOT


def test_a_non_manifest_leaf_is_reported_rather_than_counted_as_a_terminal():
    graph = FakeGraph(
        edges=[edge(ROOT, "mdl_01j", "model", 1), edge(ROOT, "mdl_01j", "model", 1, ordinal=1)],
        derivations={
            ROOT: derivation_row(ROOT, "alloc.apply", dataset="marts.well_month_allocated")
        },
    )
    chain = resolve_chain_from(graph, HANDLE)
    assert [node.type for node in chain.nodes] == ["derivation", "model"]
    assert chain.terminals == []
    assert any("not a manifest" in warning for warning in chain.warnings)
    # The duplicate reference is one node with two edges, not two nodes.
    assert len(chain.edges) == 2


def test_chain_json_matches_the_sb07_9_3_shape():
    document = to_json(resolve_chain_from(nd_graph(), HANDLE, depth="full"))
    assert set(document) == {
        "handle",
        "root",
        "depth",
        "truncated",
        "as_of_vintage",
        "nodes",
        "edges",
        "terminals",
        "recipe",
        "warnings",
    }
    assert document["as_of_vintage"] == "2026-08-01"
    assert document["edges"][0]["from"] == ROOT
    assert document["edges"][0]["to"] == PARSE
    promote = document["nodes"][0]
    assert promote["type"] == "derivation"
    assert promote["operation"] == "canonical.promote"
    assert promote["output"]["dataset"] == "canonical.production_monthly"
    assert promote["conformance_rules"][0]["rule_id"] == "cr_nd_units_1"
    manifest = document["nodes"][-1]
    assert manifest["type"] == "manifest"
    assert manifest["fetched_at"] == "2026-08-01T05:02:11+00:00"
