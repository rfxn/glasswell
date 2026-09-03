"""The neighbour mart's keys stop naming North Dakota, without stopping being intra-state.

Migration 045 wrote `^33` into three checks, so no second state could be represented at all.
Widening them is prophylactic for New Mexico — neither NM source ships a lateral, so no NM edge
can be built — and load-bearing for the deferred spacing figures and for Montana. It lands
before any non-ND row because a served figure built under the narrow constraint would have to
be restated, and a restatement is a much more expensive apology than a migration.

The invariant that must *survive* the widening is the one this file spends most of its
assertions on: an edge is intra-state, because the distance is measured in a UTM zone chosen
from the pair's own midpoint and that choice is undefined across an arbitrary state pair.
"""

from __future__ import annotations

from datetime import date

import psycopg
import pytest

from glasswell.seed import seed_all
from glasswell.seed.jurisdictions import PREFIXES, REGISTERED_ON, RESTATED_ON
from tests.support.seed import seed_derivation

pytestmark = pytest.mark.integration

VINTAGE = date(2026, 8, 1)
ND = ("3305300001", "3305300002")
NM = ("3001512345", "3001512346")


@pytest.fixture
def derivation(db: psycopg.Connection, lineage_env) -> str:
    return seed_derivation(db, operation="mart.refresh")


def subject(db: psycopg.Connection, api10: str, derivation_id: str) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "insert into marts.nd_neighbor_subjects (api10, formation_status, formation_pools,"
            " formation_month, formation_id, formation_group, lateral_component_count,"
            " snapshot_vintage, derivation_id)"
            " values (%s, 'mapped', array['BAKKEN'], %s, 'bakken', 'bakken', 1, %s, %s)",
            (api10, VINTAGE, VINTAGE, derivation_id),
        )


def edge(db: psycopg.Connection, api10: str, neighbor: str, derivation_id: str) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "insert into marts.nd_neighbor_edges (api10, neighbor_api10, distance_m,"
            " distance_epsg, subject_geom_key, neighbor_geom_key, snapshot_vintage,"
            " derivation_id)"
            " values (%s, %s, 500.000, 32613, 'k1', 'k2', %s, %s)",
            (api10, neighbor, VINTAGE, derivation_id),
        )


def test_a_new_mexico_subject_is_representable(db: psycopg.Connection, derivation: str) -> None:
    subject(db, NM[0], derivation)

    with db.cursor() as cursor:
        cursor.execute("select api10 from marts.nd_neighbor_subjects")
        assert [row[0] for row in cursor.fetchall()] == [NM[0]]


def test_a_new_mexico_edge_is_representable(db: psycopg.Connection, derivation: str) -> None:
    for api10 in NM:
        subject(db, api10, derivation)

    edge(db, NM[0], NM[1], derivation)

    with db.cursor() as cursor:
        cursor.execute("select count(*) from marts.nd_neighbor_edges")
        assert cursor.fetchone()[0] == 1


def test_north_dakota_is_unchanged_by_the_widening(db: psycopg.Connection, derivation: str):
    for api10 in ND:
        subject(db, api10, derivation)

    edge(db, ND[0], ND[1], derivation)

    with db.cursor() as cursor:
        cursor.execute("select count(*) from marts.nd_neighbor_edges")
        assert cursor.fetchone()[0] == 1


def test_an_edge_that_crosses_a_state_line_is_representable(
    db: psycopg.Connection, derivation: str
) -> None:
    """066 lifted the intra-state restriction this test used to assert. It was there because a
    pair-local UTM zone had no defined answer off the two ND zones; the distance_epsg constraint
    now bounds that answer, and a cross-border edge is the ND/MT repair's whole point."""
    subject(db, ND[0], derivation)
    subject(db, NM[0], derivation)

    edge(db, ND[0], NM[0], derivation)


@pytest.mark.parametrize("malformed", ["3312345", "abc", "33053000012", "33-0530-0001"])
def test_a_malformed_api10_is_still_refused(
    db: psycopg.Connection, derivation: str, malformed: str
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        subject(db, malformed, derivation)


def test_no_migration_still_pins_the_north_dakota_prefix_on_these_tables(
    db: psycopg.Connection,
) -> None:
    """Asserted against the database rather than by grepping the migration directory: what
    matters is the constraint that is installed, not the file that installed it."""
    with db.cursor() as cursor:
        cursor.execute(
            "select pg_get_constraintdef(oid) from pg_constraint"
            " where conrelid in ('marts.nd_neighbor_subjects'::regclass,"
            "                    'marts.nd_neighbor_edges'::regclass)"
            "   and contype = 'c'"
        )
        definitions = " ".join(row[0] for row in cursor.fetchall())

    assert "^33" not in definitions
    # 066 lifted it: an edge across the ND/MT line is the repair, not a violation. Asserted
    # absent rather than deleted, so re-adding the restriction reddens here.
    assert "left(api10, 2) = left(neighbor_api10, 2)" not in definitions.replace('"', "")


def test_the_refresh_binds_a_state_tuple_rather_than_a_literal() -> None:
    """The seam is a bind, not a literal. Which jurisdictions fill it is two registrations
    now -- `neighbors_available` and a serving `neighbors_scope` rule -- rather than a tuple
    pinned here, so this asserts the binding and leaves the membership to the registry."""
    from glasswell.marts import neighbors

    assert "%(state_code)s" not in neighbors._COMPONENTS
    assert "any(%(state_codes)s)" in neighbors._COMPONENTS
    assert set(neighbors.STATE_CODES) <= PREFIXES


def test_the_resident_subject_list_is_the_one_the_derivation_param_already_carried(
    db: psycopg.Connection,
) -> None:
    """The pin that matters: `state_codes` is inside `hash_payload(params)`, so a subject list
    resolved from the registry has to be byte-identical to the tuple it replaced or
    `marts.nd_neighbors` moves address for a naming property."""
    from glasswell.lineage.jurisdictions import clear_jurisdiction_cache, load_jurisdictions
    from glasswell.marts import neighbors

    seed_all(db)
    clear_jurisdiction_cache()
    registry = load_jurisdictions(db)

    assert neighbors.subject_prefixes(registry) == ("33", "25")
    assert neighbors.excluded_prefixes(registry) == ()


def test_a_registration_the_measured_domain_does_not_reach_is_excluded_not_an_outlier(
    db: psycopg.Connection,
) -> None:
    """The failure this closes: a fifth jurisdiction registered neighbours-available outside
    the envelope was a subject, was counted as an outlier, and aborted the whole monthly run
    with a message beginning "ND neighbour geometry falls outside" while reporting its well."""
    from glasswell.lineage.jurisdictions import clear_jurisdiction_cache, load_jurisdictions
    from glasswell.marts import neighbors

    seed_all(db)
    _register_out_of_domain(db)
    clear_jurisdiction_cache()
    registry = load_jurisdictions(db)

    assert neighbors.subject_prefixes(registry) == ("33", "25")
    assert neighbors.excluded_prefixes(registry) == ("49",)


def test_a_registration_that_does_claim_the_domain_and_leaves_it_still_raises(
    db: psycopg.Connection,
) -> None:
    """Excluding by absence must not become excusing by absence: a jurisdiction that registers
    neighbors_scope and whose geometry still leaves the envelope is a measurement that has
    stopped being true, and the refusal names it."""
    from glasswell.lineage.jurisdictions import clear_jurisdiction_cache, load_jurisdictions
    from glasswell.marts import neighbors

    seed_all(db)
    _register_out_of_domain(db, with_scope_rule=True)
    clear_jurisdiction_cache()
    registry = load_jurisdictions(db)

    assert "49" in neighbors.subject_prefixes(registry)


def test_the_python_envelope_and_the_migration_constraint_name_the_same_zones() -> None:
    """R-7. The zone set is a tuple in Python and a CHECK in 066; two spellings of one
    measurement drift the first time one of them is widened alone."""
    from glasswell.db.migrate import discover_migrations
    from glasswell.marts import neighbors

    body = next(
        item.sql for item in discover_migrations() if item.name == "neighbors_multistate"
    )
    declared = ", ".join(str(epsg) for epsg in neighbors.SUPPORTED_ZONE_EPSGS)

    assert f"distance_epsg in ({declared})" in body
    assert str(neighbors.SUPPORTED_LONGITUDE_MIN) in body
    assert str(neighbors.SUPPORTED_LONGITUDE_MAX) in body


def _register_out_of_domain(db: psycopg.Connection, *, with_scope_rule: bool = False) -> None:
    """A fifth registration that is neighbours-available and outside both bounds: Wyoming's
    prefix, west of the longitude floor is not the point -- it is south of 44.30 and its
    midpoint zone is 32613, so it exercises the envelope arm."""
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.jurisdiction_codes values ('WY', 'state')"
            " on conflict do nothing"
        )
        cursor.execute(
            "insert into lineage.jurisdictions (jurisdiction_code, effective_from,"
            " published_at, evidence_tag, evidence_commit, name, regulator_name,"
            " regulator_url, identity_scheme, identity_prefix, identity_pattern, source_ids,"
            " rationale, neighbors_available)"
            " values ('WY', %s, %s, 'v0.77', %s, 'Wyoming', 'WOGCC',"
            " 'https://wogcc.wyo.gov', 'api10', '49', '^49[0-9]{8}$',"
            " array['nd_mpr_xlsx'], 'planted', true)",
            # Valid from the founding instant, published at the restatement's: a future
            # effective_from resolves no registration, which the loader reads as absent.
            (REGISTERED_ON, RESTATED_ON, "a" * 40),
        )
        if with_scope_rule:
            cursor.execute(
                "insert into lineage.jurisdiction_rules (jurisdiction_code, effective_from,"
                " published_at, decision, rule_id)"
                " values ('WY', %s, %s, 'neighbors_scope', 'cr_nd_neighbors_scope_1')",
                (REGISTERED_ON, RESTATED_ON),
            )
