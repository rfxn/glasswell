"""`/v1/wells/status-summary`: the counts the map legend reads, against seeded rows.

The legend used to count what MapLibre had drawn, so zooming out — which thins the tile tier
and withdraws the low-salience classes — shrank the counts while the viewed area grew. A count
that moves when the drawing changes is not a count of anything, so it is asked of the data
here. This file holds the surface: the envelope, the buckets, the refusals and the handles.
Per-class arithmetic against a population of known statuses is
`tests/integration/test_well_status_summary.py`.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10, EXAMPLE_BBOX
from glasswell.api.routers.wells import STATUS_VOCABULARY_RULES
from tests.contract.conftest import TX_API10
from tests.contract.test_naked_numbers import handles, naked_numbers

SUMMARY = "/v1/wells/status-summary"
# The published example: the seeded ND well's surface hole and its lateral. OTHER_API10S carry
# no geometry at all, so they are in no viewport and in no count.
ND_BOX = EXAMPLE_BBOX
# Both jurisdictions: ND at 47.9N/103.6W and the TX well at 32.4N/102.8W.
BOTH_BOX = "-105,30,-100,50"
EMPTY_BOX = "-40,10,-39,11"


def summary(client: TestClient, bbox: str = ND_BOX, **params: Any) -> dict[str, Any]:
    response = client.get(SUMMARY, params={"bbox": bbox, **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_the_summary_counts_the_wells_whose_geometry_is_in_the_box(client: TestClient) -> None:
    data = summary(client)["data"]

    assert data["wells"]["value"] == "1"
    assert data["wells"]["unit"] == "wells"
    assert [(row["status"], row["wells"]["value"]) for row in data["statuses"]] == [("active", "1")]


def test_a_box_with_no_wells_reports_no_class_rather_than_a_zero(client: TestClient) -> None:
    """`refreshCounts` already reads absence as "no count to report"; a zero would claim the
    viewport contains a class it does not."""
    data = summary(client, EMPTY_BOX)["data"]

    assert data["wells"] is None
    assert data["statuses"] == []
    assert data["basins"] == []
    assert data["unmapped_wells"] is None


def test_a_well_on_the_boundary_is_inside_the_box(client: TestClient) -> None:
    """The box is closed: a surface hole exactly on the edge is in view, and a legend that
    dropped it would disagree with the dot the map draws there."""
    edge = summary(client, "-103.5803,47.9075,-103.4,48.0")["data"]

    assert edge["wells"]["value"] == "1"


def test_the_box_excludes_what_is_outside_it(client: TestClient) -> None:
    both = summary(client, BOTH_BOX)["data"]
    north = summary(client, ND_BOX)["data"]

    assert both["wells"]["value"] == "2"
    assert north["wells"]["value"] == "1"


def test_the_counts_are_split_per_basin_with_the_rule_that_mapped_them(client: TestClient) -> None:
    """R8: two jurisdictions, two status vocabularies, and the response says which is which
    rather than implying one vocabulary spans both."""
    basins = summary(client, BOTH_BOX)["data"]["basins"]

    assert [(row["basin"], row["state_code"], row["status_vocabulary_rule"]) for row in basins] == [
        ("permian", "42", "cr_tx_status_vocab_1"),
        ("williston", "33", "cr_nd_status_vocab_1"),
    ]
    assert [row["wells"]["value"] for row in basins] == ["1", "1"]


def test_the_vocabulary_rules_it_names_are_rows_in_the_registry(client: TestClient) -> None:
    """The pinned map is held to the seeded registry: a rule id that resolves nowhere is a
    citation to nothing."""
    for rule_id in sorted(set(STATUS_VOCABULARY_RULES.values())):
        rule = client.get(f"/v1/conformance/{rule_id}")

        assert rule.status_code == 200, rule_id
        assert rule.json()["data"]["rule_kind"] == "vocab_map"


def test_the_named_rules_are_linked_where_a_reader_can_open_them(client: TestClient) -> None:
    body = summary(client, BOTH_BOX)

    assert body["data"]["vocabulary_rules"] == ["cr_nd_status_vocab_1", "cr_tx_status_vocab_1"]
    assert body["links"]["cr_nd_status_vocab_1"] == "/v1/conformance/cr_nd_status_vocab_1"
    assert body["links"]["cr_tx_status_vocab_1"] == "/v1/conformance/cr_tx_status_vocab_1"


def test_the_collection_link_is_offered_only_where_the_collection_can_answer(
    client: TestClient,
) -> None:
    """`/v1/wells` caps its box at four degrees a side; this endpoint has no cap, so the link
    to the rows behind the counts is published only when the collection would accept it."""
    small = summary(client, ND_BOX)["links"]
    large = summary(client, BOTH_BOX)["links"]

    assert small["wells"] == f"/v1/wells?bbox={ND_BOX}"
    assert "wells" not in large


def test_the_box_is_echoed_so_a_late_answer_can_be_matched_to_its_viewport(
    client: TestClient,
) -> None:
    data = summary(client, ND_BOX)["data"]

    assert data["bbox"] == ND_BOX


def test_every_count_carries_a_handle_that_resolves_to_a_manifest(client: TestClient) -> None:
    """R6 on a serve-time aggregate: the count is not a number the API invented, and the
    handle walks back to the file the statuses were promoted from."""
    body = summary(client, BOTH_BOX)
    found = handles(body["data"])

    assert len(found) >= 4
    for handle in sorted(found):
        chain = client.get("/v1/explain", params={"h": handle, "depth": "full"}).json()
        resolved = chain["data"]["chains"][0]
        node_types = {node["id"]: node["type"] for node in resolved["nodes"]}
        assert resolved["terminals"], f"{handle} resolves to no terminal"
        assert all(node_types[terminal] == "manifest" for terminal in resolved["terminals"])


def test_the_response_carries_a_prebuilt_explain_call(client: TestClient) -> None:
    body = summary(client, BOTH_BOX)

    assert body["links"]["explain"].startswith("/v1/explain?h=")


def test_no_number_it_serves_is_naked(client: TestClient) -> None:
    """The R6 walker reaches this operation through its published example; asserted here too
    because the example is one box and the jurisdictions split at another."""
    assert naked_numbers(summary(client, BOTH_BOX)["data"]) == []


def test_the_counts_pin_to_the_vintage_the_rest_of_the_surface_serves(client: TestClient) -> None:
    body = summary(client, ND_BOX)
    well = client.get(f"/v1/wells/{EXAMPLE_API10}").json()

    assert body["meta"]["as_of"]["requested"] == "latest"
    assert body["meta"]["as_of"]["resolved"] == well["meta"]["as_of"]["resolved"]


def test_an_as_of_before_the_spine_leaves_the_box_empty_rather_than_full(
    client: TestClient,
) -> None:
    """A well row that does not exist yet at that knowledge time is not counted at it."""
    data = summary(client, BOTH_BOX, as_of="2019-01-01")["data"]

    assert data["wells"] is None
    assert data["statuses"] == []


def test_geometry_with_no_well_row_is_disclosed_and_never_counted_as_a_class(
    client: TestClient,
) -> None:
    """At a knowledge time before the spine, every geometry in the box is orphaned. It is a
    warning with a count, not a status class and not a silent drop."""
    warnings = summary(client, BOTH_BOX, as_of="2019-01-01")["meta"]["warnings"]

    assert [item["code"] for item in warnings] == ["geometry_without_a_well_row"]
    assert "2" in warnings[0]["detail"]


@pytest.mark.parametrize(
    ("bbox", "code"),
    [
        ("-104,47.5,-103", "bbox_shape"),
        ("-104,47.5,-103,48.5,1", "bbox_shape"),
        ("west,47.5,-103,48.5", "bbox_number"),
        ("", "bbox_shape"),
        ("-103,47.5,-104,48.5", "bbox_order"),
        ("-104,48.5,-103,47.5", "bbox_order"),
        ("170,40,-170,50", "bbox_order"),
        ("-181,47.5,-103,48.5", "bbox_range"),
        ("-104,47.5,-103,91", "bbox_range"),
    ],
)
def test_a_box_that_is_not_a_box_is_refused(client: TestClient, bbox: str, code: str) -> None:
    response = client.get(SUMMARY, params={"bbox": bbox})

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "/v1/errors/validation_failed"
    assert [item["code"] for item in body["errors"]] == [code]
    assert [item["pointer"] for item in body["errors"]] == ["/query/bbox"]


def test_the_box_is_required_because_the_answer_is_about_a_viewport(client: TestClient) -> None:
    assert client.get(SUMMARY).status_code == 422


def test_a_whole_world_box_is_answered_rather_than_capped(client: TestClient) -> None:
    """`/v1/wells` refuses a box over four degrees a side because it pages rows. This one
    returns at most one row per class per basin however wide the box is, so a capped answer
    would be the same bug the endpoint exists to fix."""
    data = summary(client, "-180,-90,180,90")["data"]

    assert data["wells"]["value"] == "2"
    assert {row["status"] for row in data["statuses"]} == {"active"}


def test_a_zero_area_box_is_a_box(client: TestClient) -> None:
    """Degenerate, not malformed: a viewport can collapse, and the honest answer is what sits
    on that line — here, the seeded surface hole."""
    data = summary(client, "-103.5803,47.9075,-103.5803,47.9075")["data"]

    assert data["wells"]["value"] == "1"


def test_the_summary_says_which_glossary_term_its_classes_belong_to(client: TestClient) -> None:
    labels = summary(client)["meta"]["labels"]

    assert labels["/statuses"] == "gt_well_status"
    assert labels["/vocabulary_rules"] == "gt_conformance_rule"


def test_the_texas_well_is_reachable_through_the_summary(client: TestClient) -> None:
    """MUST-KNOW-14's fixture arm: the walker's second jurisdiction is in this surface too."""
    basins = summary(client, "-103,32,-102,33")["data"]["basins"]

    assert [row["state_code"] for row in basins] == ["42"]
    assert client.get(f"/v1/wells/{TX_API10}").status_code == 200
