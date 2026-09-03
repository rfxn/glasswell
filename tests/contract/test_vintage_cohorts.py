"""`/v1/wells/vintage-cohorts`: the cohort key is a rule, and the population states its edge."""

from __future__ import annotations

import psycopg
from fastapi.testclient import TestClient

from glasswell.marts.cumulatives import STATE_API_PREFIXES
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


def test_the_support_measure_is_named_and_registered_rather_than_decided_in_a_query(
    client: TestClient,
) -> None:
    """MA-1's half: the field is named for what it counts and the rule declares the measure.

    This guards the naming and the registration only. It reads no served count, so it cannot
    detect a wrong aggregate — the two tests below are what do that.
    """
    rule = client.get("/v1/conformance/cr_nd_vintage_cohort_1").json()["data"]
    measure = rule["spec"]["support_measure"]
    cohorts = client.get(PATH).json()["data"]["cohorts"]

    assert measure["field"] == "wells_with_a_filed_month"
    assert "reported_zero" in measure["definition"]
    assert "cr_producing_window_1" in measure["why_not_the_producing_classification"]
    assert all("wells_with_a_filed_month" in cohort for cohort in cohorts)
    assert not any("producing_wells" in cohort for cohort in cohorts)


def test_every_cohort_s_support_is_the_wells_its_totals_actually_draw_from(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """BL-1: the rule row and this endpoint must not report two numbers for one quantity.

    The expectation is computed from marts.well_cumulatives directly, under the same predicate
    the cumulative admits, so it is independent of the rollup's own SQL. A support count taken
    on any other measure — `months_reported > 0` was the one that shipped — disagrees here.
    """
    with seeded.cursor() as cursor:
        cursor.execute(
            "select coalesce(extract(year from w.spud_date)::int::text, 'no_spud_date'),"
            "       count(distinct c.api10) filter ("
            "           where c.months_reported + c.months_reported_zero > 0)"
            "  from canonical.wells_latest w"
            "  join marts.well_cumulatives c on c.api10 = w.api10"
            " where w.state_code = '33' group by 1"
        )
        expected = dict(cursor.fetchall())
    cohorts = client.get(PATH).json()["data"]["cohorts"]

    assert expected, "no ND cohort reached the mart, so this proves nothing"
    served = {
        (str(item["cohort_year"]) if item["cohort_year"] is not None else "no_spud_date"): int(
            item["wells_with_a_filed_month"]["value"]
        )
        for item in cohorts
    }
    assert served == expected


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
    # Exact, not a floor: six ND wells carry spud year 2019, and four of them admit a month —
    # the example well, the two that filed oil, and this zero-filer. `months_reported > 0`
    # serves 3 by dropping exactly this well, so a floor of 3 would pass on the defect it
    # claims to catch.
    assert int(keyed["wells_with_a_filed_month"]["value"]) == 4


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
    # Every jurisdiction the registry puts in the cumulatives scope, read from that scope
    # rather than typed: the cohort mart is built over the same population, so a state
    # registered into one is served by the other and a literal here would say otherwise.
    assert scope["states_served"] == list(STATE_API_PREFIXES)
    codes = {warning["code"] for warning in body["meta"]["warnings"]}
    assert "population_state_truncated" in codes


def test_a_well_with_no_spud_date_is_its_own_cohort(client: TestClient) -> None:
    """Never folded into a year and never dropped; the cost of the key is served, not hidden."""
    cohorts = client.get(PATH).json()["data"]["cohorts"]

    unkeyed = [item for item in cohorts if item["cohort_year"] is None]
    assert len(unkeyed) == 1
    assert unkeyed[0]["cohort_key_semantics"] == "no_spud_date"
    # Two: the North Dakota well the fixture strips the spud date from, and the Texas well --
    # the RRC publishes no spud date in this slice at all, so every Texas well lands here. It
    # is one cohort with two wells rather than a year invented for either of them.
    assert int(unkeyed[0]["wells"]["value"]) == 2
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


def test_an_unrefreshed_mart_is_refused_by_name_rather_than_served_a_null_vintage(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """gate-v075 MINOR-4.

    `max(snapshot_vintage)` over an empty rollup is null, and the endpoint served it against a
    schema that declares snapshot_vintage a required date — FastAPI does not catch it because
    the handler returns a JSONResponse. An empty `cohorts` beside it would have read as "North
    Dakota has no cohorts", which is a statement about the wells rather than about the refresh.
    The per-well sibling already refuses by name in this state.
    """
    with seeded.cursor() as cursor:
        cursor.execute("delete from marts.well_cumulatives")
    seeded.commit()

    response = client.get(PATH)
    body = response.json()

    assert response.status_code == 503, response.text
    assert body["type"].endswith("service_degraded")
    assert "marts.well_cumulatives" in body["detail"]
    assert "not a statement that no cohort exists" in body["detail"]
