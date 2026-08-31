"""Tier 2, whole: header bytes to a decoded Permian tile and a served well.

`test_nm_wells_promote.py` proves the promotion and `test_marts_nm.py` proves the mart, each
against its own inputs — the mart's fixture seeds `canonical.wells` rows by hand. Nothing joined
them, so nothing measured what the operator actually runs: stage, promote, refresh, serve. This
file runs that chain once and asserts on its seam.

The tile is pinned to a New Mexico Permian tile chosen from geography, not from
`ST_Extent(marts.nm_wells_tile)`. A covering tile of whatever happens to be loaded cannot be
empty and so cannot fail; a fixed Permian tile can, which is the only version of this assertion
worth running.

Numbers here are fixture-derived. The fixture is a truncation of the sealed 2026-08-20 header
artifact, so its ratios are not the production ratios and no count in this file is a forecast.
"""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.ingest import nm_wells
from glasswell.ingest.base import open_ingest_run
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts import nm_wells as nm_marts
from tests.integration.test_marts_nd import rows, scalar, tile_of
from tests.integration.test_nm_stage import stage
from tests.integration.test_nm_stage import staging_root as _staging_root
from tests.integration.test_nm_wells_promote import FIXTURE, SOURCE
from tests.support.fakes import FixedClock
from tests.support.mvt import attribute_keys, attribute_values, feature_count, layer_name, layers

staging_root = _staging_root

pytestmark = pytest.mark.integration

PROMOTED_AT = datetime(2026, 8, 21, 6, 15, 0, tzinfo=UTC)
STAGED_AT = datetime(2026, 8, 20, 6, 15, 0, tzinfo=UTC)

# Southeastern New Mexico: the state's Permian Basin acreage, Eddy and Lea up through the
# Northwest Shelf in Chaves. The tile's own envelope is asserted to sit inside this box, so
# "over the Permian" is measured rather than asserted about.
PERMIAN_NM = (-105.00, 31.33, -103.00, 34.00)
# Chaves County, north of Roswell. The header fixture was cut for coordinate populations rather
# than for geography, so its acreage is the Northwest Shelf and not the Delaware core; z9 is
# past THIN_MAX_ZOOM, so the count on the wire is the count in the store.
PERMIAN_ANCHOR = (-104.20, 33.35)
PERMIAN_ZOOM = 9

REFUSALS = ("coordinate_absent", "coordinate_sentinel")


@pytest.fixture
def seeded(db: psycopg.Connection) -> None:
    from glasswell.seed import seed_all

    seed_all(db)
    db.commit()


@pytest.fixture
def tier2(db, seeded, lineage_env, raw_root, staging_root, tmp_path, monkeypatch):
    """The operator's chain, in the operator's order, on one database."""
    staged = stage(
        db,
        raw_root,
        tmp_path,
        monkeypatch,
        table="wellhistory",
        document=FIXTURE.read_bytes(),
        at=STAGED_AT,
    )
    with open_ingest_run(db, source_id=SOURCE, clock=FixedClock(PROMOTED_AT)) as run:
        promotion = nm_wells.promote_headers(run)
    db.commit()
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        refresh = nm_marts.refresh_all(db)
    db.commit()
    return staged, promotion, refresh


def envelope(connection: psycopg.Connection, zoom: int, x: int, y: int) -> tuple[float, ...]:
    box = rows(
        connection,
        "select ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e) from"
        " (select ST_Transform(ST_TileEnvelope(%s, %s, %s), 4326) e) tile",
        (zoom, x, y),
    )[0]
    return tuple(float(value) for value in box)


def permian_tile() -> tuple[int, int, int]:
    x, y = tile_of(*PERMIAN_ANCHOR, PERMIAN_ZOOM)
    return PERMIAN_ZOOM, x, y


def test_the_chain_reconciles_from_staged_record_to_promoted_header(tier2) -> None:
    """Every staged record becomes a header, and a refused coordinate never removes one."""
    staged, promotion, _ = tier2
    refusals = sum(promotion.quarantined.get(code, 0) for code in REFUSALS)

    assert promotion.staged_rows == staged.staged_rows
    assert promotion.header_rows == promotion.staged_rows
    assert promotion.geometry_rows + refusals == promotion.header_rows
    assert all(promotion.quarantined.get(code, 0) > 0 for code in REFUSALS), (
        "both refusal codes must fire or the reconciliation proves nothing"
    )


def test_the_mart_publishes_one_tile_row_per_promoted_geometry(tier2, db) -> None:
    """The seam nothing measured: canonical geometry in, mart rows out, no state bleed."""
    _, promotion, refresh = tier2

    assert refresh.row_counts["nm_wells_tile"] == promotion.geometry_appended
    assert scalar(db, "select count(*) from marts.nm_wells_tile") == promotion.geometry_appended
    assert rows(db, "select distinct left(api10, 2) from marts.nm_wells_tile") == [("30",)]


def test_no_new_mexico_well_carries_an_invented_status_class(tier2, db) -> None:
    """The unmapped status class, end to end: the letter reaches the tile, the class stays null."""
    reported, canonical = rows(
        db,
        "select count(status_reported), count(status_canonical) from marts.nm_wells_tile",
    )[0]

    assert reported > 0
    assert canonical == 0


def test_a_permian_tile_carries_new_mexico_points_on_the_wire(tier2, db) -> None:
    """A fixed Permian tile, decoded from the bytes the tile server would return."""
    zoom, x, y = permian_tile()
    west, south, east, north = envelope(db, zoom, x, y)
    assert PERMIAN_NM[0] <= west
    assert east <= PERMIAN_NM[2]
    assert PERMIAN_NM[1] <= south
    assert north <= PERMIAN_NM[3]

    body = scalar(db, "select marts.nm_wells(%s, %s, %s)", (zoom, x, y))
    assert body, f"z{zoom}/{x}/{y} returned no tile at all"
    decoded = layers(bytes(body))
    assert [layer_name(layer) for layer in decoded] == ["nm_wells"]

    resident = scalar(
        db,
        "select count(*) from marts.nm_wells_tile"
        " where geom && ST_Transform(ST_TileEnvelope(%s, %s, %s), 4326)",
        (zoom, x, y),
    )
    assert resident > 0, "the fixture carries no Permian well; the tile assertion is vacuous"
    assert feature_count(decoded[0]) == resident
    declared = {column for column, _ in nm_marts.NM_LAYERS[0].properties}
    assert set(attribute_keys(decoded[0])) <= declared


def test_every_api10_on_the_wire_is_a_new_mexico_one(tier2, db) -> None:
    """Read the value pool rather than the writer: a Texas or Dakota key here is a mart defect."""
    zoom, x, y = permian_tile()
    body = scalar(db, "select marts.nm_wells(%s, %s, %s)", (zoom, x, y))
    keys = [
        value
        for kind, value in attribute_values(layers(bytes(body))[0])
        if kind == "string" and len(value) == 10 and value.isdigit()
    ]

    assert keys
    assert {key[:2] for key in keys} == {"30"}


def test_every_tile_feature_carries_the_derivation_that_built_it(tier2, db) -> None:
    """No naked numbers: a tile is a served figure and carries its handle."""
    _, _, refresh = tier2
    zoom, x, y = permian_tile()
    layer = layers(bytes(scalar(db, "select marts.nm_wells(%s, %s, %s)", (zoom, x, y))))[0]

    assert "derivation_id" in attribute_keys(layer)
    assert refresh.derivation_id in [value for _, value in attribute_values(layer)]


def test_the_gate_opens_on_the_served_surface_and_not_before(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch, api_client: TestClient
) -> None:
    """The whole track's claim, red then green on the same key against the real router.

    The first promotion is rolled back rather than a synthetic key probed, so the 404 and the
    200 are the same API-10 on the same database — which is the only ordering that proves the
    header row is what changed the answer.
    """
    stage(
        db,
        raw_root,
        tmp_path,
        monkeypatch,
        table="wellhistory",
        document=FIXTURE.read_bytes(),
        at=STAGED_AT,
    )
    with open_ingest_run(db, source_id=SOURCE, clock=FixedClock(PROMOTED_AT)) as run:
        nm_wells.promote_headers(run)
    api10 = scalar(db, "select api10 from canonical.wells order by api10 limit 1")
    db.rollback()

    assert scalar(db, "select count(*) from canonical.wells") == 0
    assert api_client.get(f"/v1/wells/{api10}").status_code == 404

    with open_ingest_run(db, source_id=SOURCE, clock=FixedClock(PROMOTED_AT)) as run:
        nm_wells.promote_headers(run)
    db.commit()

    response = api_client.get(f"/v1/wells/{api10}")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["state_code"] == "30"


def test_tier2_writes_no_production_row_and_needs_none(tier2, db) -> None:
    """Tier 2 is the spine and the map. The 24.8M-row history is a different runbook."""
    assert scalar(db, "select count(*) from canonical.production_monthly") == 0
    assert scalar(db, "select count(*) from marts.nm_wells_tile") > 0


def seed_aliases(connection: psycopg.Connection, ogrids: list[str]) -> None:
    with connection.cursor() as cursor:
        cursor.executemany(
            "insert into lineage.operator_aliases (operator_raw, operator, confidence,"
            " effective_from, source_id) values (%s, %s, 1.000, date '2026-08-20',"
            " 'nm_ocd_ogrid')",
            [(ogrid, f"OPERATOR {ogrid}") for ogrid in ogrids],
        )
    connection.commit()


def test_an_operator_name_absent_at_promotion_stays_absent_for_that_header(tier2, db) -> None:
    """The ordering constraint the runbook exists to state, asserted rather than reasoned.

    `operator_name_reported` is read from `lineage.operator_aliases`, which only the dimension
    promotion writes, and it is not one of the attributes `_HEADER_DIVERGENCE` compares. So a
    re-run once the aliases exist finds no divergence, appends nothing through the
    (api10, effective_from) anti-join, and leaves every name null. `canonical.wells` is
    append-only; the only route back is a restatement under a new effective row.
    """
    total, named = rows(
        db, "select count(*), count(operator_name_reported) from canonical.wells"
    )[0]
    assert total > 0
    assert named == 0, "the fixture must promote before the aliases exist or this proves nothing"

    seed_aliases(db, [ogrid for (ogrid,) in rows(
        db, "select distinct operator_id from canonical.wells where operator_id is not null"
    )])
    with open_ingest_run(
        db, source_id=SOURCE, clock=FixedClock(datetime(2026, 8, 25, 6, 15, tzinfo=UTC))
    ) as run:
        rerun = nm_wells.promote_headers(run)
    db.commit()

    assert rerun.headers_appended == 0
    assert rows(db, "select count(operator_name_reported) from canonical.wells")[0][0] == 0


def test_an_operator_name_present_at_promotion_reaches_the_header_and_the_tile(
    db, seeded, lineage_env, raw_root, staging_root, tmp_path, monkeypatch
) -> None:
    """The other half: the aliases are not optional decoration, they are an ordering input."""
    staged = stage(
        db, raw_root, tmp_path, monkeypatch,
        table="wellhistory", document=FIXTURE.read_bytes(), at=STAGED_AT,
    )
    seed_aliases(db, [ogrid for (ogrid,) in rows(
        db,
        "select distinct rtrim(ogrid_cde) from"
        f" {nm_wells.staging_table_for('wellhistory')} where manifest_id = %s"
        "  and ogrid_cde is not null",
        (staged.manifest_id,),
    )])
    with open_ingest_run(db, source_id=SOURCE, clock=FixedClock(PROMOTED_AT)) as run:
        nm_wells.promote_headers(run)
    db.commit()
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        nm_marts.refresh_all(db)
    db.commit()

    assert rows(db, "select count(operator_name_reported) from canonical.wells")[0][0] > 0
    assert scalar(db, "select count(operator_name) from marts.nm_wells_tile") > 0
