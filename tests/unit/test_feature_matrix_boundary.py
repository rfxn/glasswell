from pathlib import Path

from glasswell.modeling.feature_matrix import build_feature_matrix

FEATURE_MATRIX = (
    Path(__file__).resolve().parents[2] / "src" / "glasswell" / "modeling" / "feature_matrix.py"
)


def test_modeling_feature_builder_has_no_direct_canonical_read():
    assert "canonical." not in FEATURE_MATRIX.read_text()


def test_the_global_partition_builder_does_not_expose_a_partial_geography_selector():
    parameters = build_feature_matrix.__annotations__

    assert "state_code" not in parameters
    assert "basin" not in parameters
