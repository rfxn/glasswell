#!/usr/bin/env python3
"""E-9 — re-confirm NDOGD_Surveys station granularity without downloading the archive.

Reads the zip central directory and the head of each `.gdbtable` member over HTTP range
requests (~200 KB against a 321 MB archive), and asserts that the survey feature classes
carry `measdpth`, `inclination`, `azimuth` and `tvd`. A "no" here removes `landing_tvd_ft`
and `structural_residual_ft` from the ND feature spec, so it is evidence, not an assumption
(v0.6 §4A.6 family C, SB-02 §1.3 C).

The units and identity assertions in E-9 (ii) and (iii) run against loaded data at first
full ingest and are conformance rules, not part of this probe.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import zipfile

import httpx

URL = "https://gis.dmr.nd.gov/downloads/oilgas/filegeodatabase/NDOGD_Surveys.gdb.zip"
REQUIRED_FIELDS = ("measdpth", "inclination", "azimuth", "tvd")
FIELD_TYPES = {
    0: "int16", 1: "int32", 2: "float32", 3: "float64", 4: "string", 5: "date",
    6: "objectid", 7: "geometry", 8: "binary", 9: "raster", 10: "uuid", 11: "uuid", 12: "xml",
}
NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,31}")


class HttpRangeFile(io.RawIOBase):
    """A seekable file over HTTP byte ranges, so zipfile can read members lazily."""

    def __init__(self, client: httpx.Client, url: str) -> None:
        self._client = client
        self._url = url
        self._pos = 0
        self.bytes_pulled = 0
        head = client.head(url)
        head.raise_for_status()
        if head.headers.get("accept-ranges") != "bytes":
            raise RuntimeError(f"{url} does not advertise byte ranges")
        self.size = int(head.headers["content-length"])
        self.last_modified = head.headers.get("last-modified", "")

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self._pos = offset
        elif whence == io.SEEK_CUR:
            self._pos += offset
        else:
            self._pos = self.size + offset
        return self._pos

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = self.size - self._pos
        size = min(size, self.size - self._pos)
        if size <= 0:
            return b""
        end = self._pos + size - 1
        response = self._client.get(self._url, headers={"Range": f"bytes={self._pos}-{end}"})
        response.raise_for_status()
        payload = response.content
        self.bytes_pulled += len(payload)
        self._pos += len(payload)
        return payload

    def readinto(self, buffer) -> int:
        chunk = self.read(len(buffer))
        buffer[: len(chunk)] = chunk
        return len(chunk)


def scan_fields(head: bytes, limit: int = 20000) -> list[tuple[str, str]]:
    """Recover (name, type) pairs from a FileGDB field-descriptor section.

    Names are length-prefixed UTF-16LE followed by a length-prefixed alias and a type byte.
    Resynchronizing by scan rather than by exact advance keeps the geometry field's
    variable-length spatial-reference payload from desynchronizing the rest of the list.
    """
    fields: list[tuple[str, str]] = []
    offset = 40
    ceiling = min(len(head), limit)
    while offset < ceiling:
        length = head[offset]
        if 3 <= length <= 32:
            raw = head[offset + 1 : offset + 1 + 2 * length]
            if len(raw) == 2 * length and all(raw[i + 1] == 0 for i in range(0, len(raw), 2)):
                name = raw.decode("utf-16-le", errors="ignore")
                if NAME_RE.fullmatch(name):
                    alias_at = offset + 1 + 2 * length
                    alias_len = head[alias_at] if alias_at < len(head) else 255
                    if alias_len <= 32:
                        type_at = alias_at + 1 + 2 * alias_len
                        type_id = head[type_at] if type_at < len(head) else 255
                        if type_id in FIELD_TYPES:
                            fields.append((name, FIELD_TYPES[type_id]))
                            offset = type_at + 1
                            continue
        offset += 1
    return fields


def datum_of(head: bytes) -> str:
    text = head.decode("utf-16-le", errors="ignore")
    start = text.find("GEOGCS")
    if start < 0:
        return "unknown"
    end = text.find("]]", start)
    return text[start : end + 2] if end > 0 else text[start : start + 120]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=URL)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    with httpx.Client(timeout=args.timeout, follow_redirects=True) as client:
        remote = HttpRangeFile(client, args.url)
        print(f"url|{args.url}")
        print(f"bytes|{remote.size}")
        print(f"last_modified|{remote.last_modified}")
        archive = zipfile.ZipFile(remote)
        tables = sorted(i.filename for i in archive.infolist() if i.filename.endswith(".gdbtable"))
        found = {}
        for table in tables:
            with archive.open(table) as member:
                head = member.read(65536)
            rows = int.from_bytes(head[4:8], "little")
            fields = scan_fields(head)
            names = [name for name, _ in fields]
            print(f"table|{table}|rows={rows}|fields={len(fields)}")
            if all(required in names for required in REQUIRED_FIELDS):
                found[table] = rows
                print(f"  datum|{datum_of(head)}")
                for name, kind in fields:
                    print(f"  field|{name}|{kind}")
        print(f"bytes_pulled|{remote.bytes_pulled}")

    if not found:
        print("VERDICT|G-12 station granularity|NO — no feature class carries MD/INC/AZI/TVD")
        return 1
    stations = max(found.values())
    print(
        f"VERDICT|G-12 station granularity|YES — {len(found)} feature classes carry "
        f"{', '.join(REQUIRED_FIELDS)}; largest holds {stations} rows"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
