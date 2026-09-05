"""`infra/verify.sh`'s four status assertions, executed against a database rather than stubbed.

Each of the four is the only check on the host that can see one defect class, and a query that
is never run against real rows is a check nobody has tested. So the SQL is read out of the
script itself, run on a seeded database, and then run again with the defect it exists for
planted: an assertion that passes on a broken fixture is worse than no assertion, because it
reports health.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from glasswell.seed import seed_all
from tests.support.jurisdictions import restate
from tests.support.seed import seed_statusless_well, seed_well

pytestmark = pytest.mark.integration

VERIFY = Path(__file__).resolve().parents[2] / "infra" / "verify.sh"
ASSERTIONS = (
    "unconstrained_maps",
    "untriggered_maps",
    "absence_over_share",
    "clock_gap",
    "rule_rows_lost",
)


@pytest.fixture
def seeded(db: psycopg.Connection) -> psycopg.Connection:
    """The registry as a deploy leaves it: migrations applied, then `seed_all`, which is what
    attaches the refresh triggers the second assertion is about."""
    seed_all(db)
    db.commit()
    return db


def statement(name: str) -> str:
    """The SQL one assertion runs, read where it is written: `name="$("${PSQL[@]}" "<sql>")"`."""
    text = VERIFY.read_text(encoding="utf-8")
    opening = f'{name}="$("${{PSQL[@]}}" "'
    start = text.index(opening) + len(opening)
    end = text.index('")"', start)
    return text[start:end]


def answer(connection: psycopg.Connection, name: str) -> str:
    with connection.cursor() as cursor:
        cursor.execute(statement(name))
        row = cursor.fetchone()
    return "" if row is None or row[0] is None else str(row[0])


def test_every_assertion_reads_a_query_this_file_can_find() -> None:
    """The extraction is part of the gate: a renamed variable would silently test nothing."""
    for name in ASSERTIONS:
        assert "select" in statement(name)


def test_a_healthy_database_answers_all_four_empty(seeded: psycopg.Connection) -> None:
    for name in ASSERTIONS:
        assert answer(seeded, name) == "", name


def test_v1_reddens_when_a_registered_map_stops_targeting_the_domain(
    seeded: psycopg.Connection,
) -> None:
    """The sixth-map case, planted on the fifth: without the foreign key the map can hold a
    class the domain never declared, and nothing else on the host would say so."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select conname from pg_constraint where conrelid = 'lineage.nd_status_map'::regclass"
            "   and contype = 'f' and confrelid = 'lineage.status_classes'::regclass"
        )
        constraint = cursor.fetchone()[0]
        cursor.execute(f"alter table lineage.nd_status_map drop constraint {constraint}")

    assert "nd_status_map" in answer(seeded, "unconstrained_maps")


def test_v2_reddens_on_the_gap_colorado_shipped_with(seeded: psycopg.Connection) -> None:
    """Measured on the deployed instance on 2026-09-03: three refresh triggers, none of them on
    lineage.co_facility_status_map, while the resolver held thirteen Colorado rows."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "drop trigger status_map_refresh_status_resolution"
            " on lineage.co_facility_status_map"
        )

    assert "co_facility_status_map" in answer(seeded, "untriggered_maps")


def test_v3_reddens_when_a_jurisdiction_serves_the_absence_class_past_its_share(
    seeded: psycopg.Connection,
) -> None:
    """The replacement for the null: after the absence arm a broken resolver draws grey rather
    than nothing, so the share is what says a jurisdiction stopped resolving."""
    classed = seed_well(seeded, api10="3344199000", state_code="33", status_canonical="active")
    for index in range(1, 5):
        seed_statusless_well(seeded, api10=f"334419900{index}", like=classed)

    assert answer(seeded, "absence_over_share").startswith("33 80.0%")


def test_v3_reddens_when_the_domain_declares_no_absence_class(
    seeded: psycopg.Connection,
) -> None:
    """The other half of the same check, and the reason it is worth its query: with no absence
    row the subselect every serving path shares resolves nothing and every well in every
    jurisdiction goes unclassed, which a share comparison alone would read as zero per cent.

    Planted through the append-only trigger rather than around it, because the state being
    reproduced is a database whose seed did not land the domain.
    """
    with seeded.cursor() as cursor:
        cursor.execute(
            "alter table lineage.status_classes disable trigger reject_status_classes_mutation"
        )
        cursor.execute("delete from lineage.status_classes where is_absence")
        cursor.execute(
            "alter table lineage.status_classes enable trigger reject_status_classes_mutation"
        )

    assert answer(seeded, "absence_over_share") == (
        "the class domain declares no single absence class"
    )


def test_v1_reddens_when_a_registered_view_loses_the_constraint_under_it(
    seeded: psycopg.Connection,
) -> None:
    """Montana registers a view over its map, and a view carries no foreign key, so the check
    has to resolve the relation that holds the rows or it reads a healthy host as broken and a
    broken one as healthy."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select conname from pg_constraint where conrelid = 'lineage.mt_status_map'::regclass"
            "   and contype = 'f' and confrelid = 'lineage.status_classes'::regclass"
        )
        constraint = cursor.fetchone()[0]
        cursor.execute(f"alter table lineage.mt_status_map drop constraint {constraint}")

    assert "mt_status_promoted_map" in answer(seeded, "unconstrained_maps")


def test_v4_reddens_when_the_resolver_was_built_at_another_clock(
    seeded: psycopg.Connection,
) -> None:
    """Facts 16 and 17: both halves are internally consistent when they disagree, so only a
    comparison finds it."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "update lineage.status_resolution_resolved"
            "   set knowledge_for = knowledge_for - interval '1 day'"
        )

    assert " against the registry's " in answer(seeded, "clock_gap")


def test_v4_reddens_when_a_jurisdiction_would_lose_a_rule_row_at_the_cut(
    seeded: psycopg.Connection,
) -> None:
    """The invariant M-15 asked for, rather than a date: a registration published after the
    resolver's cut declares rule rows the resolver's own registration does not carry."""
    restate(seeded, "NM", rules={"cumulatives_scope": "cr_nm_wcproduction_pool_rollup_2"})
    with seeded.cursor() as cursor:
        cursor.execute(
            "update lineage.status_resolution_resolved"
            "   set knowledge_for = (select min(published_at) from lineage.jurisdictions)"
        )

    assert "NM " in answer(seeded, "rule_rows_lost")
