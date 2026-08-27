"""Contract-tier fixtures: a seeded database whose ids are the OpenAPI examples.

SB-07 §10's harness calls every operation with its documented example, so the fixture
has to contain exactly those entities. `glasswell.api.examples` is the single place
they are written down; everything here seeds against those constants.
"""

from __future__ import annotations

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

from glasswell.api.deps import get_key_store
from glasswell.api.examples import (
    EXAMPLE_API10,
    EXAMPLE_DERIVATION_ID,
    EXAMPLE_MANIFEST_ID,
    EXAMPLE_QUARANTINE_ID,
    KEY_HEADER,
)
from glasswell.api.principal import ConnectionKeyStore, fingerprint, mint_secret
from glasswell.api.routers.keys import EXAMPLE_KEY_ID
from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.fetch import RAW_ROOT_ENV
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.serialization import hash_payload
from glasswell.lineage.store import PostgresRecorder
from glasswell.lineage.vintages import open_vintage
from glasswell.seed import seed_all
from tests.support.fakes import FixedClock
from tests.support.seed import FIXTURE_ENV, seed_manifest, seed_well, seed_well_spatial

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


@pytest.fixture
def seeded(db: psycopg.Connection, raw_zone: Path) -> psycopg.Connection:
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
    completion = _completion_derivation(db, fracfocus_manifest)

    seed_well(db, api10=EXAMPLE_API10, manifest_id=mpr_manifest, derivation_id=promotion)
    for index, api10 in enumerate(OTHER_API10S):
        seed_well(
            db,
            api10=api10,
            manifest_id=mpr_manifest,
            derivation_id=promotion,
            well_name=f"CONTRACT {index + 1}H",
            status_canonical="plugged" if index % 2 else "active",
            operator_name_reported="CONTINENTAL RESOURCES, INC" if index % 2 else "HESS",
        )
    seed_well(
        db,
        api10=TX_API10,
        manifest_id=gis_manifest,
        derivation_id=spatial,
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
    _seed_quarantine(db, mpr_manifest)
    _seed_example_key(db)
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
