"""The land grid's membership universe is every state, and the served figure must not move.

Modelled on `test_mart_state_scope.py`, whose docstring is about this exact class of bug:
nothing failed and no test moved, because no test had ever run a refresh with two states in the
database. This one runs it with three.

The finding it guards is that 355,463 Texas surface points are already in the universe and all
of them are unassigned. Scoping the universe to the grid's own states would have collapsed the
served `unassigned_wells` count to about zero and called it a no-op — and an ND-only fixture
could not have caught it, because it contains nothing for the filter to remove.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts import land_metrics
from glasswell.marts.land_metrics import refresh_land_metrics
from glasswell.marts.land_units import refresh_land_units
from glasswell.seed import seed_all
from tests.integration.test_blm_plss_load import load_all
from tests.integration.test_land_metrics import (
    HORIZONTAL,
    HORIZONTAL_LATERAL,
    HORIZONTAL_SURFACE,
    MONTH,
    VERTICAL,
    VERTICAL_SURFACE,
    VINTAGE,
    cell,
)
from tests.integration.test_marts_nd import rows, scalar
from tests.support.seed import (
    seed_derivation,
    seed_manifest,
    seed_production,
    seed_well,
    seed_well_spatial,
)

pytestmark = pytest.mark.integration

SECTION_A = "ND051520N0950W0SN360"
SECTION_B = "ND051520N0950W0SN130"

# Two Texas wells and two New Mexico wells, all with surface points, none with a grid to fall
# in — the live shape, at four rows instead of 355,463.
TX_WELLS = ("4200399001", "4200399002")
NM_WELLS = ("3001599001", "3001599002")
OUT_OF_SCOPE_SURFACE = (
    "POINT(-102.1000 31.9000)",
    "POINT(-102.2000 31.9500)",
    "POINT(-103.9000 32.1000)",
    "POINT(-103.8000 32.2000)",
)


@pytest.fixture
def three_states(db, raw_root, lineage_env):
    """North Dakota with a grid and land units; Texas and New Mexico with points and no grid."""
    seed_all(db)
    db.commit()
    load_all(db, raw_root, lineage_env)

    for api10, surface in ((HORIZONTAL, HORIZONTAL_SURFACE), (VERTICAL, VERTICAL_SURFACE)):
        seed_well(db, api10=api10)
        seed_well_spatial(db, api10=api10, geom_type="surface", wkt=surface)
    seed_well_spatial(db, api10=HORIZONTAL, geom_type="lateral", wkt=HORIZONTAL_LATERAL)

    for api10, surface in zip((*TX_WELLS, *NM_WELLS), OUT_OF_SCOPE_SURFACE, strict=True):
        seed_well(db, api10=api10, state_code=api10[:2])
        seed_well_spatial(db, api10=api10, geom_type="surface", wkt=surface)

    manifest_id = seed_manifest(db, sha256="f" * 64)
    derivation_id = seed_derivation(db)
    for api10, stream, volume in (
        (HORIZONTAL, "oil", Decimal("1000")),
        (VERTICAL, "oil", Decimal("200")),
        # Out-of-scope wells that produced: their barrels must not reach a cell, and their
        # absence must not be the reason the counter is right.
        (TX_WELLS[0], "oil", Decimal("9999")),
        (NM_WELLS[0], "oil", Decimal("8888")),
    ):
        seed_production(
            db,
            api10=api10,
            production_month=MONTH,
            report_vintage=VINTAGE,
            volume=volume,
            stream=stream,
            manifest_id=manifest_id,
            derivation_id=derivation_id,
        )
    db.commit()

    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        refresh_land_units(db)
        refresh = refresh_land_metrics(db)
    db.commit()
    return db, refresh


def test_the_unassigned_total_still_counts_every_state(three_states) -> None:
    """The figure this change must not move. Four out-of-scope wells, four unassigned."""
    _, refresh = three_states

    assert refresh.unassigned_wells == len(TX_WELLS) + len(NM_WELLS)


def test_the_grid_state_anomaly_counter_stays_zero(three_states) -> None:
    """It exists to say that a well the grid should hold was not held. No such well exists."""
    _, refresh = three_states

    assert refresh.unassigned_grid_state_wells == 0


def test_the_third_counter_is_the_out_of_scope_population(three_states) -> None:
    _, refresh = three_states

    assert refresh.unassigned_out_of_grid_scope_wells == len(TX_WELLS) + len(NM_WELLS)


def test_the_three_counters_reconcile(three_states) -> None:
    """In-scope unassigned plus out-of-scope unassigned is the total, by construction."""
    _, refresh = three_states
    in_scope = refresh.unassigned_wells - refresh.unassigned_out_of_grid_scope_wells

    assert in_scope >= refresh.unassigned_grid_state_wells
    assert in_scope + refresh.unassigned_out_of_grid_scope_wells == refresh.unassigned_wells


def test_the_derivation_params_carry_all_three_and_both_prefix_sets(three_states) -> None:
    db, refresh = three_states
    params = scalar(
        db,
        "select params from lineage.derivations where derivation_id = %s",
        (refresh.derivation_id,),
    )

    assert params["unassigned_wells"] == 4
    assert params["unassigned_grid_state_wells"] == 0
    assert params["unassigned_out_of_grid_scope_wells"] == 4
    assert params["grid_state_api_prefixes"] == ["33"]
    assert params["grid_scope_api_prefixes"] == ["33"]


def test_the_two_prefix_constants_stay_separate() -> None:
    """Collapsing them would silence the anomaly alarm one of them exists to raise.

    Equal today and equal for a while: the grid covers one state and that state is in scope.
    What must not happen is one name becoming an alias of the other, so the assertion is on the
    two declarations rather than on two values that Python interns to one object.
    """
    source = Path(land_metrics.__file__).read_text(encoding="utf-8")

    assert land_metrics.GRID_STATE_API_PREFIXES == ("33",)
    assert land_metrics.GRID_SCOPE_API_PREFIXES == ("33",)
    assert source.count("\nGRID_STATE_API_PREFIXES = ") == 1
    assert source.count("\nGRID_SCOPE_API_PREFIXES: tuple[str, ...] = ") == 1
    assert "GRID_SCOPE_API_PREFIXES = GRID_STATE_API_PREFIXES" not in source


def test_the_cells_are_unchanged_by_the_presence_of_two_other_states(three_states) -> None:
    """No out-of-scope well reaches a cell, and no out-of-scope barrel reaches a sum."""
    db, refresh = three_states

    assert cell(db, SECTION_A)[1] == 1
    assert cell(db, SECTION_B)[1] == 1
    assert scalar(db, "select sum(liquid_cum_bbl) from marts.land_metrics_tile") == 2400.0
    assert refresh.row_counts == {"land_metrics_tile": 3}


def test_the_production_cte_restriction_changes_no_output(three_states) -> None:
    """13.3's cost fix, asserted as output identity rather than argued.

    The restricted CTE is run beside an unrestricted copy of itself on the same database; the
    per-well sums must be identical over the wells membership joins.
    """
    db, _ = three_states
    unrestricted = land_metrics._MEMBERSHIP.replace(
        "       and api10 in (select api10 from member)\n", ""
    )
    assert unrestricted != land_metrics._MEMBERSHIP

    tail = (
        "select member.api10, coalesce(prod.liquid_bbl, 0)::float8"
        "  from member left join prod using (api10) order by member.api10"
    )
    restricted_rows = rows(db, land_metrics._MEMBERSHIP + tail)
    unrestricted_rows = rows(db, unrestricted + tail)

    assert restricted_rows == unrestricted_rows
    assert restricted_rows


def test_the_membership_rule_cited_is_the_superseding_row(three_states) -> None:
    db, refresh = three_states
    linked = {
        rule
        for (rule,) in rows(
            db,
            "select rule_id from lineage.derivation_rules where derivation_id = %s",
            (refresh.derivation_id,),
        )
    }

    assert "cr_land_agg_membership_2" in linked
    assert "cr_land_agg_membership_1" not in linked
    superseded = rows(
        db,
        "select supersedes_rule_id, spec ->> 'version' from lineage.conformance_rules"
        " where rule_id = 'cr_land_agg_membership_2'",
    )
    assert superseded == [("cr_land_agg_membership_1", "2")]
    # The superseded row is history, not a mistake: it stays exactly as written.
    assert rows(
        db,
        "select count(*) from lineage.conformance_rules where rule_id = %s",
        ("cr_land_agg_membership_1",),
    ) == [(1,)]


def test_the_superseding_row_records_the_populations_it_was_written_against() -> None:
    from glasswell.seed.conformance_land import MEMBERSHIP_2

    measured = MEMBERSHIP_2["spec"]["unassigned_populations_measured"]  # type: ignore[index]

    assert measured["tx_surface"] == 355463
    assert measured["nd_surface"] == 43817
    assert measured["nm_surface_after_the_header_promotion"] == 141778


def test_the_land_grid_scope_migration_registers_the_publication(three_states) -> None:
    db, _ = three_states

    assert rows(
        db,
        "select evidence_tag from lineage.conformance_rule_publications where rule_id = %s",
        ("cr_land_agg_membership_2",),
    ) == [("v0.68",)]


def test_a_land_unit_is_not_created_for_a_state_with_no_grid(three_states) -> None:
    """The out-of-scope wells are unassigned because there is no grid, not because a filter
    removed them: `anchor` still holds every one of them."""
    db, _ = three_states
    anchored = rows(
        db,
        land_metrics._MEMBERSHIP + "select count(*) from anchor",
    )
    assert anchored == [(2 + len(TX_WELLS) + len(NM_WELLS),)]
    assert scalar(
        db,
        "select count(*) from canonical.land_units where left(land_unit_id, 2) <> 'ND'",
    ) == 0


def test_the_out_of_scope_wells_are_the_states_the_grid_does_not_cover(three_states) -> None:
    db, _ = three_states
    universe = rows(
        db,
        land_metrics._MEMBERSHIP
        + "select left(anchor.api10, 2), count(*) from anchor"
        "  where not exists (select 1 from member where member.api10 = anchor.api10)"
        "  group by 1 order by 1",
    )

    assert universe == [("30", 2), ("42", 2)]


def test_the_month_is_the_one_the_fixture_seeded(three_states) -> None:
    """Guards the fixture rather than the mart: a silent month drift would make the sums above
    pass for the wrong reason."""
    db, _ = three_states

    assert scalar(
        db, "select min(production_month) from canonical.production_monthly"
    ) == date(MONTH.year, MONTH.month, 1)
