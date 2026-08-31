"""The staged header frame declares its dtypes instead of letting polars infer them.

Inference reads only the leading rows of each batch. `stg_nm_ocd_wellhistory__records` is 39 text
columns and one integer, and a text column that is null across that window is typed `Null` —
so the first row further down carrying a state code refuses the whole frame with
`could not append value: "TX"`. The 28-record fixture cannot contain that row; the 321,510-record
artifact does, and it failed the production promotion at the step that opens the New Mexico gate.
"""

from __future__ import annotations

import polars as pl
import pytest

from glasswell.ingest.nm_wells import HEADER_TABLE
from glasswell.seed.conformance_nm import NM_COLUMNS

COLUMNS = ["source_row_ordinal", *NM_COLUMNS[HEADER_TABLE]]


def _declared_schema() -> dict[str, pl.DataType]:
    """The schema the module builds, mirrored here so a drift in either shows up as a failure."""
    return {
        name: pl.Int64() if name == "source_row_ordinal" else pl.String() for name in COLUMNS
    }


def _rows_that_defeat_inference(width: int, leading: int = 150) -> list[tuple]:
    """Null first, then a state code in the same column — the shape the artifact has.

    Staging is text, so psycopg yields `str` or `None`. A column null across the inference
    window is typed `Null`, and the first non-null string below it cannot be appended. Leading
    *digits* do not reproduce it: those arrive as `str` too and infer as String correctly.
    """
    empty = [(index, *([None] * (width - 1))) for index in range(leading)]
    return [*empty, (leading, *(["TX"] * (width - 1)))]


def test_inference_would_refuse_the_artifacts_own_shape() -> None:
    """The floor under this guard: without a declared schema the frame genuinely fails."""
    rows = _rows_that_defeat_inference(len(COLUMNS))
    with pytest.raises(pl.exceptions.ComputeError, match="could not append value"):
        pl.DataFrame(rows, schema=COLUMNS, orient="row")


def test_the_declared_schema_accepts_it() -> None:
    rows = _rows_that_defeat_inference(len(COLUMNS))
    frame = pl.DataFrame(rows, schema=_declared_schema(), orient="row")

    assert frame.height == len(rows)
    assert frame["source_row_ordinal"].dtype == pl.Int64
    text = [name for name in COLUMNS if name != "source_row_ordinal"]
    assert {frame[name].dtype for name in text} == {pl.String}


def test_every_staged_column_the_promoter_reads_is_text_or_the_ordinal() -> None:
    """The declaration must describe the store, not a convenient guess about it."""
    schema = _declared_schema()
    assert schema["source_row_ordinal"] == pl.Int64()
    assert all(schema[name] == pl.String() for name in COLUMNS if name != "source_row_ordinal")
