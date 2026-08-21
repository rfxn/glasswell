"""Streaming reader for namespaced row-set XML, sized for a member that does not fit in RAM.

NM's `wcproduction.xml` is 48,310,560,330 bytes of UTF-16LE across 48,104,334 records, so the
document is never a tree: records are matched on their fully-qualified tag, handed on in batches
and dropped, and the root is pruned after each one. Three defaults are load-bearing and each has
a test — BOM-aware `utf-16` decoding, a fully-qualified tag match, and root pruning.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Sequence
from typing import IO

import polars as pl

DEFAULT_ENCODING = "utf-16"
DEFAULT_BATCH_ROWS = 65536


class MalformedRecordStream(ValueError):
    """The document stopped being XML. What parsed before it is handed on, then this."""

    def __init__(self, record_tag: str, parsed_rows: int, line: int, column: int, detail: str):
        super().__init__(
            f"{record_tag}: the document is not well-formed at line {line} column {column}"
            f" after {parsed_rows} record(s) ({detail})"
        )
        self.record_tag = record_tag
        self.parsed_rows = parsed_rows
        self.line = line
        self.column = column
        self.detail = detail

    @property
    def position(self) -> tuple[int, int]:
        return (self.line, self.column)


def stream_records(
    binary: IO[bytes],
    *,
    record_tag: str,
    namespace: str,
    encoding: str = DEFAULT_ENCODING,
    batch_rows: int = DEFAULT_BATCH_ROWS,
) -> Iterator[pl.DataFrame]:
    """Yield every `record_tag` element as text columns, `batch_rows` at a time.

    Columns are the union of the children seen so far, in source order. The reader declares no
    header of its own: a child nobody expected still reaches the frame, because the parse
    directive is what judges a header and it cannot judge what the reader dropped.
    """
    qualified = f"{{{namespace}}}{record_tag}" if namespace else record_tag
    prefix = f"{{{namespace}}}" if namespace else ""
    seen: list[str] = []
    pending: list[dict[str, str | None]] = []
    parsed = 0

    text = io.TextIOWrapper(binary, encoding=encoding)
    events = ET.iterparse(text, events=("start", "end"))
    try:
        _, root = next(events)
        for event, element in events:
            if event != "end" or element.tag != qualified:
                continue
            row: dict[str, str | None] = {}
            for child in element:
                name = child.tag.removeprefix(prefix)
                if name not in row and name not in seen:
                    seen.append(name)
                row[name] = child.text
            pending.append(row)
            parsed += 1
            element.clear()
            # clear() alone leaves the root holding every processed sibling, which at this scale
            # is an out-of-memory kill rather than a slowdown.
            root.clear()
            if len(pending) >= batch_rows:
                yield _frame(pending, seen)
                pending = []
    except (ET.ParseError, UnicodeDecodeError) as error:
        if pending:
            yield _frame(pending, seen)
        line, column = getattr(error, "position", (0, 0))
        raise MalformedRecordStream(record_tag, parsed, line, column, str(error)) from error
    if pending:
        yield _frame(pending, seen)


def _frame(rows: list[dict[str, str | None]], columns: Sequence[str]) -> pl.DataFrame:
    """Text in, text out: staging is source-faithful and the reader coerces nothing (§3.4.2)."""
    return pl.DataFrame(rows, schema=dict.fromkeys(columns, pl.String))
