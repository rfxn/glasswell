"""`/v1/modeling/publications`: what the served modeling layer is pinned to, and what pinned it."""

from __future__ import annotations

from datetime import date

import psycopg
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_PUBLICATION_ID
from tests.contract.conftest import CONTROL_SUBJECTS
from tests.support.typecurve_fixture import register_pinned_control, write_control_artifact

DETAIL = f"/v1/modeling/publications/{EXAMPLE_PUBLICATION_ID}"


def test_the_list_names_the_accepted_publication(client: TestClient) -> None:
    body = client.get("/v1/modeling/publications").json()
    rows = body["data"]
    assert [row["publication_id"] for row in rows] == [EXAMPLE_PUBLICATION_ID]
    row = rows[0]
    assert row["accepted"] is True
    assert row["basin"] == "williston"
    assert row["versions"] == {
        "feature": "fv2.0",
        "model_dataset": "mdv1.4",
        "type_curve": "tcv1.0",
    }
    assert row["split_set_id"].startswith("sset_")


def test_the_list_filters_by_basin(client: TestClient) -> None:
    assert client.get("/v1/modeling/publications", params={"basin": "williston"}).json()["data"]
    assert (
        client.get("/v1/modeling/publications", params={"basin": "permian"}).json()["data"] == []
    )


def test_the_detail_states_every_pinned_identity(client: TestClient) -> None:
    data = client.get(DETAIL).json()["data"]
    assert data["publication_id"] == EXAMPLE_PUBLICATION_ID
    assert set(data["derivations"]) == {"feature", "model_dataset", "type_curve"}
    assert data["baseline"]["split_set_id"] == data["split_set_id"]
    assert data["artifact_sha256"]["type_curve"]
    assert {item["split_id"] for item in data["splits"]} == {
        "spl_20210101_24",
        "spl_20210101_12",
        "spl_20210701_24",
    }
    assert all(item["sha256"] for item in data["splits"])


def test_the_detail_states_the_support_distribution(client: TestClient) -> None:
    support = client.get(DETAIL).json()["data"]["coverage"]["support"]
    levels = support["fallback_by_level"]
    assert set(levels) == {
        "control_unavailable",
        "formation_area",
        "formation_area_length",
        "formation_basin",
    }
    assert levels["control_unavailable"]["value"] == "1"
    assert levels["control_unavailable"]["unit"] == "subject_instances"
    assert levels["control_unavailable"]["d"]
    mentions = support["control_unavailable_reason_mentions"]
    assert mentions["missing_lateral_length"]["value"] == "1"
    assert support["test_subject_instances"]["value"] == str(len(CONTROL_SUBJECTS))
    # Protocol 4D: a distribution, never a mean.
    assert "mean" not in str(support)


def test_the_acceptance_gates_are_served_with_their_thresholds(client: TestClient) -> None:
    acceptance = client.get(DETAIL).json()["data"]["coverage"]["acceptance"]
    assert set(acceptance) == {"pooled_control_unavailable_share", "pooled_rung1_share"}
    rung1 = acceptance["pooled_rung1_share"]
    assert rung1["observed"]["unit"] == "share"
    assert rung1["observed"]["d"]
    assert rung1["minimum"] == "0.600000"
    assert rung1["status"] == "pass"
    assert acceptance["pooled_control_unavailable_share"]["maximum"] == "0.050000"


def test_the_control_contract_is_served_verbatim(client: TestClient) -> None:
    contract = client.get(DETAIL).json()["data"]["coverage"]["control_contract"]
    assert contract["min_peers"] == 20
    assert contract["vintage_window_months"] == 36
    assert contract["quantile_convention"] == "statistical_ascending"
    assert contract["fallback_ladder"][-1] == "control_unavailable"


def test_every_figure_resolves_to_the_control_derivation(client: TestClient) -> None:
    body = client.get(DETAIL, params={"explain": "true"}).json()
    control = body["data"]["derivations"]["type_curve"]
    handle = body["data"]["coverage"]["support"]["test_subject_instances"]["d"]
    chains = body["_explain"]
    assert handle in chains
    assert control in {
        node["id"] for node in chains[handle]["nodes"] if node.get("id")
    }
    kinds = {node["id"]: node["type"] for node in chains[handle]["nodes"]}
    assert chains[handle]["terminals"]
    assert all(kinds[terminal] == "manifest" for terminal in chains[handle]["terminals"])
    assert chains[handle]["truncated"] is False
    assert chains[handle]["depth"] <= 7


def test_an_unknown_publication_id_is_not_found(client: TestClient) -> None:
    response = client.get("/v1/modeling/publications/p3pub_" + "0" * 32)
    assert response.status_code == 404
    assert response.json()["type"].endswith("/not_found")


def test_a_malformed_publication_id_is_refused_by_the_pattern(client: TestClient) -> None:
    assert client.get("/v1/modeling/publications/not-a-publication").status_code == 422


def test_the_detail_links_its_conformance_rules(client: TestClient) -> None:
    links = client.get(DETAIL).json()["links"]
    for rule in ("cr_tc_publication_scope_1", "cr_tc_peer_ladder_1", "cr_tc_quantile_convention_1"):
        assert links[rule] == f"/v1/conformance/{rule}"
        assert client.get(links[rule]).status_code == 200


def test_the_detail_does_not_disclose_a_filesystem_path(client: TestClient) -> None:
    """A path is deployment information; artifact_sha256 addresses the same bytes without it."""
    body = client.get(DETAIL).text
    assert "artifact_uri" not in body
    assert "part-0000.parquet" not in body
    assert "coverage.json" not in body


def test_a_second_publication_is_announced_as_superseding(
    client: TestClient, seeded: psycopg.Connection, pinned_control
) -> None:
    later = write_control_artifact(
        pinned_control.root,
        subjects=CONTROL_SUBJECTS,
        eval_vintage=date(2026, 8, 29),
    )
    second = register_pinned_control(seeded, later, manifest_id="man_" + "e" * 32)
    seeded.commit()

    rows = client.get("/v1/modeling/publications").json()["data"]
    assert {row["publication_id"] for row in rows} == {EXAMPLE_PUBLICATION_ID, second}

    newer = client.get(f"/v1/modeling/publications/{second}").json()
    assert newer["data"]["supersedes"] == EXAMPLE_PUBLICATION_ID
    assert newer["links"]["supersedes"] == DETAIL
    assert [w["code"] for w in newer["meta"]["warnings"]] == ["publication_superseded"]

    prior = client.get(DETAIL).json()
    assert prior["data"]["supersedes"] is None
    assert [w["code"] for w in prior["meta"]["warnings"]] == ["publication_superseded"]
    assert second in prior["meta"]["warnings"][0]["detail"]
