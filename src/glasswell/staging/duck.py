"""DuckDB as both halves of tabular staging: the Parquet writer, and the reader promotion joins.

SB-01 §3.2 puts tabular staging in Parquet — 48.31 GB of NM text is not going into Postgres on
this VM — and §3.6 pins the write profile that makes those artifacts D1-reproducible. `pyarrow`
is not in the lockfile and is not being added, so frames cross into DuckDB through the Arrow C
stream capsule polars already exposes.

Batches are appended to a scratch DuckDB database beside the output rather than concatenated in
memory: at 48.1M rows the corpus never fits, and the profile's row-group size and sort order are
properties of the finished file, not of whatever batch size the reader happened to use.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import duckdb
import polars as pl

STAGING_ROOT_ENV = "GLASSWELL_STAGING_ROOT"
DEFAULT_STAGING_ROOT = Path("data/staging")
PARTITION_FILENAME = "part-0000.parquet"
DEFAULT_SORT_ORDER = "source_row_ordinal"

# SB-01 §3.6. Data page size and the dictionary-autotuning switch have no COPY option in
# duckdb 1.5.5; the divergence is recorded in the phase status file rather than approximated.
COMPRESSION = "zstd"
COMPRESSION_LEVEL = 3
ROW_GROUP_SIZE = 122880
THREADS = 1
# The write shares one 15 GB VM with Postgres and the API, and spilling to the scratch directory
# beside the output is cheaper than being the process that pushes them into swap.
DEFAULT_MEMORY_LIMIT = "2GB"
_CHUNK_BYTES = 1 << 20


@dataclass(frozen=True, slots=True)
class PartitionWrite:
    uri: str
    rows: int
    sha256: str
    sort_order: str


class _ArrowStream:
    """A capsule holder duckdb can scan without importing pyarrow (polars owns the buffers)."""

    def __init__(self, frame: pl.DataFrame) -> None:
        self._frame = frame

    def __arrow_c_stream__(self, requested_schema: object = None) -> object:
        return self._frame.__arrow_c_stream__(requested_schema)


def resolve_staging_root(explicit: Path | str | None = None) -> Path:
    """Explicit argument, then `GLASSWELL_STAGING_ROOT`, then a repo-local default — never /srv."""
    if explicit is not None:
        return Path(explicit)
    return Path(os.environ.get(STAGING_ROOT_ENV) or DEFAULT_STAGING_ROOT)


def partition_uri(
    source_id: str, artifact: str, manifest_id: str, *, root: Path | str | None = None
) -> Path:
    """SB-01 §3.2's path. One partition per manifest, exactly SB-07 §1.2's lineage key."""
    return (
        resolve_staging_root(root)
        / source_id
        / artifact
        / f"manifest={manifest_id}"
        / PARTITION_FILENAME
    )


def write_partition(
    frames: Iterable[pl.DataFrame],
    uri: Path | str,
    *,
    sort_order: str = DEFAULT_SORT_ORDER,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
) -> PartitionWrite:
    """Write one Parquet partition under the §3.6 profile and return its content address."""
    destination = Path(uri)
    destination.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(dir=destination.parent, prefix=".write-"))
    columns: list[str] | None = None
    rows = 0
    try:
        connection = duckdb.connect(str(scratch / "staged.duckdb"))
        try:
            connection.execute(f"SET threads={THREADS}")
            connection.execute(f"SET temp_directory='{scratch}'")
            connection.execute(f"SET memory_limit='{memory_limit}'")
            for frame in frames:
                batch = _ArrowStream(frame)  # noqa: F841 — duckdb resolves it by name
                if columns is None:
                    columns = list(frame.columns)
                    connection.execute("create table staged as select * from batch")
                else:
                    _require_same_columns(columns, frame)
                    connection.execute("insert into staged select * from batch")
                rows += frame.height
            if columns is None:
                raise ValueError(f"{destination}: no batches to write")
            order = f" order by {_column(sort_order, columns)}" if sort_order else ""
            connection.execute(
                f"COPY (select * from staged{order}) TO '{destination}'"
                f" (FORMAT PARQUET, COMPRESSION {COMPRESSION},"
                f" COMPRESSION_LEVEL {COMPRESSION_LEVEL}, ROW_GROUP_SIZE {ROW_GROUP_SIZE})"
            )
        finally:
            connection.close()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return PartitionWrite(
        uri=str(destination),
        rows=rows,
        sha256=file_sha256(destination),
        sort_order=sort_order,
    )


def scan_partition(
    uri: Path | str, *, connection: duckdb.DuckDBPyConnection | None = None
) -> duckdb.DuckDBPyRelation:
    """The written partition as a relation: promotion reads Parquet, never a Python list."""
    reader = connection or duckdb.connect()
    reader.execute(f"SET threads={THREADS}")
    return reader.read_parquet(str(uri))


@contextmanager
def partition_reader(
    partitions: Mapping[str, Path | str],
    *,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    scratch_root: Path | str | None = None,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Each named partition as a view, under the same pins the writer runs with.

    The promotion reads a month at a time out of a 245 MB partition and compares it against
    another; both stay in DuckDB, and the spill goes to a scratch directory beside the data
    rather than to whatever `/tmp` happens to have (N-3).
    """
    anchor = Path(scratch_root) if scratch_root else Path(next(iter(partitions.values()))).parent
    anchor.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(dir=anchor, prefix=".read-"))
    connection = duckdb.connect()
    try:
        connection.execute(f"SET threads={THREADS}")
        connection.execute(f"SET temp_directory='{scratch}'")
        connection.execute(f"SET memory_limit='{memory_limit}'")
        for name, uri in partitions.items():
            connection.execute(
                f"create view {identifier(name)} as select * from read_parquet('{Path(uri)}')"
            )
        yield connection
    finally:
        connection.close()
        shutil.rmtree(scratch, ignore_errors=True)


def register_head(
    connection: duckdb.DuckDBPyConnection,
    frames: Iterable[pl.DataFrame],
    *,
    name: str,
) -> duckdb.DuckDBPyRelation:
    """Materialise a comparison side inside DuckDB so an anti-join stays off the Python heap."""
    created = False
    for frame in frames:
        batch = _ArrowStream(frame)  # noqa: F841 — duckdb resolves it by name
        if created:
            connection.execute(f"insert into {identifier(name)} select * from batch")
        else:
            connection.execute(f"create temp table {identifier(name)} as select * from batch")
            created = True
    if not created:
        raise ValueError(f"{name}: no batches to register")
    return connection.table(name)


_POLARS_TYPES: dict[str, pl.DataType] = {
    "VARCHAR": pl.String,
    "BIGINT": pl.Int64,
    "INTEGER": pl.Int32,
    "DOUBLE": pl.Float64,
    "BOOLEAN": pl.Boolean,
    "DATE": pl.Date,
}


def frame_of(relation: duckdb.DuckDBPyRelation) -> pl.DataFrame:
    """A DuckDB result as a polars frame, without pyarrow.

    `relation.pl()` goes through an Arrow table and imports pyarrow, which is deliberately
    absent from the lockfile (SB-01 §3.6, M13). A column type this map does not name is read as
    text, which is what staging holds anyway.
    """
    schema = {
        name: _POLARS_TYPES.get(str(dtype), pl.String)
        for name, dtype in zip(relation.columns, relation.types, strict=True)
    }
    return pl.DataFrame(relation.fetchall(), schema=schema, orient="row")


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_same_columns(columns: Sequence[str], frame: pl.DataFrame) -> None:
    if list(frame.columns) != list(columns):
        raise ValueError(
            f"batch column list {list(frame.columns)} differs from the partition's {list(columns)};"
            " a partition holds one schema, and a drifted header belongs in quarantine"
        )


def _column(name: str, columns: Sequence[str]) -> str:
    if name not in columns:
        raise ValueError(f"sort_order {name!r} is not a column of the partition: {list(columns)}")
    return f'"{name}"'


def identifier(name: str) -> str:
    if not name.replace("_", "").isalnum() or not name[0].isalpha():
        raise ValueError(f"{name!r} is not a valid relation name")
    return name
