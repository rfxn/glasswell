"""The percentile frame is arithmetic the legend repeats to readers — it gets pinned."""

from __future__ import annotations

import pytest

from glasswell.marts.land_metrics import UNPAINTED_BIN, bin_edges, liquid_bin, percentile


def test_percentile_is_percentile_cont_linear_interpolation():
    ordered = [0.0, 10.0, 20.0, 30.0, 40.0]
    assert percentile(ordered, 0.0) == 0.0
    assert percentile(ordered, 1.0) == 40.0
    assert percentile(ordered, 0.5) == 20.0
    # (n-1)*q = 4*0.02 = 0.08 → 8% of the way from 0 to 10.
    assert percentile(ordered, 0.02) == pytest.approx(0.8)


def test_percentile_of_an_empty_population_refuses():
    with pytest.raises(ValueError, match="empty population"):
        percentile([], 0.5)


def test_edges_are_min_p2_through_p98_max():
    values = [float(v) for v in range(1, 101)]
    edges = bin_edges(values)
    assert len(edges) == 8
    assert edges[0] == 1.0
    assert edges[-1] == 100.0
    assert edges[1] == pytest.approx(2.98)  # P2
    assert edges[-2] == pytest.approx(98.02)  # P98
    assert edges == sorted(edges)


def test_bins_clamp_through_the_percentile_frame():
    edges = bin_edges([float(v) for v in range(1, 101)])
    assert liquid_bin(0.0, edges) == UNPAINTED_BIN
    assert liquid_bin(-5.0, edges) == UNPAINTED_BIN
    # Below P2 and at the minimum: the first bin, never invisible.
    assert liquid_bin(1.0, edges) == 0
    # A far-outlier artefact stays in the last bin instead of stretching the ramp — the
    # P98 clamp is what the bins exist for.
    assert liquid_bin(5_628_503_000.0, edges) == 6
    assert liquid_bin(50.0, edges) == 3


def test_a_one_cell_population_bins_degenerately_but_deterministically():
    edges = bin_edges([42.0])
    assert edges == [42.0] * 8
    assert liquid_bin(42.0, edges) == 6
