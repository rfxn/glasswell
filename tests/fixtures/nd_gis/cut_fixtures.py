"""Cut the checked-in ND GIS fixtures from the real regulator downloads (DIR-10).

    python tests/fixtures/nd_gis/cut_fixtures.py --downloads /tmp

Truncation only: no attribute value is edited, and the .prj is copied byte-for-byte
because the datum rule reads it.
"""

from __future__ import annotations

import argparse
import io
import tempfile
import zipfile
from collections.abc import Sequence
from pathlib import Path

import shapefile

LAYERS = ("OGD_Wells", "OGD_Horizontals_Line", "OGD_DrillingSpacingUnits")
RECORD_COUNT = 300
BASE_URL = "https://gis.dmr.nd.gov/downloads/oilgas/shapefile"


def open_layer(archive: Path) -> tuple[shapefile.Reader, bytes]:
    with zipfile.ZipFile(archive) as bundle:
        members = {name.rsplit(".", 1)[-1].lower(): name for name in bundle.namelist()}
        reader = shapefile.Reader(
            shp=io.BytesIO(bundle.read(members["shp"])),
            shx=io.BytesIO(bundle.read(members["shx"])),
            dbf=io.BytesIO(bundle.read(members["dbf"])),
        )
        return reader, bundle.read(members["prj"])


def write_subset(
    reader: shapefile.Reader, prj: bytes, ordinals: Sequence[int], destination: Path
) -> None:
    with tempfile.TemporaryDirectory() as scratch:
        stem = Path(scratch) / destination.stem
        writer = shapefile.Writer(target=str(stem), shapeType=reader.shapeType)
        writer.fields = reader.fields[1:]
        for ordinal in ordinals:
            record = reader.shapeRecord(ordinal)
            writer.record(*list(record.record))
            writer.shape(record.shape)
        writer.close()
        stem.with_suffix(".prj").write_bytes(prj)
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for extension in (".shp", ".shx", ".dbf", ".prj"):
                bundle.write(stem.with_suffix(extension), destination.stem + extension)


def lateral_ordinals(reader: shapefile.Reader) -> list[int]:
    """The head of the file: records 0 and 1 are the documented _LAT1/_LAT2 pair."""
    return list(range(RECORD_COUNT))


def well_ordinals(reader: shapefile.Reader, api10s: set[str]) -> list[int]:
    """Every well the lateral fixture references, one well per reported status, then the head."""
    records = [reader.record(ordinal) for ordinal in range(len(reader))]
    selected = {ordinal for ordinal, row in enumerate(records) if row["api"][:10] in api10s}
    first_of_status: dict[str, int] = {}
    for ordinal, row in enumerate(records):
        first_of_status.setdefault(row["status"], ordinal)
    selected |= set(first_of_status.values())
    for ordinal in range(len(records)):
        if len(selected) >= RECORD_COUNT:
            break
        selected.add(ordinal)
    return sorted(selected)[:RECORD_COUNT]


def cut(downloads: Path, destination: Path) -> dict[str, int]:
    destination.mkdir(parents=True, exist_ok=True)
    laterals, lateral_prj = open_layer(downloads / "OGD_Horizontals_Line.zip")
    lateral_rows = lateral_ordinals(laterals)
    api10s = {laterals.record(ordinal)["linekey"][:10] for ordinal in lateral_rows}
    write_subset(
        laterals, lateral_prj, lateral_rows, destination / "OGD_Horizontals_Line_300.zip"
    )

    wells, wells_prj = open_layer(downloads / "OGD_Wells.zip")
    write_subset(wells, wells_prj, well_ordinals(wells, api10s), destination / "OGD_Wells_300.zip")

    units, units_prj = open_layer(downloads / "OGD_DrillingSpacingUnits.zip")
    write_subset(
        units,
        units_prj,
        list(range(RECORD_COUNT)),
        destination / "OGD_DrillingSpacingUnits_300.zip",
    )
    return {layer: RECORD_COUNT for layer in LAYERS}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downloads", type=Path, default=Path("/tmp"))
    parser.add_argument("--destination", type=Path, default=Path(__file__).parent)
    arguments = parser.parse_args()
    for layer, count in cut(arguments.downloads, arguments.destination).items():
        print(f"{layer}: {count} records <- {BASE_URL}/{layer}.zip")


if __name__ == "__main__":
    main()
