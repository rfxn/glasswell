from pathlib import Path

FEATURE_MATRIX = (
    Path(__file__).resolve().parents[2] / "src" / "glasswell" / "modeling" / "feature_matrix.py"
)


def test_modeling_feature_builder_has_no_direct_canonical_read():
    assert "canonical." not in FEATURE_MATRIX.read_text()
