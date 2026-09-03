"""What a TX well serves, and what it deliberately does not.

The ND fixtures cannot exercise any of this: a Texas well is the only one with a depth figure,
a jurisdiction that reports at the lease, and a production endpoint whose honest answer is a
disclosure rather than a series. A gate that only ever sees ND data is green on data it does
not represent (N-1).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.contract.conftest import TX_API10

PENDING = "production_pending_allocation"
# The disclosure's rule, superseded by the one that admits an allocated series. Both stay
# served: lineage.conformance_rules is append-only and an as_of before this train still
# resolves the sentence the card used to show.
SUPERSEDED_DISCLOSURE = "cr_tx_allocation_scope_1"
ALLOCATION_RULE = "cr_tx_allocation_v0_1"
ERROR_RULE = "cr_alloc_v0_error_bounds_1"


def envelope(client: TestClient, path: str, **params) -> dict:
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_tx_well_is_served_by_the_same_endpoint_nd_wells_are(client: TestClient) -> None:
    body = envelope(client, f"/v1/wells/{TX_API10}")

    assert body["data"]["api10"] == TX_API10
    assert body["data"]["state_code"] == "42"
    assert body["data"]["basin"] == "permian"
    assert body["data"]["operator_name_reported"]
    assert body["data"]["surface_point"] is not None


def test_the_tx_well_appears_in_the_collection_and_filters_by_county(client: TestClient) -> None:
    listed = envelope(client, "/v1/wells", county="003", limit=50)

    assert [item["api10"] for item in listed["data"]] == [TX_API10]
    assert listed["data"][0]["spud_date"] is None, "TX publishes no spud date in this slice"


def test_total_depth_is_a_figure_with_a_handle_that_resolves(client: TestClient) -> None:
    """R6: a served number carries its derivation, and the depth is the TX card's own number."""
    depth = envelope(client, f"/v1/wells/{TX_API10}")["data"]["total_depth_ft"]

    assert depth["unit"] == "ft"
    assert depth["value"] == "11450.0"
    assert "#" in depth["d"]
    chain = envelope(client, "/v1/explain", h=depth["d"], depth="full")["data"]["chains"][0]
    assert chain["handle"] == depth["d"]
    assert chain["terminals"], "the depth figure resolves to no checksummed file"


def test_the_geometry_records_the_datum_the_rrc_published_and_the_rule_that_moved_it(
    client: TestClient,
) -> None:
    body = envelope(client, f"/v1/wells/{TX_API10}")

    assert [row["source_datum"] for row in body["data"]["geometry"]] == ["EPSG:4267"]
    assert body["data"]["storage_crs"] == "EPSG:4326"


def test_the_card_no_longer_says_production_is_pending(client: TestClient) -> None:
    """The disclosure was true until the allocation shipped and is false the moment it does.

    `cr_tx_production_grain_1` supersedes the rule that said no well-level TX volume would be
    served, and it carries the third spec key that tells the predicate so. A card still showing
    "pending allocation" over a chart would be the product contradicting itself.
    """
    body = envelope(client, f"/v1/wells/{TX_API10}")

    assert PENDING not in {warning["code"] for warning in body["meta"]["warnings"]}
    assert "reporting_rule" not in body["links"]
    assert body["links"]["cumulatives"] == f"/v1/wells/{TX_API10}/cumulatives"


def test_the_production_endpoint_serves_a_chart_and_says_it_is_allocated(
    client: TestClient,
) -> None:
    """Two series and no water column, and every point labelled as what it is."""
    body = envelope(client, f"/v1/wells/{TX_API10}/production")
    data = body["data"]

    assert data["streams"] == ["oil", "gas"]
    assert data["series"]["pm"] == ["2024-01", "2024-02", "2024-03"]
    assert data["series"]["oil_bbl"] == ["300.000", "301.000", "302.000"]
    assert data["reporting_level"] == "lease"
    assert PENDING not in {warning["code"] for warning in body["meta"]["warnings"]}


def test_no_water_column_is_served_because_the_regulator_publishes_none(
    client: TestClient,
) -> None:
    """`OG_LEASE_CYCLE` has oil, condensate, gas, casinghead gas, allowables, balances and
    dispositions, and no water column at all. An empty water array would read as a well that
    produced no water rather than as a regulator that files none."""
    data = envelope(client, f"/v1/wells/{TX_API10}/production")["data"]

    assert "water_bbl" not in data["series"]
    assert "water" not in data["streams"]


def test_every_allocated_point_carries_its_class_its_divisor_and_its_granularity(
    client: TestClient,
) -> None:
    """N-5. The scalar cannot describe a series that is partly observed and partly allocated,
    and the additive-only freeze forbids changing its type, so the arrays are authoritative."""
    series = envelope(client, f"/v1/wells/{TX_API10}/production")["data"]["series"]

    assert series["oil_bbl_granularity_by_month"] == ["lease_allocated"] * 3
    assert series["oil_bbl_allocation_class_by_month"] == ["allocated_equal_share"] * 3
    assert series["oil_bbl_eligible_wells_by_month"] == [3, 3, 3]
    # The gas stream sums two leases every month, so the dominant class is the safe one:
    # a month that is partly a share reads as a share, never as an observation.
    assert series["gas_mcf_granularity_by_month"] == ["lease_allocated"] * 3
    assert series["gas_mcf_allocation_class_by_month"] == ["allocated_equal_share"] * 3


def test_an_allocated_series_carries_the_model_that_produced_it(client: TestClient) -> None:
    """`envelope.py` makes the model id mandatory alongside the granularity, because the
    versioned artifact that produced a number is part of the number."""
    data = envelope(client, f"/v1/wells/{TX_API10}/production")["data"]

    assert data["allocation"]["model_id"]
    assert data["allocation"]["rule_id"] == "cr_tx_production_grain_1"
    assert set(data["series"]["oil_bbl_granularity_by_month"]) == {"lease_allocated"}
    assert data["_units"]["series.oil_bbl"] == "bbl"
    assert data["_basis"]["series.oil_bbl"] == "oil+condensate"


def test_the_absent_error_bound_is_served_rather_than_omitted(client: TestClient) -> None:
    """R-13. `not_measured` naming the study that will close it makes the absence a resolvable
    fact; a band measured on Montana's leases over a horizon nobody has shown to match would
    be a naked number with a decoration on it."""
    data = envelope(client, f"/v1/wells/{TX_API10}/production")["data"]

    assert data["allocation"]["error_bounds"] == {
        "outcome": "not_measured",
        "measured_by_rule": ERROR_RULE,
    }


def test_a_dual_lease_wellbore_says_which_leases_the_sum_is_over(client: TestClient) -> None:
    """M-16. The served point is the sum of a well's shares and is stored nowhere; each share
    is separately addressable with its lease key."""
    body = envelope(client, f"/v1/wells/{TX_API10}/production")

    assert body["data"]["allocation"]["leases"] == ["G-08-000303", "O-08-000101"]
    assert "well_carries_more_than_one_lease" in {
        warning["code"] for warning in body["meta"]["warnings"]
    }


def test_the_incomplete_window_is_warned_about_rather_than_left_to_look_like_decline(
    client: TestClient,
) -> None:
    """The Commission's own sentence: production records are substantially complete after
    about six months. A reader sees a decline, not an incompleteness."""
    warnings = {
        warning["code"]: warning
        for warning in envelope(client, f"/v1/wells/{TX_API10}/production")["meta"]["warnings"]
    }

    assert "production_incomplete_window" in warnings
    assert "2024-03" in warnings["production_incomplete_window"]["detail"]


def test_as_of_is_refused_on_the_allocated_series_with_a_stated_reason(
    client: TestClient,
) -> None:
    """M-19. The mart holds one snapshot per key, so an older as_of would return today's
    allocation labelled with the caller's date, and the back-projection makes the two differ by
    the whole well set. A refusal is a served class, not a silence."""
    response = client.get(f"/v1/wells/{TX_API10}/production", params={"as_of": "2020-01-01"})

    assert response.status_code == 422, response.text
    problem = response.json()
    assert problem["type"].endswith("as_of_not_supported")
    assert "one snapshot per key" in problem["detail"]
    assert "cr_tx_production_grain_1" in problem["detail"]
    assert ALLOCATION_RULE in problem["detail"]


def test_the_disclosure_the_allocation_replaced_is_still_readable(client: TestClient) -> None:
    """Superseded, not deleted: any as_of before this train still resolves the sentence the
    card used to show, and the derivations that cited it go on citing what shaped them."""
    body = envelope(client, f"/v1/conformance/{SUPERSEDED_DISCLOSURE}")

    assert body["data"]["spec"]["reporting_level"] == "lease"
    assert body["data"]["spec"]["well_level_production_served"] is False


def test_an_nd_well_carries_no_such_disclosure(client: TestClient) -> None:
    """The disclosure is a registry fact about a jurisdiction, not a banner on every well."""
    from glasswell.api.examples import EXAMPLE_API10

    body = envelope(client, f"/v1/wells/{EXAMPLE_API10}")

    assert PENDING not in {warning["code"] for warning in body["meta"]["warnings"]}
    assert "reporting_rule" not in body["links"]


def test_the_rule_behind_the_allocation_is_readable(client: TestClient) -> None:
    body = envelope(client, f"/v1/conformance/{ALLOCATION_RULE}")

    assert body["data"]["rule_kind"] == "code_ref"
    assert body["data"]["spec"]["allocation_model_id"]
    assert body["data"]["spec"]["as_of_supported"] is False
    assert body["data"]["rationale"]


def test_the_card_said_pending_until_the_day_the_allocation_was_published(
    client: TestClient,
) -> None:
    """The two clocks, on the real supersession rather than a planted one.

    `cr_tx_production_grain_1` supersedes the disclosure with an effective date and a published
    vintage of 2026-09-02. A knowledge cut before that resolves the disclosure and the card
    says production is pending; a cut at or after it resolves the successor and the card draws
    a chart. Nothing about the answer changes retroactively, which is the whole point of
    publishing a rule separately from dating it.
    """
    path = f"/v1/wells/{TX_API10}"
    before = envelope(client, path, as_of="2026-08-28")
    after = envelope(client, path, as_of="2026-09-02")

    assert PENDING in {warning["code"] for warning in before["meta"]["warnings"]}
    assert before["links"]["reporting_rule"] == f"/v1/conformance/{SUPERSEDED_DISCLOSURE}"
    assert PENDING not in {warning["code"] for warning in after["meta"]["warnings"]}
    assert "reporting_rule" not in after["links"]


def a_point_handle(client: TestClient, column: str, month: str) -> str:
    """The handle the chart's own button mints: the column's, addressed at one month."""
    lineage = envelope(client, f"/v1/wells/{TX_API10}/production")["data"]["_lineage"]
    derivation, _, selector = lineage[f"series.{column}"].partition("#")
    return f"{derivation}#{selector}&pm={month}"


def test_the_point_handle_the_chart_mints_resolves_to_the_lease_row(
    client: TestClient,
) -> None:
    """B1. The summed per-well point is a figure, so it is addressable as one.

    R6 and the masthead: every served figure carries a derivation handle and `?explain=true`
    resolves it. A chart whose every point handle answers `selector_ambiguous` serves numbers
    nobody can walk back, which is the one defect this system exists against.
    """
    handle = a_point_handle(client, "oil_bbl", "2024-01")

    chain = envelope(client, "/v1/explain", h=handle, depth="4")["data"]["chains"][0]

    assert chain["handle"] == handle
    rules = {
        rule["rule_id"] for node in chain["nodes"] for rule in node.get("conformance_rules", [])
    }
    assert ALLOCATION_RULE in rules
    datasets = [node.get("output", {}).get("dataset") for node in chain["nodes"]]
    assert "marts.tx_allocated_production" in datasets
    assert "canonical.production_monthly" in datasets, "the point does not reach the lease row"
    assert chain["terminals"], "the point resolves to no checksummed file"


def test_every_month_of_every_served_column_is_addressable(client: TestClient) -> None:
    """A handle that resolves for January and 422s for February is the same defect, found
    one month later. Each served point is recorded, including the months with no volume."""
    body = envelope(client, f"/v1/wells/{TX_API10}/production")
    months = body["data"]["series"]["pm"]

    for column in ("oil_bbl", "gas_mcf"):
        for month in months:
            handle = a_point_handle(client, column, month)
            response = client.get("/v1/explain", params={"h": handle, "depth": "4"})
            assert response.status_code == 200, f"{column} {month}: {response.text}"


def test_the_wire_says_the_lease_filed_it_never_that_this_well_reported_it(
    client: TestClient,
) -> None:
    """M1. 300 bbl was not reported: the lease filed 901 and 300 is a computed third of it.

    The glossary term the card itself renders is the contract -- an allocated figure is always
    labelled allocated and never observed -- and the bare word `reported` on a series in which
    no well-month was reported is that label, in the one vocabulary the band paints from.
    """
    series = envelope(client, f"/v1/wells/{TX_API10}/production")["data"]["series"]

    assert series["oil_bbl_null_semantics"] == ["lease_reported"] * 3
    assert series["gas_mcf_null_semantics"] == ["lease_reported"] * 3
    assert "reported" not in set(series["oil_bbl_null_semantics"])


def test_a_summed_point_states_the_count_of_shares_and_no_divisor(
    client: TestClient,
) -> None:
    """M2. 3 eligible wells plus 1 eligible well is not a four-well division.

    The oil stream is one lease split three ways and says so. The gas stream is two lease
    records summed, and there is no single divisor to state -- the per-lease one lives on each
    share's own `lk` handle, which resolves independently at alloc.apply.
    """
    series = envelope(client, f"/v1/wells/{TX_API10}/production")["data"]["series"]

    assert series["gas_mcf_eligible_wells_by_month"] == [None, None, None], (
        "a summed point states a divisor that divided nothing"
    )
    assert series["gas_mcf_shares_by_month"] == [2, 2, 2]
    assert series["oil_bbl_eligible_wells_by_month"] == [3, 3, 3]
    assert series["oil_bbl_shares_by_month"] == [1, 1, 1]
