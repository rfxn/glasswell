from __future__ import annotations

import pytest

from glasswell.api.provenance import _bind_derivation, _selector_outputs
from glasswell.lineage.envelope import Figure, Series


def _series(**overrides) -> Series:
    payload = {
        "values": [1.5, None, 3.0],
        "unit": "bbl",
        "derivation": "drv_placeholder",
        "selector": "api10=3305310451&col=monthly_p50",
    }
    payload.update(overrides)
    return Series(**payload)


def test_a_series_without_a_selector_is_refused() -> None:
    with pytest.raises(ValueError, match="must carry a selector"):
        _selector_outputs({"series": _series(selector=None)})


def test_a_series_with_point_handles_is_refused() -> None:
    with pytest.raises(ValueError, match="may not carry point handles"):
        _selector_outputs({"series": _series(point_handles=["a#b", None, None])})


def test_a_series_with_point_overrides_is_refused_on_the_same_rule() -> None:
    # The weaker per-point form has to be refused here too, or the registrar records a column
    # of evidence a point handle then addresses past (the H-1 class).
    with pytest.raises(ValueError, match="may not carry point handles"):
        _selector_outputs({"series": _series(point_overrides={1: "drv_a#api10=1&col=oil_bbl"})})


def test_a_series_and_a_figure_sharing_a_selector_and_disagreeing_is_refused() -> None:
    figure = Figure(
        value="1.50", unit="bbl", derivation="drv_placeholder", selector="col=monthly_p50"
    )
    with pytest.raises(ValueError, match="conflicting response figures"):
        _selector_outputs({"a": figure, "b": _series(selector="col=monthly_p50")})


def test_series_evidence_records_the_whole_array_and_its_unit() -> None:
    outputs = _selector_outputs({"series": _series()})
    assert outputs == {
        "api10=3305310451&col=monthly_p50": {"values": [1.5, None, 3.0], "unit": "bbl"}
    }


def test_a_null_valued_series_records_its_nulls_rather_than_dropping_them() -> None:
    outputs = _selector_outputs({"series": _series(values=[None, None, None])})
    assert outputs["api10=3305310451&col=monthly_p50"]["values"] == [None, None, None]


def test_a_series_nested_in_a_list_inside_a_mapping_is_reached() -> None:
    outputs = _selector_outputs({"page": [{"series": _series()}]})
    assert list(outputs) == ["api10=3305310451&col=monthly_p50"]


def test_the_selector_is_normalised_the_same_way_a_figure_is() -> None:
    outputs = _selector_outputs({"series": _series(selector="col=monthly_p50&api10=3305310451")})
    assert list(outputs) == ["api10=3305310451&col=monthly_p50"]


def test_binding_rebinds_a_series_and_leaves_everything_else_alone() -> None:
    payload = {"series": _series(), "note": "unchanged", "rows": [1, 2, 3]}
    bound = _bind_derivation(payload, "drv_response")
    assert bound["series"].derivation == "drv_response"
    assert bound["series"].values == [1.5, None, 3.0]
    assert bound["note"] == "unchanged"
    assert bound["rows"] == [1, 2, 3]


def test_the_existing_figure_walk_is_byte_identical() -> None:
    """Regression guard: the Series branch must not move a Figure's evidence shape."""
    figure = Figure(
        value="12.00",
        unit="bbl",
        derivation="drv_placeholder",
        selector="api10=3305310451&metric=lateral",
    )
    assert _selector_outputs({"figure": figure}) == {
        "api10=3305310451&metric=lateral": {"value": "12.00", "unit": "bbl"}
    }
    assert _bind_derivation(figure, "drv_response").derivation == "drv_response"
