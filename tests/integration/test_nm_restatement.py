"""DIR-2 at New Mexico's grain: Arms A and C, plus the arm the four do not cover.

Arms B and D — identical bytes, and a vintage that never comes from MDTM — live in
`test_nm_fetch_vintage.py`, where the fetch is. What is here is what promotion decides: a
restatement is a value change appended under a new vintage, a `mod_dte` bump is not a
restatement, and a second promotion inside one vintage is a no-op or a refusal, never a partial
land (wave-1's cross-cutting lesson from gate-a1b Defect A).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from glasswell.lineage.errors import VintageAlreadyPromoted
from glasswell.lineage.vintages import select_production
from tests.integration.test_nm_promote import (
    DAY_ONE,
    DAY_TWO,
    FIXTURE_ROWS,
    FULL_HISTORY,
    IN_WINDOW_ROWS,
    SPINE_SOURCE,
    promote,
    query,
    scalar,
    spine_record,
)
from tests.integration.test_nm_promote import seeded as _seeded
from tests.integration.test_nm_promote import staged_day_one as _staged_day_one
from tests.integration.test_nm_promote import staging_root as _staging_root
from tests.integration.test_nm_stage import fixture_for, stage, synthetic_document

# Re-exported rather than redefined: pytest resolves a fixture by module attribute.
seeded = _seeded
staged_day_one = _staged_day_one
staging_root = _staging_root

# SOURCE.md: the amended fixture differs in one record and three cells — prod_amt 2983 -> 3983,
# amend_ind N -> Y, mod_dte bumped. The record is 30-45-23968 pool 72319, 2014-03, gas.
AMENDED_KEY = "3004523968:72319"
AMENDED_MONTH = date(2014, 3, 1)
BASE_VOLUME = Decimal("2983.000")
AMENDED_VOLUME = Decimal("3983.000")


def restage(db, raw_root, tmp_path, monkeypatch, *, name: str, at):
    return stage(
        db,
        raw_root,
        tmp_path,
        monkeypatch,
        document=(fixture_for("wcproduction").parent / name).read_bytes(),
        at=at,
    )


def gas_rows(db):
    return query(
        db,
        "select report_vintage, volume, value_hash from canonical.production_monthly"
        " where source_id = %s and entity_key = %s and production_month = %s and stream = 'gas'"
        " order by report_vintage",
        SPINE_SOURCE,
        AMENDED_KEY,
        AMENDED_MONTH,
    )


def test_changed_bytes_on_two_days_append_one_row_and_keep_the_first(
    db, staged_day_one, raw_root, tmp_path, monkeypatch
) -> None:
    """Arm A. One cell moved, so one row is appended at a second vintage and the first still
    answers as of the first day."""
    first = promote(db, window_start=FULL_HISTORY)
    restage(db, raw_root, tmp_path, monkeypatch, name="nm_wcproduction_300_amended.xml", at=DAY_TWO)

    second = promote(db, at=DAY_TWO, window_start=FULL_HISTORY)

    assert first.promoted_rows == FIXTURE_ROWS
    assert second.promoted_rows == 1
    assert second.restatement_summary == {AMENDED_MONTH.isoformat(): 1}
    assert gas_rows(db) == [
        (DAY_ONE.date(), BASE_VOLUME, gas_rows(db)[0][2]),
        (DAY_TWO.date(), AMENDED_VOLUME, gas_rows(db)[1][2]),
    ]
    assert gas_rows(db)[0][2] != gas_rows(db)[1][2]


def test_the_manifest_chain_is_built_on_the_undated_filename(
    db, staged_day_one, raw_root, tmp_path, monkeypatch
) -> None:
    """Arm A.3: a vintage-stamped source_key would start a new chain every pull and no
    restatement would ever be detected."""
    restage(db, raw_root, tmp_path, monkeypatch, name="nm_wcproduction_300_amended.xml", at=DAY_TWO)

    manifests = query(
        db,
        "select source_key, fetch_vintage, supersedes_manifest_id from lineage.manifests"
        " where source_id = %s order by fetch_vintage",
        SPINE_SOURCE,
    )

    assert [row[0] for row in manifests] == ["wcproduction.zip", "wcproduction.zip"]
    assert [row[1] for row in manifests] == [DAY_ONE.date(), DAY_TWO.date()]
    assert manifests[1][2] == staged_day_one.manifest_id
    assert manifests[0][2] is None


def test_an_as_of_read_still_returns_the_answer_that_was_current_then(
    db, staged_day_one, raw_root, tmp_path, monkeypatch
) -> None:
    """Arm A.6. Gate G8 is what makes this meaningful: the window partitions on the S-E key,
    so a well's two pools are two heads rather than one shadowing the other."""
    promote(db, window_start=FULL_HISTORY)
    restage(db, raw_root, tmp_path, monkeypatch, name="nm_wcproduction_300_amended.xml", at=DAY_TWO)
    promote(db, at=DAY_TWO, window_start=FULL_HISTORY)

    selector = {
        "entity_type": "well_completion_pool",
        "entity_key": AMENDED_KEY,
        "production_month": AMENDED_MONTH,
        "stream": "gas",
        "source_id": SPINE_SOURCE,
    }
    as_of_day_one = select_production(db, as_of=DAY_ONE.date(), **selector)
    latest = select_production(db, **selector)

    assert [row["volume"] for row in as_of_day_one] == [BASE_VOLUME]
    assert [row["volume"] for row in latest] == [AMENDED_VOLUME]
    assert latest[0]["report_vintage"] == DAY_TWO.date()


def test_both_pools_of_the_amended_well_are_still_two_heads(
    db, staged_day_one, raw_root, tmp_path, monkeypatch
) -> None:
    """The multi-pool well is the amended one, so an api10-keyed window would answer this
    question with one row and would look right while being wrong (B2/G8)."""
    promote(db, window_start=FULL_HISTORY)
    restage(db, raw_root, tmp_path, monkeypatch, name="nm_wcproduction_300_amended.xml", at=DAY_TWO)
    promote(db, at=DAY_TWO, window_start=FULL_HISTORY)

    heads = select_production(
        db, api10="3004523968", production_month=AMENDED_MONTH, stream="gas"
    )

    assert len(heads) == 2
    assert {row["well_completion_pool"] for row in heads} == {"72319", "71599"}
    assert {row["report_vintage"] for row in heads} == {DAY_ONE.date(), DAY_TWO.date()}


def test_a_mod_dte_that_moves_without_a_measurement_appends_nothing(
    db, staged_day_one, raw_root, tmp_path, monkeypatch
) -> None:
    """Arm C, the labelled synthetic invariant (SOURCE.md). The artifact changed, so there is
    a new manifest at a new vintage; nothing measured changed, so canonical is untouched. At
    48.1M rows a `mod_dte` semantics drift that manufactured restatements would be
    unrecoverable, which is what this is the regression for."""
    promote(db, window_start=FULL_HISTORY)
    restaged = restage(
        db, raw_root, tmp_path, monkeypatch, name="nm_wcproduction_300_moddte.xml", at=DAY_TWO
    )

    second = promote(db, at=DAY_TWO, window_start=FULL_HISTORY)

    assert restaged.manifest_id != staged_day_one.manifest_id
    assert second.promoted_rows == 0
    assert second.restatement_summary == {}
    assert second.skipped_unchanged_mod_dte == 0  # every mod_dte moved: nothing to skip
    assert second.suppressed_unchanged == FIXTURE_ROWS
    assert scalar(db, "select count(*) from canonical.production_monthly where source_id = %s",
                  SPINE_SOURCE) == FIXTURE_ROWS
    assert scalar(
        db,
        "select count(*) from lineage.audit_events where event_type = %s",
        "canonical.restatement_detected",
    ) == 0
    assert query(
        db,
        "select vintage_date, rows_examined, rows_appended from lineage.vintages"
        " where source_id = %s order by vintage_date",
        SPINE_SOURCE,
    ) == [(DAY_ONE.date(), FIXTURE_ROWS, FIXTURE_ROWS), (DAY_TWO.date(), FIXTURE_ROWS, 0)]


def ledger_fingerprint(db) -> dict[str, object]:
    """What a refusal may not move, in the shape gate-a1b's re-gate measured it."""
    return {
        "canonical_rows": scalar(db, "select count(*) from canonical.production_monthly"),
        "canonical_volume": scalar(
            db, "select coalesce(sum(volume), 0) from canonical.production_monthly"
        ),
        "newest_vintage": scalar(
            db, "select max(report_vintage) from canonical.production_monthly"
        ),
        "quarantine_rows": scalar(db, "select count(*) from lineage.quarantine_rows"),
        "vintages": scalar(db, "select count(*) from lineage.vintages"),
        "rows_appended": scalar(
            db, "select coalesce(sum(rows_appended), 0) from lineage.vintages"
        ),
        "well_completions": scalar(db, "select count(*) from canonical.well_completions"),
        "derivations": scalar(db, "select count(*) from lineage.derivations"),
        "audit_events": scalar(db, "select count(*) from lineage.audit_events"),
    }


def test_a_second_promotion_inside_one_vintage_that_agrees_is_a_no_op(db, staged_day_one) -> None:
    """The fifth arm. A re-run that computes what is already recorded lands nothing, and the
    vintage keeps the counters of the pass that did the work rather than being overwritten with
    zeroes (gate-a1b's §4 minor)."""
    promote(db)
    before = ledger_fingerprint(db)
    events = scalar(db, "select count(*) from lineage.audit_events")

    again = promote(db)

    after = ledger_fingerprint(db)

    assert again.promoted_rows == 0
    assert again.suppressed_unchanged == 29
    assert {key: value for key, value in after.items() if key != "audit_events"} == {
        key: value for key, value in before.items() if key != "audit_events"
    }
    # The one thing a no-op does record is that it happened and learned nothing.
    assert after["audit_events"] == events + 1


def test_a_second_promotion_inside_one_vintage_that_disagrees_is_refused(
    db, staged_day_one, raw_root, tmp_path, monkeypatch
) -> None:
    """A1b's landed semantics, reused rather than reinvented: knowledge time is a date, so two
    promotions on one day share a primary key, and `on conflict do nothing` would swallow the
    difference. The refusal names the row."""
    promote(db, window_start=FULL_HISTORY)
    restage(db, raw_root, tmp_path, monkeypatch, name="nm_wcproduction_300_amended.xml", at=DAY_ONE)
    before = ledger_fingerprint(db)

    with pytest.raises(VintageAlreadyPromoted) as refused:
        promote(db, window_start=FULL_HISTORY)
    db.rollback()

    after = ledger_fingerprint(db)

    assert AMENDED_KEY in str(refused.value)
    assert "re-run on a day after the newest report_vintage" in str(refused.value)
    assert refused.value.report_vintage == DAY_ONE.date()
    # Nothing moved here because every month before the diverging one recomputed what was
    # already recorded. A month that had something to append would have kept it - see
    # test_a_refusal_on_a_later_month_keeps_what_an_earlier_one_committed.
    for measure in ("canonical_rows", "canonical_volume", "quarantine_rows", "rows_appended"):
        assert after[measure] == before[measure], measure


def test_a_refusal_on_a_later_month_keeps_what_an_earlier_one_committed(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
) -> None:
    """Months commit one at a time, so a refusal is not a run-level withdrawal: the months
    before the diverging one keep what they appended. What the ledger may not do is understate
    it - `rows_appended` at a vintage is what canonical holds at that vintage."""
    early = spine_record(prod_amt="100")
    late = spine_record(api_well_idn="1030", prodn_mth="3", prod_amt="200")
    stage(db, raw_root, tmp_path, monkeypatch, at=DAY_ONE,
          document=synthetic_document([early, late]))
    promote(db)
    added = spine_record(api_well_idn="1032", prod_amt="300")
    diverged = spine_record(api_well_idn="1030", prodn_mth="3", prod_amt="999",
                            mod_dte="2026-08-19T00:00:00.000")
    stage(db, raw_root, tmp_path, monkeypatch, at=DAY_ONE,
          document=synthetic_document([early, added, diverged]))
    before = ledger_fingerprint(db)

    with pytest.raises(VintageAlreadyPromoted, match="3000501030"):
        promote(db)
    db.rollback()

    after = ledger_fingerprint(db)

    assert before["canonical_rows"] == 2
    assert after["canonical_rows"] == 3
    assert scalar(
        db,
        "select count(*) from canonical.production_monthly where entity_key = %s",
        "3000501032:8559",
    ) == 1
    assert after["rows_appended"] == after["canonical_rows"]


def test_a_same_day_widening_accumulates_the_vintage_counters(db, staged_day_one) -> None:
    """DIR-12's widening performed on the day of the first promotion: exit 0, refusing nothing,
    because widening only adds months. `open_vintage` upserts on (source, day), so the counters
    have to be the vintage-day's rather than the last run's."""
    first = promote(db)

    widened = promote(db, window_start=FULL_HISTORY)

    landed = scalar(
        db,
        "select count(*) from canonical.production_monthly"
        " where source_id = %s and report_vintage = %s",
        SPINE_SOURCE,
        DAY_ONE.date(),
    )

    assert first.promoted_rows == IN_WINDOW_ROWS
    assert widened.promoted_rows == FIXTURE_ROWS - IN_WINDOW_ROWS
    assert landed == FIXTURE_ROWS
    # sum(rows_appended) at the vintage is what canonical holds at it, not the second run's 271.
    assert query(
        db,
        "select rows_examined, sum(rows_appended)::int, array_length(months_touched, 1)"
        " from lineage.vintages where source_id = %s and vintage_date = %s"
        " group by rows_examined, months_touched",
        SPINE_SOURCE,
        DAY_ONE.date(),
    ) == [(IN_WINDOW_ROWS + FIXTURE_ROWS, landed, 27)]


def test_a_vintage_may_not_withdraw_a_row_it_already_published(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
) -> None:
    """The other half of the same rule. A re-run under changed rules that leaves a published
    row uncomputed is rewriting the vintage by omission."""
    stage(
        db, raw_root, tmp_path, monkeypatch, at=DAY_ONE,
        document=synthetic_document([spine_record(prod_amt="100")]),
    )
    promote(db)
    stage(
        db, raw_root, tmp_path, monkeypatch, at=DAY_ONE,
        document=synthetic_document(
            [
                spine_record(prod_amt="100", ogrid_cde="111111"),
                spine_record(prod_amt="900", ogrid_cde="222222"),
            ]
        ),
    )
    before = ledger_fingerprint(db)

    with pytest.raises(VintageAlreadyPromoted, match="computed nothing"):
        promote(db)
    db.rollback()

    after = ledger_fingerprint(db)

    for measure in ("canonical_rows", "canonical_volume", "quarantine_rows", "rows_appended"):
        assert after[measure] == before[measure], measure


@pytest.mark.parametrize("mod_dte_shortcut", [True, False])
def test_the_mod_dte_shortcut_lands_exactly_what_the_full_comparison_lands(
    db, staged_day_one, raw_root, tmp_path, monkeypatch, mod_dte_shortcut: bool
) -> None:
    """M10. The shortcut is an optimisation, so the two paths are asserted against the same
    block: it reads 1 of 300 rows instead of 300, and what lands is identical either way."""
    promote(db, window_start=FULL_HISTORY)
    restage(db, raw_root, tmp_path, monkeypatch, name="nm_wcproduction_300_amended.xml", at=DAY_TWO)

    second = promote(
        db, at=DAY_TWO, window_start=FULL_HISTORY, mod_dte_shortcut=mod_dte_shortcut
    )

    assert second.promoted_rows == 1
    assert second.restatement_summary == {AMENDED_MONTH.isoformat(): 1}
    assert gas_rows(db)[-1][:2] == (DAY_TWO.date(), AMENDED_VOLUME)
    assert scalar(db, "select count(*) from canonical.production_monthly where source_id = %s",
                  SPINE_SOURCE) == FIXTURE_ROWS + 1
    assert second.staged_rows == FIXTURE_ROWS
    assert second.skipped_unchanged_mod_dte == (FIXTURE_ROWS - 1 if mod_dte_shortcut else 0)
    assert second.suppressed_unchanged == (0 if mod_dte_shortcut else FIXTURE_ROWS - 1)


def test_the_shortcut_falls_back_when_there_is_no_prior_partition(db, staged_day_one) -> None:
    """First run, and the state SB-01 §3.2's 30-day staging truncation leaves behind: the
    comparison it would have skipped is the comparison it does."""
    report = promote(db, window_start=FULL_HISTORY, mod_dte_shortcut=True)

    assert report.skipped_unchanged_mod_dte == 0
    assert report.promoted_rows == FIXTURE_ROWS


def test_the_shortcut_never_splits_a_two_row_key(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
) -> None:
    """A key whose two filings were split between skipped and kept would promote one of two
    answers the full comparison refuses, so the skip is decided per key and not per row."""
    pair = [
        spine_record(prod_amt="100", ogrid_cde="111111", mod_dte="2015-04-07T07:37:04.160"),
        spine_record(prod_amt="900", ogrid_cde="222222", mod_dte="2015-04-07T07:37:04.160"),
    ]
    stage(db, raw_root, tmp_path, monkeypatch, at=DAY_ONE, document=synthetic_document(pair))
    promote(db)
    moved = spine_record(prod_amt="900", ogrid_cde="222222", mod_dte="2026-08-19T00:00:00.000")
    touched = [pair[0], moved]
    stage(db, raw_root, tmp_path, monkeypatch, at=DAY_TWO, document=synthetic_document(touched))

    report = promote(db, at=DAY_TWO)

    assert report.skipped_unchanged_mod_dte == 0
    assert report.staged_rows == 2
    assert dict(report.quarantined) == {"key_collision": 2}
    assert scalar(db, "select count(*) from canonical.production_monthly where source_id = %s",
                  SPINE_SOURCE) == 0
