from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from glasswell.ingest import nd_mpr
from glasswell.ingest.base import open_ingest_run
from glasswell.lineage.explain import resolve_chain
from glasswell.seed import seed_all

FIXTURES = Path(__file__).parents[1] / "fixtures" / "nd_mpr"
TRUNCATED = FIXTURES / "2026_03_truncated.xlsx"
YEAR, MONTH = 2026, 3
DATA_ROWS = 200
CLEAN_ROWS = 195
PROMOTED_STREAMS = 3
NOT_PROMOTED_REASON = "stream_not_promoted"


def client_for(path: Path) -> httpx.Client:
    payload = path.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload,
            headers={
                "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "etag": '"050923fa3e3dc1:0"',
                "last-modified": "Thu, 14 May 2026 13:12:00 GMT",
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def ingest(db, raw_root: Path, lineage_env, fixture: Path = TRUNCATED) -> nd_mpr.IngestReport:
    with open_ingest_run(
        db, source_id=nd_mpr.SOURCE_ID, raw_root=raw_root, environment=lineage_env
    ) as run, client_for(fixture) as client:
        report = nd_mpr.ingest_month(run, year=YEAR, month=MONTH, client=client)
    db.commit()
    return report


@pytest.fixture
def promoted(db, raw_root, lineage_env) -> nd_mpr.IngestReport:
    seed_all(db)
    db.commit()
    return ingest(db, raw_root, lineage_env)


def query(db, sql: str, *parameters: object) -> list[tuple]:
    with db.cursor() as cursor:
        cursor.execute(sql, parameters or None)
        return cursor.fetchall()


def scalar(db, sql: str, *parameters: object):
    return query(db, sql, *parameters)[0][0]


def test_one_artifact_produces_one_manifest_and_one_derivation_per_stage(db, promoted):
    assert scalar(db, "select count(*) from lineage.manifests") == 1
    assert query(
        db, "select operation, count(*) from lineage.derivations group by operation order by 1"
    ) == [("canonical.promote", 1), ("raw.fetch", 1), ("stage.parse", 1)]


def test_staging_is_source_faithful_with_dense_one_based_ordinals(db, promoted):
    assert scalar(db, "select count(*) from staging.nd_mpr_oil") == DATA_ROWS
    assert scalar(db, "select count(*) from staging.nd_mpr_oil where manifest_id is null") == 0
    assert query(
        db,
        "select min(source_row_ordinal), max(source_row_ordinal),"
        " count(distinct source_row_ordinal) from staging.nd_mpr_oil",
    ) == [(1, DATA_ROWS, DATA_ROWS)]
    assert scalar(
        db, "select oil from staging.nd_mpr_oil where source_row_ordinal = 1"
    ) == "304"


def test_only_the_three_canonical_streams_are_promoted(db, promoted):
    assert query(
        db, "select stream, count(*) from canonical.production_monthly group by stream order by 1"
    ) == [("gas", CLEAN_ROWS), ("oil", CLEAN_ROWS), ("water", CLEAN_ROWS)]
    assert promoted.rows_appended == CLEAN_ROWS * PROMOTED_STREAMS


def test_gas_sold_and_flared_produce_no_canonical_row_and_quarantine_with_a_reason(db, promoted):
    """C7 measured, not asserted: the dispositions are recorded as rejects, not invented."""
    assert (
        scalar(
            db,
            "select count(*) from lineage.quarantine_rows where rule_id = %s",
            "cr_nd_stream_vocab_1",
        )
        == CLEAN_ROWS * 2
    )
    assert scalar(db, "select count(*) from canonical.production_monthly") == CLEAN_ROWS * 3


def test_a_stream_that_is_not_promoted_carries_its_own_reason_code(db, promoted):
    """M-3: GasSold and Flared are the opposite of unknown — cr_nd_stream_vocab_1 enumerates
    them. Migration 011 admits the code the rule names, so the ledger stops reading as
    "the ingest does not understand its own source file"."""
    assert (
        scalar(
            db,
            "select distinct reason_code from lineage.quarantine_rows where rule_id = %s",
            "cr_nd_stream_vocab_1",
        )
        == NOT_PROMOTED_REASON
    )


def test_the_quarantine_share_is_above_zero_and_every_row_carries_a_reason(db, promoted):
    reasons = dict(
        query(
            db,
            "select reason_code, count(*) from lineage.quarantine_rows group by reason_code"
            " order by 1",
        )
    )

    assert reasons == {"confidential_withheld": 5, NOT_PROMOTED_REASON: CLEAN_ROWS * 2}
    assert promoted.quarantined == reasons
    assert scalar(db, "select count(*) from lineage.quarantine_rows where rule_id is null") == 0


def test_every_canonical_row_carries_the_manifest_fetch_vintage(db, promoted):
    fetch_vintage = scalar(db, "select fetch_vintage from lineage.manifests")

    assert promoted.report_vintage == fetch_vintage
    assert (
        scalar(
            db,
            "select count(*) from canonical.production_monthly where report_vintage <> %s",
            fetch_vintage,
        )
        == 0
    )


def test_the_promotion_cites_the_conformance_rules_it_applied(db, promoted):
    cited = [
        row[0]
        for row in query(
            db,
            "select rule_id from lineage.derivation_rules where derivation_id = %s order by 1",
            promoted.promote_derivation_id,
        )
    ]

    assert "cr_nd_stream_vocab_1" in cited
    assert "cr_nd_units_1" in cited
    assert len(cited) >= 1


def test_the_promotion_opens_a_vintage_row_that_counts_what_it_appended(db, promoted):
    rows = query(
        db,
        "select source_id, vintage_date, rows_examined, rows_appended, months_touched,"
        " promotion_derivation_id from lineage.vintages",
    )

    assert len(rows) == 1
    source_id, vintage_date, examined, appended, months, derivation = rows[0]
    assert (source_id, vintage_date) == (nd_mpr.SOURCE_ID, promoted.report_vintage)
    assert appended == CLEAN_ROWS * PROMOTED_STREAMS
    assert examined >= appended
    assert months == ["2026-03-01"]
    assert derivation == promoted.promote_derivation_id


def test_the_promotion_records_the_liquids_basis_the_policy_rule_declares(db, promoted):
    payload = scalar(
        db,
        "select payload from lineage.audit_events where event_type = %s",
        "canonical.promotion_completed",
    )

    assert payload["liquids_basis"] == nd_mpr.liquids_basis()


def test_re_ingesting_the_identical_artifact_is_a_no_op(db, raw_root, lineage_env, promoted):
    second = ingest(db, raw_root, lineage_env)

    assert second.unchanged is True
    assert second.rows_appended == 0
    assert scalar(db, "select count(*) from lineage.manifests") == 1
    assert scalar(db, "select count(*) from canonical.production_monthly") == CLEAN_ROWS * 3
    assert scalar(db, "select count(*) from lineage.derivations") == 3
    assert (
        scalar(
            db,
            "select count(*) from lineage.audit_events where event_type = %s",
            "raw.fetch_verified_unchanged",
        )
        == 1
    )


def test_a_served_production_number_resolves_back_to_the_verified_bytes(db, promoted):
    """SB-07 §10 check 3, on the one path that matters: figure → manifest → sha256 on disk."""
    derivation_id, api10 = query(
        db,
        "select derivation_id, api10 from canonical.production_monthly"
        " where stream = %s order by api10 limit 1",
        "oil",
    )[0]

    chain = resolve_chain(db, derivation_id, depth="full")
    manifest_nodes = [node for node in chain.nodes if node.type == "manifest"]

    terminals = set(chain.terminals)
    assert chain.root == derivation_id
    assert terminals
    assert all(node.type == "manifest" for node in chain.nodes if node.id in terminals)
    assert len(manifest_nodes) == 1
    storage_uri = scalar(
        db, "select storage_uri from lineage.manifests where manifest_id = %s", chain.terminals[0]
    )
    on_disk = hashlib.sha256(Path(storage_uri).read_bytes()).hexdigest()

    assert on_disk == manifest_nodes[0].attributes["sha256"]
    assert api10 == "3303300190"


def test_a_rule_the_parse_did_not_apply_stamps_no_rows(db, promoted):
    """D4: cr_nd_land_unit_1's executor checks column names; MPR staging has no land unit."""
    stamped = dict(
        query(
            db,
            "select r.rule_id, r.applied_rows from lineage.derivation_rules r"
            "  join lineage.derivations d on d.derivation_id = r.derivation_id"
            " where d.operation = 'stage.parse'",
        )
    )

    assert stamped["cr_nd_land_unit_1"] == 0
    assert stamped["cr_nd_api_identity_1"] == DATA_ROWS
    assert stamped["cr_nd_month_convention_1"] == DATA_ROWS


def test_the_promote_stage_stamps_what_each_rule_judged(db, promoted):
    stamped = dict(
        query(
            db,
            "select r.rule_id, r.applied_rows from lineage.derivation_rules r"
            "  join lineage.derivations d on d.derivation_id = r.derivation_id"
            " where d.operation = 'canonical.promote'",
        )
    )

    # The validate stage sees one row per source row; the conform stage sees one per stream.
    assert stamped["cr_nd_confidential_1"] == DATA_ROWS
    assert stamped["cr_nd_days_range_1"] == CLEAN_ROWS
    assert stamped["cr_nd_stream_vocab_1"] == CLEAN_ROWS * 5
