"""`/v1/wells/facets`: counted buckets, what they exclude, and what has no value at all."""

from __future__ import annotations

from datetime import date

import psycopg
from fastapi.testclient import TestClient

from glasswell.api.routers.facets import DIMENSIONS
from glasswell.lineage.ids import parse_handle
from tests.support.seed import seed_conformance_rule, seed_derivation, seed_well

# Enough operators to be truncated by a small `top`, with a deliberate long tail and a
# deliberate absence, because both are what this surface exists to state.
_TX_POPULATION = (
    ("PIONEER NATURAL RESOURCES USA INC", 5),
    ("DIAMONDBACK E&P LLC", 4),
    ("APACHE CORPORATION", 3),
    ("DEVON ENERGY PRODUCTION CO LP", 2),
    ("CHEVRON USA INC", 1),
)
_TX_ABSENT = 7


def _seed_tx(connection: psycopg.Connection) -> None:
    """A Texas population whose shape mirrors the real one: a head, a tail, and an absence."""
    serial = 0
    for operator, wells in _TX_POPULATION:
        for _ in range(wells):
            serial += 1
            seed_well(
                connection,
                api10=f"42{serial:08d}",
                state_code="42",
                county_code_at_permit="003",
                basin="permian",
                operator_name_reported=operator,
                status_canonical="active",
                well_type_reported="PRODUCING",
                completion_date=date(2019, 4, 12),
            )
    for _ in range(_TX_ABSENT):
        serial += 1
        seed_well(
            connection,
            api10=f"42{serial:08d}",
            state_code="42",
            county_code_at_permit="003",
            basin="permian",
            operator_name_reported=None,
            status_canonical="active",
            well_type_reported="PRODUCING",
            completion_date=date(2019, 4, 12),
        )
    connection.commit()


def _facets(client: TestClient, **params: object) -> dict:
    params.setdefault("state", "42")
    params.setdefault("by", "operator")
    response = client.get("/v1/wells/facets", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_buckets_the_remainder_and_the_absence_sum_to_the_population(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The invariant the whole surface rests on. If it can be broken, every number is a claim
    about a population the reader cannot reconstruct."""
    _seed_tx(seeded)
    body = _facets(client, top=2)
    data = body["data"]

    listed = sum(int(bucket["wells"]["value"]) for bucket in data["buckets"])
    remainder = int(data["remainder"]["wells"]["value"])
    absent = int(data["absence"]["wells"]["value"])

    assert listed + remainder + absent == int(data["wells"]["value"])


def test_under_a_search_the_buckets_reconcile_against_the_matched_population(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The unsearched sum does not extend to a search. `q` narrows the ranked arms and never
    the absence bucket, so the three of them fall short of `wells` by the unmatched values —
    which is why the reconciling figure under a search is `matched_wells`."""
    _seed_tx(seeded)
    # "usa" matches two operators, so the cut is real and the remainder is served rather than
    # absent — the arm that would otherwise leave the relationship untested.
    data = _facets(client, top=1, q="usa")["data"]

    listed = sum(int(bucket["wells"]["value"]) for bucket in data["buckets"])
    remainder = int(data["remainder"]["wells"]["value"])
    absent = int(data["absence"]["wells"]["value"])

    assert data["remainder"]["values"] == 1
    assert listed + remainder == int(data["matched_wells"]["value"])
    assert absent == _TX_ABSENT
    assert listed + remainder + absent < int(data["wells"]["value"])


def test_the_absence_is_its_own_named_bucket_and_never_enters_the_ranking(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The 70,039-well case. Ranked, it would outrank every real Texas operator; dropped, the
    buckets would not sum to the population."""
    _seed_tx(seeded)
    data = _facets(client, top=15)["data"]

    assert data["absence"]["label"] == "not reported"
    assert int(data["absence"]["wells"]["value"]) == _TX_ABSENT
    assert [bucket["value"] for bucket in data["buckets"]] == [
        operator for operator, _ in _TX_POPULATION
    ]
    assert None not in [bucket["value"] for bucket in data["buckets"]]


def test_the_texas_operator_absence_cites_the_rule_that_decided_it(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """R8: the absence is a registered decision with a rationale and a date, not an inference
    this endpoint makes at serving time."""
    _seed_tx(seeded)
    body = _facets(client)

    assert body["data"]["absence"]["rule_id"] == "cr_tx_operator_absence_1"
    assert body["links"]["cr_tx_operator_absence_1"] == "/v1/conformance/cr_tx_operator_absence_1"
    resolved = client.get("/v1/conformance/cr_tx_operator_absence_1")
    assert resolved.status_code == 200, resolved.text


def test_the_remainder_counts_what_the_list_leaves_out(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    _seed_tx(seeded)
    data = _facets(client, top=2)["data"]

    assert len(data["buckets"]) == 2
    assert data["remainder"]["values"] == len(_TX_POPULATION) - 2
    excluded = sum(wells for _, wells in _TX_POPULATION[2:])
    assert int(data["remainder"]["wells"]["value"]) == excluded
    assert str(excluded) in data["remainder"]["detail"]


def test_a_complete_list_has_no_remainder_rather_than_a_zero_one(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    _seed_tx(seeded)

    assert _facets(client, top=50)["data"]["remainder"] is None


def test_a_restated_well_is_counted_once_and_not_once_per_vintage(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """canonical.wells is append-only and bitemporal, so North Dakota carries two rows per
    well. A facet that grouped the table directly would report every ND operator at 2x."""
    seed_well(
        seeded,
        api10="4299999999",
        state_code="42",
        effective_from=date(2026, 1, 1),
        operator_name_reported="FIRST OPERATOR LLC",
    )
    seed_well(
        seeded,
        api10="4299999999",
        state_code="42",
        effective_from=date(2026, 6, 1),
        operator_name_reported="SECOND OPERATOR LLC",
    )
    seeded.commit()
    data = _facets(client, top=50)["data"]
    counts = {bucket["value"]: int(bucket["wells"]["value"]) for bucket in data["buckets"]}

    # The restated well contributes its current operator once and its superseded one never.
    assert counts["SECOND OPERATOR LLC"] == 1
    assert "FIRST OPERATOR LLC" not in counts
    # One pre-seeded Texas well plus this one, counted as wells rather than as spine rows.
    assert int(data["wells"]["value"]) == 2


def test_the_search_ranks_the_whole_state_and_not_the_served_page(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The API-shaping question: with 9,369 operators, a search over the fifteen on screen
    answers "no such operator" for the 9,354 it never loaded."""
    _seed_tx(seeded)
    # CHEVRON is last by well count, so a page-scoped search at top=2 could not reach it.
    data = _facets(client, top=2, q="chevron")["data"]

    assert [bucket["value"] for bucket in data["buckets"]] == ["CHEVRON USA INC"]
    assert int(data["matched_wells"]["value"]) == 1


def test_the_search_does_not_narrow_the_absence_bucket(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """A well with no operator name matches no operator text. Filtering the absence bucket by
    the search would make it vanish the moment a reader typed a letter."""
    _seed_tx(seeded)
    data = _facets(client, q="chevron")["data"]

    assert int(data["absence"]["wells"]["value"]) == _TX_ABSENT


def test_the_absence_bucket_says_the_search_did_not_narrow_it(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """Under a search the buckets and the remainder reconcile against `matched_wells`, and the
    absence bucket alone is still the whole state. Its count is identical to the unsearched one
    while every figure around it has moved, so the sentence beside it has to say which
    population it belongs to — served with the count so the two cannot drift apart."""
    _seed_tx(seeded)
    unsearched = _facets(client)["data"]["absence"]
    searched = _facets(client, q="chevron")["data"]["absence"]

    assert int(searched["wells"]["value"]) == int(unsearched["wells"]["value"]) == _TX_ABSENT
    assert searched["detail"] != unsearched["detail"]
    assert "chevron" in searched["detail"]
    assert "Texas" in searched["detail"]
    assert "chevron" not in unsearched["detail"]


def test_a_search_matching_nothing_says_so_rather_than_serving_a_silent_empty_list(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    _seed_tx(seeded)
    data = _facets(client, q="no such operator anywhere")["data"]

    assert data["buckets"] == []
    assert data["remainder"] is None
    assert "No " in data["caption"] or "0 " in data["caption"]


def test_a_state_the_spine_has_no_wells_for_is_refused_not_served_as_empty(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """New Mexico's promotion is gated, so it holds no rows. An empty operator list would read
    as a fact about New Mexico's operators rather than about its ingest."""
    _seed_tx(seeded)
    response = client.get("/v1/wells/facets", params={"state": "30", "by": "operator"})

    assert response.status_code == 422
    body = response.json()
    assert "no well in state 30" in body["detail"]
    assert body["errors"][0]["code"] == "state_not_loaded"


def test_the_served_state_list_names_the_unloaded_states_rather_than_hiding_them(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    _seed_tx(seeded)
    states = {row["code"]: row for row in _facets(client)["data"]["states"]}

    assert states["30"]["loaded"] is False
    assert states["30"]["name"] == "New Mexico"
    assert states["42"]["loaded"] is True


def test_every_count_carries_a_handle_that_explain_resolves(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """No naked numbers: a bucket, the remainder, the absence and the total are all figures."""
    _seed_tx(seeded)
    body = _facets(client, top=2, explain="true")
    data = body["data"]

    handles = [bucket["wells"]["d"] for bucket in data["buckets"]]
    handles += [data["remainder"]["wells"]["d"], data["absence"]["wells"]["d"]]
    handles.append(data["wells"]["d"])

    assert all(handle for handle in handles)
    for handle in handles:
        resolved = client.get("/v1/explain", params={"h": handle})
        assert resolved.status_code == 200, f"{handle}: {resolved.text}"


def test_a_truncated_list_warns_that_it_is_a_cut(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    _seed_tx(seeded)
    codes = {
        warning["code"] for warning in _facets(client, top=2)["meta"]["warnings"]
    }

    assert "list_truncated" in codes


def test_the_caption_states_what_the_list_is_a_cut_of(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """How a reader learns what the top-N excludes without reading the remainder arithmetic."""
    _seed_tx(seeded)
    data = _facets(client, top=2)["data"]

    assert "2" in data["caption"]
    assert str(len(_TX_POPULATION)) in data["caption"]
    assert "Texas" in data["caption"]


def test_the_caption_names_the_direction_the_list_was_actually_ranked_in(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """`order=asc` serves the values with the fewest wells. A caption reading "with the most
    wells" over that list is a served sentence that is false about the rows beside it."""
    _seed_tx(seeded)

    def caption(sort: str, order: str) -> str:
        return _facets(client, top=2, sort=sort, order=order)["data"]["caption"]

    assert caption("count", "desc") == (
        "The 2 operator values with the most wells, of 5 operator values in Texas."
    )
    assert caption("count", "asc") == (
        "The 2 operator values with the fewest wells, of 5 operator values in Texas."
    )
    # The button beside the caption reads `Z to A` / `A to Z` under `sort=value`; one
    # vocabulary, or the two controls describe the same parameter in different words.
    assert caption("value", "desc") == ("2 of 5 operator values in Texas, ranked by value, Z to A.")
    assert caption("value", "asc") == ("2 of 5 operator values in Texas, ranked by value, A to Z.")
    # The prose is bound to the rows: ascending by count serves the two smallest operators.
    ascending = _facets(client, top=2, sort="count", order="asc")["data"]
    assert [bucket["value"] for bucket in ascending["buckets"]] == [
        "CHEVRON USA INC",
        "DEVON ENERGY PRODUCTION CO LP",
    ]


def test_a_complete_list_says_which_way_it_is_ranked_rather_than_only_by_what(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    _seed_tx(seeded)

    def caption(sort: str, order: str) -> str:
        return _facets(client, top=50, sort=sort, order=order)["data"]["caption"]

    assert caption("count", "desc") == (
        "All 5 operator values in Texas, ranked by well count, highest first."
    )
    assert caption("count", "asc") == (
        "All 5 operator values in Texas, ranked by well count, lowest first."
    )
    assert caption("value", "asc") == ("All 5 operator values in Texas, ranked by value, A to Z.")


def test_ranking_by_value_orders_by_the_value_and_not_the_count(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    _seed_tx(seeded)
    data = _facets(client, top=50, sort="value", order="asc")["data"]

    values = [bucket["value"] for bucket in data["buckets"]]
    assert values == sorted(values)


def test_the_searched_caption_pluralises_on_what_it_counted(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """"All 1 operator values" was on screen at every width: the `q` arm hard-coded the s."""
    _seed_tx(seeded)

    assert _facets(client, top=50, q="chevron")["data"]["caption"] == (
        "All 1 operator value matching 'chevron' in Texas, ranked by well count, highest first."
    )


def test_every_dimension_serves_and_sums(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """A dimension that 422s or mis-sums is worse than one that was never offered."""
    _seed_tx(seeded)
    for dimension in ("operator", "county", "status", "well_type", "completion_year"):
        data = _facets(client, by=dimension, top=50)["data"]
        listed = sum(int(bucket["wells"]["value"]) for bucket in data["buckets"])
        absent = int(data["absence"]["wells"]["value"]) if data["absence"] else 0
        remainder = int(data["remainder"]["wells"]["value"]) if data["remainder"] else 0

        assert listed + remainder + absent == int(data["wells"]["value"]), dimension


def test_a_bucket_links_to_the_rows_behind_it(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """A count with nowhere to go is a dead end; the link is what makes the facet a control."""
    _seed_tx(seeded)
    bucket = _facets(client, top=1)["data"]["buckets"][0]

    # The limit rides the URL: httpx replaces a URL query wholesale when `params` is given,
    # which silently dropped the filter and made this assertion pass against every well.
    followed = client.get(f"{bucket['links']['wells']}&limit=200")
    assert followed.status_code == 200, followed.text
    names = {row["operator_name_reported"] for row in followed.json()["data"]}
    assert names == {bucket["value"]}


def test_a_bucket_link_is_scoped_to_the_state_it_was_counted_in(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """A bucket is counted within one state, so its link has to narrow to that state. Without
    `state` on the collection, a county-003 link returned Texas and North Dakota together."""
    _seed_tx(seeded)
    seed_well(
        seeded,
        api10="3399999999",
        state_code="33",
        county_code_at_permit="003",
        operator_name_reported="A ND OPERATOR",
    )
    seeded.commit()
    bucket = _facets(client, by="county", top=1)["data"]["buckets"][0]

    followed = client.get(f"{bucket['links']['wells']}&limit=200")
    assert followed.status_code == 200, followed.text
    # The API-10 carries its own state code in the first two digits, which is the spine's
    # own answer to "which state" and needs no column the projection may not carry.
    prefixes = {row["api10"][:2] for row in followed.json()["data"]}
    assert prefixes == {"42"}


def test_a_bucket_link_percent_encodes_the_value_it_carries(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """Written into a URL verbatim, `DIAMONDBACK E&P LLC` ends at the ampersand and mints a
    stray `P LLC` parameter, so the published link narrows to a different population than the
    count beside it — and the spaces make it a URL no agent or auditor can issue at all."""
    _seed_tx(seeded)
    buckets = {
        bucket["value"]: bucket for bucket in _facets(client, top=50)["data"]["buckets"]
    }
    link = buckets["DIAMONDBACK E&P LLC"]["links"]["wells"]

    assert link == "/v1/wells?operator=DIAMONDBACK+E%26P+LLC&state=42"
    followed = client.get(f"{link}&limit=200")
    assert followed.status_code == 200, followed.text
    names = {row["operator_name_reported"] for row in followed.json()["data"]}
    assert names == {"DIAMONDBACK E&P LLC"}


def test_a_dimension_the_collection_cannot_filter_on_publishes_no_link(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """`/v1/wells` accepts no completion-year filter, so the bucket offers no link rather than
    one that narrows to something else."""
    _seed_tx(seeded)
    bucket = _facets(client, by="completion_year", top=1)["data"]["buckets"][0]

    assert bucket["links"] == {}


def test_the_collection_declares_every_filter_a_facet_bucket_narrows_by(
    client: TestClient,
) -> None:
    """A bucket's link is only as good as the dataset declaration behind it: a filter the
    collection applies but does not declare is one the grid cannot show a chip for, and one a
    reader cannot clear on its own once a well-type bucket has set it."""
    declaration = client.get("/openapi.json").json()["paths"]["/v1/wells"]["get"][
        "x-glasswell-dataset"
    ]

    narrowed = {entry["filter"] for entry in DIMENSIONS.values() if entry["filter"]}

    assert narrowed | {"state"} <= set(declaration["facets"])


def test_the_state_name_matches_the_layer_panel_convention(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The map renamed every well row to `Noun (Full state name)`; the name is served so the
    two surfaces cannot drift into two spellings of one state."""
    _seed_tx(seeded)

    assert _facets(client)["data"]["state_name"] == "Texas"


# --- the scope is a set -------------------------------------------------------

_ND_OPERATOR = "A ND OPERATOR"
_MT_WELLS = 3


def _seed_nd(connection: psycopg.Connection) -> str:
    """North Dakota under a derivation of its own, so a combined bucket has two to reach."""
    derivation = seed_derivation(
        connection, params={"source_key": "nd.xlsx", "liquids_basis": "oil+condensate"}
    )
    for serial in range(1, 4):
        seed_well(
            connection,
            api10=f"33{serial:08d}",
            state_code="33",
            county_code_at_permit="053",
            operator_name_reported=_ND_OPERATOR,
            derivation_id=derivation,
        )
    connection.commit()
    return derivation


def _seed_mt(connection: psycopg.Connection) -> None:
    """Montana with no operator on any well.

    A seeded shape, not an observed one: the deployed Montana carries 3,257 distinct operators
    over all 40,626 of its wells, and on the deployed spine no (jurisdiction, dimension) pair is
    `absent_by_rule` at all. What is real is the registered decision: `cr_mt_operator_absence_1`
    exists and says what a blank Montana operator means. What is seeded is a population carrying
    nothing but blanks, so the arm that reads the two together has something to read.
    `test_the_absent_by_rule_arm_reads_the_registry_and_not_a_jurisdiction` is the same mechanism
    over a planted rule of the suite's own, with no real regulator named at all.
    """
    for serial in range(1, _MT_WELLS + 1):
        seed_well(
            connection,
            api10=f"25{serial:08d}",
            state_code="25",
            county_code_at_permit="019",
            operator_name_reported=None,
            basin=None,
        )
    connection.commit()


def test_a_repeated_state_and_a_comma_list_ask_the_same_question(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """One grammar, two spellings. A reader who types one and a link that carries the other
    must land on the same population, or the panel and its own URL disagree."""
    _seed_tx(seeded)
    _seed_nd(seeded)
    repeated = client.get(
        "/v1/wells/facets?state=42&state=33&by=operator&top=50"
    ).json()["data"]
    listed = client.get("/v1/wells/facets?state=33,42&by=operator&top=50").json()["data"]

    assert repeated["state"] == listed["state"] == "33,42"
    assert repeated["caption"] == listed["caption"]
    assert [bucket["value"] for bucket in repeated["buckets"]] == [
        bucket["value"] for bucket in listed["buckets"]
    ]
    assert int(repeated["wells"]["value"]) == int(listed["wells"]["value"])


def test_all_is_every_registered_jurisdiction_the_spine_carries(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """Read from the registry at request time, which is what lets a fifth state join the
    answer without a client, a query string or a line of this module changing."""
    _seed_tx(seeded)
    _seed_nd(seeded)
    _seed_mt(seeded)
    data = client.get("/v1/wells/facets?state=all&by=operator&top=50").json()["data"]

    loaded = sorted(row["code"] for row in data["states"] if row["loaded"])
    assert data["state"] == "all"
    assert [row["code"] for row in data["jurisdictions"]] == loaded
    assert int(data["wells"]["value"]) == sum(
        int(row["wells"]["value"]) for row in data["jurisdictions"]
    )


def test_all_cannot_be_combined_with_a_code(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """One of the two would be ignored and the response could not say which."""
    _seed_tx(seeded)
    response = client.get("/v1/wells/facets?state=all&state=42&by=operator")

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "state_set_mixed"


def test_a_code_no_jurisdiction_is_registered_under_is_refused_by_name(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """A code the registry does not carry names no jurisdiction at all, which is a different
    refusal from a registered state whose ingest has not run — and the reader needs to know
    which, because only one of them is waiting on a load."""
    _seed_tx(seeded)
    response = client.get("/v1/wells/facets", params={"state": "99", "by": "operator"})

    assert response.status_code == 422
    body = response.json()
    assert body["errors"][0]["code"] == "state_not_registered"
    assert "Texas" in body["detail"]
    assert {row["code"] for row in body["states"]}


def test_the_jurisdictions_say_which_of_them_carries_the_dimension(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """R8 at the (jurisdiction, dimension) grain, over the seeded population `_seed_mt` lays
    down: given a jurisdiction that contributes no value and a registered decision about that
    absence, the wells leave the shared `not reported` bucket. Folded into it they would read as
    the same absence Texas's blanks are, and they are not the same fact. The registered decision
    is real; the population is the fixture's, and the deployed Montana is not in it."""
    _seed_tx(seeded)
    _seed_nd(seeded)
    _seed_mt(seeded)
    data = client.get("/v1/wells/facets?state=all&by=operator&top=50").json()["data"]
    by_code = {row["code"]: row for row in data["jurisdictions"]}

    assert by_code["25"]["dimension"] == "absent_by_rule"
    assert by_code["25"]["rule_id"] == "cr_mt_operator_absence_1"
    assert int(by_code["25"]["wells"]["value"]) == _MT_WELLS
    assert by_code["33"]["dimension"] == "carried"
    assert by_code["42"]["dimension"] == "carried"
    assert by_code["42"]["rule_id"] == "cr_tx_operator_absence_1"
    assert "cr_mt_operator_absence_1" in data["rules"]


def test_a_jurisdiction_absent_by_rule_is_outside_the_not_reported_bucket(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The reconciliation the whole surface rests on, restated for a set: everything is still
    counted, and the wells whose absence a rule explains are counted where the rule is."""
    _seed_tx(seeded)
    _seed_nd(seeded)
    _seed_mt(seeded)
    data = client.get("/v1/wells/facets?state=all&by=operator&top=50").json()["data"]

    listed = sum(int(bucket["wells"]["value"]) for bucket in data["buckets"])
    absent = int(data["absence"]["wells"]["value"])
    by_rule = sum(
        int(row["wells"]["value"])
        for row in data["jurisdictions"]
        if row["dimension"] == "absent_by_rule"
    )

    assert absent == _TX_ABSENT
    assert by_rule == _MT_WELLS
    assert listed + absent + by_rule == int(data["wells"]["value"])
    warned = _facets(client, state="all", top=50)["meta"]["warnings"]
    codes = {warning["code"] for warning in warned}
    assert "dimension_absent_by_rule" in codes


def test_a_combined_bucket_reaches_every_promotion_behind_it(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """A number over two jurisdictions whose lineage reaches one of them is a number nobody
    can audit: the half it does not name is invisible and still inside the count."""
    _seed_tx(seeded)
    nd_derivation = _seed_nd(seeded)
    tx_derivation = seeded.execute(
        "select max(derivation_id) from canonical.wells where state_code = '42'"
    ).fetchone()[0]
    handle = client.get(
        "/v1/wells/facets?state=33,42&by=operator&top=50"
    ).json()["data"]["wells"]["d"]

    seeded.rollback()
    response_derivation = parse_handle(handle).derivation_id
    reached = {
        row[0]
        for row in seeded.execute(
            "select ref_id from lineage.derivation_inputs where derivation_id = %s",
            (response_derivation,),
        ).fetchall()
    }

    assert {nd_derivation, tx_derivation} <= reached
    resolved = client.get("/v1/explain", params={"h": handle})
    assert resolved.status_code == 200, resolved.text


def test_a_bucket_link_narrows_the_collection_to_exactly_the_set_it_was_counted_over(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The link is the control. Counted over two jurisdictions and narrowing to one, it hands
    the reader a shorter list than the number they pressed."""
    _seed_tx(seeded)
    _seed_nd(seeded)
    bucket = next(
        row
        for row in client.get(
            "/v1/wells/facets?state=33,42&by=county&top=50"
        ).json()["data"]["buckets"]
        if row["value"] == "003"
    )

    assert bucket["links"]["wells"] == "/v1/wells?county=003&state=33%2C42"
    followed = client.get(f"{bucket['links']['wells']}&limit=200")
    assert followed.status_code == 200, followed.text
    assert len(followed.json()["data"]) == int(bucket["wells"]["value"])


def test_a_set_names_itself_in_the_served_prose(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The panel says the population in the server's words, so two surfaces cannot spell one
    set two ways — and a set of one reads exactly as it always did."""
    _seed_tx(seeded)
    _seed_nd(seeded)
    combined = client.get("/v1/wells/facets?state=33,42&by=operator&top=50").json()["data"]

    assert combined["state_name"] == "North Dakota and Texas"
    assert "North Dakota and Texas" in combined["caption"]
    assert _facets(client)["data"]["state_name"] == "Texas"


def test_a_response_carrying_more_handles_than_explain_inlines_says_so(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """`all` over four jurisdictions puts the per-jurisdiction figures on top of the ranking,
    which is exactly where /v1/explain's own cap of twenty starts to bite. The truncation is
    served rather than left for a reader to notice that a handle has no chain."""
    _seed_tx(seeded)
    _seed_nd(seeded)
    _seed_mt(seeded)
    for serial in range(100, 120):
        seed_well(
            seeded,
            api10=f"42{serial:08d}",
            state_code="42",
            operator_name_reported=f"OPERATOR {serial}",
        )
    seeded.commit()
    body = client.get("/v1/wells/facets?state=all&by=operator&top=50&explain=true").json()

    codes = {warning["code"] for warning in body["meta"]["warnings"]}
    assert "explain_inline_truncated" in codes
    assert len(body["_explain"]) == 20



# The rule id and its evidence tag are the suite's, not a regulator's: `seed_conformance_rule`
# registers `harness-fixture` publication evidence, and nothing about this row is a claim that
# any real jurisdiction reports nothing. It exists so the `absent_by_rule` arm is exercised by a
# decision the fixture owns end to end — on the deployed spine no (jurisdiction, dimension) pair
# is absent by rule, and the gate report's H-1 is why no row was appended to make one.
FIXTURE_ABSENCE_RULE = "cr_fixture_well_type_absence_1"


def _plant_an_absence_rule(
    connection: psycopg.Connection, *, jurisdiction: str, dimension: str
) -> None:
    """A registered absence decision of the suite's own, at the resolving registration's triple."""
    seed_conformance_rule(
        connection,
        rule_id=FIXTURE_ABSENCE_RULE,
        source_id="nd_mpr_xlsx",
        rationale="Planted by the suite so the absent-by-rule arm has a decision to read.",
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.jurisdiction_rules (jurisdiction_code, effective_from,"
            " published_at, decision, rule_id, serving, note)"
            " select j.jurisdiction_code, j.effective_from, j.published_at, %s, %s, true,"
            " 'Planted by the suite.'"
            "   from lineage.jurisdictions_as_of(current_date, current_date) j"
            "  where j.jurisdiction_code = %s"
            " on conflict do nothing",
            (f"absence:{dimension}", FIXTURE_ABSENCE_RULE, jurisdiction),
        )
    connection.commit()


def test_the_absent_by_rule_arm_reads_the_registry_and_not_a_jurisdiction(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The mechanism, over a decision the fixture owns: no real regulator is named.

    Montana here files no well type on any of its wells and a registered rule says what that
    means, so its wells leave the shared bucket and are counted against the rule instead. The
    arm is registry-driven — it fires for whatever `absence:<dimension>` row resolves, which is
    the property worth testing, and not for the two `absence:operator` rows that happen to exist.
    """
    _seed_tx(seeded)
    for serial in range(1, 4):
        seed_well(
            seeded,
            api10=f"25{serial:08d}",
            state_code="25",
            well_type_reported=None,
            basin=None,
        )
    seeded.commit()
    _plant_an_absence_rule(seeded, jurisdiction="MT", dimension="well_type")
    data = client.get("/v1/wells/facets?state=25,42&by=well_type&top=50").json()["data"]
    by_code = {row["code"]: row for row in data["jurisdictions"]}

    assert by_code["25"]["dimension"] == "absent_by_rule"
    assert by_code["25"]["rule_id"] == FIXTURE_ABSENCE_RULE
    assert by_code["42"]["dimension"] == "carried"
    listed = sum(int(bucket["wells"]["value"]) for bucket in data["buckets"])
    absent = int(data["absence"]["wells"]["value"]) if data["absence"] else 0
    assert listed + absent + int(by_code["25"]["wells"]["value"]) == int(data["wells"]["value"])


def test_the_arm_stays_shut_where_the_registry_holds_no_decision(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The other half, and the one the deployed data is in: a jurisdiction that reports nothing
    with no rule to explain it stays in the shared bucket, which then cites none and says so."""
    _seed_tx(seeded)
    for serial in range(1, 4):
        seed_well(
            seeded,
            api10=f"25{serial:08d}",
            state_code="25",
            well_type_reported=None,
            basin=None,
        )
    seeded.commit()
    body = client.get("/v1/wells/facets?state=25,42&by=well_type&top=50").json()
    by_code = {row["code"]: row for row in body["data"]["jurisdictions"]}

    assert by_code["25"]["dimension"] == "absent_unregistered"
    assert by_code["25"]["rule_id"] is None
    assert body["data"]["absence"]["rule_id"] is None
    assert "absence_unregistered" in {w["code"] for w in body["meta"]["warnings"]}


def test_a_jurisdiction_with_no_wells_at_the_asked_vintage_is_not_blamed_on_a_rule(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The knowledge-time arm, which this surface had no test for at all.

    `all` resolves against what the spine carries *today*; the counts are taken as of the date
    asked for. A jurisdiction promoted after that date is therefore in the set and contributes
    nothing — and a jurisdiction that contributes nothing has exercised no absence rule. Read as
    `absent_by_rule` it would say a conformance decision explains an emptiness whose real cause
    is the reader's own `as_of`, which is a claim with no row behind it.
    """
    _seed_tx(seeded)
    for serial in range(1, 4):
        seed_well(
            seeded,
            api10=f"25{serial:08d}",
            state_code="25",
            effective_from=date(2026, 9, 1),
            operator_name_reported=None,
            basin=None,
        )
    seeded.commit()
    body = client.get(
        "/v1/wells/facets?state=all&by=operator&top=50&as_of=2026-08-15"
    ).json()
    by_code = {row["code"]: row for row in body["data"]["jurisdictions"]}

    assert by_code["25"]["dimension"] == "no_wells_in_scope"
    assert by_code["25"]["rule_id"] == "cr_mt_operator_absence_1"
    assert by_code["25"]["wells"] is None
    assert by_code["42"]["dimension"] == "carried"
    assert "dimension_absent_by_rule" not in {w["code"] for w in body["meta"]["warnings"]}


def test_the_same_jurisdiction_is_absent_by_rule_once_its_wells_are_in_scope(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The other side of the same seed: at `latest` the wells are there and the rule applies."""
    _seed_tx(seeded)
    _seed_mt(seeded)
    body = client.get("/v1/wells/facets?state=all&by=operator&top=50").json()
    by_code = {row["code"]: row for row in body["data"]["jurisdictions"]}

    assert by_code["25"]["dimension"] == "absent_by_rule"
    assert "dimension_absent_by_rule" in {w["code"] for w in body["meta"]["warnings"]}


def test_the_server_and_the_panel_say_the_scope_the_same_way(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """One vocabulary, or two sentences describe the same set differently 40 px apart.

    `_caption`'s own comment states the standard; the panel says `across` for a set, and the
    caption two lines above it said `in`. The preposition is the server's to choose, because the
    server is the one that knows how many jurisdictions are in the scope.
    """
    _seed_tx(seeded)
    _seed_nd(seeded)
    combined = client.get("/v1/wells/facets?state=33,42&by=operator&top=50").json()["data"]
    one = _facets(client, top=50)["data"]

    assert "across North Dakota and Texas" in combined["caption"]
    assert " in North Dakota and Texas" not in combined["caption"]
    assert "in Texas" in one["caption"]


def test_the_absence_sentence_uses_the_same_preposition_under_a_search(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The `q` arm names the population the count belongs to, and names it the same way."""
    _seed_tx(seeded)
    _seed_nd(seeded)
    data = client.get(
        "/v1/wells/facets?state=33,42&by=operator&top=50&q=usa"
    ).json()["data"]

    assert "across North Dakota and Texas" in data["absence"]["detail"]
