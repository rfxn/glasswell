from __future__ import annotations

from typing import Any

import polars as pl
import pytest

from glasswell.lineage.conformance import PREDICATE_NODE_TYPES, _compile_predicate
from glasswell.lineage.errors import RuleSpecError

FRAME = pl.DataFrame(
    {
        "oil": [10, -5, None, 0],
        "days": [30, 31, 45, None],
        "stream": ["oil", "gas", "water", "flared"],
    }
)


def evaluate(node: Any) -> list[bool | None]:
    return FRAME.select(_compile_predicate(node).alias("keep"))["keep"].to_list()


def test_the_allowlist_is_exactly_the_seven_declared_node_types():
    assert set(PREDICATE_NODE_TYPES) == {
        "and",
        "or",
        "not",
        "cmp",
        "in",
        "between",
        "is_null",
    }


def test_cmp_compiles_to_a_polars_expression():
    assert evaluate({"cmp": [{"col": "oil"}, ">=", {"lit": 0}]}) == [True, False, None, True]


def test_and_or_and_not_compose():
    node = {
        "and": [
            {"cmp": [{"col": "oil"}, ">=", {"lit": 0}]},
            {"not": {"is_null": {"col": "days"}}},
        ]
    }
    assert evaluate(node) == [True, False, None, False]
    either = {"or": [{"is_null": {"col": "oil"}}, {"cmp": [{"col": "days"}, "==", {"lit": 31}]}]}
    assert evaluate(either) == [False, True, True, None]


def test_between_is_inclusive():
    assert evaluate({"between": [{"col": "days"}, {"lit": 0}, {"lit": 31}]}) == [
        True,
        True,
        False,
        None,
    ]


def test_in_matches_a_declared_option_list():
    assert evaluate({"in": [{"col": "stream"}, ["oil", "gas"]]}) == [True, True, False, False]


def test_is_null_reports_the_missing_rows():
    assert evaluate({"is_null": {"col": "oil"}}) == [False, False, True, False]


@pytest.mark.parametrize(
    "node",
    [
        {"eval": [{"col": "oil"}]},
        {"regex_match": [{"col": "stream"}, {"lit": ".*"}]},
        {"call": {"fn": "os.system"}},
        {"and": [{"cmp": [{"col": "oil"}, ">=", {"lit": 0}]}], "or": []},
        {},
        "__import__('os').system('id')",
        ["and", []],
        42,
        None,
    ],
)
def test_any_node_outside_the_allowlist_is_rejected(node):
    with pytest.raises(RuleSpecError):
        _compile_predicate(node)


@pytest.mark.parametrize(
    "leaf",
    [
        {"lit": {"__import__": "os"}},
        {"lit": ["os", "system"]},
        {"col": "__import__('os')"},
        {"col": "oil.__class__"},
        {"col": "1oil"},
        {"col": ""},
        {"attr": "os.system"},
        {"col": "oil", "lit": 1},
        {"getattr": {"col": "oil"}},
        "oil",
    ],
)
def test_a_leaf_that_is_not_a_plain_column_or_scalar_is_rejected(leaf):
    with pytest.raises(RuleSpecError):
        _compile_predicate({"is_null": leaf})


def test_an_unknown_comparison_operator_is_rejected():
    with pytest.raises(RuleSpecError):
        _compile_predicate({"cmp": [{"col": "oil"}, "matches", {"lit": 0}]})


def test_a_malformed_node_payload_is_rejected_before_compilation():
    with pytest.raises(RuleSpecError):
        _compile_predicate({"cmp": [{"col": "oil"}, ">="]})
    with pytest.raises(RuleSpecError):
        _compile_predicate({"between": [{"col": "days"}, {"lit": 0}]})
    with pytest.raises(RuleSpecError):
        _compile_predicate({"and": []})
