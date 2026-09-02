"""The Status page's jurisdiction arms are generated from the registry, not written per state.

Sixteen literals decided the wells arms and ten more the completions arms, so a fifth
jurisdiction meant editing this collector. It does not any more: the arms are a comprehension
over the resolved registrations, and an arm the tables hold nothing for says so rather than
publishing a zero that reads as "no wells".
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import psycopg
import pytest

from glasswell.lineage.capture import lineage_session
from glasswell.lineage.jurisdictions import clear_jurisdiction_cache
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.counts import refresh_jurisdiction_counts
from glasswell.status.collector import EMPTY_ARM, _inventory
from tests.support.fakes import FixedClock
from tests.support.jurisdictions import restate
from tests.support.seed import FIXTURE_ENV

pytestmark = pytest.mark.contract

OBSERVED = datetime(2026, 8, 26, 18, tzinfo=UTC)
WYOMING_PREFIX = "49"


def counted(connection: psycopg.Connection, measured: date):
    """The refresh, inside the lineage session every derivation is recorded in."""
    with lineage_session(
        recorder=PostgresRecorder(connection),
        environment=FIXTURE_ENV,
        clock=FixedClock(OBSERVED),
        correlation_id="run_contract_counts",
    ):
        return refresh_jurisdiction_counts(connection, measured_on=measured)


@pytest.fixture(autouse=True)
def _uncached() -> None:
    clear_jurisdiction_cache()


def inventory(connection: psycopg.Connection) -> dict[str, object]:
    datasets, _ = _inventory(connection, OBSERVED)
    return {item.dataset_id: item for item in datasets}


def register_wyoming(connection: psycopg.Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("insert into lineage.jurisdiction_codes values ('WY', 'state')")
        cursor.execute(
            "insert into lineage.jurisdictions (jurisdiction_code, effective_from,"
            " published_at, evidence_tag, evidence_commit, name, regulator_name, regulator_url,"
            " identity_scheme, identity_prefix, identity_pattern, source_ids, rationale)"
            " select %s, effective_from, published_at, evidence_tag, evidence_commit,"
            " 'Wyoming', 'WOGCC', 'https://wogcc.wyo.gov', 'api10', %s, %s,"
            " array['nd_mpr_xlsx'], 'a fifth jurisdiction, registered and not yet loaded'"
            " from lineage.jurisdictions where jurisdiction_code = 'ND'",
            ("WY", WYOMING_PREFIX, f"^{WYOMING_PREFIX}[0-9]{{8}}$"),
        )
    clear_jurisdiction_cache()


def test_a_fifth_jurisdiction_yields_a_fifth_dataset_with_no_edit(
    seeded: psycopg.Connection,
) -> None:
    """The exit criterion, stated as the thing that used to require a commit."""
    before = inventory(seeded)
    assert "canonical.wells_latest/wy" not in before

    register_wyoming(seeded)

    after = inventory(seeded)
    assert after["canonical.wells_latest/wy"].label == "Current Wyoming wells"
    assert after["canonical.wells_latest/wy"].scope == "Wyoming"
    assert "canonical.well_completions/co" in after
    assert len(after) == len(before) + 2


def test_an_arm_the_tables_hold_nothing_for_is_unavailable_and_not_a_zero(
    seeded: psycopg.Connection,
) -> None:
    """"Not loaded" and "none" are different facts. A zero here would say Wyoming has no
    wells, which is a claim nothing measured — the same ruling as an absent `well_count`."""
    register_wyoming(seeded)
    resident = inventory(seeded)

    empty = resident["canonical.wells_latest/wy"]
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
