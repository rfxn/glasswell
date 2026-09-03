"""The Texas registration is corrected by appending a registration, never by an edit.

Its founding row says Texas files at the lease, so no liquids basis and no grain decision are
registered and the API serves a disclosure instead of a series. That stops being true the day
the allocation ships. What is pinned here is what a renumber cannot change: that the new
registration resolves at the later clock, that it carried every rule row and every presentation
column of the one it supersedes, and that the row it supersedes still answers under its own
knowledge cut.
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import dict_row

from glasswell.db.migrate import discover_migrations
from glasswell.seed import seed_all
from glasswell.seed.jurisdictions import (
    PRESENTATION_COLUMNS,
    REGISTERED_ON,
    RESTATED_ON,
    TX_SUPERSEDED_EVIDENCE_COMMIT,
    TX_SUPERSEDED_EVIDENCE_TAG,
    TX_SUPERSEDED_ON,
    TX_SUPERSEDED_RULES,
)

pytestmark = pytest.mark.integration

MIGRATION = "tx_lease_production"


def resolved(connection: psycopg.Connection, knowledge, valid, code: str = "TX") -> dict:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select * from lineage.jurisdictions_as_of(%s, %s) where jurisdiction_code = %s",
            (knowledge, valid, code),
        )
        row = cursor.fetchone()
    assert row is not None, f"{code} resolves to no registration at {knowledge}"
    return row


def rules(connection: psycopg.Connection, row: dict) -> dict[str, str]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select decision, rule_id from lineage.jurisdiction_rules"
            " where jurisdiction_code = %s and effective_from = %s and published_at = %s"
            "   and serving",
            (row["jurisdiction_code"], row["effective_from"], row["published_at"]),
        )
        return {item["decision"]: item["rule_id"] for item in cursor.fetchall()}


def test_the_migration_is_found_by_its_suffix_and_never_by_a_number() -> None:
    found = [item for item in discover_migrations() if item.name.endswith(MIGRATION)]

    assert len(found) == 1
    assert found[0].path.name.endswith(f"_{MIGRATION}.sql")


def test_the_supersession_clock_is_later_than_every_clock_texas_already_carried() -> None:
    """It must resolve, and it must not land on either instant a standing gate plants a rival
    registration on: the partial unique indexes would refuse them."""
    assert TX_SUPERSEDED_ON > RESTATED_ON > REGISTERED_ON
    assert REGISTERED_ON.replace(day=REGISTERED_ON.day + 1) != TX_SUPERSEDED_ON
    assert RESTATED_ON.replace(day=RESTATED_ON.day + 1) != TX_SUPERSEDED_ON


def test_the_seeded_registration_serves_the_allocation_registration(
    db: psycopg.Connection,
) -> None:
    seed_all(db)

    row = resolved(db, TX_SUPERSEDED_ON, REGISTERED_ON)

    assert row["published_at"] == TX_SUPERSEDED_ON
    assert row["effective_from"] == REGISTERED_ON
    assert row["liquids_basis"] == "oil+condensate"
    assert "tx_pdq_dsv" in row["source_ids"]


def test_the_registration_it_supersedes_still_answers_under_its_own_knowledge_cut(
    db: psycopg.Connection,
) -> None:
    """lineage.jurisdictions is append-only, so an as_of before this train still resolves the
    registration that said Texas had no production and no liquids basis."""
    seed_all(db)

    before = resolved(db, RESTATED_ON, REGISTERED_ON)

    assert before["published_at"] == RESTATED_ON
    assert before["liquids_basis"] is None
    assert "tx_pdq_dsv" not in before["source_ids"]


def test_the_supersession_carries_every_presentation_column_forward(
    db: psycopg.Connection,
) -> None:
    """Dropping them would blank the Texas Wells row in the web legend, and nothing else in
    the suite would notice: the client reads the registry."""
    seed_all(db)

    before = resolved(db, RESTATED_ON, REGISTERED_ON)
    after = resolved(db, TX_SUPERSEDED_ON, REGISTERED_ON)

    assert all(after[column] is not None or before[column] is None
               for column in PRESENTATION_COLUMNS)
    for column in PRESENTATION_COLUMNS:
        assert after[column] == before[column]


def test_the_supersession_carries_the_five_decisions_it_inherits_and_adds_four(
    db: psycopg.Connection,
) -> None:
    """basin_scope and length_source are read by the seam's MartProfile engine for behaviour,
    so dropping either would silently remove Texas's lateral-length measurement and its basin
    CRS from the tile mart while the mart went on running."""
    seed_all(db)

    carried = rules(db, resolved(db, TX_SUPERSEDED_ON, REGISTERED_ON))

    assert carried["basin_scope"] == "cr_tx_basin_scope_1"
    assert carried["length_source"] == "cr_tx_length_source_1"
    assert carried["status_vocabulary"] == "cr_tx_status_vocab_1"
    assert carried["identity"] == "cr_tx_api10_build_1"
    assert carried["absence:operator"] == "cr_tx_operator_absence_1"
    assert carried["production_grain"] == "cr_tx_production_grain_1"
    assert carried["liquids"] == "cr_tx_liquids_basis_1"
    assert carried["geometry_provenance"] == "cr_tx_geometry_provenance_1"
    assert carried["cumulatives_scope"] == "cr_tx_allocation_v0_1"
    assert len(carried) == len(TX_SUPERSEDED_RULES) == 9


def test_texas_had_no_geometry_provenance_decision_before_this_track(
    db: psycopg.Connection,
) -> None:
    """The finding survives the registry: Texas resolved its provenance through a fallback,
    so a filed cartographic line could read as a survey-derived path."""
    seed_all(db)

    before = rules(db, resolved(db, RESTATED_ON, REGISTERED_ON))

    assert "geometry_provenance" not in before


def test_two_writers_land_exactly_one_registration(db: psycopg.Connection) -> None:
    """The migration and the seed both carry the supersession, on purpose: glasswell-migrate
    alone must yield a database that serves, and every deploy re-runs seed_all. Both writing
    it must still leave one row, or the registry would carry a duplicate at its own clock."""
    seed_all(db)
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.jurisdictions"
            " where jurisdiction_code = 'TX' and published_at = %s",
            (TX_SUPERSEDED_ON,),
        )
        assert cursor.fetchone()[0] == 1


def test_the_evidence_pair_is_repointed_in_one_place_or_in_none(
    db: psycopg.Connection,
) -> None:
    """The registration reads its pair back from the publication row, so a repoint that moved
    the registration without the rules is not expressible in the migration."""
    seed_all(db)

    row = resolved(db, TX_SUPERSEDED_ON, REGISTERED_ON)
    with db.cursor() as cursor:
        cursor.execute(
            "select evidence_tag, evidence_commit from lineage.conformance_rule_publications"
            " where rule_id = 'cr_tx_allocation_v0_1'"
        )
        published = cursor.fetchone()

    assert (row["evidence_tag"], row["evidence_commit"]) == published
    assert published == (TX_SUPERSEDED_EVIDENCE_TAG, TX_SUPERSEDED_EVIDENCE_COMMIT)


def test_the_nine_rules_seed_and_the_publication_evidence_admits_them(
    db: psycopg.Connection,
) -> None:
    """049's trigger refuses a rule whose publication is not registered, so the migration
    carries the evidence and the seeders carry the rules."""
    seed_all(db)
    with db.cursor() as cursor:
        cursor.execute(
            "select rule_id from lineage.conformance_rules where rule_id = any(%s)"
            " order by rule_id",
            ([
                "cr_tx_pdq_format_1", "cr_tx_pdq_scope_1", "cr_tx_production_grain_1",
                "cr_tx_pdq_crosswalk_1", "cr_tx_allocation_v0_1", "cr_alloc_v0_error_bounds_1",
                "cr_tx_liquids_basis_1", "cr_tx_gas_basis_1", "cr_tx_geometry_provenance_1",
            ],),
        )
        assert len(cursor.fetchall()) == 9


def test_the_superseded_disclosure_is_still_served(db: psycopg.Connection) -> None:
    """cr_tx_allocation_scope_1 is superseded, not deleted: any as_of before this train still
    resolves the disclosure the card used to show."""
    seed_all(db)
    with db.cursor() as cursor:
        cursor.execute(
            "select supersedes_rule_id from lineage.conformance_rules"
            " where rule_id = 'cr_tx_production_grain_1'"
        )
        assert cursor.fetchone()[0] == "cr_tx_allocation_scope_1"
        cursor.execute(
            "select count(*) from lineage.conformance_rules"
            " where rule_id = 'cr_tx_allocation_scope_1'"
        )
        assert cursor.fetchone()[0] == 1
