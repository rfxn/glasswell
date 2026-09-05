"""The blank-is-absent column set, held to the table it is a set over.

gate-cofix L-1. `SOURCE_REPORTED_TEXT_COLUMNS` decides which reads apply the rule, and its
membership was prose: the module said why `basin` and `land_unit_label` are out and said
nothing about `ndic_file_no`, which is as source-reported as the six that are in. A set whose
completeness nobody can check is a set that goes stale the next time a text column lands on
the spine.
"""

from __future__ import annotations

import psycopg
import pytest

from glasswell.absence import NOT_SOURCE_REPORTED, SOURCE_REPORTED_TEXT_COLUMNS

pytestmark = pytest.mark.integration


def test_every_text_column_of_the_spine_is_classified_by_one_of_the_two_sets(
    db: psycopg.Connection,
) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "select column_name from information_schema.columns"
            " where table_schema = 'canonical' and table_name = 'wells'"
            "   and data_type = 'text'"
        )
        columns = {row[0] for row in cursor.fetchall()}

    assert columns == set(SOURCE_REPORTED_TEXT_COLUMNS) | set(NOT_SOURCE_REPORTED)
    assert not set(SOURCE_REPORTED_TEXT_COLUMNS) & set(NOT_SOURCE_REPORTED)
