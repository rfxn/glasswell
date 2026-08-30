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
# What the box reads as once parsed and rendered back: the same four floats, shortest form.
NORMALIZED_ND_BOX = "-104.0,47.5,-103.0,48.5"
# Both jurisdictions: ND at 47.9N/103.6W and the TX well at 32.4N/102.8W.
BOTH_BOX = "-105,30,-100,50"
EMPTY_BOX = "-40,10,-39,11"
# A box around the ND well whose corners need more than the six significant digits `%g`
# renders. Every literal is already in shortest-round-trip form, so a correct echo is byte
# equal to it; `%g` would publish `-103.58`, a line 76 m east that holds no well at all.
LOSSY_BOX = "-103.5803217,47.9074998,-103.4,48.0"
# The same viewport nudged by a ten-millionth of a degree — a different box with the same
# answer, which must therefore be a different handle.
NEIGHBOURING_LOSSY_BOX = "-103.5803218,47.9074998,-103.4,48.0"
# The TX well sits exactly on this box's western edge. `%g` moves that edge 40 m east, which
# puts the well outside the box the collection link names while the count still says 1.
LOSSY_TX_BOX = "-102.7644756,32.35,-102.76,32.36"


def summary(client: TestClient, bbox: str = ND_BOX, **params: Any) -> dict[str, Any]:
    response = client.get(SUMMARY, params={"bbox": bbox, **params})
    assert response.status_code == 200, response.text
    return response.json()


def corners(bbox: str) -> list[float]:
    return [float(part) for part in bbox.split(",")]


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
    assert data["geometry_provenance"] == []
    assert data["well_types"] == []


def test_a_well_on_the_boundary_is_inside_the_box(client: TestClient) -> None:
    """The box is closed: a surface hole exactly on the edge is in view, and a legend that
    dropped it would disagree with the dot the map draws there.

    The edge here is `maxx`, and the well's lateral runs east out of the box, so the only
    thing holding the count up is the surface point sitting exactly on the boundary. The
    earlier form of this test put the edge on the lateral's western end, where the whole
    lateral stayed inside — an open box still contained it and the count never moved, so the
    named boundary test survived the mutation that opened the box (gate-wss MINOR-2). The
    second box below is one ten-thousandth of a degree short of the point, which is the same
    assertion from the other side: on the line is in, west of it is out.
    """
    on_the_edge = summary(client, "-103.6,47.9,-103.5803,47.92")["data"]
    just_short = summary(client, "-103.6,47.9,-103.58031,47.92")["data"]

    assert on_the_edge["wells"]["value"] == "1"
    assert just_short["wells"] is None


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
    citation to nothing.

    The kind check is per rule rather than fixed at `vocab_map`, and it is stricter for it: a
    mapping rule has to name the table it maps through, and a rule that records an *absent*
    mapping — New Mexico's, because the OCD publishes no codebook for its status letters — has
    to say so in its own spec and carry the domain it measured. The old assertion checked
    neither. Every id here still decides a status vocabulary; not every vocabulary decision is
    a mapping.
    """
    for rule_id in sorted(set(STATUS_VOCABULARY_RULES.values())):
        rule = client.get(f"/v1/conformance/{rule_id}")

        assert rule.status_code == 200, rule_id
        spec = rule.json()["data"]["spec"]
        if rule.json()["data"]["rule_kind"] == "vocab_map":
            assert spec.get("mapping_table"), rule_id
        else:
            assert spec.get("mapping_table") is None, rule_id
            assert spec.get("status_canonical") is None, rule_id
            assert spec.get("measured_domain"), rule_id


def test_the_named_rules_are_linked_where_a_reader_can_open_them(client: TestClient) -> None:
    body = summary(client, BOTH_BOX)

    assert body["data"]["vocabulary_rules"] == ["cr_nd_status_vocab_1", "cr_tx_status_vocab_1"]
    assert body["links"]["cr_nd_status_vocab_1"] == "/v1/conformance/cr_nd_status_vocab_1"
    assert body["links"]["cr_tx_status_vocab_1"] == "/v1/conformance/cr_tx_status_vocab_1"


def test_the_box_is_classed_by_geometry_provenance_with_handles(client: TestClient) -> None:
    """m13 residual / m17 R-3: the legend count for a provenance class is a served figure
    with a handle, so a coverage statement derives from the API rather than from a pinned
    constant. Largest first, ties alphabetical; classes overlap where a well holds several
    geometry kinds, so they do not sum to `wells`."""
    both = summary(client, BOTH_BOX)["data"]["geometry_provenance"]
    north = summary(client, ND_BOX)["data"]["geometry_provenance"]

    assert [(row["geometry_provenance"], row["wells"]["value"]) for row in both] == [
        ("surface", "2"),
        ("lateral", "1"),
    ]
    assert [(row["geometry_provenance"], row["wells"]["value"]) for row in north] == [
        ("lateral", "1"),
        ("surface", "1"),
    ]
    for row in both:
        assert row["wells"]["unit"] == "wells"
        assert f"geometry_provenance={row['geometry_provenance']}" in row["wells"]["d"]


def test_the_box_is_classed_by_reported_well_type_with_handles(client: TestClient) -> None:
    """The other half of the coverage derivation: wells per code as filed, verbatim, so a
    disposal-class statement sums the codes its rule names instead of pinning a total."""
    both = summary(client, BOTH_BOX)["data"]["well_types"]

    assert [(row["well_type_reported"], row["wells"]["value"]) for row in both] == [
        ("OG", "1"),
        ("PRODUCING", "1"),
    ]
    for row in both:
        assert row["wells"]["unit"] == "wells"
        assert f"well_type={row['well_type_reported']}" in row["wells"]["d"]


def test_the_provenance_classing_rule_is_linked_and_is_a_registry_row(client: TestClient) -> None:
    """The pinned rule id is held to the seeded registry, and the response links it where a
    reader can open it — same discipline as the status vocabularies."""
    body = summary(client)
    rule = client.get("/v1/conformance/cr_nd_geometry_provenance_1")

    assert body["links"]["cr_nd_geometry_provenance_1"] == (
        "/v1/conformance/cr_nd_geometry_provenance_1"
    )
    assert rule.status_code == 200
    assert rule.json()["data"]["rule_kind"] == "code_ref"


def test_provenance_counts_the_geometry_not_the_vintage(client: TestClient) -> None:
    """Geometry rows are not effective-dated: at a knowledge time before the spine the
    provenance classes still count what draws — the orphan warning disclosed the gap —
    while the spine-derived well_types are honestly empty."""
    data = summary(client, BOTH_BOX, as_of="2019-01-01")["data"]

    assert [
        (row["geometry_provenance"], row["wells"]["value"])
        for row in data["geometry_provenance"]
    ] == [("surface", "2"), ("lateral", "1")]
    assert data["well_types"] == []


def test_the_collection_link_is_offered_only_where_the_collection_can_answer(
    client: TestClient,
) -> None:
    """`/v1/wells` caps its box at four degrees a side; this endpoint has no cap, so the link
    to the rows behind the counts is published only when the collection would accept it."""
    small = summary(client, ND_BOX)["links"]
    large = summary(client, BOTH_BOX)["links"]

    assert small["wells"] == f"/v1/wells?bbox={NORMALIZED_ND_BOX}"
    assert "wells" not in large


def test_the_box_is_echoed_so_a_late_answer_can_be_matched_to_its_viewport(
    client: TestClient,
) -> None:
    """The echo is the parsed box rendered back, not the caller's string: `-104` reads as
    `-104.0`, and the floats it parses to are the floats the query ran with."""
    data = summary(client, ND_BOX)["data"]

    assert data["bbox"] == NORMALIZED_ND_BOX
    assert corners(data["bbox"]) == corners(ND_BOX)


def test_a_box_finer_than_six_significant_digits_is_echoed_as_asked(client: TestClient) -> None:
    """gate-wss BLOCK-1. The echo was rendered with `%g` — six significant digits, which at a
    three-digit longitude is three decimals, about 76 m. A viewport asking about
    -103.5803217 was told the answer was about -103.58, a line the well is not on."""
    data = summary(client, LOSSY_BOX)["data"]

    assert data["bbox"] == LOSSY_BOX
    assert corners(data["bbox"]) == corners(LOSSY_BOX)


def test_the_handle_names_the_box_the_count_was_taken_over(client: TestClient) -> None:
    """A handle that names a different box is a false provenance claim that resolves: worse
    than a missing one. Every figure in the body has to name this box, not a rounding of it."""
    data = summary(client, LOSSY_BOX)["data"]
    selector = "bbox=-103.5803217:47.9074998:-103.4:48.0"

    assert data["wells"]["value"] == "1"
    assert data["wells"]["d"].endswith(selector)
    assert data["unmapped_wells"] is None
    for handle in sorted(handles(data)):
        assert handle.endswith(selector), handle


def test_two_viewports_a_metre_apart_are_two_handles(client: TestClient) -> None:
    """The handle identifies the computation, not the answer: two boxes that agree on the
    count still ran over different boxes, and `%g` collapsed them onto one address."""
    near = summary(client, LOSSY_BOX)["data"]
    nearer = summary(client, NEIGHBOURING_LOSSY_BOX)["data"]

    assert near["wells"]["value"] == nearer["wells"]["value"] == "1"
    assert near["bbox"] != nearer["bbox"]
    assert near["wells"]["d"] != nearer["wells"]["d"]


def test_following_the_collection_link_finds_the_wells_the_summary_counted(
    client: TestClient,
) -> None:
    """The legend's click-through, over the Texas well because it is the fixture's only
    point-without-a-lateral: the ND well's lateral has a bounding box wide enough that the
    collection answers for it either way, which would make this assertion pass on a rounded
    link and prove nothing. Under `%g` this link named a box 40 m west and returned no rows
    under a summary reporting one (gate-wss BLOCK-1 evidence C)."""
    body = summary(client, LOSSY_TX_BOX)
    listed = client.get(body["links"]["wells"])

    assert body["data"]["wells"]["value"] == "1"
    assert listed.status_code == 200, listed.text
    assert [row["api10"] for row in listed.json()["data"]] == [TX_API10]


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
    assert body["meta"]["as_of"]["resolved"] == "2026-08-01"
    assert well["meta"]["as_of"]["resolved"] == "2026-08-20"


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
    assert warnings[0]["detail"].startswith("2 geometries in this box have no well row")


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
    on that point — here, the seeded surface hole. The echo and the handle have to name that
    point too: under `%g` this test read `wells: 1` while its handle named `-103.58`, a
    location holding nothing (gate-wss BLOCK-1 evidence A)."""
    point = "-103.5803,47.9075,-103.5803,47.9075"
    data = summary(client, point)["data"]

    assert data["wells"]["value"] == "1"
    assert data["bbox"] == point
    assert data["wells"]["d"].endswith("bbox=-103.5803:47.9075:-103.5803:47.9075")


def test_the_summary_says_which_glossary_term_its_classes_belong_to(client: TestClient) -> None:
    labels = summary(client)["meta"]["labels"]

    assert labels["/statuses"] == "gt_well_status"
    assert labels["/vocabulary_rules"] == "gt_conformance_rule"


def test_the_texas_well_is_reachable_through_the_summary(client: TestClient) -> None:
    """MUST-KNOW-14's fixture arm: the walker's second jurisdiction is in this surface too."""
    basins = summary(client, "-103,32,-102,33")["data"]["basins"]

    assert [row["state_code"] for row in basins] == ["42"]
    assert client.get(f"/v1/wells/{TX_API10}").status_code == 200
