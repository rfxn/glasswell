"""Pass one: one fetch, one manifest, and the crosswalk promoted as membership.

The archive is served from a mock transport rather than from the portal — a test that fetched
3.65 GB would be measuring the RRC's uptime. What is exercised is everything after the bytes
land: the member inventory, the two staged members, the allowlist derived from the crosswalk
because the lease member has no county, and the membership rows a dual-lease wellbore produces.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import psycopg
import pytest

from glasswell.ingest import tx_pdq
from glasswell.ingest.tx_pdq import (
    LEASE_CYCLE_MEMBER,
    SOURCE_KEY,
    WELL_COMPLETION_MEMBER,
    _member_rows,
    api10_from,
    lease_key,
)
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.seed import seed_all
from glasswell.seed.conformance_tx import PERMIAN_COUNTY_CODES

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tx_pdq"
SAMPLE = FIXTURES / "PDQ_DSV_sample.zip"
RESTATED = FIXTURES / "PDQ_DSV_sample_restated.zip"


def expected() -> dict[str, int]:
    """Counted from the fixture itself, never written down: a number typed here would be a
    claim about what the builder was supposed to make rather than about what it made."""
    import zipfile

    with zipfile.ZipFile(SAMPLE) as archive:
        completions = list(_member_rows(archive, WELL_COMPLETION_MEMBER))
        leases = list(_member_rows(archive, LEASE_CYCLE_MEMBER))
    by_api: dict[str, set[str]] = {}
    in_scope: set[str] = set()
    for row in completions:
        api10 = api10_from(row["API_COUNTY_CODE"], row["API_UNIQUE_NO"])
        assert api10 is not None
        key = lease_key(row["OIL_GAS_CODE"], row["DISTRICT_NO"], row["LEASE_NO"])
        by_api.setdefault(api10, set()).add(key)
        if row["API_COUNTY_CODE"] in PERMIAN_COUNTY_CODES:
            in_scope.add(key)
    return {
        "completions": len(completions),
        "lease_dimension": len({
            lease_key(row["OIL_GAS_CODE"], row["DISTRICT_NO"], row["LEASE_NO"])
            for row in leases
        }),
        "api10s": len(by_api),
        "doubled": sum(1 for keys in by_api.values() if len(keys) > 1),
        "lease_keys": len({key for keys in by_api.values() for key in keys}),
        "in_scope": len(in_scope),
        "pairs": sum(len(keys) for keys in by_api.values()),
    }


EXPECTED = expected()


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


def test_the_archive_is_fetched_once_and_recorded_with_its_hash_and_byte_count(
    loaded, seeded, raw_root: Path
) -> None:
    """The raw bytes are retained and their hash is the manifest's, so widening the scope later
    is a re-parse rather than a second 3.65 GB fetch."""
    manifest = scalar(
        seeded,
        "select sha256 is not null and bytes = %s from lineage.manifests where manifest_id = %s",
        (SAMPLE.stat().st_size, loaded.manifest_id),
    )

    assert manifest is True
    assert scalar(
        seeded, "select count(*) from lineage.manifests where source_id = 'tx_pdq_dsv'"
    ) == 1


def test_the_member_inventory_is_recorded_before_anything_is_parsed(loaded) -> None:
    inventory = {member.name: member for member in loaded.members}

    assert len(inventory) == 6
    assert inventory[LEASE_CYCLE_MEMBER].uncompressed > 0
    assert inventory[LEASE_CYCLE_MEMBER].compressed > 0


def test_the_crosswalk_and_the_lease_dimension_stage_unfiltered(loaded, seeded) -> None:
    """Unfiltered on purpose: the county scope is a promotion decision, and a parse that
    dropped rows would make the staged bytes disagree with the artifact their manifest names."""
    assert loaded.staged_completions == EXPECTED["completions"]
    assert loaded.staged_regulatory_leases == EXPECTED["lease_dimension"]
    assert scalar(seeded, "select count(*) from staging.tx_pdq_well_completion") == (
        EXPECTED["completions"]
    )


def test_the_lease_member_is_left_for_the_promotion_phase(loaded, seeded) -> None:
    """Pass one reads the small members and the crosswalk. The lease member is pass two's, and
    both passes read one on-disk artifact under one manifest and one sha256."""
    assert scalar(seeded, "select count(*) from staging.tx_pdq_lease_cycle") == 0


def test_membership_lands_as_the_canonical_crosswalk(loaded, seeded) -> None:
    assert loaded.membership_rows == EXPECTED["pairs"]
    assert scalar(
        seeded,
        "select count(*) from canonical.lease_membership"
        " where jurisdiction_code = 'TX' and link_role = 'canonical_crosswalk'",
    ) == EXPECTED["pairs"]


def test_a_wellbore_on_two_leases_carries_two_membership_rows(loaded, seeded) -> None:
    """M-16. They are not duplicates to collapse: they are the thing being allocated, and
    folding them would make the share's lease ambiguous."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select lease_key from canonical.lease_membership"
            " where api10 = '4200300001' order by lease_key"
        )
        keys = [row[0] for row in cursor.fetchall()]

    assert keys == ["G-08-000303", "O-08-000101"]
    assert loaded.api10s_with_two_lease_keys == 1


def test_the_scope_allowlist_is_derived_from_the_crosswalk_and_not_from_the_lease_member(
    loaded,
) -> None:
    """OG_LEASE_CYCLE has no county, so a lease is in scope when one of its wells is — and only
    OG_WELL_COMPLETION says where a well is. The fixture's out-of-scope lease is the proof."""
    assert loaded.lease_keys == EXPECTED["lease_keys"]
    assert loaded.in_scope_lease_keys == EXPECTED["in_scope"]
    assert loaded.in_scope_lease_keys < loaded.lease_keys


def test_the_exclusion_is_an_audit_event_and_never_a_quarantine(loaded, seeded) -> None:
    """Nothing about an out-of-scope row failed: it is a row about a well this deployment does
    not hold, and widening the scope is a re-parse."""
    assert scalar(
        seeded,
        "select count(*) from lineage.audit_events"
        " where event_type = 'staging.scope_excluded' and subject_id = %s",
        (loaded.manifest_id,),
    ) == 1
    assert scalar(seeded, "select count(*) from lineage.quarantine_rows") == 0


def test_every_measurement_this_load_took_lands_dated_in_the_census(loaded, seeded) -> None:
    """N-2. They live here rather than inside a rule row because a rule row cannot be
    re-measured, and R-5 needs to see the population move."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select measure, value from marts.tx_allocation_census order by measure"
        )
        census = dict(cursor.fetchall())

    assert census["crosswalk_api10s"] == EXPECTED["api10s"]
    assert census["crosswalk_api10s_with_two_lease_keys"] == EXPECTED["doubled"]
    assert census["crosswalk_lease_keys"] == EXPECTED["lease_keys"]
    assert census["crosswalk_lease_keys_in_scope"] == EXPECTED["in_scope"]
    assert census["districts_published"] == 15


def test_the_dump_states_its_own_window(loaded) -> None:
    assert loaded.window == ("202401", "202506")


def test_the_chain_reaches_the_manifest_that_names_the_archive(loaded, seeded) -> None:
    """Proof 1's terminal node: a share's handle resolves through the allocation, the lease
    row and the parse to a manifest whose acquisition_url names PDQ_DSV.zip."""
    url = scalar(
        seeded,
        "select acquisition_url from lineage.manifests where manifest_id = %s",
        (loaded.manifest_id,),
    )

    assert SOURCE_KEY in url


def test_a_second_vintage_appends_membership_and_removes_no_month(
    loaded, seeded, raw_root: Path, lineage_env
) -> None:
    """A later vintage that drops a well never removes it from months already resolved at an
    earlier one: nothing is retro-deleted and history accretes forward."""
    before = scalar(seeded, "select count(*) from canonical.lease_membership")
    with lineage_session(
        recorder=PostgresRecorder(seeded), environment=lineage_env
    ), client_for(RESTATED) as client:
        second = tx_pdq.load(
            seeded,
            url=f"https://example.invalid/{SOURCE_KEY}",
            raw_root=raw_root,
            client=client,
            expect_bytes=RESTATED.stat().st_size,
        )
    seeded.commit()

    assert second.manifest_id != loaded.manifest_id
    assert scalar(seeded, "select count(*) from canonical.lease_membership") >= before
    assert scalar(
        seeded,
        "select count(*) from canonical.lease_membership where api10 = '4200300001'",
    ) >= 2


def test_a_membership_row_is_never_edited(loaded, seeded) -> None:
    with pytest.raises(psycopg.errors.RestrictViolation), seeded.cursor() as cursor:
        cursor.execute(
            "update canonical.lease_membership set link_role = 'filing_derived'"
        )
    seeded.rollback()
