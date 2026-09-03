"""The six classes, the two keys, and conservation at tolerance zero.

Every assertion here is about a figure a card will show. The share is an estimate and says so
on every row; conservation is exact by construction, so a residual is volume with no eligible
well to carry it rather than a rounding term; and a well the RRC plugged does not draw an
unannounced share to the present.
"""

from __future__ import annotations

import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import psycopg
import pytest

from glasswell.allocation.v0 import MODEL_ID
from glasswell.ingest import tx_pdq
from glasswell.ingest.tx_pdq import WELL_COMPLETION_MEMBER, _member_rows, api10_from
from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.models import OutputSpec
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts import tx_allocation
from glasswell.marts.tx_allocation import ConservationError
from glasswell.seed import seed_all
from tests.support.seed import FIXTURE_ENV, seed_derivation, seed_manifest, seed_well

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SAMPLE = FIXTURES / "tx_pdq" / "PDQ_DSV_sample.zip"
SPINE_VINTAGE = date(2026, 8, 20)
# O-08-000404's second well carries a filed plug date mid-history: it bounds, and the months
# after it are served at volume zero with the share redistributed.
PLUGGED_WITH_A_DATE = "4200300021"
PLUG_DATE = date(2024, 6, 30)
# O-08-000505's second well is plugged with no date: it does not bound, and its months are
# labelled instead. Both are plugged; only one of them has a date.
PLUGGED = {PLUGGED_WITH_A_DATE, "4213500031"}
# O-08-000808's only well is completed after every month its lease filed, so nothing is
# eligible and the volume has no well to carry it. That is the ledger's `all_wells_after_month`
# cause, and without a well like it the ledger is unreachable from one crosswalk vintage.
COMPLETED_AFTER_ITS_LEASE = "4200300050"
LATE_COMPLETION = date(2026, 1, 1)


def client_for(payload: Path) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload.read_bytes())

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
def loaded(db: psycopg.Connection, raw_root: Path, lineage_env):
    """The dump loaded over a wells spine that carries the eligibility cases.

    The spine is seeded rather than loaded from the EWA export: that fixture holds real
    Anderson-county wells and the PDQ fixture holds constructed Permian ones, so joining them
    would prove only that two unrelated cuts do not overlap. What the allocation needs from
    canonical is a well per crosswalk row with a completion date, a plug date and a status, and
    those are stated here so the eligibility cases are visible rather than incidental.
    """
    seed_all(db)
    db.commit()
    manifest = seed_manifest(db, sha256="c" * 64, source_id="tx_gis_wells_county",
                             source_key="well003.zip")
    derivation = seed_derivation(db, operation="canonical.promote")
    with zipfile.ZipFile(SAMPLE) as archive:
        completions = list(_member_rows(archive, WELL_COMPLETION_MEMBER))
    # One well per API-10, not one per completion: a wellbore completed on two leases is one
    # well, which is the whole of cr_tx_identity_collapse_1's decision.
    spine = {}
    for row in completions:
        api10 = api10_from(row["API_COUNTY_CODE"], row["API_UNIQUE_NO"])
        assert api10 is not None
        spine[api10] = row
    for api10, row in sorted(spine.items()):
        seed_well(
            db,
            api10=api10,
            state_code="42",
            county_code_at_permit=row["API_COUNTY_CODE"],
            effective_from=SPINE_VINTAGE,
            manifest_id=manifest,
            derivation_id=derivation,
            completion_date=LATE_COMPLETION
            if api10 == COMPLETED_AFTER_ITS_LEASE
            else date(2023, 1, 1),
            plug_date=PLUG_DATE if api10 == PLUGGED_WITH_A_DATE else None,
            status_canonical="plugged" if api10 in PLUGGED else "active",
            basin="permian",
        )
    db.commit()
    with lineage_session(
        recorder=PostgresRecorder(db), environment=lineage_env
    ), client_for(SAMPLE) as client:
        tx_pdq.load(
            db,
            url="https://example.invalid/PDQ_DSV.zip",
            raw_root=raw_root,
            client=client,
            expect_bytes=SAMPLE.stat().st_size,
        )
    db.commit()
    return db


@pytest.fixture
def allocated(loaded, lineage_env):
    with lineage_session(recorder=PostgresRecorder(loaded), environment=lineage_env):
        report = tx_allocation.refresh_tx_allocation(loaded)
    loaded.commit()
    return report


def test_the_mart_produces_shares_and_every_one_says_what_it_is(allocated, loaded) -> None:
    assert allocated.shares > 0
    assert rows(
        loaded,
        "select distinct allocation_model_id, error_bounds_outcome, error_rule_id"
        "  from marts.tx_allocated_production",
    ) == [(MODEL_ID, "not_measured", "cr_alloc_v0_error_bounds_1")]


def test_a_gas_lease_and_a_single_well_oil_lease_pass_through_observed(
    allocated, loaded
) -> None:
    """granularity cannot tell the two observed classes apart, because both are well_observed.
    allocation_class is what does, and it is why the wire can name them separately."""
    classes = dict(
        rows(
            loaded,
            "select allocation_class, granularity from marts.tx_allocated_production"
            " group by 1, 2",
        )
    )

    assert classes["observed_gas_well"] == "well_observed"
    assert classes["observed_single_well_lease"] == "well_observed"
    assert classes["allocated_equal_share"] == "lease_allocated"


def test_a_multi_well_oil_lease_divides_and_the_remainder_is_deterministic(
    allocated, loaded
) -> None:
    """900 over three wells divides exactly; 901 leaves one barrel, and it goes to the lowest
    API-10 rather than to whichever row the crosswalk happened to emit first."""
    january = dict(
        rows(
            loaded,
            "select api10, volume from marts.tx_allocated_production"
            " where lease_key = 'O-08-000101' and production_month = '2024-01-01'"
            "   and stream = 'liquid'",
        )
    )

    assert january == {
        "4200300001": Decimal("301.000"),
        "4200300002": Decimal("300.000"),
        "4200300003": Decimal("300.000"),
    }
    assert sum(january.values()) == Decimal("901.000")


def test_a_dual_lease_wellbore_holds_two_shares_at_one_month(allocated, loaded) -> None:
    """M-16. The mart is keyed by lease as well as by well, so the summed per-well series is a
    sum the API computes and never a row that lost its lease."""
    shares = rows(
        loaded,
        "select lease_key, stream, allocation_class from marts.tx_allocated_production"
        " where api10 = '4200300001' and production_month = '2024-01-01' order by lease_key",
    )

    assert ("G-08-000303", "gas", "observed_gas_well") in shares
    assert ("O-08-000101", "liquid", "allocated_equal_share") in shares
    assert len({lease for lease, _, _ in shares}) == 2


def test_conservation_is_exact_on_every_allocated_lease_month(allocated, loaded) -> None:
    """V-1 at tolerance zero, reconciled per lease_key from the mart directly — which is the
    grain it is defined on and which a folded row could not answer."""
    residuals = rows(
        loaded,
        "select a.lease_key, a.production_month, a.stream, sum(a.volume) as allocated,"
        "       max(c.filed) as filed"
        "  from marts.tx_allocated_production a"
        "  join (select entity_key, production_month,"
        "               case when stream in ('oil', 'condensate') then 'liquid' else 'gas' end"
        "                 as stream, sum(volume) as filed"
        "          from canonical.production_monthly_latest"
        "         where entity_type = 'lease' and source_id = 'tx_pdq_dsv'"
        "           and null_semantics in ('reported', 'reported_zero')"
        "         group by 1, 2, 3) c"
        "    on (c.entity_key, c.production_month, c.stream)"
        "     = (a.lease_key, a.production_month, a.stream)"
        " group by 1, 2, 3 having sum(a.volume) <> max(c.filed)",
    )

    assert residuals == []


def test_a_negative_correction_conserves_and_gives_no_well_a_positive_barrel(
    allocated, loaded
) -> None:
    """floor(-7/2) is -4 twice and the remainder needed to conserve is +1, which conservation
    would not catch because it conserves."""
    shares = rows(
        loaded,
        "select api10, volume from marts.tx_allocated_production"
        " where lease_key = 'O-08-000606' and production_month = '2024-06-01'"
        "   and stream = 'liquid' order by api10",
    )

    assert sum(volume for _, volume in shares) == Decimal("-7.000")
    assert all(volume <= 0 for _, volume in shares)


def test_a_lease_month_with_no_eligible_well_lands_in_the_ledger_with_a_cause(
    allocated, loaded
) -> None:
    """N-1. Nothing failed to parse, so the residual is decomposed by a closed cause vocabulary
    on the ledger rather than by a quarantine reason code."""
    assert allocated.ledger_rows > 0
    causes = {
        row[0]
        for row in rows(loaded, "select distinct cause from marts.tx_allocation_ledger")
    }

    assert causes <= set(tx_allocation.CAUSES)
    assert "all_wells_after_month" in causes
    assert scalar(
        loaded,
        "select count(*) from marts.tx_allocation_ledger where lease_key = 'O-08-000808'",
    ) > 0
    # `no_crosswalk_row` needs two crosswalk vintages -- a lease promoted under one allowlist
    # whose wells left it at the next -- so it is not reachable from a single-vintage fixture.
    # The vocabulary is closed and the cause is in it; the case belongs to a two-vintage run.
    assert "no_crosswalk_row" in tx_allocation.CAUSES


def test_the_retired_share_is_served_as_a_figure_and_not_left_open(allocated) -> None:
    """M-18. The undated-plugged case is the one eligibility error term with no date behind
    it, and V-1 serves the share of allocated volume it carries as an upper bound on it."""
    assert Decimal(allocated.share_allocated_to_retired_wells) >= 0
    assert Decimal(allocated.share_allocated_to_retired_wells) <= 1


def test_every_share_names_the_membership_vintage_it_was_resolved_against(
    allocated, loaded
) -> None:
    """v0 back-projects one crosswalk snapshot over the whole history, so a reader has to be
    able to see which snapshot a share was resolved against."""
    assert scalar(
        loaded,
        "select count(*) from marts.tx_allocated_production where membership_vintage is null",
    ) == 0
    assert allocated.membership_vintage is not None


def test_the_last_six_months_are_marked_incomplete(allocated, loaded) -> None:
    """The Commission's own sentence: production records are substantially complete after about
    six months, so the tail of every Texas chart is systematically under-filed."""
    assert allocated.incomplete_from is not None
    assert scalar(
        loaded,
        "select bool_and(incomplete_window) from marts.tx_allocated_production"
        " where production_month >= %s",
        (allocated.incomplete_from,),
    ) is True
    assert scalar(
        loaded,
        "select bool_or(incomplete_window) from marts.tx_allocated_production"
        " where production_month < %s",
        (allocated.incomplete_from,),
    ) in (False, None)


def test_the_refresh_raises_rather_than_publishing_when_conservation_fails(
    loaded, lineage_env, monkeypatch
) -> None:
    """R-2. A refresh that cannot satisfy conservation raises rather than publishing: the
    split is exact by construction, so a difference is a defect in the module."""
    import glasswell.marts.tx_allocation as module

    real = module.allocate_lease_month

    def short(volume, candidates, *, gas_lease=False):
        shares = real(volume, candidates, gas_lease=gas_lease)
        return [share for share in shares[:1]] if len(shares) > 1 else shares

    monkeypatch.setattr(module, "allocate_lease_month", short)
    with lineage_session(
        recorder=PostgresRecorder(loaded), environment=lineage_env
    ), pytest.raises(ConservationError):
        module.refresh_tx_allocation(loaded)
    loaded.rollback()


def test_the_mart_addresses_its_output_at_the_operation_that_produced_it(
    allocated, loaded
) -> None:
    """N-11. `alloc.apply` is already in the vocabulary and is the honest name for this node:
    `mart.refresh` would make the allocation indistinguishable from any other refresh."""
    operation = scalar(
        loaded,
        "select operation from lineage.derivations where derivation_id = %s",
        (allocated.derivation_id,),
    )

    assert operation == "alloc.apply"
    assert scalar(
        loaded,
        "select output_dataset from lineage.derivations where derivation_id = %s",
        (allocated.derivation_id,),
    ) == "marts.tx_allocated_production"


def test_the_jurisdiction_is_read_from_the_registry_and_not_written_in_the_mart(
    allocated, loaded
) -> None:
    """A jurisdiction code in a serving module is what test_add_a_state.py refuses, and it
    refuses it because the registry is where a jurisdiction is declared."""
    partition = scalar(
        loaded,
        "select output_partition ->> 'jurisdiction' from lineage.derivations"
        " where derivation_id = %s",
        (allocated.derivation_id,),
    )

    assert partition == scalar(
        loaded,
        "select jurisdiction_code from lineage.jurisdiction_rules"
        " where rule_id = 'cr_tx_allocation_v0_1' and serving limit 1",
    )


def test_a_second_refresh_rebuilds_rather_than_appending(allocated, loaded, lineage_env) -> None:
    """Marts are rebuilt, never appended: two runs over one input are one answer."""
    before = scalar(loaded, "select count(*) from marts.tx_allocated_production")
    with lineage_session(recorder=PostgresRecorder(loaded), environment=lineage_env):
        again = tx_allocation.refresh_tx_allocation(loaded)
    loaded.commit()

    assert scalar(loaded, "select count(*) from marts.tx_allocated_production") == before
    assert again.derivation_id == allocated.derivation_id


# V-2a's own inputs: the PDQ crosswalk the dump promotes, and the EWA export's links kept
# beside it and never merged (cr_tx_ewa_role_1). The fixture loads the first and not the
# second, which is the state of an instance that has never run the wellbore ingest.
VALIDATOR_SOURCE = "tx_w10_wlf607"


@pytest.fixture
def with_the_validator_crosswalk(loaded: psycopg.Connection):
    """One EWA link per PDQ well, with one wellbore deliberately mapped to another lease."""
    manifest = seed_manifest(
        loaded, sha256="d" * 64, source_id=VALIDATOR_SOURCE, source_key="wlf607.zip"
    )
    with lineage_session(recorder=PostgresRecorder(loaded), environment=FIXTURE_ENV), derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset="canonical.well_lease_links",
            partition={"source_id": VALIDATOR_SOURCE},
        ),
        params={"link_role": "validator_a"},
    ) as context:
        context.set_output_hash("d" * 64)
    derivation = context.derivation_id
    with loaded.cursor() as cursor:
        cursor.execute(
            "select api10, lease_key from canonical.lease_membership"
            " where link_role = 'canonical_crosswalk' order by api10, lease_key"
        )
        membership = cursor.fetchall()
        disagreeing = membership[0][0]
        cursor.executemany(
            "insert into canonical.well_lease_links (api10, lease_key, oil_gas_code,"
            " district_no, lease_no, link_role, source_id, effective_from,"
            " source_manifest_id, derivation_id)"
            " values (%(api10)s, %(lease_key)s, %(code)s, %(district)s, %(lease_no)s,"
            " 'validator_a', %(source)s, %(vintage)s, %(manifest)s, %(derivation)s)"
            " on conflict do nothing",
            [
                {
                    "api10": api10,
                    # The disagreement the block exists to measure: the same wellbore under a
                    # different lease key in the other regulator-published crosswalk.
                    "lease_key": f"{lease_key}-B" if api10 == disagreeing else lease_key,
                    "code": lease_key.split("-")[0],
                    "district": lease_key.split("-")[1],
                    "lease_no": lease_key.split("-")[2],
                    "source": VALIDATOR_SOURCE,
                    "vintage": SPINE_VINTAGE,
                    "manifest": manifest,
                    "derivation": derivation,
                }
                for api10, lease_key in membership
            ],
        )
    loaded.commit()
    return loaded


def test_no_residual_is_published_where_only_one_crosswalk_is_loaded(
    allocated, loaded
) -> None:
    """The fixture loads the PDQ crosswalk and not the EWA export, which is the state of an
    instance that has never run the wellbore ingest. Every well would be "in one crosswalk and
    not the other" -- a measured 100 percent disagreement over an input nobody loaded."""
    assert allocated.crosswalk_rows == 0
    assert scalar(loaded, "select count(*) from marts.tx_crosswalk_residual") == 0


def test_the_residual_is_measured_per_district_where_both_crosswalks_are_loaded(
    with_the_validator_crosswalk, lineage_env
) -> None:
    """V-2a: wells assigned to different lease keys, as counts, shares and a district
    breakdown. It reports and does not gate, so a disagreement is a row and not a refusal."""
    db = with_the_validator_crosswalk
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        report = tx_allocation.refresh_tx_allocation(db)
    db.commit()

    residual = rows(
        db,
        "select district_no, disagreement_kind, well_count, share"
        "  from marts.tx_crosswalk_residual order by district_no, disagreement_kind",
    )

    assert report.crosswalk_rows == len(residual) > 0
    assert {row[1] for row in residual} <= {
        "only_in_pdq",
        "only_in_validator",
        "different_lease_key",
    }
    assert "different_lease_key" in {row[1] for row in residual}
    for _district, _kind, count, share in residual:
        assert count > 0
        assert Decimal(0) < Decimal(share) <= Decimal(1)


def test_the_residual_cites_both_crosswalks_it_measured(
    with_the_validator_crosswalk, lineage_env
) -> None:
    """A residual whose chain names only one of the two crosswalks is a measurement a reader
    cannot check: the disagreement is between them."""
    db = with_the_validator_crosswalk
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        report = tx_allocation.refresh_tx_allocation(db)
    db.commit()

    sources = {
        row[0]
        for row in rows(
            db,
            "select distinct d.output_dataset from lineage.derivation_inputs i"
            "  join lineage.derivations d on d.derivation_id = i.ref_id"
            " where i.derivation_id = %s",
            (report.derivation_id,),
        )
    }

    assert "canonical.lease_membership" in sources
    assert "canonical.well_lease_links" in sources
