"""The method control: what equal share costs, measured where both grains are published.

Montana is the one bed this system has. It publishes well-level and lease-level volumes as two
disjoint families, so the split can be scored against a truth Texas does not have — which is
also why the study is published as a control and never as a decoration on a Texas figure.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from glasswell.allocation.v0 import MODEL_ID
from glasswell.ingest import mt_bogc
from glasswell.ingest.base import open_ingest_run
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts import allocation_backtest
from glasswell.marts.allocation_backtest import quantile
from glasswell.seed import seed_all

FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "mt_bogc" / "MT_Historical_Production_sample.zip"
)


def client_for(path: Path) -> httpx.Client:
    payload = path.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload,
            headers={
                "content-type": "application/zip",
                "etag": '"4653fb2-6593e310d4b83"',
                "last-modified": "Mon, 17 Aug 2026 13:31:46 GMT",
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def scalar(db, sql: str, parameters: tuple = ()):
    with db.cursor() as cursor:
        cursor.execute(sql, parameters)
        row = cursor.fetchone()
    return row[0] if row else None


def rows(db, sql: str, parameters: tuple = ()) -> list[tuple]:
    with db.cursor() as cursor:
        cursor.execute(sql, parameters)
        return cursor.fetchall()


@pytest.fixture
def montana(db, raw_root, lineage_env):
    seed_all(db)
    db.commit()
    with open_ingest_run(
        db, source_id=mt_bogc.SOURCE_ID, raw_root=raw_root, environment=lineage_env
    ) as run, client_for(FIXTURE) as client:
        mt_bogc.ingest_archive(run, client=client)
    db.commit()
    return db


@pytest.fixture
def study(montana, lineage_env):
    with lineage_session(recorder=PostgresRecorder(montana), environment=lineage_env):
        report = allocation_backtest.refresh_allocation_backtest(montana)
    montana.commit()
    return report


def test_the_study_publishes_one_row_per_bed_and_model(study, montana) -> None:
    published = rows(
        montana,
        "select bed_jurisdiction, model_id from marts.allocation_method_error",
    )

    assert published == [(study.bed_jurisdiction, MODEL_ID)]


def test_the_bed_is_the_rule_s_declaration_and_not_a_constant_in_the_module(
    study, montana
) -> None:
    """A jurisdiction code in a serving module is what test_add_a_state.py refuses, and the bed
    is a published decision with a rationale and a date rather than a literal."""
    declared = scalar(
        montana,
        "select spec ->> 'bed_jurisdiction' from lineage.conformance_rules"
        " where rule_id = 'cr_alloc_v0_error_bounds_1'",
    )

    assert study.bed_jurisdiction == declared


def test_the_study_reads_canonical_and_not_the_staging_column_the_unit_lives_on(
    study, montana
) -> None:
    """P4 exists for this: the lease unit is a staging column, and a mart reading staging is
    the breach marts/producing.py:9-10 names."""
    from tests.support.layers import schema_reads_in

    module = (
        Path(allocation_backtest.__file__).resolve()
    )
    assert schema_reads_in(module, "staging") == []
    assert study.lease_months_scored > 0


def test_the_bed_is_the_well_family_and_never_the_pool_rows_plus_their_aggregate(
    study, montana
) -> None:
    """N-25. Montana writes three shapes for one well-month; summing the pool rows and the
    aggregate would double-count every decomposable well, and that is a mapping decision."""
    predicate = scalar(
        montana,
        "select params ->> 'bed_entity_predicate' from lineage.derivations"
        " where derivation_id = %s",
        (study.derivation_id,),
    )

    assert predicate == "entity_type='well'"


def test_the_statistic_is_bounded_and_every_published_bound_was_measured(study) -> None:
    """N-7. A relative error is unbounded above and undefined at zero truth, which is the
    commonest case rather than an edge."""
    for bound in (study.error_lo, study.p50, study.error_hi):
        assert bound is not None
        assert Decimal("-1") <= Decimal(bound) <= Decimal("1")
    assert Decimal(study.error_lo) <= Decimal(study.p50) <= Decimal(study.error_hi)


def test_a_quantile_is_a_value_the_study_measured_and_not_an_interpolation() -> None:
    values = [Decimal(value) for value in ("-0.5", "-0.1", "0", "0.2", "0.9")]

    assert quantile(values, Decimal("0.10")) == Decimal("-0.5")
    assert quantile(values, Decimal("0.50")) == Decimal("0")
    assert quantile(values, Decimal("0.90")) == Decimal("0.9")
    assert quantile([], Decimal("0.5")) is None
    # Nearest-rank: with five samples the ninetieth percentile is the largest of them, which is
    # a property of the sample and is why lease_months_scored is published beside the band.


def test_the_zero_zero_months_are_excluded_and_their_share_is_served(study) -> None:
    """A well that produced nothing in a month it was eligible for is the commonest case, and
    the excluded share is its own figure rather than something folded into the statistic."""
    assert study.excluded_zero_zero_share is not None
    assert Decimal("0") <= Decimal(study.excluded_zero_zero_share) <= Decimal("1")


def test_the_study_states_the_bed_s_shape_beside_its_bounds(study) -> None:
    """M-17. Transferability is measured before it is claimed, so the bed's multi-well
    distribution and month span travel with the bounds."""
    assert study.mean_wells_per_lease is not None
    assert Decimal(study.mean_wells_per_lease) >= 1
    assert study.months_measured
    assert sum(study.lease_month_well_counts.values()) == study.lease_months_scored


def test_no_band_reaches_a_texas_figure_from_this_study(study, montana) -> None:
    """v0's whole ruling: a band measured on another regulator's leases over a horizon that has
    not been shown to match is a naked number with a decoration on it."""
    assert study.transfer_outcome == "not_measured"
    assert scalar(
        montana,
        "select count(*) from marts.tx_allocated_production"
        " where error_bounds_outcome <> 'not_measured'",
    ) == 0


def test_the_study_cites_the_precondition_and_never_as_the_measurement(study, montana) -> None:
    """cr_mt_pru_reconciliation_1 measures that summing up agrees; it does not measure the
    error of splitting down."""
    params = scalar(
        montana,
        "select params ->> 'precondition_rule' from lineage.derivations where derivation_id = %s",
        (study.derivation_id,),
    )

    assert params == "cr_mt_pru_reconciliation_1"
    assert scalar(
        montana,
        "select count(*) from lineage.derivation_rules where derivation_id = %s"
        "   and rule_id = 'cr_alloc_v0_error_bounds_1'",
        (study.derivation_id,),
    ) == 1


def test_the_study_is_rebuilt_rather_than_appended(study, montana, lineage_env) -> None:
    with lineage_session(recorder=PostgresRecorder(montana), environment=lineage_env):
        again = allocation_backtest.refresh_allocation_backtest(montana)
    montana.commit()

    assert scalar(montana, "select count(*) from marts.allocation_method_error") == 1
    assert again.derivation_id == study.derivation_id
