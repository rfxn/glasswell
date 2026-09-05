"""A revised lease volume is appended, never applied as an edit.

The RRC's own sentence is the justification: *"Production reports reflect a snapshot in time.
For this reason, production information may change and be updated as the Commission receives
revised, corrected or delinquent production reports from operators."* PDQ is a full monthly
re-publication, so a restatement is two dumps and the canonical PK's `report_vintage` is the
whole mechanism — the older figure stays readable at `?as_of=` on the lease series.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import psycopg
import pytest

from glasswell.ingest import tx_pdq
from glasswell.ingest.tx_pdq import SOURCE_KEY
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.seed import seed_all
from tests.conftest import install_lineage_env
from tests.support.fakes import FixedClock

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tx_pdq"
FIRST = FIXTURES / "PDQ_DSV_sample.zip"
SECOND = FIXTURES / "PDQ_DSV_sample_restated.zip"

RESTATED_LEASE = "O-08-000101"
RESTATED_MONTH = "2024-01-01"
AUGUST = datetime(2026, 8, 27, 6, 0, 0, tzinfo=UTC)
SEPTEMBER = datetime(2026, 9, 26, 6, 0, 0, tzinfo=UTC)


def client_for(payload: Path) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload.read_bytes())

    return httpx.Client(transport=httpx.MockTransport(handler))


def scalar(db, sql: str, parameters: tuple = ()):
    with db.cursor() as cursor:
        cursor.execute(sql, parameters)
        row = cursor.fetchone()
    return row[0] if row else None


def rows(db, sql: str, parameters: tuple = ()) -> list[tuple]:
    with db.cursor() as cursor:
        cursor.execute(sql, parameters)
        return cursor.fetchall()


def _load(connection, payload: Path, raw_root: Path, lineage_env, *, clock=None):
    with lineage_session(
        recorder=PostgresRecorder(connection), environment=lineage_env, clock=clock
    ), client_for(payload) as client:
        result = tx_pdq.load(
            connection,
            url=f"https://example.invalid/{SOURCE_KEY}",
            raw_root=raw_root,
            client=client,
            expect_bytes=payload.stat().st_size,
            promote_years=[2024],
        )
    connection.commit()
    return result


@pytest.fixture(scope="module")
def restated_template(module_template, module_raw_root: Path) -> tuple[str, tuple]:
    """Two dumps a month apart, run once into a template every test here clones.

    Nothing is backdated by hand: canonical is append-only, so the only honest way to have two
    vintages is to run the load under two clocks. Six tests read the same pair, and building it
    per test was 5.4-7.4 s of setup against a 0.00 s body on each (A-timing.md 1).
    """
    loads = []

    def seed(connection: psycopg.Connection) -> None:
        seed_all(connection)
        connection.commit()
        environment = install_lineage_env(connection)
        loads.append(
            _load(connection, FIRST, module_raw_root, environment, clock=FixedClock(AUGUST))
        )
        loads.append(
            _load(connection, SECOND, module_raw_root, environment, clock=FixedClock(SEPTEMBER))
        )

    return module_template("tx_restatement", seed), tuple(loads)


@pytest.fixture
def seeded(clone, restated_template: tuple[str, tuple]) -> psycopg.Connection:
    """This test's own copy of the restated database."""
    return clone(restated_template[0])


@pytest.fixture
def restated(seeded: psycopg.Connection, restated_template: tuple[str, tuple]) -> tuple:
    """The two load reports. `seeded` is what they landed in."""
    return restated_template[1]


@pytest.fixture
def raw_root(shared_raw_root: Path) -> Path:
    """The module's zone: both vintages' archives are already in it."""
    return shared_raw_root


@pytest.fixture
def lineage_env(seeded: psycopg.Connection):
    """Overrides the tier fixture, which would clone a second database for the row."""
    return install_lineage_env(seeded)


def test_a_revised_volume_appends_a_second_row_and_edits_none(restated, seeded) -> None:
    volumes = rows(
        seeded,
        "select report_vintage, volume from canonical.production_monthly"
        " where source_id = 'tx_pdq_dsv' and entity_key = %s and production_month = %s"
        "   and stream = 'oil' order by report_vintage",
        (RESTATED_LEASE, RESTATED_MONTH),
    )

    assert len(volumes) == 2
    assert [volume for _, volume in volumes] == [Decimal("901.000"), Decimal("1201.000")]


def test_the_older_figure_is_still_readable_at_its_own_vintage(restated, seeded) -> None:
    """`greatest report_vintage <= as_of, per (entity, month, stream, source)` is the semantics
    lineage/vintages.py states, and this is what makes it answerable for Texas leases."""
    older = AUGUST.date()

    assert scalar(
        seeded,
        "select volume from canonical.production_monthly"
        " where source_id = 'tx_pdq_dsv' and entity_key = %s and production_month = %s"
        "   and stream = 'oil' and report_vintage <= %s"
        " order by report_vintage desc limit 1",
        (RESTATED_LEASE, RESTATED_MONTH, older),
    ) == Decimal("901.000")


def test_a_lease_month_nothing_revised_carries_one_row_per_vintage_and_no_duplicate(
    restated, seeded
) -> None:
    """A full re-publication re-files every month, so the unchanged ones are appended at the
    new vintage too -- what must not happen is a third row at a vintage nobody filed."""
    vintages = rows(
        seeded,
        "select count(distinct report_vintage), count(*) from canonical.production_monthly"
        " where source_id = 'tx_pdq_dsv' and entity_key = %s and production_month = '2024-02-01'"
        "   and stream = 'oil'",
        (RESTATED_LEASE,),
    )

    assert vintages == [(2, 2)]


def test_nothing_in_canonical_was_updated_or_deleted(restated, seeded) -> None:
    """The append-only trigger is what makes the claim structural rather than a convention."""
    with pytest.raises(psycopg.errors.RestrictViolation), seeded.cursor() as cursor:
        cursor.execute(
            "update canonical.production_monthly set volume = 0 where source_id = 'tx_pdq_dsv'"
        )
    seeded.rollback()
    with pytest.raises(psycopg.errors.RestrictViolation), seeded.cursor() as cursor:
        cursor.execute("delete from canonical.production_monthly where source_id = 'tx_pdq_dsv'")
    seeded.rollback()


def test_the_two_vintages_carry_two_manifests_and_two_derivations(restated, seeded) -> None:
    """The restatement is traceable to the dump that filed it: a reader asking why the figure
    moved gets a different manifest, not a different opinion."""
    first, second = restated

    assert first.manifest_id != second.manifest_id
    derivations = rows(
        seeded,
        "select count(distinct derivation_id) from canonical.production_monthly"
        " where source_id = 'tx_pdq_dsv' and entity_key = %s and production_month = %s"
        "   and stream = 'oil'",
        (RESTATED_LEASE, RESTATED_MONTH),
    )
    assert derivations == [(2,)]


def test_membership_accretes_across_vintages_and_removes_no_month(restated, seeded) -> None:
    """A later crosswalk that drops a well never removes it from a month already resolved at an
    earlier vintage: nothing is retro-deleted and each vintage is appended."""
    vintages = scalar(
        seeded,
        "select count(distinct effective_from) from canonical.lease_membership"
        " where jurisdiction_code = 'TX'",
    )

    assert vintages == 2
    assert scalar(
        seeded,
        "select count(*) from canonical.lease_membership"
        " where jurisdiction_code = 'TX' and api10 = '4200300001'",
    ) == 4
