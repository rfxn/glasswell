"""F2: a value the parser could not read must be distinguishable from one the regulator
never filed.

`_date` returns None for anything that is not eight digits parsing as a calendar date, and
`_depth` returns None for anything `str.isdigit` rejects after one decimal point. Both fed
`canonical.wells` directly with no reject and no counter, so 131,252 live TX wells carry a
null completion date and 174,121 a null depth with nothing in the ledger saying which of
those are absences and which are failures. `_assert_layout` checks field count, the county
prefix and the oil-gas domain — a thousands separator in TOTAL_DEPTH or a switch to
MM/DD/YYYY passes it, and every TX well silently loses the field while the pipeline exits 0.

The fixture is four records of the 2026-08 export: one with an unreadable depth, one with an
unreadable date, one that filed neither, and one that filed both readably.
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
EWA_CSV = FIXTURES / "tx_ewa" / "OG_WELLBORE_EWA_unreadable_measures.csv"
UNREADABLE_DEPTH = "4200301007"
UNREADABLE_DATE = "4200301165"
FILED_NOTHING = "4200301691"
FILED_BOTH = "4200302197"


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


def withheld(db, api10: str) -> list[tuple]:
    return rows(
        db,
        "select reason_code, row_payload ->> 'field', row_payload ->> 'filed_as',"
        "       row_payload ->> 'field_action'"
        "  from lineage.quarantine_rows"
        " where source_id = 'tx_wellbore_ewa_csv' and row_payload ->> 'api10' = %s"
        "   and row_payload ? 'field'"
        " order by row_payload ->> 'field'",
        (api10,),
    )


def test_a_depth_the_parser_cannot_read_is_rejected_with_the_value_it_could_not_read(
    promoted, seeded
):
    assert withheld(seeded, UNREADABLE_DEPTH) == [
        ("unreliable_numeric", "total_depth_ft", "13,862", "null_field")
    ]


def test_a_date_the_parser_cannot_read_is_rejected_with_the_value_it_could_not_read(
    promoted, seeded
):
    assert withheld(seeded, UNREADABLE_DATE) == [
        ("out_of_range_date", "completion_date", "03/06/1990", "null_field")
    ]


def test_a_field_the_regulator_never_filed_is_not_a_reject(promoted, seeded):
    """The whole point of the distinction: an absence is not a failure, and quarantining it
    would drown the real ones — 36 % of live TX wells have no completion date on file."""
    assert withheld(seeded, FILED_NOTHING) == []
    assert rows(
        seeded,
        "select total_depth_ft, completion_date from canonical.wells where api10 = %s",
        (FILED_NOTHING,),
    ) == [(None, None)]


def test_a_readable_filing_is_promoted_and_not_rejected(promoted, seeded):
    """The floor: without this the rejects above could be produced by rejecting everything."""
    assert withheld(seeded, FILED_BOTH) == []
    assert rows(
        seeded,
        "select total_depth_ft is not null, completion_date is not null from canonical.wells"
        " where api10 = %s",
        (FILED_BOTH,),
    ) == [(True, True)]


def test_the_null_is_still_written_so_the_well_promotes(promoted, seeded):
    """Withholding a field is not dropping the well; the row lands with the field null."""
    assert rows(
        seeded,
        "select total_depth_ft, completion_date is not null from canonical.wells"
        " where api10 = %s",
        (UNREADABLE_DEPTH,),
    ) == [(None, True)]


def test_the_load_counts_what_it_withheld(promoted):
    """`WellboreLoad.quarantined` reported zeroes for this class, so a format change was
    invisible to every caller including the ingest run summary."""
    assert promoted.quarantined["unreliable_numeric"] == 1
    assert promoted.quarantined["out_of_range_date"] == 1


def test_every_withholding_cites_the_rule_that_decided_it(promoted, seeded):
    """R8: the policy is `cr_tx_ewa_measures_1`'s, so the reject names it and carries the
    stage the rule itself is filed under rather than a stage chosen at the call site."""
    assert rows(
        seeded,
        "select distinct rule_id, stage from lineage.quarantine_rows"
        " where source_id = 'tx_wellbore_ewa_csv' and row_payload ? 'field'",
    ) == [(tx_wellbore.MEASURES_RULE, "validate")]


def test_the_promotion_derivation_cites_the_withholding_rule(promoted, seeded):
    """Without this the withheld number can name a rule the derivation never applied."""
    assert rows(
        seeded,
        "select 1 from lineage.derivation_rules where derivation_id = %s and rule_id = %s",
        (promoted.identity_derivation_id, tx_wellbore.MEASURES_RULE),
    ) == [(1,)]
