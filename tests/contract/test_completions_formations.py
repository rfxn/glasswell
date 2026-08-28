"""Completion context and formation reference surfaces stay source-faithful."""

from __future__ import annotations

import base64
from datetime import UTC, date, datetime, timedelta

import psycopg
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10
from glasswell.lineage.ids import new_ulid, parse_handle
from tests.support.seed import seed_well, seed_well_spatial


def test_completion_context_keeps_events_and_pool_assignments_independent(
    client: TestClient,
) -> None:
    response = client.get(f"/v1/wells/{EXAMPLE_API10}/completions")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data"]["design_availability"] == "not_promoted"
    assert body["data"]["events"] == [
        {
            "event_id": "ff-contract-0001",
            "event_kind": "hydraulic_frac_job_end",
            "job_start_date": "2025-12-10",
            "completion_date": "2025-12-20",
            "source_id": "fracfocus_csv",
            "report_vintage": "2026-08-26",
            "_lineage": body["data"]["events"][0]["_lineage"],
        }
    ]
    assert body["data"]["pools"] == [
        {
            "completion_key": f"{EXAMPLE_API10}:single",
            "well_completion_pool": "single",
            "pool_reported": "BAKKEN",
            "formation": "bakken",
            "formation_group": "bakken",
            "formation_null_semantics": "mapped",
            "source_id": "nd_mpr_xlsx",
            "first_production_month": "2026-01-01",
            "last_production_month": "2026-01-01",
            "effective_from": None,
            "latest_report_vintage": "2026-08-01",
            "_lineage": body["data"]["pools"][0]["_lineage"],
        }
    ]
    assert body["meta"]["as_of"] == {"requested": "latest", "resolved": "2026-08-26"}
    assert body["links"]["formations"] == "/v1/formations"
    assert body["data"]["events"][0]["_lineage"]["completion_date"].startswith("drv_")
    assert body["data"]["pools"][0]["_lineage"]["pool_reported"].startswith("drv_")
    assert set(body["meta"]["source_freshness"]) == {"fracfocus_csv", "nd_mpr_xlsx"}


def test_completion_and_production_freshness_share_durable_poll_semantics(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    first_at = datetime.now(UTC) - timedelta(seconds=2)
    with seeded.cursor() as cursor:
        cursor.execute(
            "select distinct on (source_id) source_id, source_key, manifest_id"
            " from lineage.manifests where source_id = any(%s)"
            " order by source_id, fetched_at desc, manifest_id desc",
            (["fracfocus_csv", "nd_mpr_xlsx"],),
        )
        manifests = {row[0]: row[1:] for row in cursor.fetchall()}
        for source_id, (source_key, manifest_id) in manifests.items():
            cursor.execute(
                "insert into lineage.fetch_attempts"
                " (attempt_id, source_id, source_key, attempted_at, completed_at, outcome,"
                " manifest_id) values (%s, %s, %s, %s, %s, 'unchanged', %s)",
                (
                    f"fat_{new_ulid(first_at)}",
                    source_id,
                    source_key,
                    first_at,
                    first_at,
                    manifest_id,
                ),
            )
    seeded.commit()

    production = client.get(f"/v1/wells/{EXAMPLE_API10}/production").json()
    completions = client.get(f"/v1/wells/{EXAMPLE_API10}/completions").json()
    assert production["meta"]["source_freshness"]["nd_mpr_xlsx"]["last_outcome"] == "unchanged"
    assert production["meta"]["source_freshness"]["nd_mpr_xlsx"]["state"] == "current"
    assert {
        source_id: evidence["last_outcome"]
        for source_id, evidence in completions["meta"]["source_freshness"].items()
    } == {"fracfocus_csv": "unchanged", "nd_mpr_xlsx": "unchanged"}

    failed_at = datetime.now(UTC) - timedelta(seconds=1)
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into lineage.fetch_attempts"
            " (attempt_id, source_id, source_key, attempted_at, completed_at, outcome,"
            " failure_code, failure_detail) values"
            " (%s, 'nd_mpr_xlsx', %s, %s, %s, 'failed', 'contract_failure',"
            " 'upstream unavailable')",
            (
                f"fat_{new_ulid(failed_at)}",
                manifests["nd_mpr_xlsx"][0],
                failed_at,
                failed_at,
            ),
        )
    seeded.commit()

    production_failed = client.get(f"/v1/wells/{EXAMPLE_API10}/production").json()
    completions_failed = client.get(f"/v1/wells/{EXAMPLE_API10}/completions").json()
    for response in (production_failed, completions_failed):
        evidence = response["meta"]["source_freshness"]["nd_mpr_xlsx"]
        assert (evidence["last_outcome"], evidence["state"]) == ("failed", "stale")
    assert completions_failed["meta"]["source_freshness"]["fracfocus_csv"]["state"] == "current"


def test_completion_as_of_does_not_leak_a_later_event_or_alias(client: TestClient) -> None:
    body = client.get(
        f"/v1/wells/{EXAMPLE_API10}/completions", params={"as_of": "2026-08-01"}
    ).json()

    assert body["data"]["events"] == []
    assert body["data"]["pools"][0]["formation"] is None
    assert body["data"]["pools"][0]["formation_group"] is None
    assert body["data"]["pools"][0]["formation_null_semantics"] == "alias_unavailable"
    assert body["meta"]["as_of"] == {"requested": "2026-08-01", "resolved": "2026-08-01"}
    assert set(body["meta"]["source_freshness"]) == {"fracfocus_csv", "nd_mpr_xlsx"}
    assert body["meta"]["warnings"] == [
        {
            "code": "source_history_unavailable",
            "detail": (
                "fracfocus_csv has captured events for this well, but its first available"
                " observation is 2026-08-26, after the requested cut."
            ),
            "pointer": "/events",
        }
    ]


def test_completion_resolved_vintage_includes_derivation_availability(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    api10 = "3305300001"
    with seeded.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id from canonical.well_completion_anchors"
            " where api10 = %s limit 1",
            (EXAMPLE_API10,),
        )
        manifest_id, derivation_id = cursor.fetchone()
        cursor.execute(
            "insert into canonical.well_completion_anchors"
            " (disclosure_id, api10, completion_date, anchor_kind, source_id, report_vintage,"
            " source_manifest_id, derivation_id) values"
            " ('ff-contract-backdated', %s, '2026-07-20', 'hydraulic_frac_job_end',"
            " 'fracfocus_csv', '2026-08-01', %s, %s)",
            (api10, manifest_id, derivation_id),
        )

    body = client.get(f"/v1/wells/{api10}/completions").json()

    assert body["data"]["events"][0]["report_vintage"] == "2026-08-01"
    assert body["meta"]["as_of"] == {"requested": "latest", "resolved": "2026-08-26"}


def test_completion_alias_resolution_cannot_cross_source_namespaces(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, formation_group, confidence, effective_from, source_id,"
            " created_vintage) values"
            " ('BAKKEN', 'wrong', 'wrong', 1.000, '2026-08-26', 'nd_gis_wells', '2026-08-26')"
        )

    pool = client.get(f"/v1/wells/{EXAMPLE_API10}/completions").json()["data"]["pools"][0]

    assert pool["formation"] == "bakken"
    assert pool["formation_group"] == "bakken"


def test_a_relabelled_completion_entity_keeps_one_dataset_identity(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    with seeded.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id from canonical.well_completions"
            " where api10 = %s limit 1",
            (EXAMPLE_API10,),
        )
        manifest_id, derivation_id = cursor.fetchone()
        cursor.execute(
            "insert into canonical.well_completions"
            " (completion_key, api10, well_completion_pool, pool_reported, source_id,"
            " production_month, report_vintage, source_manifest_id, derivation_id)"
            " values (%s, %s, 'single', 'THREE FORKS', 'nd_mpr_xlsx', '2026-02-01',"
            " '2026-08-02', %s, %s)",
            (f"{EXAMPLE_API10}:single", EXAMPLE_API10, manifest_id, derivation_id),
        )

    pools = client.get(f"/v1/wells/{EXAMPLE_API10}/completions").json()["data"]["pools"]

    assert len(pools) == 1
    assert pools[0]["completion_key"] == f"{EXAMPLE_API10}:single"
    assert pools[0]["pool_reported"] == "THREE FORKS"
    assert pools[0]["formation"] == "three_forks"
    assert pools[0]["first_production_month"] == "2026-01-01"
    assert pools[0]["last_production_month"] == "2026-02-01"
    assert pools[0]["_lineage"]["pool_reported"].endswith("&pm=2026-02")


def test_completion_handles_preserve_unsafe_keys_and_effective_grain_pods(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    with seeded.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id from canonical.well_completions"
            " where api10 = %s limit 1",
            (EXAMPLE_API10,),
        )
        manifest_id, derivation_id = cursor.fetchone()
        cursor.execute(
            "insert into canonical.well_completions"
            " (completion_key, api10, well_completion_pool, pool_reported, source_id, pod_id,"
            " effective_from, report_vintage, source_manifest_id, derivation_id)"
            " values (%s, %s, 'unsafe', 'BAKKEN', 'nd_mpr_xlsx', 'POD 1/2', '2026-01-01',"
            " '2026-08-01', %s, %s)",
            (f"{EXAMPLE_API10}:RED RIVER/ALT", EXAMPLE_API10, manifest_id, derivation_id),
        )

    pools = client.get(f"/v1/wells/{EXAMPLE_API10}/completions").json()["data"]["pools"]
    unsafe = next(pool for pool in pools if pool["well_completion_pool"] == "unsafe")
    handle = unsafe["_lineage"]["effective_from"]
    parsed = parse_handle(handle)
    assert parsed.selector is not None
    selector = dict(term.split("=", 1) for term in parsed.selector.split("&"))

    assert "completion_key_b64=" in handle
    assert "pod_id_b64=" in handle
    encoded_key = selector["completion_key_b64"]
    assert base64.urlsafe_b64decode(
        encoded_key + "=" * (-len(encoded_key) % 4)
    ).decode() == f"{EXAMPLE_API10}:RED RIVER/ALT"

    valid = client.get("/v1/explain", params={"h": handle})
    missing_key = base64.urlsafe_b64encode(b"missing completion/key").decode().rstrip("=")
    missing = client.get(
        "/v1/explain", params={"h": handle.replace(encoded_key, missing_key)}
    )
    wrong_column = client.get(
        "/v1/explain", params={"h": handle.replace("col=effective_from", "col=api10")}
    )

    assert valid.status_code == 200, valid.text
    assert missing.status_code == 404
    assert missing.json()["stop_reason"] == "unknown_id"
    assert wrong_column.status_code == 422
    assert wrong_column.json()["type"] == "/v1/errors/selector_ambiguous"


def test_a_well_without_completion_context_is_explicitly_empty(client: TestClient) -> None:
    response = client.get("/v1/wells/3305300001/completions").json()
    body = response["data"]

    assert body == {
        "api10": "3305300001",
        "design_availability": "not_promoted",
        "events": [],
        "pools": [],
    }
    assert response["meta"]["as_of"] == {"requested": "latest", "resolved": "2026-08-01"}


def test_completion_latest_excludes_future_and_unvintaged_aliases(
    client: TestClient, seeded: psycopg.Connection, monkeypatch
) -> None:
    monkeypatch.setattr("glasswell.api.routers.completions.today", lambda: date(2026, 8, 26))
    with seeded.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id from canonical.well_completions"
            " where api10 = %s limit 1",
            (EXAMPLE_API10,),
        )
        manifest_id, derivation_id = cursor.fetchone()
        cursor.execute(
            "insert into canonical.well_completions"
            " (completion_key, api10, well_completion_pool, pool_reported, source_id,"
            " production_month, report_vintage, source_manifest_id, derivation_id) values"
            " (%s, %s, 'future', 'FUTURE POOL', 'nd_mpr_xlsx', '2026-01-01', '2026-08-01',"
            " %s, %s),"
            " (%s, %s, 'unvintaged', 'UNVINTAGED POOL', 'nd_mpr_xlsx', '2026-01-01',"
            " '2026-08-01', %s, %s)",
            (
                f"{EXAMPLE_API10}:future",
                EXAMPLE_API10,
                manifest_id,
                derivation_id,
                f"{EXAMPLE_API10}:unvintaged",
                EXAMPLE_API10,
                manifest_id,
                derivation_id,
            ),
        )
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, formation_group, confidence, effective_from, source_id,"
            " created_vintage) values"
            " ('FUTURE POOL', 'future_pool', '__other__', 1.000, '2026-08-27',"
            " 'nd_mpr_xlsx', '2026-08-26'),"
            " ('UNVINTAGED POOL', 'unvintaged_pool', '__other__', 1.000, '2026-08-01',"
            " 'nd_mpr_xlsx', null)"
        )

    pools = client.get(f"/v1/wells/{EXAMPLE_API10}/completions").json()["data"]["pools"]
    by_name = {pool["well_completion_pool"]: pool for pool in pools}

    assert by_name["future"]["formation_null_semantics"] == "alias_unavailable"
    assert by_name["future"]["formation"] is None
    assert by_name["unvintaged"]["formation_null_semantics"] == "alias_unavailable"
    assert by_name["unvintaged"]["formation"] is None


def test_completion_history_before_its_first_source_vintage_is_refused(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    api10 = "3305300001"
    with seeded.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id from canonical.well_completion_anchors"
            " where api10 = %s limit 1",
            (EXAMPLE_API10,),
        )
        manifest_id, derivation_id = cursor.fetchone()
        cursor.execute(
            "insert into canonical.well_completion_anchors"
            " (disclosure_id, api10, completion_date, anchor_kind, source_id, report_vintage,"
            " source_manifest_id, derivation_id) values"
            " ('ff-contract-future', %s, '2026-07-20', 'hydraulic_frac_job_end',"
            " 'fracfocus_csv', '2026-08-26', %s, %s)",
            (api10, manifest_id, derivation_id),
        )

    response = client.get(f"/v1/wells/{api10}/completions", params={"as_of": "2026-08-01"})

    assert response.status_code == 422
    assert response.json()["type"].endswith("/as_of_out_of_range")


def test_a_late_discovered_backdated_well_does_not_leak_into_history(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    api10 = "3305399998"
    with seeded.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id from canonical.well_completion_anchors"
            " where api10 = %s limit 1",
            (EXAMPLE_API10,),
        )
        manifest_id, derivation_id = cursor.fetchone()
    seed_well(
        seeded,
        api10=api10,
        effective_from=date(2020, 1, 1),
        manifest_id=manifest_id,
        derivation_id=derivation_id,
    )

    response = client.get(f"/v1/wells/{api10}/completions", params={"as_of": "2026-08-01"})

    assert response.status_code == 404


def test_a_late_discovered_geometry_does_not_leak_into_a_historical_well(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    with seeded.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id from canonical.well_completion_anchors"
            " where api10 = %s limit 1",
            (EXAMPLE_API10,),
        )
        manifest_id, derivation_id = cursor.fetchone()
    seed_well_spatial(
        seeded,
        api10=EXAMPLE_API10,
        geom_key=f"{EXAMPLE_API10}0000_LAT2",
        wkt="LINESTRING(-103.5401 47.9081, -103.5000 47.9090)",
        manifest_id=manifest_id,
        derivation_id=derivation_id,
    )

    historical_response = client.get(
        f"/v1/wells/{EXAMPLE_API10}", params={"as_of": "2026-08-01"}
    ).json()
    latest_response = client.get(f"/v1/wells/{EXAMPLE_API10}").json()
    historical = historical_response["data"]
    latest = latest_response["data"]

    assert historical["lateral_count"] == 1
    assert historical["length_method"] == "projected"
    assert len(historical["geometry"]) == 2
    assert latest["lateral_count"] == 2
    assert latest["length_method"] == "geodesic"
    assert len(latest["geometry"]) == 3
    assert historical_response["meta"]["as_of"]["resolved"] == "2026-08-01"
    assert latest_response["meta"]["as_of"]["resolved"] == "2026-08-26"
    replay = client.get(
        f"/v1/wells/{EXAMPLE_API10}", params={"as_of": "2026-08-26"}
    ).json()
    assert replay["data"] == latest


def test_held_back_geometry_release_respects_the_requested_vintage(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    with seeded.cursor() as cursor:
        cursor.execute(
            "update lineage.quarantine_rows"
            " set source_id = 'nd_gis_horizontals_line',"
            "     row_payload = jsonb_build_object('api10', %s::text, 'segment', 'LAT'),"
            "     reason_code = 'segment_not_promoted', rule_id = 'cr_nd_datum_1',"
            "     state = 'released', released_at_vintage = '2026-08-26'"
            " where source_id = 'nd_gis_wells'",
            (EXAMPLE_API10,),
        )

    historical = client.get(
        f"/v1/wells/{EXAMPLE_API10}", params={"as_of": "2026-08-01"}
    ).json()
    latest = client.get(f"/v1/wells/{EXAMPLE_API10}").json()

    assert any(
        warning["code"] == "geometry_not_promoted"
        for warning in historical["meta"]["warnings"]
    )
    assert not any(
        warning["code"] == "geometry_not_promoted"
        for warning in latest["meta"]["warnings"]
    )
    assert historical["meta"]["as_of"]["resolved"] == "2026-08-01"
    assert latest["meta"]["as_of"]["resolved"] == "2026-08-26"


def test_formations_are_current_source_scoped_reference_rows(client: TestClient) -> None:
    response = client.get("/v1/formations", params={"basin": "williston", "q": "BAKKEN"})

    assert response.status_code == 200, response.text
    rows = {row["formation"]: row for row in response.json()["data"]}
    assert rows["bakken"] == {
        "formation": "bakken",
        "formation_groups": ["bakken"],
        "basins": ["williston"],
        "alias_count": 1,
        "aliases": ["BAKKEN"],
        "source_ids": ["nd_mpr_xlsx"],
    }
    assert "bakken_three_forks" in rows


def test_formation_search_matches_reported_aliases_and_counts_distinct_labels(
    client: TestClient,
) -> None:
    response = client.get("/v1/formations", params={"basin": "williston", "q": "Dakota"})

    assert response.status_code == 200, response.text
    assert response.json()["data"] == [
        {
            "formation": "dakota",
            "formation_groups": ["__other__"],
            "basins": ["williston"],
            "alias_count": 2,
            "aliases": ["DAKOTA", "Dakota"],
            "source_ids": ["nd_mpr_xlsx"],
        }
    ]


def test_formation_history_refuses_a_cut_before_the_vintaged_registry(
    client: TestClient,
) -> None:
    response = client.get("/v1/formations", params={"as_of": "2026-08-25"})

    assert response.status_code == 422
    assert response.json()["type"].endswith("/as_of_out_of_range")


def test_formation_valid_time_is_not_collapsed_to_latest_knowledge_vintage(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, formation_group, confidence, effective_from, source_id,"
            " created_vintage) values"
            " ('VALID TOMORROW', 'valid_tomorrow', '__other__', 1.000, '2026-08-27',"
            " 'nd_mpr_xlsx', '2026-08-26')"
        )

    before = client.get("/v1/formations", params={"as_of": "2026-08-26", "q": "VALID"})
    effective = client.get("/v1/formations", params={"as_of": "2026-08-27", "q": "VALID"})

    assert before.json()["data"] == []
    assert [row["formation"] for row in effective.json()["data"]] == ["valid_tomorrow"]


def test_formation_cursor_pins_out_later_alias_vintages_during_ingest(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    first = client.get("/v1/formations", params={"limit": 1}).json()
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, formation_group, confidence, effective_from, source_id,"
            " created_vintage) values"
            " ('ZZZ NEW', 'zzz_new', '__other__', 1.000, '2026-08-27', 'nd_mpr_xlsx',"
            " '2026-08-27')"
        )

    seen = [first["data"][0]["formation"]]
    cursor = first["meta"]["next_cursor"]
    while cursor is not None:
        page = client.get("/v1/formations", params={"limit": 10, "cursor": cursor}).json()
        seen.extend(row["formation"] for row in page["data"])
        cursor = page["meta"]["next_cursor"]

    assert "zzz_new" not in seen


def test_formation_cursor_pins_valid_time_across_a_date_rollover(
    client: TestClient, seeded: psycopg.Connection, monkeypatch
) -> None:
    monkeypatch.setattr("glasswell.api.routers.formations.today", lambda: date(2026, 8, 26))
    first = client.get("/v1/formations", params={"limit": 1}).json()
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, formation_group, confidence, effective_from, source_id,"
            " created_vintage) values"
            " ('ROLLOVER POOL', 'rollover_pool', '__other__', 1.000, '2026-08-27',"
            " 'nd_mpr_xlsx', '2026-08-26')"
        )
    monkeypatch.setattr("glasswell.api.routers.formations.today", lambda: date(2026, 8, 27))

    seen = [first["data"][0]["formation"]]
    cursor = first["meta"]["next_cursor"]
    while cursor is not None:
        page = client.get("/v1/formations", params={"limit": 10, "cursor": cursor}).json()
        seen.extend(row["formation"] for row in page["data"])
        cursor = page["meta"]["next_cursor"]

    assert "rollover_pool" not in seen


def test_formation_cursor_is_bound_to_its_filter(client: TestClient) -> None:
    first = client.get("/v1/formations", params={"basin": "williston", "limit": 1}).json()
    cursor = first["meta"]["next_cursor"]

    assert cursor is not None
    mismatch = client.get(
        "/v1/formations",
        params={"basin": "williston", "q": "bakken", "limit": 1, "cursor": cursor},
    )

    assert mismatch.status_code == 422
    assert mismatch.json()["type"] == "/v1/errors/cursor_query_mismatch"
