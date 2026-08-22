"""The NM completion dimension: the substrate D3's Validator B is built on.

The whole path runs here against the 300-record sibling fixtures — the sealed zips, staging, the
registry's rules, the OGRID alias load, the POD fan-out and the ledger. Two things the corpus
cannot demonstrate are driven from synthetic documents whose shape is the measured shape of the
real artifacts: an OGRID with no registry row (all 2,223 codes wchistory cites resolve) and a
completion carrying none of the three lease-equivalent identifiers.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import psycopg
import pytest

from glasswell.ingest import nm_dims
from glasswell.ingest.base import open_ingest_run
from glasswell.lineage.conformance import load_rules
from glasswell.lineage.errors import VintageAlreadyPromoted
from glasswell.seed import seed_all
from glasswell.seed.conformance_nm import NM_COLUMNS
from tests.integration.test_nm_stage import record_text, stage, synthetic_document
from tests.integration.test_nm_stage import staging_root as _staging_root
from tests.support.fakes import FixedClock

staging_root = _staging_root

DIM_SOURCE = "nm_ocd_wchistory"
SIBLINGS = ("wchistory", "podwc", "spacingunit", "property", "ogrid")
DAY_ONE = datetime(2026, 8, 21, 6, 15, 0, tzinfo=UTC)
DAY_TWO = datetime(2026, 8, 22, 6, 15, 0, tzinfo=UTC)
LEASE_RULE = "cr_nm_wcproduction_lease_equivalent_1"


@pytest.fixture
def seeded(db: psycopg.Connection) -> None:
    seed_all(db)
    db.commit()


@pytest.fixture
def staged(db, seeded, raw_root, staging_root, tmp_path, monkeypatch):
    for table in SIBLINGS:
        stage(db, raw_root, tmp_path, monkeypatch, table=table, at=DAY_ONE)
    return None


def promote(db: psycopg.Connection, *, at: datetime = DAY_ONE) -> nm_dims.DimensionReport:
    with open_ingest_run(db, source_id=DIM_SOURCE, clock=FixedClock(at)) as run:
        report = nm_dims.promote_dimensions(run)
    db.commit()
    return report


def query(db: psycopg.Connection, sql: str, *parameters: object) -> list[tuple]:
    with db.cursor() as cursor:
        cursor.execute(sql, parameters or None)
        return cursor.fetchall()


def scalar(db: psycopg.Connection, sql: str, *parameters: object):
    return query(db, sql, *parameters)[0][0]


def rule_spec(db: psycopg.Connection, rule_id: str) -> dict:
    return json.loads(
        json.dumps(
            scalar(db, "select spec from lineage.conformance_rules where rule_id = %s", rule_id)
        )
    )


# ---------------------------------------------------------------- 5.4 operator aliases


def test_every_registered_ogrid_becomes_an_alias_at_confidence_one(db, staged):
    report = promote(db)
    rows = query(
        db,
        "select operator_raw, operator, confidence, source_id from lineage.operator_aliases"
        " order by operator_raw limit 1",
    )

    staged = scalar(db, "select count(*) from staging.stg_nm_ocd_ogrid__records")
    assert report.aliases_written == staged
    assert report.aliases_registered == staged
    assert rows[0][2] == Decimal("1.000")
    assert rows[0][3] == "nm_ocd_ogrid"
    assert scalar(db, "select count(*) from lineage.operator_aliases where confidence <> 1") == 0


def test_the_alias_load_records_the_method_in_the_rule_and_not_on_the_row(db, staged):
    promote(db)

    assert "method" not in {
        column
        for (column,) in query(
            db,
            "select column_name from information_schema.columns where table_schema = 'lineage'"
            " and table_name = 'operator_aliases'",
        )
    }
    assert rule_spec(db, "cr_nm_ogrid_operator_1")["method"] == "exact_key"
    assert rule_spec(db, "cr_nm_ogrid_registry_1")["fuzzy_matching"] == "prohibited"


def test_an_unknown_ogrid_quarantines_as_alias_unresolved_and_is_counted(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
):
    """No fuzzy fallback: an OGRID the registry does not carry leaves under its own reason code
    with its payload, rather than joining to the nearest name (SB-01 §5.3)."""
    for table in SIBLINGS:
        document = None
        if table == "wchistory":
            document = _wchistory_with(ogrid_cde="99999999")
        stage(db, raw_root, tmp_path, monkeypatch, table=table, document=document, at=DAY_ONE)

    report = promote(db)

    assert report.quarantined["alias_unresolved"] == 1
    payload = scalar(
        db,
        "select row_payload from lineage.quarantine_rows where reason_code = 'alias_unresolved'",
    )
    assert payload["operator_raw"] == "99999999"
    assert report.staged_rows == report.kept_completions + sum(report.quarantined.values())


def test_the_unresolved_share_is_a_property_of_the_fixture_cut_and_not_of_the_corpus(db, staged):
    """`nm_ogrid_300.xml` is the registry head, and the wchistory cut names operators outside
    it, so most fixture observations leave as alias_unresolved. On the real artifacts all 2,223
    OGRID codes wchistory cites resolve against all 31,696 registered — measured, and recorded
    in cr_nm_ogrid_registry_1 so this number is never read as a finding about New Mexico."""
    report = promote(db)
    measured = rule_spec(db, "cr_nm_ogrid_registry_1")["measured"]

    assert report.quarantined["alias_unresolved"] > 0
    assert measured["wchistory_ogrids_absent_from_registry"] == 0
    assert measured["distinct_ogrid_in_wchistory"] == 2223
    assert scalar(
        db,
        "select count(*) from staging.stg_nm_ocd_ogrid__records",
    ) < measured["ogrid_rows"]


# ---------------------------------------------------------------- 5.2 the dimension itself


def test_every_staged_completion_that_keys_lands_a_row(db, staged):
    report = promote(db)

    assert report.staged_rows == scalar(
        db, "select count(*) from staging.stg_nm_ocd_wchistory__records"
    )
    assert report.kept_completions == report.staged_rows - sum(report.quarantined.values())
    assert scalar(
        db,
        "select count(distinct (completion_key, effective_from)) from canonical.well_completions"
        " where source_id = %s",
        DIM_SOURCE,
    ) == report.kept_completions


def test_the_completion_key_is_the_entity_key_the_spine_reports_under(db, staged):
    promote(db)
    rows = query(
        db,
        "select completion_key, api10, well_completion_pool from canonical.well_completions"
        " where source_id = %s limit 200",
        DIM_SOURCE,
    )

    assert rows
    for completion_key, api10, pool in rows:
        assert completion_key == f"{api10}:{pool}"
        assert len(api10) == 10
        assert api10.startswith("30")


def test_a_dimension_row_carries_no_production_month_and_a_month_row_carries_no_effective_from(
    db, staged
):
    """Migration 029's grain CHECK. The two grains coexist; neither can claim the other's key."""
    promote(db)

    assert scalar(
        db,
        "select count(*) from canonical.well_completions"
        " where source_id = %s and production_month is not null",
        DIM_SOURCE,
    ) == 0
    assert scalar(
        db,
        "select count(*) from canonical.well_completions"
        " where source_id = %s and effective_from is null",
        DIM_SOURCE,
    ) == 0


def test_a_status_change_is_a_new_row_and_never_an_update(db, staged):
    promote(db)
    repeated = query(
        db,
        "select completion_key, count(distinct effective_from) from canonical.well_completions"
        " where source_id = %s group by 1 having count(distinct effective_from) > 1 limit 1",
        DIM_SOURCE,
    )

    assert repeated, "the fixture carries a completion with more than one observation"
    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"):
        with db.cursor() as cursor:
            cursor.execute("update canonical.well_completions set status_reported = 'X'")
    db.rollback()


def test_the_status_letter_is_promoted_verbatim_and_nothing_is_canonicalised(db, staged):
    """No codebook maps NM's status letters, so status_canonical is an absent mapping rather
    than a mapping to a guess (cr_nm_wchistory_status_domain_1)."""
    promote(db)

    assert scalar(
        db,
        "select count(*) from canonical.well_completions"
        " where source_id = %s and status_canonical is not null",
        DIM_SOURCE,
    ) == 0
    assert scalar(
        db,
        "select count(distinct status_reported) from canonical.well_completions"
        " where source_id = %s",
        DIM_SOURCE,
    ) > 1
    assert set(rule_spec(db, "cr_nm_wchistory_status_domain_1")["measured_domain"]) >= {"A", "P"}


def test_a_spacing_unit_of_zero_is_absent_and_never_an_identifier(db, staged):
    """119,662 of 426,529 records file spc_unit_idn '0'. Promoted verbatim it would be one
    spacing unit holding a quarter of New Mexico."""
    promote(db)

    assert scalar(
        db,
        "select count(*) from canonical.well_completions"
        " where source_id = %s and spacing_unit_id = '0'",
        DIM_SOURCE,
    ) == 0
    assert scalar(
        db,
        "select count(*) from staging.stg_nm_ocd_wchistory__records where btrim(spc_unit_idn)='0'"
    ) > 0


def test_a_completion_with_no_lease_equivalent_identifier_is_quarantined_and_counted(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
):
    """P5.8's orphan case. A row that resolves no POD, no spacing unit and no property cannot
    enter a Validator B group at all, so it leaves as orphan_fk with its payload."""
    for table in SIBLINGS:
        document = None
        if table == "wchistory":
            document = _wchistory_with(
                api_well_idn="99999", pool_idn="99999", spc_unit_idn="0", prod_prop_idn="0"
            )
        stage(db, raw_root, tmp_path, monkeypatch, table=table, document=document, at=DAY_ONE)

    report = promote(db)

    assert report.quarantined["orphan_fk"] == 1
    assert scalar(
        db,
        "select count(*) from lineage.quarantine_rows where reason_code = 'orphan_fk'"
        " and rule_id = 'cr_nm_wchistory_lease_identifier_1'",
    ) == 1
    assert scalar(
        db,
        "select count(*) from canonical.well_completions where source_id = %s"
        " and pod_id is null and spacing_unit_id is null and property_id is null",
        DIM_SOURCE,
    ) == 0


# ---------------------------------------------------------------- 5.3 the wellbore policy


def test_the_multi_wellbore_policy_is_vacuous_because_nm_cannot_express_a_sidetrack(db, staged):
    """A metric that cannot be non-zero is not a measurement. The rule says vacuous; the
    dimension reports no api12; and no row is quarantined under the policy."""
    report = promote(db)
    spec = rule_spec(db, "cr_nm_wchistory_wellbore_policy_1")

    assert spec["status"] == "vacuous"
    assert spec["detection_field"] is None
    assert report.wellbore_policy == "vacuous"
    assert report.quarantined.get("multi_wellbore_policy", 0) == 0
    assert scalar(
        db,
        "select count(*) from canonical.well_completions where source_id = %s"
        " and api12 is not null",
        DIM_SOURCE,
    ) == 0


def test_no_in_scope_nm_source_carries_a_column_past_the_api_ten_triple(db, staged):
    """The detection source SB-01 §5.3 names is wchistory, and this is what it ships."""
    columns = {
        column
        for (column,) in query(
            db,
            "select column_name from information_schema.columns where table_schema = 'staging'"
            " and table_name like 'stg\\_nm\\_ocd\\_%%' and column_name like 'api%%'",
        )
    }

    assert columns == {"api_st_cde", "api_cnty_cde", "api_well_idn"}


# ---------------------------------------------------------------- 5.2 the POD fan-out


def test_a_completion_in_several_pods_is_several_rows_and_not_one_pod_chosen_by_order(db, staged):
    report = promote(db)
    fanned = query(
        db,
        "select completion_key, effective_from, count(*), count(distinct pod_id)"
        " from canonical.well_completions where source_id = %s and pod_id is not null"
        " group by 1, 2 having count(*) > 1",
        DIM_SOURCE,
    )

    assert fanned, "the fixture carries a completion crosswalked to more than one POD"
    assert report.promoted_rows > report.kept_completions
    assert report.pod_fanout == report.promoted_rows
    for _key, _effective, rows, pods in fanned:
        assert rows == pods


def test_a_pod_crosswalked_after_the_observation_is_not_backdated_onto_it(db, staged):
    """cr_nm_podwc_pod_1's predicate is one-sided: podwc has no termination date, so a POD is
    never withdrawn, but neither is it in force before the date it was filed."""
    promote(db)
    joined = scalar(
        db,
        "select count(*) from canonical.well_completions c"
        "  join staging.stg_nm_ocd_podwc__records p"
        "    on p.pod_idn = c.pod_id"
        "   and p.api_st_cde || lpad(p.api_cnty_cde, 3, '0') || lpad(p.api_well_idn, 5, '0')"
        "       = c.api10"
        "   and p.pool_idn = c.well_completion_pool"
        " where c.source_id = %s",
        DIM_SOURCE,
    )
    backdated = scalar(
        db,
        "select count(*) from canonical.well_completions c"
        "  join staging.stg_nm_ocd_podwc__records p"
        "    on p.pod_idn = c.pod_id"
        "   and p.api_st_cde || lpad(p.api_cnty_cde, 3, '0') || lpad(p.api_well_idn, 5, '0')"
        "       = c.api10"
        "   and p.pool_idn = c.well_completion_pool"
        " where c.source_id = %s and left(p.eff_dte, 10)::date > c.effective_from",
        DIM_SOURCE,
    )

    assert joined > 0, "the assertion is about crosswalk rows that exist"
    assert backdated == 0


def test_the_pod_rules_measured_figures_are_taken_at_the_granularity_it_joins_at(db, staged):
    """gate-nm-p5 B1. `podwc` timestamps every row and the join truncates to the date, so a
    timestamp-grained measurement counts a different grouping: 71,435 groups against 80,663,
    and 762,522 fanned rows against the 763,473 the promotion actually appends. The label and
    the predicate are asserted together, so changing one without the other goes red."""
    promote(db)
    measured = rule_spec(db, "cr_nm_podwc_pod_1")["measured"]

    assert measured["measured_at"] == "date"
    assert "left(eff_dte, 10)::date" in nm_dims._CREATE_CROSSWALK
    assert "w.effective_from <= b.effective_from" in nm_dims._POD_LATERAL
    assert sum(measured["pods_per_completion_at_one_eff_dte"].values()) == 80663
    assert sum(measured["pods_per_completion_at_one_eff_timestamp"].values()) == 71435
    assert measured["fanned_out_rows"] == 763473
    assert measured["fanned_out_rows_at_one_eff_timestamp"] == 762522


def test_a_pod_crosswalked_after_the_observation_does_not_rescue_it_from_the_orphan_exit(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
):
    """gate-nm-p5 O3. The orphan test asks the question the POD attach asks — is a POD in force
    *at this observation's* effective date — so a completion whose only POD is crosswalked five
    years later, with no spacing unit and no property, leaves as orphan_fk rather than landing
    with all three identifiers null."""
    for table in SIBLINGS:
        document = None
        if table == "wchistory":
            document = _wchistory_with(
                api_well_idn="99999", pool_idn="99999", spc_unit_idn="0", prod_prop_idn="0",
                eff_dte="2015-01-01T00:00:00",
            )
        elif table == "podwc":
            document = _podwc_with(
                api_well_idn="99999", pool_idn="99999", eff_dte="2020-06-01T00:00:00"
            )
        stage(db, raw_root, tmp_path, monkeypatch, table=table, document=document, at=DAY_ONE)

    report = promote(db)

    assert report.quarantined["orphan_fk"] == 1
    assert report.promoted_rows == 0
    assert scalar(
        db,
        "select count(*) from canonical.well_completions where source_id = %s"
        " and pod_id is null and spacing_unit_id is null and property_id is null",
        DIM_SOURCE,
    ) == 0


# ---------------------------------------------------------------- 5.5 the rule row


def test_the_lease_equivalent_rule_names_all_three_identifiers_and_the_reweighting_caveat(db,
                                                                                          staged):
    promote(db)
    row = query(
        db,
        "select rule_kind, stage, rule, rationale, spec from lineage.conformance_rules"
        " where rule_id = %s",
        LEASE_RULE,
    )

    assert len(row) == 1
    _kind, _stage, rule, rationale, spec = row[0]
    assert spec["grouping_key"] == [
        "source_operator_key",
        "pool_idn",
        "pod_id | spacing_unit_id | property_id",
    ]
    for identifier in ("pod_id", "spacing_unit_id", "property_id"):
        assert identifier in rule
    assert "post-hoc group-selection reweighting" in rationale
    assert "residual mismatch" in rationale
    assert "no coordinates" in rationale or "ships no coordinates" in rationale
    assert "NM Delaware is not TX Midland" in rationale
    assert spec["resampling"] == "post_hoc_group_selection_reweighting"
    assert spec["residual_mismatch"] == "must_be_published"
    assert set(spec["measured_wells_per_group"]) >= {"pod", "spacing_unit", "property"}
    # The number D3 actually needs: property is the only key that reaches every completion,
    # and every key's median group holds one well.
    reached = spec["measured_wells_per_group"]["completions_reached"]
    assert reached["property"] == reached["total"]
    for key in ("pod", "spacing_unit", "property"):
        assert spec["measured_wells_per_group"][key]["p50"] == 1


def test_the_lease_equivalent_rule_is_cited_by_the_derivation_that_built_the_substrate(db,
                                                                                       staged):
    report = promote(db)
    cited = {
        rule_id
        for (rule_id,) in query(
            db,
            "select rule_id from lineage.derivation_rules where derivation_id = %s",
            report.derivation_id,
        )
    }

    assert LEASE_RULE in cited
    assert "cr_nm_wchistory_completion_key_1" in cited
    assert "cr_nm_podwc_pod_1" in cited


# ---------------------------------------------------------------- 5.8 Validator B arithmetic


def test_a_validator_b_group_sums_exactly_what_the_individual_rows_hold(db, staged):
    """SB-01 §8.6 step 3: no estimate enters here. The group total is the sum of the rows it
    is made of, computed two ways and compared for equality, not for closeness."""
    promote(db)
    grouped = query(
        db,
        "select source_operator_key, well_completion_pool, pod_id, count(distinct api10)"
        "  from canonical.well_completions"
        " where source_id = %s and pod_id is not null"
        " group by 1, 2, 3 order by 4 desc, 1, 2, 3 limit 5",
        DIM_SOURCE,
    )

    assert grouped
    for operator, pool, pod, wells in grouped:
        members = {
            api10
            for (api10,) in query(
                db,
                "select distinct api10 from canonical.well_completions where source_id = %s"
                " and source_operator_key = %s and well_completion_pool = %s and pod_id = %s",
                DIM_SOURCE,
                operator,
                pool,
                pod,
            )
        }
        assert len(members) == wells


def test_the_group_well_months_equal_the_sum_of_the_members_own_well_months(db, staged, seeded):
    """The Validator-B-shaped query: group by (operator, pool, pod), sum well-months over the
    completions that group holds, against the same sum taken one completion at a time."""
    promote(db)
    _seed_well_months(db)

    grouped = query(
        db,
        "select c.source_operator_key, c.well_completion_pool, c.pod_id, sum(p.well_months)"
        "  from canonical.well_completions c"
        "  join _well_months p on p.completion_key = c.completion_key"
        " where c.source_id = %s and c.pod_id is not null"
        " group by 1, 2, 3 order by 4 desc limit 3",
        DIM_SOURCE,
    )

    assert grouped
    for operator, pool, pod, total in grouped:
        one_at_a_time = sum(
            months
            for (months,) in query(
                db,
                "select p.well_months from canonical.well_completions c"
                "  join _well_months p on p.completion_key = c.completion_key"
                " where c.source_id = %s and c.source_operator_key = %s"
                "   and c.well_completion_pool = %s and c.pod_id = %s",
                DIM_SOURCE,
                operator,
                pool,
                pod,
            )
        )
        assert total == one_at_a_time


# ---------------------------------------------------------------- ledger and re-runs


def test_promoting_the_same_manifest_at_the_same_vintage_appends_nothing(db, staged):
    first = promote(db)
    landed = scalar(db, "select count(*) from canonical.well_completions")
    second = promote(db)

    assert second.promoted_rows == 0
    assert scalar(db, "select count(*) from canonical.well_completions") == landed
    assert first.promoted_rows > 0


def test_a_vintage_that_already_answered_differently_is_refused_rather_than_rewritten(db, staged):
    promote(db)
    with db.cursor() as cursor:
        cursor.execute(
            "update staging.stg_nm_ocd_wchistory__records set wc_stat_cde = 'Z'"
            " where wc_stat_cde is distinct from 'Z'"
        )
    db.commit()

    with pytest.raises(VintageAlreadyPromoted):
        promote(db)
    db.rollback()


def test_the_vintage_records_what_the_run_examined_and_appended(db, staged):
    report = promote(db)
    row = query(
        db,
        "select rows_examined, rows_appended from lineage.vintages"
        " where source_id = %s and vintage_date = %s",
        DIM_SOURCE,
        date(2026, 8, 21),
    )

    assert row == [(report.staged_rows, report.promoted_rows)]


def test_a_same_day_second_manifest_accumulates_the_vintage_ledger(
    db, staged, raw_root, staging_root, tmp_path, monkeypatch
):
    """DR-85: every same-day promotion upserts one (source, day) ledger row, so the counters
    must be the day's sum — which is what canonical holds for the source — not the last
    run's report."""
    first = promote(db)
    stage(
        db, raw_root, tmp_path, monkeypatch,
        table="wchistory",
        document=_wchistory_with(api_well_idn="90210"),
        at=DAY_ONE,
    )
    second = promote(db)

    rows = query(
        db,
        "select rows_examined, rows_appended, manifest_ids from lineage.vintages"
        " where source_id = %s",
        DIM_SOURCE,
    )
    assert second.promoted_rows > 0
    assert len(rows) == 1
    examined, appended, manifests = rows[0]
    assert examined == first.staged_rows + second.staged_rows
    assert appended == first.promoted_rows + second.promoted_rows
    assert appended == scalar(
        db,
        "select count(*) from canonical.well_completions where source_id = %s",
        DIM_SOURCE,
    )
    assert set(manifests) == set(first.manifest_ids.values()) | set(second.manifest_ids.values())

    third = promote(db)
    assert third.promoted_rows == 0
    assert query(
        db,
        "select rows_examined, rows_appended from lineage.vintages where source_id = %s",
        DIM_SOURCE,
    ) == [(examined, appended)], "a re-run that appended nothing must leave the ledger alone"


def test_a_registry_with_no_staged_rows_is_reported_as_zero_rather_than_assumed_resolved(db,
                                                                                          staged):
    """`pod` has no 300-record fixture, so this run resolves none of its PODs against it. The
    resolution counts are published rather than inferred, and the promotion does not depend on
    them (cr_nm_wchistory_lease_identifier_1)."""
    report = promote(db)

    assert report.resolution["pod"] == 0
    assert report.promoted_rows > 0


# ---------------------------------------------------------------- 5.7 the ND serving path


def test_both_the_served_query_and_the_latest_view_filter_below_the_window(db, seeded):
    """P5.7's structural half, the half a fixture-sized container can prove. The served path
    (`select_production`) pushes api10 inside the window subquery, so the planner can use
    production_monthly_api10_idx. The view could not — api10 was missing from its PARTITION BY
    and it re-ranked the whole table for one well: 156,370 ms at 17,597,960 rows against
    1.3 ms served (work-output/d1-p5-status.md §7). Migration 031 put api10 in the PARTITION
    BY (DR-79), so the same size-independent property now holds for both paths."""
    served = _plan(db, nm_dims.SERVED_PRODUCTION_PROBE)
    view = _plan(
        db,
        "select * from canonical.production_monthly_latest where api10 = '3305301633'",
    )

    assert _api10_below_window(served), served
    assert _api10_below_window(view), view


def _plan(db: psycopg.Connection, sql: str) -> dict:
    with db.cursor() as cursor:
        cursor.execute(f"explain (format json) {sql}")
        return cursor.fetchone()[0][0]["Plan"]


def _api10_below_window(plan: dict) -> bool:
    """True when the api10 predicate is applied under the WindowAgg rather than over it."""

    def walk(node: dict, under_window: bool) -> bool:
        text = " ".join(
            str(node.get(key, "")) for key in ("Filter", "Index Cond", "Recheck Cond")
        )
        if "api10" in text and not under_window:
            return False
        window = under_window or node.get("Node Type") == "WindowAgg"
        return all(walk(child, window) for child in node.get("Plans", []))

    return walk(plan, under_window=False)


# ---------------------------------------------------------------- helpers


def _wchistory_with(**overrides: str) -> bytes:
    """One wchistory record with the named cells replaced, carrying every column the source
    declares — the parse directive halts on a column it does not know and quarantines the batch
    on one it is missing."""
    cells = {column: "1" for column in NM_COLUMNS["wchistory"]}
    cells.update(
        api_st_cde="30",
        api_cnty_cde="5",
        api_well_idn="1028",
        pool_idn="8559",
        eff_dte="2015-01-01T00:00:00",
        rec_termn_dte="9999-12-31T00:00:00",
        wc_stat_cde="A",
        ogrid_cde="28",
        spc_unit_idn="96200",
        prod_prop_idn="30041",
        well_nbr_idn="001 ",
    )
    cells.update(overrides)
    return synthetic_document([record_text(**cells)], tag="wchistory")


def _podwc_with(**overrides: str) -> bytes:
    """One podwc record, carrying every column the source declares."""
    cells = {column: "1" for column in NM_COLUMNS["podwc"]}
    cells.update(
        pod_idn="700001",
        api_st_cde="30",
        api_cnty_cde="5",
        api_well_idn="1028",
        pool_idn="8559",
        eff_dte="2015-01-01T00:00:00",
    )
    cells.update(overrides)
    return synthetic_document([record_text(**cells)], tag="podwc")


def _seed_well_months(db: psycopg.Connection) -> None:
    """A well-month count per completion, so the group sum has something exact to be exact
    about. Values are ordinal, not measured: the assertion is that grouping is lossless."""
    with db.cursor() as cursor:
        cursor.execute(
            "create temp table _well_months as"
            " select distinct completion_key,"
            "        (abs(hashtext(completion_key)) %% 97 + 1) as well_months"
            "   from canonical.well_completions where source_id = %s",
            (DIM_SOURCE,),
        )
    db.commit()


def test_every_dimension_rule_is_loaded_for_the_source_it_names(db, staged):
    """M5: rule_id carries one source_id and load_rules reads one at a time, so a rule seeded
    against the wrong source is invisible at the moment it is needed."""
    promote(db)
    for rule_id, source_id, stage_name in (
        ("cr_nm_wchistory_api10_1", "nm_ocd_wchistory", "conform"),
        ("cr_nm_wchistory_completion_key_1", "nm_ocd_wchistory", "conform"),
        ("cr_nm_podwc_pod_1", "nm_ocd_podwc", "join"),
        ("cr_nm_ogrid_registry_1", "nm_ocd_ogrid", "join"),
        (LEASE_RULE, "nm_ocd_wcproduction", "join"),
    ):
        loaded = {
            rule.rule_id for rule in load_rules(db, source_id=source_id, stage=stage_name)
        }
        assert rule_id in loaded, (rule_id, source_id, stage_name)
