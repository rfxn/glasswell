"""The Parquet writer and reader staging leans on: SB-01 §3.6's profile, made checkable.

Byte reproducibility is the whole claim behind D1 determinism (SB-07 §4.2), so it is asserted
against two writes of the same rows rather than assumed from the settings.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb
import polars as pl
import pytest

from glasswell.staging.duck import (
    ROW_GROUP_SIZE,
    STAGING_ROOT_ENV,
    partition_uri,
    register_head,
    resolve_staging_root,
    scan_partition,
    write_partition,
)

MANIFEST = "man_4d3bceb6a5b79880db518e00d933ae95"


def frames(count: int = 3, *, rows: int = 4) -> list[pl.DataFrame]:
    return [
        pl.DataFrame(
            {
                "source_row_ordinal": pl.Series(
                    range(batch * rows, batch * rows + rows), dtype=pl.Int64
                ),
                "prd_knd_cde": ["G ", "O ", "W ", "C "][:rows],
                "prod_amt": ["0", "53612", None, "12"][:rows],
            }
        )
        for batch in range(count)
    ]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_partition_path_is_the_declared_one(tmp_path, monkeypatch):
    monkeypatch.setenv(STAGING_ROOT_ENV, str(tmp_path))

    uri = partition_uri("nm_ocd_wcproduction", "records", MANIFEST)

    assert uri == tmp_path / "nm_ocd_wcproduction" / "records" / f"manifest={MANIFEST}" / (
        "part-0000.parquet"
    )
    assert resolve_staging_root() == tmp_path


def test_the_same_rows_written_twice_are_byte_identical(tmp_path):
    first = write_partition(frames(), tmp_path / "one" / "part-0000.parquet")
    second = write_partition(frames(), tmp_path / "two" / "part-0000.parquet")

    assert first.sha256 == second.sha256
    assert digest(Path(first.uri)) == first.sha256
    assert first.rows == second.rows == 12


def test_the_write_leaves_no_scratch_behind(tmp_path):
    write_partition(frames(), tmp_path / "part-0000.parquet")

    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["part-0000.parquet"]


def test_the_rows_come_back_verbatim_in_the_declared_sort_order(tmp_path):
    shuffled = list(reversed(frames()))

    written = write_partition(shuffled, tmp_path / "part-0000.parquet")
    frame = pl.read_parquet(written.uri)

    assert scan_partition(written.uri).columns == frame.columns
    assert written.sort_order == "source_row_ordinal"
    assert frame["source_row_ordinal"].to_list() == list(range(12))
    assert frame["prd_knd_cde"].to_list()[:4] == ["G ", "O ", "W ", "C "]
    assert frame["prod_amt"][2] is None


def test_the_artifact_carries_no_clock_and_no_hostname(tmp_path):
    """SB-01 §3.6: no custom key/value metadata, and `created_by` pinned by the lockfile."""
    written = write_partition(frames(), tmp_path / "part-0000.parquet")
    connection = duckdb.connect()

    metadata = connection.execute(
        "select key, value from parquet_kv_metadata(?)", [written.uri]
    ).fetchall()
    created_by = connection.execute(
        "select created_by from parquet_file_metadata(?)", [written.uri]
    ).fetchone()[0]

    assert metadata == []
    assert created_by.startswith(f"DuckDB version v{duckdb.__version__}")


def test_one_row_group_holds_the_declared_number_of_rows(tmp_path):
    written = write_partition(
        [pl.DataFrame({"source_row_ordinal": pl.Series(range(3), dtype=pl.Int64)})],
        tmp_path / "part-0000.parquet",
    )

    groups = duckdb.connect().execute(
        "select count(distinct row_group_id) from parquet_metadata(?)", [written.uri]
    ).fetchone()[0]

    assert groups == 1
    assert ROW_GROUP_SIZE == 122880


def test_a_batch_that_drifts_from_the_first_schema_is_refused(tmp_path):
    drifted = [*frames(1), pl.DataFrame({"source_row_ordinal": pl.Series([9], dtype=pl.Int64)})]

    with pytest.raises(ValueError, match="column"):
        write_partition(drifted, tmp_path / "part-0000.parquet")


def test_writing_no_rows_is_refused_rather_than_leaving_an_empty_artifact(tmp_path):
    with pytest.raises(ValueError, match="no batches"):
        write_partition([], tmp_path / "part-0000.parquet")


def test_the_partition_anti_joins_against_a_registered_head(tmp_path):
    """P4.4's substrate: neither side is ever a Python list."""
    written = write_partition(frames(1), tmp_path / "part-0000.parquet")
    connection = duckdb.connect()
    head = [pl.DataFrame({"prd_knd_cde": ["G ", "W "]})]

    register_head(connection, head, name="head")
    partition = scan_partition(written.uri, connection=connection)
    partition.to_view("staged")
    unseen = connection.execute(
        "select prd_knd_cde from staged s"
        " where not exists (select 1 from head h where h.prd_knd_cde = s.prd_knd_cde)"
        " order by 1"
    ).fetchall()

    assert unseen == [("C ",), ("O ",)]
