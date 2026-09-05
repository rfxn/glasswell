"""The DOT gate's own gate: a parser that accepts everything proves nothing about `to_dot`.

Every rejection below is a way `format=dot` could ship broken while a substring assertion
stayed green (N-1: before trusting a gate, ask what it makes impossible).
"""

from __future__ import annotations

import pytest

from tests.contract.dotgrammar import DotSyntaxError, parse

WELL_FORMED = """
strict digraph lineage {
  rankdir="LR";
  node [shape=box];
  "drv_a" [type="derivation", label="canonical.promote"];
  "man_b" [type="manifest"];
  "drv_a" -> "man_b" [role="primary"];
}
"""


def test_it_reads_a_well_formed_graph() -> None:
    graph = parse(WELL_FORMED)

    assert graph.directed is True
    assert graph.strict is True
    assert graph.name == "lineage"
    assert graph.attributes["rankdir"] == "LR"
    assert set(graph.nodes) == {"drv_a", "man_b"}
    assert graph.nodes["drv_a"]["type"] == "derivation"
    assert graph.edge("drv_a", "man_b")["role"] == "primary"


def test_an_edge_chain_becomes_one_edge_per_hop() -> None:
    graph = parse('digraph g { "a" -> "b" -> "c" [role="primary"]; }')

    assert [(tail, head) for tail, head, _ in graph.edges] == [("a", "b"), ("b", "c")]


def test_a_subgraph_body_is_read_and_not_skipped() -> None:
    graph = parse('digraph g { subgraph cluster_0 { "a" [type="derivation"]; } "a" -> "b"; }')

    assert graph.nodes["a"]["type"] == "derivation"
    assert graph.edge("a", "b") == {}


def test_comments_and_numerals_are_ids_not_syntax_errors() -> None:
    graph = parse('digraph g { /* c */ "a" [rows=41822, weight=-0.5]; } // tail')

    assert graph.nodes["a"] == {"rows": "41822", "weight": "-0.5"}


@pytest.mark.parametrize(
    ("body", "why"),
    [
        ('digraph g { "a" -> "b" ', "unbalanced braces"),
        ('digraph g { "a [label="x"]; }', "unterminated quoted id"),
        ('graph g { "a" -> "b"; }', "-> in an undirected graph"),
        ('digraph g { -> "b"; }', "an edge with no tail"),
        ('digraph g { "a" -> ; }', "an edge with no head"),
        ('digraph g { "a" [label=]; }', "an attribute with no value"),
        ('digraph g { "a" [label="x"; }', "an unclosed attribute list"),
        ('lineage { "a"; }', "no graph keyword"),
        ('digraph g { "a"; } trailing', "input after the closing brace"),
        ('digraph g { "a" [label="x"] }}', "an extra closing brace"),
        ('digraph g { "a" [role="x"] ] }', "a stray closing bracket"),
        ('digraph g { subgraph cluster_0 { "a"; } ', "an unclosed subgraph"),
        ('digraph g { "a" @ "b"; }', "a character outside the language"),
    ],
)
def test_it_refuses_what_the_grammar_does_not_admit(body: str, why: str) -> None:
    with pytest.raises(DotSyntaxError):
        parse(body)

    assert why
