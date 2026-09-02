"""The standing gates on the jurisdiction registry: two writers, one truth, no silent drift.

Three of these close residuals no constraint in the migration can reach (§4): a prefix
that resolves to two jurisdictions, a registration whose rule rows were not re-appended with it, and
a `source_ids` array that has quietly stopped being complete. The fourth holds the migration's
copy of the rows to the seed module's, evidence and knowledge time included, so a repoint that
touches one and forgets the other reddens here rather than on the deployed host.
"""

from __future__ import annotations

from datetime import date, timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from glasswell.lineage.jurisdictions import (
    JurisdictionRegistryError,
    clear_jurisdiction_cache,
    load_jurisdictions,
)
from glasswell.seed.conformance_basins import BASIN_SOURCES
from glasswell.seed.conformance_c115b import C115B_SOURCES
from glasswell.seed.conformance_land import LAND_SOURCES
from glasswell.seed.conformance_nm_wells import NM_WELLS_GIS_SOURCES
from glasswell.seed.conformance_tx import TX_SOURCES
from glasswell.seed.jurisdictions import (
    EXPLORER_DEFAULT_CODE,
    FOUNDING_JURISDICTIONS,
    JURISDICTION_RESTATEMENTS,
    JURISDICTION_RULES,
    REGISTERED_ON,
    REQUIRED_DECISIONS,
    RESTATED_ON,
    colorado_parameters,
    registration_parameters,
    restatement_parameters,
    rule_parameters,
)
from glasswell.seed.reference import SOURCES
from tests.conftest import FIXTURE_SOURCES

pytestmark = pytest.mark.contract

# Every source any seeder registers. The harness inserts fixture rows of its own before
# seed_sources runs, and a source no seeder declares is not one an array can be incomplete
# about -- so the completeness gate is scoped to what the tree actually registers.
DECLARED_SOURCES = {
    str(row["source_id"])
    for tuple_ in (
        SOURCES, TX_SOURCES, LAND_SOURCES, BASIN_SOURCES, C115B_SOURCES, NM_WELLS_GIS_SOURCES
    )
    for row in tuple_
}
# Coverage, not regulator: the two EIA boundary sets, the NOAA datum grid and the FracFocus
# archive cover the country, so they carry US and stay outside the registry (B-4).
FEDERAL_SOURCES = frozenset(
    {"eia_sedimentary_basins", "eia_shale_plays", "proj_grid_nad27", "fracfocus_csv"}
)


@pytest.fixture(autouse=True)
def _uncached() -> None:
    """The loader caches per clock pair and per database; a planted row must be seen."""
    clear_jurisdiction_cache()


def sources_for(connection: psycopg.Connection, jurisdiction: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select source_id from lineage.sources where jurisdiction = %s", (jurisdiction,)
        )
        return {row[0] for row in cursor.fetchall()} & DECLARED_SOURCES


def test_every_resolved_prefix_belongs_to_exactly_one_jurisdiction(
    db: psycopg.Connection,
) -> None:
    """Gate (a), N-3. The partial unique index covers a collision only at one (effective_from,
    published_at); an executed probe registered CO with prefix 33 one day after ND's and both
    resolved. So the test plants exactly that and expects the loader to refuse."""
    registry = load_jurisdictions(db)
    assert registry.by_prefix["33"].jurisdiction_code == "ND"

    collision = REGISTERED_ON + timedelta(days=1)
    with db.cursor() as cursor:
        cursor.execute("insert into lineage.jurisdiction_codes values ('WY', 'state')")
        cursor.execute(
            "insert into lineage.jurisdictions (jurisdiction_code, effective_from,"
            " published_at, evidence_tag, evidence_commit, name, regulator_name, regulator_url,"
            " identity_scheme, identity_prefix, identity_pattern, source_ids, rationale)"
            " values ('WY', %s, %s, 'v0.76', %s, 'Wyoming', 'WOGCC', 'https://wogcc.wyo.gov',"
            " 'api10', '33', '^33[0-9]{8}$', array['nd_mpr_xlsx'], 'planted')",
            (collision, collision, "a" * 40),
        )
    clear_jurisdiction_cache()

    with pytest.raises(JurisdictionRegistryError) as refused:
        load_jurisdictions(db, collision)

    assert "33" in str(refused.value)


def test_every_resolved_registration_carries_the_rule_rows_it_declares(
    db: psycopg.Connection,
) -> None:
    """Gate (b). A restatement is a new row, and a row published at T2 states what was known at
    T2 -- so its rule rows are re-appended with it. This catches one that forgot."""
    registry = load_jurisdictions(db)
    declared: dict[str, set[tuple[str, str, bool]]] = {}
    for rule in (rule_parameters(row) for row in JURISDICTION_RULES):
        declared.setdefault(str(rule["jurisdiction_code"]), set()).add(
            (str(rule["decision"]), str(rule["rule_id"]), bool(rule["serving"]))
        )

    for row in registry:
        resident = {(rule.decision, rule.rule_id, rule.serving) for rule in row.rules}
        assert resident == declared[row.jurisdiction_code]
        for decision in REQUIRED_DECISIONS:
            assert row.rule(decision) is not None


def test_no_absence_decision_claims_a_dimension_the_spine_carries_values_for(
    db: psycopg.Connection,
) -> None:
    """R8 runs both ways: a registered decision has to be true of the data it decides about.

    An `absence:<dimension>` row says a jurisdiction reports no value of that dimension at all,
    which is what takes its wells out of the shared `not reported` bucket. The register is
    append-only, so a row asserting it of a jurisdiction that does report the dimension can only
    be superseded, never corrected — and on the deployed spine Texas carries 228,169 completion
    dates over 107 distinct years, which is what this gate was written after.

    The two rows that exist are both `absence:operator`, and both say what a *blank* operator
    means rather than that the jurisdiction files none; the facet only reads them as
    `absent_by_rule` where the jurisdiction contributes no value at all, which neither does.
    """
    registry = load_jurisdictions(db)
    claimed = {
        (row.jurisdiction_code, rule.decision.split(":", 1)[1])
        for row in registry
        for rule in row.rules
        if rule.serving and rule.decision.startswith("absence:")
    }

    assert claimed == {("TX", "operator"), ("MT", "operator")}, (
        "an absence decision was registered or removed; it must be measured against the"
        " deployed spine before it lands, because the register cannot be corrected"
    )


def test_exactly_one_resolved_registration_is_the_explorer_default(
    db: psycopg.Connection,
) -> None:
    """The standing gate the partial unique index cannot make. The index holds it to one per
    `(effective_from, published_at)`; two registrations a day apart both resolve, and a client
    that finds two defaults — or none — has to pick, which is the thing being taken away."""
    registry = load_jurisdictions(db)
    defaults = [row for row in registry if row.explorer_default]

    assert [row.jurisdiction_code for row in defaults] == [EXPLORER_DEFAULT_CODE]
    assert "explorer_default" in defaults[0].rationale


def test_a_second_explorer_default_at_one_instant_is_refused_by_the_index(
    db: psycopg.Connection,
) -> None:
    with db.cursor() as cursor:
        cursor.execute("insert into lineage.jurisdiction_codes values ('WY', 'state')")
        with pytest.raises(psycopg.errors.UniqueViolation):
            cursor.execute(
                "insert into lineage.jurisdictions (jurisdiction_code, effective_from,"
                " published_at, evidence_tag, evidence_commit, name, regulator_name,"
                " regulator_url, identity_scheme, identity_prefix, identity_pattern,"
                " source_ids, rationale, explorer_default)"
                " values ('WY', %s, %s, 'v0.76', %s, 'Wyoming', 'WOGCC',"
                " 'https://wogcc.wyo.gov', 'api10', '49', '^49[0-9]{8}$',"
                " array['nd_mpr_xlsx'], 'planted', true)",
                (REGISTERED_ON, REGISTERED_ON, "a" * 40),
            )


def test_a_second_explorer_default_a_day_later_is_caught_by_the_gate_the_index_cannot_make(
    db: psycopg.Connection,
) -> None:
    """The N-3 shape again, on a different column: accepted by the index, refused by the set."""
    later = REGISTERED_ON + timedelta(days=1)
    with db.cursor() as cursor:
        cursor.execute("insert into lineage.jurisdiction_codes values ('WY', 'state')")
        cursor.execute(
            "insert into lineage.jurisdictions (jurisdiction_code, effective_from,"
            " published_at, evidence_tag, evidence_commit, name, regulator_name, regulator_url,"
            " identity_scheme, identity_prefix, identity_pattern, source_ids, rationale,"
            " explorer_default)"
            " values ('WY', %s, %s, 'v0.76', %s, 'Wyoming', 'WOGCC',"
            " 'https://wogcc.wyo.gov', 'api10', '49', '^49[0-9]{8}$',"
            " array['nd_mpr_xlsx'], 'planted', true)",
            (later, later, "a" * 40),
        )
    clear_jurisdiction_cache()

    registry = load_jurisdictions(db, later)

    assert len([row for row in registry if row.explorer_default]) == 2


def test_every_registration_lists_every_source_registered_to_it(
    db: psycopg.Connection,
) -> None:
    """Gate (c), N-4. Set equality rather than membership: a source registered for a
    jurisdiction and left out of the array is the drift this catches."""
    registry = load_jurisdictions(db)

    for row in registry:
        assert set(row.source_ids) == sources_for(db, row.jurisdiction_code)


def test_only_the_federal_coverage_sources_resolve_to_no_registration(
    db: psycopg.Connection,
) -> None:
    """The round trip: `lineage.sources.jurisdiction` is a coverage axis, so the two EIA sets,
    the NOAA grid and FracFocus carry US and have no regulator to register."""
    registry = load_jurisdictions(db)
    registered = {source_id for row in registry for source_id in row.source_ids}

    assert DECLARED_SOURCES - registered == FEDERAL_SOURCES

    with db.cursor() as cursor:
        cursor.execute("select source_id from lineage.sources")
        resident = {row[0] for row in cursor.fetchall()}
    # Anything resident but undeclared is the harness's own fixture row, never a real source.
    assert resident - DECLARED_SOURCES <= {source_id for source_id, _ in FIXTURE_SOURCES}


def test_the_migration_and_the_seed_module_write_the_same_registrations(
    db: psycopg.Connection,
) -> None:
    """N-5: evidence_tag, evidence_commit and published_at are compared, so a repoint that
    touches the migration and forgets the mirror reddens here."""
    with db.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select * from lineage.jurisdictions order by jurisdiction_code, effective_from,"
            " published_at"
        )
        resident = cursor.fetchall()

    # An explicit key, not declaration order plus a stable sort: the database emits founding
    # before restated per code, and a concatenation that happened to emit them the other way
    # round paired every row with its own restatement and failed on evidence_tag with no hint.
    expected = sorted(
        (
            *(registration_parameters(row) for row in JURISDICTION_RESTATEMENTS),
            *(restatement_parameters(row) for row in FOUNDING_JURISDICTIONS),
            # Founded whole at its own instant: a registration that arrives after the
            # presentation columns exist has nothing to restate, so it is one row and not two.
            colorado_parameters(),
        ),
        key=lambda row: (str(row["jurisdiction_code"]), row["published_at"]),
    )
    assert len(resident) == len(expected)
    for landed, declared in zip(resident, expected, strict=True):
        for column, value in declared.items():
            assert landed[column] == (
                list(value) if isinstance(value, tuple) else value
            ), f"{landed['jurisdiction_code']}.{column}"


def test_a_registration_published_after_the_cut_is_not_served_under_it(
    db: psycopg.Connection,
) -> None:
    """B-6, at the loader. as_of is a knowledge-time cut, so a row published after it does not
    exist yet -- which is the failure a static current view cannot avoid."""
    corrected = "https://www.dmr.nd.gov/oilgas/"
    later = REGISTERED_ON + timedelta(days=61)
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.jurisdictions (jurisdiction_code, effective_from,"
            " published_at, evidence_tag, evidence_commit, name, regulator_name, regulator_url,"
            " identity_scheme, identity_prefix, identity_pattern, source_ids, rationale)"
            " select jurisdiction_code, effective_from, %s, evidence_tag, evidence_commit,"
            " name, regulator_name, %s, identity_scheme, identity_prefix, identity_pattern,"
            " source_ids, 'regulator_url typo corrected' from lineage.jurisdictions"
            " where jurisdiction_code = 'ND' and published_at ="
            "   (select max(published_at) from lineage.jurisdictions"
            "     where jurisdiction_code = 'ND')",
            (later, corrected),
        )

    before = load_jurisdictions(db, later - timedelta(days=1))
    clear_jurisdiction_cache()
    after = load_jurisdictions(db, later)

    assert before.by_code["ND"].regulator_url.endswith("mprindex.asp")
    assert before.by_code["ND"].published_at == RESTATED_ON
    assert after.by_code["ND"].regulator_url == corrected
    assert after.by_code["ND"].published_at == later


def test_a_registry_that_answers_nothing_is_a_refusal_and_not_an_empty_map(
    db: psycopg.Connection,
) -> None:
    """R8, mirroring `marts/producing.py`: the definition is rows, so a missing row is a
    refusal, never an assumed default. The API serves service_degraded for this."""
    with pytest.raises(JurisdictionRegistryError) as refused:
        load_jurisdictions(db, date(2026, 1, 1))

    assert "resolves no registration" in str(refused.value)
