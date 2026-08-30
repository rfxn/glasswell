from __future__ import annotations

from datetime import date

import psycopg
import pytest
from psycopg.rows import dict_row

from glasswell.api.provenance import register_response_figures
from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.envelope import Series
from glasswell.lineage.errors import DeterminismViolation, InvalidSelector
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.selector_registry import validate_selector
from glasswell.lineage.store import PostgresRecorder
from glasswell.seed import seed_all
from tests.support.fakes import FixedClock
from tests.support.seed import FIXTURE_ENV, seed_manifest

SELECTOR = "api10=3305310451&col=monthly_p50&split_id=spl_20210101_24"


@pytest.fixture
def source_derivation(db: psycopg.Connection) -> str:
    seed_all(db)
    manifest_id = seed_manifest(db, sha256="3" * 64)
    with (
        lineage_session(
            recorder=PostgresRecorder(db),
            environment=FIXTURE_ENV,
            clock=FixedClock(),
            correlation_id="run_series_evidence",
        ),
        derive(
            "typecurve.build",
            output=OutputSpec(
                store="parquet",
                dataset="modeling.typecurve_control",
                partition={"control_version": "tcv1.0"},
                locator="/models/typecurve_control/part-0000.parquet",
                schema_version="1",
            ),
            params={"fixture": "series_evidence"},
            inputs=[
                InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=date(2026, 8, 1))
            ],
        ) as context,
    ):
        context.set_output_hash("cd" * 32)
        context.set_rows(24)
    db.commit()
    return context.derivation_id


def _derivation_row(db, derivation_id: str) -> dict:
    with db.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select derivation_id, operation, output_dataset, output_sha256"
            " from lineage.derivations where derivation_id = %s",
            (derivation_id,),
        )
        return dict(cursor.fetchone())


def _validate(db, derivation_id: str) -> None:
    validate_selector(
        db,
        _derivation_row(db, derivation_id),
        SELECTOR,
        handle=f"{derivation_id}#{SELECTOR}",
    )


def _register(db, source: str, values, *, partition):
    payload = {
        "series": {
            "monthly_p50": Series(
                values=values, unit="bbl", derivation=source, selector=SELECTOR
            )
        }
    }
    return register_response_figures(
        db,
        payload,
        dataset="api.type_curve",
        operation_id="get_well_type_curve",
        locator="/v1/wells/3305310451/type-curve",
        partition=partition,
        input_derivations=[source],
        correlation_id="req_series_evidence",
        rule_ids=["cr_tc_peer_ladder_1"],
    )


def test_a_registered_series_resolves_through_the_response_output_profile(
    db, source_derivation
) -> None:
    bound = _register(db, source_derivation, [1.5, 2.5], partition={"api10": "3305310451"})
    response_id = bound["series"]["monthly_p50"].derivation
    assert response_id != source_derivation

    with db.cursor() as cursor:
        cursor.execute(
            "select evidence from lineage.response_selector_outputs"
            " where derivation_id = %s and selector = %s",
            (response_id, SELECTOR),
        )
        assert cursor.fetchone()[0] == {"values": [1.5, 2.5], "unit": "bbl"}

    _validate(db, response_id)


def test_a_null_valued_series_records_its_nulls_and_still_resolves(db, source_derivation) -> None:
    bound = _register(db, source_derivation, [None, None], partition={"api10": "3305310452"})
    response_id = bound["series"]["monthly_p50"].derivation
    with db.cursor() as cursor:
        cursor.execute(
            "select evidence from lineage.response_selector_outputs where derivation_id = %s",
            (response_id,),
        )
        assert cursor.fetchone()[0] == {"values": [None, None], "unit": "bbl"}
    _validate(db, response_id)


def test_replaying_the_same_series_is_idempotent_on_the_derivation_id(
    db, source_derivation
) -> None:
    first = _register(db, source_derivation, [1.5, 2.5], partition={"api10": "3305310451"})
    second = _register(db, source_derivation, [1.5, 2.5], partition={"api10": "3305310451"})
    assert (
        first["series"]["monthly_p50"].derivation == second["series"]["monthly_p50"].derivation
    )


def test_a_changed_series_value_under_the_same_partition_is_refused(db, source_derivation) -> None:
    """B-2 in miniature: one partition, two arrays, one derivation id.

    The refusal arrives one step earlier than the plan expected. The recorder compares the
    incoming output hash against the recorded one and raises DeterminismViolation before
    _record_response_outputs ever re-reads the evidence. Either way it is unhandled inside a
    request and answers 500, so E4's page key is still mandatory.
    """
    _register(db, source_derivation, [1.5, 2.5], partition={"api10": "3305310451"})
    with pytest.raises(DeterminismViolation, match="recorded output sha256"):
        _register(db, source_derivation, [9.9, 8.8], partition={"api10": "3305310451"})


def test_a_different_partition_mints_a_different_derivation(db, source_derivation) -> None:
    """And the escape hatch: page 2 must put its page key in the partition."""
    first = _register(db, source_derivation, [1.5, 2.5], partition={"limit": "2"})
    second = _register(
        db, source_derivation, [9.9, 8.8], partition={"limit": "2", "after_api10": "3305310452"}
    )
    assert (
        first["series"]["monthly_p50"].derivation != second["series"]["monthly_p50"].derivation
    )


def test_an_empty_partition_value_is_refused_so_a_null_key_must_be_omitted(
    db, source_derivation
) -> None:
    """Why E4 omits null facet keys rather than rendering them: an empty value is not a
    selector value, so a rendered null would 422 the whole page rather than page it."""
    with pytest.raises(InvalidSelector, match="disallowed characters"):
        _register(db, source_derivation, [1.5], partition={"after_api10": ""})
