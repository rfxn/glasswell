"""Contract-tier fixtures: a seeded database whose ids are the OpenAPI examples.

SB-07 §10's harness calls every operation with its documented example, so the fixture
has to contain exactly those entities. `glasswell.api.examples` is the single place
they are written down; everything here seeds against those constants.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from glasswell.api.accounts import (
    ConnectionSessionStore,
    create_session,
    find_user_by_id,
    new_user_id,
)
from glasswell.api.csrf import CSRF_HEADER
from glasswell.api.deps import SESSION_COOKIE, get_key_store, get_session_store
from glasswell.api.examples import (
    EXAMPLE_API10,
    EXAMPLE_DERIVATION_ID,
    EXAMPLE_MANIFEST_ID,
    EXAMPLE_PUBLICATION_ID,
    EXAMPLE_QUARANTINE_ID,
    KEY_HEADER,
)
from glasswell.api.password import hash_password
from glasswell.api.principal import ConnectionKeyStore, fingerprint, mint_secret
from glasswell.api.routers.keys import EXAMPLE_KEY_ID
from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.fetch import RAW_ROOT_ENV
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.serialization import hash_payload
from glasswell.lineage.store import PostgresRecorder
from glasswell.lineage.vintages import open_vintage
from glasswell.marts.neighbors import refresh_neighbors, resident_content_identity
from glasswell.modeling import served
from glasswell.modeling.model_dataset import MODEL_ROOT_ENV
from glasswell.seed import seed_all
from tests.support.fakes import FixedClock
from tests.support.seed import FIXTURE_ENV, seed_manifest, seed_well, seed_well_spatial
from tests.support.typecurve_fixture import (
    ControlArtifact,
    ControlSubject,
    register_pinned_control,
    write_control_artifact,
)

MPR_SHA256 = "e" * 64
GIS_SHA256 = "d" * 64
FRACFOCUS_SHA256 = "c" * 64
# The GIS promote records its compute CRS as a param, so the walker meets a numeric param.
COMPUTE_EPSG = 32614
REPORT_VINTAGE = date(2026, 8, 1)
COMPLETION_REPORT_VINTAGE = date(2026, 8, 26)
EARLIER_VINTAGE = date(2026, 7, 1)
RESTATED_MONTH = date(2026, 3, 1)
PRODUCTION_MONTHS = tuple(date(2026, month, 1) for month in range(1, 7))
OTHER_API10S = tuple(f"330530000{index}" for index in range(1, 7))
# One Texas well, so the walkers see the surfaces only TX reaches: a depth figure, a null
# status, and a production endpoint whose honest answer is "pending allocation" rather than an
# empty series. A fixture that makes those impossible is how a gate goes quietly vacuous (N-1).
TX_API10 = "4200345818"
ALL_API10S = (EXAMPLE_API10, *OTHER_API10S, TX_API10)
STREAM_UNITS = {"oil": "bbl", "gas": "mcf", "water": "bbl"}
TILE_BODY = b"\x1a\x2fcontract-fixture-tile"

_INSERT_PRODUCTION = (
    "insert into canonical.production_monthly (api10, production_month, stream, source_id,"
    " report_vintage, volume, unit, days_produced, granularity, value_hash, null_semantics,"
    " source_manifest_id, derivation_id)"
    " values (%(api10)s, %(production_month)s, %(stream)s, %(source_id)s, %(report_vintage)s,"
    " %(volume)s, %(unit)s, %(days_produced)s, %(granularity)s, %(value_hash)s,"
    " %(null_semantics)s, %(manifest_id)s, %(derivation_id)s)"
)

_INSERT_QUARANTINE = (
    "insert into lineage.quarantine_rows (quarantine_id, row_fingerprint, source_id,"
    " staging_table, stage, reason_code, rule_id, row_payload, first_seen_at,"
    " first_seen_manifest_id, last_seen_at, last_seen_manifest_id, occurrence_count, state)"
    " values (%(quarantine_id)s, %(fingerprint)s, %(source_id)s, %(staging_table)s, %(stage)s,"
    " %(reason_code)s, %(rule_id)s, %(payload)s, %(seen_at)s, %(manifest_id)s, %(seen_at)s,"
    " %(manifest_id)s, %(occurrences)s, %(state)s)"
)


def _promotion_derivation(connection: psycopg.Connection, manifest_id: str) -> str:
    recorder = PostgresRecorder(connection)
    with lineage_session(
        recorder=recorder,
        environment=FIXTURE_ENV,
        clock=FixedClock(),
        correlation_id="run_contract",
    ), derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset="canonical.production_monthly",
            partition={"source_id": "nd_mpr_xlsx", "report_vintage": REPORT_VINTAGE.isoformat()},
        ),
        params={"source_id": "nd_mpr_xlsx"},
        inputs=[
            InputRef(
                kind="manifest",
                ref_id=manifest_id,
                role="primary",
                as_of_vintage=REPORT_VINTAGE,
            )
        ],
        rules=["cr_nd_stream_vocab_1", "cr_nd_units_1"],
    ) as context:
        context.set_output_hash("a1" * 32)
        context.set_rows(len(PRODUCTION_MONTHS) * len(STREAM_UNITS))
    return context.derivation_id


def _spatial_derivation(connection: psycopg.Connection, manifest_id: str) -> str:
    recorder = PostgresRecorder(connection)
    with lineage_session(
        recorder=recorder,
        environment=FIXTURE_ENV,
        clock=FixedClock(),
        correlation_id="run_contract",
    ), derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgis",
            dataset="canonical.well_spatial",
            partition={"source_id": "nd_gis_horizontals_line"},
        ),
        params={
            "layer": "nd_gis_horizontals_line",
            "compute_epsg": COMPUTE_EPSG,
            "length_expression": None,
        },
        inputs=[
            InputRef(
                kind="manifest",
                ref_id=manifest_id,
                role="primary",
                as_of_vintage=REPORT_VINTAGE,
            )
        ],
        rules=["cr_nd_datum_1"],
    ) as context:
        context.set_output_hash("b2" * 32)
        context.set_rows(2)
    return context.derivation_id


def _well_derivation(
    connection: psycopg.Connection, manifest_id: str, *, source_id: str, output_rows: int
) -> str:
    recorder = PostgresRecorder(connection)
    with lineage_session(
        recorder=recorder,
        environment=FIXTURE_ENV,
        clock=FixedClock(),
        correlation_id=f"run_contract_{source_id}_wells",
    ), derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset="canonical.wells",
            partition={"source_id": source_id},
        ),
        params={"source_id": source_id},
        inputs=[
            InputRef(
                kind="manifest",
                ref_id=manifest_id,
                role="primary",
                as_of_vintage=REPORT_VINTAGE,
            )
        ],
    ) as context:
        context.set_output_hash(hash_payload({"source_id": source_id, "rows": output_rows}))
        context.set_rows(output_rows)
    return context.derivation_id


def _completion_derivation(connection: psycopg.Connection, manifest_id: str) -> str:
    recorder = PostgresRecorder(connection)
    with lineage_session(
        recorder=recorder,
        environment=FIXTURE_ENV,
        clock=FixedClock(datetime(2026, 8, 26, 5, 0, 0, tzinfo=UTC)),
        correlation_id="run_contract",
    ), derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset="canonical.well_completion_anchors",
            partition={"source_id": "fracfocus_csv"},
        ),
        params={"source_id": "fracfocus_csv", "event": "hydraulic_frac_job_end"},
        inputs=[
            InputRef(
                kind="manifest",
                ref_id=manifest_id,
                role="primary",
                as_of_vintage=COMPLETION_REPORT_VINTAGE,
            )
        ],
        rules=["cr_ff_completion_anchor_1"],
    ) as context:
        context.set_output_hash("c3" * 32)
        context.set_rows(1)
    return context.derivation_id


def _insert_production(
    connection: psycopg.Connection,
    *,
    api10: str,
    production_month: date,
    stream: str,
    volume: Decimal | None,
    manifest_id: str,
    derivation_id: str,
    report_vintage: date = REPORT_VINTAGE,
    null_semantics: str = "reported",
    days_produced: int | None = 30,
) -> None:
    row: dict[str, Any] = {
        "api10": api10,
        "production_month": production_month,
        "stream": stream,
        "source_id": "nd_mpr_xlsx",
        "report_vintage": report_vintage,
        "volume": volume if volume is not None else Decimal("0"),
        "unit": STREAM_UNITS[stream],
        "days_produced": days_produced,
        "granularity": "well_observed",
        "value_hash": hash_payload({"volume": str(volume), "stream": stream}),
        "null_semantics": null_semantics,
        "manifest_id": manifest_id,
        "derivation_id": derivation_id,
    }
    with connection.cursor() as cursor:
        cursor.execute(_INSERT_PRODUCTION, row)


def _seed_production(connection: psycopg.Connection, manifest_id: str, derivation_id: str) -> None:
    for ordinal, month in enumerate(PRODUCTION_MONTHS):
        for stream, factor in (("oil", 1000), ("gas", 2400), ("water", 800)):
            withheld = month == PRODUCTION_MONTHS[-1] and stream == "water"
            _insert_production(
                connection,
                api10=EXAMPLE_API10,
                production_month=month,
                stream=stream,
                volume=Decimal(factor * (ordinal + 1)),
                manifest_id=manifest_id,
                derivation_id=derivation_id,
                null_semantics="withheld" if withheld else "reported",
            )
    # The restatement DIR-2 exists for: the same month reported twice, never updated.
    _insert_production(
        connection,
        api10=EXAMPLE_API10,
        production_month=RESTATED_MONTH,
        stream="oil",
        volume=Decimal("2500"),
        manifest_id=manifest_id,
        derivation_id=derivation_id,
        report_vintage=EARLIER_VINTAGE,
    )
    for api10 in OTHER_API10S[:2]:
        _insert_production(
            connection,
            api10=api10,
            production_month=PRODUCTION_MONTHS[0],
            stream="oil",
            volume=Decimal("500"),
            manifest_id=manifest_id,
            derivation_id=derivation_id,
        )
    # An active well that filed a zero in the newest month: the case the producing filter turns
    # on, and the only one that separates a fact from an absence at this tier.
    _insert_production(
        connection,
        api10=OTHER_API10S[4],
        production_month=PRODUCTION_MONTHS[-1],
        stream="oil",
        volume=Decimal("0"),
        manifest_id=manifest_id,
        derivation_id=derivation_id,
        null_semantics="reported_zero",
    )


def _seed_completion_context(
    connection: psycopg.Connection,
    *,
    mpr_manifest_id: str,
    production_derivation_id: str,
    fracfocus_manifest_id: str,
    completion_derivation_id: str,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into canonical.well_completions"
            " (completion_key, api10, well_completion_pool, pool_reported, source_id,"
            " production_month, report_vintage, source_manifest_id, derivation_id)"
            " values (%s, %s, 'single', 'BAKKEN', 'nd_mpr_xlsx', %s, %s, %s, %s)",
            (
                f"{EXAMPLE_API10}:single",
                EXAMPLE_API10,
                PRODUCTION_MONTHS[0],
                REPORT_VINTAGE,
                mpr_manifest_id,
                production_derivation_id,
            ),
        )
        cursor.execute(
            "insert into canonical.well_completion_anchors"
            " (disclosure_id, api10, job_start_date, completion_date, anchor_kind, source_id,"
            " report_vintage, source_manifest_id, derivation_id)"
            " values ('ff-contract-0001', %s, '2025-12-10', '2025-12-20',"
            " 'hydraulic_frac_job_end', 'fracfocus_csv', %s, %s, %s)",
            (
                EXAMPLE_API10,
                COMPLETION_REPORT_VINTAGE,
                fracfocus_manifest_id,
                completion_derivation_id,
            ),
        )


def _seed_neighbor_mart(connection: psycopg.Connection) -> None:
    """Add isolated mart peers under their own content-matching fixture derivation."""
    neighbor_api10s = ("3305399998", "3305399999")
    with connection.cursor() as cursor:
        cursor.execute(
            "select api10, completion_date, formation_id, formation_group, formation_status,"
            " formation_pools, formation_month, lateral_component_count, snapshot_vintage,"
            " derivation_id from marts.nd_neighbor_subjects"
            " where api10 = %s",
            (EXAMPLE_API10,),
        )
        subject = cursor.fetchone()
    snapshot_vintage = subject[8]
    source_derivation_id = subject[9]
    output = OutputSpec(
        store="postgis",
        dataset="marts.nd_neighbors",
        partition={"state": "ND", "snapshot_vintage": snapshot_vintage.isoformat()},
        schema_version="1",
    )
    params = {
        "fixture": "contract_neighbor_rows",
        "snapshot_vintage": snapshot_vintage.isoformat(),
    }
    inputs = [
        InputRef(
            kind="derivation",
            ref_id=source_derivation_id,
            as_of_vintage=snapshot_vintage,
        )
    ]
    with lineage_session(
        recorder=PostgresRecorder(connection),
        environment=FIXTURE_ENV,
        clock=FixedClock(datetime(2026, 8, 27, 6, 5, 0, tzinfo=UTC)),
        correlation_id="run_contract_neighbor_fixture",
    ):
        with derive(
            "mart.refresh",
            output=output,
            params=params,
            inputs=inputs,
            ttl_class="ephemeral",
        ) as context:
            pass
        derivation_id = context.derivation_id
        with connection.cursor() as cursor:
            cursor.execute("delete from marts.nd_neighbor_edges")
            cursor.execute("delete from marts.nd_neighbor_subjects")
            cursor.execute(
                "insert into marts.nd_neighbor_subjects"
                " (api10, completion_date, formation_id, formation_group, formation_status,"
                " formation_pools, formation_month, lateral_component_count, snapshot_vintage,"
                " derivation_id) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (*subject[:9], derivation_id),
            )
            cursor.executemany(
                "insert into marts.nd_neighbor_subjects"
                " (api10, completion_date, formation_id, formation_group, formation_status,"
                " formation_pools, formation_month, lateral_component_count, snapshot_vintage,"
                " derivation_id) values"
                " (%s, %s, 'bakken', 'bakken', 'mapped', array['BAKKEN'],"
                " '2025-01-01', 1, %s, %s)",
                [
                    (neighbor_api10s[0], date(2025, 9, 10), snapshot_vintage, derivation_id),
                    (neighbor_api10s[1], date(2025, 10, 10), snapshot_vintage, derivation_id),
                ],
            )
            cursor.executemany(
                "insert into marts.nd_neighbor_edges"
                " (api10, neighbor_api10, distance_m, distance_epsg, subject_geom_key,"
                " neighbor_geom_key, snapshot_vintage, derivation_id)"
                " values (%s, %s, %s, 32613, %s, %s, %s, %s)",
                [
                    (
                        source_api10,
                        target_api10,
                        Decimal(distance),
                        f"{source_api10}:lateral:1",
                        f"{target_api10}:lateral:1",
                        snapshot_vintage,
                        derivation_id,
                    )
                    for neighbor_api10, distance in zip(
                        neighbor_api10s, ("800.000", "1000.000"), strict=True
                    )
                    for source_api10, target_api10 in (
                        (EXAMPLE_API10, neighbor_api10),
                        (neighbor_api10, EXAMPLE_API10),
                    )
                ],
            )
        subject_rows, subject_digest, edge_rows, edge_digest = resident_content_identity(
            connection
        )
        with derive(
            "mart.refresh",
            output=output,
            params=params,
            inputs=inputs,
            ttl_class="ephemeral",
        ) as context:
            context.set_rows(subject_rows + edge_rows)
            context.set_output_hash(
                hash_payload(
                    {
                        "subjects": {"rows": subject_rows, "sha256": subject_digest},
                        "edges": {"rows": edge_rows, "sha256": edge_digest},
                    }
                )
            )


def _seed_quarantine(connection: psycopg.Connection, manifest_id: str) -> None:
    seen_at = datetime(2026, 8, 1, 5, 2, 11, tzinfo=UTC)
    rows = [
        {
            "quarantine_id": EXAMPLE_QUARANTINE_ID,
            "fingerprint": "fp_contract_0001",
            "source_id": "nd_mpr_xlsx",
            "staging_table": "staging.nd_mpr_oil",
            "stage": "conform",
            "reason_code": "unknown_vocab",
            "rule_id": "cr_nd_stream_vocab_1",
            "payload": Jsonb({"stream_raw": "GasSold", "api_wellno": "33-053-01234"}),
            "seen_at": seen_at,
            "manifest_id": manifest_id,
            "occurrences": 3,
            "state": "open",
        },
        {
            "quarantine_id": "qr_01contract0002",
            "fingerprint": "fp_contract_0002",
            "source_id": "nd_mpr_xlsx",
            "staging_table": "staging.nd_mpr_oil",
            "stage": "validate",
            "reason_code": "impossible_volume",
            "rule_id": "cr_nd_volume_range_1",
            "payload": Jsonb({"oil": "-14"}),
            "seen_at": seen_at,
            "manifest_id": manifest_id,
            "occurrences": 1,
            "state": "open",
        },
        {
            "quarantine_id": "qr_01contract0003",
            "fingerprint": "fp_contract_0003",
            "source_id": "nd_gis_wells",
            "staging_table": "staging.nd_gis_wells",
            "stage": "conform",
            "reason_code": "unknown_vocab",
            "rule_id": "cr_nd_status_vocab_1",
            "payload": Jsonb({"status": "MYSTERY"}),
            "seen_at": seen_at,
            "manifest_id": manifest_id,
            "occurrences": 2,
            "state": "released",
        },
    ]
    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(_INSERT_QUARANTINE, row)


RAW_PAYLOAD = b"contract-fixture raw bytes, hashed as fetched"


@pytest.fixture
def raw_zone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A raw zone holding the example manifest's payload.

    Without it the published `get_manifest_bytes` example 404s, which is exactly the
    MAJOR-2(b) shape: an example that only resolves where the artifact happens to exist.
    """
    root = tmp_path / "raw"
    (root / "nd_mpr_xlsx").mkdir(parents=True)
    payload = root / "nd_mpr_xlsx" / "2026_06.xlsx"
    payload.write_bytes(RAW_PAYLOAD)
    monkeypatch.setenv(RAW_ROOT_ENV, str(root))
    return payload


CONTROL_ORIGIN = date(2021, 1, 1)
LATER_ORIGIN = date(2021, 7, 1)
# One subject per served shape: the published example at both horizons, one rung below the
# first, one basin rung under the peer floor, one control_unavailable subject, two fillers so
# a small limit pages twice, and one at a second origin so `available_origins` is not a
# singleton. A fixture that cannot produce a page 2 cannot regress B-2.
CONTROL_SUBJECTS = (
    ControlSubject(api10=EXAMPLE_API10, origin=CONTROL_ORIGIN, horizon_months=24),
    ControlSubject(api10=EXAMPLE_API10, origin=CONTROL_ORIGIN, horizon_months=12),
    ControlSubject(
        api10=OTHER_API10S[0],
        origin=CONTROL_ORIGIN,
        horizon_months=24,
        fallback_level="formation_area",
        lateral_length_bucket="lt_8000",
        lateral_length_ft=7200.0,
    ),
    ControlSubject(
        api10=OTHER_API10S[1],
        origin=CONTROL_ORIGIN,
        horizon_months=24,
        fallback_level="formation_basin",
        peer_count=12,
    ),
    ControlSubject(
        api10=OTHER_API10S[2],
        origin=CONTROL_ORIGIN,
        horizon_months=24,
        fallback_level="control_unavailable",
        lateral_length_bucket=None,
        lateral_length_ft=None,
        reasons=("missing_lateral_length",),
    ),
    ControlSubject(api10=OTHER_API10S[3], origin=CONTROL_ORIGIN, horizon_months=24),
    ControlSubject(api10=OTHER_API10S[4], origin=CONTROL_ORIGIN, horizon_months=24),
    ControlSubject(api10=OTHER_API10S[5], origin=LATER_ORIGIN, horizon_months=24),
    # The same subject held out at a second origin, at one horizon. Without it the index's
    # page boundary can never land mid-subject and the paging test cannot fail.
    ControlSubject(
        api10=OTHER_API10S[0],
        origin=LATER_ORIGIN,
        horizon_months=24,
        fallback_level="formation_area",
        lateral_length_bucket="lt_8000",
        lateral_length_ft=7200.0,
    ),
)


@pytest.fixture
def pinned_control(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ControlArtifact:
    """A registered control artifact under a model root the resolver will accept.

    `DEFAULT_MODEL_ROOT` is relative, so without this the type-curve routes are fail-closed
    and every published example would 409 instead of serving.

    The root is named relative to a per-test working directory rather than as an absolute
    path, because the receipt document carries `artifact_uri` and the publication id is a
    content address over that document: an absolute temp path would move the published
    `EXAMPLE_PUBLICATION_ID` on every run. A relative root is a shape the real builder
    produces too — `resolve_model_root()` falls back to `data/models`.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(MODEL_ROOT_ENV, "models")
    served.clear_caches()
    return write_control_artifact(Path("models"), subjects=CONTROL_SUBJECTS)


@pytest.fixture
def seeded(
    db: psycopg.Connection, raw_zone: Path, pinned_control: ControlArtifact
) -> psycopg.Connection:
    """Registries, wells, geometry, production and quarantine, keyed to the examples."""
    seed_all(db)
    mpr_manifest = seed_manifest(db, sha256=MPR_SHA256, source_key="2026_06.xlsx")
    gis_manifest = seed_manifest(
        db, sha256=GIS_SHA256, source_id="nd_gis_wells", source_key="OGD_Wells.zip"
    )
    fracfocus_manifest = seed_manifest(
        db,
        sha256=FRACFOCUS_SHA256,
        source_id="fracfocus_csv",
        source_key="registryupload.zip",
    )
    assert mpr_manifest == EXAMPLE_MANIFEST_ID, "the documented manifest example must be seeded"
    with db.cursor() as cursor:
        cursor.execute(
            "update lineage.manifests set storage_uri = %s where manifest_id = %s",
            (str(raw_zone), mpr_manifest),
        )

    promotion = _promotion_derivation(db, mpr_manifest)
    assert promotion == EXAMPLE_DERIVATION_ID, (
        f"the documented derivation example is stale: seeded {promotion}"
    )
    spatial = _spatial_derivation(db, gis_manifest)
    nd_wells = _well_derivation(
        db, mpr_manifest, source_id="nd_wells", output_rows=1 + len(OTHER_API10S)
    )
    tx_wells = _well_derivation(
        db, gis_manifest, source_id="tx_gis_wells", output_rows=1
    )
    completion = _completion_derivation(db, fracfocus_manifest)

    seed_well(db, api10=EXAMPLE_API10, manifest_id=mpr_manifest, derivation_id=nd_wells)
    for index, api10 in enumerate(OTHER_API10S):
        seed_well(
            db,
            api10=api10,
            manifest_id=mpr_manifest,
            derivation_id=nd_wells,
            well_name=f"CONTRACT {index + 1}H",
            status_canonical="plugged" if index % 2 else "active",
            operator_name_reported="CONTINENTAL RESOURCES, INC" if index % 2 else "HESS",
        )
    seed_well(
        db,
        api10=TX_API10,
        manifest_id=gis_manifest,
        derivation_id=tx_wells,
        state_code="42",
        county_code_at_permit="003",
        ndic_file_no=None,
        basin="permian",
        land_unit_label=None,
        well_name="UNIVERSITY 12-1",
        operator_name_reported="PIONEER NATURAL RESOURCES USA INC",
        operator_id="663854",
        status_canonical="active",
        status_reported="PRODUCING",
        well_type_reported="PRODUCING",
        spud_date=None,
        total_depth_ft=Decimal("11450.0"),
        completion_date=date(2019, 4, 12),
    )
    seed_well_spatial(
        db,
        api10=TX_API10,
        geom_type="surface",
        wkt="POINT(-102.7644756 32.3578353)",
        source_datum="EPSG:4267",
        transform_rule_id="cr_tx_nad27_1",
        manifest_id=gis_manifest,
        derivation_id=spatial,
    )
    seed_well_spatial(
        db, api10=EXAMPLE_API10, manifest_id=gis_manifest, derivation_id=spatial
    )
    seed_well_spatial(
        db,
        api10=EXAMPLE_API10,
        geom_type="surface",
        manifest_id=gis_manifest,
        derivation_id=spatial,
    )
    _seed_production(db, mpr_manifest, promotion)
    _seed_completion_context(
        db,
        mpr_manifest_id=mpr_manifest,
        production_derivation_id=promotion,
        fracfocus_manifest_id=fracfocus_manifest,
        completion_derivation_id=completion,
    )
    db.commit()
    with lineage_session(
        recorder=PostgresRecorder(db),
        environment=FIXTURE_ENV,
        clock=FixedClock(datetime(2026, 8, 27, 6, 0, 0, tzinfo=UTC)),
        correlation_id="run_contract_neighbors",
    ):
        refresh_neighbors(db)
    _seed_neighbor_mart(db)
    _seed_quarantine(db, mpr_manifest)
    _seed_example_key(db)
    publication = register_pinned_control(db, pinned_control, manifest_id=mpr_manifest)
    assert publication == EXAMPLE_PUBLICATION_ID, (
        f"the documented publication example is stale: seeded {publication}"
    )
    open_vintage(
        db,
        source_id="nd_mpr_xlsx",
        vintage_date=REPORT_VINTAGE,
        manifest_ids=[mpr_manifest],
        opened_at=datetime(2026, 8, 1, 5, 2, 11, tzinfo=UTC),
        promotion_derivation_id=promotion,
        rows_examined=24,
        rows_appended=19,
        months_touched=[month.isoformat() for month in PRODUCTION_MONTHS],
        # DR-82: the fixture restates a month, so its vintage must say so — an empty summary
        # left the restatement-exemption arm of the R6 walker with nothing to defend.
        restatement_summary={RESTATED_MONTH.isoformat(): 1},
    )
    return db


def _seed_example_key(connection: psycopg.Connection) -> None:
    """The key id `revoke_key` and `rotate_key` publish, as a row rather than as a fiction.

    Its cleartext is minted here and dropped on the floor: what the examples need is an id
    that resolves, not a credential (gate-a2-qa M-3).
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.api_keys (key_id, sha256, label, scope, created_at,"
            " created_by) values (%s, %s, %s, 'guest', %s, 'owner')"
            " on conflict (key_id) do nothing",
            (
                EXAMPLE_KEY_ID,
                fingerprint(mint_secret()),
                "the documented example key",
                datetime(2026, 8, 1, 5, 2, 11, tzinfo=UTC),
            ),
        )


def _tile_transport(request: httpx.Request) -> httpx.Response:
    """Stands in for martin: a body for the seeded tile, 204 for anything else.

    The body is an iterator so the double presents an unconsumed stream, which is what the
    proxy reads: bytes content would arrive already consumed and no transport does that.
    """
    if request.url.path.endswith("/0/0/0"):
        return httpx.Response(204)
    return httpx.Response(
        200, content=iter([TILE_BODY]), headers={"content-type": "application/x-protobuf"}
    )


@pytest.fixture
def client(api_client: TestClient, seeded: psycopg.Connection) -> Iterator[TestClient]:
    """The authenticated TestClient with martin replaced by a transport stub."""
    api_client.app.state.tile_client = httpx.Client(
        transport=httpx.MockTransport(_tile_transport), base_url="http://martin.invalid"
    )
    api_client.app.dependency_overrides[get_key_store] = lambda: ConnectionKeyStore(seeded)
    api_client.app.dependency_overrides[get_session_store] = lambda: ConnectionSessionStore(seeded)
    yield api_client
    api_client.app.state.tile_client.close()


def issue_key(client: TestClient, *, label: str, scope: str) -> str:
    """Issue through the API rather than the table: a test key that skipped the endpoint
    would not prove the endpoint stores what it claims to store."""
    response = client.post("/v1/keys", json={"label": label, "scope": scope})
    assert response.status_code == 201, response.text
    return response.json()["data"]["secret"]


def as_principal(client: TestClient, secret: str | None) -> TestClient:
    """A second client on the same app, presenting a different credential (or none)."""
    headers = {} if secret is None else {KEY_HEADER: secret}
    return TestClient(client.app, headers=headers)


@pytest.fixture
def guest_client(client: TestClient) -> TestClient:
    return as_principal(client, issue_key(client, label="qa-guest-2026", scope="guest"))


@pytest.fixture
def agent_client(client: TestClient) -> TestClient:
    return as_principal(client, issue_key(client, label="qa-agent-2026", scope="agent"))


# --- session principals -------------------------------------------------------------------
#
# A session client speaks https so the __Host- cookie, which requires Secure, is actually
# stored by the transport. Over http the client would silently drop it and every session test
# would read as an authentication failure.

SESSION_BASE_URL = "https://testserver"
VIEWER_PASSWORD = "a-sufficiently-long-viewer-password"
OWNER_PASSWORD = "a-sufficiently-long-owner-password"

# Argon2id at the shipped parameters costs ~60 ms per call by design, and the login route pads
# itself to a 250 ms floor so the failure classes cannot be told apart by timing. Both are
# correct in production and ruinous in a fixture the auth matrix builds several hundred times.
# These are computed once per session; fixtures that only need *a principal holding a session*
# seed the row directly, and the tests that exist to prove login works call `login()`.
_OWNER_HASH = hash_password(OWNER_PASSWORD)
_VIEWER_HASH = hash_password(VIEWER_PASSWORD)


def seed_session(
    client: TestClient, connection: psycopg.Connection, *, username: str, role: str
) -> TestClient:
    """A client holding a live session, without paying for the login route.

    The matrix asks what a principal class may *reach*; that login works is a different
    question, proved against the real route in test_login_uniformity.py and
    test_session_cookie.py. Going through login here would add a 250 ms floor and an Argon2id
    verify to every one of several hundred parametrised cases.
    """
    user_id = seed_user(
        connection,
        username=username,
        role=role,
        password_hash=_OWNER_HASH if role == "owner" else _VIEWER_HASH,
    )
    now = datetime.now(UTC)
    user = find_user_by_id(connection, user_id)
    assert user is not None
    _, token = create_session(connection, user=user, now=now, client_ip="198.51.100.4")
    connection.commit()
    session = TestClient(client.app, base_url=SESSION_BASE_URL)
    session.cookies.set(SESSION_COOKIE, token)
    return session


def seed_user(
    connection: psycopg.Connection,
    *,
    username: str,
    role: str,
    password: str | None = None,
    password_hash: str | None = None,
) -> str:
    """Insert an account directly, the way `glasswell-owner-bootstrap` does.

    There is deliberately no API path that creates the *first* owner -- `/v1/users` is
    owner-only, so it cannot bootstrap itself. A fixture that needs an account to log in
    with therefore seeds it exactly as the console entry point does.
    """
    now = datetime.now(UTC)
    user_id = new_user_id(now)
    stored = password_hash or hash_password(password or "")
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.users (user_id, username, password_hash, role, created_at,"
            " created_by, password_changed_at) values (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, username, stored, role, now, "contract-fixture", now),
        )
    connection.commit()
    return user_id


def create_user(client: TestClient, *, username: str, password: str, role: str) -> str:
    """Through the API, for the same reason `issue_key` is: a row inserted behind the
    endpoint would not prove the endpoint stores what it claims to."""
    response = client.post(
        "/v1/users", json={"username": username, "password": password, "role": role}
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["user_id"]


def login(client: TestClient, *, username: str, password: str) -> TestClient:
    """A fresh cookie-bearing client, logged in through the real challenge/login pair."""
    session = TestClient(client.app, base_url=SESSION_BASE_URL)
    token = challenge(session)
    response = session.post(
        "/v1/session",
        json={"username": username, "password": password},
        headers={CSRF_HEADER: token},
    )
    assert response.status_code == 201, response.text
    return session


def challenge(client: TestClient) -> str:
    response = client.get("/v1/session/challenge")
    assert response.status_code == 200, response.text
    return response.json()["data"]["csrf_token"]


# --- rate-limit windows -------------------------------------------------------------------
#
# `consume_rate_limit` counts into `date_trunc('minute', clock_timestamp())`, so a bucket a
# test drove or seeded is worth nothing once the clock crosses a minute boundary: the counter
# resets to 1 and the refusal a test is about to assert never comes. Any test that spends a
# bucket and then measures the request after it is racing that boundary. These wait it out
# instead, on the database's clock, which is the one the limiter reads.

RATE_WINDOW_HEADROOM = 10.0


def rate_window_remaining(connection: psycopg.Connection) -> float:
    """Seconds left in the limiter's current window."""
    with connection.cursor() as cursor:
        cursor.execute(
            "select extract(epoch from (date_trunc('minute', clock_timestamp())"
            " + interval '1 minute') - clock_timestamp())"
        )
        remaining = float(cursor.fetchone()[0])
    connection.commit()
    return remaining


def await_rate_window(
    connection: psycopg.Connection, *, headroom: float = RATE_WINDOW_HEADROOM
) -> None:
    """Block until the window has `headroom` seconds left, so a spent bucket outlives the
    request it was spent for. Costs nothing on five runs in six and removes the race on the
    sixth; a request under test is a few hundred milliseconds against that headroom."""
    remaining = rate_window_remaining(connection)
    if remaining < headroom:
        time.sleep(remaining + 0.05)


def spend_rate_window(connection: psycopg.Connection, *, operation: str, count: int) -> None:
    """Move an already-open per-operation bucket to `count`, in the window the next request
    lands in. The route has written the row, so its principal id stays where it is resolved
    rather than being restated -- and mis-stating it would seed a bucket nothing reads."""
    await_rate_window(connection)
    with connection.cursor() as cursor:
        cursor.execute(
            "update lineage.api_rate_windows"
            "   set requests = %s,"
            "       window_started_at = date_trunc('minute', clock_timestamp())"
            " where operation = %s",
            (count, operation),
        )
        assert cursor.rowcount == 1, f"no {operation} window is open to spend"
    connection.commit()


@pytest.fixture
def owner_session(client: TestClient, seeded: psycopg.Connection) -> TestClient:
    return seed_session(client, seeded, username="owner-session", role="owner")


@pytest.fixture
def viewer_session(client: TestClient, seeded: psycopg.Connection) -> TestClient:
    return seed_session(client, seeded, username="viewer-session", role="viewer")


@pytest.fixture
def expired_session(client: TestClient, seeded: psycopg.Connection) -> TestClient:
    """A session whose row is revoked server-side: the cookie is held but is dead.

    Scoped to this account. Revoking every live session would silently kill the sibling
    fixtures, and the matrix would then read as "a session reaches nothing".
    """
    session = seed_session(client, seeded, username="expired-session", role="viewer")
    with seeded.cursor() as cursor:
        cursor.execute(
            "update lineage.sessions set revoked_at = now(), revoked_reason = 'admin'"
            " where revoked_at is null and user_id in"
            "       (select user_id from lineage.users where username = 'expired-session')"
        )
    seeded.commit()
    return session
