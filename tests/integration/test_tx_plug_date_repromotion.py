"""Filling a column the promotion never persisted, from the bytes the parse already staged.

`_INSERT_WELL` ends `on conflict (api10, effective_from) do nothing`, so a new column takes a
new effective_from — which is right and DIR-2-safe: it appends a vintage and rewrites none.
The precedent is `ingest/repromote.py`, written for the identical shape on North Dakota: it
reads staging, re-runs validate, conform and promote, and a well whose values are unchanged
appends nothing.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import psycopg
import pytest

from glasswell.ingest import tx_wellbore
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.seed import seed_all

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
EWA_CSV = FIXTURES / "tx_ewa" / "OG_WELLBORE_EWA_sample.csv"
LATER_VINTAGE = date(2026, 9, 6)


def client_for(payload: Path) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload.read_bytes())

    return httpx.Client(transport=httpx.MockTransport(handler))


def scalar(db, sql: str, parameters: tuple = ()):
    with db.cursor() as cursor:
        cursor.execute(sql, parameters)
        row = cursor.fetchone()
    return row[0] if row else None


@pytest.fixture
def seeded(db: psycopg.Connection) -> psycopg.Connection:
    seed_all(db)
    db.commit()
    return db


@pytest.fixture
def loaded(seeded, raw_root: Path, lineage_env):
    with lineage_session(
        recorder=PostgresRecorder(seeded), environment=lineage_env
    ), client_for(EWA_CSV) as client:
        result = tx_wellbore.load(seeded, raw_root=raw_root, client=client)
    seeded.commit()
    return result


def test_the_first_load_already_persists_the_plug_date(loaded, seeded) -> None:
    """The value was parsed since the slice and used as the collapse rule's first tie-break,
    and discarded every time. A load from here on writes it."""
    filled = scalar(
        seeded, "select count(*) from canonical.wells_latest where plug_date is not null"
    )

    assert filled > 0
    assert scalar(
        seeded,
        "select bool_and(plug_date <= current_date) from canonical.wells_latest"
        " where plug_date is not null",
    ) is True


def test_a_re_promotion_over_unchanged_bytes_appends_nothing(loaded, seeded, lineage_env) -> None:
    """The whole claim of a re-promotion is that nothing but the schema moved, so a run over
    the same staged rows against the same canonical values is a no-op."""
    before = scalar(seeded, "select count(*) from canonical.wells")
    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env):
        report = tx_wellbore.repromote_plug_dates(seeded, report_vintage=LATER_VINTAGE)
    seeded.commit()

    assert report.wells_examined > 0
    assert report.wells_appended == 0
    assert scalar(seeded, "select count(*) from canonical.wells") == before


def test_a_re_promotion_onto_a_spine_with_no_plug_dates_appends_only_the_wells_that_move(
    loaded, seeded, lineage_env
) -> None:
    """The upper bound if the skip were not implemented is the whole spine at a second
    vintage; the floor is the wells carrying a plugging date. This measures which it is."""
    with seeded.cursor() as cursor:
        cursor.execute("select count(*) from canonical.wells_latest where plug_date is not null")
        (with_dates,) = cursor.fetchone()
        cursor.execute("select count(*) from canonical.wells_latest")
        (spine,) = cursor.fetchone()
        # Put the spine back to what it looked like before the column existed, which is the
        # state the deployed host is in.
        cursor.execute("alter table canonical.wells disable trigger wells_append_only")
        cursor.execute("update canonical.wells set plug_date = null")
        cursor.execute("alter table canonical.wells enable trigger wells_append_only")
    seeded.commit()

    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env):
        report = tx_wellbore.repromote_plug_dates(seeded, report_vintage=LATER_VINTAGE)
    seeded.commit()

    assert report.wells_appended == with_dates
    assert report.wells_appended < spine
    assert report.plug_dates_filled == with_dates


def test_the_appended_rows_land_at_their_own_report_vintage(
    loaded, seeded, lineage_env
) -> None:
    with seeded.cursor() as cursor:
        cursor.execute("alter table canonical.wells disable trigger wells_append_only")
        cursor.execute("update canonical.wells set plug_date = null")
        cursor.execute("alter table canonical.wells enable trigger wells_append_only")
    seeded.commit()
    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env):
        tx_wellbore.repromote_plug_dates(seeded, report_vintage=LATER_VINTAGE)
    seeded.commit()

    assert scalar(
        seeded,
        "select count(*) from canonical.wells where effective_from = %s and plug_date is not null",
        (LATER_VINTAGE,),
    ) > 0
    assert scalar(
        seeded,
        "select bool_and(plug_date is not null) from canonical.wells_latest"
        " where api10 in (select api10 from canonical.wells where effective_from = %s)",
        (LATER_VINTAGE,),
    ) is True


def test_the_re_promotion_reads_staging_and_never_a_second_fetch(
    loaded, seeded, lineage_env
) -> None:
    """A 3.65 GB sibling and a 1.3 M-record export are not re-fetched to fill a column: the
    raw bytes are retained and their hash is the manifest's."""
    manifests = scalar(seeded, "select count(*) from lineage.manifests")
    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env):
        tx_wellbore.repromote_plug_dates(seeded, report_vintage=LATER_VINTAGE)
    seeded.commit()

    assert scalar(seeded, "select count(*) from lineage.manifests") == manifests


def test_the_run_says_what_it_did_as_a_ledger_fact(loaded, seeded, lineage_env) -> None:
    """A status that moves under a track about production is a thing a reader should be told
    about rather than discover."""
    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env):
        report = tx_wellbore.repromote_plug_dates(seeded, report_vintage=LATER_VINTAGE)
    seeded.commit()

    payload = scalar(
        seeded,
        "select payload from lineage.audit_events"
        " where event_type = 'canonical.repromotion_required' order by occurred_at desc limit 1",
    )

    assert payload["wells_examined"] == report.wells_examined
    assert payload["status_moved"] == report.status_moved
    assert payload["reason"].startswith("plug_date")
