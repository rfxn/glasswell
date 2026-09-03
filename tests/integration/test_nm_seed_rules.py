"""The NM promotion registry: every mapping decision the spine will cite, executed here first.

A rule row is immutable and is served at `/v1/conformance`, so a wrong one is a correction
with a date rather than an edit (R8). These tests run each row against a one-row frame before
any of them meets 48.1M, and pin the two decisions that would be silently wrong at scale: the
per-segment pad that builds the API-10, and the trimmed code that maps `'O '` to oil.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl
import psycopg
import pytest

from glasswell.ingest.xml_stream import stream_records
from glasswell.lineage.conformance import apply_registry_rules, apply_rules, load_rules
from glasswell.seed import seed_all
from glasswell.seed.conformance_nm import NM_PROMOTION_RULES, NM_RULES, RECORD_NAMESPACE
from glasswell.seed.conformance_nm_wells import NM_WELLS_GIS_RULES, NM_WELLS_RULES
from glasswell.seed.reference import NM_TABLES

NM_SOURCE_IDS = tuple(f"nm_ocd_{table}" for table, _ in NM_TABLES)
SPINE_SOURCE = "nm_ocd_wcproduction"
FIXTURE = Path(__file__).parents[1] / "fixtures" / "nm_ocd" / "nm_wcproduction_300.xml"
NAMESPACE = RECORD_NAMESPACE

# The 2015-01 oil row of 30-005-01028 in pool 8559, verbatim from
# tests/fixtures/nm_ocd/nm_wcproduction_300.xml: county 5 is one digit and the well number
# four, so the fixture's own record is the padding case.
OIL_ROW = {
    "api_st_cde": "30",
    "api_cnty_cde": "5",
    "api_well_idn": "1028",
    "pool_idn": "8559",
    "prd_knd_cde": "O ",
    "prod_amt": "79",
}
OIL_API10 = "3000501028"

# The one record in 48,104,334 whose api_well_idn is six characters (SOURCE.md, T1-d).
OVERWIDE_WELL = ("30", "15", "256350")
# The registered operator the ogrid fixture opens with, name trimmed of its CHAR(44) padding.
PROBE_OGRID = ("28", "A A OILFIELD SERVICE INC")

DECLARATION_FRAME = pl.DataFrame({"source_row_ordinal": [0]})

PROBE_FRAMES: dict[str, pl.DataFrame] = {
    "cr_nm_wcproduction_api10_1": pl.DataFrame(
        {key: [OIL_ROW[key]] for key in ("api_st_cde", "api_cnty_cde", "api_well_idn")}
    ),
    "cr_nm_wcproduction_entity_key_1": pl.DataFrame(
        {"api10": [OIL_API10], "pool_idn": [OIL_ROW["pool_idn"]]}
    ),
    "cr_nm_wcproduction_county_parity_1": pl.DataFrame(
        {"api_st_cde": ["30"], "api_cnty_cde": [OIL_ROW["api_cnty_cde"]]}
    ),
    "cr_nm_wcproduction_stream_vocab_1": pl.DataFrame({"stream_raw": ["O"]}),
    "cr_nm_wcproduction_units_1": pl.DataFrame(
        {"prod_amt": [Decimal("79.000")]}, schema={"prod_amt": pl.Decimal(18, 3)}
    ),
    "cr_nm_wcproduction_volume_range_1": pl.DataFrame(
        {"prod_amt": [Decimal("79.000")]}, schema={"prod_amt": pl.Decimal(18, 3)}
    ),
    "cr_nm_ogrid_operator_1": pl.DataFrame({"operator_raw": [PROBE_OGRID[0]]}),
    "cr_nm_wcproduction_amend_ind_1": DECLARATION_FRAME,
    "cr_nm_wcproduction_flare_property_1": DECLARATION_FRAME,
    "cr_nm_wcproduction_liquids_1": DECLARATION_FRAME,
    "cr_nm_wcproduction_null_semantics_1": DECLARATION_FRAME,
    "cr_nm_wcproduction_restatement_1": DECLARATION_FRAME,
    "cr_nm_wcproduction_status_vocab_1": DECLARATION_FRAME,
    "cr_nm_wcproduction_collision_1": DECLARATION_FRAME,
    "cr_nm_wcproduction_days_1": DECLARATION_FRAME,
    "cr_nm_wcproduction_window_1": DECLARATION_FRAME,
    "cr_nm_pool_vocab_1": DECLARATION_FRAME,
    "cr_nm_wchistory_status_vocab_1": DECLARATION_FRAME,
}

EXECUTABLE_RULE_IDS = sorted(
    str(rule["rule_id"]) for rule in NM_PROMOTION_RULES if rule["rule_kind"] != "code_ref"
)
DECLARATION_RULE_IDS = sorted(
    str(rule["rule_id"])
    for rule in NM_PROMOTION_RULES
    if rule["spec"].get("asserts_header") is False
)


@pytest.fixture
def seeded(db: psycopg.Connection) -> psycopg.Connection:
    seed_all(db)
    with db.cursor() as cursor:
        # The operator registry is promoted from the staged ogrid rows, which is P5's work.
        # One real row from the fixture is what gives cr_nm_ogrid_operator_1 a key to hit.
        cursor.execute(
            "insert into lineage.operator_aliases"
            " (operator_raw, operator, confidence, effective_from, source_id)"
            " values (%s, %s, 1.000, %s, 'nm_ocd_ogrid')",
            (*PROBE_OGRID, date(2026, 8, 21)),
        )
    db.commit()
    return db


def rule_row(rule_id: str) -> dict:
    return next(rule for rule in NM_PROMOTION_RULES if rule["rule_id"] == rule_id)


def load_one(connection: psycopg.Connection, rule_id: str):
    declared = rule_row(rule_id)
    loaded = load_rules(
        connection, source_id=str(declared["source_id"]), stage=str(declared["stage"])
    )
    return next(rule for rule in loaded if rule.rule_id == rule_id)


def nm_rows(connection: psycopg.Connection) -> list[tuple]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select rule_id, source_id, stage, rule_kind, rationale, evidence_url"
            " from lineage.conformance_rules where source_id like 'nm\\_ocd\\_%%'"
            # A cadence rule is filed under the source its job polls, so it carries an
            # nm_ocd_ id without being one of New Mexico's conformance decisions. It is the
            # scheduler registry's row and its own gates hold it.
            "   and stage <> 'schedule'"
            " order by rule_id"
        )
        return cursor.fetchall()


def conform(connection: psycopg.Connection, frame: pl.DataFrame):
    return apply_registry_rules(connection, frame, source_id=SPINE_SOURCE, stage="conform")


def test_every_nm_source_carries_at_least_one_rule_under_its_own_source_id(seeded):
    """M5: rule_id is a primary key holding one source_id, and load_rules reads one at a time,
    so a sibling with no row of its own would trip P4.7's every-promotion-cites-a-rule check."""
    loaded = {source: load_rules(seeded, source_id=source) for source in NM_SOURCE_IDS}

    assert {source: len(rules) for source, rules in loaded.items() if not rules} == {}
    for source, rules in loaded.items():
        assert {rule.source_id for rule in rules} == {source}


def test_a_rule_is_invisible_to_the_source_it_does_not_name(seeded):
    pool_rules = {rule.rule_id for rule in load_rules(seeded, source_id="nm_ocd_pool")}

    assert "cr_nm_pool_vocab_1" in pool_rules
    assert "cr_nm_wcproduction_api10_1" not in pool_rules


def test_every_rule_id_names_the_table_its_source_id_holds(seeded):
    """P3.0's convention: cr_nm_<table>_<family>_N, never an unprefixed global rule."""
    misfiled = [
        (rule_id, source_id)
        for rule_id, source_id, *_ in nm_rows(seeded)
        if not rule_id.startswith(f"cr_nm_{source_id.removeprefix('nm_ocd_')}_")
    ]

    assert misfiled == []


def test_no_nm_rule_ships_an_empty_rationale_or_evidence_url(seeded):
    """m2. A rule with no rationale is a mapping decision with no reason, which is the thing
    R8 exists to prevent - and it is served to a reader at /v1/conformance."""
    rows = nm_rows(seeded)
    unevidenced = [
        rule_id
        for rule_id, _, _, _, rationale, evidence_url in rows
        if not (rationale or "").strip() or not (evidence_url or "").strip()
    ]

    # A filter over an empty read passes without reading anything. The well-header rules carry
    # nm_ocd_ source ids too, so this read is both seeders' output.
    assert len(rows) == len(NM_RULES) + len(NM_WELLS_RULES) + len(NM_WELLS_GIS_RULES)
    assert unevidenced == []


def test_every_executable_nm_promotion_rule_is_probed_by_this_file():
    assert sorted(PROBE_FRAMES) == EXECUTABLE_RULE_IDS


@pytest.mark.parametrize("rule_id", EXECUTABLE_RULE_IDS)
def test_every_executable_seeded_rule_runs_against_a_one_row_frame(seeded, rule_id):
    application = apply_rules(PROBE_FRAMES[rule_id], [load_one(seeded, rule_id)])

    assert application.applied_rule_ids == [rule_id]
    assert application.quarantined == []


@pytest.mark.parametrize("rule_id", DECLARATION_RULE_IDS)
def test_a_declaration_passes_the_frame_through_rather_than_asserting_a_header(seeded, rule_id):
    """A parse_directive that names frame columns becomes a header assertion, and a header
    assertion quarantines the whole batch the day a later phase projects a column away - the
    failure the retrieval rules already had to be filtered out of apply_rules to avoid."""
    application = apply_rules(DECLARATION_FRAME, [load_one(seeded, rule_id)])

    assert application.frame.to_dicts() == DECLARATION_FRAME.to_dicts()
    assert application.quarantined == []
    assert application.applied_rows[rule_id] == 0


def test_the_api10_pads_each_segment_to_its_own_width(seeded):
    """M3. The segments arrive unpadded and each pads to its own width: concatenating first
    and padding the result builds 0003051028, which is a different well."""
    frame = pl.DataFrame({key: [value] for key, value in OIL_ROW.items()})
    unpadded = "".join(OIL_ROW[key] for key in ("api_st_cde", "api_cnty_cde", "api_well_idn"))

    application = apply_rules(frame, [load_one(seeded, "cr_nm_wcproduction_api10_1")])

    assert application.frame["api10"].to_list() == [OIL_API10]
    assert unpadded.zfill(10) == "0003051028"


def test_the_one_six_digit_well_number_quarantines_rather_than_building_an_eleven_digit_key(
    seeded,
):
    """D1-P3 MUST-INHERIT, asserted on the row it was measured on: 30-15-256350, ordinal
    15,226,075 of 48,104,334. zfill does not truncate, so a pad-and-hope rule emits an
    eleven-character API-10; SQL's lpad truncates to 25635, which is a real well carrying 487
    rows of its own. The seeded rule refuses the segment instead."""
    state, county, well = OVERWIDE_WELL
    frame = pl.DataFrame(
        {"api_st_cde": [state], "api_cnty_cde": [county], "api_well_idn": [well]}
    )

    application = apply_rules(frame, [load_one(seeded, "cr_nm_wcproduction_api10_1")])

    assert application.frame.is_empty()
    assert [batch.reason_code for batch in application.quarantined] == ["key_incomplete"]
    assert application.quarantined[0].frame["api_well_idn"].to_list() == ["256350"]


def test_a_segment_that_is_not_digits_is_refused_at_a_width_that_would_have_passed(seeded):
    """The TX re-gate's standing residual, closed on the source it was raised for: pad and
    min_width judge length, so a letter O typed for a zero is four characters like any other
    four and would have keyed 3000501O28 as a well."""
    frame = pl.DataFrame(
        {"api_st_cde": ["30"], "api_cnty_cde": ["5"], "api_well_idn": ["1O28"]}
    )

    application = apply_rules(frame, [load_one(seeded, "cr_nm_wcproduction_api10_1")])

    assert application.frame.is_empty()
    assert [batch.reason_code for batch in application.quarantined] == ["key_incomplete"]


def test_an_even_county_code_promotes_because_the_rule_forbids_parity_filtering(seeded):
    """E9. Cibola is 30-006 and Los Alamos 30-028; the evidence that NM county codes are odd
    is LIKELY, not VERIFIED, so the rule asserts the shape and admits every code the shape
    admits. A parity filter would look correct on the spine and delete Cibola in silence."""
    frame = pl.DataFrame(
        {
            "api_st_cde": ["30"],
            "api_cnty_cde": ["6"],
            "api_well_idn": ["1028"],
            "prod_amt": [Decimal("79.000")],
        },
        schema_overrides={"prod_amt": pl.Decimal(18, 3)},
    )

    validated = apply_registry_rules(seeded, frame, source_id=SPINE_SOURCE, stage="validate")
    keyed = apply_rules(validated.frame, [load_one(seeded, "cr_nm_wcproduction_api10_1")])

    assert validated.quarantined == [], "30-006 (Cibola, even) must not be filtered on parity"
    assert keyed.frame["api10"].to_list() == ["3000601028"]


def test_an_api_that_is_not_new_mexicos_leaves_under_the_reason_the_state_gives_it(seeded):
    frame = pl.DataFrame(
        {
            "api_st_cde": ["33", "30"],
            "api_cnty_cde": ["053", "5"],
            "prod_amt": [Decimal("1.000"), Decimal("79.000")],
        },
        schema_overrides={"prod_amt": pl.Decimal(18, 3)},
    )

    application = apply_registry_rules(seeded, frame, source_id=SPINE_SOURCE, stage="validate")

    assert application.frame["api_st_cde"].to_list() == ["30"]
    assert [batch.reason_code for batch in application.quarantined] == ["parse_error"]


def test_an_oil_row_promotes_as_oil_through_the_trim_its_rule_declares(seeded):
    """B5 end to end. Staging holds the CHAR(2) 'O ', the trim is a rule row rather than a
    .strip() in the parser, and an exact match against the padded value would have quarantined
    100% of the spine as stream_not_promoted while every rule reported success."""
    parse_rules = load_rules(seeded, source_id=SPINE_SOURCE, stage="parse")
    trim = next(
        rule for rule in parse_rules if rule.rule_id == "cr_nm_wcproduction_pad_1"
    ).spec["trim"]["prd_knd_cde"]
    staged = pl.DataFrame({key: [value] for key, value in OIL_ROW.items()})
    frame = staged.with_columns(
        pl.col("prd_knd_cde").str.strip_chars_end(trim["char"]).alias("stream_raw"),
        # Staging is verbatim text; the numeric cast belongs to the promotion, and
        # cr_nm_wcproduction_units_1 quantises what it is handed.
        pl.col("prod_amt").cast(pl.Decimal(18, 3)),
    )

    application = conform(seeded, frame)

    assert trim == {"width": 2, "side": "right", "char": " "}
    assert application.frame["stream_raw"].to_list() == ["O"]
    assert application.frame["stream_canonical"].to_list() == ["oil"]
    assert application.frame["api10"].to_list() == [OIL_API10]
    assert application.frame["entity_key"].to_list() == [f"{OIL_API10}:{OIL_ROW['pool_idn']}"]
    assert application.frame["prod_amt"].to_list() == [Decimal("79.000")]
    assert application.quarantined == []


def test_the_conform_pass_keys_and_maps_every_record_of_the_fixture(seeded):
    """The rules meet 300 real records before they meet 48.1M: every one is keyed, every
    stream is mapped, and nothing is quarantined. A quarantine share here is the rules being
    wrong rather than the data - the spine has no blank key component and no null volume."""
    with FIXTURE.open("rb") as handle:
        batches = list(
            stream_records(handle, record_tag="wcproduction", namespace=NAMESPACE)
        )
    staged = pl.concat(batches)
    frame = staged.with_columns(
        pl.col("prd_knd_cde").str.strip_chars_end(" ").alias("stream_raw"),
        pl.col("prod_amt").cast(pl.Decimal(18, 3)),
    )

    application = conform(seeded, frame)
    keyed = application.frame

    assert staged.height == 300
    assert application.quarantined == []
    assert keyed.height == 300
    assert keyed["api10"].str.len_chars().to_list() == [10] * 300
    assert set(keyed["api10"].str.slice(0, 2).to_list()) == {"30"}
    assert dict(
        sorted(keyed["stream_canonical"].value_counts().iter_rows())
    ) == {"gas": 149, "oil": 45, "water": 106}
    assert keyed["entity_key"].n_unique() == keyed.select("api10", "pool_idn").n_unique()


def test_the_untrimmed_code_is_what_the_map_refuses(seeded):
    """The same row keyed on the padded value: one rule row is all that stands between the
    spine and a silent 100% quarantine."""
    frame = pl.DataFrame({"stream_raw": ["O "]})

    application = apply_rules(frame, [load_one(seeded, "cr_nm_wcproduction_stream_vocab_1")])

    assert application.frame.is_empty()
    assert [batch.reason_code for batch in application.quarantined] == ["stream_not_promoted"]


def test_the_stream_map_carries_the_fourth_code_no_promotion_window_would_have_seen(seeded):
    """'C ' is 3,398 rows and every one of them is 1986-1993, so a vocabulary measured on the
    2015-01 window would quarantine them all on the day the window widens (P2 MUST-KNOW 3)."""
    frame = pl.DataFrame({"stream_raw": ["C", "G", "O", "W"]})

    application = apply_rules(frame, [load_one(seeded, "cr_nm_wcproduction_stream_vocab_1")])

    assert application.frame["stream_canonical"].to_list() == [
        "condensate",
        "gas",
        "oil",
        "water",
    ]


def test_an_ogrid_the_registry_does_not_carry_is_unresolved_rather_than_guessed(seeded):
    frame = pl.DataFrame({"operator_raw": [PROBE_OGRID[0], "999999"]})

    application = apply_rules(frame, [load_one(seeded, "cr_nm_ogrid_operator_1")])

    assert application.frame["operator"].to_list() == [PROBE_OGRID[1]]
    assert [batch.reason_code for batch in application.quarantined] == ["alias_unresolved"]


def test_the_permian_compute_crs_is_registered_so_no_nm_path_defaults_to_williston(seeded):
    """api/routers/wells.py:354 defaults an unknown basin to williston. NM geometry is out of
    scope, and the row that keeps a future NM spatial path from silently landing in UTM 14N
    was written by the TX slice's migration; D1 asserts it rather than declaring it twice."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select compute_epsg, storage_epsg from lineage.crs_registry where basin = 'permian'"
        )

        assert cursor.fetchone() == (32613, 4326)


def test_the_collision_rule_names_the_base_each_measurement_was_taken_on(seeded):
    """`12,351` is measured over the pairs that disagree on the *amount*, not over all 22,591
    that disagree on the amount or the day count. A key that says only "disagreeing" reads as
    the wider base, and the spec is served at /v1/conformance."""
    measured = load_one(seeded, "cr_nm_wcproduction_collision_1").spec["measured"]
    rationale = load_one(seeded, "cr_nm_wcproduction_collision_1").rationale

    assert measured["disagreeing_groups"] == 22591
    assert measured["amount_disagreeing_groups"] == 19465
    assert measured["amount_disagreeing_with_both_producing"] == 12351
    assert measured["amount_disagreeing_separated_by_amend_ind"] == 5106
    assert "disagreeing_with_both_producing" not in measured
    assert "of the 19,465 pairs that disagree on the amount, 12,351" in rationale
