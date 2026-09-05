"""The percentile frame is arithmetic the legend repeats to readers — it gets pinned.

The two prefix tuples below sit here for the same reason: they are module state and
registry rows, and the metrics refresh that consumes them is the database half.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from glasswell.marts import land_metrics
from glasswell.marts.land_metrics import UNPAINTED_BIN, bin_edges, liquid_bin, percentile
from glasswell.seed.jurisdictions import JURISDICTIONS


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


def test_the_two_prefix_sources_stay_separate() -> None:
    """Collapsing them would silence the anomaly alarm one of them exists to raise.

    Equal today and equal for a while: the grid covers one state and that state is in scope.
    What must not happen is one name becoming an alias of the other — so the assertion is that
    each reads its own registry column, rather than on two values Python interns to one object.

    Rewritten from an exact-declaration-text check when the prefixes moved into the registry
    (R-12). The invariant is the same one, asserted one layer down: the two remain separately
    named and separately sourced, and neither is derived from the other.
    """
    source = Path(land_metrics.__file__).read_text(encoding="utf-8")

    assert land_metrics.GRID_STATE_API_PREFIXES == ("33",)
    assert land_metrics.GRID_SCOPE_API_PREFIXES == ("33",)
    # Separately sourced: each reads the registry column named for it, and only that one.
    assert source.count('row["land_grid_state"]') == 1
    assert source.count('row["land_grid_scope"]') == 1
    assert source.count("\ndef grid_state_prefixes() -> tuple[str, ...]:") == 1
    assert source.count("\ndef grid_scope_prefixes() -> tuple[str, ...]:") == 1
    # Separately named, and neither an alias of the other in either direction.
    assert "GRID_SCOPE_API_PREFIXES: tuple[str, ...] = GRID_STATE_API_PREFIXES" not in source
    assert "GRID_STATE_API_PREFIXES: tuple[str, ...] = GRID_SCOPE_API_PREFIXES" not in source
    assert land_metrics.grid_state_prefixes is not land_metrics.grid_scope_prefixes
    # And the registry can tell them apart: a jurisdiction in scope need not be in the grid.
    scoped = {row["jurisdiction_code"] for row in JURISDICTIONS if row["land_grid_scope"]}
    gridded = {row["jurisdiction_code"] for row in JURISDICTIONS if row["land_grid_state"]}
    assert gridded <= scoped


def test_the_superseding_row_records_the_populations_it_was_written_against() -> None:
    from glasswell.seed.conformance_land import MEMBERSHIP_2

    measured = MEMBERSHIP_2["spec"]["unassigned_populations_measured"]  # type: ignore[index]

    assert measured["tx_surface"] == 355463
    assert measured["nd_surface"] == 43817
    assert measured["nm_surface_after_the_header_promotion"] == 141778
