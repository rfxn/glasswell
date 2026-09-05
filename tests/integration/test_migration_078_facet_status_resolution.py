"""The two costs a facet over every jurisdiction paid, and the rule that names the third.

`web/PERF.md` §7 is the measurement; this is the shape that measurement depends on. Both
assertions are about the plan the deployed database can reach, so both are written against a
relation and an index rather than against a timing, which no fixture can reproduce.
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg import sql

from glasswell.api.routers.facets import _FACETS, _SCOPED_LATEST, _VALUE_SORTS, DIMENSIONS
from glasswell.db.migrate import discover_migrations
from glasswell.seed import seed_all
from glasswell.seed.jurisdictions import REGISTERED_ON
from glasswell.status_resolution import resolver_rules
from tests.support.seed import seed_conformance_rule

pytestmark = pytest.mark.integration

FACET_INDEX = "wells_facet_dimensions_idx"


def migration_sql(name: str) -> str:
    """By name: the version integer is assigned by merge order and this file will be renumbered."""
    return next(item.sql for item in discover_migrations() if item.name == name)


def _indexdef(connection: psycopg.Connection, name: str) -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            "select pg_get_indexdef(c.oid) from pg_class c"
            " join pg_namespace n on n.oid = c.relnamespace"
            " where c.relname = %s and n.nspname = 'canonical'",
            (name,),
        )
        row = cursor.fetchone()
    assert row is not None, f"{name} is not present"
    return str(row[0])


def _status_facet_plan(connection: psycopg.Connection) -> str:
    """The exact statement `get_well_facets` emits for the one dimension that joins."""
    scoped = _SCOPED_LATEST.format(
        column=DIMENSIONS["status"]["column"], join=DIMENSIONS["status"].get("join", "")
    )
    statement = _FACETS.format(scoped=scoped, order=_VALUE_SORTS[("count", "desc")])
    with connection.cursor() as cursor:
        # A fixture holds tens of rows, where a sequential scan -- or a bitmap over two of
        # them -- is genuinely cheaper and the planner is right to take it. Turning both off is
        # what makes the assertions below claims about the index rather than about the
        # fixture's size. Neither is set on the serving path; at 809,191 rows the planner
        # reaches this plan on its own (web/PERF.md section 7).
        cursor.execute("set local enable_seqscan = off")
        cursor.execute("set local enable_bitmapscan = off")
        cursor.execute(
            f"explain {statement}",
            {"states": ["33", "42"], "as_of": None, "q": None, "top": 15},
        )
        return "\n".join(str(row[0]) for row in cursor.fetchall())


def test_the_covering_index_carries_the_reported_status(db: psycopg.Connection) -> None:
    """The status dimension resolves through a join on `status_reported`, so a covering list
    without it costs the facet its index-only scan — 296,762 buffers of heap at four states on
    the deployed load, against 12,778 for every other dimension."""
    definition = _indexdef(db, FACET_INDEX)

    assert "INCLUDE" in definition
    include = definition.split("INCLUDE", 1)[1]
    for column in (
        "operator_name_reported",
        "county_code_at_permit",
        "status_canonical",
        "status_reported",
        "well_type_reported",
        "completion_date",
        "derivation_id",
    ):
        assert column in include, column


def test_the_status_facet_reads_the_covering_index_rather_than_the_heap(
    db: psycopg.Connection,
) -> None:
    """The plan the INCLUDE buys. A plain `Index Scan` here is the defect: it means a heap visit
    per spine row for a column the index could have carried."""
    plan = _status_facet_plan(db)

    assert f"Index Only Scan using {FACET_INDEX}" in plan, plan


def test_the_resolver_is_reached_by_lookup_rather_than_by_scanning_it(
    db: psycopg.Connection,
) -> None:
    """The plan the keyed relation buys, and the whole of (b): one index probe per spine row
    against a relation the planner knows the size and the order of, instead of a merge on
    `state_code` alone with the reported code left to a join filter."""
    plan = _status_facet_plan(db)

    assert "status_resolution_resolved_pkey" in plan, plan
    assert "Rows Removed by Join Filter" not in plan, plan


def test_the_resolver_can_be_looked_up_by_both_keys(db: psycopg.Connection) -> None:
    """A view over a window function gives the planner no index and no order, so over a set of
    states it merged on `state_code` alone and filtered the reported code — 4,179,636 rows
    removed by that filter on the deployed load. A keyed relation is what makes it a lookup."""
    with db.cursor() as cursor:
        cursor.execute(
            "select i.indisprimary,"
            "       array_agg(a.attname order by k.ord)"
            "  from pg_index i"
            "  join pg_class c on c.oid = i.indrelid"
            "  join pg_namespace n on n.oid = c.relnamespace"
            "  join lateral unnest(i.indkey) with ordinality as k(attnum, ord) on true"
            "  join pg_attribute a on a.attrelid = c.oid and a.attnum = k.attnum"
            " where n.nspname = 'lineage' and c.relname = 'status_resolution_resolved'"
            "   and (i.indisprimary or i.indisunique)"
            " group by i.indexrelid, i.indisprimary"
        )
        keyed = {tuple(row[1]) for row in cursor.fetchall()}

    assert ("for_state_code", "for_status_reported") in keyed, keyed


def _live_registry_resolution(connection: psycopg.Connection) -> set[tuple[str, str, str]]:
    """What the registry says the resolver should hold, evaluated fresh and independently.

    Deliberately not the migration's own SELECT re-typed: a two-way `except` against a copy of
    the function body proves the function ran, never that it computes what the registry means.
    This walks the registry the *serving path* reads — `status_resolution.resolver_rules()` is
    the same query `marts/counts.py` uses to decide which jurisdictions resolve at read time —
    and then reads each rule's own spec for the table and columns its classes live in.
    """
    resolved: set[tuple[str, str, str]] = set()
    for prefix, rule_id in resolver_rules(connection).items():
        with connection.cursor() as cursor:
            cursor.execute(
                "select spec->>'mapping_table', spec->>'key_col', spec->>'value_col'"
                "  from lineage.conformance_rules where rule_id = %s",
                (rule_id,),
            )
            table, key_column, value_column = cursor.fetchone()
            cursor.execute(
                sql.SQL("select {key}::text, {value}::text from {table}").format(
                    key=sql.Identifier(key_column),
                    value=sql.Identifier(value_column),
                    table=sql.Identifier("lineage", table),
                )
            )
            resolved |= {(prefix, row[0], row[1]) for row in cursor.fetchall() if row[1]}
    return resolved


def test_the_resolver_matches_the_registry_it_was_built_from(db: psycopg.Connection) -> None:
    """Materialised data with no authority of its own has one obligation: to equal its source.

    Read-time resolution was exact by construction before this; now it is exact by refresh, and
    this is the gate that says so. Seeded, because the rule rows the registry answers from are
    the seed's by design (073's own comment says so) and a migrate-only database has no
    status-vocabulary rule for any jurisdiction.
    """
    seed_all(db)
    db.commit()
    with db.cursor() as cursor:
        cursor.execute(
            "select for_state_code, for_status_reported, resolved_status"
            "  from canonical.status_resolution"
        )
        held = {(row[0], row[1], row[2]) for row in cursor.fetchall()}
    expected = _live_registry_resolution(db)

    # A resolver that resolves nothing satisfies the equality by vacuity, and the registry this
    # fixture carries is the seed's own.
    assert expected
    assert held == expected


def test_appending_to_the_status_map_reaches_the_resolver(db: psycopg.Connection) -> None:
    """Both sources are append-only, so an append is the only way their content can change and
    a statement trigger on it is exact. Without the refresh the resolver is a stale copy."""
    seed_all(db)
    db.commit()
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.nm_wellhistory_status_map"
            " (status, decode, status_canonical, published_vintage)"
            " values ('Y', 'Planted by the suite', 'inactive', current_date)"
        )
        cursor.execute(
            "select resolved_status from canonical.status_resolution"
            " where for_status_reported = 'Y'"
        )
        resolved = cursor.fetchall()
    db.rollback()

    assert [row[0] for row in resolved] == ["inactive"]



# A jurisdiction the registry has never carried and no regulator answers to: `ZZ` passes
# `lineage.jurisdiction_codes`' `^[A-Z]{2}$` check and `99` collides with no registered prefix.
# The point is that nothing about the resolver knows which jurisdictions resolve at read time
# except the registry, so a fifth one is rows and not an edit.
PLANTED_CODE = "ZZ"
PLANTED_PREFIX = "99"
PLANTED_RULE = "cr_fixture_read_time_vocab_1"
PLANTED_MAP = "fixture_read_time_status_map"


def _plant_a_read_time_jurisdiction(
    connection: psycopg.Connection, *, with_map: bool = True
) -> None:
    """A registration, a read-time status vocabulary and the map its rule names.

    `with_map=False` registers the rule and leaves the table absent, which is the shape a typo
    in a spec makes and the shape a later migration makes by renaming a map.
    """
    seed_conformance_rule(
        connection,
        rule_id=PLANTED_RULE,
        spec={
            "resolved_at": "read_time",
            "mapping_table": PLANTED_MAP,
            "key_col": "status",
            "value_col": "status_canonical",
        },
        rationale="Planted so the resolver is proved to read the registry rather than a state.",
    )
    with connection.cursor() as cursor:
        if with_map:
            cursor.execute(
                f"create table if not exists lineage.{PLANTED_MAP} ("
                " status text primary key, status_canonical text not null)"
            )
            cursor.execute(
                f"insert into lineage.{PLANTED_MAP} (status, status_canonical)"
                " values ('W', 'active'), ('V', 'plugged') on conflict do nothing"
            )
        cursor.execute(
            "insert into lineage.jurisdiction_codes (jurisdiction_code, level)"
            " values (%s, 'state') on conflict do nothing",
            (PLANTED_CODE,),
        )
        cursor.execute(
            "insert into lineage.jurisdictions (jurisdiction_code, effective_from, published_at,"
            " evidence_tag, evidence_commit, name, regulator_name, regulator_url,"
            " identity_scheme, identity_prefix, identity_pattern, source_ids, rationale)"
            " values (%s, %s, %s, 'harness-fixture', %s, 'Planted', 'regulator',"
            " 'https://example.invalid/', 'api10', %s, %s, array['nd_mpr_xlsx'], 'fixture')"
            " on conflict do nothing",
            (
                PLANTED_CODE,
                REGISTERED_ON,
                REGISTERED_ON,
                "0" * 40,
                PLANTED_PREFIX,
                f"^{PLANTED_PREFIX}[0-9]{{8}}$",
            ),
        )
        cursor.execute(
            "insert into lineage.jurisdiction_rules (jurisdiction_code, effective_from,"
            " published_at, decision, rule_id) values (%s, %s, %s, 'status_vocabulary', %s)"
            " on conflict do nothing",
            (PLANTED_CODE, REGISTERED_ON, REGISTERED_ON, PLANTED_RULE),
        )


def test_a_fifth_read_time_jurisdiction_resolves_without_an_edit(
    db: psycopg.Connection,
) -> None:
    """The resolver is the registry's answer, not New Mexico's.

    Colorado registers a read-time status vocabulary in this same train and brings its own
    mapping table. If the refresh named one jurisdiction, its wells would resolve to null and
    the whole Colorado spine would draw unmapped — the defect v0.77 shipped a release to repair
    over Texas. So the function reads which jurisdictions resolve at read time, and which table
    and columns each one's rule names, out of `lineage.jurisdiction_rules` and the rule's own
    spec, and a jurisdiction the suite invents is answered for on the same terms.
    """
    seed_all(db)
    db.commit()
    _plant_a_read_time_jurisdiction(db)
    with db.cursor() as cursor:
        cursor.execute("select lineage.refresh_status_resolution()")
        cursor.execute(
            "select for_status_reported, resolved_status from canonical.status_resolution"
            " where for_state_code = %s order by 1",
            (PLANTED_PREFIX,),
        )
        resolved = cursor.fetchall()
    db.rollback()

    assert resolved == [("V", "plugged"), ("W", "active")]


def test_a_registered_jurisdiction_whose_mapping_table_has_not_landed_is_skipped(
    db: psycopg.Connection,
) -> None:
    """Migrations arrive in merge order and a registration can precede the table its rule names.

    A refresh that aborted on the missing table would abort the migration or the deploy's seed
    that called it, which is a worse failure than resolving one jurisdiction late. What the skip
    must not be is silent: the notice reaches the migrate log and `seed_all`'s output, and
    `/v1/status`'s `status_resolver` check and `infra/verify.sh` are what catch a skip that
    lasts -- a `mapping_table` misspelt in a spec, or a map renamed out from under a rule.

    Planted on a jurisdiction of the suite's own: a second serving `status_vocabulary` rule on a
    real one is refused by the registry's own partial unique index, so a test written that way
    plants nothing and passes on the refresh it never changed.
    """
    seed_all(db)
    db.commit()
    notices: list[str] = []
    db.add_notice_handler(lambda notice: notices.append(notice.message_primary or ""))
    _plant_a_read_time_jurisdiction(db, with_map=False)

    with db.cursor() as cursor:
        cursor.execute("select lineage.refresh_status_resolution()")
        resolved = int(cursor.fetchone()[0])
        cursor.execute(
            "select count(*) from canonical.status_resolution where for_state_code = %s",
            (PLANTED_PREFIX,),
        )
        planted = int(cursor.fetchone()[0])
    db.rollback()

    assert resolved > 0, "one unlanded map must not cost the jurisdictions that did land"
    assert planted == 0
    assert any(PLANTED_MAP in notice for notice in notices), notices


def test_a_registration_and_its_rules_reach_the_resolver_through_their_own_triggers(
    db: psycopg.Connection,
) -> None:
    """The registry path, fired rather than called. No refresh is invoked anywhere below.

    A jurisdiction arrives as a registration and then, because of the composite foreign key, as
    its rule rows — and the rules are the fact the refresh reads, so the registration's own
    trigger runs one statement too early to see them. Nothing in the tree exercised either
    trigger on the registry side before this; only the status map's was under test. If they do
    not fire, the resolver never hears about the jurisdiction and the assertions read that back.
    """
    seed_all(db)
    db.commit()
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from canonical.status_resolution where for_state_code = %s",
            (PLANTED_PREFIX,),
        )
        assert cursor.fetchone()[0] == 0

    _plant_a_read_time_jurisdiction(db)

    with db.cursor() as cursor:
        cursor.execute(
            "select for_status_reported, resolved_status from canonical.status_resolution"
            " where for_state_code = %s order by 1",
            (PLANTED_PREFIX,),
        )
        followed = cursor.fetchall()
        cursor.execute(
            "select count(*) from canonical.status_resolution where for_state_code = '30'"
        )
        untouched = int(cursor.fetchone()[0])
    db.rollback()

    assert followed == [("V", "plugged"), ("W", "active")]
    assert untouched > 0


# The two roles a served request and a pipeline run actually connect as. The owner is excluded
# for the reason test_layer_boundary.py excludes a superuser and says so: it holds every
# privilege by definition, and on this harness the fixture connects as it. On the deployed host
# `glasswell` is neither owner nor superuser and holds no insert here either, which was read
# read-only during the gate; what a test can assert is the two roles below.
SERVING_ROLES = ("glasswell_api", "glasswell_pipeline")


def test_a_registered_mapping_table_that_is_not_one_is_refused_by_the_class_domain(
    db: psycopg.Connection,
) -> None:
    """The escalation the grant below is the first thing standing in front of, and the class
    domain is the second.

    `refresh_status_resolution()` reads whatever two columns of whatever `lineage` table a rule
    spec names. The identifiers are `format(%I)`-quoted, so nothing injects -- but quoting bounds
    the *syntax*, not the *choice of table*. Registered against `lineage.conformance_rules`, the
    refresh would copy its rows straight into `lineage.status_resolution_resolved`, which
    `glasswell_api` may select and which `resolved_status()` reads as a well's served status
    class.

    The status-vocabulary train made that a refusal rather than a leak: every value the resolver
    materialises has a foreign key to `lineage.status_classes`, so a table that is not a status
    map cannot reach the wire through it. The grant is still the bound that matters, because a
    two-column `lineage` table whose values happened to be class names would satisfy the key.
    """
    seed_all(db)
    db.commit()
    seed_conformance_rule(
        db,
        rule_id="cr_fixture_arbitrary_table_1",
        spec={
            "resolved_at": "read_time",
            "mapping_table": "conformance_rules",
            "key_col": "rule_id",
            "value_col": "rationale",
        },
        rationale="Planted to show what the registry can name if anything may append to it.",
    )
    with db.cursor() as cursor:
        cursor.execute("select count(*) from lineage.conformance_rules")
        assert int(cursor.fetchone()[0]) > 0, "an empty rule set would pass on nothing"
        cursor.execute(
            "insert into lineage.jurisdiction_codes (jurisdiction_code, level)"
            " values (%s, 'state') on conflict do nothing",
            (PLANTED_CODE,),
        )
        cursor.execute(
            "insert into lineage.jurisdictions (jurisdiction_code, effective_from, published_at,"
            " evidence_tag, evidence_commit, name, regulator_name, regulator_url,"
            " identity_scheme, identity_prefix, identity_pattern, source_ids, rationale)"
            " values (%s, %s, %s, 'harness-fixture', %s, 'Planted', 'regulator',"
            " 'https://example.invalid/', 'api10', %s, %s, array['nd_mpr_xlsx'], 'fixture')",
            (
                PLANTED_CODE,
                REGISTERED_ON,
                REGISTERED_ON,
                "0" * 40,
                PLANTED_PREFIX,
                f"^{PLANTED_PREFIX}[0-9]{{8}}$",
            ),
        )
        with pytest.raises(psycopg.errors.ForeignKeyViolation) as refused:
            cursor.execute(
                "insert into lineage.jurisdiction_rules (jurisdiction_code, effective_from,"
                " published_at, decision, rule_id)"
                " values (%s, %s, %s, 'status_vocabulary', 'cr_fixture_arbitrary_table_1')",
                (PLANTED_CODE, REGISTERED_ON, REGISTERED_ON),
            )
    db.rollback()

    assert "resolved_status_class_fk" in str(refused.value)


def test_no_serving_role_may_append_the_registry_row_that_selects_a_mapping_table(
    db: psycopg.Connection,
) -> None:
    """The bound, made a gate instead of an absent grant nobody wrote down.

    What makes the `%I` path safe is not the quoting — that bounds the syntax. It is that
    selecting which table the refresh reads takes a `lineage.jurisdiction_rules` row, and no
    role a request or a pipeline run acts as may append one: only the table owner, through a
    migration or the seed, both of which are reviewed. The test above is what that grant is
    standing in front of.

    The day a migration grants `glasswell_pipeline` insert here — the cadence track registers
    rules and job rows of its own — the escalation above becomes reachable and nothing else in
    the tree would notice.
    """
    with db.cursor() as cursor:
        cursor.execute(
            "select r.rolname,"
            "       has_table_privilege(r.rolname, 'lineage.jurisdiction_rules', 'insert'),"
            "       has_table_privilege(r.rolname, 'lineage.jurisdictions', 'insert'),"
            "       has_table_privilege(r.rolname, 'lineage.conformance_rules', 'insert')"
            "  from pg_roles r where r.rolname = any(%s) order by r.rolname",
            (list(SERVING_ROLES),),
        )
        held = cursor.fetchall()
        # Not a fixed list of roles: one added later must be caught the day it is created, not
        # the day somebody remembers to name it here. `pg_*` are PostgreSQL's own predefined
        # roles, which nothing connects as, and the owner and a superuser hold every privilege
        # by definition -- the same exclusion test_layer_boundary.py makes and states.
        cursor.execute(
            "select r.rolname, has_table_privilege(r.rolname, c.oid, 'insert')"
            "  from pg_roles r"
            "  join pg_class c on c.relname = 'jurisdiction_rules'"
            "  join pg_namespace n on n.oid = c.relnamespace and n.nspname = 'lineage'"
            " where not r.rolsuper and r.oid <> c.relowner and r.rolname not like %s"
            " order by r.rolname",
            (r"pg\_%",),
        )
        candidates = cursor.fetchall()
    others = [role for role, may_insert in candidates if may_insert]

    # A candidate set that had lost the serving roles would satisfy the assertion below by
    # vacuity, which is the failure mode a grant gate is most likely to reach.
    assert set(SERVING_ROLES) <= {role for role, _ in candidates}
    assert [row[0] for row in held] == sorted(SERVING_ROLES)
    for role, rules, registrations, conformance in held:
        assert rules is False, f"{role} may append a jurisdiction rule"
        assert registrations is False, f"{role} may append a registration"
        # The pipeline legitimately seeds conformance rules, and that is not the escalation:
        # a rule spec reaches the resolver only through a jurisdiction_rules row.
        assert conformance in (True, False)
    assert others == [], f"a non-owner role may append a jurisdiction rule: {others}"


DUPLICATE_MAP = "fixture_duplicate_status_map"


def _plant_a_map_with_a_repeated_key(connection: psycopg.Connection) -> None:
    """A registered map whose key column is not unique within it, and the rule naming it."""
    seed_conformance_rule(
        connection,
        rule_id="cr_fixture_duplicate_key_1",
        spec={
            "resolved_at": "read_time",
            "mapping_table": DUPLICATE_MAP,
            "key_col": "status",
            "value_col": "status_canonical",
        },
        rationale="Planted so the registration-time check has something to refuse.",
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"create table if not exists lineage.{DUPLICATE_MAP} ("
            " status text not null, status_canonical text not null)"
        )
        cursor.execute(
            f"insert into lineage.{DUPLICATE_MAP} (status, status_canonical)"
            " values ('A', 'active'), ('A', 'plugged')"
        )
        cursor.execute(
            "insert into lineage.jurisdiction_codes (jurisdiction_code, level)"
            " values (%s, 'state') on conflict do nothing",
            (PLANTED_CODE,),
        )
        cursor.execute(
            "insert into lineage.jurisdictions (jurisdiction_code, effective_from, published_at,"
            " evidence_tag, evidence_commit, name, regulator_name, regulator_url,"
            " identity_scheme, identity_prefix, identity_pattern, source_ids, rationale)"
            " values (%s, %s, %s, 'harness-fixture', %s, 'Planted', 'regulator',"
            " 'https://example.invalid/', 'api10', %s, %s, array['nd_mpr_xlsx'], 'fixture')"
            " on conflict do nothing",
            (
                PLANTED_CODE,
                REGISTERED_ON,
                REGISTERED_ON,
                "0" * 40,
                PLANTED_PREFIX,
                f"^{PLANTED_PREFIX}[0-9]{{8}}$",
            ),
        )


def test_a_map_whose_key_repeats_is_refused_at_registration_and_named(
    db: psycopg.Connection,
) -> None:
    """The precondition moved when the resolver stopped reading one known table, and nobody
    wrote it down: the loop inserts into a relation keyed `(for_state_code, for_status_reported)`
    and assumes the registered key column is unique within its map.

    Left to the refresh, a repeated key surfaced as `status_resolution_resolved_pkey` from
    inside a statement trigger -- naming the primary key rather than the registry row that
    caused it, and aborting **every** later append to the registry, `seed_jurisdictions`
    included, which would take `seed_all` and therefore the deploy down. It is refused at the
    registration that introduces it now, by name.
    """
    seed_all(db)
    db.commit()
    _plant_a_map_with_a_repeated_key(db)

    with db.cursor() as cursor, pytest.raises(psycopg.errors.RaiseException) as refused:
        cursor.execute(
            "insert into lineage.jurisdiction_rules (jurisdiction_code, effective_from,"
            " published_at, decision, rule_id)"
            " values (%s, %s, %s, 'status_vocabulary', 'cr_fixture_duplicate_key_1')",
            (PLANTED_CODE, REGISTERED_ON, REGISTERED_ON),
        )
    db.rollback()

    message = str(refused.value)
    assert DUPLICATE_MAP in message
    assert "cr_fixture_duplicate_key_1" in message
    assert "status_resolution_resolved_pkey" not in message


def test_a_refused_registration_leaves_every_other_append_alone(
    db: psycopg.Connection,
) -> None:
    """The blast radius, which was the real defect: one bad map row poisoned the registry.

    The refusal has to be the registration's own, not a later unrelated one's, so an append that
    has nothing to do with the bad map still lands and the resolver still answers.
    """
    seed_all(db)
    db.commit()
    _plant_a_map_with_a_repeated_key(db)
    with db.cursor() as cursor:
        with pytest.raises(psycopg.errors.RaiseException):
            cursor.execute(
                "insert into lineage.jurisdiction_rules (jurisdiction_code, effective_from,"
                " published_at, decision, rule_id)"
                " values (%s, %s, %s, 'status_vocabulary', 'cr_fixture_duplicate_key_1')",
                (PLANTED_CODE, REGISTERED_ON, REGISTERED_ON),
            )
    db.rollback()

    # A new statement, after the refusal: the registry is still appendable and the resolver
    # still resolves the jurisdictions whose maps are sound.
    _plant_a_read_time_jurisdiction(db)
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from canonical.status_resolution where for_state_code = %s",
            (PLANTED_PREFIX,),
        )
        resolved = int(cursor.fetchone()[0])
        cursor.execute("select count(*) from canonical.status_resolution")
        total = int(cursor.fetchone()[0])
    db.rollback()

    assert resolved == 2
    assert total > 2
