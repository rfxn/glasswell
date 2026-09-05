"""The DOT gate's own gate: a parser that accepts everything proves nothing about `to_dot`.

Every rejection below is a way `format=dot` could ship broken while a substring assertion
stayed green (N-1: before trusting a gate, ask what it makes impossible). The escaping tests at
the foot are the other half of the same question, read off `to_dot`'s output rather than off a
served response, so they need no app and no database.
"""

from __future__ import annotations

from datetime import date

import pytest

from glasswell.lineage.explain import Chain, ChainEdge, ChainNode, to_dot
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
