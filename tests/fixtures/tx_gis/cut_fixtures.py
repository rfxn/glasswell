"""Cut the checked-in TX fixtures from the real RRC downloads (DIR-10).

    python tests/fixtures/tx_gis/cut_fixtures.py --downloads /tmp/gw-tx

Selection only. No attribute value is edited, each `.prj` is copied byte for byte because the
datum rule reads it, and the wellbore-export rows are whole records taken from the shipped
file. The one edit is to the portal listing's declared row count, which is rewritten to the
number of rows kept — the parser's contract is that the two agree, and a fixture that
contradicted it would be testing a portal state that has never existed.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import tempfile
import zipfile
from collections.abc import Sequence
from pathlib import Path

import shapefile

COUNTY = "003"
SURFACE_RECORDS = 400
LINE_RECORDS = 120
LISTING_ROWS = 12
EWA_API_LIMIT = 400
LAYER_SUFFIXES = ("s", "b", "l")
ROW = re.compile(r'<tr data-ri="\d+".*?</tr>', re.DOTALL)
ROW_COUNT = re.compile(r"rowCount:(\d+)")


def _open(archive: Path, suffix: str) -> tuple[shapefile.Reader, bytes]:
    with zipfile.ZipFile(archive) as bundle:
        members = {}
        for name in bundle.namelist():
            stem, _, extension = name.rpartition(".")
            if stem.lower().endswith(suffix):
                members.setdefault(extension.lower(), name)
        reader = shapefile.Reader(
            shp=io.BytesIO(bundle.read(members["shp"])),
            shx=io.BytesIO(bundle.read(members["shx"])),
            dbf=io.BytesIO(bundle.read(members["dbf"])),
        )
        return reader, bundle.read(members["prj"])


def _write(
    bundle: zipfile.ZipFile,
    reader: shapefile.Reader,
    prj: bytes,
    ordinals: Sequence[int],
    stem_name: str,
) -> None:
    with tempfile.TemporaryDirectory() as scratch:
        stem = Path(scratch) / stem_name
        writer = shapefile.Writer(target=str(stem), shapeType=reader.shapeType)
        writer.fields = reader.fields[1:]
        for ordinal in ordinals:
            record = reader.shapeRecord(ordinal)
            writer.record(*list(record.record))
            writer.shape(record.shape)
        writer.close()
        stem.with_suffix(".prj").write_bytes(prj)
        for extension in (".shp", ".shx", ".dbf", ".prj"):
            bundle.write(stem.with_suffix(extension), stem_name + extension)


def cut_county(downloads: Path, destination: Path) -> dict[str, int]:
    """Keep the arcs' wells: a lateral whose surface point is absent is an orphan, not a test."""
    archive = downloads / "wells" / f"well{COUNTY}.zip"
    lines, _ = _open(archive, "l")
    line_rows = list(range(min(LINE_RECORDS, len(lines))))
    wanted = {lines.record(ordinal)["API"] for ordinal in line_rows}

    counts = {}
    out = destination / f"well{COUNTY}_sample.zip"
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for suffix in LAYER_SUFFIXES:
            reader, prj = _open(archive, suffix)
            if suffix == "l":
                ordinals = line_rows
            else:
                selected = [
                    ordinal
                    for ordinal in range(len(reader))
                    if reader.record(ordinal)["API"] in wanted
                ]
                for ordinal in range(len(reader)):
                    if len(selected) >= SURFACE_RECORDS:
                        break
                    if ordinal not in selected:
                        selected.append(ordinal)
                ordinals = sorted(set(selected))[:SURFACE_RECORDS]
            _write(bundle, reader, prj, ordinals, f"well{COUNTY}{suffix}")
            counts[suffix] = len(ordinals)
            reader.close()
    lines.close()
    return counts


def cut_listing(downloads: Path, destination: Path) -> tuple[int, int]:
    """The page and the partial that completes it: the folder holds one row the page never shows.

    That is the live portal's own shape — 255 well archives behind a 250-row page — reproduced
    at fixture scale so the pagination path is exercised rather than described.
    """
    page = (downloads / "wells" / "listing.html").read_text(encoding="utf-8")
    partial = (downloads / "mft_listing_full.html").read_text(encoding="utf-8")
    page_rows = ROW.findall(page)[:LISTING_ROWS]
    hidden = [row for row in ROW.findall(partial) if "well501.zip" in row]
    full_rows = [*page_rows, *hidden]

    head = page[: page.index(ROW.findall(page)[0])]
    foot = page[page.index(ROW.findall(page)[-1]) + len(ROW.findall(page)[-1]) :]
    listing = ROW_COUNT.sub(f"rowCount:{len(full_rows)}", head + "".join(page_rows) + foot)
    (destination / "mft_listing.html").write_text(listing, encoding="utf-8")

    body = "".join(full_rows)
    view = re.search(r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"', page).group(1)
    (destination / "mft_listing_partial.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><partial-response id="j_id__v_0"><changes>'
        f'<update id="fileTable"><![CDATA[{body}]]></update>'
        f'<update id="j_id__v_0:javax.faces.ViewState:1"><![CDATA[{view}]]></update>'
        "</changes></partial-response>",
        encoding="utf-8",
    )
    return len(page_rows), len(full_rows)


def cut_ewa(downloads: Path, destination: Path, apis: set[str]) -> int:
    """Every record for the fixture's own wells, plus one per well type the export carries."""
    source = downloads / "tx-ewa" / "OG_WELLBORE_EWA_Report.csv"
    kept: list[list[str]] = []
    seen_types: set[str] = set()
    with source.open("r", newline="", encoding="utf-8", errors="replace") as handle:
        for record in csv.reader(handle):
            if len(record) != 59:
                if len(kept) and len(record) > 1:
                    kept.append(record)  # one malformed record, so the layout guard has work
                continue
            well_type = record[18].strip()
            if record[2] in apis or (well_type and well_type not in seen_types):
                seen_types.add(well_type)
                kept.append(record)
            if len(kept) > EWA_API_LIMIT and len(seen_types) > 20:
                break
    target = destination.parent / "tx_ewa" / "OG_WELLBORE_EWA_sample.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle, quoting=csv.QUOTE_ALL).writerows(kept)
    return len(kept)


def sample_apis(destination: Path) -> set[str]:
    with zipfile.ZipFile(destination / f"well{COUNTY}_sample.zip") as bundle:
        members = {
            name.rpartition(".")[2].lower(): name
            for name in bundle.namelist()
            if name.startswith(f"well{COUNTY}s")
        }
        reader = shapefile.Reader(
            shp=io.BytesIO(bundle.read(members["shp"])),
            shx=io.BytesIO(bundle.read(members["shx"])),
            dbf=io.BytesIO(bundle.read(members["dbf"])),
        )
        apis = {record["API"] for record in reader.records()}
        reader.close()
        return apis


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downloads", type=Path, default=Path("/tmp/gw-tx"))
    parser.add_argument("--destination", type=Path, default=Path(__file__).parent)
    arguments = parser.parse_args()
    arguments.destination.mkdir(parents=True, exist_ok=True)
    counts = cut_county(arguments.downloads, arguments.destination)
    page_rows, full_rows = cut_listing(arguments.downloads, arguments.destination)
    apis = sample_apis(arguments.destination)
    records = cut_ewa(arguments.downloads, arguments.destination, apis)
    print(f"well{COUNTY}_sample.zip: {counts}")
    print(f"mft_listing.html: {page_rows} rows, partial: {full_rows}")
    print(f"OG_WELLBORE_EWA_sample.csv: {records} records")


if __name__ == "__main__":
    main()
