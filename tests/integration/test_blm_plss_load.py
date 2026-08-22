"""The land-grid pipeline end to end: paginated fetch, staging, promotion, mart, tiles.

Everything runs off the fixture extract through the FakeArcGis double — never the live
service (SB-01 §1.2.1 politeness; the full pull belongs to the deployed ingest timer).
"""

from __future__ import annotations

import stat

import pytest

from glasswell.ingest.arcgis import PageWalkIncomplete
from glasswell.ingest.blm_plss import load_layer
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.land_units import refresh_land_units
from glasswell.seed import seed_all
from tests.integration.test_marts_nd import covering_tile, extent_of, rows, scalar
from tests.support.arcgis_fake import SERVICE_PATH, FakeArcGis
from tests.support.mvt import attribute_keys, feature_count, layer_name, layers

SERVICE_URL = f"https://gis.blm.gov{SERVICE_PATH}"
TOWNSHIPS = 2
SECTIONS = 4


@pytest.fixture
def seeded(db):
    seed_all(db)
    db.commit()
    return db


def load(db, raw_root, lineage_env, layer: str, *, fake: FakeArcGis | None = None):
    fake = fake or FakeArcGis()
    with lineage_session(
        recorder=PostgresRecorder(db), environment=lineage_env
    ), fake.client() as client:
        result = load_layer(
            db,
            layer,
            service_url=SERVICE_URL,
            raw_root=raw_root,
            client=client,
            page_size=2,
            page_delay_seconds=0.0,
        )
    db.commit()
    return result


def load_all(db, raw_root, lineage_env):
    return (
        load(db, raw_root, lineage_env, "townships"),
        load(db, raw_root, lineage_env, "sections"),
    )


def test_both_layers_promote_with_full_lineage(seeded, raw_root, lineage_env):
    townships, sections = load_all(seeded, raw_root, lineage_env)
    assert townships.staged_rows == TOWNSHIPS
    assert townships.promoted_rows == TOWNSHIPS
    assert sections.staged_rows == SECTIONS
    assert sections.promoted_rows == SECTIONS
    assert all(count == 0 for count in townships.quarantined.values())
    assert all(count == 0 for count in sections.quarantined.values())

    assert scalar(seeded, "select count(*) from canonical.land_units") == TOWNSHIPS + SECTIONS
    assert (
        scalar(
            seeded,
            "select count(*) from canonical.land_units"
            " where unit_type = 'section' and frstdivid is null",
        )
        == 0
    )
    # Every section's parent township is present, by join and not by substring.
    assert (
        scalar(
            seeded,
            "select count(*) from canonical.land_units section"
            " where section.unit_type = 'section' and not exists"
            "  (select 1 from canonical.land_units township"
            "    where township.land_unit_id = section.plssid"
            "      and township.unit_type = 'township')",
        )
        == 0
    )
    labels = {
        label
        for (label,) in rows(
            seeded,
            "select label from canonical.land_units where unit_type = 'township'",
        )
    }
    assert labels == {"152N 95W", "153N 95W"}
    assert (
        scalar(seeded, "select distinct ST_SRID(geom) from canonical.land_units") == 4326
    )

    for result in (townships, sections):
        operations = {
            operation
            for (operation,) in rows(
                seeded,
                "select operation from lineage.derivations"
                " where derivation_id in (%s, %s)",
                (result.parse_derivation_id, result.promote_derivation_id),
            )
        }
        assert operations == {"stage.parse", "canonical.promote"}
        input_refs = {
            ref
            for (ref,) in rows(
                seeded,
                "select ref_id from lineage.derivation_inputs where derivation_id = %s",
                (result.promote_derivation_id,),
            )
        }
        assert result.parse_derivation_id in input_refs
        assert result.manifest_id in input_refs
        assert (
            scalar(
                seeded,
                "select count(*) from lineage.vintages where source_id = %s",
                (result.source_id,),
            )
            == 1
        )


def test_the_manifest_records_the_h11_acquisition_shape(seeded, raw_root, lineage_env):
    result = load(seeded, raw_root, lineage_env, "townships")
    method, media_type, params = rows(
        seeded,
        "select acquisition_method, media_type, acquisition_params"
        " from lineage.manifests where manifest_id = %s",
        (result.manifest_id,),
    )[0]
    assert method == "arcgis_rest_paginate"
    assert media_type == "application/x-ndjson"
    assert set(params) == {
        "service_url", "layer_id", "layer_json_sha256", "service_version", "where", "out_sr",
        "format", "result_record_count", "order_by", "pages", "count_before", "count_after",
        "features_written",
    }
    assert params["count_before"] == params["count_after"] == params["features_written"]
    assert params["where"] == "PLSSID LIKE 'ND%'"
    # Self-stamped vintage: a service publishes none, so upstream_mtime stays null.
    assert (
        scalar(
            seeded,
            "select upstream_mtime from lineage.manifests where manifest_id = %s",
            (result.manifest_id,),
        )
        is None
    )


def test_the_sealed_artifact_verifies_from_its_own_directory(seeded, raw_root, lineage_env):
    result = load(seeded, raw_root, lineage_env, "townships")
    storage = scalar(
        seeded,
        "select storage_uri from lineage.manifests where manifest_id = %s",
        (result.manifest_id,),
    )
    from pathlib import Path

    payload = Path(storage)
    directory = payload.parent
    assert (directory / "manifest.json").exists()
    assert (directory / "MANIFEST.sha256").exists()
    assert stat.S_IMODE(payload.stat().st_mode) == 0o444


def test_reloading_identical_bytes_is_a_recorded_noop(seeded, raw_root, lineage_env):
    first = load(seeded, raw_root, lineage_env, "townships")
    second = load(seeded, raw_root, lineage_env, "townships")
    assert second.unchanged
    assert second.manifest_id == first.manifest_id
    assert second.staged_rows == 0
    assert (
        scalar(
            seeded,
            "select count(*) from lineage.manifests where source_id = 'blm_plss_townships'",
        )
        == 1
    )
    assert scalar(seeded, "select count(*) from canonical.land_units") == TOWNSHIPS


class RevisedArcGis(FakeArcGis):
    """The same service, same keys, new bytes: every feature gains one extra property, so
    the assembled artifact hashes to a new manifest while every land_unit_id conflicts."""

    def features(self, layer_id: int) -> list[dict]:
        return [
            {**feature, "properties": {**feature["properties"], "DR89_REVISION": "1"}}
            for feature in super().features(layer_id)
        ]


def test_a_revised_pull_whose_rows_all_conflict_is_detected_not_silently_promoted(
    seeded, raw_root, lineage_env
):
    """DR-89: land_units is keyed on land_unit_id alone, so a revised monthly pull whose
    rows all conflict owned nothing and was invisible to the canonical-ownership guard —
    re-staged and re-promoted on every poll with the refusal never recorded."""
    first = load(seeded, raw_root, lineage_env, "townships")
    second = load(seeded, raw_root, lineage_env, "townships", fake=RevisedArcGis())

    assert second.manifest_id != first.manifest_id
    assert second.unchanged is False
    assert second.staged_rows == TOWNSHIPS
    assert second.promoted_rows == 0
    assert second.quarantined["key_collision"] == TOWNSHIPS
    assert scalar(seeded, "select count(*) from canonical.land_units") == TOWNSHIPS
    assert (
        scalar(
            seeded,
            "select count(*) from lineage.quarantine_rows"
            " where reason_code = 'key_collision' and stage = 'join'"
            " and first_seen_manifest_id = %s",
            (second.manifest_id,),
        )
        == TOWNSHIPS
    )
    assert rows(
        seeded,
        "select rows_examined, rows_appended from lineage.vintages"
        " where source_id = 'blm_plss_townships'",
    ) == [(TOWNSHIPS, TOWNSHIPS)], "a pass that appended nothing must not inflate the ledger"

    third = load(seeded, raw_root, lineage_env, "townships", fake=RevisedArcGis())
    assert third.unchanged is True, "a detected all-conflict revision reloads as unchanged"
    assert scalar(seeded, "select count(*) from canonical.land_units") == TOWNSHIPS


class RevisedWithOrphanArcGis(RevisedArcGis):
    """The revision plus one section whose township is nowhere. The orphan pins the
    township-exists half of the refused mirror: it must stay an orphan_fk fact and never
    be double-counted into the key_collision set."""

    ORPHAN_PLSSID = "ND051700N0900W0"
    ORPHAN_FRSTDIVID = "ND051700N0900W0SN010"

    def features(self, layer_id: int) -> list[dict]:
        features = super().features(layer_id)
        if layer_id == 2:
            template = features[0]
            features.append(
                {
                    **template,
                    "properties": {
                        **template["properties"],
                        "PLSSID": self.ORPHAN_PLSSID,
                        "FRSTDIVID": self.ORPHAN_FRSTDIVID,
                        "FRSTDIVNO": "1",
                        "FRSTDIVLAB": "1",
                    },
                }
            )
        return features


def test_a_revised_sections_pull_whose_rows_all_conflict_is_detected_not_silently_promoted(
    seeded, raw_root, lineage_env
):
    """DR-89 C1: pins _REFUSED_SECTIONS to _INSERT_SECTIONS' admission clause. The refused
    set must be exactly the rows the insert would have attempted — occurrence = 1 with a
    parent township present — so mutating either half of the mirror breaks this count:
    flipping the occurrence test empties it, dropping the exists test sweeps the orphan in."""
    load(seeded, raw_root, lineage_env, "townships")
    first = load(seeded, raw_root, lineage_env, "sections")
    admitted = first.promoted_rows
    assert admitted == SECTIONS

    second = load(seeded, raw_root, lineage_env, "sections", fake=RevisedWithOrphanArcGis())

    assert second.manifest_id != first.manifest_id
    assert second.unchanged is False
    assert second.staged_rows == SECTIONS + 1
    assert second.promoted_rows == 0
    assert second.quarantined["orphan_fk"] == 1
    assert second.quarantined["key_collision"] == admitted
    assert (
        scalar(
            seeded,
            "select count(*) from lineage.quarantine_rows"
            " where reason_code = 'key_collision' and stage = 'join'"
            " and first_seen_manifest_id = %s",
            (second.manifest_id,),
        )
        == admitted
    )
    assert scalar(
        seeded,
        "select count(*) from lineage.quarantine_rows"
        " where reason_code = 'key_collision' and row_payload ->> 'frstdivid' = %s",
        (RevisedWithOrphanArcGis.ORPHAN_FRSTDIVID,),
    ) == 0, "the orphan belongs to orphan_fk, never to the refused set"
    assert scalar(
        seeded, "select count(*) from canonical.land_units where unit_type = 'section'"
    ) == admitted

    third = load(seeded, raw_root, lineage_env, "sections", fake=RevisedWithOrphanArcGis())
    assert third.unchanged is True, "a detected all-conflict revision reloads as unchanged"


def test_sections_without_townships_are_quarantined_as_orphans(seeded, raw_root, lineage_env):
    result = load(seeded, raw_root, lineage_env, "sections")
    assert result.promoted_rows == 0
    assert result.quarantined["orphan_fk"] == SECTIONS
    assert (
        scalar(
            seeded,
            "select count(*) from lineage.quarantine_rows"
            " where source_id = 'blm_plss_sections' and reason_code = 'orphan_fk'",
        )
        == SECTIONS
    )
    assert scalar(seeded, "select count(*) from canonical.land_units") == 0


def test_a_partial_walk_writes_no_manifest_and_says_why(seeded, raw_root, lineage_env):
    fake = FakeArcGis(count_override={1: 5})
    with pytest.raises(PageWalkIncomplete):
        load(seeded, raw_root, lineage_env, "townships", fake=fake)
    seeded.commit()
    assert (
        scalar(
            seeded,
            "select count(*) from lineage.manifests where source_id = 'blm_plss_townships'",
        )
        == 0
    )
    reasons = [
        payload["reason"]
        for (payload,) in rows(
            seeded,
            "select payload from lineage.audit_events where event_type = 'raw.fetch_failed'",
        )
    ]
    assert "page_walk_incomplete" in reasons


def test_the_mart_serves_both_grains_as_decodable_tiles(seeded, raw_root, lineage_env):
    load_all(seeded, raw_root, lineage_env)
    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env):
        refresh = refresh_land_units(seeded)
    seeded.commit()
    assert refresh.row_counts["land_units_tile"] == TOWNSHIPS + SECTIONS
    assert refresh.layers == ("land_townships", "land_sections")

    zoom, x, y = covering_tile(extent_of(seeded, "marts.land_units_tile"))
    for function, expected in (("land_townships", TOWNSHIPS), ("land_sections", SECTIONS)):
        tile = scalar(seeded, f"select marts.{function}(%s, %s, %s)", (zoom, x, y))
        assert tile is not None, f"{function} returned no tile at z{zoom}"
        decoded = {layer_name(layer): layer for layer in layers(bytes(tile))}
        # Two sublayers since M2-3/F1: the polygons, and one anchor point per unit for the
        # symbol layer to bind to — a tile containing every unit carries every label once.
        assert set(decoded) == {function, f"{function}_label"}
        assert feature_count(decoded[function]) == expected
        assert feature_count(decoded[f"{function}_label"]) == expected
        assert set(attribute_keys(decoded[function])) == {
            "land_unit_id", "unit_type", "plssid", "label", "derivation_id",
        }
    # Every served figure carries a derivation handle: the tile rows carry the refresh's.
    assert (
        scalar(seeded, "select distinct derivation_id from marts.land_units_tile")
        == refresh.derivation_id
    )


def test_a_label_crossing_a_tile_seam_is_emitted_exactly_once(seeded, raw_root, lineage_env):
    """The F1 defect: a polygon split across tiles grew one label per fragment. The anchor
    point is owned by exactly one tile, so the sum over any tiling is the unit count."""
    load_all(seeded, raw_root, lineage_env)
    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env):
        refresh_land_units(seeded)
    seeded.commit()

    zoom, x, y = covering_tile(extent_of(seeded, "marts.land_units_tile"))
    # Two zooms deeper: sixteen descendant tiles, so the fixture polygons are fragmented
    # across seams while every anchor still lands in exactly one descendant.
    children = [
        (zoom + 2, 4 * x + dx, 4 * y + dy) for dx in range(4) for dy in range(4)
    ]
    for function, expected in (("land_townships", TOWNSHIPS), ("land_sections", SECTIONS)):
        fragments = 0
        labels = 0
        for z, cx, cy in children:
            tile = scalar(seeded, f"select marts.{function}(%s, %s, %s)", (z, cx, cy))
            if tile is None:
                continue
            named = {layer_name(layer): layer for layer in layers(bytes(tile))}
            fragments += feature_count(named.get(function, b""))
            labels += feature_count(named.get(f"{function}_label", b""))
        assert fragments >= expected
        # A township spans several z+2 tiles, so the polygon side genuinely duplicates —
        # which is exactly what the anchor side must not do.
        if function == "land_townships":
            assert fragments > expected, "the tiling did not fragment the polygons"
        assert labels == expected
