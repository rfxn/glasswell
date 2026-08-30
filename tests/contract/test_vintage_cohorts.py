"""`/v1/wells/vintage-cohorts`: the cohort key is a rule, and the population states its edge."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.contract.test_well_cumulatives import handles

PATH = "/v1/wells/vintage-cohorts"


def test_the_collection_route_is_not_claimed_by_the_well_path(client: TestClient) -> None:
    """C7: `/wells/{api10}` declares ^\\d{10}$, and a pattern mismatch is a 422 after the
    route matches rather than a fall-through. This operation is declared before it."""
    response = client.get(PATH)

    assert response.status_code == 200, response.text


def test_the_key_is_the_rule_the_response_names(client: TestClient) -> None:
    body = client.get(PATH).json()

    assert body["data"]["cohort_basis"] == "spud_year"
    assert body["data"]["cohort_key_rule"] == "cr_nd_vintage_cohort_1"
    assert body["links"]["cr_nd_vintage_cohort_1"] == "/v1/conformance/cr_nd_vintage_cohort_1"


def test_the_support_distribution_is_on_the_cohort_scale_and_says_why(
    client: TestClient,
) -> None:
    """Protocol 4D: a section-scale band set would put nearly every cohort in one class."""
    support = client.get(PATH).json()["data"]["support_distribution"]

    assert set(support["classes"]) == {"0", "1-9", "10-99", "100-999", "1000+"}
    assert "section" in support["scale"]
    assert "wells_with_a_filed_month" in support["scale"]


def test_the_support_count_is_the_measure_the_rule_publishes(client: TestClient) -> None:
    """BL-1: the rule row and this endpoint must not report two numbers for one quantity.

    cr_nd_vintage_cohort_1 publishes its support figures measured as `the well's record admits
    at least one month into a total` — reported or reported_zero. A `months_reported > 0`
    aggregate excludes a well whose only filings are zeros, and on the deployed population that
    is the difference between a published 49 and a served 39 for the no-spud-date cohort.
    """
    rule = client.get("/v1/conformance/cr_nd_vintage_cohort_1").json()["data"]
    measure = rule["spec"]["support_measure"]
    cohorts = client.get(PATH).json()["data"]["cohorts"]

    assert measure["field"] == "wells_with_a_filed_month"
    assert "reported_zero" in measure["definition"]
    assert "cr_producing_window_1" in measure["why_not_the_producing_classification"]
    assert all("wells_with_a_filed_month" in cohort for cohort in cohorts)
    assert not any("producing_wells" in cohort for cohort in cohorts)


def test_a_well_whose_only_filing_is_a_zero_still_stands_behind_its_cohort(
    client: TestClient,
) -> None:
    """The measure's whole difference from `months_reported > 0`, exercised.

    OTHER_API10S[4] filed exactly one month and it was a zero. A filed zero is a filing, and
    the support count says so; the cumulative it supports is 0, which is a different fact from
    the null a well that filed nothing carries.
    """
    from tests.contract.conftest import OTHER_API10S

    zero_filer = OTHER_API10S[4]
    cumulative = client.get(f"/v1/wells/{zero_filer}/cumulatives").json()["data"]
    cohorts = client.get(PATH).json()["data"]["cohorts"]

    assert cumulative["coverage"]["oil_bbl"]["months_reported_zero"] == 1
    assert cumulative["coverage"]["oil_bbl"]["months_reported"] == 0
    assert cumulative["cumulative"]["oil_bbl"]["value"] == "0.000"
    keyed = next(item for item in cohorts if item["cohort_year"] is not None)
    # Every seeded ND well but one shares spud year 2019; the zero-filer is inside that cohort
    # and is counted, so the support count exceeds the wells with a reported month.
    assert int(keyed["wells_with_a_filed_month"]["value"]) >= 3


def test_the_spacing_assumption_is_stated_rather_than_omitted(client: TestClient) -> None:
    spacing = client.get(PATH).json()["data"]["spacing_assumption"]

    assert spacing["applies"] is False
    assert spacing["reason"].strip()
    assert "slot" in spacing["reason"].lower()


def test_the_population_says_where_it_stops(client: TestClient) -> None:
    body = client.get(PATH).json()

    scope = body["data"]["population_scope"]
    assert scope["basin_complete"] is False
    assert "Montana" in scope["detail"]
    assert scope["states_served"] == ["33"]
    codes = {warning["code"] for warning in body["meta"]["warnings"]}
    assert "population_state_truncated" in codes


def test_a_well_with_no_spud_date_is_its_own_cohort(client: TestClient) -> None:
    """Never folded into a year and never dropped; the cost of the key is served, not hidden."""
    cohorts = client.get(PATH).json()["data"]["cohorts"]

    unkeyed = [item for item in cohorts if item["cohort_year"] is None]
    assert len(unkeyed) == 1
    assert unkeyed[0]["cohort_key_semantics"] == "no_spud_date"
    assert int(unkeyed[0]["wells"]["value"]) > 0
    assert unkeyed[0]["wells"]["unit"] == "wells"
    assert unkeyed[0]["wells_with_a_filed_month"]["unit"] == "wells"


def test_a_keyed_cohort_carries_its_totals_with_the_snapshot_vintage(
    client: TestClient,
) -> None:
    data = client.get(PATH).json()["data"]

    keyed = [item for item in data["cohorts"] if item["cohort_year"] is not None]
    assert keyed
    oil = keyed[0]["cumulative"]["oil_bbl"]
    assert (oil["unit"], oil["basis"]) == ("bbl", "oil+condensate")
    assert oil["report_vintage"] == data["snapshot_vintage"]


def test_the_response_echoes_the_vintage_its_keys_were_read_at(client: TestClient) -> None:
    """gt_spud_date asks for exactly this: a spud-date cohort says which vintage it read."""
    data = client.get(PATH).json()["data"]

    assert data["spud_dates_read_at"] is not None


def test_every_handle_resolves(client: TestClient) -> None:
    data = client.get(PATH).json()["data"]
    found = handles(data)

    assert found
    for handle in sorted(found):
        response = client.get("/v1/explain", params={"h": handle, "depth": "full"})
        assert response.status_code == 200, (handle, response.text)


def test_explain_changes_no_value_in_data(client: TestClient) -> None:
    plain = client.get(PATH).json()
    explained = client.get(PATH, params={"explain": "true"}).json()

    assert explained["data"] == plain["data"]
