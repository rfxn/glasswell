from __future__ import annotations

from datetime import date
from decimal import Decimal

import polars as pl
import pytest

from glasswell.lineage.conformance import RULE_KINDS, apply_rules, executor_for
from glasswell.lineage.errors import RuleSpecError, UnknownRuleKind
from glasswell.lineage.models import ConformanceRule


def rule(rule_id: str, kind: str, spec: dict, **kwargs) -> ConformanceRule:
    return ConformanceRule(
        rule_id=rule_id,
        rule_family=rule_id.rsplit("_", 1)[0],
        source_id="nd_mpr_xlsx",
        stage=kwargs.pop("stage", "conform"),
        applies_to_fields=kwargs.pop("applies_to_fields", []),
        rule_kind=kind,
        spec=spec,
        rule=kwargs.pop("rule", "test rule"),
        rationale=kwargs.pop("rationale", "test rationale"),
        effective_from=date(2026, 1, 1),
        **kwargs,
    )


UNIT_RULE = rule(
    "cr_gas_cf_to_mcf_1",
    "unit_conform",
    {"from_unit": "cf", "to_unit": "mcf", "factor": "0.001", "rounding": "half_up", "scale": 3},
    applies_to_fields=["gas_volume"],
)

VOCAB_RULE = rule(
    "cr_well_status_vocab_1",
    "vocab_map",
    {
        "key_col": "status_raw",
        "value_col": "well_status",
        "mapping_table": "vocab_well_status",
        "unmapped_action": "quarantine",
    },
    lookup=[
        {"status_raw": "AC", "well_status": "active"},
        {"status_raw": "PA", "well_status": "plugged"},
    ],
)

ALIAS_RULE = rule(
    "cr_formation_alias_1",
    "alias_join",
    {
        "alias_table": "formation_aliases",
        "key_cols": ["formation_raw"],
        "target_col": "formation",
        "min_confidence": "0.80",
        "unmatched_action": "quarantine",
    },
    lookup=[
        {"formation_raw": "BAKKEN FM", "formation": "bakken", "confidence": "0.99"},
        {"formation_raw": "THREE FORKS", "formation": "three_forks", "confidence": "0.95"},
        {"formation_raw": "SANISH", "formation": "bakken", "confidence": "0.40"},
    ],
)


def test_every_declared_kind_has_a_registered_executor():
    for kind in RULE_KINDS:
        assert callable(executor_for(kind))


@pytest.mark.parametrize("kind", ["", "eval", "unit_convert", "UNIT_CONFORM", "vocab_map "])
def test_the_registry_rejects_unknown_kinds(kind):
    with pytest.raises(UnknownRuleKind):
        executor_for(kind)


@pytest.mark.parametrize(
    "kind",
    ["datum_transform", "key_composite", "parse_directive", "validity_filter", "code_ref"],
)
def test_unimplemented_kinds_fail_loudly_rather_than_silently_passing_rows_through(kind):
    frame = pl.DataFrame({"x": [1]})
    with pytest.raises(NotImplementedError, match=kind):
        apply_rules(frame, [rule(f"cr_{kind}_1", kind, {})])


def test_unit_conform_scales_and_rounds_to_the_declared_precision():
    frame = pl.DataFrame(
        {"gas_volume": [Decimal("1234500.000"), Decimal("1234.500"), None]},
        schema={"gas_volume": pl.Decimal(18, 3)},
    )
    result = apply_rules(frame, [UNIT_RULE])
    assert result.frame["gas_volume"].to_list() == [Decimal("1234.500"), Decimal("1.235"), None]
    assert result.applied_rule_ids == ["cr_gas_cf_to_mcf_1"]
    assert result.quarantined == []


def test_unit_conform_stays_in_decimal_and_never_widens_to_float():
    frame = pl.DataFrame(
        {"gas_volume": [Decimal("1.005")]}, schema={"gas_volume": pl.Decimal(18, 3)}
    )
    result = apply_rules(frame, [UNIT_RULE])
    assert result.frame.schema["gas_volume"] == pl.Decimal(18, 3)


def test_unit_conform_rounding_mode_is_taken_from_the_rule_not_the_runtime():
    frame = pl.DataFrame({"v": [Decimal("2.5"), Decimal("3.5")]}, schema={"v": pl.Decimal(18, 1)})
    spec = {"from_unit": "a", "to_unit": "b", "factor": "1", "scale": 0}
    half_up = apply_rules(frame, [rule("cr_a_1", "unit_conform", spec | {"rounding": "half_up"},
                                       applies_to_fields=["v"])])
    half_even = apply_rules(frame, [rule("cr_a_1", "unit_conform", spec | {"rounding": "half_even"},
                                         applies_to_fields=["v"])])
    assert half_up.frame["v"].to_list() == [Decimal("3"), Decimal("4")]
    assert half_even.frame["v"].to_list() == [Decimal("2"), Decimal("4")]


def test_unit_conform_rejects_a_float_factor():
    with pytest.raises(RuleSpecError, match="factor"):
        apply_rules(
            pl.DataFrame({"v": [Decimal("1")]}),
            [rule("cr_a_1", "unit_conform",
                  {"from_unit": "a", "to_unit": "b", "factor": 0.001, "rounding": "half_up",
                   "scale": 3},
                  applies_to_fields=["v"])],
        )


def test_unit_conform_rejects_an_unsupported_rounding_mode():
    with pytest.raises(RuleSpecError, match="rounding"):
        apply_rules(
            pl.DataFrame({"v": [Decimal("1")]}),
            [rule("cr_a_1", "unit_conform",
                  {"from_unit": "a", "to_unit": "b", "factor": "1", "rounding": "banker",
                   "scale": 3},
                  applies_to_fields=["v"])],
        )


def test_unit_conform_requires_its_target_field_to_exist():
    with pytest.raises(RuleSpecError, match="gas_volume"):
        apply_rules(pl.DataFrame({"other": [1]}), [UNIT_RULE])


def test_vocab_map_writes_the_canonical_value():
    frame = pl.DataFrame(
        {"api10": ["33053012340000", "33053012350000"], "status_raw": ["AC", "PA"]}
    )
    result = apply_rules(frame, [VOCAB_RULE])
    assert result.frame["well_status"].to_list() == ["active", "plugged"]
    assert result.quarantined == []


def test_vocab_map_quarantines_unmapped_rows_and_drops_them_from_the_frame():
    frame = pl.DataFrame(
        {"api10": ["33053012340000", "33053012350000"], "status_raw": ["AC", "ZZ"]}
    )
    result = apply_rules(frame, [VOCAB_RULE])

    assert result.frame["api10"].to_list() == ["33053012340000"]
    assert len(result.quarantined) == 1
    batch = result.quarantined[0]
    assert batch.reason_code == "unknown_vocab"
    assert batch.rule_id == "cr_well_status_vocab_1"
    assert batch.frame["status_raw"].to_list() == ["ZZ"]


def test_vocab_map_passthrough_keeps_unmapped_rows_with_a_null_target():
    spec = VOCAB_RULE.spec | {"unmapped_action": "passthrough"}
    frame = pl.DataFrame({"status_raw": ["AC", "ZZ"]})
    result = apply_rules(frame, [VOCAB_RULE.model_copy(update={"spec": spec})])
    assert result.frame["well_status"].to_list() == ["active", None]
    assert result.quarantined == []


def test_vocab_map_rejects_an_unsupported_unmapped_action():
    spec = VOCAB_RULE.spec | {"unmapped_action": "drop_silently"}
    with pytest.raises(RuleSpecError, match="unmapped_action"):
        apply_rules(
            pl.DataFrame({"status_raw": ["AC"]}),
            [VOCAB_RULE.model_copy(update={"spec": spec})],
        )


def test_alias_join_resolves_above_the_confidence_floor():
    frame = pl.DataFrame({"formation_raw": ["BAKKEN FM", "THREE FORKS"]})
    result = apply_rules(frame, [ALIAS_RULE])
    assert result.frame["formation"].to_list() == ["bakken", "three_forks"]


def test_alias_join_quarantines_matches_below_the_confidence_floor():
    frame = pl.DataFrame({"formation_raw": ["BAKKEN FM", "SANISH"]})
    result = apply_rules(frame, [ALIAS_RULE])

    assert result.frame["formation_raw"].to_list() == ["BAKKEN FM"]
    assert result.quarantined[0].reason_code == "alias_unresolved"
    assert result.quarantined[0].frame["formation_raw"].to_list() == ["SANISH"]


def test_alias_join_quarantines_rows_with_no_alias_row_at_all():
    frame = pl.DataFrame({"formation_raw": ["MYSTERY SHALE"]})
    result = apply_rules(frame, [ALIAS_RULE])
    assert result.frame.is_empty()
    assert result.quarantined[0].frame["formation_raw"].to_list() == ["MYSTERY SHALE"]


def test_alias_join_does_not_multiply_rows_when_the_alias_table_has_duplicates():
    duplicated = ALIAS_RULE.model_copy(
        update={
            "lookup": [
                {"formation_raw": "BAKKEN FM", "formation": "bakken", "confidence": "0.99"},
                {"formation_raw": "BAKKEN FM", "formation": "bakken_upper", "confidence": "0.85"},
            ]
        }
    )
    with pytest.raises(RuleSpecError, match="duplicate"):
        apply_rules(pl.DataFrame({"formation_raw": ["BAKKEN FM"]}), [duplicated])


def test_rules_apply_in_registry_order_and_report_every_id():
    frame = pl.DataFrame(
        {
            "status_raw": ["AC"],
            "formation_raw": ["BAKKEN FM"],
            "gas_volume": [Decimal("1000.000")],
        },
        schema={"status_raw": pl.String, "formation_raw": pl.String,
                "gas_volume": pl.Decimal(18, 3)},
    )
    result = apply_rules(frame, [UNIT_RULE, VOCAB_RULE, ALIAS_RULE])
    assert result.applied_rule_ids == [
        "cr_gas_cf_to_mcf_1",
        "cr_well_status_vocab_1",
        "cr_formation_alias_1",
    ]
    assert result.frame["gas_volume"].to_list() == [Decimal("1.000")]
    assert result.frame["well_status"].to_list() == ["active"]
    assert result.frame["formation"].to_list() == ["bakken"]


def test_a_rule_that_quarantines_everything_leaves_an_empty_frame_not_an_error():
    frame = pl.DataFrame({"status_raw": ["ZZ", "YY"]})
    result = apply_rules(frame, [VOCAB_RULE])
    assert result.frame.is_empty()
    assert result.quarantined[0].frame.height == 2


def test_unit_conform_rejects_a_factor_that_is_not_a_decimal():
    with pytest.raises(RuleSpecError, match="not a decimal"):
        apply_rules(
            pl.DataFrame({"v": [Decimal("1")]}),
            [
                rule(
                    "cr_a_1",
                    "unit_conform",
                    {"from_unit": "a", "to_unit": "b", "factor": "one", "rounding": "half_up",
                     "scale": 3},
                    applies_to_fields=["v"],
                )
            ],
        )
