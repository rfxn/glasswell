"""The identity tie-break: a filed plugging date is the plugged fact, and outranks the schedule.

`cr_tx_plugged_precedence_1` says a wellbore with a plugging date on file is plugged whatever its
type says, but `cr_tx_identity_collapse_1` chooses which of an API-10's export records becomes
the identity row before the precedence rule ever reads it. With `on_schedule` first in the
preference order the plugging record loses to a sibling that carries no date, and the well is
painted from that sibling's type: 2,157 wells drawn active, service, inactive or temporarily
abandoned against a plugging date the RRC's own export carries for them (gate-tx-qa re-gate, D3).

The fixture is the four records the 2026-08-20 export carries for API-10 4200300446, verbatim:
one on-schedule producer completed 1990-03-06 with no plugging date, and three siblings the RRC
plugged on 1986-07-15.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import psycopg
import pytest

from glasswell.ingest import tx_wellbore
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.seed import seed_all

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
EWA_CSV = FIXTURES / "tx_ewa" / "OG_WELLBORE_EWA_plugged_sibling.csv"
PINNED_API10 = "4200300446"
FILED_PLUG_DATE = "19860715"
SCHEDULE_ONLY_TYPE = "PRODUCING"


def client_for(payload: Path) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if "OG_WELLBORE" in str(request.url):
            return httpx.Response(200, content=payload.read_bytes())
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def rows(db, sql: str, parameters: tuple = ()) -> list[tuple]:
    with db.cursor() as cursor:
        cursor.execute(sql, parameters)
        return cursor.fetchall()


@pytest.fixture
def seeded(db: psycopg.Connection) -> psycopg.Connection:
    seed_all(db)
    db.commit()
    return db


@pytest.fixture
def promoted(seeded, raw_root: Path, lineage_env):
    with lineage_session(
        recorder=PostgresRecorder(seeded), environment=lineage_env
    ), client_for(EWA_CSV) as client:
        result = tx_wellbore.load(seeded, raw_root=raw_root, client=client)
    seeded.commit()
    return result


def test_a_filed_plugging_date_beats_an_on_schedule_sibling_that_has_none(promoted, seeded):
    assert rows(
        seeded,
        "select status_canonical, status_reported, completion_date from canonical.wells"
        " where api10 = %s",
        (PINNED_API10,),
    ) == [("plugged", None, None)], (
        "the RRC plugged 4200300446 on 1986-07-15 and publishes the date in the same file the"
        " product cites; painting it from the on-schedule sibling's type says the opposite"
    )


def test_the_record_that_loses_is_the_one_carrying_no_plugging_date(promoted, seeded):
    quarantined = rows(
        seeded,
        "select row_payload ->> 'well_type_name', row_payload ->> 'plug_date',"
        "       row_payload ->> 'on_schedule'"
        "  from lineage.quarantine_rows"
        " where reason_code = 'multi_completion' and rule_id = 'cr_tx_identity_collapse_1'"
        "   and row_payload ->> 'api10' = %s",
        (PINNED_API10,),
    )

    assert (SCHEDULE_ONLY_TYPE, "", "Y") in quarantined, (
        "the record that loses must be in the ledger with the fields that decided it"
    )
    assert sum(1 for _, plug, _ in quarantined if plug == FILED_PLUG_DATE) == 2, (
        "three records carry the plugging date and one of them is promoted, so two are here"
    )


def test_the_served_rule_states_the_order_that_produced_the_promotion(promoted, seeded):
    """R8: `/v1/conformance` serves the order, so a reader can check the verdict against it."""
    assert rows(
        seeded,
        "select spec -> 'prefer' from lineage.conformance_rules"
        " where rule_id = 'cr_tx_identity_collapse_1'",
    ) == [(["plug_date", "on_schedule", "completion_date", "source_row_ordinal"],)]
