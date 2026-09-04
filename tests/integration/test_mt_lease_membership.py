"""Montana's well-to-lease-unit membership, promoted into canonical before anything reads it.

The lease unit exists only on `staging.mt_bogc_well.lease_unit`. A mart reading staging is the
breach `marts/producing.py:9-10` names, so the back-test that scores the allocation method
against Montana cannot reach it until it is in canonical — which is the whole reason this phase
exists ahead of the mart that consumes it.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import psycopg
import pytest

from glasswell.ingest import mt_bogc
from glasswell.ingest.base import open_ingest_run
from glasswell.seed import seed_all

FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "mt_bogc" / "MT_Historical_Production_sample.zip"
)
SENTINEL = "-999"


def client_for(path: Path) -> httpx.Client:
    payload = path.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload,
            headers={
                "content-type": "application/zip",
                "etag": '"4653fb2-6593e310d4b83"',
                "last-modified": "Mon, 17 Aug 2026 13:31:46 GMT",
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def promoted(db, raw_root, lineage_env) -> mt_bogc.IngestReport:
    seed_all(db)
    db.commit()
    with open_ingest_run(
        db, source_id=mt_bogc.SOURCE_ID, raw_root=raw_root, environment=lineage_env
    ) as run, client_for(FIXTURE) as client:
        report = mt_bogc.ingest_archive(run, client=client)
    db.commit()
    return report


def query(db, sql: str, *parameters: object) -> list[tuple]:
    with db.cursor() as cursor:
        cursor.execute(sql, parameters or None)
        return cursor.fetchall()


def scalar(db, sql: str, *parameters: object):
    rows = query(db, sql, *parameters)
    return rows[0][0] if rows else None


def test_membership_lands_in_canonical_and_not_in_a_mart_reading_staging(promoted, db) -> None:
    assert promoted.membership is not None
    assert promoted.membership.rows_appended > 0
    assert scalar(
        db,
        "select count(*) from canonical.lease_membership where jurisdiction_code = 'MT'",
    ) == promoted.membership.rows_appended


def test_montanas_rows_say_what_kind_of_evidence_they_are(promoted, db) -> None:
    """N-26. Texas's rows are a regulator-published crosswalk table and Montana's are read off
    the production file's own column; calling both a published crosswalk would misdescribe
    half the table on the day it ships."""
    roles = query(
        db,
        "select distinct link_role from canonical.lease_membership"
        " where jurisdiction_code = 'MT'",
    )

    assert roles == [("filing_derived",)]


def test_no_sentinel_or_blank_lease_key_reaches_canonical(promoted, db) -> None:
    assert scalar(
        db,
        "select count(*) from canonical.lease_membership"
        " where jurisdiction_code = 'MT' and (lease_key = %s or btrim(lease_key) = '')",
        SENTINEL,
    ) == 0


def test_a_staged_sentinel_row_is_nulled_rather_than_keyed(
    promoted, db, raw_root, lineage_env
) -> None:
    """cr_mt_lease_unit_sentinel_1: treating -999 as data would mint a lease entity named -999
    that aggregates unrelated wells across the whole state.

    Planted rather than read from the fixture. `MT_Historical_Production_sample.zip` carries
    zero `-999` rows in either member, although `test_mt_bogc_promote.py`'s docstring says it
    carries the sentinel — so a test that read the fixture for this would pass over a
    promotion that had stopped nulling it. Handed back; proved here on a planted row.
    """
    with db.cursor() as cursor:
        cursor.execute(
            f"select manifest_id, max(source_row_ordinal) + 1 from {mt_bogc.WELL_STAGING}"
            " group by manifest_id"
        )
        manifest_id, ordinal = cursor.fetchone()
        cursor.execute(
            f"insert into {mt_bogc.WELL_STAGING} (manifest_id, source_row_ordinal,"
            " api_wellno, lease_unit, rpt_date)"
            " values (%s, %s, '2500599999', %s, '05/31/2023')",
            (manifest_id, ordinal, SENTINEL),
        )
    db.commit()

    with open_ingest_run(
        db, source_id=mt_bogc.SOURCE_ID, raw_root=raw_root, environment=lineage_env
    ) as run:
        parse_rules, _validate, _conform = mt_bogc._grain_rules(
            db, mt_bogc.SOURCE_ID, run.as_of
        )
        manifest = _manifest(db, manifest_id)
        report = mt_bogc.promote_lease_membership(
            run, manifest=manifest, parse_rules=parse_rules, sentinel=SENTINEL
        )
    db.commit()

    assert report.sentinel_rows == 1
    assert scalar(
        db,
        "select count(*) from canonical.lease_membership"
        " where jurisdiction_code = 'MT' and (lease_key = %s or api10 = '2500599999')",
        SENTINEL,
    ) == 0


class _Manifest:
    def __init__(self, manifest_id: str, fetch_vintage) -> None:
        self.manifest_id = manifest_id
        self.fetch_vintage = fetch_vintage


def _manifest(db, manifest_id: str) -> _Manifest:
    return _Manifest(
        manifest_id,
        scalar(db, "select fetch_vintage from lineage.manifests where manifest_id = %s",
               manifest_id),
    )


def test_a_well_on_more_than_one_unit_carries_a_row_for_each(promoted, db) -> None:
    """The same shape Texas needs, for the same reason: the membership is what is being
    allocated over, so it is never folded to one row per well."""
    pairs = scalar(
        db,
        "select count(*) from canonical.lease_membership where jurisdiction_code = 'MT'",
    )
    wells = scalar(
        db,
        "select count(distinct api10) from canonical.lease_membership"
        " where jurisdiction_code = 'MT'",
    )

    assert pairs >= wells == promoted.membership.wells
    assert promoted.membership.lease_units > 0


def test_the_promoted_count_is_reported_against_the_units_the_rule_records(
    promoted, db
) -> None:
    """cr_mt_pru_reconciliation_1 records 7,149 PRU units statewide. The fixture is a cut, so
    what is asserted is that the measurement is made and is a subset — never that a fixture
    reproduces a statewide figure."""
    from glasswell.seed.conformance_mt import MT_RULES

    rule = next(row for row in MT_RULES if row["rule_id"] == "cr_mt_pru_reconciliation_1")
    statewide = int(rule["spec"]["key_overlap"]["pru_units"])

    assert statewide == 7149
    assert 0 < promoted.membership.lease_units <= statewide


def test_the_api10_is_the_identity_rule_s_and_not_a_second_normalisation(promoted, db) -> None:
    assert scalar(
        db,
        "select count(*) from canonical.lease_membership"
        " where jurisdiction_code = 'MT' and api10 !~ '^25[0-9]{8}$'",
    ) == 0


def test_every_membership_row_cites_the_derivation_and_the_manifest_that_made_it(
    promoted, db
) -> None:
    """No naked numbers runs to the rows a figure is built from: a share computed over this
    membership has to be able to name the filing it came from."""
    assert scalar(
        db,
        "select count(*) from canonical.lease_membership"
        " where jurisdiction_code = 'MT' and (derivation_id is null or"
        "       source_manifest_id is null)",
    ) == 0
    assert scalar(
        db,
        "select count(distinct derivation_id) from canonical.lease_membership"
        " where jurisdiction_code = 'MT'",
    ) == 1


def test_a_montana_row_and_a_texas_row_can_share_the_table_without_sharing_a_key(
    promoted, db
) -> None:
    """The table is jurisdiction-keyed, so Montana's lease unit and a Texas lease key cannot
    collide even where the strings would."""
    primary = query(
        db,
        "select a.attname from pg_index i"
        "  join pg_attribute a on a.attrelid = i.indrelid and a.attnum = any(i.indkey)"
        " where i.indrelid = 'canonical.lease_membership'::regclass and i.indisprimary"
        " order by a.attnum",
    )

    assert primary[0] == ("jurisdiction_code",)


def test_the_membership_promotion_is_not_a_second_read_of_the_archive(promoted, db) -> None:
    """It reads the rows the parse already staged against a verified manifest, which is what
    lets the whole thing re-run without a fetch."""
    assert scalar(db, "select count(*) from lineage.manifests where source_id = %s",
                  mt_bogc.SOURCE_ID) == 1


def test_a_membership_row_cannot_be_edited_in_place(promoted, db) -> None:
    with pytest.raises(psycopg.errors.RestrictViolation), db.cursor() as cursor:
        cursor.execute(
            "update canonical.lease_membership set lease_key = 'x' where jurisdiction_code = 'MT'"
        )
    db.rollback()
