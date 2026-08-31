"""The producing filter on `/v1/wells`, its refusals, and the counts it puts a handle on.

The owner asked to tell an administratively Active well from one that is actually producing.
That is a definition rather than a lookup, so these tests hold the surface to the definition's
rule rows: the classes it may answer, the cursor it must refuse, and the fact that every count
it serves resolves to the derivation the production came from.
"""

from __future__ import annotations

from collections import Counter

import psycopg
from fastapi.testclient import TestClient

from glasswell.api.errors import TYPE_BASE
from glasswell.api.examples import EXAMPLE_API10
from glasswell.marts.producing import PRODUCING_CLASSES, PRODUCING_RULE_IDS
from tests.contract.conftest import OTHER_API10S, TX_API10
from tests.support.seed import seed_well_spatial

BOX = "-105,46,-102,49"
ZERO_FILED_WELL = OTHER_API10S[4]


def classes(client: TestClient) -> dict[str, str]:
    data = client.get("/v1/wells", params={"limit": 200}).json()["data"]
    return {item["api10"]: item["producing"] for item in data}


def test_every_well_carries_its_producing_class_beside_its_status(client: TestClient) -> None:
    """The column is served whether or not it is filtered on, so a reader can see that active
    and producing are different facts without having to ask twice."""
    by_api10 = classes(client)

    assert by_api10[EXAMPLE_API10] == "producing"
    assert by_api10[ZERO_FILED_WELL] == "not_producing"
    assert by_api10[TX_API10] == "unknown"


def test_the_collection_filters_on_the_producing_class(client: TestClient) -> None:
    producing = client.get("/v1/wells", params={"producing": "producing"}).json()["data"]

    assert [item["api10"] for item in producing] == [EXAMPLE_API10]
    assert {item["producing"] for item in producing} == {"producing"}


def test_the_filter_composes_with_status_which_is_the_owners_question(
    client: TestClient,
) -> None:
    """Active-Producing against Active-but-not: both arms are asked of the same status."""
    active = client.get("/v1/wells", params={"status": "active", "limit": 200}).json()["data"]
    producing = client.get(
        "/v1/wells", params={"status": "active", "producing": "producing"}
    ).json()["data"]
    idle = client.get(
        "/v1/wells", params={"status": "active", "producing": "not_producing"}
    ).json()["data"]

    assert len(active) > len(producing)
    assert [item["api10"] for item in producing] == [EXAMPLE_API10]
    assert [item["api10"] for item in idle] == [ZERO_FILED_WELL]


def test_a_well_that_filed_nothing_recently_is_unknown_not_not_producing(
    client: TestClient,
) -> None:
    """3305300001 produced in the oldest seeded month and has filed nothing since. That is an
    absence of evidence, and it is not the same answer as a filed zero."""
    unknown = client.get("/v1/wells", params={"producing": "unknown", "limit": 200}).json()[
        "data"
    ]

    assert OTHER_API10S[0] in {item["api10"] for item in unknown}
    assert ZERO_FILED_WELL not in {item["api10"] for item in unknown}


def test_a_lease_reporting_jurisdiction_is_never_answered_not_producing(
    client: TestClient,
) -> None:
    """DIR-3: Texas reports at the lease, so no Texas well has a well-level series to be
    absent from. Answering not_producing there would misreport the whole state."""
    idle = client.get("/v1/wells", params={"producing": "not_producing", "limit": 200}).json()
    assert TX_API10 not in {item["api10"] for item in idle["data"]}

    unknown = client.get("/v1/wells", params={"producing": "unknown", "limit": 200}).json()
    assert TX_API10 in {item["api10"] for item in unknown["data"]}


def test_a_class_outside_the_vocabulary_is_refused_rather_than_returning_nothing(
    client: TestClient,
) -> None:
    """A closed vocabulary the rules define, unlike well_type: an empty page would read as
    'no wells are active-producing' when the truth is the word means nothing here."""
    response = client.get("/v1/wells", params={"producing": "active-producing"})

    assert response.status_code == 422
    body = response.json()
    assert body["errors"][0]["pointer"] == "/query/producing"
    assert "producing" in body["errors"][0]["detail"]


def test_the_class_is_matched_verbatim_and_not_case_folded(client: TestClient) -> None:
    assert client.get("/v1/wells", params={"producing": "PRODUCING"}).status_code == 422


def test_a_cursor_minted_before_the_filter_was_added_is_refused(client: TestClient) -> None:
    """The fingerprint covers the filter, so a page cannot be resumed into a different
    population. Without this, pagination corrupts silently across pages."""
    first = client.get("/v1/wells", params={"limit": 1}).json()
    cursor = first["meta"]["next_cursor"]
    assert cursor

    resumed = client.get(
        "/v1/wells", params={"limit": 1, "cursor": cursor, "producing": "producing"}
    )

    assert resumed.status_code == 422
    assert resumed.json()["type"] == f"{TYPE_BASE}/cursor_query_mismatch"


def test_a_cursor_minted_with_the_filter_resumes_the_same_population(
    client: TestClient,
) -> None:
    first = client.get("/v1/wells", params={"limit": 1, "producing": "unknown"}).json()
    cursor = first["meta"]["next_cursor"]

    resumed = client.get(
        "/v1/wells", params={"limit": 1, "cursor": cursor, "producing": "unknown"}
    )

    assert resumed.status_code == 200
    assert {item["producing"] for item in resumed.json()["data"]} == {"unknown"}


def test_the_next_link_carries_the_filter_forward(client: TestClient) -> None:
    body = client.get("/v1/wells", params={"limit": 1, "producing": "unknown"}).json()

    assert "producing=unknown" in body["links"]["next"]


def test_the_summary_counts_each_class_with_a_handle_that_resolves(
    client: TestClient,
) -> None:
    """No naked numbers: a legend that says how many wells are producing has to say which
    derivation the production came from."""
    data = client.get("/v1/wells/status-summary", params={"bbox": BOX}).json()["data"]
    counts = {row["producing"]: row["wells"] for row in data["producing"]}

    assert counts
    for name, figure in counts.items():
        assert figure["unit"] == "wells"
        assert figure["d"].startswith("drv_")
        # The selector rides inside the handle, so the class a count is of is resolvable.
        assert f"producing={name}" in figure["d"]


def test_a_producing_count_resolves_to_the_file_the_production_came_from(
    client: TestClient,
) -> None:
    data = client.get("/v1/wells/status-summary", params={"bbox": BOX}).json()["data"]
    handle = next(
        row["wells"]["d"] for row in data["producing"] if row["producing"] == "producing"
    )

    chain = client.get("/v1/explain", params={"h": handle, "depth": "full"}).json()
    resolved = chain["data"]["chains"][0]
    node_types = {node["id"]: node["type"] for node in resolved["nodes"]}

    assert resolved["terminals"], f"{handle} resolves to no terminal"
    assert all(node_types[terminal] == "manifest" for terminal in resolved["terminals"])


def test_the_summary_states_the_window_and_the_basis_beside_the_counts(
    client: TestClient,
) -> None:
    """The vocabulary rule: liquids means oil plus condensate, and the policy is stated
    wherever the number appears — not only in the glossary."""
    data = client.get("/v1/wells/status-summary", params={"bbox": BOX}).json()["data"]
    window = data["producing_window"]

    assert window["months"] == 3
    assert window["from"]
    assert window["to"]
    assert window["from"] <= window["to"]
    assert window["streams"] == ["gas", "oil"]
    assert window["liquids_basis"] == "oil+condensate"


def test_the_summary_names_and_links_the_rules_that_defined_producing(
    client: TestClient,
) -> None:
    """R8: the mapping decision is a row, and the response says which row."""
    body = client.get("/v1/wells/status-summary", params={"bbox": BOX}).json()

    assert body["data"]["producing_rules"] == sorted(PRODUCING_RULE_IDS)
    for rule_id in PRODUCING_RULE_IDS:
        assert body["links"][rule_id] == f"/v1/conformance/{rule_id}"


def test_each_producing_rule_resolves_at_the_conformance_endpoint(client: TestClient) -> None:
    for rule_id in PRODUCING_RULE_IDS:
        body = client.get(f"/v1/conformance/{rule_id}").json()["data"]

        assert body["rule_id"] == rule_id
        assert body["rationale"]
        assert body["effective_from"]


def test_the_summary_counts_do_not_silently_omit_a_class_that_is_present(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The summary and the collection are the same population classed the same way.

    Driven from the collection, which is what proves a class is present. Iterating the served
    summary instead never visits a class the summary dropped, so a legend that omits an entire
    class still reads as agreeing with the collection about every class it kept.

    The shared fixture puts one geometry in this box, and one class cannot be short of another,
    so the zero-filed well is given a point inside it: two classes in the box is what gives an
    omission something to omit.
    """
    seed_well_spatial(
        seeded, api10=ZERO_FILED_WELL, geom_type="surface", wkt="POINT(-103.4000 47.8000)"
    )
    seeded.commit()

    listed = client.get("/v1/wells", params={"bbox": BOX, "limit": 200}).json()["data"]
    present = Counter(item["producing"] for item in listed if item["producing"] is not None)

    assert set(present) <= set(PRODUCING_CLASSES)
    assert len(present) > 1, "the box holds one class, so an omission has nothing to omit"
    data = client.get("/v1/wells/status-summary", params={"bbox": BOX}).json()["data"]
    counted = Counter(
        {row["producing"]: int(row["wells"]["value"]) for row in data["producing"]}
    )

    assert set(counted) == set(present), "the summary and the collection disagree on the classes"
    assert counted == present
