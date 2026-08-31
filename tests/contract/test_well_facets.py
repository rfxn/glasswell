"""`/v1/wells/facets`: counted buckets, what they exclude, and what has no value at all."""

from __future__ import annotations

from datetime import date

import psycopg
from fastapi.testclient import TestClient

from tests.support.seed import seed_well

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
    assert caption("value", "desc") == (
        "2 of 5 operator values in Texas, ranked by value, descending."
    )
    assert caption("value", "asc") == (
        "2 of 5 operator values in Texas, ranked by value, ascending."
    )
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
    assert caption("value", "asc") == (
        "All 5 operator values in Texas, ranked by value, ascending."
    )


def test_ranking_by_value_orders_by_the_value_and_not_the_count(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    _seed_tx(seeded)
    data = _facets(client, top=50, sort="value", order="asc")["data"]

    values = [bucket["value"] for bucket in data["buckets"]]
    assert values == sorted(values)


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


def test_the_state_name_matches_the_layer_panel_convention(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The map renamed every well row to `Noun (Full state name)`; the name is served so the
    two surfaces cannot drift into two spellings of one state."""
    _seed_tx(seeded)

    assert _facets(client)["data"]["state_name"] == "Texas"
