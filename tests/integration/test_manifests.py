from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from glasswell.lineage.errors import ManifestConflict
from glasswell.lineage.manifests import manifest_chain, register_manifest

NIGHTLY_KEY = "wcproduction.zip"
FIRST_PULL = datetime(2026, 8, 1, 5, 2, 11, tzinfo=UTC)
SECOND_PULL = datetime(2026, 8, 2, 5, 2, 11, tzinfo=UTC)


def register(
    db, sha256, *, fetched_at=FIRST_PULL, source_key=NIGHTLY_KEY, source_id="nm_ocd_wcproduction"
):
    return register_manifest(
        db,
        sha256=sha256,
        size_bytes=3812345678,
        source_id=source_id,
        source_key=source_key,
        acquisition_url=f"ftp://164.64.106.6/{source_key}",
        acquisition_method="ftp_anon",
        acquisition_params={"host": "164.64.106.6", "ftp_size": 3812345678},
        fetched_at=fetched_at,
        storage_uri=f"/data/raw/nm_ocd_wcproduction/{source_key}",
        correlation_id="run_nm_nightly",
    )


def event_types(db, subject_id):
    with db.cursor() as cursor:
        cursor.execute(
            "select event_type from lineage.audit_events where subject_id = %s order by event_id",
            (subject_id,),
        )
        return [row[0] for row in cursor.fetchall()]


def test_a_first_fetch_creates_a_manifest_and_records_the_event(db):
    registration = register(db, "a" * 64)
    db.commit()

    assert registration.created is True
    assert registration.superseded_manifest_id is None
    assert registration.manifest.manifest_id == "man_" + "a" * 32
    assert registration.manifest.fetch_vintage == date(2026, 8, 1)
    assert event_types(db, registration.manifest.manifest_id) == ["raw.manifest_created"]


def test_identical_bytes_are_a_recorded_no_op(db):
    first = register(db, "a" * 64)
    db.commit()
    second = register(db, "a" * 64, fetched_at=SECOND_PULL)
    db.commit()

    assert second.created is False
    assert second.manifest.manifest_id == first.manifest.manifest_id
    assert second.manifest.fetched_at == first.manifest.fetched_at

    with db.cursor() as cursor:
        cursor.execute("select count(*) from lineage.manifests")
        assert cursor.fetchone() == (1,)
    assert event_types(db, first.manifest.manifest_id) == [
        "raw.manifest_created",
        "raw.fetch_verified_unchanged",
    ]


def test_changed_bytes_under_the_same_source_key_supersede_the_head(db):
    first = register(db, "a" * 64)
    db.commit()
    second = register(db, "b" * 64, fetched_at=SECOND_PULL)
    db.commit()

    assert second.created is True
    assert second.superseded_manifest_id == first.manifest.manifest_id
    assert second.manifest.supersedes_manifest_id == first.manifest.manifest_id
    assert "raw.manifest_superseded" in event_types(db, first.manifest.manifest_id)


def test_the_same_bytes_under_a_different_source_key_are_refused(db):
    """`sha256` is unique, so the schema cannot hold one payload in two slots. Returning the
    incumbent's manifest would hand the second slot the first slot's provenance — a handle that
    resolves, confidently, to the wrong government file (F8)."""
    first = register(db, "a" * 64)
    db.commit()

    with pytest.raises(ManifestConflict) as refusal:
        register(db, "a" * 64, source_key="wcwell.zip")

    assert first.manifest.source_key in str(refusal.value)
    assert "wcwell.zip" in str(refusal.value)


def test_the_same_bytes_under_a_different_source_id_are_refused(db):
    """The zero-byte trigger's shape: two slots of one multi-slot source are one `source_key`
    apart, two sources are one `source_id` apart, and both must refuse."""
    register(db, "a" * 64)
    db.commit()

    with pytest.raises(ManifestConflict):
        register(db, "a" * 64, source_id="nd_gis_wells")


def test_a_refused_conflict_leaves_the_incumbent_manifest_untouched(db):
    first = register(db, "a" * 64)
    db.commit()

    with pytest.raises(ManifestConflict):
        register(db, "a" * 64, source_key="wcwell.zip", fetched_at=SECOND_PULL)
    db.rollback()

    with db.cursor() as cursor:
        cursor.execute(
            "select source_key, fetched_at from lineage.manifests where sha256 = %s",
            ("a" * 64,),
        )
        assert cursor.fetchone() == (NIGHTLY_KEY, FIRST_PULL)
        cursor.execute("select count(*) from lineage.manifests")
        assert cursor.fetchone() == (1,)
    assert first.manifest.source_key == NIGHTLY_KEY


def test_the_head_view_returns_only_the_newest_manifest_per_slot(db):
    register(db, "a" * 64)
    second = register(db, "b" * 64, fetched_at=SECOND_PULL)
    other_slot = register(db, "c" * 64, source_key="wcwell.zip")
    db.commit()

    with db.cursor() as cursor:
        cursor.execute("select manifest_id from lineage.manifest_head order by source_key")
        heads = [row[0] for row in cursor.fetchall()]
    assert heads == [second.manifest.manifest_id, other_slot.manifest.manifest_id]


def test_the_supersession_chain_is_walkable_newest_first(db):
    first = register(db, "a" * 64)
    second = register(db, "b" * 64, fetched_at=SECOND_PULL)
    third = register(db, "c" * 64, fetched_at=datetime(2026, 8, 3, tzinfo=UTC))
    db.commit()

    assert manifest_chain(db, third.manifest.manifest_id) == [
        third.manifest.manifest_id,
        second.manifest.manifest_id,
        first.manifest.manifest_id,
    ]


def test_a_prior_manifest_is_never_rewritten_by_its_successor(db):
    first = register(db, "a" * 64)
    db.commit()
    register(db, "b" * 64, fetched_at=SECOND_PULL)
    db.commit()

    with db.cursor() as cursor:
        cursor.execute(
            "select sha256, fetched_at, supersedes_manifest_id from lineage.manifests"
            " where manifest_id = %s",
            (first.manifest.manifest_id,),
        )
        assert cursor.fetchone() == ("a" * 64, FIRST_PULL, None)
