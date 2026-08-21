"""The freeze gate: after S1, the differ has to know which changes cost a version bump."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.contract.openapi_diff import Change, breaking, classify, facts, main
from tests.contract.test_openapi_snapshot import SNAPSHOT_PATH

BASE: dict[str, Any] = {
    "paths": {
        "/v1/things": {
            "get": {
                "parameters": [
                    {"name": "limit", "required": False, "schema": {"type": "integer"}},
                    {"name": "kind", "schema": {"enum": ["a", "b"]}},
                ],
                "responses": {"200": {}, "404": {}},
            },
            "post": {
                "requestBody": {
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/NewThing"}}
                    }
                },
                "responses": {"201": {}},
            },
        }
    },
    "components": {
        "schemas": {
            "Thing": {"properties": {"id": {}, "label": {}}, "required": ["id"]},
            "NewThing": {"properties": {"label": {}, "note": {}}, "required": ["label"]},
        }
    },
}


def _verdicts(before: dict, after: dict) -> dict[str, str]:
    return {change.fact: change.verdict for change in classify(before, after)}


def test_an_identical_document_reports_no_change() -> None:
    assert classify(BASE, copy.deepcopy(BASE)) == []


def test_a_removed_path_is_breaking() -> None:
    after = copy.deepcopy(BASE)
    del after["paths"]["/v1/things"]

    assert _verdicts(BASE, after)["/v1/things"] == "breaking"


def test_a_new_path_is_additive() -> None:
    after = copy.deepcopy(BASE)
    after["paths"]["/v1/others"] = {"get": {"responses": {"200": {}}}}

    assert breaking(BASE, after) == []
    assert _verdicts(BASE, after)["/v1/others"] == "additive"


def test_a_removed_operation_on_a_surviving_path_is_breaking() -> None:
    after = copy.deepcopy(BASE)
    del after["paths"]["/v1/things"]["post"]

    assert _verdicts(BASE, after)["POST /v1/things"] == "breaking"


def test_a_new_optional_parameter_is_additive_but_a_required_one_is_not() -> None:
    """The asymmetry the differ exists for: both are additions, only one breaks a caller."""
    optional = copy.deepcopy(BASE)
    optional["paths"]["/v1/things"]["get"]["parameters"].append({"name": "since"})
    required = copy.deepcopy(BASE)
    required["paths"]["/v1/things"]["get"]["parameters"].append(
        {"name": "since", "required": True}
    )

    assert breaking(BASE, optional) == []
    assert [change.fact for change in breaking(BASE, required)] == [
        "GET /v1/things ?since (required)"
    ]


def test_dropping_a_parameter_requirement_is_a_relaxation() -> None:
    before = copy.deepcopy(BASE)
    before["paths"]["/v1/things"]["get"]["parameters"][0]["required"] = True

    assert breaking(before, BASE) == []


def test_a_removed_enum_value_is_breaking_and_a_new_one_is_not() -> None:
    narrowed = copy.deepcopy(BASE)
    narrowed["paths"]["/v1/things"]["get"]["parameters"][1]["schema"]["enum"] = ["a"]
    widened = copy.deepcopy(BASE)
    widened["paths"]["/v1/things"]["get"]["parameters"][1]["schema"]["enum"] = ["a", "b", "c"]

    assert [change.verdict for change in classify(BASE, narrowed)] == ["breaking"]
    assert breaking(BASE, widened) == []


def test_a_removed_response_property_is_breaking() -> None:
    after = copy.deepcopy(BASE)
    del after["components"]["schemas"]["Thing"]["properties"]["label"]

    assert _verdicts(BASE, after)["Thing.label"] == "breaking"


def test_a_response_guarantee_runs_the_opposite_way_from_a_request_obligation() -> None:
    """`required` on a body the caller sends tightens; on a body it receives, it promises."""
    tightened_request = copy.deepcopy(BASE)
    tightened_request["components"]["schemas"]["NewThing"]["required"] = ["label", "note"]
    stronger_response = copy.deepcopy(BASE)
    stronger_response["components"]["schemas"]["Thing"]["required"] = ["id", "label"]

    assert [change.fact for change in breaking(BASE, tightened_request)] == [
        "NewThing.note (required)"
    ]
    assert breaking(BASE, stronger_response) == []


def test_a_withdrawn_response_promise_is_breaking() -> None:
    after = copy.deepcopy(BASE)
    after["components"]["schemas"]["Thing"]["required"] = []

    assert _verdicts(BASE, after)["Thing.id (required)"] == "breaking"


def test_a_removed_declared_status_is_breaking() -> None:
    after = copy.deepcopy(BASE)
    del after["paths"]["/v1/things"]["get"]["responses"]["404"]

    assert _verdicts(BASE, after)["GET /v1/things -> 404"] == "breaking"


def test_the_cli_exits_nonzero_only_on_a_breaking_change(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = tmp_path / "before.json"
    additive = tmp_path / "additive.json"
    removal = tmp_path / "removal.json"
    before.write_text(json.dumps(BASE), encoding="utf-8")
    widened = copy.deepcopy(BASE)
    widened["paths"]["/v1/others"] = {"get": {"responses": {"200": {}}}}
    additive.write_text(json.dumps(widened), encoding="utf-8")
    narrowed = copy.deepcopy(BASE)
    del narrowed["paths"]["/v1/things"]
    removal.write_text(json.dumps(narrowed), encoding="utf-8")

    assert main([str(before), str(additive)]) == 0
    assert main([str(before), str(removal)]) == 1
    assert "breaking" in capsys.readouterr().err


def test_the_served_document_is_not_a_breaking_change_against_the_snapshot(
    client: TestClient,
) -> None:
    """The CI mode. The byte gate says something moved; this says whether it costs a /v2."""
    committed = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    served = client.get("/openapi.json").json()

    offenders = breaking(committed, served)

    assert offenders == [], "\n".join(str(change) for change in offenders)


def test_the_differ_reads_its_verdicts_off_one_rule_table() -> None:
    """A kind with no rule would raise at report time, when the diff is already urgent."""
    committed = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    kinds = {fact.kind for fact in facts(committed).values()}

    assert kinds
    assert all(isinstance(Change(kind, "x", "added").verdict, str) for kind in kinds)


def test_relaxing_a_parameter_pattern_is_breaking() -> None:
    """UDM-SPEC §5.3 ground one, closed as a class (N-5).

    Widening `API10_PATTERN` is formally a relaxation, so nothing else in this table objects to
    it. Before the `pattern` kind existed the differ produced *no fact at all* for it and
    returned `additive` having examined nothing: the identifier grammar of the product's primary
    key could move with the gate reporting no semantic change.
    """
    before = copy.deepcopy(BASE)
    before["paths"]["/v1/things"]["get"]["parameters"][0]["schema"] = {
        "type": "string",
        "pattern": r"^\d{10}$",
    }
    after = copy.deepcopy(before)
    after["paths"]["/v1/things"]["get"]["parameters"][0]["schema"]["pattern"] = r"^[\dA-Z/]{10,16}$"

    assert [change.fact for change in breaking(before, after)] == [
        r"GET /v1/things ?limit =~ ^\d{10}$"
    ]


def test_dropping_a_pattern_altogether_is_breaking_and_declaring_one_reports_additive() -> None:
    """The rule table's two directions, stated so the asymmetry is deliberate rather than found.

    `("additive", "breaking")` is what §7.3 chunk 1.1 specifies, and it matches `type` and
    `enum-value`: a constraint that disappears is a promise withdrawn.
    """
    unconstrained = copy.deepcopy(BASE)
    unconstrained["components"]["schemas"]["Thing"]["properties"]["id"] = {"type": "string"}
    constrained = copy.deepcopy(unconstrained)
    constrained["components"]["schemas"]["Thing"]["properties"]["id"]["pattern"] = "^t_[a-z]+$"

    assert [change.fact for change in breaking(constrained, unconstrained)] == [
        "Thing.id =~ ^t_[a-z]+$"
    ]
    assert breaking(unconstrained, constrained) == []
    assert [change.kind for change in classify(unconstrained, constrained)] == ["pattern"]


def test_a_pattern_inside_an_anyof_branch_is_still_a_fact() -> None:
    """`from` and `to` on the production route are `str | None`, and the pattern is on the branch.

    A kind that only reads the top level would leave every optional constrained parameter in the
    served document unwatched, which is the same blind spot one level down.
    """
    before = copy.deepcopy(BASE)
    before["paths"]["/v1/things"]["get"]["parameters"][0]["schema"] = {
        "anyOf": [{"type": "string", "pattern": r"^\d{4}-\d{2}$"}, {"type": "null"}]
    }
    after = copy.deepcopy(before)
    after["paths"]["/v1/things"]["get"]["parameters"][0]["schema"]["anyOf"][0]["pattern"] = "^.*$"

    assert [change.fact for change in breaking(before, after)] == [
        r"GET /v1/things ?limit =~ ^\d{4}-\d{2}$"
    ]


def test_the_pattern_kind_reads_the_document_this_product_actually_serves() -> None:
    """A kind proven only against BASE is a kind that may see nothing in the real document."""
    committed = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    patterns = {fact for fact, entry in facts(committed).items() if entry.kind == "pattern"}

    assert r"GET /v1/wells/{api10} ?api10 =~ ^\d{10}$" in patterns
    # The two the anyOf arm above exists for, and the one on a request body property.
    assert r"GET /v1/wells/{api10}/production ?from =~ ^\d{4}-\d{2}$" in patterns
    assert "IssueRequest.label =~ ^[a-z0-9]+(-[a-z0-9]+)*$" in patterns


def test_widening_a_response_field_to_nullable_is_breaking() -> None:
    """DR-33 gated `storage_uri` behind owner scope, which is exactly this shape of change."""
    before = copy.deepcopy(BASE)
    before["components"]["schemas"]["Thing"]["properties"]["label"] = {"type": "string"}
    after = copy.deepcopy(before)
    after["components"]["schemas"]["Thing"]["properties"]["label"] = {
        "anyOf": [{"type": "string"}, {"type": "null"}]
    }

    assert [change.fact for change in breaking(before, after)] == ["Thing.label : string"]
