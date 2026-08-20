from __future__ import annotations

from datetime import date

import pytest

from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.errors import DeterminismViolation, LineageNotConfigured
from glasswell.lineage.models import DeriveEnvironment, InputRef, OutputSpec
from tests.support.fakes import FixedClock, MemoryRecorder

ENV = DeriveEnvironment(
    code_version="git:9f2c1ab",
    code_dirty=False,
    env_id="env_ubuntu2404_py312_2026w32",
)


def promote_output(production_month: str = "2024-03") -> OutputSpec:
    return OutputSpec(
        store="parquet",
        dataset="canonical.production_monthly",
        partition={"source_id": "nd_mpr_xlsx", "production_month": production_month},
        locator=f"/data/canonical/{production_month}.parquet",
    )


def session(recorder: MemoryRecorder):
    return lineage_session(
        recorder=recorder,
        environment=ENV,
        clock=FixedClock(step_ms=12),
        correlation_id="run_test",
    )


def test_derive_outside_a_session_is_refused():
    with pytest.raises(LineageNotConfigured), derive(
        "canonical.promote", output=promote_output(), params={}
    ):
        pass


def test_derive_records_one_row_with_a_content_addressed_id():
    recorder = MemoryRecorder()
    with session(recorder):
        with derive("canonical.promote", output=promote_output(), params={"a": 1}) as ctx:
            ctx.add_input(InputRef(kind="manifest", ref_id="man_9c3f", role="primary"))
            ctx.set_output_hash("f" * 64)
            ctx.set_rows(4118203)
        recorded_id = ctx.derivation_id

    assert recorder.order == [recorded_id]
    row = recorder.records[recorded_id]
    assert row.status == "ok"
    assert row.output_rows == 4118203
    assert row.correlation_id == "run_test"
    assert row.code_version == "git:9f2c1ab"
    assert row.duration_ms == 12


def test_identical_specs_collapse_onto_one_row():
    recorder = MemoryRecorder()
    with session(recorder):
        for _ in range(2):
            with derive("forecast.scenario", output=promote_output(), params={"a": 1}) as ctx:
                ctx.set_output_hash("f" * 64)
    assert len(recorder.order) == 1


def test_differing_params_produce_different_derivations():
    recorder = MemoryRecorder()
    with session(recorder):
        for value in (1, 2):
            with derive("forecast.scenario", output=promote_output(), params={"a": value}):
                pass
    assert len(recorder.order) == 2


def test_same_spec_with_a_different_output_hash_raises_determinism_violation():
    recorder = MemoryRecorder()
    with session(recorder):
        with derive("canonical.promote", output=promote_output(), params={}) as first:
            first.set_output_hash("a" * 64)
        with pytest.raises(DeterminismViolation) as excinfo:
            with derive("canonical.promote", output=promote_output(), params={}) as second:
                second.set_output_hash("b" * 64)

    violation = excinfo.value
    assert violation.derivation_id == first.derivation_id
    assert violation.recorded_sha256 == "a" * 64
    assert violation.observed_sha256 == "b" * 64


def test_nesting_links_the_child_as_an_input_of_the_parent():
    recorder = MemoryRecorder()
    with session(recorder):
        with derive("canonical.promote", output=promote_output(), params={}) as parent:
            with derive(
                "stage.parse",
                output=OutputSpec(store="postgres", dataset="staging.nd_mpr", partition={}),
                params={},
            ) as child:
                child.add_input(
                    InputRef(
                        kind="manifest",
                        ref_id="man_9c3f",
                        role="primary",
                        as_of_vintage=date(2026, 8, 1),
                    )
                )

    parent_row = recorder.records[parent.derivation_id]
    edge = next(i for i in parent_row.inputs if i.kind == "derivation")
    assert edge.ref_id == child.derivation_id
    assert [i.ord for i in parent_row.inputs] == list(range(len(parent_row.inputs)))


def test_nesting_survives_two_levels_and_orders_edges_by_completion():
    recorder = MemoryRecorder()
    with session(recorder):
        with derive("mart.refresh", output=promote_output(), params={}) as top:
            with derive("canonical.promote", output=promote_output("2024-04"), params={}) as mid:
                with derive(
                    "stage.parse",
                    output=OutputSpec(store="postgres", dataset="staging.nd_mpr", partition={}),
                    params={},
                ) as leaf:
                    pass

    assert [i.ref_id for i in recorder.records[mid.derivation_id].inputs] == [leaf.derivation_id]
    assert [i.ref_id for i in recorder.records[top.derivation_id].inputs] == [mid.derivation_id]


def test_created_vintage_is_the_max_input_vintage_not_wall_clock():
    recorder = MemoryRecorder()
    with session(recorder):
        with derive("canonical.promote", output=promote_output(), params={}) as ctx:
            ctx.add_input(
                InputRef(kind="manifest", ref_id="man_a", as_of_vintage=date(2026, 7, 1))
            )
            ctx.add_input(
                InputRef(kind="manifest", ref_id="man_b", as_of_vintage=date(2026, 8, 1))
            )
    assert recorder.records[ctx.derivation_id].created_vintage == date(2026, 8, 1)


def test_a_failing_transform_is_recorded_as_failed_and_re_raises():
    recorder = MemoryRecorder()
    with session(recorder), pytest.raises(RuntimeError, match="parse blew up"):
        with derive("stage.parse", output=promote_output(), params={}) as ctx:
            raise RuntimeError("parse blew up")

    assert recorder.records[ctx.derivation_id].status == "failed"


def test_a_failed_child_is_not_linked_into_its_parent():
    recorder = MemoryRecorder()
    with session(recorder):
        with derive("canonical.promote", output=promote_output(), params={}) as parent:
            with pytest.raises(RuntimeError):
                with derive("stage.parse", output=promote_output(), params={}):
                    raise RuntimeError("boom")

    assert recorder.records[parent.derivation_id].inputs == ()


def test_rules_are_recorded_with_their_applied_row_counts():
    recorder = MemoryRecorder()
    with session(recorder):
        with derive("canonical.promote", output=promote_output(), params={}) as ctx:
            ctx.add_rule("cr_pdq_delim_1", applied_rows=4118203)
            ctx.add_rule("cr_tx_lease_key_1", applied_rows=41822)

    row = recorder.records[ctx.derivation_id]
    assert [r.rule_id for r in row.rules] == ["cr_pdq_delim_1", "cr_tx_lease_key_1"]
    assert row.rules[0].applied_rows == 4118203


def test_rule_citations_change_the_derivation_id():
    recorder = MemoryRecorder()
    with session(recorder):
        with derive("canonical.promote", output=promote_output(), params={}) as bare:
            pass
        with derive("canonical.promote", output=promote_output(), params={}) as ruled:
            ruled.add_rule("cr_pdq_delim_1", applied_rows=1)

    assert bare.derivation_id != ruled.derivation_id


def test_inputs_and_rules_may_be_declared_up_front_instead_of_inside_the_body():
    recorder = MemoryRecorder()
    with session(recorder), derive(
        "canonical.promote",
        output=promote_output(),
        params={},
        inputs=[InputRef(kind="manifest", ref_id="man_9c3f", as_of_vintage=date(2026, 8, 1))],
        rules=["cr_month_convention_1"],
    ) as ctx:
        pass

    row = recorder.records[ctx.derivation_id]
    assert [i.ref_id for i in row.inputs] == ["man_9c3f"]
    assert [r.rule_id for r in row.rules] == ["cr_month_convention_1"]
    assert row.created_vintage == date(2026, 8, 1)


def test_declaring_the_same_input_or_rule_twice_records_it_once():
    recorder = MemoryRecorder()
    reference = InputRef(kind="manifest", ref_id="man_9c3f")
    with session(recorder), derive(
        "canonical.promote", output=promote_output(), params={}, inputs=[reference]
    ) as ctx:
        ctx.add_input(reference)
        ctx.add_rule("cr_month_convention_1")
        ctx.add_rule("cr_month_convention_1")

    row = recorder.records[ctx.derivation_id]
    assert len(row.inputs) == 1
    assert len(row.rules) == 1
