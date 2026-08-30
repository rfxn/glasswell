"""Cut the checked-in EIA boundary fixtures from the real agency downloads (DIR-10).

    python tests/fixtures/eia_boundaries/cut_fixtures.py --downloads /tmp

Selection only: no attribute value is edited and no geometry is repaired — the two invalid
rings the fixture carries are the publisher's own, because cr_eia_geometry_repair_1 is what
they exercise. Each `.prj` is copied byte-for-byte because cr_eia_boundary_datum_1 reads it.
"""

from __future__ import annotations

import argparse
import io
import zipfile
from collections.abc import Sequence
from pathlib import Path

import shapefile

BASINS_ARCHIVE = "SedimentaryBasins_US_EIA.zip"
PLAYS_ARCHIVE = "TightOil_ShaleGas_IndividualPlays_Lower48_EIA.zip"
BASINS_MEMBER = "SedimentaryBasins_US_May2011_v2"

# Every basin a fixture play names, plus the three the Niobrara rows nearly name and do not
# resolve to (UINTA-PICEANCE, DENVER, NORTH PARK). Without them the refused near-matches in
# cr_eia_basin_link_1 would be unresolvable for the trivial reason that no candidate existed.
BASIN_NAMES = (
    "WILLISTON",
    "PERMIAN",
    "WESTERN GULF",
    "APPALACHIAN",
    "POWDER RIVER",
    "UINTA-PICEANCE",
    "DENVER",
    "NORTH PARK",
)

# Bakken and Three Forks carry the two invalid rings; Wolfcamp is the only feature with a
# SubBasin; Delaware overlaps Wolfcamp inside the Permian; Niobrara is the five-feature member
# whose Basin strings are four unresolved links and one resolved one.
PLAY_MEMBERS = (
    "ShalePlay_Bakken_Boundary_EIA_Aug2015_v2",
    "ShalePlay_ThreeForks_Boundary__EIA_Aug2015_v2",
    "ShalePlay_Wolfcamp_Boundary_EIA_201809",
    "ShalePlay_Delaware_Boundary_EIA_Aug2015_v2",
    "ShalePlay_Niobrara_Boundary_EIA_Aug2015_v2",
)


def open_member(archive: Path, stem: str) -> tuple[shapefile.Reader, bytes]:
    with zipfile.ZipFile(archive) as bundle:
        members = {
            name.rsplit(".", 1)[-1].lower(): name
            for name in bundle.namelist()
            if name.rsplit(".", 1)[0] == stem
        }
        reader = shapefile.Reader(
            shp=io.BytesIO(bundle.read(members["shp"])),
            shx=io.BytesIO(bundle.read(members["shx"])),
            dbf=io.BytesIO(bundle.read(members["dbf"])),
        )
        return reader, bundle.read(members["prj"])


def write_member(
    target: zipfile.ZipFile,
    stem: str,
    reader: shapefile.Reader,
    prj: bytes,
    keep: Sequence[int] | None,
) -> int:
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    written = 0
    with shapefile.Writer(shp=shp, shx=shx, dbf=dbf) as writer:
        writer.fields = reader.fields[1:]
        for ordinal, entry in enumerate(reader.iterShapeRecords()):
            if keep is not None and ordinal not in keep:
                continue
            writer.record(*entry.record)
            writer.shape(entry.shape)
            written += 1
    target.writestr(f"{stem}.shp", shp.getvalue())
    target.writestr(f"{stem}.shx", shx.getvalue())
    target.writestr(f"{stem}.dbf", dbf.getvalue())
    target.writestr(f"{stem}.prj", prj)
    return written


def cut_basins(downloads: Path, out: Path) -> int:
    reader, prj = open_member(downloads / BASINS_ARCHIVE, BASINS_MEMBER)
    keep = [
        ordinal
        for ordinal, entry in enumerate(reader.iterShapeRecords())
        if str(entry.record.as_dict()["NAME"]).strip() in BASIN_NAMES
    ]
    reader, prj = open_member(downloads / BASINS_ARCHIVE, BASINS_MEMBER)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        return write_member(target, BASINS_MEMBER, reader, prj, keep)


def cut_plays(downloads: Path, out: Path) -> int:
    written = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for stem in PLAY_MEMBERS:
            reader, prj = open_member(downloads / PLAYS_ARCHIVE, stem)
            written += write_member(target, stem, reader, prj, None)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cut the EIA boundary test fixtures.")
    parser.add_argument("--downloads", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent)
    arguments = parser.parse_args(argv)

    basins = arguments.out / "SedimentaryBasins_US_EIA_cut.zip"
    plays = arguments.out / "TightOil_ShaleGas_IndividualPlays_Lower48_EIA_cut.zip"
    print(f"{basins.name}: {cut_basins(arguments.downloads, basins)} features")
    print(f"{plays.name}: {cut_plays(arguments.downloads, plays)} features")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
