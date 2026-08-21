"""The reader that has to survive 48.31 GB: UTF-16, a namespace, and one batch in memory.

Every failure mode here is silent in production if it is not asserted: a bare-tag match against
a namespaced document returns zero records without an error, and `elem.clear()` without pruning
the root leaks the whole document into RAM.
"""

from __future__ import annotations

import tracemalloc
from pathlib import Path

import polars as pl
import pytest

from glasswell.ingest.xml_stream import (
    MalformedRecordStream,
    stream_records,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "nm_ocd"
PRODUCTION = FIXTURES / "nm_wcproduction_300.xml"
NAMESPACE = "urn:schemas-microsoft-com:sql:SqlRowSet1"
RECORDS = 300
COLUMNS = (
    "api_st_cde",
    "api_cnty_cde",
    "api_well_idn",
    "pool_idn",
    "prodn_mth",
    "prodn_yr",
    "ogrid_cde",
    "prd_knd_cde",
    "eff_dte",
    "amend_ind",
    "c115_wc_stat_cde",
    "prod_amt",
    "prodn_day_num",
    "mod_dte",
)


def batches(path: Path, **options) -> list[pl.DataFrame]:
    with path.open("rb") as handle:
        return list(
            stream_records(
                handle,
                record_tag=options.pop("record_tag", "wcproduction"),
                namespace=options.pop("namespace", NAMESPACE),
                **options,
            )
        )


def synthetic(path: Path, records: list[str], *, tag: str = "row") -> Path:
    """A real SqlRowSet1 document: root, inline schema element, namespaced records."""
    body = "".join(
        f'<{tag} xmlns="{NAMESPACE}">{record}</{tag}>' for record in records
    )
    document = (
        '<root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f'<xsd:schema targetNamespace="{NAMESPACE}"'
        ' xmlns:xsd="http://www.w3.org/2001/XMLSchema"></xsd:schema>'
        f"{body}</root>"
    )
    path.write_text(document, encoding="utf-16")
    return path


def test_the_fixture_streams_in_batches_of_the_declared_size():
    frames = batches(PRODUCTION, batch_rows=128)

    assert [frame.height for frame in frames] == [128, 128, 44]
    assert sum(frame.height for frame in frames) == RECORDS


def test_one_batch_larger_than_the_document_yields_one_frame():
    frames = batches(PRODUCTION, batch_rows=65536)

    assert [frame.height for frame in frames] == [RECORDS]


def test_a_bare_tag_match_against_a_namespaced_document_yields_nothing():
    """The M1 regression: this returns zero records and raises nothing at all."""
    frames = batches(PRODUCTION, namespace="", batch_rows=128)

    assert frames == []


def test_the_columns_are_the_source_children_with_the_namespace_stripped():
    frame = batches(PRODUCTION)[0]

    assert tuple(frame.columns) == COLUMNS
    assert frame.schema == dict.fromkeys(COLUMNS, pl.String)


def test_the_bom_is_consumed_rather_than_parsed_as_a_tag_character():
    frame = batches(PRODUCTION)[0]

    assert PRODUCTION.read_bytes()[:2] == b"\xff\xfe"
    assert frame["api_st_cde"][0] == "30"


def test_reading_utf_16_bytes_under_another_encoding_fails_loudly():
    with pytest.raises(MalformedRecordStream, match="not well-formed"):
        batches(PRODUCTION, encoding="utf-8")


def test_utf_16_le_survives_only_because_expat_skips_the_re_encoded_bom():
    """Measured, against the plan's M2 claim that `utf-16-le` corrupts the first tag.

    It does leave the BOM as U+FEFF, but ElementTree feeds expat a str, expat re-encodes it to
    UTF-8, and a leading EF BB BF is a BOM there too. The pin stays `utf-16` because that is the
    spelling that is right about the bytes rather than lucky about the parser.
    """
    assert PRODUCTION.read_bytes().decode("utf-16-le")[0] == "\ufeff"
    assert PRODUCTION.read_bytes().decode("utf-16")[0] == "<"
    assert [frame.height for frame in batches(PRODUCTION, encoding="utf-16-le")] == [RECORDS]


def test_char_padding_reaches_the_frame_untrimmed():
    """B5: prd_knd_cde is CHAR(2) and arrives as 'O '. Trimming is a rule, never the reader."""
    frame = batches(PRODUCTION)[0]

    values = set(frame["prd_knd_cde"].to_list())
    assert values <= {"G ", "O ", "W ", "C "}
    assert all(len(value) == 2 for value in values)


def test_the_inline_schema_element_is_not_staged_as_a_record(tmp_path):
    path = synthetic(tmp_path / "two.xml", ["<a>1</a>", "<a>2</a>"])

    frames = batches(path, record_tag="row")

    assert [frame.height for frame in frames] == [2]
    assert frames[0]["a"].to_list() == ["1", "2"]


def test_columns_are_the_union_across_records_with_differing_children(tmp_path):
    path = synthetic(tmp_path / "ragged.xml", ["<a>1</a>", "<a>2</a><b>x</b>"])

    frame = batches(path, record_tag="row")[0]

    assert frame.columns == ["a", "b"]
    assert frame["b"].to_list() == [None, "x"]


def test_an_element_with_no_character_data_is_null_not_empty_text(tmp_path):
    path = synthetic(tmp_path / "empty.xml", ["<a></a><b/><c> </c>"])

    frame = batches(path, record_tag="row")[0]

    assert frame["a"][0] is None
    assert frame["b"][0] is None
    assert frame["c"][0] == " "


def test_a_malformed_document_keeps_what_parsed_and_names_where_it_stopped(tmp_path):
    path = tmp_path / "truncated.xml"
    good = synthetic(tmp_path / "good.xml", ["<a>1</a>"] * 4, tag="row").read_text(
        encoding="utf-16"
    )
    path.write_text(good[: good.index("</root>")] + "<row><a>", encoding="utf-16")

    collected: list[pl.DataFrame] = []
    with path.open("rb") as handle:
        stream = stream_records(handle, record_tag="row", namespace=NAMESPACE, batch_rows=2)
        with pytest.raises(MalformedRecordStream) as failure:
            collected.extend(stream)

    assert [frame.height for frame in collected] == [2, 2]
    assert failure.value.parsed_rows == 4
    assert failure.value.position == (failure.value.line, failure.value.column)
    assert "row" in str(failure.value)


def peak_bytes(path: Path, *, batch_rows: int) -> int:
    tracemalloc.start()
    try:
        with path.open("rb") as handle:
            for frame in stream_records(
                handle, record_tag="row", namespace=NAMESPACE, batch_rows=batch_rows
            ):
                assert frame.height <= batch_rows
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_peak_memory_tracks_the_batch_and_not_the_document(tmp_path):
    """B1's constraint in miniature: nothing bigger than one batch is ever in Python."""
    record = "".join(f"<c{index}>value-{index:04d}</c{index}>" for index in range(14))
    path = synthetic(tmp_path / "big.xml", [record] * 8000)
    document_bytes = path.stat().st_size

    small = peak_bytes(path, batch_rows=100)
    whole = peak_bytes(path, batch_rows=8000)

    assert small * 4 < whole
    assert small < document_bytes
