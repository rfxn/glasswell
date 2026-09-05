"""The Colorado tile mart: a profile row in the engine, and what it puts on the wire.

Two things are being proved. The mart is a registration, not a module -- there is no
`marts/co_wells.py` and there never will be. And the four resident jurisdictions' mart
addresses do not move because a fifth arrived, which is what makes adding one safe.
"""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest

from glasswell.lineage import PostgresRecorder
from glasswell.lineage.capture import lineage_session
from glasswell.marts import wells
from glasswell.marts.tiles import TILE_LAYERS
from glasswell.seed import seed_all
from tests.support.seed import seed_manifest, seed_well, seed_well_spatial

pytestmark = pytest.mark.integration

# Committed, not read out of work-output/: that directory is git-excluded and this path was
# absolute to one workstation, so the comparison ran on exactly one machine and raised
# PermissionError everywhere else -- including before its own absence refusal could fire.
BASELINE = Path(__file__).resolve().parents[1] / "fixtures" / "marts" / "seam-mart-baseline.json"
API10 = "0512324638"
PLANNED_API10 = "0512399002"


@pytest.fixture
def refreshed(db: psycopg.Connection, lineage_env) -> wells.MartRefresh:
    seed_all(db)
    manifest = seed_manifest(db, sha256="c" * 64, source_id="co_ecmc_wells_shp")
    for api10, status, qualifier in (
        (API10, "PR", "actual"),
        (PLANNED_API10, "SO", "planned"),
    ):
        seed_well(
            db,
            api10=api10,
            state_code="05",
            status_canonical=None,
            status_reported=status,
            well_type_reported="GW",
            county_code_at_permit="123",
            manifest_id=manifest,
            basin=None,
        )
        seed_well_spatial(
            db,
            api10=api10,
            geom_type="surface",
            wkt="POINT(-104.9 40.1)",
            manifest_id=manifest,
            location_qualifier=qualifier,
        )
    db.commit()
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        refresh = wells.refresh_for(db, "CO")
    db.commit()
    return refresh


def test_the_status_class_arrives_from_the_resolver_and_not_from_the_promotion(
    refreshed, db
) -> None:
    """The mart resolves the class rather than reading one, and the filed code rides beside it.

    Both halves are asserted, and they are not the same claim. The filed code is Colorado's own
    and this mart is what serves it. The class comes from `canonical.status_resolution`, whose
    resolver the facets track owns and which merges after this one: until it covers every
    registered codebook the class is null here, so this asserts the resolver's answer wherever
    the resolver has Colorado and asserts the filed code either way. A null class is a served
    'unmapped', not a defect in the promotion -- and `test_migration_colorado.py` is where the
    row the resolver owes Colorado is spelled out.
    """
    with db.cursor() as cursor:
        cursor.execute(
            "select api10, status_reported, status_canonical from marts.co_wells_tile"
            " order by api10"
        )
        served = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
        cursor.execute(
            "select for_status_reported, resolved_status from canonical.status_resolution r"
            "  join lineage.jurisdictions_as_of(current_date, current_date) j"
            "    on j.identity_prefix = r.for_state_code"
            " where j.jurisdiction_code = 'CO'"
        )
        resolver = dict(cursor.fetchall())

    assert served[API10][0] == "PR"
    # SO is documented and has no canonical counterpart, so where the resolver reaches Colorado
    # it carries the registered class rather than a null: the regulator did say something.
    assert served[PLANNED_API10][0] == "SO"
    for api10, (reported, resolved) in served.items():
        assert resolved == resolver.get(reported), api10


def test_the_two_geometry_axes_are_published_separately(refreshed, db) -> None:
    """geometry_provenance answers which feature this is; loc_qual_class answers how good the
    coordinate is. A client that drew them as one axis would call a permit location a survey."""
    with db.cursor() as cursor:
        cursor.execute(
            "select geometry_provenance, loc_qual_class from marts.co_wells_tile"
            " order by api10"
        )
        rows = cursor.fetchall()

    assert [row[0] for row in rows] == ["surface", "surface"]
    assert sorted(row[1] for row in rows) == ["actual", "planned"]


def test_the_tile_layer_publishes_exactly_the_columns_the_view_serves(refreshed, db) -> None:
    layer = next(layer for layer in TILE_LAYERS if layer.name == "co_wells")
    with db.cursor() as cursor:
        cursor.execute(
            "select column_name from information_schema.columns"
            " where table_schema = 'marts' and table_name = 'tile_co_wells'"
            "   and column_name <> 'geom' order by ordinal_position"
        )
        served = [row[0] for row in cursor.fetchall()]

    assert list(layer.columns) == served


def test_the_refresh_records_its_scope_and_the_rules_it_read(refreshed, db) -> None:
    """A tile is a served figure, so the refresh has to be able to prove which decisions built
    it. The scope is a derivation parameter and the rules are rows against the derivation."""
    with db.cursor() as cursor:
        cursor.execute(
            "select params from lineage.derivations where derivation_id = %s",
            (refreshed.derivation_id,),
        )
        params = cursor.fetchone()[0]
        cursor.execute(
            "select rule_id from lineage.derivation_rules where derivation_id = %s",
            (refreshed.derivation_id,),
        )
        rules = {row[0] for row in cursor.fetchall()}

    assert params["geometry_scope"] == "surface_only"
    assert params["state_code"] == "05"
    assert {
        "cr_co_wells_location_qualifier_1",
        "cr_co_wells_status_vocab_1",
        "cr_co_wells_geometry_provenance_1",
    } <= rules
    assert refreshed.to_dict()["layers"] == ["co_wells"]


def test_a_blank_well_type_promoted_before_the_rule_reaches_the_tile_as_absent(
    db: psycopg.Connection, lineage_env
) -> None:
    """The 1,172 headers promoted with an empty Well_Class, read under the rule at the mart.

    canonical.wells is append-only and Colorado's effective_from is ECMC's own Stat_Date, so
    those rows cannot be restated -- a corrected row carries the key of the row it corrects.
    The mart is one of the three reads that apply cr_co_wells_shp_blank_is_absent_1 instead,
    and the map has to agree with the well card and the legend about the same well.
    """
    seed_all(db)
    manifest = seed_manifest(db, sha256="d" * 64, source_id="co_ecmc_wells_shp")
    blank_api10 = "0512300001"
    seed_well(
        db,
        api10=blank_api10,
        state_code="05",
        status_canonical=None,
        status_reported="PR",
        well_type_reported="",
        operator_name_reported="",
        county_code_at_permit="123",
        manifest_id=manifest,
        basin=None,
    )
    seed_well_spatial(
        db,
        api10=blank_api10,
        geom_type="surface",
        wkt="POINT(-104.9 40.1)",
        manifest_id=manifest,
        location_qualifier="actual",
    )
    db.commit()
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        refresh = wells.refresh_for(db, "CO")
    db.commit()

    with db.cursor() as cursor:
        cursor.execute(
            "select well_type_reported, operator_name"
            "  from marts.co_wells_tile where api10 = %s",
            (blank_api10,),
        )
        well_type, operator = cursor.fetchone()
        cursor.execute(
            "select rule_id from lineage.derivation_rules where derivation_id = %s",
            (refresh.derivation_id,),
        )
        cited = {row[0] for row in cursor.fetchall()}

    assert well_type is None
    assert operator is None
    assert "cr_co_wells_shp_blank_is_absent_1" in cited


def test_no_resident_mart_address_moved_because_a_fifth_state_arrived(db, lineage_env) -> None:
    """The seam track measured the four addresses before Colorado existed and wrote them down.

    What this compares is what that capture holds: the layer set each profile publishes, per
    code. The derivation ids beside them were measured against that track's own planted
    fixture and are not reproducible from here, so they are not asserted rather than asserted
    weakly -- `tests/unit/test_mart_profiles.py` is what pins the rule sets and the params key
    sets those ids are built from. The phase refuses outright if the capture is absent: a run
    that cannot compare the four addresses must not report that they are unchanged.
    """
    assert BASELINE.exists(), (
        f"{BASELINE} is absent: the four resident mart addresses cannot be compared, and a"
        " phase that cannot compare them must not report that they are unchanged"
    )
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))

    assert set(baseline) == {"ND", "TX", "NM", "MT"}, (
        "the capture is of the four resident jurisdictions; a fifth in it would mean it was"
        " taken after Colorado landed and proves nothing about the move"
    )
    for code, measured in baseline.items():
        profile = wells.profile_for(code)
        assert [layer.name for layer in profile.layers] == measured["layers"], code
        assert measured["derivation_id"].startswith("drv_"), code
    assert "co_wells" not in {
        name for measured in baseline.values() for name in measured["layers"]
    }
