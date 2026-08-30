"""Cut the checked-in NM OCD fixtures from the pulled raw bytes (DIR-10).

    python tests/fixtures/nm_ocd/cut_fixtures.py --raw-root /data/raw

Reads `/data/raw`, never the network: the one polite FTP session happened in phase 1 and no
later phase opens a socket to 164.64.106.6 (SB-01 §1.3).

Truncation only. A kept record is copied as the exact character span it occupies in the source
document, so the CHAR padding, the per-record `xmlns` declaration and the element order all
survive. The prologue — `<root>` plus the inline `xsd:schema` — is copied verbatim too, so a
fixture is a real `SqlRowSet1` dump rather than a simplified one.

UTF-16 is read and written BOM-aware (`utf-16`, not `utf-16-le`): the source carries a
byte-order mark, the fixtures must too, and every written file is asserted to start `ff fe`.

`wcproduction` is ordered oldest-first and opens in 1973, so a fixture cut from the head alone
would carry nothing inside DIR-12's 2015-01 promotion window. The production fixture therefore
carries both sides of that boundary: a few records from the head, then the window.
"""

from __future__ import annotations

import argparse
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

ENCODING = "utf-16"
NAMESPACE = "urn:schemas-microsoft-com:sql:SqlRowSet1"
RECORD_COUNT = 300
ROOT_CLOSE = "</root>"
READ_CHARS = 1 << 20

# DIR-12: promotion opens at 2015-01. Twenty records from the head keep the pre-window side of
# the boundary in the fixture, so a window test has something to exclude.
WINDOW_MIN_YEAR = 2015
PRE_WINDOW_RECORDS = 20
# Enough modern records to carry every case below without reading further into a 48 GB member.
WINDOW_SCAN_RECORDS = 60_000
SMALL_TABLE_SCAN = 60_000

KEY_COLUMNS = ("api_st_cde", "api_cnty_cde", "api_well_idn")
# The header table is 321,510 records and the rarest coordinate class holds four of them, so
# the wellhistory cut scans the whole member and keeps a small, case-covering selection.
WELLHISTORY_RECORDS = 40
# The amended cell for the second effective row; the source's own datetime shape.
WELLHISTORY_RESTATED_EFF_DTE = "2024-06-01T00:00:00"
VOLUME_COLUMN = "prod_amt"
SMALL_TABLES = ("wchistory", "podwc", "spacingunit", "property", "ogrid")

_YEAR = re.compile(r"<prodn_yr>(\d+)</prodn_yr>")
# Matched on the raw span, not on a parse: a wellhistory record carries xsi:nil, whose prefix is
# declared on <root>, so ET.fromstring of one record in isolation raises on an unbound prefix.
_ORDINATE = {
    axis: re.compile(rf"<{axis}(?:\s[^>]*?)?(?:/>|>(?P<value>[^<]*)</{axis}>)")
    for axis in ("latitude", "longitude")
}
_CELL = re.compile(r"<(\w+)(?:\s[^>]*?)?(?:/>|>([^<]*)</\1>)")
_WELL = re.compile(
    r"<api_st_cde>(\d+)</api_st_cde><api_cnty_cde>(\d+)</api_cnty_cde>"
    r"<api_well_idn>(\d+)</api_well_idn>"
)


@dataclass(frozen=True, slots=True)
class Record:
    ordinal: int
    span: str
    values: dict[str, str]


def ordinate(span: str, axis: str) -> float | None:
    """The parsed ordinate, or None when the element is nil or absent. Both arrive in scientific
    notation on every record that has one, so this parses as a float rather than slicing."""
    match = _ORDINATE[axis].search(span)
    if match is None:
        return None
    text = match.group("value")
    if text is None or not text.strip():
        return None
    try:
        return float(text)
    except ValueError:
        return None


def span_values(span: str) -> dict[str, str]:
    """Cell values read off the raw span, for a record ET cannot parse in isolation."""
    body = span[span.find(">") + 1 :]
    return {name: (value or "") for name, value in _CELL.findall(body)}


def wellhistory_cases() -> dict[str, Callable[[Record], bool]]:
    """The coordinate pair's six populations, plus the header shapes the promoter has to handle.

    The pair is what matters, not either ordinate: ST_MakePoint consumes both and raises on
    neither, so a good latitude beside a zero longitude is a valid point in the Gulf of Guinea.
    """

    def pair(span: str) -> tuple[float | None, float | None]:
        return ordinate(span, "latitude"), ordinate(span, "longitude")

    def usable(record: Record) -> bool:
        lat, lon = pair(record.span)
        return lat is not None and lon is not None and lat != 0.0 and lon != 0.0

    def both_zero(record: Record) -> bool:
        return pair(record.span) == (0.0, 0.0)

    def longitude_zero_only(record: Record) -> bool:
        lat, lon = pair(record.span)
        return lat not in (None, 0.0) and lon == 0.0

    def both_nil(record: Record) -> bool:
        return pair(record.span) == (None, None)

    def latitude_nil_longitude_present(record: Record) -> bool:
        lat, lon = pair(record.span)
        return lat is None and lon is not None

    def latitude_present_longitude_nil(record: Record) -> bool:
        lat, lon = pair(record.span)
        return lat is not None and lon is None

    def unpadded_county(record: Record) -> bool:
        return len(record.values.get("api_cnty_cde", "")) < 3

    def unpadded_well_number(record: Record) -> bool:
        return len(record.values.get("api_well_idn", "")) < 5

    def horizontal(record: Record) -> bool:
        return record.values.get("directional_status", "") == "H"

    def open_ended(record: Record) -> bool:
        return record.values.get("rec_termn_dte", "").startswith("9999-12-31")

    def terminated(record: Record) -> bool:
        value = record.values.get("rec_termn_dte", "")
        return bool(value) and not value.startswith("9999-12-31")

    def char_padded(record: Record) -> bool:
        return record.values.get("prop_fm_desc", "").endswith(" ")

    return {
        "usable_pair": usable,
        "both_zero": both_zero,
        "longitude_zero_only": longitude_zero_only,
        "both_nil": both_nil,
        "latitude_nil_longitude_present": latitude_nil_longitude_present,
        "latitude_present_longitude_nil": latitude_present_longitude_nil,
        "unpadded_county": unpadded_county,
        "unpadded_well_number": unpadded_well_number,
        "horizontal": horizontal,
        "open_ended": open_ended,
        "terminated": terminated,
        "char_padded": char_padded,
    }


def read_wellhistory(archive: Path) -> tuple[str, list[Record], dict[str, int]]:
    """One full pass over the header member, keeping the head plus every case's first witness.

    The whole member is scanned because longitude_zero_only holds four records of 321,510 and
    the mixed nil/valued classes hold three between them; a head cut would carry none of them,
    and those are exactly the records the coordinate rule exists for.
    """
    cases = wellhistory_cases()
    bundle, text = _member(archive)
    head: list[Record] = []
    kept: dict[int, Record] = {}
    populations = dict.fromkeys(cases, 0)
    try:
        stream = _spans(text, "wellhistory")
        prologue = next(stream)
        for ordinal, span in enumerate(stream):
            record = Record(ordinal, span, span_values(span))
            if len(head) < WELLHISTORY_RECORDS // 2:
                head.append(record)
            for name, predicate in cases.items():
                if not predicate(record):
                    continue
                populations[name] += 1
                if not any(predicate(item) for item in kept.values()):
                    kept[ordinal] = record
    finally:
        text.close()
        bundle.close()

    for record in head:
        if len(kept) >= WELLHISTORY_RECORDS:
            break
        kept.setdefault(record.ordinal, record)

    selected = [kept[ordinal] for ordinal in sorted(kept)]
    # The corpus head hands out one effective row per well, and the promoter has to meet two:
    # (api10, effective_from) is the header key, and one surface point is kept for the pair. One
    # documented single-cell amendment, the same device the production fixture uses.
    witness = next(record for record in selected if wellhistory_cases()["usable_pair"](record))
    restated = amend(witness, eff_dte=WELLHISTORY_RESTATED_EFF_DTE)
    index = selected.index(witness)
    selected = [*selected[: index + 1], restated, *selected[index + 1 :]]
    populations["restated_effective_row"] = 1
    return prologue, selected, populations


def payload_zip(raw_root: Path, table: str) -> Path:
    """The newest sealed vintage for the table; the vintage is in the directory name."""
    candidates = sorted((raw_root / f"nm_ocd_{table}").rglob("payload.zip"))
    if not candidates:
        raise FileNotFoundError(f"no payload.zip under {raw_root}/nm_ocd_{table}")
    return candidates[-1]


def _member(archive: Path) -> tuple[zipfile.ZipFile, io.TextIOWrapper]:
    bundle = zipfile.ZipFile(archive)
    name = bundle.namelist()[0]
    return bundle, io.TextIOWrapper(bundle.open(name), encoding=ENCODING)


def _spans(text: io.TextIOWrapper, record_tag: str) -> Iterator[str]:
    """The prologue, then every record as the verbatim span it occupies in the document."""
    opening = re.compile(rf"<{re.escape(record_tag)}[\s>]")
    closing = f"</{record_tag}>"
    buffer = ""
    while (match := opening.search(buffer)) is None:
        chunk = text.read(READ_CHARS)
        if not chunk:
            raise ValueError(f"no <{record_tag}> element in the document")
        buffer += chunk
    yield buffer[: match.start()]
    # Scanning by index and compacting only on refill: re-slicing the buffer per record copies
    # the unread megabyte 48 million times, which is the difference between minutes and days.
    position = match.start()
    while True:
        end = buffer.find(closing, position)
        if end == -1:
            buffer = buffer[position:]
            position = 0
            chunk = text.read(READ_CHARS)
            if not chunk:
                return
            buffer += chunk
            continue
        end += len(closing)
        yield buffer[position:end]
        position = end


def _values(span: str) -> dict[str, str]:
    element = ET.fromstring(span)
    return {child.tag.removeprefix(f"{{{NAMESPACE}}}"): (child.text or "") for child in element}


def read_records(archive: Path, table: str, *, limit: int) -> tuple[str, list[Record]]:
    bundle, text = _member(archive)
    try:
        stream = _spans(text, table)
        prologue = next(stream)
        records = []
        for ordinal, span in enumerate(stream):
            records.append(Record(ordinal=ordinal, span=span, values=_values(span)))
            if len(records) >= limit:
                break
    finally:
        text.close()
        bundle.close()
    return prologue, records


def read_production(archive: Path) -> tuple[str, list[Record], list[Record]]:
    """The head of the member, then the first window of records inside DIR-12's year.

    Skipping is done on the raw span with a regex rather than by parsing: the 2015 boundary sits
    tens of millions of records into the file, and parsing every one of them to find it would
    turn a fixture cut into an hours-long job.
    """
    bundle, text = _member(archive)
    try:
        stream = _spans(text, "wcproduction")
        prologue = next(stream)
        head: list[Record] = []
        window: list[Record] = []
        for ordinal, span in enumerate(stream):
            if len(head) < PRE_WINDOW_RECORDS:
                head.append(Record(ordinal, span, _values(span)))
                continue
            if not window:
                year = _YEAR.search(span)
                if year is None or int(year.group(1)) < WINDOW_MIN_YEAR:
                    continue
            window.append(Record(ordinal, span, _values(span)))
            if len(window) >= WINDOW_SCAN_RECORDS:
                break
    finally:
        text.close()
        bundle.close()
    return prologue, head, window


def production_cases() -> dict[str, Callable[[Record], bool]]:
    """The cases PLAN-NM P1.9 requires the production fixture to carry."""

    def even_county(record: Record) -> bool:
        county = record.values.get("api_cnty_cde", "")
        return county.isdigit() and int(county) % 2 == 0

    def stream(kind: str) -> Callable[[Record], bool]:
        return lambda record: record.values.get("prd_knd_cde", "") == kind

    return {
        "even_county": even_county,
        "stream_gas": stream("G "),
        "stream_oil": stream("O "),
        "stream_water": stream("W "),
        "zero_volume": lambda record: _is_zero(record.values.get(VOLUME_COLUMN, "")),
        "absent_volume": lambda record: VOLUME_COLUMN not in record.values,
        "absent_key_component": lambda record: any(
            not record.values.get(column) for column in (*KEY_COLUMNS, "pool_idn")
        ),
        "amend_ind_set": lambda record: record.values.get("amend_ind", "").strip() not in ("", "N"),
        "zero_days": lambda record: _is_zero(record.values.get("prodn_day_num", "")),
    }


def _is_zero(value: str) -> bool:
    try:
        return float(value) == 0.0
    except ValueError:
        return False


def multi_pool_records(records: list[Record]) -> list[Record]:
    """Both filings of the first well-month that reports two pools — the S-E grain in one case."""
    groups: dict[tuple[str, ...], list[Record]] = {}
    for record in records:
        key = tuple(
            record.values.get(column, "")
            for column in (*KEY_COLUMNS, "prodn_yr", "prodn_mth", "prd_knd_cde")
        )
        group = groups.setdefault(key, [])
        group.append(record)
        if len({member.values.get("pool_idn", "") for member in group}) > 1:
            return group
    return []


def select(
    head: list[Record], window: list[Record], cases: dict[str, Callable[[Record], bool]]
) -> tuple[list[Record], dict[str, bool]]:
    """The head, every case the head misses, then the front of the window up to 300 records."""
    kept: dict[int, Record] = {record.ordinal: record for record in head}
    for record in multi_pool_records(window):
        kept[record.ordinal] = record
    for predicate in cases.values():
        if any(predicate(record) for record in kept.values()):
            continue
        found = next((record for record in window if predicate(record)), None)
        if found is not None:
            kept[found.ordinal] = found

    for record in window:
        if len(kept) >= RECORD_COUNT:
            break
        kept.setdefault(record.ordinal, record)

    ordered = [kept[ordinal] for ordinal in sorted(kept)][:RECORD_COUNT]
    covered = {
        name: any(predicate(record) for record in ordered) for name, predicate in cases.items()
    }
    return ordered, covered


def write_fixture(destination: Path, prologue: str, records: list[Record]) -> Path:
    document = prologue + "".join(record.span for record in records) + ROOT_CLOSE
    destination.write_text(document, encoding=ENCODING)
    mark = destination.read_bytes()[:2]
    if mark != b"\xff\xfe":
        raise ValueError(f"{destination} lost its UTF-16LE byte-order mark: {mark.hex()}")
    return destination


def amend(record: Record, **replacements: str) -> Record:
    """One documented single-cell edit per column, applied to a copy of the record's span."""
    span = record.span
    values = dict(record.values)
    for column, new in replacements.items():
        old = record.values[column]
        span = span.replace(f"<{column}>{old}</{column}>", f"<{column}>{new}</{column}>", 1)
        values[column] = new
    return Record(ordinal=record.ordinal, span=span, values=values)


def cut(raw_root: Path, destination: Path) -> dict[str, object]:
    destination.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {}

    prologue, head, window = read_production(payload_zip(raw_root, "wcproduction"))
    kept, covered = select(head, window, production_cases())
    write_fixture(destination / "nm_wcproduction_300.xml", prologue, kept)
    report["wcproduction"] = len(kept)
    report["coverage"] = covered
    report["window_first_ordinal"] = window[0].ordinal if window else None

    amended_index = next(
        index
        for index in range(len(kept) - 1, -1, -1)
        if not _is_zero(kept[index].values.get(VOLUME_COLUMN, "0"))
    )
    target = kept[amended_index]
    restated = amend(
        target,
        prod_amt=str(int(float(target.values[VOLUME_COLUMN])) + 1000),
        mod_dte="2026-08-19T04:00:00.000",
        amend_ind="Y",
    )
    write_fixture(
        destination / "nm_wcproduction_300_amended.xml",
        prologue,
        [*kept[:amended_index], restated, *kept[amended_index + 1 :]],
    )
    report["amended_ordinal"] = target.ordinal
    report["amended_prod_amt"] = f"{target.values[VOLUME_COLUMN]} -> {restated.values['prod_amt']}"

    moved = [amend(record, mod_dte="2026-08-19T04:00:00.000") for record in kept]
    write_fixture(destination / "nm_wcproduction_300_moddte.xml", prologue, moved)
    report["moddte_records"] = len(moved)

    wells = {tuple(record.values.get(c, "") for c in KEY_COLUMNS) for record in kept}
    for table in SMALL_TABLES:
        table_prologue, selected, matched = read_covering(
            payload_zip(raw_root, table), table, wells
        )
        write_fixture(destination / f"nm_{table}_300.xml", table_prologue, selected)
        report[table] = f"{len(selected)} records, {matched} of them naming a fixture well"

    # The plan expected the whole pool table ("0.2 MB source"), but 0.2 MB is the *compressed*
    # zip: the member is 7.3 MB of UTF-16 XML. A 300-record cut that covers every pool the
    # production fixture names carries the same test value at 1/25th of the repository cost.
    pool_prologue, pool_records = read_records(
        payload_zip(raw_root, "pool"), "pool", limit=SMALL_TABLE_SCAN
    )
    pools = {record.values.get("pool_idn", "") for record in kept}
    selected, covers = select(
        pool_records[:RECORD_COUNT],
        pool_records,
        {"covers_fixture_pools": lambda record: record.values.get("pool_idn", "") in pools},
    )
    write_fixture(destination / "nm_pool_300.xml", pool_prologue, selected)
    report["pool"] = f"{len(selected)} records, covers_fixture_pools={covers}"

    wh_prologue, wh_records, wh_populations = read_wellhistory(payload_zip(raw_root, "wellhistory"))
    write_fixture(destination / "nm_wellhistory_headers.xml", wh_prologue, wh_records)
    report["wellhistory"] = f"{len(wh_records)} records"
    report["wellhistory_populations"] = wh_populations
    return report


def read_covering(
    archive: Path, table: str, wells: set[tuple[str, ...]]
) -> tuple[str, list[Record], int]:
    """The head of the table plus the records that name a production-fixture well.

    The production fixture is cut from 2015 onward, so the wells it names sit deep in a table
    ordered by API. Matching is a single regex per span rather than a parse of every record,
    and only the head and the matches are held.
    """
    bundle, text = _member(archive)
    head: list[Record] = []
    matches: dict[int, Record] = {}
    try:
        stream = _spans(text, table)
        prologue = next(stream)
        for ordinal, span in enumerate(stream):
            if len(head) < RECORD_COUNT:
                head.append(Record(ordinal, span, _values(span)))
            if len(matches) >= RECORD_COUNT // 2:
                if len(head) >= RECORD_COUNT:
                    break
                continue
            found = _WELL.search(span)
            if found is not None and found.groups() in wells:
                matches[ordinal] = Record(ordinal, span, _values(span))
    finally:
        text.close()
        bundle.close()

    kept = dict(matches)
    for record in head:
        if len(kept) >= RECORD_COUNT:
            break
        kept.setdefault(record.ordinal, record)
    ordered = [kept[ordinal] for ordinal in sorted(kept)][:RECORD_COUNT]
    return prologue, ordered, sum(1 for record in ordered if record.ordinal in matches)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, default=Path("/data/raw"))
    parser.add_argument("--destination", type=Path, default=Path(__file__).parent)
    arguments = parser.parse_args()
    for name, value in cut(arguments.raw_root, arguments.destination).items():
        print(f"{name}: {value}")


if __name__ == "__main__":
    main()
