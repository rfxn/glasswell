"""The C-115B capture end to end: paginated fetch, raw preservation, staging, quarantine.

Everything runs off the fixture extract through the FakeC115B double — never the live service
(SB-01 §1.2.1 politeness; the full pull belongs to the deployed timer).
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from glasswell.ingest.arcgis import PageWalkIncomplete
from glasswell.ingest.nm_c115b import SOURCE_ID, STAGING_TABLE, WALK_ORDER, load
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.seed import seed_all
from tests.integration.test_marts_nd import rows, scalar
from tests.support.c115b_fake import SERVICE_URL, FakeC115B

FIXTURE_ROWS = 6


@pytest.fixture
def seeded(db):
    seed_all(db)
    db.commit()
    return db


def run(db, raw_root, lineage_env, *, fake: FakeC115B | None = None, restage: bool = False):
    fake = fake or FakeC115B()
    with lineage_session(
        recorder=PostgresRecorder(db), environment=lineage_env
    ), fake.client() as client:
        result = load(
            db,
            service_url=SERVICE_URL,
            raw_root=raw_root,
            client=client,
            page_size=2,
            page_delay_seconds=0.0,
            restage=restage,
        )
    db.commit()
    return result, fake


def test_the_capture_stages_every_row_with_full_lineage(seeded, raw_root, lineage_env):
    result, _ = run(seeded, raw_root, lineage_env)
    assert result.staged_rows == FIXTURE_ROWS
    assert all(count == 0 for count in result.quarantined.values())
    assert scalar(seeded, f"select count(*) from {STAGING_TABLE}") == FIXTURE_ROWS

    # Source-faithful: the dashed id is what the service shipped and staging keeps it.
    assert scalar(
        seeded, f"select count(*) from {STAGING_TABLE} where id like '__-___-_____'"
    ) == FIXTURE_ROWS
    assert scalar(seeded, f"select distinct ST_SRID(geom) from {STAGING_TABLE}") == 4326
    assert set(result.months) == {"202507", "202508", "202604", "202605"}

    operation, output_dataset = rows(
        seeded,
        "select operation, output_dataset from lineage.derivations where derivation_id = %s",
        (result.parse_derivation_id,),
    )[0]
    assert operation == "stage.parse"
    assert output_dataset == STAGING_TABLE
    assert result.manifest_id in {
        ref
        for (ref,) in rows(
            seeded,
            "select ref_id from lineage.derivation_inputs where derivation_id = %s",
            (result.parse_derivation_id,),
        )
    }


def test_the_walk_is_ordered_by_the_stable_key_and_never_the_object_id(
    seeded, raw_root, lineage_env
):
    """The layer assigns OBJECTID per query, so an OID-ordered offset walk re-reads rows while
    every count still reconciles. The order is a conformance row and the fetch must send it."""
    result, fake = run(seeded, raw_root, lineage_env)
    pages = [request for request in fake.requests if "resultOffset" in request.url.params]
    assert pages, "the walk issued no paged query"
    assert {request.url.params["orderByFields"] for request in pages} == {WALK_ORDER}
    assert scalar(
        seeded,
        "select acquisition_params ->> 'order_by' from lineage.manifests"
        " where manifest_id = %s",
        (result.manifest_id,),
    ) == WALK_ORDER


def test_the_manifest_records_the_h11_acquisition_shape(seeded, raw_root, lineage_env):
    result, _ = run(seeded, raw_root, lineage_env)
    method, media_type, params, upstream_mtime = rows(
        seeded,
        "select acquisition_method, media_type, acquisition_params, upstream_mtime"
        " from lineage.manifests where manifest_id = %s",
        (result.manifest_id,),
    )[0]
    assert method == "arcgis_rest_paginate"
    assert media_type == "application/x-ndjson"
    assert params["count_before"] == params["count_after"] == params["features_written"]
    assert params["out_sr"] == 4269
    assert params["layer_id"] == 0
    # A service publishes no vintage: self-stamped under v0.6 §4E.2.
    assert upstream_mtime is None


def test_the_preserved_artifact_is_sealed_and_verifies_from_its_own_directory(
    seeded, raw_root, lineage_env
):
    """Preservation is the whole point of the track: the bytes outlive the rolling window."""
    result, _ = run(seeded, raw_root, lineage_env)
    payload = Path(
        scalar(
            seeded,
            "select storage_uri from lineage.manifests where manifest_id = %s",
            (result.manifest_id,),
        )
    )
    assert payload.exists()
    assert (payload.parent / "manifest.json").exists()
    assert (payload.parent / "MANIFEST.sha256").exists()
    assert stat.S_IMODE(payload.stat().st_mode) == 0o444


def test_refetching_identical_bytes_is_a_recorded_noop(seeded, raw_root, lineage_env):
    first, _ = run(seeded, raw_root, lineage_env)
    second, _ = run(seeded, raw_root, lineage_env)
    assert second.unchanged
    assert second.manifest_id == first.manifest_id
    assert second.staged_rows == 0
    assert second.parse_derivation_id == first.parse_derivation_id
    assert second.months == first.months
    assert scalar(
        seeded, "select count(*) from lineage.manifests where source_id = %s", (SOURCE_ID,)
    ) == 1
    assert scalar(seeded, f"select count(*) from {STAGING_TABLE}") == FIXTURE_ROWS


def test_a_month_that_rolls_out_of_the_window_survives_in_staging(
    seeded, raw_root, lineage_env
):
    """The reason this track exists. The second pull no longer carries the oldest month; the
    first pull's rows for it are still there, under their own manifest."""

    class RolledForward(FakeC115B):
        def features(self):
            return [
                feature
                for feature in super().features()
                if feature["properties"]["reporting_period"] != 202507
            ]

    first, _ = run(seeded, raw_root, lineage_env)
    second, _ = run(seeded, raw_root, lineage_env, fake=RolledForward())

    assert "202507" in first.months
    assert "202507" not in second.months
    assert second.manifest_id != first.manifest_id
    assert scalar(
        seeded,
        f"select count(*) from {STAGING_TABLE} where reporting_period = '202507'",
    ) == 1
    assert scalar(
        seeded,
        f"select manifest_id from {STAGING_TABLE} where reporting_period = '202507'",
    ) == first.manifest_id
    assert set(rows(seeded, f"select distinct manifest_id from {STAGING_TABLE}")) == {
        (first.manifest_id,),
        (second.manifest_id,),
    }


class MalformedC115B(FakeC115B):
    """One row per declared reason code, each a real feature with one property spoiled."""

    OVERRIDES = (
        {"id": "not-an-api"},
        {"waste_type": "X"},
        {"reporting_period": 202613},
        {"volume": -4},
    )

    def features(self):
        template = super().features()[0]
        return [
            {**template, "properties": {**template["properties"], **override}}
            for override in self.OVERRIDES
        ]


def test_a_malformed_row_is_quarantined_with_its_reason_and_never_dropped(
    seeded, raw_root, lineage_env
):
    result, _ = run(seeded, raw_root, lineage_env, fake=MalformedC115B())
    assert result.staged_rows == len(MalformedC115B.OVERRIDES)
    assert result.quarantined["key_incomplete"] == 1
    assert result.quarantined["unknown_vocab"] == 1
    assert result.quarantined["out_of_range_date"] == 1
    assert result.quarantined["unreliable_numeric"] == 1

    held = dict(
        rows(
            seeded,
            "select reason_code, count(*) from lineage.quarantine_rows"
            " where source_id = %s group by reason_code",
            (SOURCE_ID,),
        )
    )
    assert held == {
        "key_incomplete": 1,
        "unknown_vocab": 1,
        "out_of_range_date": 1,
        "unreliable_numeric": 1,
    }
    assert set(
        rows(
            seeded,
            "select distinct staging_table, stage from lineage.quarantine_rows"
            " where source_id = %s",
            (SOURCE_ID,),
        )
    ) == {(STAGING_TABLE, "parse")}
    # Held is not dropped: every rejected row is in staging too, verbatim.
    assert scalar(seeded, f"select count(*) from {STAGING_TABLE}") == len(
        MalformedC115B.OVERRIDES
    )
    assert scalar(
        seeded, f"select count(*) from {STAGING_TABLE} where id = 'not-an-api'"
    ) == 1
    # The reject cites the rule that refused it, so /explain resolves the decision.
    assert scalar(
        seeded,
        "select rule_id from lineage.quarantine_rows"
        " where source_id = %s and reason_code = 'key_incomplete'",
        (SOURCE_ID,),
    ) == "cr_nm_c115b_api10_1"


def test_a_repeated_identity_key_inside_one_harvest_is_held_as_a_duplicate(
    seeded, raw_root, lineage_env
):
    """The walk-order tripwire. If the paginator ever re-reads a row, this is what says so."""

    class DoubledC115B(FakeC115B):
        def features(self):
            first = super().features()[0]
            return [first, first]

    result, _ = run(seeded, raw_root, lineage_env, fake=DoubledC115B())
    assert result.staged_rows == 2
    assert result.quarantined["duplicate_row"] == 1
    assert scalar(
        seeded,
        "select rule_id from lineage.quarantine_rows"
        " where source_id = %s and reason_code = 'duplicate_row'",
        (SOURCE_ID,),
    ) == "cr_nm_c115b_walk_order_1"


def test_a_partial_walk_writes_no_manifest_and_says_why(seeded, raw_root, lineage_env):
    with pytest.raises(PageWalkIncomplete):
        run(seeded, raw_root, lineage_env, fake=FakeC115B(count_override=99))
    seeded.commit()
    assert scalar(
        seeded, "select count(*) from lineage.manifests where source_id = %s", (SOURCE_ID,)
    ) == 0
    assert scalar(seeded, f"select count(*) from {STAGING_TABLE}") == 0
    assert "page_walk_incomplete" in [
        payload["reason"]
        for (payload,) in rows(
            seeded,
            "select payload from lineage.audit_events where event_type = 'raw.fetch_failed'",
        )
    ]


def test_the_capture_writes_staging_only(seeded, raw_root, lineage_env):
    """Layer boundary: parsers write staging only, and this track has no canonical terminus."""
    run(seeded, raw_root, lineage_env)
    written = {
        table
        for (table,) in rows(
            seeded,
            "select distinct output_dataset from lineage.derivations"
            " where output_dataset is not null and left(output_dataset, 4) <> 'raw.'",
        )
    }
    assert written == {STAGING_TABLE}


def test_the_vintage_day_records_the_months_this_pull_actually_held(
    seeded, raw_root, lineage_env
):
    result, _ = run(seeded, raw_root, lineage_env)
    months, examined, appended, manifests = rows(
        seeded,
        "select months_touched, rows_examined, rows_appended, manifest_ids"
        " from lineage.vintages where source_id = %s",
        (SOURCE_ID,),
    )[0]
    assert set(months) == set(result.months)
    assert examined == appended == FIXTURE_ROWS
    assert manifests == [result.manifest_id]


def test_restaging_reparses_the_preserved_bytes_without_refetching(
    seeded, raw_root, lineage_env
):
    first, _ = run(seeded, raw_root, lineage_env)
    again, _ = run(seeded, raw_root, lineage_env, restage=True)
    assert again.unchanged is False
    assert again.manifest_id == first.manifest_id
    assert again.staged_rows == FIXTURE_ROWS
    assert scalar(seeded, f"select count(*) from {STAGING_TABLE}") == FIXTURE_ROWS
