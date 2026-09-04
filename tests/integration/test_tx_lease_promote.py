"""The filed lease volume, promoted at the grain the regulator filed it at.

4F.1 keeps the fact in canonical at its native grain and 4F.2 keeps the estimate in a mart, and
`020_production_entity_key.sql:43-46` enforces the split independently of anything this module
does. What is exercised here is everything the promotion decides: which columns become which
stream, what a filed zero is against an unfiled month, what happens to a volume that is not one,
and what happens to a lease this deployment does not hold.
"""

from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import psycopg
import pytest

from glasswell.ingest import tx_pdq
from glasswell.ingest.tx_pdq import (
    LEASE_CYCLE_MEMBER,
    SOURCE_KEY,
    ArchiveFormatError,
    MemberLayout,
    _member_rows,
    production_month,
)
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.seed import seed_all
from glasswell.seed.conformance_tx import PDQ_MEMBER_LAYOUT
from tests.support.fakes import FixedClock

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tx_pdq"
SAMPLE = FIXTURES / "PDQ_DSV_sample.zip"

# The layout load() resolves from the rule in force, built from the same registry the rule row
# is published from so a reader of the fixture is judged by the rule and not by the fixture.
LAYOUT = MemberLayout("cr_tx_pdq_format_2", PDQ_MEMBER_LAYOUT)


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


@pytest.fixture
def seeded(db: psycopg.Connection) -> psycopg.Connection:
    seed_all(db)
    db.commit()
    return db


@pytest.fixture
def promoted(seeded, raw_root: Path, lineage_env):
    with lineage_session(
        recorder=PostgresRecorder(seeded), environment=lineage_env
    ), client_for(SAMPLE) as client:
        result = tx_pdq.load(
            seeded,
            url=f"https://example.invalid/{SOURCE_KEY}",
            raw_root=raw_root,
            client=client,
            expect_bytes=SAMPLE.stat().st_size,
        )
    seeded.commit()
    return result


def test_every_promoted_row_is_a_lease_row_at_the_lease_grain(promoted, seeded) -> None:
    """DIR-3 and the composition check both say it, and this is the observation that it held."""
    distinct = rows(
        seeded,
        "select distinct entity_type, reporting_level, granularity, api10 is null"
        "  from canonical.production_monthly where source_id = 'tx_pdq_dsv'",
    )

    assert distinct == [("lease", "lease", "lease_reported", True)]


def test_the_entity_key_is_the_three_part_lease_key(promoted, seeded) -> None:
    """Bare LEASE_NO collides on 33,868 of 348,293 leases, so the district and the oil-gas code
    are both in the key -- and the oil-gas code is what keeps one wellbore's two leases apart."""
    assert scalar(
        seeded,
        "select count(*) from canonical.production_monthly"
        " where source_id = 'tx_pdq_dsv' and entity_key !~ '^[OG]-[0-9]{2}-[0-9]{6}$'",
    ) == 0


def test_an_oil_lease_files_oil_and_casinghead_gas_and_a_gas_lease_files_the_other_two(
    promoted, seeded
) -> None:
    """The two liquid columns are disjoint populations keyed by OIL_GAS_CODE, so their union
    double-counts nothing, and casinghead gas is the whole gas story on an oil lease."""
    def streams(code: str) -> set[str]:
        return {
            row[0]
            for row in rows(
                seeded,
                "select distinct stream from canonical.production_monthly"
                " where source_id = 'tx_pdq_dsv' and left(entity_key, 1) = %s",
                (code,),
            )
        }

    oil_streams, gas_streams = streams("O"), streams("G")

    assert oil_streams == {"oil", "gas"}
    assert gas_streams == {"condensate", "gas"}


def test_no_water_stream_is_promoted_because_the_member_has_no_water_column(
    promoted, seeded
) -> None:
    assert scalar(
        seeded,
        "select count(*) from canonical.production_monthly"
        " where source_id = 'tx_pdq_dsv' and stream = 'water'",
    ) == 0


def test_a_filed_zero_and_an_unfiled_month_are_never_collapsed(promoted, seeded) -> None:
    """PROD_REPORT_FILED_FLAG is the operator's own statement that a report exists, so a zero
    under it is a reported zero and a blank without it is a month nobody filed. A reader sees a
    decline either way; only null_semantics says which it is."""
    labelled = dict(
        rows(
            seeded,
            "select null_semantics, count(*) from canonical.production_monthly"
            " where source_id = 'tx_pdq_dsv' and entity_key = 'O-08-000808'"
            " group by 1 order by 1",
        )
    )

    assert labelled["reported_zero"] > 0
    assert labelled["no_report"] > 0
    # Both carry volume 0, because canonical.volume is NOT NULL. The label is the difference.
    assert scalar(
        seeded,
        "select bool_and(volume = 0) from canonical.production_monthly"
        " where source_id = 'tx_pdq_dsv' and entity_key = 'O-08-000808'"
        "   and null_semantics in ('reported_zero', 'no_report')",
    ) is True


def test_a_negative_correction_is_promoted_as_filed(promoted, seeded) -> None:
    """The RRC says production information may change as revised, corrected or delinquent
    reports arrive. A correction dropped here leaves the lease's history overstated for ever."""
    assert scalar(
        seeded,
        "select volume from canonical.production_monthly"
        " where source_id = 'tx_pdq_dsv' and entity_key = 'O-08-000606'"
        "   and production_month = '2024-06-01' and stream = 'oil'",
    ) == Decimal("-7.000")


def test_a_volume_that_is_not_one_is_quarantined_and_never_promoted(promoted, seeded) -> None:
    """Both arms: a value that is not a number, and one canonical's numeric(18,3) cannot hold.
    Truncating either would produce a number that looks filed."""
    quarantined = scalar(
        seeded,
        "select count(*) from lineage.quarantine_rows"
        " where source_id = 'tx_pdq_dsv' and reason_code = 'impossible_volume'",
    )

    assert quarantined == 2
    assert scalar(
        seeded,
        "select count(*) from canonical.production_monthly"
        " where source_id = 'tx_pdq_dsv' and entity_key = 'O-08-001010'"
        "   and production_month in ('2024-02-01', '2024-03-01') and stream = 'oil'",
    ) == 0


def test_an_out_of_scope_lease_is_counted_and_never_quarantined(promoted, seeded) -> None:
    """Nothing about an out-of-scope row failed: it is a row about a well this deployment does
    not hold, and widening the scope is a re-parse rather than a release."""
    assert scalar(
        seeded,
        "select count(*) from canonical.production_monthly"
        " where source_id = 'tx_pdq_dsv' and entity_key = 'O-08-000909'",
    ) == 0
    assert promoted.lease_promotion["rows_excluded_out_of_scope"] > 0
    assert scalar(
        seeded,
        "select count(*) from lineage.quarantine_rows"
        " where source_id = 'tx_pdq_dsv' and reason_code = 'out_of_scope'",
    ) == 0


def test_a_lease_with_no_crosswalk_row_promotes_nothing(promoted, seeded) -> None:
    """It is out of scope for want of a well to place it, which is the same audit-event path
    and not a reject: the volume is real and the ledger is where it is accounted for."""
    assert scalar(
        seeded,
        "select count(*) from canonical.production_monthly"
        " where source_id = 'tx_pdq_dsv' and entity_key = 'O-08-000707'",
    ) == 0


def test_the_promotion_runs_a_calendar_year_at_a_time_with_a_recorded_high_water_mark(
    promoted, seeded
) -> None:
    """canonical is append-only, so a stop lands on a year boundary rather than inside one."""
    with zipfile.ZipFile(SAMPLE) as archive:
        years = {
            production_month(row["CYCLE_YEAR_MONTH"]).year
            for row in _member_rows(archive, LEASE_CYCLE_MEMBER, LAYOUT)
        }

    assert promoted.lease_promotion["high_water_year"] == max(years)
    partitions = rows(
        seeded,
        "select distinct output_partition ->> 'entity_type' from lineage.derivations"
        " where operation = 'canonical.promote'"
        "   and output_dataset = 'canonical.production_monthly'"
        "   and output_partition ->> 'state' = 'TX'",
    )
    assert partitions == [("lease",)]


def test_a_re_promotion_of_the_same_vintage_appends_nothing(
    promoted, seeded, raw_root: Path, lineage_env
) -> None:
    """The canonical PK carries report_vintage, so the same lease-month at the same vintage is
    one row however many times the promotion runs."""
    before = scalar(
        seeded,
        "select count(*) from canonical.production_monthly where source_id = 'tx_pdq_dsv'",
    )
    with lineage_session(
        recorder=PostgresRecorder(seeded), environment=lineage_env
    ), client_for(SAMPLE) as client:
        tx_pdq.load(
            seeded,
            url=f"https://example.invalid/{SOURCE_KEY}",
            raw_root=raw_root,
            client=client,
            expect_bytes=SAMPLE.stat().st_size,
        )
    seeded.commit()

    assert scalar(
        seeded,
        "select count(*) from canonical.production_monthly where source_id = 'tx_pdq_dsv'",
    ) == before


def test_a_member_whose_header_moved_promotes_nothing_at_all(
    seeded, raw_root: Path, lineage_env, tmp_path: Path
) -> None:
    """NIT-6. A schema change invalidates the row mapping rather than one row, so there is
    nothing to quarantine and the run refuses before it has written a single canonical row."""
    drifted = tmp_path / "drifted.zip"
    with zipfile.ZipFile(SAMPLE) as source, zipfile.ZipFile(drifted, "w") as target:
        for name in source.namelist():
            text = source.read(name).decode()
            if name == LEASE_CYCLE_MEMBER:
                lines = text.splitlines()
                lines[1] = lines[1] + "}extra"
                text = "\n".join(lines) + "\n"
            target.writestr(name, text)

    with lineage_session(
        recorder=PostgresRecorder(seeded), environment=lineage_env
    ), client_for(drifted) as client, pytest.raises(ArchiveFormatError):
        tx_pdq.load(
            seeded,
            url=f"https://example.invalid/{SOURCE_KEY}",
            raw_root=raw_root,
            client=client,
            expect_bytes=drifted.stat().st_size,
        )
    seeded.rollback()

    assert scalar(
        seeded,
        "select count(*) from canonical.production_monthly where source_id = 'tx_pdq_dsv'",
    ) == 0


def test_a_refused_stage_still_records_the_fetch_it_completed(
    seeded, raw_root: Path, lineage_env, tmp_path: Path
) -> None:
    """A completed fetch is a fact and the parse is a separate outcome.

    Held to the end of load(), the manifest rolled back with the refusal and left the archive
    sealed on disk with no row naming it -- which is what happened on 2026-09-04 to 3.65 GB
    that no re-run can reach, because stage_payload() reuses a slot only through owning_slot()
    and owning_slot() reads lineage.manifests.
    """
    seeded.commit()  # the environments row the fixture planted, so the rollback below is the load's
    drifted = tmp_path / "drifted.zip"
    with zipfile.ZipFile(SAMPLE) as source, zipfile.ZipFile(drifted, "w") as target:
        for name in source.namelist():
            text = source.read(name).decode()
            if name == LEASE_CYCLE_MEMBER:
                header, _, body = text.partition("\n")
                text = header + "}INVENTED_COLUMN\n" + body
            target.writestr(name, text)

    with lineage_session(
        recorder=PostgresRecorder(seeded), environment=lineage_env
    ), client_for(drifted) as client, pytest.raises(ArchiveFormatError):
        tx_pdq.load(
            seeded,
            url=f"https://example.invalid/{SOURCE_KEY}",
            raw_root=raw_root,
            client=client,
            expect_bytes=drifted.stat().st_size,
        )
    seeded.rollback()

    recorded = rows(
        seeded,
        "select sha256, storage_uri from lineage.manifests where source_id = 'tx_pdq_dsv'",
    )
    assert len(recorded) == 1
    assert Path(recorded[0][1]).is_file()
    assert scalar(
        seeded, "select count(*) from staging.tx_pdq_well_completion"
    ) == 0


def test_the_re_run_after_a_refusal_reuses_the_slot_it_already_paid_for(
    seeded, raw_root: Path, lineage_env, tmp_path: Path
) -> None:
    """There is no resume -- the portal ignores Range -- so a re-run spends the whole fetch
    again. What it must not do is place a second 3.65 GB copy beside the first."""
    seeded.commit()  # the environments row the fixture planted, so the rollback below is the load's
    drifted = tmp_path / "drifted.zip"
    with zipfile.ZipFile(SAMPLE) as source, zipfile.ZipFile(drifted, "w") as target:
        for name in source.namelist():
            text = source.read(name).decode()
            if name == LEASE_CYCLE_MEMBER:
                header, _, body = text.partition("\n")
                text = header + "}INVENTED_COLUMN\n" + body
            target.writestr(name, text)

    # Two clocks a minute apart: the artifact directory carries the fetch time to the second,
    # so two runs inside one second would collide into the same slot and prove nothing.
    for minute in (11, 12):
        with lineage_session(
            recorder=PostgresRecorder(seeded),
            environment=lineage_env,
            clock=FixedClock(datetime(2026, 9, 4, 19, minute, 0, tzinfo=UTC)),
        ), client_for(drifted) as client, pytest.raises(ArchiveFormatError):
            tx_pdq.load(
                seeded,
                url=f"https://example.invalid/{SOURCE_KEY}",
                raw_root=raw_root,
                client=client,
                expect_bytes=drifted.stat().st_size,
            )
        seeded.rollback()

    placed = sorted((raw_root / "tx_pdq_dsv" / "pdq-dsv-zip").iterdir())

    assert len(placed) == 1
    assert scalar(
        seeded, "select count(*) from lineage.manifests where source_id = 'tx_pdq_dsv'"
    ) == 1


def test_the_run_reports_what_it_promoted(promoted) -> None:
    """The count is measured and reported rather than estimated: the relation growth an
    operator has to plan for is the number of rows this actually appended."""
    measured = promoted.lease_promotion

    assert measured["rows_appended"] == measured["rows_built"] > 0
    assert measured["rows_read"] == promoted.lease_rows_staged
    assert measured["rows_quarantined"] == 2
