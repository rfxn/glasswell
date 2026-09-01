"""The New Mexico tile mart: one point layer, and a test that no second one appears.

Modelled on `test_marts_nd.py`. What is specific to New Mexico is what it must *not* publish:
neither in-scope source ships a lateral, so a `nm_laterals` layer would draw a producing
footprint nobody filed. The assertion is against `PUBLISHED_LAYERS` — the set the tile proxy
refuses on — rather than against the mart module's own constant, which would be the module
asserting itself back at itself.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import psycopg
import pytest
import yaml

from glasswell.api.routers.tiles import PUBLISHED_LAYERS
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts import nd_wells as nd_marts
from glasswell.marts import nm_wells as nm_marts
from glasswell.seed import seed_all
from glasswell.seed.conformance_nm_wells import (
    DOCUMENTED_UNMAPPED_CLASS,
    STATUS_CANONICAL_MAP,
)
from tests.integration.test_marts_nd import MARTIN_CONFIG, covering_tile, extent_of, rows, scalar
from tests.support.layers import schema_reads_in
from tests.support.mvt import attribute_keys, feature_count, layer_name, layers
from tests.support.seed import seed_manifest, seed_well, seed_well_spatial

pytestmark = pytest.mark.integration

NM_API10S = ("3001599001", "3001599002")
NM_SURFACE = ("POINT(-103.9000 32.1000)", "POINT(-103.8000 32.2000)")
# A New Mexico point whose api10 carries no header row: it must still tile, unstyled.
NM_ORPHAN = "3001599003"
NM_ORPHAN_SURFACE = "POINT(-103.7000 32.3000)"
ND_API10 = "3305399001"
ND_SURFACE = "POINT(-102.7850 47.9400)"
TILE_KEYS = {
    "api10", "operator_name", "status_canonical", "status_reported", "well_type_reported",
    "county_code", "spud_year", "derivation_id",
}


@pytest.fixture
def refreshed(db: psycopg.Connection, lineage_env):
    seed_all(db)
    manifest = seed_manifest(db, sha256="b" * 64, source_id="nm_ocd_wellhistory")
    for api10, surface in zip(NM_API10S, NM_SURFACE, strict=True):
        seed_well(
            db,
            api10=api10,
            state_code="30",
            manifest_id=manifest,
            status_canonical=None,
            status_reported="A",
            well_type_reported="O",
            operator_name_reported="MEWBOURNE OIL COMPANY",
            spud_date=date(2019, 5, 27),
        )
        seed_well_spatial(
            db, api10=api10, geom_type="surface", wkt=surface, manifest_id=manifest
        )
    seed_well_spatial(
        db, api10=NM_ORPHAN, geom_type="surface", wkt=NM_ORPHAN_SURFACE, manifest_id=manifest
    )
    seed_well(db, api10=ND_API10)
    seed_well_spatial(db, api10=ND_API10, geom_type="surface", wkt=ND_SURFACE)
    db.commit()

    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        refresh = nm_marts.refresh_all(db)
    db.commit()
    return db, refresh


def test_the_refresh_publishes_one_point_layer_and_rebuilds_rather_than_appends(refreshed):
    db, refresh = refreshed

    assert refresh.layers == ("nm_wells",)
    assert refresh.row_counts == {"nm_wells_tile": len(NM_API10S) + 1}
    with lineage_session(
        recorder=PostgresRecorder(db),
        environment=nm_marts.resolve_environment(db, env_id="env_nm_repeat"),
    ):
        again = nm_marts.refresh_all(db)
    db.commit()
    assert again.row_counts == refresh.row_counts
    assert scalar(db, "select count(distinct derivation_id) from marts.nm_wells_tile") == 1


def test_a_geometry_with_no_well_row_still_tiles_unstyled(refreshed):
    """The left-join property: a point must not disappear between canonical and the map."""
    db, _ = refreshed
    row = rows(
        db,
        "select operator_name, status_canonical, well_type_reported from marts.nm_wells_tile"
        " where api10 = %s",
        (NM_ORPHAN,),
    )

    assert row == [(None, None, None)]


def test_no_other_states_geometry_is_in_the_new_mexico_mart(refreshed):
    db, _ = refreshed

    assert rows(db, "select distinct left(api10, 2) from marts.nm_wells_tile") == [("30",)]
    assert scalar(
        db, "select count(*) from marts.nm_wells_tile where api10 = %s", (ND_API10,)
    ) == 0


def test_the_nd_mart_does_not_sweep_the_new_mexico_points_in(refreshed, lineage_env):
    """The sibling half of the same property, run with both states resident."""
    db, _ = refreshed
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        nd_marts.refresh_all(db)
    db.commit()

    assert rows(db, "select distinct left(api10, 2) from marts.nd_wells_tile") == [("33",)]


def test_the_status_letter_rides_the_tile_beside_the_class_it_resolves_to(refreshed):
    """Both, not either: the class is what the map paints and the letter is what the regulator
    filed, and carrying the letter is what makes the mapping readable on the card."""
    db, _ = refreshed
    row = rows(
        db,
        "select status_canonical, status_reported from marts.nm_wells_tile where api10 = %s",
        (NM_API10S[0],),
    )

    assert row == [("active", "A")]


def test_the_derivation_records_the_state_and_the_rules_it_cited(refreshed):
    db, refresh = refreshed
    params = scalar(
        db,
        "select params from lineage.derivations where derivation_id = %s",
        (refresh.derivation_id,),
    )
    cited = {
        rule
        for (rule,) in rows(
            db,
            "select rule_id from lineage.derivation_rules where derivation_id = %s",
            (refresh.derivation_id,),
        )
    }

    assert params["state_code"] == "30"
    assert params["geometry_scope"] == "surface_only"
    assert params["layers"] == ["nm_wells"]
    assert {
        "cr_nm_wellhistory_datum_1",
        "cr_nm_wellhistory_geometry_provenance_1",
        "cr_nm_wellhistory_geometry_scope_1",
        "cr_nm_wellhistory_status_vocab_2",
    } <= cited


def test_the_mart_reads_canonical_only(refreshed):
    """Layer boundary: marts read canonical, never staging."""
    source = (
        nm_marts._WELLS_SELECT + nm_marts._INPUT_DERIVATIONS + nm_marts._WELLS_AS_OF
    )

    # Folded over the whole module rather than grepped over the three constants: a staging name
    # spelled in pieces elsewhere in the file greps clean and still reads staging.
    assert schema_reads_in(Path(nm_marts.__file__), "staging") == []
    assert "canonical.well_spatial" in source
    assert "canonical.wells" in source


def test_no_nm_laterals_layer_is_published(refreshed):
    """Asserted against the proxy's allowlist, which is what a request is refused on."""
    assert "nm_wells" in PUBLISHED_LAYERS
    assert "nm_laterals" not in PUBLISHED_LAYERS
    assert not any(name.startswith("nm_") and name != "nm_wells" for name in PUBLISHED_LAYERS)


def test_the_martin_config_publishes_the_new_layer_too(refreshed):
    """CI asserts the config equals the allowlist, so the two move together or the build fails."""
    functions = yaml.safe_load(MARTIN_CONFIG.read_text())["postgres"]["functions"]

    assert set(functions) == set(PUBLISHED_LAYERS)
    assert functions["nm_wells"] == {"schema": "marts", "function": "nm_wells"}


def test_the_layer_serves_a_decodable_tile_with_its_declared_properties(refreshed):
    db, _ = refreshed
    zoom, x, y = covering_tile(extent_of(db, "marts.nm_wells_tile"))
    body = scalar(db, "select marts.nm_wells(%s, %s, %s)", (zoom, x, y))

    assert body
    decoded = layers(bytes(body))
    assert layer_name(decoded[0]) == "nm_wells"
    assert feature_count(decoded[0]) == len(NM_API10S) + 1
    assert set(attribute_keys(decoded[0])) <= TILE_KEYS


# One well per OCD letter the header table carries, so the mart's resolution is exercised over
# the whole published vocabulary rather than over the one code the fixture above happens to use.
RESOLVED_API10S = {
    code: f"3001598{index:03d}" for index, code in enumerate(sorted(STATUS_CANONICAL_MAP), start=1)
}


@pytest.fixture
def resolved(db: psycopg.Connection, lineage_env):
    """Every published letter, promoted with a null class exactly as the ingest writes it."""
    seed_all(db)
    manifest = seed_manifest(db, sha256="c" * 64, source_id="nm_ocd_wellhistory")
    for index, (code, api10) in enumerate(sorted(RESOLVED_API10S.items())):
        seed_well(
            db,
            api10=api10,
            state_code="30",
            manifest_id=manifest,
            status_canonical=None,
            status_reported=code,
        )
        seed_well_spatial(
            db,
            api10=api10,
            geom_type="surface",
            wkt=f"POINT(-103.{500 + index} 32.500)",
            manifest_id=manifest,
        )
    db.commit()
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        nm_marts.refresh_all(db)
    db.commit()
    return db


def test_every_published_letter_resolves_to_the_class_the_registry_maps_it_to(resolved):
    """The whole point of the read-time resolver: canonical.wells still says null, and the
    tile the map reads says what cr_nm_wellhistory_status_vocab_2 decided it says."""
    served = dict(
        rows(
            resolved,
            "select t.status_reported, t.status_canonical from marts.nm_wells_tile t"
            " where t.api10 = any(%s)",
            (list(RESOLVED_API10S.values()),),
        )
    )

    assert served == STATUS_CANONICAL_MAP


def test_the_promoted_column_is_still_null_because_nothing_was_backfilled(resolved):
    """Append-only holds: the class is a join, not a write."""
    assert scalar(
        resolved,
        "select count(*) from canonical.wells"
        " where state_code = '30' and status_canonical is not null",
    ) == 0


def test_the_four_documented_codes_reach_the_tile_as_a_class_and_not_as_a_null(resolved):
    served = rows(
        resolved,
        "select status_reported from marts.nm_wells_tile"
        " where status_canonical = %s order by status_reported",
        (DOCUMENTED_UNMAPPED_CLASS,),
    )

    assert [row[0] for row in served] == ["I", "J", "Q", "Z"]


def test_a_letter_the_registry_does_not_map_passes_through_unclassed(db, lineage_env):
    """`unmapped_action` is passthrough, so an unknown letter keeps its header and its point
    and arrives at the map as the absence class — it is not quarantined out of the spine."""
    seed_all(db)
    manifest = seed_manifest(db, sha256="d" * 64, source_id="nm_ocd_wellhistory")
    seed_well(
        db,
        api10="3001597001",
        state_code="30",
        manifest_id=manifest,
        status_canonical=None,
        status_reported="&",
    )
    seed_well_spatial(
        db, api10="3001597001", geom_type="surface", wkt="POINT(-103.4 32.4)",
        manifest_id=manifest,
    )
    db.commit()
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        nm_marts.refresh_all(db)
    db.commit()

    assert rows(
        db,
        "select status_reported, status_canonical from marts.nm_wells_tile where api10 = %s",
        ("3001597001",),
    ) == [("&", None)]


def test_no_other_states_letters_are_resolved_through_the_new_mexico_map(db, lineage_env):
    """The resolver is keyed by state as well as by letter. A North Dakota `A` must not pick
    up New Mexico's decode — the two vocabularies share letters and not meanings."""
    seed_all(db)
    assert scalar(
        db,
        "select count(*) from canonical.status_resolution where for_state_code <> '30'",
    ) == 0
