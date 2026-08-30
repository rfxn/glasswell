"""The boundary pipeline end to end: fetch, staging, promotion, repair ledger, mart, tiles.

Everything runs off the cut fixtures through a MockTransport — never the live archives.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import httpx
import pytest

from glasswell.ingest.eia_boundaries import (
    REPAIR_RULE_ID,
    BasinLayerMissing,
    load_layer,
)
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.basin_boundaries import refresh_basin_boundaries
from glasswell.seed import seed_all
from tests.integration.test_marts_nd import covering_tile, extent_of, rows, scalar
from tests.support.mvt import attribute_keys, feature_count, layer_name, layers

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "eia_boundaries"
ARCHIVES = {
    "basins": FIXTURES / "SedimentaryBasins_US_EIA_cut.zip",
    "plays": FIXTURES / "TightOil_ShaleGas_IndividualPlays_Lower48_EIA_cut.zip",
}

BASINS = 8
PLAYS = 9
# Every unresolved link in the full archive is a Niobrara row, and the fixture keeps all five.
UNLINKED_PLAYS = 4
# Bakken and Three Forks, both Williston, both ring self-intersections.
INVALID_PLAYS = 2


@pytest.fixture
def seeded(db):
    seed_all(db)
    db.commit()
    return db


def client_for(archive: Path) -> httpx.Client:
    payload = archive.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload, headers={"content-type": "application/zip"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def load(db, raw_root, lineage_env, layer: str, archive: Path | None = None):
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env), client_for(
        archive or ARCHIVES[layer]
    ) as client:
        result = load_layer(db, layer, raw_root=raw_root, client=client)
    db.commit()
    return result


def load_all(db, raw_root, lineage_env):
    return (
        load(db, raw_root, lineage_env, "basins"),
        load(db, raw_root, lineage_env, "plays"),
    )


def refreshed(db, lineage_env):
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        refresh = refresh_basin_boundaries(db)
    db.commit()
    return refresh


def test_both_layers_promote_with_full_lineage(seeded, raw_root, lineage_env):
    basins, plays = load_all(seeded, raw_root, lineage_env)

    assert basins.staged_rows == basins.promoted_rows == BASINS
    assert plays.staged_rows == plays.promoted_rows == PLAYS
    assert scalar(seeded, "select count(*) from canonical.basin_boundaries") == BASINS + PLAYS
    assert scalar(seeded, "select distinct ST_SRID(geom) from canonical.basin_boundaries") == 4326

    for result in (basins, plays):
        operations = {
            operation
            for (operation,) in rows(
                seeded,
                "select operation from lineage.derivations where derivation_id in (%s, %s)",
                (result.parse_derivation_id, result.promote_derivation_id),
            )
        }
        assert operations == {"stage.parse", "canonical.promote"}
        assert (
            scalar(
                seeded,
                "select count(*) from lineage.vintages where source_id = %s",
                (result.source_id,),
            )
            == 1
        )


def test_a_basin_and_a_play_stay_different_objects(seeded, raw_root, lineage_env):
    """cr_eia_boundary_taxonomy_1. Conflating the two is the mapping this track exists to
    refuse, so the discriminator is asserted on the counts and on the served split."""
    load_all(seeded, raw_root, lineage_env)

    kinds = dict(
        rows(
            seeded,
            "select boundary_kind, count(*) from canonical.basin_boundaries group by 1",
        )
    )

    assert kinds == {"basin": BASINS, "play": PLAYS}
    # A play carries its parent's own label; a basin carries none, by check constraint.
    assert (
        scalar(
            seeded,
            "select count(*) from canonical.basin_boundaries"
            " where boundary_kind = 'basin' and basin_name is not null",
        )
        == 0
    )


def test_the_minted_key_is_the_play_and_basin_pair_not_the_play_name(
    seeded, raw_root, lineage_env
):
    """Niobrara is five features under five Basin labels; keyed on the name alone, four of
    them would collide into one and the map would draw a fifth of the play."""
    load_all(seeded, raw_root, lineage_env)

    niobrara = rows(
        seeded,
        "select boundary_id, basin_name from canonical.basin_boundaries"
        " where boundary_kind = 'play' and name = 'Niobrara' order by boundary_id",
    )

    assert len(niobrara) == 5
    assert len({boundary_id for boundary_id, _ in niobrara}) == 5
    assert "play_niobrara_powder_river" in {boundary_id for boundary_id, _ in niobrara}


def test_a_play_links_to_its_basin_by_exact_name_and_to_nothing_otherwise(
    seeded, raw_root, lineage_env
):
    """cr_eia_basin_link_1. The four refused near-matches all have a candidate row present in
    the fixture, so an unresolved link here is the rule's refusal and not a missing basin."""
    _, plays = load_all(seeded, raw_root, lineage_env)

    linked = dict(
        rows(
            seeded,
            "select basin_name, basin_boundary_id from canonical.basin_boundaries"
            " where boundary_kind = 'play'",
        )
    )

    assert plays.unlinked == UNLINKED_PLAYS
    assert linked["Williston"] == "basin_williston"
    assert linked["Permian"] == "basin_permian"
    assert linked["Powder River"] == "basin_powder_river"
    assert linked["Piceance Basin"] is None, "UINTA-PICEANCE is a wider container, not a match"
    assert linked["Denver Basin"] is None
    assert linked["Park Basin"] is None
    assert linked["North-Central MT"] is None
    # The refused candidates are in the fixture: the null is a decision, not an absence.
    assert {
        name
        for (name,) in rows(
            seeded,
            "select name from canonical.basin_boundaries where boundary_kind = 'basin'",
        )
    } >= {"UINTA-PICEANCE", "DENVER", "NORTH PARK"}


def test_the_publishers_own_string_survives_an_unresolved_link(seeded, raw_root, lineage_env):
    """A later crosswalk supersedes the rule; it cannot do that if the string was discarded."""
    load_all(seeded, raw_root, lineage_env)

    orphaned = rows(
        seeded,
        "select name, basin_name from canonical.basin_boundaries"
        " where boundary_kind = 'play' and basin_boundary_id is null order by basin_name",
    )

    assert [basin for _, basin in orphaned] == [
        "Denver Basin", "North-Central MT", "Park Basin", "Piceance Basin",
    ]


def test_plays_refuse_to_promote_before_the_basin_layer_is_loaded(
    seeded, raw_root, lineage_env
):
    """A null link must mean the name did not resolve. Promoting plays against an empty basin
    table would make every link null and every one of them a lie."""
    with pytest.raises(BasinLayerMissing):
        load(seeded, raw_root, lineage_env, "plays")
    seeded.rollback()

    assert scalar(seeded, "select count(*) from canonical.basin_boundaries") == 0


def test_an_invalid_ring_is_repaired_and_the_repair_is_a_released_reject(
    seeded, raw_root, lineage_env
):
    """cr_eia_geometry_repair_1. Quarantining the Bakken would take the Bakken off a Bakken
    product; repairing it silently would draw a geometry nobody published."""
    _, plays = load_all(seeded, raw_root, lineage_env)

    assert plays.repaired == INVALID_PLAYS
    repaired = rows(
        seeded,
        "select name, geometry_repair, geometry_repair_reason, ST_IsValid(geom)"
        "  from canonical.basin_boundaries where geometry_repair is not null order by name",
    )

    assert [row[0] for row in repaired] == ["Bakken", "Three Forks"]
    for _, operator, reason, valid in repaired:
        assert operator == "st_makevalid_collection_extract"
        assert "Self-intersection" in reason
        assert valid, "the repair produced a geometry PostGIS still calls invalid"

    ledger = rows(
        seeded,
        "select row_payload ->> 'name', state, released_by_rule_id, release_derivation_id"
        "  from lineage.quarantine_rows where reason_code = 'invalid_geometry'"
        " order by row_payload ->> 'name'",
    )

    assert [row[0] for row in ledger] == ["Bakken", "Three Forks"]
    for _, state, released_by, release_derivation in ledger:
        assert state == "released", "a repair that leaves no reject behind is a silent repair"
        assert released_by == REPAIR_RULE_ID
        assert release_derivation == plays.promote_derivation_id


def test_the_repair_moves_no_boundary_a_reader_could_see(seeded, raw_root, lineage_env):
    """The rule claims a relative area change below 1e-15; that claim is checkable."""
    load_all(seeded, raw_root, lineage_env)

    drift = rows(
        seeded,
        "select boundary.name,"
        "       abs(ST_Area(boundary.geom) - ST_Area(staged.geom)) / ST_Area(staged.geom)"
        "  from canonical.basin_boundaries boundary"
        "  join staging.eia_plays staged"
        "    on staged.manifest_id = boundary.source_manifest_id"
        "   and btrim(staged.shale_play) = boundary.name"
        " where boundary.geometry_repair is not null",
    )

    assert len(drift) == INVALID_PLAYS
    for name, relative in drift:
        assert relative < 1e-12, f"{name} moved {relative} of its area under repair"


def test_overlapping_plays_are_served_overlapping_and_never_dissolved(
    seeded, raw_root, lineage_env
):
    """cr_eia_boundary_overlap_1. A dissolve would make the Permian one target instead of two,
    and would erase that Bakken and Three Forks are stacked over the same ground."""
    load_all(seeded, raw_root, lineage_env)

    # Area, not ST_Intersects: a de-overlapped set still intersects along the shared edge the
    # difference leaves behind, so the boolean cannot tell a dissolve from an overlap. The
    # first draft of this test used it and stayed green under a progressive ST_Difference.
    overlaps = {
        tuple(sorted((a, b))): share
        for a, b, share in rows(
            seeded,
            "select a.name, b.name,"
            "       ST_Area(ST_Intersection(a.geom, b.geom)) / ST_Area(a.geom)"
            "  from canonical.basin_boundaries a"
            "  join canonical.basin_boundaries b on a.boundary_id < b.boundary_id"
            " where a.boundary_kind = 'play' and b.boundary_kind = 'play'"
            "   and ST_Area(ST_Intersection(a.geom, b.geom)) > 0",
        )
    }

    assert overlaps[("Delaware", "Wolfcamp")] > 0.5, "the Permian stack was flattened"
    assert overlaps[("Bakken", "Three Forks")] > 0.5, "the Williston stack was flattened"
    assert scalar(
        seeded, "select count(*) from canonical.basin_boundaries where boundary_kind = 'play'"
    ) == PLAYS, "a dissolve would have collapsed the overlapping pairs"


def test_a_point_inside_no_boundary_is_unassigned_rather_than_nearest(
    seeded, raw_root, lineage_env
):
    """The other half of the overlap rule: membership is a set, and the empty set is allowed."""
    load_all(seeded, raw_root, lineage_env)
    # Mid-Atlantic, several hundred miles off the fixture's easternmost basin.
    outside = "ST_SetSRID(ST_Point(-40.0, 35.0), 4326)"

    assert (
        scalar(
            seeded,
            "select count(*) from canonical.basin_boundaries"
            f" where ST_Intersects(geom, {outside})",
        )
        == 0
    )


def test_the_served_area_is_the_publishers_own_and_says_so(seeded, raw_root, lineage_env):
    """cr_eia_area_provenance_1: a figure whose provenance is unstated reads as glasswell's."""
    load_all(seeded, raw_root, lineage_env)
    refreshed(seeded, lineage_env)

    bases = {
        basis
        for (basis,) in rows(seeded, "select distinct area_basis from marts.basin_boundaries_tile")
    }
    published, served = rows(
        seeded,
        "select staged.area_sq_mi::double precision, tile.area_sq_mi"
        "  from marts.basin_boundaries_tile tile"
        "  join staging.eia_basins staged on btrim(staged.name) = tile.name"
        " where tile.name = 'WILLISTON'",
    )[0]

    assert bases == {"publisher_reported"}
    assert served == round(published, 2)


def test_every_served_boundary_carries_the_refresh_handle(seeded, raw_root, lineage_env):
    """No naked numbers: the area rides beside the derivation ?explain=true resolves."""
    load_all(seeded, raw_root, lineage_env)
    refresh = refreshed(seeded, lineage_env)

    assert refresh.row_counts["basin_boundaries_tile"] == BASINS + PLAYS
    assert refresh.layers == ("basins", "plays")
    assert (
        scalar(seeded, "select distinct derivation_id from marts.basin_boundaries_tile")
        == refresh.derivation_id
    )
    assert (
        scalar(
            seeded,
            "select count(*) from marts.basin_boundaries_tile"
            " where area_sq_mi is not null and derivation_id is null",
        )
        == 0
    )


def test_the_refresh_cites_every_rule_that_shaped_the_boundaries(
    seeded, raw_root, lineage_env
):
    """R8's other half: a rule nothing references is a rule nothing is held to."""
    load_all(seeded, raw_root, lineage_env)
    refresh = refreshed(seeded, lineage_env)

    cited = {
        rule_id
        for (rule_id,) in rows(
            seeded,
            "select rule_id from lineage.derivation_rules where derivation_id = %s",
            (refresh.derivation_id,),
        )
    }
    registered = {
        rule_id
        for (rule_id,) in rows(
            seeded,
            "select rule_id from lineage.conformance_rules where rule_id like %s",
            ("cr\\_eia\\_%",),
        )
    }

    assert registered
    assert cited == registered


def test_the_mart_serves_both_kinds_as_decodable_tiles(seeded, raw_root, lineage_env):
    load_all(seeded, raw_root, lineage_env)
    refreshed(seeded, lineage_env)

    zoom, x, y = covering_tile(extent_of(seeded, "marts.basin_boundaries_tile"))
    for function, expected in (("basins", BASINS), ("plays", PLAYS)):
        tile = scalar(seeded, f"select marts.{function}(%s, %s, %s)", (zoom, x, y))
        assert tile is not None, f"{function} returned no tile at z{zoom}"
        decoded = {layer_name(layer): layer for layer in layers(bytes(tile))}
        assert set(decoded) == {function, f"{function}_label"}
        assert feature_count(decoded[function]) == expected
        assert feature_count(decoded[f"{function}_label"]) == expected
        assert "boundary_kind" in attribute_keys(decoded[function])
        assert "derivation_id" in attribute_keys(decoded[function])


def test_the_two_kinds_never_appear_on_each_others_layer(seeded, raw_root, lineage_env):
    """The publication boundary is the view's where-clause; a widened view would show here."""
    load_all(seeded, raw_root, lineage_env)
    refreshed(seeded, lineage_env)

    assert rows(
        seeded, "select distinct boundary_kind from marts.tile_basins"
    ) == [("basin",)]
    assert rows(seeded, "select distinct boundary_kind from marts.tile_plays") == [("play",)]


def test_the_play_view_publishes_the_link_and_the_basin_view_does_not(
    seeded, raw_root, lineage_env
):
    """Every column martin can read is served; a basin has no parent to publish."""
    served = {
        relation: {
            column
            for (column,) in rows(
                seeded,
                "select column_name from information_schema.columns"
                " where table_schema = 'marts' and table_name = %s",
                (relation,),
            )
        }
        for relation in ("tile_basins", "tile_plays")
    }

    assert "basin_boundary_id" in served["tile_plays"]
    assert "sub_basin" in served["tile_plays"]
    assert "basin_boundary_id" not in served["tile_basins"]


def test_reloading_identical_bytes_is_a_recorded_noop(seeded, raw_root, lineage_env):
    first = load(seeded, raw_root, lineage_env, "basins")
    second = load(seeded, raw_root, lineage_env, "basins")

    assert second.unchanged
    assert second.manifest_id == first.manifest_id
    assert second.staged_rows == 0
    assert scalar(seeded, "select count(*) from canonical.basin_boundaries") == BASINS


def revised_zip(target: Path, source: Path) -> Path:
    """The archive with new bytes and identical members: a revision whose every canonical key
    already belongs to the first manifest."""
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w") as revised:
        revised.comment = b"dr89 all-conflict revision"
        for name in original.namelist():
            revised.writestr(name, original.read(name))
    return target


def test_a_revised_pull_whose_rows_all_conflict_is_detected_not_silently_promoted(
    seeded, raw_root, lineage_env, tmp_path
):
    """DR-89: basin_boundaries is keyed on boundary_id alone, so a revision whose rows all
    conflict owns nothing and would be re-staged on every poll with the refusal unrecorded."""
    first = load(seeded, raw_root, lineage_env, "basins")
    second = load(
        seeded,
        raw_root,
        lineage_env,
        "basins",
        archive=revised_zip(tmp_path / "revised.zip", ARCHIVES["basins"]),
    )

    assert second.manifest_id != first.manifest_id
    assert second.unchanged is False
    assert second.staged_rows == BASINS
    assert second.promoted_rows == 0
    assert second.quarantined["key_collision"] == BASINS
    assert scalar(seeded, "select count(*) from canonical.basin_boundaries") == BASINS


def test_staging_holds_the_published_ring_verbatim_including_the_invalid_ones(
    seeded, raw_root, lineage_env
):
    """Staging is source-faithful: repairing on the way in would leave no evidence of the
    defect, and the repair rule's own test would have nothing to test against."""
    load_all(seeded, raw_root, lineage_env)

    assert (
        scalar(
            seeded,
            "select count(*) from staging.eia_plays where not ST_IsValid(geom)",
        )
        == INVALID_PLAYS
    )
    assert (
        scalar(
            seeded,
            "select count(*) from canonical.basin_boundaries where not ST_IsValid(geom)",
        )
        == 0
    )
