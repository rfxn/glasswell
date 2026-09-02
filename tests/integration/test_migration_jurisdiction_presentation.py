"""The presentation migration: seven columns, four appended restatements, and the new rules.

Discovered by suffix rather than by number: the integrator assigns the digits at the merge
train, so nothing here spells one. What is pinned is the behaviour a renumber cannot change --
that the restatement resolves at the later clock, that its rule rows were re-appended with it,
that the founding registration still answers under its own knowledge cut, and that a second
apply on the same day raises instead of being quietly absorbed.
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import dict_row

from glasswell.db.migrate import discover_migrations
from glasswell.seed import seed_all
from glasswell.seed.jurisdictions import (
    JURISDICTION_RESTATEMENTS,
    JURISDICTION_RULES,
    JURISDICTION_RULES_AS_FOUNDED,
    JURISDICTIONS,
    PRESENTATION_COLUMNS,
    REGISTERED_ON,
    RESTATED_EVIDENCE_COMMIT,
    RESTATED_EVIDENCE_TAG,
    RESTATED_ON,
    TRACK_RULE_IDS,
)

pytestmark = pytest.mark.integration

MIGRATION = "jurisdiction_presentation"


def migration(name: str):
    return next(item for item in discover_migrations() if item.name == name)


def resolved(connection: psycopg.Connection, knowledge, valid) -> list[dict]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select * from lineage.jurisdictions_as_of(%s, %s) order by jurisdiction_code",
            (knowledge, valid),
        )
        return cursor.fetchall()


def test_the_migration_is_found_by_its_suffix_and_never_by_a_number() -> None:
    """The number is the integrator's; the suffix is this track's."""
    found = [item for item in discover_migrations() if item.name.endswith(MIGRATION)]

    assert len(found) == 1
    assert found[0].path.name.endswith(f"_{MIGRATION}.sql")


def test_the_restatement_resolves_and_carries_the_presentation_columns(
    db: psycopg.Connection,
) -> None:
    rows = {row["jurisdiction_code"]: row for row in resolved(db, RESTATED_ON, RESTATED_ON)}

    assert sorted(rows) == ["MT", "ND", "NM", "TX"]
    for declared in JURISDICTIONS:
        landed = rows[str(declared["jurisdiction_code"])]
        assert landed["published_at"] == RESTATED_ON
        for column in PRESENTATION_COLUMNS:
            expected = declared[column]
            assert landed[column] == (
                list(expected) if isinstance(expected, tuple) else expected
            ), f"{landed['jurisdiction_code']}.{column}"


def test_the_founding_registration_still_answers_under_its_own_knowledge_cut(
    db: psycopg.Connection,
) -> None:
    """A restatement is an append. What was published on the founding day did not change."""
    rows = {row["jurisdiction_code"]: row for row in resolved(db, REGISTERED_ON, REGISTERED_ON)}

    assert sorted(rows) == ["MT", "ND", "NM", "TX"]
    for code, row in rows.items():
        assert row["published_at"] == REGISTERED_ON
        assert row["wells_layer_id"] is None, code


def test_the_restatement_is_published_strictly_later_than_every_founding_row(
    db: psycopg.Connection,
) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "select min(published_at), max(published_at) from lineage.jurisdictions"
        )
        earliest, latest = cursor.fetchone()

    assert earliest == REGISTERED_ON
    assert latest == RESTATED_ON
    assert RESTATED_ON > REGISTERED_ON


def test_a_second_apply_on_the_same_day_raises_instead_of_being_absorbed(
    db: psycopg.Connection,
) -> None:
    """M-15. `on conflict do nothing` is deliberately absent: a clock that was not repointed
    would otherwise land nothing, report success, and leave all seven columns null."""
    with db.cursor() as cursor, pytest.raises(psycopg.errors.UniqueViolation):
        cursor.execute(migration(MIGRATION).sql)


def test_every_rule_this_track_registers_carries_publication_evidence(
    db: psycopg.Connection,
) -> None:
    """A conformance rule cannot be seeded before its publication row exists (049), so the
    migration writes the evidence and the seed writes the rules."""
    with db.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select rule_id, evidence_tag, evidence_commit"
            "  from lineage.conformance_rule_publications where rule_id = any(%s)",
            (list(TRACK_RULE_IDS),),
        )
        rows = cursor.fetchall()

    assert sorted(row["rule_id"] for row in rows) == sorted(TRACK_RULE_IDS)
    assert {(row["evidence_tag"], row["evidence_commit"]) for row in rows} == {
        (RESTATED_EVIDENCE_TAG, RESTATED_EVIDENCE_COMMIT)
    }


def test_the_registration_and_its_rules_read_one_evidence_pair(
    db: psycopg.Connection,
) -> None:
    """The pair is written once and read back, so a half-repoint is not expressible."""
    with db.cursor() as cursor:
        cursor.execute(
            "select distinct evidence_tag, evidence_commit from lineage.jurisdictions"
            " where published_at = %s",
            (RESTATED_ON,),
        )
        assert cursor.fetchall() == [(RESTATED_EVIDENCE_TAG, RESTATED_EVIDENCE_COMMIT)]


def test_length_scope_still_resolves_to_montana_alone(
    db: psycopg.Connection,
) -> None:
    """M-14. The serving path reads the *existence* of a length_scope rule as `withheld`, so
    registering one for North Dakota would have deleted its lateral length from the card."""
    seed_all(db)
    with db.cursor() as cursor:
        cursor.execute(
            "select distinct jurisdiction_code from lineage.jurisdiction_rules"
            " where decision = 'length_scope' and serving"
        )
        assert [row[0] for row in cursor.fetchall()] == ["MT"]
        cursor.execute(
            "select rule_id from lineage.jurisdiction_rules"
            " where decision = 'length_scope' and published_at = %s",
            (RESTATED_ON,),
        )
        assert cursor.fetchone()[0] == "cr_mt_paths_length_scope_2"


def test_which_source_governs_a_length_is_its_own_decision(
    db: psycopg.Connection,
) -> None:
    seed_all(db)
    with db.cursor() as cursor:
        cursor.execute(
            "select jurisdiction_code, rule_id from lineage.jurisdiction_rules"
            " where decision = 'length_source' and published_at = %s"
            " order by jurisdiction_code",
            (RESTATED_ON,),
        )
        assert cursor.fetchall() == [
            ("ND", "cr_nd_length_source_1"),
            ("TX", "cr_tx_length_source_1"),
        ]


def test_the_restatement_re_appends_every_rule_row_it_declares(
    db: psycopg.Connection,
) -> None:
    """Gate (b)'s migration-side twin: a restatement states what was known when it was
    published, so its rule rows travel with it or the registration claims fewer decisions."""
    seed_all(db)
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.jurisdiction_rules where published_at = %s",
            (RESTATED_ON,),
        )
        assert cursor.fetchone()[0] == len(JURISDICTION_RULES)
        cursor.execute(
            "select count(*) from lineage.jurisdiction_rules where published_at = %s",
            (REGISTERED_ON,),
        )
        assert cursor.fetchone()[0] == len(JURISDICTION_RULES_AS_FOUNDED)


def test_the_migration_and_the_seed_write_the_same_restatements(
    db: psycopg.Connection,
) -> None:
    """Two writers, one truth. The migration derives its values from the founding rows and the
    seed states them, so this is the gate that holds the two spellings together."""
    columns = ", ".join(
        ("jurisdiction_code", "effective_from", "published_at", *PRESENTATION_COLUMNS)
    )
    with db.cursor() as cursor:
        cursor.execute(f"select {columns} from lineage.jurisdictions order by 1, 2, 3")
        from_migration = cursor.fetchall()
    db.rollback()

    seed_all(db)
    with db.cursor() as cursor:
        cursor.execute(f"select {columns} from lineage.jurisdictions order by 1, 2, 3")
        from_seed = cursor.fetchall()

    assert from_migration == from_seed
    assert len(from_seed) == len(JURISDICTIONS) + len(JURISDICTION_RESTATEMENTS)


def test_two_registrations_cannot_claim_one_draw_order_at_one_instant(
    db: psycopg.Connection,
) -> None:
    """The order is a real per-row integer -- disposal-wells sits between ND and TX -- so two
    jurisdictions claiming one slot is a silent overdraw on the canvas."""
    with db.cursor() as cursor:
        cursor.execute("insert into lineage.jurisdiction_codes values ('CO', 'state')")
        with pytest.raises(psycopg.errors.UniqueViolation):
            cursor.execute(
                "insert into lineage.jurisdictions (jurisdiction_code, effective_from,"
                " published_at, evidence_tag, evidence_commit, name, regulator_name,"
                " regulator_url, identity_scheme, identity_prefix, identity_pattern,"
                " source_ids, rationale, wells_layer_id, wells_style_layer_ids,"
                " wells_draw_order)"
                " values ('CO', %s, %s, 'v0.77', %s, 'Colorado', 'ECMC',"
                " 'https://ecmc.state.co.us', 'api10', '05', '^05[0-9]{8}$',"
                " array['nd_mpr_xlsx'], 'planted', 'co-wells',"
                " array['co-wells', 'co-wells-struck'], 40)",
                (REGISTERED_ON, RESTATED_ON, "a" * 40),
            )


def test_a_wells_row_names_its_style_layers_or_neither(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute("insert into lineage.jurisdiction_codes values ('CO', 'state')")
        with pytest.raises(psycopg.errors.CheckViolation):
            cursor.execute(
                "insert into lineage.jurisdictions (jurisdiction_code, effective_from,"
                " published_at, evidence_tag, evidence_commit, name, regulator_name,"
                " regulator_url, identity_scheme, identity_prefix, identity_pattern,"
                " source_ids, rationale, wells_layer_id)"
                " values ('CO', %s, %s, 'v0.77', %s, 'Colorado', 'ECMC',"
                " 'https://ecmc.state.co.us', 'api10', '05', '^05[0-9]{8}$',"
                " array['nd_mpr_xlsx'], 'planted', 'co-wells')",
                (RESTATED_ON, RESTATED_ON, "a" * 40),
            )


def test_a_subtitle_template_that_cannot_carry_a_count_is_refused(
    db: psycopg.Connection,
) -> None:
    """No naked numbers, and no place to put the measured one either: the template is the
    contract that the census fills it at render time rather than a constant being baked."""
    with db.cursor() as cursor:
        cursor.execute("insert into lineage.jurisdiction_codes values ('CO', 'state')")
        with pytest.raises(psycopg.errors.CheckViolation):
            cursor.execute(
                "insert into lineage.jurisdictions (jurisdiction_code, effective_from,"
                " published_at, evidence_tag, evidence_commit, name, regulator_name,"
                " regulator_url, identity_scheme, identity_prefix, identity_pattern,"
                " source_ids, rationale, wells_subtitle_template)"
                " values ('CO', %s, %s, 'v0.77', %s, 'Colorado', 'ECMC',"
                " 'https://ecmc.state.co.us', 'api10', '05', '^05[0-9]{8}$',"
                " array['nd_mpr_xlsx'], 'planted', 'ECMC surface locations')",
                (RESTATED_ON, RESTATED_ON, "a" * 40),
            )


def test_the_presentation_columns_reach_no_response_model() -> None:
    """N-17: they are read by the generator and by nothing else, so the OpenAPI snapshot and
    the naked-number allowlist are untouched by this track."""
    from glasswell.api.routers import jurisdictions as router

    served = set(router.MapPresentation.model_fields)

    assert served.isdisjoint(PRESENTATION_COLUMNS)
