from decimal import Decimal
from pathlib import Path

import pytest

from glasswell.modeling.feature_matrix import (
    UnsupportedFeatureSpecError,
    _formation_min_confidence,
    build_feature_matrix,
)
from glasswell.seed.features import FEATURE_SPECS

FEATURE_MATRIX = (
    Path(__file__).resolve().parents[2] / "src" / "glasswell" / "modeling" / "feature_matrix.py"
)


def test_modeling_feature_builder_has_no_direct_canonical_read():
    assert "canonical." not in FEATURE_MATRIX.read_text()


def test_the_global_partition_builder_does_not_expose_a_partial_geography_selector():
    parameters = build_feature_matrix.__annotations__

    assert "state_code" not in parameters
    assert "basin" not in parameters


@pytest.mark.parametrize("value", [None, "not-a-number"])
def test_invalid_formation_confidence_is_a_controlled_spec_error(value):
    spec = FEATURE_SPECS[0].model_copy(
        update={"params": {**FEATURE_SPECS[0].params, "min_confidence": value}}
    )

    with pytest.raises(UnsupportedFeatureSpecError, match="invalid min_confidence"):
        _formation_min_confidence([spec])


def test_equivalent_formation_confidence_encodings_agree():
    specs = [
        FEATURE_SPECS[0].model_copy(
            update={"params": {**FEATURE_SPECS[0].params, "min_confidence": value}}
        )
        for value in (0.8, "0.800")
    ]

    assert _formation_min_confidence(specs) == Decimal("0.8")
