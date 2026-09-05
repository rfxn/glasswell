from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
import shapefile
from shapely import wkb

from glasswell.ingest.nd_gis import api10_from_linekey, parse_linekey
from glasswell.ingest.shapefile import MalformedArchive, UnknownProjection, ZippedShapefile

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "nd_gis"
WELLS = FIXTURES / "OGD_Wells_300.zip"
LATERALS = FIXTURES / "OGD_Horizontals_Line_300.zip"
UNITS = FIXTURES / "OGD_DrillingSpacingUnits_300.zip"

WELL_FIELDS = (
    "fileno", "api_no", "operator", "well_name", "td", "spud_date", "field_name", "qq",
    "sec", "twp", "rng", "feet_ns", "fnsl", "feet_ew", "fewl", "latitude", "longitude",
    "well_type", "status", "api", "County", "symbol",
)
ND_PRJ = (
    'GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",'
    'SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],'
    'UNIT["Degree",0.0174532925199433]]'
)


def write_zip(destination: Path, *, shapes: int, prj: str | None, null_shape: bool = False) -> Path:
    buffers = {extension: io.BytesIO() for extension in ("shp", "shx", "dbf")}
    writer = shapefile.Writer(**buffers)
    writer.field("name", "C", 20)
    for index in range(shapes):
        writer.record(f"row-{index}")
        if null_shape and index == 0:
            writer.null()
        else:
            writer.point(-103.5 + index, 48.0)
    writer.close()
    with zipfile.ZipFile(destination, "w") as bundle:
        for extension, buffer in buffers.items():
            bundle.writestr(f"layer.{extension}", buffer.getvalue())
        if prj is not None:
            bundle.writestr("layer.prj", prj)
    return destination


def write_encoded_zip(destination: Path, *, name: str, encoding: str, layers: int = 1) -> Path:
    """An archive whose DBF holds `name` in `encoding`, optionally twinned as `layer_p`."""
    stems = ["layer"] + [f"layer_p{index}" for index in range(1, layers)]
    with zipfile.ZipFile(destination, "w") as bundle:
        for stem in stems:
            buffers = {extension: io.BytesIO() for extension in ("shp", "shx", "dbf")}
            writer = shapefile.Writer(**buffers, encoding=encoding)
            writer.field("well_nm", "C", 40)
            writer.record(name if stem == "layer" else f"{name}-twin")
            writer.point(-104.5, 47.9)
            writer.close()
            for extension, buffer in buffers.items():
                bundle.writestr(f"{stem}.{extension}", buffer.getvalue())
            bundle.writestr(f"{stem}.prj", ND_PRJ)
    return destination


def test_a_windows_1252_dbf_reads_when_the_archive_declares_its_encoding(tmp_path: Path):
    """MBOGC ships cp1252; pyshp's utf-8 default raises partway through iteration."""
    archive = write_encoded_zip(tmp_path / "cp1252.zip", name="Blasé 15-10", encoding="cp1252")
    with ZippedShapefile(archive, encoding="cp1252") as layer:
        records = list(layer)
    assert [record.attributes["well_nm"] for record in records] == ["Blasé 15-10"]


def test_an_undeclared_encoding_keeps_the_strict_utf8_default(tmp_path: Path):
    """The default is unchanged, so ND/TX/NM read exactly as before this parameter existed."""
    archive = write_encoded_zip(tmp_path / "undeclared.zip", name="Blasé 15-10", encoding="cp1252")
    with pytest.raises(shapefile.ShapefileException), ZippedShapefile(archive) as layer:
        list(layer)


def write_named_zip(destination: Path, *stems: str) -> Path:
    """One point layer per stem, named exactly as given -- separators and all."""
    with zipfile.ZipFile(destination, "w") as bundle:
        for stem in stems:
            buffers = {extension: io.BytesIO() for extension in ("shp", "shx", "dbf")}
            writer = shapefile.Writer(**buffers)
            writer.field("name", "C", 40)
            writer.record(stem)
            writer.point(-104.5, 40.1)
            writer.close()
            for extension, buffer in buffers.items():
                bundle.writestr(f"{stem}.{extension}", buffer.getvalue())
            bundle.writestr(f"{stem}.prj", ND_PRJ)
    return destination


def test_the_member_ecmc_actually_ships_is_selected_through_its_separators(tmp_path: Path):
    """Measured 2026-09-04 20:06Z on VM 111: DIRECTIONAL_BOTTOMHOLE_LOCATIONS_SHP.ZIP carries
    `Directional_Bottomhole_Locations.{dbf,prj,shp,shx}` and the layer is registered as
    `directionalbottomholelocations`, so an endswith over the raw stem matched nothing and the
    staging raised MalformedArchive after the wells layer had already been staged and recorded.

    The suffix is a name, not a spelling: the regulator's punctuation is not a decision anybody
    made here, so both sides are compared with case and separators removed.
    """
    archive = write_named_zip(tmp_path / "bh.zip", "Directional_Bottomhole_Locations")

    with ZippedShapefile(archive, layer_suffix="directionalbottomholelocations") as layer:
        assert [record.attributes["name"] for record in layer] == [
            "Directional_Bottomhole_Locations"
        ]


def test_the_normalised_match_still_tells_two_twinned_layers_apart(tmp_path: Path):
    """The looser match must not make every layer match every suffix: MT ships a geographic
    layer and a StatePlane twin under one zip and the suffix is the only thing between them."""
    archive = write_named_zip(tmp_path / "twins.zip", "WellPaths", "WellPaths_P")

    with ZippedShapefile(archive, layer_suffix="WellPaths") as layer:
        assert [record.attributes["name"] for record in layer] == ["WellPaths"]
    with ZippedShapefile(archive, layer_suffix="wellpaths_p") as twin:
        assert [record.attributes["name"] for record in twin] == ["WellPaths_P"]


def test_a_member_that_is_absent_is_still_a_refusal_naming_the_selector(tmp_path: Path):
    """Normalising is not the same as guessing: a suffix that names no member still refuses."""
    archive = write_named_zip(tmp_path / "absent.zip", "Directional_Lines")

    with pytest.raises(MalformedArchive, match="matching 'surfaceholelocations'"):
        ZippedShapefile(archive, layer_suffix="surfaceholelocations")


def test_a_layer_suffix_selects_one_of_two_twinned_layers(tmp_path: Path):
    """Both MT archives ship a geographic layer and a StatePlane twin under one zip."""
    archive = write_encoded_zip(tmp_path / "twinned.zip", name="Well", encoding="cp1252", layers=2)
    with ZippedShapefile(archive, layer_suffix="layer", encoding="cp1252") as layer:
        assert [record.attributes["well_nm"] for record in layer] == ["Well"]
    with ZippedShapefile(archive, layer_suffix="layer_p1", encoding="cp1252") as twin:
        assert [record.attributes["well_nm"] for record in twin] == ["Well-twin"]


def test_the_wells_fixture_reads_three_hundred_records_with_its_fields_in_order():
    with ZippedShapefile(WELLS) as layer:
        assert layer.fields == WELL_FIELDS
        records = list(layer)
    assert len(records) == 300
    assert records[0].ordinal == 0
    assert records[0].attributes["api"] == "33043000020000"
    assert records[0].attributes["status"] == "DRY"


def test_the_shipped_prj_resolves_to_nad83():
    for fixture in (WELLS, LATERALS, UNITS):
        with ZippedShapefile(fixture) as layer:
            assert layer.source_epsg == 4269


def test_an_absent_prj_raises_rather_than_defaulting_to_4326(tmp_path: Path):
    archive = write_zip(tmp_path / "no_prj.zip", shapes=2, prj=None)
    with pytest.raises(UnknownProjection, match=r"no \.prj"), ZippedShapefile(archive) as layer:
        layer.source_epsg  # noqa: B018 — the property is the behaviour under test


def test_an_unrecognised_prj_raises_rather_than_guessing(tmp_path: Path):
    archive = write_zip(tmp_path / "odd_prj.zip", shapes=1, prj='LOCAL_CS["mystery"]')
    with pytest.raises(UnknownProjection), ZippedShapefile(archive) as layer:
        layer.source_epsg  # noqa: B018 — the property is the behaviour under test


def test_members_are_located_by_extension_not_by_assumed_filename(tmp_path: Path):
    archive = write_zip(tmp_path / "renamed.zip", shapes=3, prj=ND_PRJ)
    with zipfile.ZipFile(archive) as source:
        payloads = {name: source.read(name) for name in source.namelist()}
    renamed = tmp_path / "odd_names.zip"
    with zipfile.ZipFile(renamed, "w") as bundle:
        for name, payload in payloads.items():
            bundle.writestr(f"nested/dir/UNRELATED_NAME.{name.rsplit('.', 1)[-1].upper()}", payload)
    with ZippedShapefile(renamed) as layer:
        assert layer.source_epsg == 4269
        assert len(list(layer)) == 3


def test_geometry_round_trips_through_wkb():
    with ZippedShapefile(LATERALS) as layer:
        record = next(iter(layer))
    assert record.geometry is not None
    assert record.geometry.geom_type == "LineString"
    assert wkb.loads(record.geometry.wkb).equals(record.geometry)


def test_a_null_shape_is_flagged_and_still_yielded(tmp_path: Path):
    archive = write_zip(tmp_path / "with_null.zip", shapes=3, prj=ND_PRJ, null_shape=True)
    with ZippedShapefile(archive) as layer:
        records = list(layer)
    assert len(records) == 3
    assert records[0].geometry is None
    assert records[0].is_empty is True
    assert [record.is_empty for record in records[1:]] == [False, False]


def test_the_lateral_fixture_carries_a_multi_lateral_well():
    with ZippedShapefile(LATERALS) as layer:
        keys = [record.attributes["linekey"] for record in layer]
    assert keys[0] == "33011003910000_LAT1"
    assert keys[1] == "33011003910000_LAT2"
    assert api10_from_linekey(keys[0]) == api10_from_linekey(keys[1])


def test_a_linekey_parses_to_an_api10_a_segment_kind_and_an_ordinal():
    parsed = parse_linekey("33011003910000_LAT1")
    assert parsed.api14 == "33011003910000"
    assert parsed.api10 == "3301100391"
    assert parsed.segment == "LAT"
    assert parsed.ordinal == 1
    assert api10_from_linekey("33011003910000_LAT1") == "3301100391"
    assert parse_linekey("33011003910000_LAT2").ordinal == 2


@pytest.mark.parametrize(
    ("linekey", "segment", "ordinal"),
    [
        ("33053016580000_STK1", "STK", 1),
        ("33053016580000_VERT", "VERT", None),
        ("33011004000000_LAT12", "LAT", 12),
    ],
)
def test_the_layer_carries_segments_that_are_not_lateral_centrelines(linekey, segment, ordinal):
    parsed = parse_linekey(linekey)
    assert parsed.segment == segment
    assert parsed.ordinal == ordinal
    assert parsed.is_lateral is (segment == "LAT")


@pytest.mark.parametrize("linekey", ["", "3301100391", "33011003910000", "notanapi_LAT1"])
def test_an_unparseable_linekey_raises_rather_than_returning_a_wrong_key(linekey):
    with pytest.raises(ValueError, match="linekey"):
        parse_linekey(linekey)


def test_the_spacing_unit_fixture_reads_polygons():
    with ZippedShapefile(UNITS) as layer:
        records = list(layer)
    assert len(records) == 300
    assert records[0].geometry.geom_type in {"Polygon", "MultiPolygon"}
    assert records[0].attributes["mapsymbol"] == "1280SPC"


def test_a_suffix_that_names_two_layers_refuses_instead_of_taking_the_first(tmp_path: Path):
    """H-4. `endswith` over a normalised stem admits a decoy, and ZIP order decided which one
    won. The Colorado rows name one exact member, so a second candidate is a source that grew a
    layer -- something to read, not a tie to break."""
    archive = write_named_zip(
        tmp_path / "decoy.zip", "Directional_Lines", "Historic_Directional-Lines"
    )

    with pytest.raises(MalformedArchive) as refusal:
        ZippedShapefile(archive, layer_suffix="directionallines")

    message = str(refusal.value)
    assert "2 members matching 'directionallines'" in message
    assert "Directional_Lines" in message
    assert "Historic_Directional-Lines" in message


def test_the_ambiguity_refusal_states_the_requirement_instead_of_citing_a_rule(tmp_path: Path):
    """H-16. `layer_suffix` is also how nd_gis, mt_gis, tx_gis and eia_boundaries pick a member,
    and no conformance row names one for any of them, so "the rule names one" sent an operator
    looking for a row that does not exist. The requirement is the reader's, and it says so."""
    archive = write_named_zip(tmp_path / "nd.zip", "Wells", "Historic_Wells")

    with pytest.raises(MalformedArchive) as refusal:
        ZippedShapefile(archive, layer_suffix="wells")

    message = str(refusal.value)
    assert "a suffix must select exactly one" in message
    assert "rule" not in message


def test_one_matching_layer_beside_others_that_do_not_match_still_reads(tmp_path: Path):
    """The refusal is about ambiguity, not about company: an archive shipping several layers
    reads the one its suffix names."""
    archive = write_named_zip(
        tmp_path / "many.zip", "Directional_Lines", "Directional_Bottomhole_Locations", "Wells"
    )

    with ZippedShapefile(archive, layer_suffix="directionallines") as layer:
        assert [record.attributes["name"] for record in layer] == ["Directional_Lines"]
