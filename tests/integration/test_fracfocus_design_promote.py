"""canonical.well_completion_design: the disclosed base fluid, with its absences kept apart.

A blank is a fact about the source and promotes as no_report with a null volume; a filed zero
is a filing; a non-numeric literal and one above the plausibility bound are quarantined with
their reason rather than dropped or promoted.
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import psycopg
import pytest

from glasswell.ingest.fracfocus import (
    DESIGN_TABLE,
    design_rules,
    promote_resident_design,
)
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from tests.integration.test_fracfocus_load import loaded, scalar  # noqa: F401

DESIGN_ROWS = 4


def design(connection: psycopg.Connection, disclosure_id: str) -> tuple:
    with connection.cursor() as cursor:
        cursor.execute(
            "select api10, base_water_volume, base_water_unit, base_water_null_semantics"
            " from canonical.well_completion_design where disclosure_id = %s",
            (disclosure_id,),
        )
        return cursor.fetchone()


def test_the_promotion_records_the_unit_the_rule_declares(loaded, db):  # noqa: F811
    result, _ = loaded

    assert result.design_rows == DESIGN_ROWS
    assert scalar(db, f"select count(*) from {DESIGN_TABLE}") == DESIGN_ROWS
    assert scalar(db, f"select distinct base_water_unit from {DESIGN_TABLE}") == "gal"


def test_a_blank_promotes_as_no_report_rather_than_as_a_zero(loaded, db):  # noqa: F811
    api10, volume, _, semantics = design(db, "d2")

    assert (api10, volume, semantics) == ("3304300002", None, "no_report")


def test_a_filed_zero_promotes_as_a_filing(loaded, db):  # noqa: F811
    _, volume, _, semantics = design(db, "d1")

    assert (volume, semantics) == (Decimal("0.00"), "reported_zero")


def test_a_reported_volume_promotes_verbatim(loaded, db):  # noqa: F811
    _, volume, _, semantics = design(db, "d3")

    assert (volume, semantics) == (Decimal("6342549.00"), "reported")


def test_an_unparseable_literal_is_quarantined_and_never_promoted(loaded, db):  # noqa: F811
    result, _ = loaded

    assert result.design_quarantined["parse_error"] == 1
    assert design(db, "d4") is None


def test_a_volume_above_the_bound_is_quarantined_as_impossible(loaded, db):  # noqa: F811
    """The bound is a rule row, so moving it later is a superseding row rather than an edit."""
    result, _ = loaded

    assert result.design_quarantined["impossible_volume"] == 1
    assert design(db, "d5") is None
    assert scalar(
        db,
        "select count(*) from lineage.quarantine_rows where reason_code = 'impossible_volume'"
        "   and rule_id = 'cr_ff_design_promote_1'",
    ) == 1


def test_a_duplicate_disclosure_is_rejected_rather_than_collapsed(loaded, db):  # noqa: F811
    result, _ = loaded

    assert result.design_quarantined["duplicate_row"] == 1
    assert scalar(
        db, f"select count(*) from {DESIGN_TABLE} where disclosure_id = 'd3'"
    ) == 1


def test_the_design_table_refuses_an_update(loaded, db):  # noqa: F811
    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"):
        with db.cursor() as cursor:
            cursor.execute(f"update {DESIGN_TABLE} set base_water_volume = 1")
    db.rollback()


def test_the_derivation_cites_the_parse_and_both_new_rules(loaded, db):  # noqa: F811
    result, _ = loaded

    assert scalar(
        db,
        "select output_dataset from lineage.derivations where derivation_id = %s",
        (result.design_derivation_id,),
    ) == DESIGN_TABLE
    with db.cursor() as cursor:
        cursor.execute(
            "select rule_id from lineage.derivation_rules where derivation_id = %s",
            (result.design_derivation_id,),
        )
        rules = {row[0] for row in cursor.fetchall()}
        cursor.execute(
            "select ref_id from lineage.derivation_inputs"
            " where derivation_id = %s and kind = 'derivation'",
            (result.design_derivation_id,),
        )
        inputs = {row[0] for row in cursor.fetchall()}

    assert {"cr_ff_base_water_units_1", "cr_ff_design_promote_1"} <= rules
    assert result.parse_derivation_id in inputs


def test_the_rules_are_pinned_by_family_so_a_supersession_is_not_missed(loaded, db):  # noqa: F811
    units_rule, promote_rule = design_rules(db)

    assert (units_rule.rule_family, promote_rule.rule_family) == (
        "cr_ff_base_water_units",
        "cr_ff_design_promote",
    )
    assert promote_rule.spec["plausibility_max_gal"] == 50000000


def test_the_backfill_promotes_from_resident_staging_without_a_fetch(
    loaded, db, lineage_env  # noqa: F811
):
    """C5: the deployed instance already holds the staged rows and must not re-download 440 MB.

    The client would raise if anything reached the network, so a fetch is a failure here
    rather than a slow test.
    """

    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"the backfill path fetched {request.url}")

    result, _ = loaded
    with (
        httpx.Client(transport=httpx.MockTransport(refuse)),
        lineage_session(recorder=PostgresRecorder(db), environment=lineage_env),
    ):
        report = promote_resident_design(db)
    db.commit()

    assert report["outcome"] == "promoted"
    assert report["manifest_id"] == result.manifest_id
    assert report["design_rows"] == 0  # on conflict do nothing: the rows are already resident
    assert report["design_derivation_id"] == result.design_derivation_id


def test_the_backfill_states_its_outcome_when_nothing_is_staged(db, lineage_env):
    """A host that has never fetched the archive has nothing to promote, which is a plan."""
    from glasswell.seed import seed_all

    seed_all(db)
    db.commit()
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        report = promote_resident_design(db)

    assert report == {"outcome": "no_staged_disclosures", "design_rows": 0, "quarantined": {}}


def test_an_unregistered_intensity_rule_refuses_and_says_it_is_the_registry(
    db: psycopg.Connection,
):
    """R8: the loader refuses rather than defaulting, and the warning names the registry gap.

    The database is migrated and unseeded, which is the only way to reach this state — the
    registry is append-only, so a registered rule cannot be removed.
    """
    from glasswell.api.routers.completions import _intensity_policy

    policy, warnings = _intensity_policy(db)

    assert policy is None
    assert [warning["code"] for warning in warnings] == ["intensity_rule_unregistered"]
    assert "registry gap, not a fact about the well" in warnings[0]["detail"]
