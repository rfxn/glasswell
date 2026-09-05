"""marts.well_basin_context's shape: what the migration guarantees about every row.

The classes are constrained in the table rather than only in the writer, because the whole
point of the column is that an absence carries a reason, and a check constraint is the only
thing that keeps a null from arriving without one.
"""

from __future__ import annotations

import psycopg
import pytest

from tests.support.seed import seed_derivation

pytestmark = pytest.mark.integration

MART = "marts.well_basin_context"


def columns(connection: psycopg.Connection) -> dict[str, tuple[str, str]]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select column_name, data_type, is_nullable from information_schema.columns"
            " where table_schema = 'marts' and table_name = 'well_basin_context'"
        )
        return {name: (kind, nullable) for name, kind, nullable in cursor.fetchall()}


def insert(connection: psycopg.Connection, **overrides: object) -> None:
    derivation = seed_derivation(connection, operation="mart.refresh")
    with connection.cursor() as cursor:
        row = {
            "api10": "3305310451",
            "state_code": "33",
            "basin_name": "WILLISTON",
            "basin_class": "in_published_boundary",
            "basin_overlap": 1,
            "play_name": ["BAKKEN"],
            "play_class": "plays",
            "basin_label_filed": "williston",
            "label_class": "agrees",
            "label_agrees": True,
            "boundary_vintage": "2024",
            "geometry_basis": "surface",
            "derivation_id": derivation,
            **overrides,
        }
        cursor.execute(
            f"insert into {MART} (api10, state_code, basin_name, basin_class, basin_overlap,"
            " play_name, play_class, basin_label_filed, label_class, label_agrees,"
            " boundary_vintage, geometry_basis, derivation_id)"
            " values (%(api10)s, %(state_code)s, %(basin_name)s, %(basin_class)s,"
            " %(basin_overlap)s, %(play_name)s, %(play_class)s, %(basin_label_filed)s,"
            " %(label_class)s, %(label_agrees)s, %(boundary_vintage)s, %(geometry_basis)s,"
            " %(derivation_id)s)",
            row,
        )


def test_the_mart_carries_every_field_the_section_reads(db: psycopg.Connection) -> None:
    found = columns(db)
    for name in (
        "api10",
        "state_code",
        "basin_name",
        "basin_class",
        "basin_overlap",
        "play_name",
        "play_class",
        "basin_label_filed",
        "label_class",
        "label_agrees",
        "boundary_vintage",
        "geometry_basis",
        "boundary_id",
        "rule_id",
        "derivation_id",
    ):
        assert name in found, name
    # The plural one is an array, because plays stack and picking one would be a claim.
    assert found["play_name"][0] == "ARRAY"
    # And the classes are never null: an absence has to carry its reason.
    for name in ("basin_class", "play_class", "label_class", "geometry_basis"):
        assert found[name][1] == "NO", name


def test_a_basin_name_without_the_class_that_admits_one_is_refused(
    db: psycopg.Connection,
) -> None:
    # The pair is constrained, so no row can serve a name under `outside_published_boundaries`
    # and no row can serve `in_published_boundary` with nothing in it.
    with pytest.raises(psycopg.errors.CheckViolation):
        insert(db, basin_class="outside_published_boundaries")
    db.rollback()
    with pytest.raises(psycopg.errors.CheckViolation):
        insert(db, basin_name=None)


def test_an_agreement_verdict_without_two_things_to_compare_is_refused(
    db: psycopg.Connection,
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        insert(db, label_class="not_labelled", basin_label_filed=None, label_agrees=True)
    db.rollback()
    with pytest.raises(psycopg.errors.CheckViolation):
        insert(db, label_class="agrees", label_agrees=None)


def test_a_class_nobody_registered_is_refused(db: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        insert(db, basin_class="probably_permian")
    db.rollback()
    with pytest.raises(psycopg.errors.CheckViolation):
        insert(db, geometry_basis="vibes")


def test_one_row_per_well_and_the_api_may_read_it(db: psycopg.Connection) -> None:
    insert(db)
    with pytest.raises(psycopg.errors.UniqueViolation):
        insert(db)
    db.rollback()
    with db.cursor() as cursor:
        cursor.execute(
            "select has_table_privilege('glasswell_api', %s, 'select'),"
            "       has_table_privilege('glasswell_api', %s, 'insert')",
            (MART, MART),
        )
        readable, writable = cursor.fetchone()
    assert readable is True
    assert writable is False
