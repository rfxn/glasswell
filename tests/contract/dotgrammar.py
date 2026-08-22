"""A DOT parser, so `format=dot` is checked against the grammar and not against a substring.

`assert "digraph" in body` passes for a truncated graph, an unbalanced brace and an
unterminated quoted label. This is the graphviz DOT language as published — tokenizer plus
recursive descent over `graph`, `stmt_list`, `node_stmt`, `edge_stmt`, `attr_list`,
`subgraph` — and it raises on anything the grammar does not admit.

Written here rather than taken from PyPI because the contract tier has no parser dependency
and `dot(1)` is not a test-host guarantee; written as a parser rather than a regex because
`test_dotgrammar.py` has to be able to prove it rejects, and a gate nobody can make fail is
not a gate (N-1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import pairwise

KEYWORDS = frozenset({"graph", "digraph", "strict", "node", "edge", "subgraph"})

_NUMERAL = re.compile(r"-?(\.[0-9]+|[0-9]+(\.[0-9]*)?)")
_NAME = re.compile(r"[A-Za-z-ÿ_][A-Za-z-ÿ_0-9]*")


class DotSyntaxError(Exception):
    """The body is not DOT. Carries the offset so a failure names where it stopped."""

    def __init__(self, message: str, offset: int) -> None:
        super().__init__(f"{message} at offset {offset}")
        self.offset = offset


@dataclass(frozen=True, slots=True)
class Token:
    kind: str
    value: str
    offset: int


@dataclass
class Graph:
    directed: bool
    strict: bool
    name: str | None
    nodes: dict[str, dict[str, str]] = field(default_factory=dict)
    edges: list[tuple[str, str, dict[str, str]]] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)

    def edge(self, source: str, target: str) -> dict[str, str]:
        for tail, head, attributes in self.edges:
            if (tail, head) == (source, target):
                return attributes
        raise KeyError(f"no edge {source} -> {target}")


def parse(text: str) -> Graph:
    """The published DOT grammar, or `DotSyntaxError`."""
    return _Parser(_tokenize(text)).graph()


def _tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character.isspace():
            index += 1
            continue
        if text.startswith("//", index) or character == "#":
            index = text.find("\n", index)
            if index == -1:
                break
            continue
        if text.startswith("/*", index):
            closing = text.find("*/", index + 2)
            if closing == -1:
                raise DotSyntaxError("unterminated comment", index)
            index = closing + 2
            continue
        if character == '"':
            value, index = _quoted(text, index)
            tokens.append(Token("id", value, index))
            continue
        if text.startswith("->", index) or text.startswith("--", index):
            tokens.append(Token("edgeop", text[index : index + 2], index))
            index += 2
            continue
        if character in "{}[];,=:":
            tokens.append(Token(character, character, index))
            index += 1
            continue
        numeral = _NUMERAL.match(text, index)
        if numeral is not None:
            tokens.append(Token("id", numeral.group(), index))
            index = numeral.end()
            continue
        name = _NAME.match(text, index)
        if name is None:
            raise DotSyntaxError(f"unexpected character {character!r}", index)
        word = name.group()
        kind = "keyword" if word.lower() in KEYWORDS else "id"
        tokens.append(Token(kind, word, index))
        index = name.end()
    tokens.append(Token("eof", "", length))
    return tokens


def _quoted(text: str, start: int) -> tuple[str, int]:
    parts: list[str] = []
    index = start + 1
    while index < len(text):
        character = text[index]
        if character == "\\":
            if index + 1 >= len(text):
                raise DotSyntaxError("trailing escape in a quoted id", index)
            following = text[index + 1]
            # DOT keeps `\n` and friends verbatim; only `\"` and `\\` collapse.
            parts.append(following if following in '"\\' else character + following)
            index += 2
            continue
        if character == '"':
            return "".join(parts), index + 1
        parts.append(character)
        index += 1
    raise DotSyntaxError("unterminated quoted id", start)


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._at = 0

    def graph(self) -> Graph:
        strict = self._take_keyword("strict")
        if self._peek().kind != "keyword" or self._peek().value.lower() not in {
            "graph",
            "digraph",
        }:
            raise DotSyntaxError("expected 'graph' or 'digraph'", self._peek().offset)
        directed = self._next().value.lower() == "digraph"
        name = self._next().value if self._peek().kind == "id" else None
        graph = Graph(directed=directed, strict=strict, name=name)
        self._expect("{")
        self._statements(graph)
        self._expect("}")
        if self._peek().kind != "eof":
            raise DotSyntaxError("trailing input after the closing brace", self._peek().offset)
        return graph

    def _statements(self, graph: Graph) -> None:
        while self._peek().kind not in {"}", "eof"}:
            self._statement(graph)
            while self._peek().kind == ";":
                self._next()
        if self._peek().kind == "eof":
            raise DotSyntaxError("unclosed graph body", self._peek().offset)

    def _statement(self, graph: Graph) -> None:
        token = self._peek()
        if token.kind in {"{", "keyword"} and (
            token.kind == "{" or token.value.lower() == "subgraph"
        ):
            self._subgraph(graph)
            return
        if token.kind == "keyword" and token.value.lower() in {"graph", "node", "edge"}:
            self._next()
            self._attributes()
            return
        if token.kind != "id":
            raise DotSyntaxError(f"unexpected {token.value!r} in a statement", token.offset)
        name = self._node_id()
        if self._peek().kind == "=":
            self._next()
            value = self._expect("id").value
            graph.attributes[name] = value
            return
        if self._peek().kind == "edgeop":
            self._edge(graph, name)
            return
        graph.nodes.setdefault(name, {}).update(self._attributes())

    def _subgraph(self, graph: Graph) -> None:
        if self._peek().kind == "keyword":
            self._next()
            if self._peek().kind == "id":
                self._next()
        self._expect("{")
        self._statements(graph)
        self._expect("}")

    def _edge(self, graph: Graph, tail: str) -> None:
        hops = [tail]
        while self._peek().kind == "edgeop":
            operator = self._next()
            if (operator.value == "->") != graph.directed:
                raise DotSyntaxError(
                    f"{operator.value!r} is not the edge operator of this graph kind",
                    operator.offset,
                )
            if self._peek().kind != "id":
                raise DotSyntaxError("expected a node after the edge operator", self._peek().offset)
            hops.append(self._node_id())
        attributes = self._attributes()
        for source, target in pairwise(hops):
            graph.nodes.setdefault(source, {})
            graph.nodes.setdefault(target, {})
            graph.edges.append((source, target, dict(attributes)))

    def _node_id(self) -> str:
        name = self._expect("id").value
        while self._peek().kind == ":":
            self._next()
            self._expect("id")
        return name

    def _attributes(self) -> dict[str, str]:
        collected: dict[str, str] = {}
        while self._peek().kind == "[":
            self._next()
            while self._peek().kind != "]":
                key = self._expect("id").value
                self._expect("=")
                collected[key] = self._expect("id").value
                if self._peek().kind in {",", ";"}:
                    self._next()
            self._expect("]")
        return collected

    def _peek(self) -> Token:
        return self._tokens[self._at]

    def _next(self) -> Token:
        token = self._tokens[self._at]
        self._at += 1
        return token

    def _take_keyword(self, word: str) -> bool:
        token = self._peek()
        if token.kind == "keyword" and token.value.lower() == word:
            self._next()
            return True
        return False

    def _expect(self, kind: str) -> Token:
        token = self._peek()
        if token.kind != kind:
            raise DotSyntaxError(f"expected {kind}, found {token.value or 'end of input'!r}",
                                 token.offset)
        return self._next()
