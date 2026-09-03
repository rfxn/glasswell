"""The status history: over the filed code, and only where the date beside it is the
regulator's own.

Two controls, both DR-A7's: a Colorado well, whose header clock is Stat_Date and whose class
resolves at read time, and the North Dakota well `3305300001`, whose clock is the vintage of
the workbook it was promoted from. The first has a history; the second has a current status
and a sentence saying why there is nothing behind it.
"""

from __future__ import annotations

from datetime import date

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.seed.conformance_status_history import HISTORY_RULE_ID, LOAD_STAMP, SOURCE_VALID_TIME
from tests.contract.conftest import OTHER_API10S
from tests.support.seed import seed_well

pytestmark = pytest.mark.contract

# The two api10s DR-A7 names. The Colorado one is measured on the deployed instance as carrying
# no status chip at all before this track; the North Dakota one is measured there as
# status_reported PA, status_canonical plugged, and is seeded to match.
CO_CONTROL = "0512324638"
ND_CONTROL = OTHER_API10S[0]

# Two codes lineage.co_facility_status_map carries, so the class column has something to
# resolve rather than a null that would pass a weaker assertion.
CO_FIRST = ("PR", date(2019, 4, 2))
CO_LATER = ("SI", date(2024, 11, 18))


def colorado_registered(connection: psycopg.Connection) -> bool:
    """NIT-11: the control skips on the registry, never on the tree's age. A Colorado row in
    lineage.jurisdictions is the whole condition, and on this base there is one."""
    with connection.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.jurisdictions where jurisdiction_code = 'CO'"
        )
        return int(cursor.fetchone()[0]) > 0


@pytest.fixture
def controls(client: TestClient, seeded: psycopg.Connection) -> psycopg.Connection:
    """The two controls, seeded on top of the contract fixture."""
    if colorado_registered(seeded):
        for status, effective in (CO_FIRST, CO_LATER):
            seed_well(
                seeded,
                api10=CO_CONTROL,
                effective_from=effective,
                state_code="05",
                county_code_at_permit="123",
                ndic_file_no=None,
                basin=None,
                land_unit_label=None,
                well_name="ECMC CONTROL 1",
                status_reported=status,
                # Null exactly as the Colorado promote writes it: the class is a read-time join
                # through the one shared resolver, which is why it can be labelled honestly.
                status_canonical=None,
            )
    # The North Dakota control gains a later header, the way a second workbook vintage would.
    # canonical.wells is append-only and wells_latest takes the newest effective row.
    seed_well(
        seeded,
        api10=ND_CONTROL,
        effective_from=date(2026, 8, 26),
        well_name="CONTRACT 1H",
        status_reported="PA",
        status_canonical="plugged",
    )
    seeded.commit()
    return seeded


def test_a_load_stamp_jurisdiction_is_offered_no_history_link(
    client: TestClient, controls: psycopg.Connection
) -> None:
    body = client.get(f"/v1/wells/{ND_CONTROL}").json()

    assert "history" not in body["links"]
    assert "history_rule" not in body["links"]
    # And the absence is stated by the jurisdiction's own vocabulary rule, which is served.
    assert body["links"]["status_rule"].startswith("/v1/conformance/")


def test_it_answers_a_load_stamp_jurisdiction_rather_than_refusing_it(
    client: TestClient, controls: psycopg.Connection
) -> None:
    """An empty list on its own cannot tell "this well never changed" from "nobody captured
    a history here", which is exactly the pair the rule exists to separate."""
    body = client.get(f"/v1/wells/{ND_CONTROL}/history").json()
    basis = body["data"]["basis"]

    assert body["data"]["history"] == []
    assert basis["clock"] == LOAD_STAMP
    assert basis["served"] is False
    assert basis["rule_id"] is None
    assert basis["status_vocabulary_rule"]
    assert "pulled" in basis["detail"]
    assert body["data"]["cap"]["total"] == 0


def test_dr_a7_the_filed_code_and_its_class_are_both_served(
    client: TestClient, controls: psycopg.Connection
) -> None:
    """The chip is built from what the response carries. Measured on the deployed instance,
    3305300001 is PA / plugged; 68,186 Texas wells resolve to no class at all and must still
    show the code the regulator filed."""
    body = client.get(f"/v1/wells/{ND_CONTROL}").json()["data"]

    assert body["status_reported"] == "PA"
    assert body["status_canonical"] == "plugged"
    assert body["status_vocabulary_rule"]
    assert body["regulator_name"]
    assert body["jurisdiction_name"]


def test_a_well_whose_class_resolves_nowhere_still_names_its_regulator(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The Texas arm of DR-A7. Measured on the deployed instance: 68,186 Texas wells serve a
    null class, because every canonical.status_resolution row is another jurisdiction's. The
    filed code and the regulator must reach the card anyway -- a well with neither shows no
    status at all, not even what the regulator wrote down."""
    from tests.contract.conftest import TX_API10

    unresolved = f"{TX_API10[:2]}00399997"
    seed_well(
        seeded,
        api10=unresolved,
        state_code=TX_API10[:2],
        county_code_at_permit="003",
        ndic_file_no=None,
        basin="permian",
        land_unit_label=None,
        well_name="UNRESOLVED 1",
        status_reported="AC",
        status_canonical=None,
    )
    seeded.commit()

    body = client.get(f"/v1/wells/{unresolved}").json()["data"]

    assert body["status_canonical"] is None
    assert body["status_reported"] == "AC"
    assert body["regulator_name"]
    assert body["regulator_url"]
    assert body["status_vocabulary_rule"]
    # And the registry gap is a fact the card states rather than another state's rule to wear.
    assert body["geometry_provenance_rule"] is None


def test_the_history_is_over_the_filed_code_and_not_over_the_canonical_class(
    client: TestClient, controls: psycopg.Connection
) -> None:
    if not colorado_registered(controls):
        pytest.skip("no Colorado registration in lineage.jurisdictions on this base")
    body = client.get(f"/v1/wells/{CO_CONTROL}/history").json()["data"]

    codes = [row["status_reported"] for row in body["history"]]
    # Newest first, and both filed codes present: this is the axis. Every row's promoted
    # status_canonical is null, so a history over the canonical class would be empty here.
    assert codes == [CO_LATER[0], CO_FIRST[0]]
    assert [row["effective_from"] for row in body["history"]] == [
        CO_LATER[1].isoformat(),
        CO_FIRST[1].isoformat(),
    ]
    assert body["basis"]["clock"] == SOURCE_VALID_TIME
    assert body["basis"]["served"] is True
    assert body["basis"]["rule_id"] == HISTORY_RULE_ID


def test_the_class_column_says_it_is_todays_mapping_and_names_the_rule_per_row(
    client: TestClient, controls: psycopg.Connection
) -> None:
    if not colorado_registered(controls):
        pytest.skip("no Colorado registration in lineage.jurisdictions on this base")
    body = client.get(f"/v1/wells/{CO_CONTROL}/history").json()["data"]

    assert body["basis"]["class_column_label"] == "class as glasswell maps this code today"
    assert body["basis"]["class_column_is_historical"] is False
    # Resolved through the one shared resolver, so the history, the card and the tile cannot
    # answer differently about the same code.
    assert [row["status_canonical"] for row in body["history"]] == ["inactive", "active"]
    for row in body["history"]:
        assert row["status_rule_id"], row


def test_the_well_record_offers_the_history_only_where_there_is_one(
    client: TestClient, controls: psycopg.Connection
) -> None:
    if not colorado_registered(controls):
        pytest.skip("no Colorado registration in lineage.jurisdictions on this base")
    body = client.get(f"/v1/wells/{CO_CONTROL}").json()

    assert body["links"]["history"] == f"/v1/wells/{CO_CONTROL}/history"
    assert body["links"]["history_rule"] == f"/v1/conformance/{HISTORY_RULE_ID}"
    # DR-A7 for a jurisdiction whose promotion writes no class at all: the code is served and
    # the class resolves at read time, so the chip has both.
    assert body["data"]["status_reported"] == CO_LATER[0]
    assert body["data"]["status_canonical"] == "inactive"


def test_the_cap_says_what_it_held_back(
    client: TestClient, controls: psycopg.Connection
) -> None:
    if not colorado_registered(controls):
        pytest.skip("no Colorado registration in lineage.jurisdictions on this base")
    for offset in range(12):
        seed_well(
            controls,
            api10=CO_CONTROL,
            effective_from=date(2020, 1, 1) + __import__("datetime").timedelta(days=offset),
            state_code="05",
            county_code_at_permit="123",
            ndic_file_no=None,
            basin=None,
            land_unit_label=None,
            status_reported="TA",
            status_canonical=None,
        )
    controls.commit()

    body = client.get(f"/v1/wells/{CO_CONTROL}/history").json()["data"]

    assert len(body["history"]) == 10
    assert body["cap"] == {"limit": 10, "returned": 10, "total": 14, "withheld": 4}


def test_the_rule_is_resolvable_at_the_conformance_surface(
    client: TestClient, controls: psycopg.Connection
) -> None:
    rule = client.get(f"/v1/conformance/{HISTORY_RULE_ID}").json()["data"]

    assert rule["rule_id"] == HISTORY_RULE_ID
    assert "31,707" in rule["rationale"]
    assert rule["spec"]["axis"] == "status_reported"
    assert rule["spec"]["registers_for"] == ["NM", "CO"]
