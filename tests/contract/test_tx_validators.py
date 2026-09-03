"""The three residual ledgers, and the one that honestly returns no number at all.

Conservation is an invariant, the two 4F.4 measurements are measurements, and folding them
would hide the invariant. The third block is the one this whole surface exists to make
possible: an allocation with no independent truth to check it against, saying so, with its
reasons enumerated and a method control beside it that is a control on the model rather than on
these figures.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def body(client: TestClient, jurisdiction: str = "TX") -> dict:
    response = client.get(
        "/v1/validators/allocation", params={"jurisdiction": jurisdiction}
    )
    assert response.status_code == 200, response.text
    return response.json()


def blocks(client: TestClient) -> dict[str, dict]:
    return {block["name"]: block for block in body(client)["data"]["blocks"]}


def test_three_blocks_are_served_and_always_all_three(client: TestClient) -> None:
    """R-10. Three ledgers where the contract says two validators, deliberately: conservation
    is an invariant and the other two are measurements."""
    served = blocks(client)

    assert list(served) == ["conservation", "crosswalk", "independent_truth"]


def test_the_response_names_the_model_the_residuals_were_measured_against(
    client: TestClient,
) -> None:
    data = body(client)["data"]

    assert data["jurisdiction_code"] == "TX"
    assert data["model_id"]


def test_conservation_serves_its_coverage_and_decomposes_it_by_cause(
    client: TestClient,
) -> None:
    """N-1. The split is exact by construction, so a residual is volume with no eligible well
    to carry it -- decomposed by a closed cause vocabulary on the ledger, not by a quarantine
    reason code, because nothing failed to parse."""
    block = blocks(client)["conservation"]

    assert block["outcome"] == "measured"
    assert block["rule_id"] == "cr_tx_allocation_v0_1"
    assert set(block["decomposition"]) == {
        "no_crosswalk_row",
        "no_eligible_well",
        "all_wells_after_month",
        "negative_correction",
    }
    assert int(block["lease_months_total"]["value"]) > 0


def test_every_count_and_share_is_a_figure_with_a_handle(client: TestClient) -> None:
    """No naked numbers runs here too: a residual a reader cannot resolve is a claim about the
    data with nothing behind it."""
    block = blocks(client)["conservation"]

    for key in (
        "lease_months_total",
        "lease_months_unallocated",
        "share_unallocated",
        "share_allocated_to_retired_wells",
    ):
        assert "#" in block[key]["d"], key
        assert block[key]["unit"], key
    for cause, item in block["decomposition"].items():
        assert "#" in item["d"], cause


def test_the_retired_share_is_served_as_the_bound_on_the_undated_case(
    client: TestClient,
) -> None:
    """M-18. The one eligibility error term with no date behind it, bounded rather than open:
    a plugged status with no plug date does not filter, so what it can cost is served."""
    block = blocks(client)["conservation"]

    assert 0 <= float(block["share_allocated_to_retired_wells"]["value"]) <= 1
    assert block["share_allocated_to_retired_wells"]["unit"] == "share"


def test_the_degraded_threshold_is_the_rule_s_and_not_the_status_page_s(
    client: TestClient,
) -> None:
    """N-8. Half a percent of Texas volume with no well to carry it is a data question, and
    below that it is the long tail of leases whose only well predates the crosswalk. An
    engineer inventing the number is the failure this reads it from the rule to prevent."""
    block = blocks(client)["conservation"]

    assert block["degraded_at"] == "0.005"
    assert block["degraded"] is False


def test_the_third_block_returns_no_independent_truth_with_its_reasons(
    client: TestClient,
) -> None:
    """M-10/M-11. A 200 with a stated outcome and named reasons, in the shape
    control_unavailable already takes: not an omission, and not a number."""
    block = blocks(client)["independent_truth"]

    assert block["outcome"] == "no_independent_truth"
    assert len(block["reasons"]) == 3
    joined = " ".join(block["reasons"])
    assert "no per-well Texas production" in joined
    assert "26-month" in joined
    assert "rollups of the same lease rows" in joined


def test_the_third_block_carries_no_figure_pretending_to_be_a_control(
    client: TestClient,
) -> None:
    """The Montana study is a control on the model, which is a different claim from a control
    on these figures, so it never appears as a residual of them."""
    block = blocks(client)["independent_truth"]

    assert "share_unallocated" not in block
    assert "districts" not in block


def test_the_crosswalk_block_says_it_has_not_been_built_rather_than_serving_zero(
    client: TestClient,
) -> None:
    """A zero disagreement and an unbuilt mart are different facts, and only one of them is
    good news."""
    block = blocks(client)["crosswalk"]

    assert block["outcome"] == "not_available"
    assert block["rule_id"] == "cr_tx_ewa_role_1"
    assert block["reasons"]


def test_a_jurisdiction_that_registers_no_allocation_is_refused_by_name(
    client: TestClient,
) -> None:
    response = client.get("/v1/validators/allocation", params={"jurisdiction": "MT"})

    assert response.status_code == 404
    assert "MT" in response.json()["detail"]


def test_an_unregistered_jurisdiction_is_refused_rather_than_answered_empty(
    client: TestClient,
) -> None:
    response = client.get("/v1/validators/allocation", params={"jurisdiction": "WY"})

    assert response.status_code == 404


def test_the_response_links_to_both_rules_a_reader_would_want_next(
    client: TestClient,
) -> None:
    links = body(client)["links"]

    assert links["allocation_rule"] == "/v1/conformance/cr_tx_allocation_v0_1"
    assert links["error_bounds_rule"] == "/v1/conformance/cr_alloc_v0_error_bounds_1"
