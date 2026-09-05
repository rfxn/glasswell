"""The nine R8 rows the allocation is made of, and what each of them has to say.

R8 is the reason these are assertions rather than comments: a mapping decision that exists only
in code fails review, so every decision the parser, the promotion and the mart make is a row
with a rationale, an evidence URL and an effective date, and this is what holds the rows to the
decisions they claim to carry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from glasswell.seed.conformance_tx import (
    ALLOCATION_MODEL_ID,
    ALLOCATION_RULES,
    EFFECTIVE_FROM,
    PDQ_EFFECTIVE_FROM,
    PDQ_FORMAT_MEASURED_ON,
    PDQ_MEMBER_LAYOUT,
    TX_RULES,
)

TRACK_RULE_IDS = (
    "cr_tx_pdq_format_1",
    "cr_tx_pdq_scope_1",
    "cr_tx_production_grain_1",
    "cr_tx_pdq_crosswalk_1",
    "cr_tx_allocation_v0_1",
    "cr_alloc_v0_error_bounds_1",
    "cr_tx_liquids_basis_1",
    "cr_tx_gas_basis_1",
    "cr_tx_geometry_provenance_1",
)

BY_ID = {
    str(rule["rule_id"]): rule for rule in (*TX_RULES, *ALLOCATION_RULES)
}


def test_the_track_registers_nine_rules() -> None:
    assert sorted(rule for rule in TRACK_RULE_IDS if rule in BY_ID) == sorted(TRACK_RULE_IDS)
    assert len(TRACK_RULE_IDS) == 9


@pytest.mark.parametrize("rule_id", TRACK_RULE_IDS)
def test_every_rule_carries_a_rationale_an_evidence_url_and_this_track_s_clock(
    rule_id: str,
) -> None:
    rule = BY_ID[rule_id]

    assert len(str(rule["rationale"])) > 200
    assert str(rule["evidence_url"]).startswith("https://")
    assert rule["effective_from"] == PDQ_EFFECTIVE_FROM


def test_the_grain_rule_supersedes_the_disclosure_it_replaces() -> None:
    """cr_tx_allocation_scope_1 said no well-level TX volume would be served until allocation
    shipped. It has shipped, so the row is superseded rather than deleted: lineage.
    conformance_rules is append-only and an as_of before this train still resolves the old
    disclosure."""
    grain = BY_ID["cr_tx_production_grain_1"]
    superseded = next(
        rule for rule in TX_RULES if rule["rule_id"] == "cr_tx_allocation_scope_1"
    )

    assert grain["supersedes_rule_id"] == "cr_tx_allocation_scope_1"
    assert grain["effective_from"] > superseded.get("effective_from", EFFECTIVE_FROM)


def test_the_third_spec_key_is_what_lets_one_predicate_have_two_consumers() -> None:
    """M-7. `_LEASE_REPORTING` must stop returning Texas so the card renders a chart, while
    `_NO_WELL_SERIES_STATES` must keep returning it so the producing class stays unknown. The
    successor matches the same reporting_level predicate, so the divergence is a third key."""
    spec = BY_ID["cr_tx_production_grain_1"]["spec"]

    assert spec["reporting_level"] == "lease"
    assert spec["allocation_required"] is True
    assert spec["well_level_production_served"] is True


def test_the_completeness_lag_is_the_commissions_own_sentence() -> None:
    spec = BY_ID["cr_tx_production_grain_1"]["spec"]

    assert spec["completeness_lag_months"] == 6
    assert spec["no_water_stream"] is True


def test_the_allocation_rule_carries_no_scope_numbers() -> None:
    """N-2. The EWA scale figures are measured on another file and live in the rule that
    measured them; the PDQ in-scope counts are measured by the load and land dated in
    marts.tx_allocation_census. A count inside a rule row cannot be re-measured."""
    rendered = repr(BY_ID["cr_tx_allocation_v0_1"]["spec"])

    for figure in ("207,094", "283,043", "359,421", "78,579", "3.39"):
        assert figure not in rendered


def test_the_allocation_rule_states_the_method_the_bound_and_the_refusal() -> None:
    spec = BY_ID["cr_tx_allocation_v0_1"]["spec"]

    assert spec["allocation_model_id"] == ALLOCATION_MODEL_ID
    assert spec["remainder_to"] == "lowest_api10"
    assert spec["error_source"] == "cr_alloc_v0_error_bounds_1"
    assert spec["error_bounds_outcome_v0"] == "not_measured"
    assert spec["as_of_supported"] is False
    assert spec["unallocated_share_degraded_at"] == 0.005
    assert set(spec["allocation_classes"]) == {
        "observed_gas_well",
        "observed_single_well_lease",
        "allocated_equal_share",
        "allocated_after_status_change",
        "excluded_after_plug",
        "unallocated",
    }


def test_the_allocated_cumulative_states_its_basis_on_the_rule_that_admits_it() -> None:
    """R-1. Texas enters the cumulative mart on an allocated basis, and the rule that admits it
    is the rule that says so — the coverage block quotes this, not the mart's own opinion."""
    spec = BY_ID["cr_tx_allocation_v0_1"]["spec"]

    assert spec["cumulatives_grain"] == "well"
    assert spec["cumulatives_basis"] == "allocated"


def test_the_eligibility_predicate_bounds_on_a_date_and_labels_on_a_status() -> None:
    """M-18. A filed plug date is a dated fact and bounds; a plugged status with no date is a
    snapshot and does not. Refusing to filter on a today-snapshot and refusing to label with
    one are two different decisions, and v0 makes only the first."""
    spec = BY_ID["cr_tx_allocation_v0_1"]["spec"]

    assert "plug_date is null or the production month is on or before it" in spec["eligibility"]
    assert spec["eligibility_source"] == "canonical.wells_latest"
    assert spec["undated_plugged"].startswith("eligible")
    assert spec["redistribute_excluded"] is True


def test_the_error_rule_is_montanas_by_source_and_no_states_by_id() -> None:
    """N-28. A rule row cannot be sourceless and the study's evidence is Montana's files, so
    the id is jurisdiction-neutral while the source is Montana — the shape
    cr_mt_pru_reconciliation_1 already has."""
    rule = BY_ID["cr_alloc_v0_error_bounds_1"]

    assert rule["source_id"] == "mt_bogc_pru_production"
    assert rule["spec"]["bed_jurisdiction"] == "MT"
    assert rule["spec"]["bed_entity_predicate"] == "entity_type='well'"
    assert rule["spec"]["precondition_rule"] == "cr_mt_pru_reconciliation_1"
    assert rule["spec"]["transfer_outcome"] == "not_measured"


def test_the_statistic_is_bounded_and_defined_where_a_well_produced_nothing() -> None:
    """N-7. A relative error is unbounded above and undefined at zero truth, which is the
    commonest case rather than an edge."""
    spec = BY_ID["cr_alloc_v0_error_bounds_1"]["spec"]

    assert spec["statistic"] == "(allocated - truth) / (allocated + truth)"
    assert spec["statistic_range"] == [-1, 1]


def test_the_liquids_and_gas_bases_are_disjoint_populations_not_a_sum_of_overlaps() -> None:
    liquids = BY_ID["cr_tx_liquids_basis_1"]["spec"]
    gas = BY_ID["cr_tx_gas_basis_1"]["spec"]

    assert liquids["basis"] == "oil+condensate"
    assert liquids["disjoint_on"] == "OIL_GAS_CODE"
    assert liquids["mart_stream"] == "liquid"
    assert gas["basis"] == "gas_well_gas+casinghead"
    assert gas["never_summed"] == ["LEASE_GAS_LIFT_INJ_VOL", "LEASE_CSGD_GAS_LIFT"]


def test_the_parse_refuses_a_header_change_rather_than_quarantining_a_row() -> None:
    """NIT-6. A schema change invalidates the row mapping rather than one row, so nothing
    failed to parse: the file stopped being the file the rule describes."""
    spec = BY_ID["cr_tx_pdq_format_1"]["spec"]

    assert spec["on_header_change"] == "refuse"
    assert spec["member_selection"] == "by_name"
    assert len(spec["members_read"]) == 6
    assert "OG_COUNTY_LEASE_CYCLE_DATA_TABLE.dsv" in spec["members_excluded"]


def test_the_layout_the_founding_row_left_in_code_is_a_row_of_its_own() -> None:
    """R8. cr_tx_pdq_format_1 named the members and the refuse policy and carried no column
    list, so the header the parse was judged against lived only in the parser. The restatement
    carries it, and _1 is superseded rather than edited."""
    founding = BY_ID["cr_tx_pdq_format_1"]
    restated = BY_ID["cr_tx_pdq_format_2"]

    assert "members" not in founding["spec"]
    assert restated["supersedes_rule_id"] == "cr_tx_pdq_format_1"
    assert restated["effective_from"] == PDQ_FORMAT_MEASURED_ON > founding["effective_from"]
    assert sorted(restated["spec"]["members"]) == sorted(founding["spec"]["members_read"])


def test_the_completion_member_carries_the_sixteen_columns_that_were_measured() -> None:
    """The transcribed 13 were three short. All 13 the parser consumes are present; the three
    it never read sit at positions 8, 9 and 10, which is why a width check was the only thing
    between a sixteen-column row and thirteen columns of it."""
    member = BY_ID["cr_tx_pdq_format_2"]["spec"]["members"][
        "OG_WELL_COMPLETION_DATA_TABLE.dsv"
    ]

    assert member["header"] == [
        "OIL_GAS_CODE", "DISTRICT_NO", "LEASE_NO", "WELL_NO", "API_COUNTY_CODE",
        "API_UNIQUE_NO", "ONSHORE_ASSC_CNTY", "DISTRICT_NAME", "COUNTY_NAME",
        "OIL_WELL_UNIT_NO", "WELL_ROOT_NO", "WELLBORE_SHUTIN_DT", "WELL_SHUTIN_DT",
        "WELL_14B2_STATUS_CODE", "WELL_SUBJECT_14B2_FLAG", "WELLBORE_LOCATION_CODE",
    ]
    assert len(member["consumed"]) == 13
    unread = [column for column in member["header"] if column not in member["consumed"]]
    assert unread == ["DISTRICT_NAME", "COUNTY_NAME", "OIL_WELL_UNIT_NO"]


@pytest.mark.parametrize("member", sorted(PDQ_MEMBER_LAYOUT))
def test_every_consumed_column_is_a_column_of_that_member_s_own_header(member: str) -> None:
    """A consumed column that is not in the header is a mapping to a field that does not exist,
    and the parse would read it as a KeyError rather than as a refusal naming the rule."""
    layout = BY_ID["cr_tx_pdq_format_2"]["spec"]["members"][member]

    assert [column for column in layout["consumed"] if column not in layout["header"]] == []
    assert layout["consumed"] == [
        column for column in layout["header"] if column in layout["consumed"]
    ]


def test_the_county_member_is_listed_read_and_consumed_by_nobody() -> None:
    """cr_tx_pdq_format_1 lists six members read and the parse opens five. The sixth is carried
    with an empty consumed set rather than dropped, because the county allowlist is
    cr_tx_pdq_scope_1's own row and a second copy of it here would be the R8 defect again."""
    members = BY_ID["cr_tx_pdq_format_2"]["spec"]["members"]

    assert members["GP_COUNTY_DATA_TABLE.dsv"]["consumed"] == []
    assert [
        member for member, layout in members.items() if not layout["consumed"]
    ] == ["GP_COUNTY_DATA_TABLE.dsv"]


def test_the_restatement_states_the_measurement_that_produced_it() -> None:
    """A restatement whose rationale does not say what was measured is a second assertion, not
    a correction: the byte count, the sha and the row count are how a reader checks it."""
    rationale = str(BY_ID["cr_tx_pdq_format_2"]["rationale"])

    for measured in ("2026-09-04", "3,652,221,981", "add29ef717e430e0", "820,718"):
        assert measured in rationale


def test_the_restatement_is_published_before_it_is_seeded() -> None:
    """049's trigger refuses a conformance rule whose publication is not registered, so the row
    and its evidence ship in one commit or the seeder raises on a fresh database."""
    migrations = Path(__file__).resolve().parents[2] / "src/glasswell/db/migrations"
    published = [
        path.name for path in sorted(migrations.glob("*.sql"))
        if "'cr_tx_pdq_format_2'" in path.read_text(encoding="utf-8")
    ]

    assert published == ["081_tx_pdq_format.sql"]


def test_the_county_scope_is_applied_at_promotion_and_counted_not_quarantined() -> None:
    """M-4. OG_LEASE_CYCLE has no county, so the in-scope lease set is derived from the
    crosswalk and the exclusion is an audit event: nothing about an out-of-scope row failed."""
    spec = BY_ID["cr_tx_pdq_scope_1"]["spec"]

    assert spec["scope_applied_at"] == "promotion"
    assert spec["quarantine"] is False
    assert spec["excluded_rows_recorded_as"].startswith("audit event staging.scope_excluded")


def test_the_crosswalk_keys_on_the_district_number_and_never_on_its_name() -> None:
    """GP_DISTRICT carries two vocabularies: district 10 is named 08 and district 08 is named
    7B, so a join on the name silently crosses districts."""
    spec = BY_ID["cr_tx_pdq_crosswalk_1"]["spec"]

    assert spec["district_key"] == "DISTRICT_NO"
    assert spec["district_map"]["10"] == "08"
    assert spec["district_map"]["08"] == "7B"
    assert spec["pad"] == {"lease_no": 6}


def test_membership_is_a_vintage_snapshot_that_retro_deletes_nothing() -> None:
    """M-5. canonical.well_lease_links has no effective_to and no month grain, so membership
    cannot be a per-month fact; resolution is greatest-effective_from and history accretes."""
    spec = BY_ID["cr_tx_pdq_crosswalk_1"]["spec"]

    assert spec["membership_grain"] == "snapshot_at_export_vintage"
    assert spec["retro_delete"] is False
    assert spec["link_role"] == "canonical_crosswalk"


def test_texas_geometry_provenance_is_served_verbatim_and_names_the_arc_for_what_it_is() -> None:
    """Texas had no registered geometry-provenance decision, so the card fell back to a
    default and a filed cartographic line could read as a survey-derived path."""
    spec = BY_ID["cr_tx_geometry_provenance_1"]["spec"]

    assert spec["jurisdiction"] == "TX"
    assert spec["survey_derived"] is False
    assert "cartographic line" in spec["geom_types"]["lateral"]
