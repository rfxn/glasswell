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

LAYERS = ("OGD_Wells", "OGD_Horizontals_Line", "OGD_DrillingSpacingUnits", "OGD_Directionals")
RECORD_COUNT = 300
BASE_URL = "https://gis.dmr.nd.gov/downloads/oilgas/shapefile"

# Whole `(api_wellno, well_sub)` segments, never a partial one: a segment cut mid-string would
# be a bore path this repository invented. Each row is here for what it lets a test assert, and
# SOURCE.md carries the same table with the counts.
SURVEY_SEGMENTS: tuple[tuple[str, str], ...] = (
    ("33007011660000", "DIR"),   # in OGD_Wells_300, so the mart tier gets real traces
    ("33053019370000", "DIR"),   # in OGD_Wells_300
    ("33053021020000", "DIR"),   # in OGD_Wells_300
    ("33007003310000", "STK1"),  # inclination 436 deg at station 8 of 199
    ("33007006800000", "DIR"),   # four stations whose TVD exceeds their own measured depth
    ("33075014950000", "DIR"),   # azimuth 437 deg, and it is the deepest station of the 150
    ("33075011520000", "DIR"),   # the shortest segment in the file: two stations
    ("33105903760000", "STK1"),  # sidetracks and a vertical with no DIR segment at all
    ("33105903760000", "STK2"),
    ("33105903760000", "STK3"),
    ("33105903760000", "VERT"),
    ("33089006260000", "STK4"),  # the only STK4 upstream; completes the well_sub vocabulary
    ("33053105500000", "VERT"),  # deliberately left out of every well fixture: the orphan case
)


def open_layer(archive: Path, stem: str | None = None) -> tuple[shapefile.Reader, bytes]:
    """`stem` picks one shapefile where an archive ships several: OGD_Directionals.zip carries
    the station points and ND's own per-segment line rendering of them under two stems."""
    with zipfile.ZipFile(archive) as bundle:
        names = [name for name in bundle.namelist() if stem is None or Path(name).stem == stem]
        members = {name.rsplit(".", 1)[-1].lower(): name for name in names}
        reader = shapefile.Reader(
            shp=io.BytesIO(bundle.read(members["shp"])),
            shx=io.BytesIO(bundle.read(members["shx"])),
            dbf=io.BytesIO(bundle.read(members["dbf"])),
        )
        return reader, bundle.read(members["prj"])


def write_subset(
    reader: shapefile.Reader,
    prj: bytes,
    ordinals: Sequence[int],
    destination: Path,
    member_stem: str | None = None,
) -> None:
    """`member_stem` keeps the upstream member names when the archive name says how it was
    cut: the survey loader selects its layer by stem suffix, so the stem is part of the read."""
    inner = member_stem or destination.stem
    with tempfile.TemporaryDirectory() as scratch:
        stem = Path(scratch) / inner
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
                bundle.write(stem.with_suffix(extension), inner + extension)


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


def survey_ordinals(reader: shapefile.Reader) -> list[int]:
    """Every station of every segment in SURVEY_SEGMENTS, in upstream order.

    Upstream order is ascending measured depth within a segment, so keeping it means the
    fixture cannot accidentally prove that the loader sorts when the file already was sorted.
    """
    wanted = set(SURVEY_SEGMENTS)
    selected = []
    for ordinal in range(len(reader)):
        row = reader.record(ordinal)
        if (row["api_wellno"].strip(), row["well_sub"].strip()) in wanted:
            selected.append(ordinal)
    return selected


def cut(downloads: Path, destination: Path) -> dict[str, int]:
    destination.mkdir(parents=True, exist_ok=True)
    laterals, lateral_prj = open_layer(downloads / "OGD_Horizontals_Line.zip")
    lateral_rows = list(range(RECORD_COUNT))
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

    surveys, surveys_prj = open_layer(downloads / "OGD_Directionals.zip", stem="OGD_Directionals")
    survey_rows = survey_ordinals(surveys)
    write_subset(
        surveys,
        surveys_prj,
        survey_rows,
        destination / "OGD_Directionals_stations.zip",
        member_stem="OGD_Directionals",
    )
    return {
        **dict.fromkeys(LAYERS[:3], RECORD_COUNT),
        "OGD_Directionals": len(survey_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downloads", type=Path, default=Path("/tmp"))
    parser.add_argument("--destination", type=Path, default=Path(__file__).parent)
    arguments = parser.parse_args()
    for layer, count in cut(arguments.downloads, arguments.destination).items():
        print(f"{layer}: {count} records <- {BASE_URL}/{layer}.zip")


if __name__ == "__main__":
    main()
