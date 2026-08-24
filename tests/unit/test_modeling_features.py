from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from glasswell.modeling.features import (
    FeatureEvents,
    FeatureLeakageError,
    FeatureSpec,
    feature_set_hash,
    observe_feature,
)


def spec(**overrides) -> FeatureSpec:
    values = {
        "feature_id": "design.proppant_lb_per_ft",
        "family": "design",
        "dtype": "float64",
        "unit": "lb/ft",
        "knowable_at_rule": "completion_date",
        "publication_lag_days_p50": 14,
        "transform_id": "divide_proppant_by_lateral_length",
        "params": {},
        "source_refs": ["canonical.well_completions", "cr_completion_design_1"],
        "missing_policy": "indicator",
        "member_of": ["full", "design_adjusted"],
        "introduced_in_fv": "fv1.0",
    }
    values.update(overrides)
    return FeatureSpec(**values)


def test_poisoned_feature_is_rejected():
    poisoned = spec(knowable_at_rule="first_production_month")
    events = FeatureEvents(
        completion_date=date(2024, 1, 10),
        first_production_month=date(2024, 2, 1),
        anchor=date(2024, 1, 10),
    )

    with pytest.raises(FeatureLeakageError, match="after anchor"):
        observe_feature(api10="3305300001", spec=poisoned, value=1000, events=events)


def test_availability_date_never_exceeds_anchor():
    events = FeatureEvents(
        permit_date=date(2023, 1, 1),
        spud_date=date(2023, 8, 1),
        completion_date=date(2024, 1, 10),
        anchor=date(2024, 1, 10),
    )
    observation = observe_feature(api10="3305300001", spec=spec(), value=1000, events=events)

    assert observation.knowable_at <= observation.anchor


def test_publication_lag_is_recorded_but_does_not_move_well_time_availability():
    events = FeatureEvents(completion_date=date(2024, 1, 10), anchor=date(2024, 1, 10))

    observation = observe_feature(api10="3305300001", spec=spec(), value=1000, events=events)

    assert observation.knowable_at == date(2024, 1, 10)


def test_feature_set_hash_is_order_independent_and_lifecycle_aware():
    design = spec()
    geology = spec(
        feature_id="geology.formation_group",
        family="geology",
        dtype="categorical",
        unit="category",
        transform_id="lookup_formation_alias",
        missing_policy="native_nan",
        member_of=["full"],
        introduced_in_fv="fv1.1",
    )

    assert feature_set_hash(
        [design, geology], set_name="full", feature_version="fv1.1"
    ) == feature_set_hash([geology, design], set_name="full", feature_version="fv1.1")
    assert feature_set_hash(
        [design, geology], set_name="full", feature_version="fv1.0"
    ) != feature_set_hash([design, geology], set_name="full", feature_version="fv1.1")


def test_registry_set_columns_are_normalized_before_hashing():
    forward = spec(source_refs=["canonical.wells", "cr_design_1"], member_of=["full", "a"])
    reverse = spec(source_refs=["cr_design_1", "canonical.wells"], member_of=["a", "full"])

    assert feature_set_hash([forward], set_name="full", feature_version="fv1.0") == (
        feature_set_hash([reverse], set_name="full", feature_version="fv1.0")
    )


def test_latest_revision_replaces_prior_semantics_without_mutating_history():
    original = spec()
    replacement = spec(unit="kg/m", introduced_in_fv="fv1.1")

    assert feature_set_hash(
        [original, replacement], set_name="full", feature_version="fv1.1"
    ) == feature_set_hash([replacement], set_name="full", feature_version="fv1.1")


def test_zero_length_successor_retires_a_feature_without_rewriting_the_prior_row():
    design = spec()
    retirement = spec(introduced_in_fv="fv1.1", retired_in_fv="fv1.1")
    geology = spec(
        feature_id="geology.formation_group",
        family="geology",
        dtype="categorical",
        unit="category",
        transform_id="lookup_formation_alias",
        missing_policy="native_nan",
        member_of=["full"],
        introduced_in_fv="fv1.0",
    )

    assert feature_set_hash(
        [design, retirement, geology], set_name="full", feature_version="fv1.1"
    ) == feature_set_hash([geology], set_name="full", feature_version="fv1.1")


def test_registry_rejects_a_feature_whose_family_disagrees_with_its_slug():
    with pytest.raises(ValidationError, match="prefix must match family"):
        spec(family="geology")
