from __future__ import annotations

from datetime import date
from decimal import Decimal

import polars as pl
import psycopg
import pytest
from psycopg.rows import dict_row

from glasswell.lengths import resolve_length_method
from glasswell.lineage.conformance import RULE_KINDS, apply_registry_rules, apply_rules, load_rules
from glasswell.seed import seed_all
from glasswell.seed.conformance_nd import ND_RULES
from glasswell.seed.formations_nd import FORMATION_ALIASES
from glasswell.seed.reference import NM_TABLES

MINIMUM_RULES = 17
MINIMUM_TERMS = 30
MEASURED_ND_STATUSES = 19
POLICY_RULES = (
    # The land-grid publisher choice: the executor is the ingest module the spec names, and
    # the measured cross-publisher divergence rides in spec.divergence_measured (M1-4).
    "cr_blm_plss_publisher_1",
    "cr_ff_completion_anchor_1",
    # M2-3's membership decision: which section a well belongs to, chosen with measured
    # evidence and executed by the metrics mart the spec names.
    "cr_land_agg_membership_1",
    "cr_nd_basin_1",
    "cr_nd_geometry_provenance_1",
    "cr_nd_liquids_policy_1",
    "cr_nd_neighbor_context_1",
    "cr_nd_neighbor_distance_1",
    "cr_nd_null_semantics_1",
    "cr_nd_pool_rollup_1",
    "cr_nd_well_type_disposal_1",
    # One host pin per NM source: the pin is a policy declaration the fetcher implements, and
    # a rule row loads only for the source_id it names (M5).
    *sorted(f"cr_nm_{table}_host_pin_1" for table, _ in NM_TABLES),
    # The producing definition: a window, a stream set and what counts as evidence. The
    # executor is the serving path named in each spec, which reads all three at request time.
    "cr_producing_evidence_1",
    "cr_producing_streams_1",
    "cr_producing_window_1",
    "cr_tx_allocation_scope_1",
    "cr_tx_ewa_role_1",
    "cr_tx_geometry_survivor_1",
    "cr_tx_identity_collapse_1",
    "cr_tx_lateral_bounds_1",
    "cr_tx_multi_wellbore_1",
)

SUPERSEDED_RULE_IDS = {rule["supersedes_rule_id"] for rule in ND_RULES if rule.get(
    "supersedes_rule_id")}
# A superseded row stays in the registry and stops being loaded, so it is not probed here.
EXECUTABLE_RULE_IDS = [
    rule["rule_id"]
    for rule in ND_RULES
    if rule["rule_kind"] != "code_ref" and rule["rule_id"] not in SUPERSEDED_RULE_IDS
]

VOLUMES = {"oil": [Decimal("259.000")], "wtr": [Decimal("845.000")], "gas": [Decimal("1885.000")]}
VOLUME_SCHEMA = dict.fromkeys(VOLUMES, pl.Decimal(18, 3))

# One row per rule, carrying exactly the columns that rule names (B4: a rule that cannot
# execute fails at 3am inside an ingest phase instead of here).
PROBE_FRAMES: dict[str, pl.DataFrame] = {
    "cr_nd_mpr_format_1": pl.DataFrame({"report_date": ["46082"]}),
    "cr_nd_api_identity_1": pl.DataFrame({"api_wellno": ["33053039010000"]}),
    "cr_nd_month_convention_1": pl.DataFrame({"report_date": ["46082"]}),
    "cr_nd_land_unit_1": pl.DataFrame(
        {"township": ["151"], "range": ["101"], "section": ["11"]}
    ),
    "cr_nd_volume_range_1": pl.DataFrame(VOLUMES, schema=VOLUME_SCHEMA),
    "cr_nd_confidential_1": pl.DataFrame({"pool": ["BAKKEN"]}),
    "cr_nd_days_range_1": pl.DataFrame({"days": [31]}),
    "cr_nd_entity_key_1": pl.DataFrame({"api10": ["3305302532"], "pool": ["DUPEROW"]}),
    "cr_nd_formation_group_1": pl.DataFrame({"formation_raw": ["BAKKEN"]}),
    "cr_nd_stream_vocab_1": pl.DataFrame({"api10": ["3305303901"], "stream_raw": ["Oil"]}),
    "cr_nd_units_1": pl.DataFrame(VOLUMES, schema=VOLUME_SCHEMA),
    "cr_nd_status_vocab_1": pl.DataFrame({"api": ["33043000020000"], "status": ["A"]}),
    "cr_nd_datum_1": pl.DataFrame({"latitude": [47.9075079], "longitude": [-103.5803537]}),
    "cr_nd_compute_crs_2": pl.DataFrame(
        {"linekey": ["33011003910000_LAT1"], "geom": ["LINESTRING(-103.5 47.9,-103.4 47.9)"]}
    ),
    "cr_nd_segment_vocab_1": pl.DataFrame({"segment": ["LAT"]}),
    "cr_nd_multilateral_1": pl.DataFrame(
        {"linekey": ["33011003910000_LAT1"], "lateral_ordinal": [1]}
    ),
    "cr_nd_survey_api_identity_1": pl.DataFrame({"api_wellno": ["33007001460000"]}),
    "cr_nd_survey_segment_vocab_1": pl.DataFrame({"well_sub": ["DIR"]}),
    "cr_nd_survey_station_order_1": pl.DataFrame(
        {"measdpth": ["4520.0"], "geom": ["POINT(-103.5027379 47.2394938)"]}
    ),
    "cr_nd_survey_station_range_1": pl.DataFrame(
        {
            "inclination_deg": [0.87],
            "azimuth_deg": [21.5],
            "true_vertical_depth_ft": [4519.56],
            "measured_depth_ft": [4520.0],
        }
    ),
    "cr_nd_survey_min_stations_1": pl.DataFrame({"station_count": [2]}),
    "cr_nd_survey_azimuth_reference_1": pl.DataFrame({"azimuth": [21.5]}),
}


@pytest.fixture
def seeded(db: psycopg.Connection) -> dict[str, int]:
    counts = seed_all(db)
    db.commit()
    return counts


def registry_rows(connection: psycopg.Connection) -> list[dict]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select rule_id, rule_kind, stage, rationale, evidence_url, spec, source_id,"
            "       supersedes_rule_id, effective_from"
            " from lineage.conformance_rules order by rule_id"
        )
        return cursor.fetchall()


def test_all_measured_nd_pool_labels_have_reviewed_vintaged_aliases(db, seeded):
    assert len(FORMATION_ALIASES) == 40
    with db.cursor() as cursor:
        cursor.execute(
            "select formation_raw, formation, formation_group, confidence, created_vintage"
            " from lineage.formation_aliases where source_id = 'nd_mpr_xlsx'"
        )
        aliases = {row[0]: row[1:] for row in cursor.fetchall()}
    assert set(aliases) == {row[0] for row in FORMATION_ALIASES}
    assert aliases["BAKKEN"][1] == "bakken"
    assert aliases["THREE FORKS"][1] == "three_forks"
    assert aliases["BAKKEN/THREE FORKS"][1] == "__other__"
    assert all(row[3] == date(2026, 8, 26) for row in aliases.values())


def test_alias_rule_hydration_resolves_the_latest_mapping_as_of_knowledge_time(db, seeded):
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, formation_group, confidence, effective_from, source_id,"
            " created_vintage) values"
            " ('BAKKEN', 'bakken', 'revised_bakken', 1.000, '2026-08-27', 'nd_mpr_xlsx',"
            " '2026-08-27')"
        )
    before = load_rules(db, source_id="nd_mpr_xlsx", stage="join", as_of=date(2026, 8, 26))[0]
    after = load_rules(db, source_id="nd_mpr_xlsx", stage="join", as_of=date(2026, 8, 27))[0]

    assert next(row for row in before.lookup if row["formation_raw"] == "BAKKEN")[
        "formation_group"
    ] == "bakken"
    assert next(row for row in after.lookup if row["formation_raw"] == "BAKKEN")[
        "formation_group"
    ] == "revised_bakken"


def test_alias_rule_hydration_does_not_leak_another_sources_mapping(db, seeded):
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, formation_group, confidence, effective_from, source_id,"
            " created_vintage) values"
            " ('BAKKEN', 'not_bakken', 'not_bakken', 1.000, '2026-08-28', 'tx_pdq_dsv',"
            " '2026-08-28')"
        )

    rule = load_rules(db, source_id="nd_mpr_xlsx", stage="join", as_of=date(2026, 8, 28))[0]

    assert next(row for row in rule.lookup if row["formation_raw"] == "BAKKEN")[
        "formation_group"
    ] == "bakken"


def test_alias_rule_hydration_prefers_its_source_over_a_newer_unscoped_fallback(db, seeded):
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, formation_group, confidence, effective_from, source_id,"
            " created_vintage) values"
            " ('BAKKEN', 'unscoped', 'unscoped', 1.000, '2026-08-29', null, '2026-08-29')"
        )

    rule = load_rules(db, source_id="nd_mpr_xlsx", stage="join", as_of=date(2026, 8, 29))[0]

    assert next(row for row in rule.lookup if row["formation_raw"] == "BAKKEN")[
        "formation_group"
    ] == "bakken"


def load_one(connection: psycopg.Connection, rule_id: str):
    declared = next(rule for rule in ND_RULES if rule["rule_id"] == rule_id)
    loaded = load_rules(
        connection, source_id=declared["source_id"], stage=declared["stage"]
    )
    return next(rule for rule in loaded if rule.rule_id == rule_id)


def test_the_registry_carries_the_nd_slice_rules(db, seeded):
    assert seeded["conformance_rules"] >= MINIMUM_RULES
    assert len(registry_rows(db)) >= MINIMUM_RULES


def test_every_seeded_rule_states_why_it_exists_and_cites_its_evidence(db, seeded):
    unevidenced = [
        row["rule_id"]
        for row in registry_rows(db)
        if not row["rationale"] or not row["evidence_url"]
    ]
    assert unevidenced == []


def test_every_seeded_rule_declares_a_stage_and_a_kind_the_spine_knows(db, seeded):
    for row in registry_rows(db):
        assert row["stage"] in ("parse", "validate", "conform", "join")
        assert row["rule_kind"] in RULE_KINDS


def test_every_executable_rule_is_probed_by_this_test_file():
    assert sorted(PROBE_FRAMES) == sorted(EXECUTABLE_RULE_IDS)


@pytest.mark.parametrize("rule_id", EXECUTABLE_RULE_IDS)
def test_every_executable_seeded_rule_runs_against_a_one_row_frame(db, seeded, rule_id):
    application = apply_rules(PROBE_FRAMES[rule_id], [load_one(db, rule_id)])
    assert application.applied_rule_ids == [rule_id]
    assert application.quarantined == []


def test_the_only_rules_without_an_executor_are_the_policy_declarations(db, seeded):
    declarations = tuple(
        row["rule_id"] for row in registry_rows(db) if row["rule_kind"] == "code_ref"
    )
    assert declarations == POLICY_RULES
    for row in registry_rows(db):
        if row["rule_kind"] == "code_ref":
            assert row["spec"]["module_function"].startswith("glasswell.")
            assert row["spec"]["contract_note"]


def test_a_conform_pass_that_forgets_to_drop_the_code_ref_rows_fails_loudly(db, seeded):
    frame = pl.DataFrame({"api10": ["3305302532"], "pool": ["DUPEROW"], "stream_raw": ["Oil"]})
    with pytest.raises(NotImplementedError, match="code_ref"):
        apply_registry_rules(db, frame, source_id="nd_mpr_xlsx", stage="conform")


def test_the_mpr_parse_stage_passes_the_real_header_and_quarantines_a_lost_column(db, seeded):
    header = pl.DataFrame(
        {
            "report_date": ["46082"],
            "api_wellno": ["33053039010000"],
            "township": ["151"],
            "range": ["101"],
            "section": ["11"],
        }
    )
    passed = apply_registry_rules(db, header, source_id="nd_mpr_xlsx", stage="parse")
    assert passed.quarantined == []
    assert passed.frame.height == 1

    lost = apply_registry_rules(
        db, header.drop("api_wellno"), source_id="nd_mpr_xlsx", stage="parse"
    )
    assert [batch.reason_code for batch in lost.quarantined] == ["schema_mismatch"]


def test_the_mpr_validate_stage_routes_an_impossible_volume_to_quarantine(db, seeded):
    frame = pl.DataFrame(
        {
            "oil": [Decimal("259.000"), Decimal("-3.000")],
            "wtr": [Decimal("845.000"), Decimal("1.000")],
            "gas": [Decimal("1885.000"), Decimal("2.000")],
            "days": [31, 31],
            "pool": ["BAKKEN", "BAKKEN"],
        },
        schema={**VOLUME_SCHEMA, "days": pl.Int64, "pool": pl.String},
    )
    application = apply_registry_rules(db, frame, source_id="nd_mpr_xlsx", stage="validate")
    assert application.frame.height == 1
    assert [batch.reason_code for batch in application.quarantined] == ["impossible_volume"]


def test_the_stream_vocabulary_promotes_three_streams_and_measures_the_dispositions(db, seeded):
    frame = pl.DataFrame({"stream_raw": ["Oil", "Wtr", "Gas", "GasSold", "Flared"]})
    application = apply_rules(frame, [load_one(db, "cr_nd_stream_vocab_1")])
    assert application.frame["stream_canonical"].to_list() == ["oil", "water", "gas"]
    batch = application.quarantined[0]
    assert batch.reason_code == "stream_not_promoted"
    assert batch.frame["stream_raw"].to_list() == ["GasSold", "Flared"]


def test_the_status_vocabulary_maps_a_measured_code_and_quarantines_an_unknown_one(db, seeded):
    frame = pl.DataFrame(
        {
            "api": ["33043000020000", "33053039010000", "33053039020000"],
            "status": ["A", "Confidential", "ZZ"],
            "latitude": [47.9, 48.1, 47.5],
            "longitude": [-103.5, -102.9, -103.1],
        }
    )
    rules = [
        rule
        for rule in load_rules(db, source_id="nd_gis_wells", stage="conform")
        # cr_nd_well_type_disposal_1 is a code_ref policy row with no executor; every real
        # consumer of this source drops the kind before applying (ingest/nd_gis.py), and the
        # forgets-to-drop failure mode has its own test above.
        if rule.rule_kind != "code_ref"
    ]
    application = apply_rules(frame, rules)
    assert application.frame["status_canonical"].to_list() == ["active", "confidential"]
    assert [batch.reason_code for batch in application.quarantined] == ["unknown_status"]


def test_the_status_map_carries_every_value_measured_in_the_shipped_dbf(db, seeded):
    with db.cursor() as cursor:
        cursor.execute("select count(*) from lineage.nd_status_map")
        assert cursor.fetchone()[0] == MEASURED_ND_STATUSES
        cursor.execute(
            "select status_canonical, confidential from lineage.nd_status_map"
            " where status = 'Confidential'"
        )
        assert cursor.fetchone() == ("confidential", True)


def test_the_compute_crs_for_the_williston_basin_is_pinned_to_utm_14n(db, seeded):
    with db.cursor() as cursor:
        cursor.execute(
            "select compute_epsg, storage_epsg from lineage.crs_registry where basin = 'williston'"
        )
        assert cursor.fetchone() == (32614, 4326)


def test_the_five_nd_sources_the_ingest_phases_fetch_are_registered(db, seeded):
    with db.cursor() as cursor:
        cursor.execute(
            "select source_id from lineage.sources where source_id like 'nd_%' order by source_id"
        )
        assert [row[0] for row in cursor.fetchall()] == [
            "nd_gis_directionals",
            "nd_gis_horizontals_line",
            "nd_gis_spacing_units",
            "nd_gis_wells",
            "nd_mpr_xlsx",
        ]


def test_the_survey_source_registers_the_publisher_s_own_licence_text(db, seeded):
    """SB-01 §1.1: the register carries the terms, not a summary of them — this one is quoted
    from the metadata inside the archive, which is the copy that travels with the bytes."""
    with db.cursor() as cursor:
        cursor.execute(
            "select license_note, redistributable from lineage.sources where source_id = %s",
            ("nd_gis_directionals",),
        )
        note, redistributable = cursor.fetchone()

    assert "warrants the accuracy, reliability or timeliness" in note
    assert "does so at his or her own risk" in note
    # The honest reading: a warranty disclaimer grants nothing.
    assert redistributable is False
    # The 313.6 MB geodatabase is redundant with this artifact and is not on the pull schedule.
    assert "NDOGD_Surveys.gdb.zip" in note
    assert "confidential" in note


def test_the_glossary_reaches_the_database_with_its_cut_line_floor(db, seeded):
    assert seeded["glossary_terms"] >= MINIMUM_TERMS
    with db.cursor() as cursor:
        cursor.execute("select count(*) from canonical.glossary_terms")
        assert cursor.fetchone()[0] >= MINIMUM_TERMS
        cursor.execute(
            "select term_id, highlightable from canonical.glossary_terms where term = 'Stream'"
        )
        assert cursor.fetchone() == ("gt_stream", False)


def test_seeding_a_database_that_is_already_seeded_changes_nothing(db, seeded):
    tables = (
        "lineage.conformance_rules",
        "lineage.sources",
        "lineage.crs_registry",
        "canonical.glossary_terms",
        "features.feature_specs",
    )
    with db.cursor() as cursor:
        cursor.execute(" union all ".join(f"select count(*) from {t}" for t in tables))
        before = cursor.fetchall()

    assert seed_all(db) == seeded
    db.commit()

    with db.cursor() as cursor:
        cursor.execute(" union all ".join(f"select count(*) from {t}" for t in tables))
        assert cursor.fetchall() == before


def test_the_compute_crs_rule_was_superseded_and_the_old_row_was_not_edited(db, seeded):
    """R8: the UTM-14N row stays in the registry exactly as written (fp-audit A3-F1)."""
    registry = {row["rule_id"]: row for row in registry_rows(db)}

    assert registry["cr_nd_compute_crs_1"]["spec"]["compute_epsg"] == 32614
    successor = registry["cr_nd_compute_crs_2"]
    assert successor["supersedes_rule_id"] == "cr_nd_compute_crs_1"
    assert successor["spec"]["length_method"] == "geodesic"
    assert successor["effective_from"] > registry["cr_nd_compute_crs_1"]["effective_from"]
    assert "A3-F1" in successor["rationale"]


def test_only_the_superseding_rule_is_loaded_for_the_laterals_source(db, seeded):
    loaded = [
        rule.rule_id
        for rule in load_rules(db, source_id="nd_gis_horizontals_line")
        if rule.rule_family == "cr_nd_compute_crs"
    ]

    assert loaded == ["cr_nd_compute_crs_2"]


def test_the_active_length_method_is_zone_free(db, seeded):
    method = resolve_length_method(db)

    assert (method.rule_id, method.method, method.compute_epsg) == (
        "cr_nd_compute_crs_2",
        "geodesic",
        None,
    )
