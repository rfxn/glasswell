from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
import shapefile
from shapely import wkb

from glasswell.ingest.nd_gis import api10_from_linekey, parse_linekey
from glasswell.ingest.shapefile import UnknownProjection, ZippedShapefile

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
