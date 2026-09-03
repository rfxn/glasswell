"""`GET /v1/jurisdictions`: the registry as a served collection.

Four registrations, every figure with a handle that resolves, and two clocks the caller can
move independently. The counts are deliberately partial — North Dakota and Texas measured, New
Mexico and Montana registered and not — because "not measured yet" and "zero wells" are
different facts and only one of them is true here.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

import glasswell.marts.counts as writer
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.status_classes import load_status_classes
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.counts import refresh_jurisdiction_counts
from glasswell.seed.jurisdictions import JURISDICTIONS, REGISTERED_ON, RESTATED_ON
from glasswell.status_resolution import UNMAPPED_CLASS
from tests.contract.conftest import JURISDICTION_MEASURED_ON, ND_MEASURED, TX_API10
from tests.support.fakes import FixedClock
from tests.support.jurisdictions import restate
from tests.support.seed import FIXTURE_ENV, seed_statusless_well

pytestmark = pytest.mark.contract

PATH = "/v1/jurisdictions"
STATUSLESS_API10 = f"{TX_API10[:2]}00399991"
REMEASURED_ON = JURISDICTION_MEASURED_ON + timedelta(days=1)


def remeasure(
    connection: psycopg.Connection, codes: Collection[str] | None = ("ND", "TX")
) -> str:
    """The count writer, run again the way the host runs it, on a later day."""
    with lineage_session(
        recorder=PostgresRecorder(connection),
        environment=FIXTURE_ENV,
        clock=FixedClock(datetime(2026, 8, 28, 6, 0, 0, tzinfo=UTC)),
        correlation_id="run_contract_recount",
    ):
        refresh = refresh_jurisdiction_counts(
            connection, measured_on=REMEASURED_ON, codes=codes
        )
    connection.commit()
    return refresh.derivation_id


def sum_identity(rows: list[dict[str, Any]]) -> tuple[int, list[str]]:
    """Jurisdictions whose parts were compared with their whole, and where the two disagree.

    The count is returned rather than left implicit because every arm of the comparison is
    inside a branch an unmeasured jurisdiction skips: a registry that served no counts at all
    would otherwise satisfy this silently, which is the one answer it must not be able to give.
    """
    checked = 0
    broken = []
    for row in rows:
        code = row["jurisdiction_code"]
        if row["well_count"] is None:
            if row["well_counts_by_status"]:
                broken.append(f"{code} serves classes under no total")
            continue
        checked += 1
        classes = sum(int(item["wells"]["value"]) for item in row["well_counts_by_status"])
        if classes != int(row["well_count"]["value"]):
            broken.append(f"{code} classes sum to {classes}, total is {row['well_count']['value']}")
    return checked, broken


def body(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get(PATH, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def refused(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get(PATH, params=params)
    assert response.status_code >= 400, response.text
    return response.json()


@pytest.fixture(autouse=True)
def _uncached() -> None:
    from glasswell.lineage.jurisdictions import clear_jurisdiction_cache

    clear_jurisdiction_cache()


def test_it_serves_every_registration_as_a_bare_array_in_code_order(client: TestClient) -> None:
    envelope = body(client)
    data = envelope["data"]

    assert isinstance(data, list)
    assert [row["jurisdiction_code"] for row in data] == ["CO", "MT", "ND", "NM", "TX"]
    assert len(data) == len(JURISDICTIONS)
    assert envelope["links"]["self"] == PATH


def test_a_row_carries_the_regulator_the_identity_and_the_capabilities(
    client: TestClient,
) -> None:
    row = next(item for item in body(client)["data"] if item["jurisdiction_code"] == "ND")

    assert row["name"] == "North Dakota"
    assert row["level"] == "state"
    assert row["regulator"]["name"].startswith("ND Dept. of Mineral Resources")
    assert row["regulator"]["url"].startswith("https://")
    assert row["identity"] == {
        "scheme": "api10",
        "prefix": "33",
        "pattern": "^33[0-9]{8}$",
        "is_unique": True,
    }
    assert row["capabilities"] == {
        "neighbors": True,
        "land_grid_state": True,
        "land_grid_scope": True,
        # The v0.76 sentinel's P4-R5: the explorer opens on the registration whose production
        # history it can walk, which is a fact about the data and not a client preference.
        "explorer_default": True,
    }
    assert row["map"] == {
        "wells_tile_layer_id": "nd_wells",
        "colour": "#3FA55E",
        # 075's presentation columns, on the wire rather than only in the generated module, so
        # a subtitle or a note can change without a rebuild.
        "wells_layer_id": "wells",
        "wells_style_layer_ids": ["wells", "wells-struck"],
        "wells_draw_order": 40,
        "wells_default_on": True,
        "wells_snapshot_key": "nd_wells_refresh",
        "wells_subtitle_template": row["map"]["wells_subtitle_template"],
    }
    assert "{count}" in row["map"]["wells_subtitle_template"]
    assert row["liquids_basis"] == "oil+condensate"
    assert row["effective_from"] == REGISTERED_ON.isoformat()
    assert row["published_at"] == RESTATED_ON.isoformat()


def test_montanas_two_inventory_rules_are_both_visible_and_one_serves(
    client: TestClient,
) -> None:
    """An array of decisions rather than a column per decision is what makes this expressible:
    a scalar `inventory_rule_id` would have had to pick one and say nothing about the other."""
    row = next(item for item in body(client)["data"] if item["jurisdiction_code"] == "MT")
    inventory = [
        rule for rule in row["rules"] if rule["decision"] == "inventory_jurisdiction"
    ]

    assert sorted(rule["rule_id"] for rule in inventory) == [
        "cr_mt_inventory_jurisdiction_1",
        "cr_mt_pru_inventory_jurisdiction_1",
    ]
    assert [rule["serving"] for rule in sorted(inventory, key=lambda r: r["rule_id"])] == [
        True,
        False,
    ]
    assert next(rule for rule in inventory if not rule["serving"])["note"] == "PRU lease grain"


def test_texas_registers_no_geometry_provenance_decision_and_says_so_by_omission(
    client: TestClient,
) -> None:
    row = next(item for item in body(client)["data"] if item["jurisdiction_code"] == "TX")

    assert all(rule["decision"] != "geometry_provenance" for rule in row["rules"])
    assert row["liquids_basis"] is None


def test_every_rule_it_names_resolves_at_the_conformance_route(client: TestClient) -> None:
    """A registry that cites a rule nobody can read is a citation to nothing."""
    named = {rule["rule_id"] for row in body(client)["data"] for rule in row["rules"]}

    assert named
    for rule_id in sorted(named):
        assert client.get(f"/v1/conformance/{rule_id}").status_code == 200, rule_id


def test_a_measured_count_is_a_figure_with_a_handle_and_a_date(client: TestClient) -> None:
    row = next(item for item in body(client)["data"] if item["jurisdiction_code"] == "ND")

    assert row["measured_on"] == JURISDICTION_MEASURED_ON.isoformat()
    assert row["well_count"]["value"] == str(ND_MEASURED[None])
    assert row["well_count"]["unit"] == "wells"
    assert row["well_count"]["d"].endswith("#jurisdiction=ND")
    by_status = {item["status_canonical"]: item for item in row["well_counts_by_status"]}
    # Every registered class, at whatever this jurisdiction holds of it: a class no well
    # carries is measured at zero rather than left out, because absent and zero are different
    # facts and the client hides only one of them.
    assert set(by_status) > {"active", "plugged", "drilling", UNMAPPED_CLASS}
    assert by_status["active"]["wells"]["value"] == str(ND_MEASURED["active"])
    assert by_status["active"]["wells"]["d"].endswith("#jurisdiction=ND&status=active")
    assert by_status["drilling"]["wells"]["value"] == "0"
    assert by_status["drilling"]["wells"]["d"].endswith("#jurisdiction=ND&status=drilling")


def test_every_jurisdictions_classes_sum_to_the_total_they_are_served_beside(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """No naked numbers, in the direction that matters: the parts of a served figure resolve.

    A well whose regulator filed no status was inside the total and inside no class, so a
    reader who added up what was served got a different number from the one served beside it
    (68,186 wells in Texas on the deployed build).
    """
    seed_statusless_well(seeded, api10=STATUSLESS_API10, like=TX_API10)
    remeasure(seeded)

    checked, broken = sum_identity(body(client)["data"])

    assert broken == []
    assert checked >= 2, "no jurisdiction served a count, so this proves nothing"


def test_the_sum_identity_cannot_be_satisfied_by_a_registry_that_served_no_counts() -> None:
    """The vacuity the guard above refuses, made a case rather than left to be trusted: every
    comparison sits inside a branch an unmeasured jurisdiction skips, so a refresh that silently
    stopped writing would leave the check green over a registry serving nothing at all."""
    unmeasured = [
        {"jurisdiction_code": code, "well_count": None, "well_counts_by_status": []}
        for code in ("MT", "ND", "NM", "TX")
    ]

    assert sum_identity(unmeasured) == (0, [])
    assert sum_identity(
        [{"jurisdiction_code": "ND", "well_count": None, "well_counts_by_status": [1]}]
    ) == (0, ["ND serves classes under no total"])


def test_a_day_whose_rows_name_two_runs_is_served_whole_and_each_row_resolves(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The host's own re-measure, on the wire rather than only in the ledger.

    Run the writer on a day the ledger already holds and the per-row `on conflict do nothing`
    inserts the keys that day is missing and keeps every key it has, so the day's rows name two
    runs. That is exactly what the deployed ledger does the first time this train's writer meets
    a v0.76 day: the classes already on it stay under the run that wrote them and the ones that
    writer never measured arrive under the new one. Simulated by growing the vocabulary between
    the runs, which is the same fact one layer up.

    The population does not move between the two, so the identity has to survive the mixed day,
    and each row has to resolve to the run that measured it rather than to whichever ran last.
    """
    seed_statusless_well(seeded, api10=STATUSLESS_API10, like=TX_API10)
    domain = load_status_classes(seeded)
    # A class the fixture holds no well of, so the narrowed run leaves it out altogether.
    absent = next(
        row.status_canonical
        for row in domain
        if row.status_canonical not in {"active", "plugged", UNMAPPED_CLASS}
    )
    # Its own context: the fixtures that build this client hold patches of their own on the
    # test's `monkeypatch`, and undoing theirs to restore one of mine takes the session with it.
    with pytest.MonkeyPatch.context() as narrowed:
        narrowed.setattr(
            writer,
            "load_status_classes",
            lambda *_, **__: [row for row in domain if row.status_canonical != absent],
        )
        first = remeasure(seeded, codes=None)

    second = remeasure(seeded, codes=None)

    assert first != second
    with seeded.cursor() as cursor:
        cursor.execute(
            "select status_key, derivation_id from lineage.jurisdiction_well_counts"
            " where jurisdiction_code = 'TX' and measured_on = %s",
            (REMEASURED_ON,),
        )
        wrote = dict(cursor.fetchall())
    assert wrote[writer.TOTAL_STATUS_KEY] == first, "the total the first run wrote was rewritten"
    assert wrote[UNMAPPED_CLASS] == first
    assert wrote[absent] == second, "the class the day lacked did not land"

    served = body(client)["data"]
    row = next(item for item in served if item["jurisdiction_code"] == "TX")
    classes = {item["status_canonical"] for item in row["well_counts_by_status"]}
    assert classes == {row.status_canonical for row in domain}, "the day is served in halves"
    assert row["measured_on"] == REMEASURED_ON.isoformat()

    checked, broken = sum_identity(served)
    assert broken == []
    assert checked >= 2

    # One handle per figure and two runs behind it: the response's lineage names both, so a
    # reader who asks where the day came from is not shown one run as if it had measured all
    # of it. The served handle is the response's own (SB-07 §9.1) and the runs are its inputs.
    walked = client.get(
        "/v1/explain",
        params={
            "h": next(
                item["wells"]["d"]
                for item in row["well_counts_by_status"]
                if item["status_canonical"] == absent
            ),
            "depth": "full",
        },
    )
    assert walked.status_code == 200, walked.text
    nodes = {node["id"] for node in walked.json()["data"]["chains"][0]["nodes"]}
    assert {first, second} <= nodes, sorted(nodes)


def test_a_well_whose_source_filed_no_status_is_served_as_the_absence_class(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """`unmapped`, not `documented_unmapped`: the regulator published no code to map, which is
    an absence rather than a code glasswell has no word for. Both are served, and they are
    different facts."""
    seed_statusless_well(seeded, api10=STATUSLESS_API10, like=TX_API10)
    remeasure(seeded)

    row = next(item for item in body(client)["data"] if item["jurisdiction_code"] == "TX")
    classes = {item["status_canonical"]: item["wells"] for item in row["well_counts_by_status"]}

    assert classes[UNMAPPED_CLASS]["value"] == "1"
    assert classes[UNMAPPED_CLASS]["unit"] == "wells"
    assert classes[UNMAPPED_CLASS]["d"].endswith(f"#jurisdiction=TX&status={UNMAPPED_CLASS}")
    assert row["measured_on"] == REMEASURED_ON.isoformat()


def test_an_unmeasured_jurisdiction_serves_no_count_rather_than_a_zero(
    client: TestClient,
) -> None:
    """R-3. A zero here would say Montana holds no wells, which is a claim nothing measured."""
    row = next(item for item in body(client)["data"] if item["jurisdiction_code"] == "MT")

    assert row["well_count"] is None
    assert row["well_counts_by_status"] == []
    assert row["measured_on"] is None


def test_explain_resolves_a_count_to_the_manifest_the_file_arrived_in(
    client: TestClient,
) -> None:
    """No naked numbers, end to end: the count's handle walks to a government file."""
    envelope = body(client, explain="true", explain_depth=3)
    inlined = envelope["_explain"]

    row = next(item for item in envelope["data"] if item["jurisdiction_code"] == "ND")
    handle = row["well_count"]["d"]
    assert handle in inlined, envelope["meta"]["warnings"]
    chain = inlined[handle]
    assert chain["terminals"], chain
    assert all(terminal.startswith("man_") for terminal in chain["terminals"])
    assert chain["truncated"] is False

    # A figure per class per jurisdiction is more handles than `_explain` inlines -- SB-07
    # §9.4's cap of 20, not this operation's -- so the response says so rather than dropping
    # them quietly, and a handle it left out still resolves. That is what makes the cap a cap
    # and not a hole.
    assert [
        item["code"] for item in envelope["meta"]["warnings"] if item["code"].startswith("explain_")
    ] == ["explain_inline_truncated"]
    left_out = next(
        item["wells"]["d"]
        for jurisdiction in envelope["data"]
        for item in jurisdiction["well_counts_by_status"]
        if item["wells"]["d"] not in inlined
    )
    resolved = client.get("/v1/explain", params={"h": left_out, "depth": "full"})
    assert resolved.status_code == 200, resolved.text
    walked = resolved.json()["data"]["chains"][0]
    assert walked["handle"] == left_out
    assert all(terminal.startswith("man_") for terminal in walked["terminals"]), walked


def test_the_level_filter_narrows_to_the_registrations_at_that_level(
    client: TestClient,
) -> None:
    assert len(body(client, level="state")["data"]) == len(JURISDICTIONS)
    assert body(client, level="province")["data"] == []


def test_the_page_is_a_page_and_its_cursor_walks_the_rest(client: TestClient) -> None:
    first = body(client, limit=2)

    assert [row["jurisdiction_code"] for row in first["data"]] == ["CO", "MT"]
    assert first["meta"]["next_cursor"]
    second = body(client, limit=2, cursor=first["meta"]["next_cursor"])
    assert [row["jurisdiction_code"] for row in second["data"]] == ["ND", "NM"]
    assert second["meta"]["next_cursor"]
    third = body(client, limit=2, cursor=second["meta"]["next_cursor"])
    assert [row["jurisdiction_code"] for row in third["data"]] == ["TX"]
    assert third["meta"]["next_cursor"] is None


def test_a_registration_published_after_the_cut_is_not_served_under_it(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """B-6 on the wire. `as_of` is the knowledge cut, which is exactly what a static
    current-state view could not have honoured."""
    corrected = "https://www.dmr.nd.gov/oilgas/"
    restate(seeded, "ND", regulator_url=corrected)
    later = RESTATED_ON + timedelta(days=1)

    before = body(client, as_of=RESTATED_ON.isoformat())
    after = body(client, as_of=later.isoformat())

    assert next(r for r in before["data"] if r["jurisdiction_code"] == "ND")["regulator"][
        "url"
    ].endswith("mprindex.asp")
    restated = next(r for r in after["data"] if r["jurisdiction_code"] == "ND")
    assert restated["regulator"]["url"] == corrected
    assert restated["published_at"] == later.isoformat()
    assert restated["effective_from"] == REGISTERED_ON.isoformat()


def test_a_cut_before_the_first_registration_is_out_of_range_not_an_empty_page(
    client: TestClient,
) -> None:
    """An empty array would read as "glasswell serves no jurisdictions", which is false."""
    problem = refused(client, as_of=(REGISTERED_ON - timedelta(days=1)).isoformat())

    assert problem["status"] == 422
    assert problem["type"].endswith("as_of_out_of_range")


def test_a_cursor_minted_against_another_cut_is_refused(client: TestClient) -> None:
    minted = body(client, limit=2)["meta"]["next_cursor"]

    problem = refused(client, limit=2, cursor=minted, as_of=REGISTERED_ON.isoformat())

    assert problem["type"].endswith("cursor_query_mismatch")


def test_a_malformed_cursor_is_refused(client: TestClient) -> None:
    problem = refused(client, cursor="not-a-cursor")

    assert problem["type"].endswith("cursor_malformed")
