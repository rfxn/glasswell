"""What moves a served jurisdiction decision is a row, not a dict in a router.

Every assertion here changes the registry and reads the wire. Before this phase each of these
values came from a per-state map in `wells.py`, `facets.py` or `production.py`, so no row could
have moved one — which is precisely what R8 says must not be true of a mapping decision.

The append used is a restatement: the same `effective_from` with a later `published_at`. A
supersession would need a later valid time, and the founding registrations are dated today.
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10, EXAMPLE_BBOX
from glasswell.lineage.jurisdictions import clear_jurisdiction_cache
from glasswell.status_resolution import resolver_rules
from tests.contract.conftest import TX_API10
from tests.contract.test_well_facets import _seed_tx
from tests.support.jurisdictions import restate

pytestmark = pytest.mark.contract

# Real conformance rows, so the composite FK is satisfied and the move is a registry move
# rather than a broken reference. None of them is the rule the founding registration names.
ANOTHER_ND_VOCAB_RULE = "cr_nd_segment_vocab_1"
ANOTHER_ND_PROVENANCE_RULE = "cr_nd_datum_1"
A_LENGTH_SCOPE_RULE = "cr_nd_multilateral_1"
A_BLANK_IS_ABSENT_RULE = "cr_nd_units_1"
ANOTHER_TX_ABSENCE_RULE = "cr_tx_status_vocab_1"
BOTH_STATES_BOX = "-105,30,-100,50"


def body(client: TestClient, path: str, **params: Any) -> dict[str, Any]:
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(autouse=True)
def _uncached() -> None:
    clear_jurisdiction_cache()


def test_the_well_card_cites_the_rule_the_registry_names_today(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    before = body(client, f"/v1/wells/{EXAMPLE_API10}")["data"]
    assert before["status_vocabulary_rule"] == "cr_nd_status_vocab_1"

    restate(seeded, "ND", rules={"status_vocabulary": ANOTHER_ND_VOCAB_RULE})

    after = body(client, f"/v1/wells/{EXAMPLE_API10}")["data"]
    assert after["status_vocabulary_rule"] == ANOTHER_ND_VOCAB_RULE


def test_the_collection_row_cites_it_too(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """One registry, two surfaces: the list and the card cannot answer differently."""
    restate(seeded, "ND", rules={"status_vocabulary": ANOTHER_ND_VOCAB_RULE})

    listed = body(client, "/v1/wells", api10=EXAMPLE_API10)["data"]

    assert [row["status_vocabulary_rule"] for row in listed] == [ANOTHER_ND_VOCAB_RULE]


def test_the_card_and_the_collection_cite_the_rule_the_blank_read_applied(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """gate-cofix H-1, at the spine read. `_COLUMNS` applies absent_if_blank to every
    source-reported text column the card and the collection serve, so both name the decision
    that shaped what they served -- and neither names it before a jurisdiction registers one.
    """
    before = body(client, f"/v1/wells/{EXAMPLE_API10}")
    assert "absence_rule" not in before["links"]

    restate(seeded, "ND", rules={"blank_is_absent": A_BLANK_IS_ABSENT_RULE})

    card = body(client, f"/v1/wells/{EXAMPLE_API10}")
    listed = body(client, "/v1/wells", api10=EXAMPLE_API10)

    assert card["links"]["absence_rule"] == f"/v1/conformance/{A_BLANK_IS_ABSENT_RULE}"
    assert listed["links"][A_BLANK_IS_ABSENT_RULE] == (
        f"/v1/conformance/{A_BLANK_IS_ABSENT_RULE}"
    )


def test_the_status_summary_names_it_per_basin(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    restate(seeded, "ND", rules={"status_vocabulary": ANOTHER_ND_VOCAB_RULE})

    basins = body(client, "/v1/wells/status-summary", bbox=BOTH_STATES_BOX)["data"]["basins"]
    named = {row["state_code"]: row["status_vocabulary_rule"] for row in basins}

    assert named["33"] == ANOTHER_ND_VOCAB_RULE
    assert named["42"] == "cr_tx_status_vocab_1"


def test_a_jurisdiction_that_stops_registering_a_vocabulary_is_reported_as_unregistered(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The registry can say "no decision" as well as "this decision", and the response says so
    rather than leaving the count looking rule-backed."""
    restate(seeded, "ND", drop=["status_vocabulary"])

    data = body(client, "/v1/wells/status-summary", bbox=EXAMPLE_BBOX)["data"]

    assert "cr_nd_status_vocab_1" not in data["vocabulary_rules"]
    assert body(client, f"/v1/wells/{EXAMPLE_API10}")["data"]["status_vocabulary_rule"] is None


def test_the_geometry_provenance_rule_the_summary_links_is_a_registry_row(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    before = body(client, "/v1/wells/status-summary", bbox=EXAMPLE_BBOX)
    assert "cr_nd_geometry_provenance_1" in before["links"]

    restate(seeded, "ND", rules={"geometry_provenance": ANOTHER_ND_PROVENANCE_RULE})

    after = body(client, "/v1/wells/status-summary", bbox=EXAMPLE_BBOX)
    assert ANOTHER_ND_PROVENANCE_RULE in after["links"]
    assert "cr_nd_geometry_provenance_1" not in after["links"]


def test_texas_no_longer_inherits_north_dakotas_provenance_rule(client: TestClient) -> None:
    """The dict served TX `cr_nd_geometry_provenance_1` — a rule about North Dakota geometry —
    through a module-level default. Texas registers no such decision, so it cites none."""
    envelope = body(client, "/v1/wells/status-summary", bbox="-104,31,-101,34")

    assert body(client, f"/v1/wells/{TX_API10}")["data"]["state_code"] == "42"
    assert "cr_nd_geometry_provenance_1" not in envelope["links"]


def test_registering_a_length_scope_rule_withholds_the_length_and_links_the_reason(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """North Dakota registers no length_scope decision, so its length is served. Registering
    one has to withhold the figure and name the rule in its place — with no code change."""
    before = body(client, f"/v1/wells/{EXAMPLE_API10}")
    assert before["data"]["length_method"] == "geodesic"
    assert "length_rule" not in before["links"]

    restate(seeded, "ND", rules={"length_scope": A_LENGTH_SCOPE_RULE})

    after = body(client, f"/v1/wells/{EXAMPLE_API10}")
    assert after["data"]["length_method"] == "not_served"
    assert after["links"]["length_rule"] == f"/v1/conformance/{A_LENGTH_SCOPE_RULE}"


def test_the_neighbour_link_follows_the_capability_column(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    assert "neighbors" in body(client, f"/v1/wells/{EXAMPLE_API10}")["links"]

    restate(seeded, "ND", neighbors_available=False)

    assert "neighbors" not in body(client, f"/v1/wells/{EXAMPLE_API10}")["links"]


def test_the_liquids_basis_on_a_barrel_comes_from_the_registration(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The sidecar `lineage/envelope.py` makes mandatory on a liquids figure. Serving one
    state's policy on another state's barrel is the R8 failure it exists to prevent."""
    path = f"/v1/wells/{EXAMPLE_API10}/production"
    assert body(client, path)["data"]["_basis"]["series.oil_bbl"] == "oil+condensate"

    restate(seeded, "ND", liquids_basis="oil")

    after = body(client, path)["data"]
    assert after["_basis"]["series.oil_bbl"] == "oil"
    assert after["_basis"]["series.water_bbl"] == "water"


def test_the_facet_state_name_and_picker_come_from_the_registration(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    before = body(client, "/v1/wells/facets", state="42", by="operator")["data"]
    assert before["state_name"] == "Texas"

    restate(seeded, "TX", name="Texas (RRC)")

    after = body(client, "/v1/wells/facets", state="42", by="operator")["data"]
    assert after["state_name"] == "Texas (RRC)"
    assert {row["code"]: row["name"] for row in after["states"]}["42"] == "Texas (RRC)"
    assert sorted(row["code"] for row in after["states"]) == ["05", "25", "30", "33", "42"]


def test_the_absence_bucket_cites_the_rule_at_the_jurisdiction_and_dimension_grain(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """`absence:operator` is one decision at (jurisdiction, dimension) grain, so a second
    dimension is a row rather than another key in a tuple-keyed dict."""
    _seed_tx(seeded)
    before = body(client, "/v1/wells/facets", state="42", by="operator")["data"]
    assert before["absence"]["rule_id"] == "cr_tx_operator_absence_1"

    restate(seeded, "TX", rules={"absence:operator": ANOTHER_TX_ABSENCE_RULE})

    after = body(client, "/v1/wells/facets", state="42", by="operator")["data"]
    assert after["absence"]["rule_id"] == ANOTHER_TX_ABSENCE_RULE
    assert after["absence"]["links"]["rule"] == f"/v1/conformance/{ANOTHER_TX_ABSENCE_RULE}"


def test_an_unregistered_absence_dimension_claims_nothing_about_it(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    _seed_tx(seeded)
    restate(seeded, "TX", drop=["absence:operator"])

    envelope = body(client, "/v1/wells/facets", state="42", by="operator")
    absence = envelope["data"]["absence"]

    assert absence["rule_id"] is None
    assert absence["links"] == {}
    assert any(item["code"] == "absence_unregistered" for item in envelope["meta"]["warnings"])


def test_a_well_vintage_cut_does_not_narrow_the_registry(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """`as_of` on this route selects well vintages, not registrations. The rule beside a status
    is the rule that decided that class, so a retrospective read still cites it — and does not
    503 because the registry had published nothing on the day the well was filed."""
    envelope = body(client, "/v1/wells/status-summary", bbox=BOTH_STATES_BOX, as_of="2019-01-01")

    assert envelope["data"]["wells"] is None or envelope["data"]["basins"] == []
    assert body(client, f"/v1/wells/{EXAMPLE_API10}")["data"]["status_vocabulary_rule"] == (
        "cr_nd_status_vocab_1"
    )


def test_which_jurisdictions_resolve_at_read_time_is_a_registry_row(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """P5-R1. `RESOLVER_RULES = {"30": "cr_nm_wellhistory_status_vocab_2"}` was a dict in
    `status_resolution.py` — a jurisdiction keyed by API prefix, outside every tree the
    add-a-state scan looked at. It is a join now: the registered status-vocabulary rule, for
    every jurisdiction whose rule says in its own spec that it resolves at read time."""
    assert resolver_rules(seeded) == {
        "05": "cr_co_wells_status_vocab_1",
        "30": "cr_nm_wellhistory_status_vocab_2",
    }

    # A fifth jurisdiction registering the same read-time rule appears without an edit.
    with seeded.cursor() as cursor:
        cursor.execute("insert into lineage.jurisdiction_codes values ('WY', 'state')")
        cursor.execute(
            "insert into lineage.jurisdictions (jurisdiction_code, effective_from,"
            " published_at, evidence_tag, evidence_commit, name, regulator_name, regulator_url,"
            " identity_scheme, identity_prefix, identity_pattern, source_ids, rationale)"
            " select 'WY', effective_from, published_at, evidence_tag, evidence_commit,"
            " 'Wyoming', 'WOGCC', 'https://wogcc.wyo.gov', 'api10', '49', '^49[0-9]{8}$',"
            " array['nd_mpr_xlsx'], 'a fifth jurisdiction resolving at read time'"
            " from lineage.jurisdictions where jurisdiction_code = 'ND'"
        )
        cursor.execute(
            "insert into lineage.jurisdiction_rules (jurisdiction_code, effective_from,"
            " published_at, decision, rule_id)"
            " select 'WY', effective_from, published_at, 'status_vocabulary',"
            " 'cr_nm_wellhistory_status_vocab_2'"
            " from lineage.jurisdictions where jurisdiction_code = 'WY'"
        )
    clear_jurisdiction_cache()

    assert resolver_rules(seeded) == {
        "05": "cr_co_wells_status_vocab_1",
        "30": "cr_nm_wellhistory_status_vocab_2",
        "49": "cr_nm_wellhistory_status_vocab_2",
    }


def test_a_restatement_moves_which_rule_the_resolver_is_read_under(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The move-proof: a registry row change, and the resolver's answer follows it. New Mexico
    restated onto a rule that resolves at promotion time stops resolving at read time."""
    assert "30" in resolver_rules(seeded)

    restate(seeded, "NM", rules={"status_vocabulary": "cr_nm_wchistory_status_domain_1"})

    # Colorado is registered at read time too, so restating New Mexico leaves its arm
    # standing: the proof is that NM's entry goes, not that the resolver empties.
    assert resolver_rules(seeded) == {"05": "cr_co_wells_status_vocab_1"}
    assert body(client, f"/v1/wells/{EXAMPLE_API10}")["data"]["status_vocabulary_rule"] == (
        "cr_nd_status_vocab_1"
    )
