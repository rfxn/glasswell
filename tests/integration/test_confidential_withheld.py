"""D2 / A5-F7: a withheld month is withheld, not out of range, and not a silent gap.

ND publishes a confidential well's month with the literal string NULL in Oil/Wtr/Gas/Days and
Pool = CONFIDENTIAL. `between(days, 0, 31)` cannot judge a row with no days, so the row fell
out under `out_of_range_date` — a reason code asserting a value exists and is wrong, for a
value the regulator withheld. 1,055 well-months on the VM.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import psycopg
from psycopg.types.json import Jsonb

from glasswell.seed import seed_all
from tests.integration.test_migration_014 import migration_sql
from tests.integration.test_nd_mpr_promote import promoted, query, scalar  # noqa: F401
from tests.support.seed import seed_manifest, seed_production, seed_well

CONFIDENTIAL_ROWS = 5
CONFIDENTIAL_RULE = "cr_nd_confidential_1"
DAYS_RULE = "cr_nd_days_range_1"
WITHHELD_API10 = "3310506452"


def test_a_withheld_month_is_labelled_withheld(db, promoted):  # noqa: F811
    reasons = dict(
        query(db, "select reason_code, count(*) from lineage.quarantine_rows group by 1")
    )

    assert reasons.get("confidential_withheld") == CONFIDENTIAL_ROWS
    assert "out_of_range_date" not in reasons


def test_the_withheld_rows_cite_the_rule_that_recognised_them(db, promoted):  # noqa: F811
    cited = query(
        db,
        "select distinct rule_id, row_payload ->> 'pool' from lineage.quarantine_rows"
        " where reason_code = 'confidential_withheld'",
    )

    assert cited == [(CONFIDENTIAL_RULE, "CONFIDENTIAL")]


def test_the_days_rule_still_judges_a_row_that_has_days(db, promoted):  # noqa: F811
    """The range rule is not removed — it is no longer asked to judge an absence."""
    with db.cursor() as cursor:
        cursor.execute(
            "select spec -> 'predicate_ast' from lineage.conformance_rules where rule_id = %s",
            (DAYS_RULE,),
        )
        predicate = cursor.fetchone()[0]

    assert predicate == {"between": [{"col": "days"}, {"lit": 0}, {"lit": 31}]}


def test_a_withheld_month_stays_on_the_axis_of_a_well_that_reports(
    db,
    promoted,  # noqa: F811
    api_client,
):
    """The OpenAPI promise: a withheld value is never collapsed into a gap."""
    manifest, derivation = query(
        db, "select source_manifest_id, derivation_id from canonical.production_monthly limit 1"
    )[0]
    seed_well(db, api10=WITHHELD_API10)
    seed_production(
        db,
        api10=WITHHELD_API10,
        production_month=date(2026, 2, 1),
        report_vintage=date(2026, 8, 1),
        volume=Decimal("120.000"),
        manifest_id=manifest,
        derivation_id=derivation,
    )

    body = api_client.get(f"/v1/wells/{WITHHELD_API10}/production").json()

    assert body["data"]["series"]["pm"] == ["2026-02", "2026-03"]
    assert body["data"]["series"]["oil_bbl"] == ["120.000", None]
    assert body["data"]["series"]["oil_bbl_null_semantics"] == ["reported", "withheld"]
    withheld = [w for w in body["meta"]["warnings"] if w["code"] == "months_withheld"]
    assert withheld, "the response gives no reason for the month it cannot serve"
    assert CONFIDENTIAL_RULE in withheld[0]["detail"]


def test_a_well_with_nothing_withheld_says_nothing(db, promoted, api_client):  # noqa: F811
    api10 = scalar(db, "select api10 from canonical.production_monthly limit 1")
    seed_well(db, api10=api10)

    warnings = api_client.get(f"/v1/wells/{api10}/production").json()["meta"]["warnings"]

    assert [w for w in warnings if w["code"] == "months_withheld"] == []


def test_the_migration_relabels_what_the_payload_proves(db: psycopg.Connection) -> None:
    """The VM's 1,055 rows, bounded by pool and by the absent day count."""
    seed_all(db)
    manifest = seed_manifest(db, sha256="d" * 64, source_key="2025_10.xlsx")
    payloads = [
        ("qtn_conf_1", {"api10": "3305310469", "pool": "CONFIDENTIAL", "days": None,
                        "production_month": "2025-10-01"}),
        ("qtn_range_1", {"api10": "3305310470", "pool": "BAKKEN", "days": "44",
                         "production_month": "2025-10-01"}),
    ]
    with db.cursor() as cursor:
        for quarantine_id, payload in payloads:
            cursor.execute(
                "insert into lineage.quarantine_rows (quarantine_id, row_fingerprint, source_id,"
                " staging_table, stage, reason_code, rule_id, row_payload, first_seen_at,"
                " first_seen_manifest_id, last_seen_at, last_seen_manifest_id)"
                " values (%s, %s, 'nd_mpr_xlsx', 'staging.nd_mpr_oil', 'validate',"
                " 'out_of_range_date', %s, %s, now(), %s, now(), %s)",
                (quarantine_id, quarantine_id, DAYS_RULE, Jsonb(payload), manifest, manifest),
            )
        cursor.execute(migration_sql("confidential_withheld"))
        cursor.execute(
            "select quarantine_id, reason_code, rule_id from lineage.quarantine_rows"
            " order by quarantine_id"
        )
        relabelled = cursor.fetchall()
        cursor.execute(
            "select payload from lineage.audit_events"
            " where event_id = 'evt_migration_018_cr_nd_confidential_1'"
        )
        event = cursor.fetchone()

    assert relabelled == [
        ("qtn_conf_1", "confidential_withheld", CONFIDENTIAL_RULE),
        ("qtn_range_1", "out_of_range_date", DAYS_RULE),
    ]
    assert event is not None
    assert event[0]["rows"] == 1
    assert event[0]["finding"] == "fp-audit D2"
