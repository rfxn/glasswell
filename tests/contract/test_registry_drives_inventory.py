"""The Status page's jurisdiction arms are generated from the registry, not written per state.

Sixteen literals decided the wells arms and ten more the completions arms, so a fifth
jurisdiction meant editing this collector. It does not any more: the arms are a comprehension
over the resolved registrations, and an arm the tables hold nothing for says so rather than
publishing a zero that reads as "no wells".
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import UTC, date, datetime

import psycopg
import pytest

from glasswell.lineage.capture import lineage_session
from glasswell.lineage.jurisdictions import clear_jurisdiction_cache
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.counts import TOTAL_STATUS_KEY, refresh_jurisdiction_counts
from glasswell.seed.jurisdictions import CODES
from glasswell.status.collector import EMPTY_ARM, _inventory
from glasswell.status_resolution import UNMAPPED_CLASS, served_status_vocabulary
from tests.contract.conftest import TX_API10
from tests.support.fakes import FixedClock
from tests.support.jurisdictions import restate
from tests.support.seed import FIXTURE_ENV, seed_statusless_well

pytestmark = pytest.mark.contract

OBSERVED = datetime(2026, 8, 26, 18, tzinfo=UTC)
COLORADO_PREFIX = "05"


def counted(
    connection: psycopg.Connection, measured: date, codes: Collection[str] | None = None
):
    """The refresh, inside the lineage session every derivation is recorded in."""
    with lineage_session(
        recorder=PostgresRecorder(connection),
        environment=FIXTURE_ENV,
        clock=FixedClock(OBSERVED),
        correlation_id="run_contract_counts",
    ):
        return refresh_jurisdiction_counts(connection, measured_on=measured, codes=codes)


def ledger(connection: psycopg.Connection, measured: date) -> dict[tuple[str, str], tuple]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select jurisdiction_code, status_key, well_count, derivation_id"
            " from lineage.jurisdiction_well_counts where measured_on = %s",
            (measured,),
        )
        return {(code, key): (wells, derivation) for code, key, wells, derivation in cursor}


@pytest.fixture(autouse=True)
def _uncached() -> None:
    clear_jurisdiction_cache()


def inventory(connection: psycopg.Connection) -> dict[str, object]:
    datasets, _ = _inventory(connection, OBSERVED)
    return {item.dataset_id: item for item in datasets}


def register_colorado(connection: psycopg.Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("insert into lineage.jurisdiction_codes values ('CO', 'state')")
        cursor.execute(
            "insert into lineage.jurisdictions (jurisdiction_code, effective_from,"
            " published_at, evidence_tag, evidence_commit, name, regulator_name, regulator_url,"
            " identity_scheme, identity_prefix, identity_pattern, source_ids, rationale)"
            " select %s, effective_from, published_at, evidence_tag, evidence_commit,"
            " 'Colorado', 'COGCC', 'https://ecmc.state.co.us', 'api10', %s, %s,"
            " array['nd_mpr_xlsx'], 'a fifth jurisdiction, registered and not yet loaded'"
            " from lineage.jurisdictions where jurisdiction_code = 'ND'",
            ("CO", COLORADO_PREFIX, f"^{COLORADO_PREFIX}[0-9]{{8}}$"),
        )
    clear_jurisdiction_cache()


def test_a_fifth_jurisdiction_yields_a_fifth_dataset_with_no_edit(
    seeded: psycopg.Connection,
) -> None:
    """The exit criterion, stated as the thing that used to require a commit."""
    before = inventory(seeded)
    assert "canonical.wells_latest/co" not in before

    register_colorado(seeded)

    after = inventory(seeded)
    assert after["canonical.wells_latest/co"].label == "Current Colorado wells"
    assert after["canonical.wells_latest/co"].scope == "Colorado"
    assert "canonical.well_completions/co" in after
    assert len(after) == len(before) + 2


def test_an_arm_the_tables_hold_nothing_for_is_unavailable_and_not_a_zero(
    seeded: psycopg.Connection,
) -> None:
    """"Not loaded" and "none" are different facts. A zero here would say Colorado has no
    wells, which is a claim nothing measured — the same ruling as an absent `well_count`."""
    register_colorado(seeded)
    resident = inventory(seeded)

    empty = resident["canonical.wells_latest/co"]
    assert empty.state == EMPTY_ARM
    assert empty.metrics[0].value == 0
    assert empty.latest_knowledge_at is None
    assert resident["canonical.well_completions/co"].state == EMPTY_ARM

    loaded = resident["canonical.wells_latest/nd"]
    assert loaded.state == "available"
    assert loaded.metrics[0].value == 7


def test_the_scope_and_the_prose_a_jurisdiction_reads_as_are_registry_rows(
    seeded: psycopg.Connection,
) -> None:
    """`JURISDICTION_SCOPES` was a map from code to display name; the name is a column now, and
    the wells arm's caveat prose is `status_dataset_detail` rather than a literal block."""
    assert inventory(seeded)["canonical.wells_latest/mt"].detail.startswith("Headers only")

    restate(seeded, "ND", name="North Dakota (NDIC)", status_dataset_detail="Restated prose.")

    after = inventory(seeded)
    assert after["canonical.wells_latest/nd"].scope == "North Dakota (NDIC)"
    assert after["canonical.wells_latest/nd"].label == "Current North Dakota (NDIC) wells"
    assert after["canonical.wells_latest/nd"].detail == "Restated prose."
    assert after["canonical.well_completions/nd"].scope == "North Dakota (NDIC)"


def test_the_collector_reads_the_registry_as_the_api_role(seeded: psycopg.Connection) -> None:
    """The exit criterion, and the reason 044 exists: a grant missed once is a surface that
    works for the owner and 500s for the service that actually runs it."""
    with seeded.cursor() as cursor:
        cursor.execute("set local role glasswell_api")
        datasets, _ = _inventory(seeded, OBSERVED)
    seeded.rollback()

    assert {item.dataset_id for item in datasets} >= {
        "canonical.wells_latest/nd",
        "canonical.wells_latest/tx",
    }


def test_the_count_writer_appends_a_measurement_per_registered_jurisdiction(
    seeded: psycopg.Connection,
) -> None:
    """R-3's other half: the ledger the served `well_count` reads, written by a refresh that
    names itself. A jurisdiction with no wells gets a zero *total* here, because a measurement
    was taken — which is a different statement from serving no measurement at all."""
    measured = date(2026, 8, 28)
    refresh = counted(seeded, measured)

    with seeded.cursor() as cursor:
        cursor.execute(
            "select jurisdiction_code, status_key, well_count, derivation_id"
            " from lineage.jurisdiction_well_counts where measured_on = %s order by 1, 2",
            (measured,),
        )
        rows = cursor.fetchall()

    measurement = {(code, key): wells for code, key, wells, _ in rows}
    assert measurement[("ND", "*total*")] == 7
    assert measurement[("TX", "*total*")] == 1
    assert measurement[("NM", "*total*")] == 0
    # The total is the sum of the classes it is served beside, not a second count(*).
    classes = [
        wells
        for (code, key), wells in measurement.items()
        if code == "ND" and key != "*total*"
    ]
    assert sum(classes) == measurement[("ND", "*total*")]
    assert {derivation for *_, derivation in rows} == {refresh.derivation_id}
    assert refresh.rows == len(rows)


def test_a_well_whose_source_filed_no_status_is_counted_in_a_class_of_its_own(
    seeded: psycopg.Connection,
) -> None:
    """D2's upstream. The null bucket was summed into the total and dropped on the way out, so
    the classes served beside a total did not add up to it."""
    seed_statusless_well(seeded, api10=f"{TX_API10[:2]}00399991", like=TX_API10)
    measured = date(2026, 8, 29)

    counted(seeded, measured)

    measurement = ledger(seeded, measured)
    assert measurement[("TX", UNMAPPED_CLASS)][0] == 1
    for code in ("ND", "TX", "NM", "MT"):
        classes = [
            wells
            for (owner, key), (wells, _) in measurement.items()
            if owner == code and key != TOTAL_STATUS_KEY
        ]
        assert sum(classes) == measurement[(code, TOTAL_STATUS_KEY)][0], code


def test_a_class_no_well_carries_is_measured_at_zero_rather_than_left_out(
    seeded: psycopg.Connection,
) -> None:
    """"None of these here" is a measurement; "nobody has counted" is not, and only the writer
    can tell the client which it is. `group by` yields no group for a class nothing carries, so
    the zero has to be emitted rather than left to be inferred from an absence -- which is the
    same mistake, one layer up, as the null bucket that was dropped on the way out."""
    measured = date(2026, 8, 29)

    counted(seeded, measured)

    measurement = ledger(seeded, measured)
    vocabulary = set(served_status_vocabulary(seeded)) | {UNMAPPED_CLASS}
    assert len(vocabulary) > 5, vocabulary
    for code in CODES:
        classes = {
            key for (owner, key), _ in measurement.items() if owner == code
        } - {TOTAL_STATUS_KEY}
        assert classes == vocabulary, code
    # The fixture's North Dakota holds active and plugged wells and nothing else.
    assert measurement[("ND", "active")][0] > 0
    assert measurement[("ND", "drilling")][0] == 0
    assert measurement[("ND", UNMAPPED_CLASS)][0] == 0


def test_a_class_the_day_does_not_hold_lands_on_it_without_rewriting_what_does(
    seeded: psycopg.Connection,
) -> None:
    """The day-of-fix re-measure, which is what the host needs after this lands: the key is
    (jurisdiction, measured_on, status), so a row the day is missing inserts on a per-row
    conflict and every row already on it is kept, with the derivation that wrote it."""
    seed_statusless_well(seeded, api10=f"{TX_API10[:2]}00399991", like=TX_API10)
    measured = date(2026, 8, 29)
    first = counted(seeded, measured, codes=("ND",))
    seeded.commit()

    second = counted(seeded, measured)

    measurement = ledger(seeded, measured)
    assert measurement[("TX", UNMAPPED_CLASS)] == (1, second.derivation_id)
    assert measurement[("ND", TOTAL_STATUS_KEY)][1] == first.derivation_id


def test_a_second_run_on_the_same_day_appends_nothing_rather_than_rewriting(
    seeded: psycopg.Connection,
) -> None:
    """The ledger is append-only, so a correction is a measurement on a later day."""
    measured = date(2026, 8, 28)
    counted(seeded, measured)
    seeded.commit()
    with seeded.cursor() as cursor:
        cursor.execute("select count(*) from lineage.jurisdiction_well_counts")
        first = cursor.fetchone()[0]

    counted(seeded, measured)

    with seeded.cursor() as cursor:
        cursor.execute("select count(*) from lineage.jurisdiction_well_counts")
        assert cursor.fetchone()[0] == first
