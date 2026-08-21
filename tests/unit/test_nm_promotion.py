"""The promotion's pure decisions, before any of them meets a database.

Three of them are only ever exercised at scale and would be invisible in an integration test
over a 300-record fixture: the day count NM files past the end of its own month, the two rows
it files for one well-completion-month when an operator changes mid-month, and the payload
`value_hash` is allowed to cover.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import polars as pl
import pytest

from glasswell.ingest.nm_ocd import PromotionPolicy, promotion_records, route_collisions
from glasswell.lineage.models import ConformanceRule
from glasswell.lineage.serialization import hash_payload
from glasswell.seed.conformance_nm import EFFECTIVE_FROM, NM_RULES

SPINE_SOURCE = "nm_ocd_wcproduction"


def seeded_rules() -> list[ConformanceRule]:
    """The registry rows the promotion loads, read from the module that seeds them."""
    return [
        ConformanceRule(
            **{
                **rule,
                "rule_family": str(rule["rule_id"]).rsplit("_", 1)[0],
                "effective_from": rule.get("effective_from", EFFECTIVE_FROM),
            }
        )
        for rule in NM_RULES
        if rule["source_id"] == SPINE_SOURCE
    ]


POLICY = PromotionPolicy.from_rules(seeded_rules())

APRIL = date(2015, 4, 1)
MARCH = date(2015, 3, 1)


def staged(**overrides: object) -> pl.DataFrame:
    row: dict[str, object] = {
        "source_row_ordinal": 0,
        "entity_key": "3000501028:8559",
        "api10": "3000501028",
        "pool_idn": "8559",
        "production_month": MARCH,
        "stream_canonical": "oil",
        "prod_amt": Decimal("79.000"),
        "prodn_day_num": "31",
        "mod_dte": "2015-04-07T07:37:04.160",
        "amend_ind": "N",
        "ogrid_cde": "12345",
    }
    row.update(overrides)
    return pl.DataFrame(
        {key: [value] for key, value in row.items()},
        schema={
            "source_row_ordinal": pl.Int64,
            "entity_key": pl.String,
            "api10": pl.String,
            "pool_idn": pl.String,
            "production_month": pl.Date,
            "stream_canonical": pl.String,
            "prod_amt": pl.Decimal(18, 3),
            "prodn_day_num": pl.String,
            "mod_dte": pl.String,
            "amend_ind": pl.String,
            "ogrid_cde": pl.String,
        },
    )


def records(frame: pl.DataFrame) -> list[dict]:
    return promotion_records(frame, policy=POLICY).to_dicts()


def test_the_canonical_tuple_is_the_one_the_composition_check_admits() -> None:
    """Migration 020 admits well_completion_pool only with granularity well_observed and a
    non-null pool; `granularity = 'observed'` is rejected (entry gate G6)."""
    frame = staged()
    record = records(frame)[0]

    assert record["entity_type"] == "well_completion_pool"
    assert record["reporting_level"] == "well_completion_pool"
    assert record["granularity"] == "well_observed"
    assert record["aggregation"] is None
    # The pool comes off the column the entity-key rule names, not a literal this fixture set.
    # `entity_key` is not this function's to compute — test_nm_promote.py asserts it where the
    # conform rules that build it run.
    assert record["well_completion_pool"] == frame[POLICY.pool_column].item()


def test_the_unit_is_decided_by_the_stream_because_nm_files_one_amount_column() -> None:
    """ND ships three named volume columns; NM ships prod_amt discriminated by prd_knd_cde, so
    the unit is a property of the mapped stream (cr_nm_wcproduction_units_1)."""
    units = {
        record["stream"]: record["unit"]
        for stream in ("oil", "gas", "water", "condensate")
        for record in records(staged(stream_canonical=stream))
    }

    assert units == {"oil": "bbl", "gas": "mcf", "water": "bbl", "condensate": "bbl"}


def test_a_reported_zero_is_not_an_absent_report() -> None:
    assert records(staged())[0]["null_semantics"] == "reported"
    assert records(staged(prod_amt=Decimal("0.000")))[0]["null_semantics"] == "reported_zero"
    assert records(staged(prod_amt=None))[0]["null_semantics"] == "no_report"


def test_the_value_hash_covers_the_measurement_and_not_the_change_signals() -> None:
    """Arm C's invariant, at the level it is decided: mod_dte and amend_ind are carried as
    evidence and folding either into the hash would make a timestamp bump a restatement."""
    base = records(staged())[0]
    touched = records(staged(mod_dte="2026-08-19T04:00:00.000", amend_ind="Y"))[0]
    transferred = records(staged(ogrid_cde="999999"))[0]
    restated = records(staged(prod_amt=Decimal("80.000")))[0]

    assert base["value_hash"] == touched["value_hash"] == transferred["value_hash"]
    assert base["value_hash"] != restated["value_hash"]
    assert base["value_hash"] == hash_payload(
        {
            "volume": Decimal("79.000"),
            "unit": "bbl",
            "days_produced": 31,
            "null_semantics": "reported",
            "liquids_policy": POLICY.liquids_policy,
        }
    )


@pytest.mark.parametrize(
    ("month", "filed", "promoted"),
    [
        (MARCH, "31", 31),
        (APRIL, "30", 30),
        (APRIL, "31", None),
        (MARCH, "0", 0),
        (MARCH, "99", None),
        (MARCH, "32", None),
    ],
)
def test_a_day_count_past_the_end_of_its_own_month_is_withheld(
    month: date, filed: str, promoted: int | None
) -> None:
    """41,593 in-window rows file a day count longer than the month they file it for, and 4
    file 99. The volume is real and promotes; the day count is not a day count and is left
    null with the raw value in staging (cr_nm_wcproduction_days_1)."""
    record = records(staged(production_month=month, prodn_day_num=filed))[0]

    assert record["days_produced"] == promoted
    assert record["volume"] == Decimal("79.000")


def test_withholding_a_day_count_does_not_withhold_the_volume() -> None:
    withheld = records(staged(prodn_day_num="99"))[0]
    filed = records(staged(prodn_day_num="31"))[0]

    assert withheld["days_produced"] is None
    assert withheld["volume"] == filed["volume"]
    assert withheld["value_hash"] != filed["value_hash"]


def pair(**second: object) -> pl.DataFrame:
    return pl.concat(
        [staged(), staged(source_row_ordinal=1, ogrid_cde="654321", **second)], how="vertical"
    )


def routed(frame: pl.DataFrame):
    return route_collisions(promotion_records(frame, policy=POLICY))


def test_one_row_per_key_is_left_alone() -> None:
    routing = routed(staged())

    assert routing.kept.height == 1
    assert routing.duplicates.is_empty()
    assert routing.collisions.is_empty()


def test_two_rows_saying_the_same_thing_promote_once_and_the_second_is_a_duplicate() -> None:
    """2,438 of the 25,029 in-window pairs carry an identical measurement under two OGRIDs.
    Promoting one is not a choice between answers, because there is only one answer."""
    routing = routed(pair())

    assert routing.kept["source_row_ordinal"].to_list() == [0]
    assert routing.duplicates["source_row_ordinal"].to_list() == [1]
    assert routing.collisions.is_empty()


def test_two_rows_that_disagree_promote_nothing_and_both_go_to_the_ledger() -> None:
    """22,591 pairs disagree, 12,351 of them with both rows producing and 801 differing more
    than tenfold. Nothing in the artifact says which is the month, so the S-E row is withheld
    and both filings are quarantined rather than one being chosen by ordinal (fp-audit D1)."""
    routing = routed(pair(prod_amt=Decimal("1000.000")))

    assert routing.kept.is_empty()
    assert routing.duplicates.is_empty()
    assert sorted(routing.collisions["source_row_ordinal"].to_list()) == [0, 1]


def test_a_pair_that_agrees_once_the_day_rule_has_spoken_is_a_duplicate() -> None:
    """Two impossible day counts are two absences of a day count. The rule that withholds
    them runs before the grouping, so what is compared is what would have been promoted."""
    routing = routed(pair(prodn_day_num="99"))

    assert routing.kept.height == 0  # 31 vs withheld is still a disagreement
    assert sorted(routing.collisions["source_row_ordinal"].to_list()) == [0, 1]

    agreeing = pl.concat(
        [
            staged(prodn_day_num="66"),
            staged(source_row_ordinal=1, ogrid_cde="654321", prodn_day_num="99"),
        ],
        how="vertical",
    )
    routing = routed(agreeing)

    assert routing.kept["source_row_ordinal"].to_list() == [0]
    assert routing.duplicates["source_row_ordinal"].to_list() == [1]


def test_a_different_month_or_stream_is_a_different_key_and_not_a_collision() -> None:
    frame = pl.concat(
        [
            staged(),
            staged(source_row_ordinal=1, production_month=APRIL),
            staged(source_row_ordinal=2, stream_canonical="gas"),
            staged(source_row_ordinal=3, entity_key="3000501028:9999", pool_idn="9999"),
        ],
        how="vertical",
    )

    routing = routed(frame)

    assert routing.kept.height == 4
    assert routing.collisions.is_empty()
