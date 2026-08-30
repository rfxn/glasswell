"""The producing classifier against a population built to break it.

Every well below exists because the live data holds its shape: a filed zero beside an absent
filing, a month restated down to nothing, a well lifting only water, a confidential well whose
months never reached canonical, and a Texas well whose regulator reports at the lease. The
classes have to survive all five, because on the deployed load they are 1,082,374 filed zeros,
4,368 withheld wells and 114,122 Texas wells the state calls active.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import psycopg
import pytest
from psycopg.rows import dict_row

from glasswell.lineage.conformance import lease_reporting_rule, pool_grain_rule
from glasswell.marts.producing import (
    NOT_PRODUCING,
    PRODUCING,
    UNKNOWN,
    ProducingPolicyError,
    anchor_month,
    class_expression,
    load_producing_policy,
    no_well_series_states,
    producing_params,
    window_start,
)
from glasswell.seed import seed_all
from tests.support.seed import seed_derivation, seed_manifest, seed_production, seed_well

ANCHOR = date(2026, 3, 1)
INSIDE = date(2026, 2, 1)
STALE = date(2025, 1, 1)
VINTAGE = date(2026, 4, 1)
EARLIER_VINTAGE = date(2026, 3, 15)

CLASSIFY = f"""
select w.api10, {class_expression(api10="w.api10", state_code="w.state_code")} as producing
  from canonical.wells w
 order by w.api10
"""


@pytest.fixture
def population(db: psycopg.Connection) -> psycopg.Connection:
    seed_all(db)
    manifest = seed_manifest(db, sha256="d" * 64, source_key="2026_03.xlsx")
    derivation = seed_derivation(db)
    kw = {"manifest_id": manifest, "derivation_id": derivation}

    def well(api10: str, **overrides: object) -> None:
        seed_well(db, api10=api10, manifest_id=manifest, derivation_id=derivation, **overrides)

    def production(api10: str, **overrides: object) -> None:
        seed_production(
            db,
            api10=api10,
            production_month=overrides.pop("production_month", INSIDE),  # type: ignore[arg-type]
            report_vintage=overrides.pop("report_vintage", VINTAGE),  # type: ignore[arg-type]
            **kw,
            **overrides,  # type: ignore[arg-type]
        )

    # The anchor: one well always holds the newest month, so the window is deterministic.
    well("3305300001", status_canonical="active")
    production("3305300001", production_month=ANCHOR, volume=Decimal("900"))

    well("3305300002", status_canonical="active")  # oil inside the window
    production("3305300002", volume=Decimal("500"))

    well("3305300003", status_canonical="active")  # gas only, still a hydrocarbon
    production("3305300003", stream="gas", volume=Decimal("1200"))

    well("3305300004", status_canonical="active")  # filed a zero: a fact, not an absence
    production("3305300004", volume=Decimal("0"), null_semantics="reported_zero")

    well("3305300005", status_canonical="active")  # water only
    production("3305300005", stream="water", volume=Decimal("700"))

    well("3305300006", status_canonical="active")  # nothing filed in the window at all
    production("3305300006", production_month=STALE, volume=Decimal("400"))

    well("3305300007", status_canonical="active")  # never filed anything
    well("3305300008", status_canonical="confidential", confidential_flag=True)

    # A month restated down to nothing: the newest vintage is the one that counts (DIR-2).
    well("3305300009", status_canonical="active")
    production("3305300009", volume=Decimal("800"), report_vintage=EARLIER_VINTAGE)
    production("3305300009", volume=Decimal("0"), null_semantics="reported_zero")

    # A month restated upward, to prove the rule is newest-vintage and not lowest-volume.
    well("3305300010", status_canonical="active")
    production("3305300010", volume=Decimal("0"), null_semantics="reported_zero",
               report_vintage=EARLIER_VINTAGE)
    production("3305300010", volume=Decimal("650"))

    well("4200300001", status_canonical="active", state_code="42")
    db.commit()
    return db


def classify(connection: psycopg.Connection) -> dict[str, str]:
    policy = load_producing_policy(connection)
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(CLASSIFY, producing_params(connection, policy))
        return {row["api10"]: row["producing"] for row in cursor.fetchall()}


def test_the_window_is_anchored_on_the_newest_filed_month_not_on_today(population) -> None:
    policy = load_producing_policy(population)

    assert anchor_month(population, policy) == ANCHOR
    assert window_start(ANCHOR, policy) == date(2026, 1, 1)


def test_a_positive_hydrocarbon_month_inside_the_window_is_producing(population) -> None:
    classes = classify(population)

    assert classes["3305300002"] == PRODUCING
    assert classes["3305300003"] == PRODUCING


def test_a_filed_zero_is_not_producing_because_the_regulator_said_zero(population) -> None:
    assert classify(population)["3305300004"] == NOT_PRODUCING


def test_a_well_lifting_only_water_is_not_producing_but_is_not_unknown(population) -> None:
    """It filed, so the absence is not an absence: water is served, it is just not evidence."""
    assert classify(population)["3305300005"] == NOT_PRODUCING


def test_a_well_that_filed_nothing_in_the_window_is_unknown_not_not_producing(
    population,
) -> None:
    """The distinction the whole classifier exists for: no filing is an absence of evidence."""
    classes = classify(population)

    assert classes["3305300006"] == UNKNOWN
    assert classes["3305300007"] == UNKNOWN


def test_a_confidential_well_whose_months_are_withheld_is_unknown(population) -> None:
    """A regulator holding the number back is not a well that stopped producing."""
    assert classify(population)["3305300008"] == UNKNOWN


def test_a_month_restated_to_zero_stops_answering_producing(population) -> None:
    assert classify(population)["3305300009"] == NOT_PRODUCING


def test_a_month_restated_upward_starts_answering_producing(population) -> None:
    assert classify(population)["3305300010"] == PRODUCING


def test_a_jurisdiction_with_no_well_level_series_is_unknown_and_never_not_producing(
    population,
) -> None:
    """DIR-3: a state with no well-level series has nothing for its wells to be absent from.

    Two registry reasons produce that, and the function returns both because the consequence is
    the same: Texas files above the well and needs allocation, New Mexico files below it and
    nothing rolls up. Which reason applies to which state stays separable — that is what the
    two rule readers below are for — but neither state may be answered `not_producing`.
    """
    assert no_well_series_states(population) == ["30", "42"]
    assert classify(population)["4200300001"] == UNKNOWN


def test_the_two_reasons_for_an_absent_series_do_not_collapse_into_each_other(
    population,
) -> None:
    """A test that would pass on a query that returned every state for either reason."""
    assert lease_reporting_rule(population, "42") is not None
    assert lease_reporting_rule(population, "30") is None
    assert pool_grain_rule(population, "30") is not None
    assert pool_grain_rule(population, "42") is None
    assert pool_grain_rule(population, "33") is None


def test_the_policy_comes_from_the_registry_rather_than_from_the_code(population) -> None:
    policy = load_producing_policy(population)

    assert policy.window_months == 3
    assert policy.streams == ("gas", "oil")
    assert policy.evidence_semantics == ("reported",)


def test_an_unregistered_definition_refuses_rather_than_assuming_a_window(
    db: psycopg.Connection,
) -> None:
    """R8 with teeth. The rows are the definition, so a database without them has no producing
    question to answer — and says so, instead of falling back to a window nobody wrote down."""
    with pytest.raises(ProducingPolicyError, match="cr_producing_window_1"):
        load_producing_policy(db)
