"""Chain resolution (SB-07 §9.3): a served figure walked back to the bytes it came from."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Literal, Protocol

import psycopg
from psycopg.rows import dict_row

from glasswell.lineage.errors import LineageUnresolved
from glasswell.lineage.ids import parse_handle
from glasswell.lineage.models import Frozen
from glasswell.lineage.selector_registry import validate_selector
from glasswell.lineage.serialization import json_ready

MAX_DEPTH = 8
# SB-07 §9.4's request grammar: how many `h=` a caller may send in one call. It is not a
# statement about how many chains may be resolved, and `?explain=true` does not raise it.
MAX_HANDLES = 20
DEFAULT_DEPTH = 3
DOT_MEDIA_TYPE = "text/vnd.graphviz"

NodeType = Literal["derivation", "manifest", "rule", "model", "external"]


class ChainNode(Frozen):
    id: str
    type: NodeType
    attributes: Mapping[str, Any]
    explanation: str


class ChainEdge(Frozen):
    source: str
    target: str
    role: str
    as_of_vintage: date | None = None


class Chain(Frozen):
    handle: str
    root: str
    depth: int
    truncated: bool
    as_of_vintage: date | None
    nodes: Sequence[ChainNode]
    edges: Sequence[ChainEdge]
    terminals: Sequence[str]
    recipe: str | None
    warnings: Sequence[str]


class LineageGraph(Protocol):
    def edges(self, root: str, depth: int) -> list[Mapping[str, Any]]: ...
    def derivations(self, ids: Sequence[str]) -> dict[str, Mapping[str, Any]]: ...
    def manifests(self, ids: Sequence[str]) -> dict[str, Mapping[str, Any]]: ...
    def with_inputs(self, ids: Sequence[str]) -> set[str]: ...


_EDGES = """
with recursive walk (derivation_id, ord, kind, ref_id, selector, as_of_vintage, role, level) as (
    select i.derivation_id, i.ord, i.kind, i.ref_id, i.selector, i.as_of_vintage, i.role, 1
      from lineage.derivation_inputs i
     where i.derivation_id = %(root)s
    union all
    select i.derivation_id, i.ord, i.kind, i.ref_id, i.selector, i.as_of_vintage, i.role,
           w.level + 1
      from lineage.derivation_inputs i
      join walk w on w.kind = 'derivation' and i.derivation_id = w.ref_id
     where w.level < %(depth)s)
select derivation_id, ord, kind, ref_id, selector, as_of_vintage, role, level
  from walk
 order by level, derivation_id, ord
"""

_DERIVATIONS = """
select derivation_id, operation, output_store, output_dataset, output_partition, output_locator,
       output_sha256, output_rows, code_version, params_hash, created_vintage, model_id,
       recipe_id, determinism_class, status
  from lineage.derivations
 where derivation_id = any(%s)
"""

_RULES = """
select dr.derivation_id, dr.rule_id, dr.applied_rows, cr.rule_family, cr.rule_kind
  from lineage.derivation_rules dr
  left join lineage.conformance_rules cr on cr.rule_id = dr.rule_id
 where dr.derivation_id = any(%s)
 order by dr.rule_id
"""

_MANIFESTS = """
select manifest_id, source_id, source_key, sha256, bytes, fetched_at, fetch_vintage,
       acquisition_method, acquisition_url, supersedes_manifest_id, redistributable
  from lineage.manifests
 where manifest_id = any(%s)
"""


class PostgresGraph:
    """The derivation graph as a recursive CTE over `lineage.derivation_inputs`."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def edges(self, root: str, depth: int) -> list[Mapping[str, Any]]:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(_EDGES, {"root": root, "depth": depth})
            return [dict(row) for row in cursor.fetchall()]

    def derivations(self, ids: Sequence[str]) -> dict[str, Mapping[str, Any]]:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(_DERIVATIONS, (list(ids),))
            found = {row["derivation_id"]: dict(row) | {"rules": []} for row in cursor.fetchall()}
            cursor.execute(_RULES, (list(found),))
            for row in cursor.fetchall():
                found[row["derivation_id"]]["rules"].append(
                    {
                        "rule_id": row["rule_id"],
                        "family": row["rule_family"],
                        "kind": row["rule_kind"],
                        "applied_rows": row["applied_rows"],
                    }
                )
        return found

    def manifests(self, ids: Sequence[str]) -> dict[str, Mapping[str, Any]]:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(_MANIFESTS, (list(ids),))
            return {row["manifest_id"]: dict(row) for row in cursor.fetchall()}

    def with_inputs(self, ids: Sequence[str]) -> set[str]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "select distinct derivation_id from lineage.derivation_inputs"
                " where derivation_id = any(%s)",
                (list(ids),),
            )
            return {row[0] for row in cursor.fetchall()}

    def validate_selector(
        self, derivation: Mapping[str, Any], selector: str, *, handle: str
    ) -> None:
        validate_selector(self._connection, derivation, selector, handle=handle)


def _partition_text(partition: Mapping[str, Any]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(partition.items()))


def _derivation_node(row: Mapping[str, Any]) -> ChainNode:
    rules = list(row.get("rules") or ())
    attributes = {
        "operation": row["operation"],
        "output": {
            "store": row["output_store"],
            "dataset": row["output_dataset"],
            "partition": dict(row["output_partition"] or {}),
            "sha256": row["output_sha256"],
            "rows": row["output_rows"],
        },
        "code_version": row["code_version"],
        "params_hash": row["params_hash"],
        "created_vintage": row["created_vintage"],
        "model_id": row["model_id"],
        "determinism_class": row["determinism_class"],
        "recipe_id": row["recipe_id"],
        "status": row["status"],
        "conformance_rules": [
            {"rule_id": r["rule_id"], "family": r.get("family"), "kind": r.get("kind")}
            for r in rules
        ],
    }
    sentence = f"{row['operation']} produced {row['output_dataset']}"
    partition = _partition_text(dict(row["output_partition"] or {}))
    if partition:
        sentence += f" ({partition})"
    if row["output_rows"] is not None:
        sentence += f", {row['output_rows']} rows"
    sentence += f", at code {row['code_version']}"
    if rules:
        sentence += "; conformance rules " + ", ".join(r["rule_id"] for r in rules)
    return ChainNode(
        id=row["derivation_id"],
        type="derivation",
        attributes=attributes,
        explanation=sentence + ".",
    )


def _manifest_node(row: Mapping[str, Any]) -> ChainNode:
    attributes = {
        "source_id": row["source_id"],
        "source_key": row["source_key"],
        "sha256": row["sha256"],
        "bytes": row["bytes"],
        "fetched_at": row["fetched_at"],
        "fetch_vintage": row["fetch_vintage"],
        "acquisition_method": row["acquisition_method"],
        "acquisition_url": row["acquisition_url"],
        "supersedes": row["supersedes_manifest_id"],
        "redistributable": row["redistributable"],
    }
    sentence = (
        f"{row['source_id']} {row['source_key']}, fetched "
        f"{row['fetched_at'].isoformat()} via {row['acquisition_method']}; "
        f"sha256 {row['sha256'][:12]}."
    )
    return ChainNode(
        id=row["manifest_id"], type="manifest", attributes=attributes, explanation=sentence
    )


def _resolve_depth(depth: int | Literal["full"], warnings: list[str]) -> int:
    if depth == "full":
        return MAX_DEPTH
    limit = int(depth)
    if limit < 1:
        raise ValueError(f"depth must be at least 1, not {depth!r}")
    if limit > MAX_DEPTH:
        warnings.append(f"requested depth {limit} exceeds the maximum depth {MAX_DEPTH}")
        return MAX_DEPTH
    return limit


def resolve_chain_from(
    graph: LineageGraph, handle: str, *, depth: int | Literal["full"] = DEFAULT_DEPTH
) -> Chain:
    """Walk the derivation graph from a handle to its terminal manifests."""
    parsed = parse_handle(handle)
    root = parsed.derivation_id
    warnings: list[str] = []
    limit = _resolve_depth(depth, warnings)

    rows = list(graph.edges(root, limit))
    derivation_rows = graph.derivations(
        [root, *dict.fromkeys(r["ref_id"] for r in rows if r["kind"] == "derivation")]
    )
    if root not in derivation_rows:
        raise LineageUnresolved(handle, reason="unknown_id")
    if parsed.selector is not None:
        validator = getattr(graph, "validate_selector", None)
        if validator is not None:
            validator(derivation_rows[root], parsed.selector, handle=handle)
    manifest_rows = graph.manifests(
        list(dict.fromkeys(r["ref_id"] for r in rows if r["kind"] == "manifest"))
    )

    adjacency: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        adjacency.setdefault(row["derivation_id"], []).append(row)

    # DR-83: `nodes` reads root-first, terminals last. Discovery order put a root's direct
    # manifest input mid-list, ahead of deeper derivations, and the walk §9.3 claims runs
    # *to* its terminal manifests — so derivations keep BFS order and terminals close the
    # list. `edges` remains the structural truth either way.
    derivation_nodes: list[ChainNode] = [_derivation_node(derivation_rows[root])]
    reference_nodes: list[ChainNode] = []
    manifest_nodes: list[ChainNode] = []
    edges: list[ChainEdge] = []
    terminals: list[str] = []
    seen = {root}
    queue = [root]
    while queue:
        parent = queue.pop(0)
        for row in sorted(adjacency.get(parent, ()), key=lambda r: r["ord"]):
            edges.append(
                ChainEdge(
                    source=parent,
                    target=row["ref_id"],
                    role=row["role"],
                    as_of_vintage=row["as_of_vintage"],
                )
            )
            reference = row["ref_id"]
            if reference in seen:
                continue
            seen.add(reference)
            if row["kind"] == "derivation":
                if reference not in derivation_rows:
                    raise LineageUnresolved(handle, reason="derivation_swept", last_resolved=parent)
                derivation_nodes.append(_derivation_node(derivation_rows[reference]))
                queue.append(reference)
            elif row["kind"] == "manifest":
                if reference not in manifest_rows:
                    raise LineageUnresolved(handle, reason="unknown_id", last_resolved=parent)
                manifest_nodes.append(_manifest_node(manifest_rows[reference]))
                terminals.append(reference)
            else:
                reference_nodes.append(
                    ChainNode(
                        id=reference,
                        type=row["kind"],
                        attributes={"role": row["role"]},
                        explanation=f"{row['kind']} reference {reference} cited as {row['role']}.",
                    )
                )
                warnings.append(f"{reference} is a {row['kind']} reference, not a manifest")
    nodes = derivation_nodes + reference_nodes + manifest_nodes

    frontier = [r["ref_id"] for r in rows if r["level"] == limit and r["kind"] == "derivation"]
    root_row = derivation_rows[root]
    return Chain(
        handle=handle,
        root=root,
        depth=max((r["level"] for r in rows), default=0),
        truncated=bool(graph.with_inputs(frontier)),
        as_of_vintage=root_row["created_vintage"],
        nodes=nodes,
        edges=edges,
        terminals=terminals,
        recipe=root_row["recipe_id"],
        warnings=warnings,
    )


def resolve_chain(
    connection: psycopg.Connection, handle: str, *, depth: int | Literal["full"] = DEFAULT_DEPTH
) -> Chain:
    """SB-07 §9.3 chain for one handle, read through the derivation graph."""
    return resolve_chain_from(PostgresGraph(connection), handle, depth=depth)


def resolve_chains(
    connection: psycopg.Connection,
    handles: Sequence[str],
    *,
    depth: int | Literal["full"] = DEFAULT_DEPTH,
) -> list[Chain]:
    """The `/v1/explain` path: 1 to 20 handles, one graph read each (SB-07 §9.4)."""
    if not handles:
        raise ValueError("at least one handle is required")
    if len(handles) > MAX_HANDLES:
        raise ValueError(f"at most {MAX_HANDLES} handles per request, not {len(handles)}")
    graph = PostgresGraph(connection)
    return [resolve_chain_from(graph, handle, depth=depth) for handle in handles]


_DOT_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_DOT_SHAPES: Mapping[str, str] = {
    "derivation": "box",
    "manifest": "note",
    "rule": "ellipse",
    "model": "component",
    "external": "octagon",
}


def to_dot(chains: Sequence[Chain]) -> str:
    """SB-07 §9.4's second rendering: one digraph over the same resolution `to_json` returns.

    Conformance rules become nodes rather than staying fields, because R8's claim is that a
    mapping decision is part of the picture; an edge typed `rule` is what makes it visible.
    """
    nodes: dict[str, dict[str, str]] = {}
    edges: dict[tuple[str, str], dict[str, str]] = {}
    for chain in chains:
        for node in chain.nodes:
            nodes.setdefault(node.id, _dot_node(node))
            for rule in node.attributes.get("conformance_rules") or ():
                rule_id = str(rule["rule_id"])
                nodes.setdefault(
                    rule_id,
                    {"type": "rule", "shape": _DOT_SHAPES["rule"], "label": _label(rule_id)},
                )
                edges.setdefault((node.id, rule_id), {"role": "rule", "style": "dashed"})
        for edge in chain.edges:
            attributes = {"role": edge.role}
            if edge.as_of_vintage is not None:
                attributes["as_of_vintage"] = edge.as_of_vintage.isoformat()
            edges.setdefault((edge.source, edge.target), attributes)

    lines = ["digraph lineage {", '  rankdir="LR";']
    lines += [f"  {_quote(name)} {_attributes(body)};" for name, body in nodes.items()]
    lines += [
        f"  {_quote(source)} -> {_quote(target)} {_attributes(body)};"
        for (source, target), body in edges.items()
    ]
    lines.append("}")
    return "\n".join(lines) + "\n"


def _dot_node(node: ChainNode) -> dict[str, str]:
    attributes = node.attributes
    if node.type == "derivation":
        output = attributes.get("output") or {}
        label = _label(
            str(attributes.get("operation") or node.id), str(output.get("dataset") or "")
        )
    elif node.type == "manifest":
        label = _label(
            str(attributes.get("source_id") or ""), str(attributes.get("source_key") or "")
        )
    else:
        label = _label(node.id)
    return {"type": node.type, "shape": _DOT_SHAPES.get(node.type, "box"), "label": label}


def _attributes(body: Mapping[str, str]) -> str:
    """`label` is pre-quoted; every other value is data and is quoted here."""
    rendered = ", ".join(
        f"{key}={value if key == 'label' else _quote(value)}" for key, value in body.items()
    )
    return f"[{rendered}]"


def _escape(value: str) -> str:
    return _DOT_CONTROL.sub(" ", value).replace("\\", "\\\\").replace('"', '\\"')


def _quote(value: str) -> str:
    return f'"{_escape(value)}"'


def _label(*parts: str) -> str:
    r"""A quoted DOT id whose line breaks are the language's `\n`, not bytes from the data."""
    return '"' + "\\n".join(_escape(part) for part in parts if part) + '"'


def to_json(chain: Chain) -> dict[str, Any]:
    """SB-07 §9.3 wire shape: graph for the agent, per-node prose for the drawer."""
    return json_ready(
        {
            "handle": chain.handle,
            "root": chain.root,
            "depth": chain.depth,
            "truncated": chain.truncated,
            "as_of_vintage": chain.as_of_vintage,
            "nodes": [
                {
                    "id": node.id,
                    "type": node.type,
                    **node.attributes,
                    "explanation": node.explanation,
                }
                for node in chain.nodes
            ],
            "edges": [
                {
                    "from": edge.source,
                    "to": edge.target,
                    "role": edge.role,
                    "as_of_vintage": edge.as_of_vintage,
                }
                for edge in chain.edges
            ],
            "terminals": list(chain.terminals),
            "recipe": chain.recipe,
            "warnings": list(chain.warnings),
        }
    )
