from __future__ import annotations

import psycopg
import pytest

from glasswell.modeling.feature_matrix import load_feature_specs
from glasswell.seed.features import FEATURE_SPECS

INSERT = """
insert into features.feature_specs
    (feature_id, family, dtype, unit, knowable_at_rule, publication_lag_days_p50,
     transform_id, source_refs, missing_policy, member_of, introduced_in_fv)
values
    ('geology.registry_test', 'geology', 'categorical', 'category', 'completion_date', 0,
     'lookup_formation_alias', array['canonical.well_completions',
                                     'cr_formation_group_rollup'],
     'native_nan', array['full', 'rock_location_only'], 'fv1.0')
"""


def test_feature_specs_are_append_only(db):
    with db.cursor() as cursor:
        cursor.execute(INSERT)
    db.commit()

    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"):
        with db.cursor() as cursor:
            cursor.execute(
                "update features.feature_specs set unit = 'text' "
                "where feature_id = 'geology.registry_test'"
            )
    db.rollback()


def test_a_terminal_successor_retires_without_rewriting_the_prior_spec(db):
    with db.cursor() as cursor:
        cursor.execute(INSERT)
        cursor.execute(
            "insert into features.feature_specs "
            "(feature_id, family, dtype, unit, knowable_at_rule, publication_lag_days_p50, "
            "transform_id, params, source_refs, missing_policy, member_of, introduced_in_fv, "
            "retired_in_fv) "
            "select feature_id, family, dtype, unit, knowable_at_rule, "
            "publication_lag_days_p50, transform_id, params, source_refs, missing_policy, "
            "member_of, 'fv1.1', 'fv1.1' "
            "from features.feature_specs where feature_id = 'geology.registry_test'"
        )
        cursor.execute(
            "select introduced_in_fv, retired_in_fv from features.feature_specs "
            "where feature_id = 'geology.registry_test' order by introduced_in_fv"
        )
        rows = cursor.fetchall()

    assert rows == [("fv1.0", None), ("fv1.1", "fv1.1")]


def test_feature_family_must_match_the_slug_prefix(db):
    mismatched = INSERT.replace(
        "'geology.registry_test', 'geology'", "'geology.registry_test', 'design'"
    )

    with pytest.raises(psycopg.errors.CheckViolation):
        with db.cursor() as cursor:
            cursor.execute(mismatched)
    db.rollback()


def test_runtime_role_grants_match_the_registry_boundary(db):
    checks = [
        ("glasswell_pipeline", "SELECT", True),
        ("glasswell_pipeline", "INSERT", True),
        ("glasswell_pipeline", "UPDATE", False),
        ("glasswell_pipeline", "DELETE", False),
        ("glasswell_api", "SELECT", True),
        ("glasswell_api", "INSERT", False),
        ("glasswell_api", "UPDATE", False),
        ("glasswell_api", "DELETE", False),
    ]
    with db.cursor() as cursor:
        actual = []
        for role, privilege, expected in checks:
            cursor.execute(
                "select has_table_privilege(%s, 'features.feature_specs', %s)",
                (role, privilege),
            )
            actual.append((role, privilege, cursor.fetchone()[0], expected))

    assert [(role, privilege, granted) for role, privilege, granted, _ in actual] == [
        (role, privilege, expected) for role, privilege, _, expected in actual
    ]


def test_fv1_registry_row_matches_the_checked_in_declaration(db):
    assert load_feature_specs(db) == FEATURE_SPECS
