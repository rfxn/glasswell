from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from glasswell.lineage.errors import InvalidHandle, InvalidSelector
from glasswell.lineage.ids import (
    derivation_id,
    format_handle,
    format_selector,
    manifest_id,
    new_ulid,
    parse_handle,
    parse_selector,
    ruleset_hash,
)
from glasswell.lineage.models import InputRef, OutputSpec

SPEC = {
    "operation": "canonical.promote",
    "inputs": (
        InputRef(
            kind="manifest", ref_id="man_9c3f", role="primary", as_of_vintage=date(2026, 8, 1)
        ),
    ),
    "params": {"month_convention": "production_month"},
    "code_version": "git:9f2c1ab",
    "env_id": "env_ubuntu2404_py312_2026w32",
    "rule_ids": ("cr_month_convention_1",),
    "output": OutputSpec(
        store="parquet",
        dataset="canonical.production_monthly",
        partition={"source_id": "nd_mpr_xlsx", "production_month": "2024-03"},
    ),
}


def test_derivation_id_is_content_addressed_and_stable():
    assert derivation_id(**SPEC) == derivation_id(**SPEC)
    assert derivation_id(**SPEC).startswith("drv_")


def test_partition_key_order_does_not_change_the_id():
    reordered = dict(SPEC)
    reordered["output"] = OutputSpec(
        store="parquet",
        dataset="canonical.production_monthly",
        partition={"production_month": "2024-03", "source_id": "nd_mpr_xlsx"},
    )
    assert derivation_id(**reordered) == derivation_id(**SPEC)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation", "mart.refresh"),
        ("params", {"month_convention": "report_month"}),
        ("code_version", "git:deadbee"),
        ("env_id", "env_other"),
        ("rule_ids", ("cr_month_convention_2",)),
        ("inputs", (InputRef(kind="manifest", ref_id="man_71ba", role="primary"),)),
    ],
)
def test_any_spec_change_changes_the_id(field, value):
    changed = dict(SPEC)
    changed[field] = value
    assert derivation_id(**changed) != derivation_id(**SPEC)


def test_only_dataset_and_partition_of_the_output_participate_in_the_id():
    """§1.3: nothing about the produced artifact may change the ID."""
    relocated = dict(SPEC)
    relocated["output"] = OutputSpec(
        store="parquet",
        dataset=SPEC["output"].dataset,
        partition=SPEC["output"].partition,
        locator="/data/canonical/other/path.parquet",
        schema_version="v9",
    )
    assert derivation_id(**relocated) == derivation_id(**SPEC)


def test_input_ordinal_position_is_part_of_the_address():
    a = InputRef(kind="manifest", ref_id="man_a", role="primary")
    b = InputRef(kind="manifest", ref_id="man_b", role="crosswalk")
    forward = dict(SPEC, inputs=(a, b))
    reverse = dict(SPEC, inputs=(b, a))
    assert derivation_id(**forward) != derivation_id(**reverse)


def test_manifest_id_is_the_truncated_content_hash():
    digest = "9c3f" + "0" * 60
    assert manifest_id(digest) == "man_" + digest[:32]


def test_manifest_id_rejects_a_non_sha256_digest():
    with pytest.raises(ValueError, match="sha256"):
        manifest_id("not-a-digest")


def test_ruleset_hash_is_order_independent():
    assert ruleset_hash(["cr_b", "cr_a"]) == ruleset_hash(["cr_a", "cr_b"])
    assert ruleset_hash([]) != ruleset_hash(["cr_a"])


def test_ulid_is_time_ordered_and_lexically_sortable():
    early = new_ulid(datetime(2026, 8, 1, tzinfo=UTC), entropy=b"\x00" * 10)
    late = new_ulid(datetime(2026, 8, 2, tzinfo=UTC), entropy=b"\x00" * 10)
    assert len(early) == 26
    assert early < late


def test_ulid_entropy_varies_within_a_millisecond():
    at = datetime(2026, 8, 1, tzinfo=UTC)
    assert new_ulid(at) != new_ulid(at)


def test_selector_round_trips():
    raw = "api10=33053012340000&pm=2024-03&stream=oil&col=volume"
    assert format_selector(parse_selector(raw)) == raw


def test_selector_preserves_declared_order():
    assert format_selector(parse_selector("pm=2024-03&api10=42")) == "pm=2024-03&api10=42"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "col",
        "col=",
        "=oil",
        "col==oil",
        "col=oil&col=gas",
        "col=oil&&pm=2024-03",
        "col=oil value",
        "col=oil;drop table",
        "Col=oil",
        "col=$(whoami)",
        "col=oil&",
        "col=oil#pm=2024-03",
    ],
)
def test_malformed_selectors_are_rejected(bad):
    with pytest.raises(InvalidSelector):
        parse_selector(bad)


def test_handle_round_trips_with_and_without_a_selector():
    bare = "drv_7qk3m2xr4v9b0tfa"
    assert format_handle(*parse_handle(bare)) == bare
    addressed = bare + "#api10=33053012340000&col=volume"
    handle = parse_handle(addressed)
    assert handle.derivation_id == bare
    assert format_handle(handle.derivation_id, handle.selector) == addressed


@pytest.mark.parametrize(
    "bad",
    ["", "drv_", "man_9c3f", "drv_UPPER", "drv_abc#", "drv_abc#bad", "drv_abc#a=b#c=d"],
)
def test_malformed_handles_are_rejected(bad):
    with pytest.raises((InvalidHandle, InvalidSelector)):
        parse_handle(bad)


def test_ulid_rejects_a_naive_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        new_ulid(datetime(2026, 8, 1))


def test_ulid_rejects_wrong_sized_entropy():
    with pytest.raises(ValueError, match="10 bytes"):
        new_ulid(datetime(2026, 8, 1, tzinfo=UTC), entropy=b"\x00")
