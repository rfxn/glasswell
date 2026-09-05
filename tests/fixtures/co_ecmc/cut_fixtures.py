"""Cut the Colorado fixtures from the live ECMC files, so every row in them is a real row.

Run against a scratch directory holding the four archives named below; it writes the sampled
fixtures beside this file. The cut is stated rather than random: every status code in the data,
both byte-identical duplicate pairs, every location-qualifier class, a multi-wellbore API-10,
and the well-months the production sample needs to exercise the dual write.

    python tests/fixtures/co_ecmc/cut_fixtures.py /path/to/scratch
"""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from collections import Counter
from pathlib import Path

import shapefile

HERE = Path(__file__).resolve().parent
HEADER_ARCHIVE = "WELLS_SHP.ZIP"
BOTTOMHOLE_ARCHIVE = "DIRECTIONAL_BOTTOMHOLE_LOCATIONS_SHP.ZIP"
LINES_ARCHIVE = "DIRECTIONAL_LINES_SHP.ZIP"
ROLLING = "monthly_prod.csv"

PRODUCTION_ROWS = 400
DIRECTIONAL_ROWS = 60


def _reader(archive: Path) -> tuple[shapefile.Reader, bytes, str]:
    """The layer, its projection, and the stem ECMC named the members with.

    The stem is carried out because it used to be dropped here and typed in again at the write:
    the cut wrote `DirectionalBottomholeLocations` while the archive ships
    `Directional_Bottomhole_Locations`, so the fixtures asserted a name this repository had
    invented and the suite was green on a selector that matched nothing live.
    """
    members = zipfile.ZipFile(archive)
    by_extension = {name.rsplit(".", 1)[-1].lower(): name for name in members.namelist()}
    reader = shapefile.Reader(
        shp=io.BytesIO(members.read(by_extension["shp"])),
        dbf=io.BytesIO(members.read(by_extension["dbf"])),
        shx=io.BytesIO(members.read(by_extension["shx"])),
    )
    stem = by_extension["shp"].rpartition(".")[0]
    return reader, members.read(by_extension["prj"]), stem


def _write(target: Path, reader: shapefile.Reader, prj: bytes, keep: list[int], stem: str) -> None:
    buffers = {suffix: io.BytesIO() for suffix in ("shp", "shx", "dbf")}
    writer = shapefile.Writer(**{f"{name}": handle for name, handle in buffers.items()})
    writer.fields = reader.fields[1:]
    for index in keep:
        entry = reader.shapeRecord(index)
        writer.record(*entry.record)
        writer.shape(entry.shape)
    writer.close()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for suffix, handle in buffers.items():
            archive.writestr(f"{stem}.{suffix}", handle.getvalue())
        archive.writestr(f"{stem}.prj", prj)


def cut_production(scratch: Path) -> set[str]:
    """The rows first: the header cut has to cover the wells the production sample names."""
    wanted: list[dict[str, str]] = []
    api10s: set[str] = set()
    completions: Counter[tuple[str, str, str]] = Counter()
    with (scratch / ROLLING).open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        month = f"{row['ReportYear']}-{row['ReportMonth']}"
        completions[(row["ApiCountyCode"], row["ApiSequenceNumber"], month)] += 1
    multi = {key[:2] for key, count in completions.items() if count > 1}
    single = {key[:2] for key, count in completions.items() if count == 1} - multi
    keep_keys = set(list(multi)[:12] + list(single)[:12])
    for row in rows:
        key = (row["ApiCountyCode"], row["ApiSequenceNumber"])
        if key in keep_keys and len(wanted) < PRODUCTION_ROWS:
            wanted.append(row)
            api10s.add("05" + key[0].zfill(3) + key[1].zfill(5))
    with (HERE / "monthly_prod_sample.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(wanted)
    return api10s


def cut_headers(scratch: Path, api10s: set[str]) -> None:
    reader, prj, stem = _reader(scratch / HEADER_ARCHIVE)
    fields = [field[0] for field in reader.fields[1:]]
    keep: list[int] = []
    by_status: Counter[str] = Counter()
    by_qualifier: Counter[str] = Counter()
    seen: dict[tuple, int] = {}
    duplicates: list[int] = []
    for index, record in enumerate(reader.iterRecords()):
        row = dict(zip(fields, record, strict=True))
        county = str(row["API_County"]).strip().zfill(3)
        api10 = "05" + county + str(row["API_Seq"]).strip().zfill(5)
        identity = (
            api10, row["Facil_Id"], row["Loc_ID"], row["Facil_Stat"],
            row["Latitude"], row["Longitude"],
        )
        if identity in seen:
            duplicates.extend([seen[identity], index])
            continue
        seen[identity] = index
        status = str(row["Facil_Stat"]).strip()
        qualifier = (str(row["Loc_Qual"]).strip().split(" ") or [""])[0].upper()
        wanted_here = (
            api10 in api10s or by_status[status] < 4 or by_qualifier[qualifier] < 4
        )
        if not wanted_here:
            continue
        keep.append(index)
        by_status[status] += 1
        by_qualifier[qualifier] += 1
    keep = sorted(set(keep) | set(duplicates))
    _write(HERE / "Wells_sample.zip", reader, prj, keep, stem)


def cut_directional(scratch: Path, archive: str, target: str) -> None:
    reader, prj, stem = _reader(scratch / archive)
    fields = [field[0] for field in reader.fields[1:]]
    by_well: Counter[str] = Counter()
    kept_wells: Counter[str] = Counter()
    keep: list[int] = []
    for index, record in enumerate(reader.iterRecords()):
        label = str(dict(zip(fields, record, strict=True))["API_Label"]).strip()
        well = label[:12]
        by_well[well] += 1
        # A second wellbore on a well already kept is what the multi-wellbore share is about,
        # so the cut runs on until it has one rather than stopping at a round number.
        if len(keep) < DIRECTIONAL_ROWS or kept_wells[well] > 0:
            keep.append(index)
            kept_wells[well] += 1
        if len(keep) >= DIRECTIONAL_ROWS and any(count > 1 for count in kept_wells.values()):
            break
    _write(HERE / target, reader, prj, keep, stem)


def main() -> int:
    scratch = Path(sys.argv[1])
    api10s = cut_production(scratch)
    cut_headers(scratch, api10s)
    cut_directional(scratch, BOTTOMHOLE_ARCHIVE, "DirectionalBottomholeLocations_sample.zip")
    cut_directional(scratch, LINES_ARCHIVE, "DirectionalLines_sample.zip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
