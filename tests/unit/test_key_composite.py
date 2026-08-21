"""The `key_composite` executor: the S-E `entity_key` is assembled from declared columns.

Registered as unimplemented since P0, which was survivable only while ND was the one source
and its entity key was its API-10. NM reports at well-completion x pool and TX's `LEASE_NO` is
unique within district only, so both build their key from a rule — and a key built by a
literal in the parser is the R8 violation the registry exists to prevent (SB-07 §6.3).
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from glasswell.lineage.conformance import apply_rules, executor_for
from glasswell.lineage.errors import RuleSpecError
from glasswell.lineage.models import ConformanceRule


def rule(**spec: object) -> ConformanceRule:
    return ConformanceRule(
        rule_id="cr_probe_key_1",
        rule_family="cr_probe_key",
        source_id="nd_mpr_xlsx",
        stage="conform",
        applies_to_fields=["entity_key"],
        rule_kind="key_composite",
        spec=spec,
        rule="Assemble the entity key from the declared columns.",
        rationale="A probe rule for the executor's contract.",
        effective_from=date(2026, 1, 1),
    )


def run(frame: pl.DataFrame, **spec: object):
    return executor_for("key_composite")(frame, rule(**spec))


def test_a_single_component_key_is_the_component_itself():
    """ND: entity_type='well', so the entity key is the API-10 and nothing is joined."""
    frame = pl.DataFrame({"api10": ["3305302532", "3305310451"]})

    kept, quarantined = run(frame, source_cols=["api10"], target_col="entity_key")

    assert kept["entity_key"].to_list() == ["3305302532", "3305310451"]
    assert quarantined == []


def test_a_lease_key_joins_its_components_with_the_declared_separator():
    """TX: LEASE_NO is unique within district only (SB-01 §4.1), so the key is composite."""
    frame = pl.DataFrame(
        {"oil_gas_code": ["O", "G"], "district_no": ["08", "7B"], "lease_no": ["12345", "6789"]}
    )

    kept, _ = run(
        frame,
        source_cols=["oil_gas_code", "district_no", "lease_no"],
        separator=":",
        target_col="entity_key",
        uniqueness_scope="district",
    )

    assert kept["entity_key"].to_list() == ["O:08:12345", "G:7B:6789"]


def test_a_component_is_zero_padded_to_the_declared_width():
    """NM API numbers are state 30 plus a county and unique segment, zero-padded (SB-01 §4.1)."""
    frame = pl.DataFrame({"api10": ["3000512345", "300512345"]})

    kept, _ = run(frame, source_cols=["api10"], target_col="entity_key", pad={"api10": 10})

    assert kept["entity_key"].to_list() == ["3000512345", "0300512345"]


def test_a_pool_key_composes_the_well_with_the_pool_it_filed_in():
    frame = pl.DataFrame(
        {"api10": ["3305302532", "3305302532"], "pool": ["BIRDBEAR", "DUPEROW"]}
    )

    kept, _ = run(frame, source_cols=["api10", "pool"], separator=":", target_col="entity_key")

    assert kept["entity_key"].to_list() == ["3305302532:BIRDBEAR", "3305302532:DUPEROW"]


def test_a_row_missing_a_component_is_quarantined_under_the_declared_reason():
    """A partial key is a wrong key. It leaves the frame with a reason, never truncated."""
    frame = pl.DataFrame({"api10": ["3305302532", "3305310451"], "pool": ["BIRDBEAR", None]})

    kept, quarantined = run(
        frame,
        source_cols=["api10", "pool"],
        separator=":",
        target_col="entity_key",
        on_missing="quarantine",
        reason_code="key_incomplete",
    )

    assert kept["entity_key"].to_list() == ["3305302532:BIRDBEAR"]
    assert len(quarantined) == 1
    assert quarantined[0].reason_code == "key_incomplete"
    assert quarantined[0].rule_id == "cr_probe_key_1"
    assert quarantined[0].frame["api10"].to_list() == ["3305310451"]


def test_an_empty_component_counts_as_missing_rather_than_keying_on_a_blank():
    frame = pl.DataFrame({"api10": ["3305302532"], "pool": [""]})

    kept, quarantined = run(
        frame,
        source_cols=["api10", "pool"],
        separator=":",
        target_col="entity_key",
        on_missing="quarantine",
        reason_code="key_incomplete",
    )

    assert kept.is_empty()
    assert len(quarantined) == 1


def test_passthrough_leaves_the_unkeyable_row_in_the_frame_with_a_null_key():
    """ND: a month the regulator filed with no pool label is an observation of the well."""
    frame = pl.DataFrame({"api10": ["3305302532", "3305310451"], "pool": ["BIRDBEAR", None]})

    kept, quarantined = run(
        frame,
        source_cols=["api10", "pool"],
        separator=":",
        target_col="entity_key",
        on_missing="passthrough",
    )

    assert kept["entity_key"].to_list() == ["3305302532:BIRDBEAR", None]
    assert quarantined == []


def test_a_component_outside_the_declared_character_class_is_refused():
    """Width is not identity. `pad`/`min_width` judge length only, so an eight-character
    non-numeric API passes both and builds `42ABCDEFGH` — a syntactically perfect API-10 whose
    county and well number are letters. TX has no such row today; NM's key components are
    alphanumeric, so the guarantee is declared per column rather than inferred from one state's
    data (gate-tx-qa re-gate, D1 residual)."""
    frame = pl.DataFrame({"state_code": ["42", "42"], "api": ["00300446", "ABCDEFGH"]})

    kept, quarantined = run(
        frame,
        source_cols=["state_code", "api"],
        separator="",
        target_col="api10",
        pad={"api": 8},
        min_width={"api": 8},
        charset={"api": "digits"},
        on_missing="quarantine",
        reason_code="key_incomplete",
    )

    assert kept["api10"].to_list() == ["4200300446"]
    assert [batch.reason_code for batch in quarantined] == ["key_incomplete"]
    assert quarantined[0].frame["api"].to_list() == ["ABCDEFGH"]


def test_a_column_the_rule_declares_no_class_for_is_unconstrained():
    """NM's pool label is prose the regulator writes; only the columns named are bounded."""
    frame = pl.DataFrame({"api10": ["3005512345"], "pool": ["WC-025 G-09 S243308G"]})

    kept, quarantined = run(
        frame,
        source_cols=["api10", "pool"],
        separator=":",
        target_col="entity_key",
        charset={"api10": "digits"},
    )

    assert kept["entity_key"].to_list() == ["3005512345:WC-025 G-09 S243308G"]
    assert quarantined == []


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ({"target_col": "entity_key"}, "source_cols"),
        ({"source_cols": ["api10"]}, "target_col"),
        ({"source_cols": ["missing"], "target_col": "entity_key"}, "not a column"),
        ({"source_cols": ["api10"], "target_col": "api10"}, "already exists"),
        (
            {"source_cols": ["api10"], "target_col": "entity_key", "on_missing": "drop"},
            "not supported",
        ),
        (
            {"source_cols": ["api10"], "target_col": "entity_key", "pad": {"api10": 0}},
            "positive integer",
        ),
        (
            {
                "source_cols": ["api10"],
                "target_col": "entity_key",
                "charset": {"api10": "numeric"},
            },
            "the classes are",
        ),
        (
            {"source_cols": ["api10"], "target_col": "entity_key", "charset": {"pool": "digits"}},
            "which source_cols does not",
        ),
    ],
)
def test_a_spec_the_executor_cannot_honour_is_refused_before_it_runs(spec, message):
    frame = pl.DataFrame({"api10": ["3305302532"]})

    with pytest.raises(RuleSpecError, match=message):
        run(frame, **spec)


def test_apply_rules_no_longer_raises_for_the_kind():
    """P0 pinned `key_composite` as unimplemented; NM's first promotion frame would have raised."""
    frame = pl.DataFrame({"api10": ["3305302532"]})

    applied = apply_rules(frame, [rule(source_cols=["api10"], target_col="entity_key")])

    assert applied.applied_rule_ids == ["cr_probe_key_1"]
    assert applied.applied_rows["cr_probe_key_1"] == 1
