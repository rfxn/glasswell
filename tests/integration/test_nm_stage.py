"""Staging the NM artifacts: verbatim, reconciled, and re-runnable.

The fixtures are real `SqlRowSet1` documents cut from the one polite pull, re-zipped here so the
whole path runs — fetch, manifest, zip member, streaming reader, rules, staging. The production
spine lands as Parquet and the eight siblings as text rows, which is the only place in the
codebase where one ingest writes two stores.
"""

from __future__ import annotations

import zipfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import psycopg
import pytest

from glasswell.ingest import nm_ocd
from glasswell.ingest.base import open_ingest_run
from glasswell.ingest.xml_stream import MalformedRecordStream
from glasswell.lineage import ftp as ftp_module
from glasswell.lineage.conformance import load_rules, rule_for_family
from glasswell.seed import seed_all
from glasswell.seed.conformance_nm import NM_COLUMNS
from glasswell.staging.duck import STAGING_ROOT_ENV, file_sha256
from tests.support.fakes import FixedClock

FIXTURES = Path(__file__).parents[1] / "fixtures" / "nm_ocd"
SPINE = "wcproduction"
SPINE_SOURCE = "nm_ocd_wcproduction"
RECORDS = 300
DAY_ONE = datetime(2026, 8, 20, 6, 15, 0, tzinfo=UTC)
NAMESPACE = "urn:schemas-microsoft-com:sql:SqlRowSet1"


def fixture_for(table: str) -> Path:
    return FIXTURES / f"nm_{table}_300.xml"


def zipped(tmp_path: Path, table: str, document: bytes) -> bytes:
    archive = tmp_path / f"{table}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(f"{table}.xml", document)
    return archive.read_bytes()


def synthetic_document(records: list[str], *, tag: str = SPINE) -> bytes:
    body = "".join(f'<{tag} xmlns="{NAMESPACE}">{record}</{tag}>' for record in records)
    document = (
        '<root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f'<xsd:schema targetNamespace="{NAMESPACE}"'
        ' xmlns:xsd="http://www.w3.org/2001/XMLSchema"></xsd:schema>'
        f"{body}</root>"
    )
    return document.encode("utf-16")


def record_text(**cells: str) -> str:
    return "".join(f"<{name}>{value}</{name}>" for name, value in cells.items())


def full_record(**overrides: str) -> str:
    cells = {column: "1" for column in NM_COLUMNS[SPINE]}
    cells.update(prd_knd_cde="O ", prodn_yr="2015", prodn_mth="7")
    cells.update(overrides)
    return record_text(**cells)


class FakeFtp:
    payload: bytes = b""

    def __init__(self, timeout: float | None = None) -> None:
        self.timeout = timeout

    def connect(self, host: str, port: int = 21) -> str:
        return "220 ready"

    def login(self, user: str = "", passwd: str = "") -> str:
        return "230 logged in"

    def set_pasv(self, value: bool) -> None:
        return None

    def voidcmd(self, command: str) -> str:
        return f"200 {command}"

    def sendcmd(self, command: str) -> str:
        return "213 20260819225600"

    def size(self, path: str) -> int:
        return len(type(self).payload)

    def retrbinary(self, command: str, callback, blocksize: int = 8192) -> str:
        payload = type(self).payload
        for start in range(0, len(payload), blocksize):
            callback(payload[start : start + blocksize])
        return "226 transfer complete"

    def quit(self) -> str:
        return "221 bye"

    def close(self) -> None:
        return None


@pytest.fixture
def staging_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "staging"
    monkeypatch.setenv(STAGING_ROOT_ENV, str(root))
    return root


@pytest.fixture
def seeded(db: psycopg.Connection) -> None:
    seed_all(db)
    db.commit()


def stage(
    db: psycopg.Connection,
    raw_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    table: str = SPINE,
    document: bytes | None = None,
    batch_rows: int | None = None,
    at: datetime = DAY_ONE,
) -> nm_ocd.StageReport:
    payload = document if document is not None else fixture_for(table).read_bytes()
    FakeFtp.payload = zipped(tmp_path, table, payload)
    monkeypatch.setattr(ftp_module, "FTP", FakeFtp)
    with open_ingest_run(
        db, source_id=nm_ocd.source_id_for(table), raw_root=raw_root, clock=FixedClock(at)
    ) as run:
        nm_ocd.fetch_table(run, table)
        report = nm_ocd.stage_table(
            run,
            table,
            manifest=nm_ocd.head_manifest(db, nm_ocd.source_id_for(table)),
            batch_rows=batch_rows,
        )
    db.commit()
    return report


def query(db: psycopg.Connection, sql: str, *parameters: object) -> list[tuple]:
    with db.cursor() as cursor:
        cursor.execute(sql, parameters or None)
        return cursor.fetchall()


def scalar(db: psycopg.Connection, sql: str, *parameters: object):
    return query(db, sql, *parameters)[0][0]


@pytest.fixture
def staged_spine(db, seeded, raw_root, staging_root, tmp_path, monkeypatch):
    return stage(db, raw_root, tmp_path, monkeypatch)


def test_the_spine_stages_every_record_to_parquet_and_nothing_to_postgres(db, staged_spine):
    assert staged_spine.parsed_rows == staged_spine.staged_rows == RECORDS
    assert staged_spine.quarantined == {}
    assert staged_spine.staging_table == "staging.stg_nm_ocd_wcproduction__partitions"
    assert (
        scalar(
            db,
            "select count(*) from information_schema.tables where table_schema = 'staging'"
            " and table_name = 'stg_nm_ocd_wcproduction__records'",
        )
        == 0
    )


def test_the_partition_registry_addresses_the_file_that_was_written(db, staged_spine):
    registered = query(
        db,
        "select manifest_id, parquet_uri, rows, sha256, sort_order"
        f" from {nm_ocd.PARTITION_TABLE}",
    )

    assert registered == [
        (
            staged_spine.manifest_id,
            staged_spine.parquet_uri,
            RECORDS,
            staged_spine.parquet_sha256,
            "source_row_ordinal",
        )
    ]
    assert file_sha256(staged_spine.parquet_uri) == staged_spine.parquet_sha256


def test_the_staged_columns_are_the_source_children_and_nothing_is_coerced(staged_spine):
    frame = pl.read_parquet(staged_spine.parquet_uri)

    assert frame.columns == ["source_row_ordinal", *NM_COLUMNS[SPINE]]
    assert set(frame.schema.values()) == {pl.Int64, pl.String}
    assert frame.schema["prod_amt"] == pl.String
    assert frame.schema["prodn_yr"] == pl.String


def test_the_row_ordinal_is_dense_and_zero_based(staged_spine):
    ordinals = pl.read_parquet(staged_spine.parquet_uri)["source_row_ordinal"].to_list()

    assert ordinals == list(range(RECORDS))


def test_the_stream_code_stages_at_width_two_and_trims_to_one_under_its_rule(db, staged_spine):
    """B5. Staging keeps 'O '; the width-2 trim is a rule row, so the map can match 'O'."""
    staged = pl.read_parquet(staged_spine.parquet_uri)["prd_knd_cde"].to_list()
    rules = load_rules(db, source_id=SPINE_SOURCE, stage="parse")
    trim = rule_for_family(rules, "cr_nm_wcproduction_pad").spec["trim"]["prd_knd_cde"]

    assert {len(value) for value in staged} == {2}
    assert set(staged) <= {"G ", "O ", "W ", "C "}
    assert trim == {"width": 2, "side": "right", "char": " "}
    assert {value.rstrip(trim["char"]) for value in staged} <= {"G", "O", "W", "C"}
    assert {len(value.rstrip(trim["char"])) for value in staged} == {1}


def test_the_declared_header_matches_the_staging_ddl_for_every_source(db, seeded):
    for table in nm_ocd.TABLES:
        if table == SPINE:
            continue
        rules = load_rules(db, source_id=nm_ocd.source_id_for(table), stage="parse")
        declared = rule_for_family(rules, f"cr_nm_{table}_parse").spec["expected_columns"]
        columns = [
            row[0]
            for row in query(
                db,
                "select column_name from information_schema.columns"
                " where table_schema = 'staging' and table_name = %s"
                " and column_name not in ('manifest_id', 'source_row_ordinal', 'ingested_at')"
                " order by ordinal_position",
                f"stg_nm_ocd_{table}__records",
            )
        ]
        assert declared == columns, table
        assert declared == list(NM_COLUMNS[table]), table


def test_a_sibling_table_stages_verbatim_rows_with_their_char_padding(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
):
    report = stage(db, raw_root, tmp_path, monkeypatch, table="pool")

    assert report.staging_table == "staging.stg_nm_ocd_pool__records"
    assert report.staged_rows == scalar(db, "select count(*) from staging.stg_nm_ocd_pool__records")
    assert query(
        db,
        "select min(source_row_ordinal), max(source_row_ordinal), count(*)"
        " from staging.stg_nm_ocd_pool__records",
    ) == [(0, report.staged_rows - 1, report.staged_rows)]
    padded = scalar(
        db,
        "select count(*) from staging.stg_nm_ocd_pool__records where pool_nam like '%% '",
    )
    assert padded > 0


def test_the_parse_derivation_carries_the_reconciliation_and_cites_its_rule(db, staged_spine):
    params, rows = query(
        db,
        "select params, output_rows from lineage.derivations where operation = 'stage.parse'",
    )[0]
    cited = query(
        db,
        "select r.rule_id, r.applied_rows from lineage.derivation_rules r"
        "  join lineage.derivations d on d.derivation_id = r.derivation_id"
        " where d.operation = 'stage.parse' order by r.rule_id",
    )

    assert params["parsed_rows"] == params["staged_rows"] == RECORDS
    assert params["quarantined_rows"] == 0
    assert rows == RECORDS
    assert ("cr_nm_wcproduction_parse_1", RECORDS) in cited
    assert ("cr_nm_wcproduction_pad_1", 0) in cited
    assert [rule_id for rule_id, _ in cited if "host_pin" in rule_id] == []


def test_the_load_is_announced_with_the_counts_it_reconciled(db, staged_spine):
    payload = scalar(
        db,
        "select payload from lineage.audit_events where event_type = 'staging.load_completed'",
    )

    assert payload["rows"] == RECORDS
    assert payload["parsed_rows"] == RECORDS
    assert payload["quarantined_rows"] == 0
    assert payload["table"] == nm_ocd.PARTITION_TABLE


def test_restaging_the_same_manifest_writes_the_same_bytes_and_no_second_derivation(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
):
    first = stage(db, raw_root, tmp_path, monkeypatch)
    derivations = scalar(
        db, "select count(*) from lineage.derivations where operation = 'stage.parse'"
    )

    second = stage(db, raw_root, tmp_path, monkeypatch)

    assert second.parquet_sha256 == first.parquet_sha256
    assert second.derivation_id == first.derivation_id
    assert (
        scalar(db, "select count(*) from lineage.derivations where operation = 'stage.parse'")
        == derivations
    )
    assert scalar(db, f"select count(*) from {nm_ocd.PARTITION_TABLE}") == 1


def test_restaging_a_sibling_replaces_its_rows_rather_than_doubling_them(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
):
    stage(db, raw_root, tmp_path, monkeypatch, table="pool")
    rows = scalar(db, "select count(*) from staging.stg_nm_ocd_pool__records")

    stage(db, raw_root, tmp_path, monkeypatch, table="pool")

    assert scalar(db, "select count(*) from staging.stg_nm_ocd_pool__records") == rows


def test_the_batch_size_does_not_change_what_is_staged(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
):
    whole = stage(db, raw_root, tmp_path, monkeypatch, batch_rows=65536)
    digest = whole.parquet_sha256
    Path(whole.parquet_uri).unlink()

    batched = stage(db, raw_root, tmp_path, monkeypatch, batch_rows=64)

    assert batched.parquet_sha256 == digest
    assert batched.staged_rows == RECORDS


def test_a_batch_that_lost_a_declared_column_is_quarantined_not_staged(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
):
    without_pool = full_record()
    cells = {column: "1" for column in NM_COLUMNS[SPINE] if column != "pool_idn"}
    document = synthetic_document([record_text(**cells)] * 2)
    assert "pool_idn" in without_pool

    report = stage(db, raw_root, tmp_path, monkeypatch, document=document)

    assert report.parsed_rows == 2
    assert report.staged_rows == 0
    assert report.quarantined == {"schema_mismatch": 2}
    assert report.parquet_uri is None
    assert scalar(db, f"select count(*) from {nm_ocd.PARTITION_TABLE}") == 0
    assert query(
        db,
        "select reason_code, rule_id, staging_table from lineage.quarantine_rows",
    ) == [("schema_mismatch", "cr_nm_wcproduction_parse_1", nm_ocd.PARTITION_TABLE)] * 2


def test_a_parsed_row_that_is_neither_staged_nor_quarantined_halts_the_load(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
):
    """SB-01 §3.5's invariant, shown firing rather than narrated: a row that leaves the frame
    without a reason code is the silent loss the whole ledger is built to make impossible."""
    applied = nm_ocd.apply_rules

    def losing(frame: pl.DataFrame, rules):
        application = applied(frame, rules)
        kept = application.frame
        return replace(application, frame=kept.head(max(kept.height - 1, 0)))

    monkeypatch.setattr(nm_ocd, "apply_rules", losing)

    with pytest.raises(nm_ocd.RowCountMismatch, match="every parsed row is one or the other"):
        stage(db, raw_root, tmp_path, monkeypatch)
    db.rollback()

    assert scalar(db, f"select count(*) from {nm_ocd.PARTITION_TABLE}") == 0


def test_a_column_nobody_declared_halts_the_load(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
):
    document = synthetic_document([full_record(surprise_col="9")])

    with pytest.raises(nm_ocd.SchemaDrift, match="surprise_col"):
        stage(db, raw_root, tmp_path, monkeypatch, document=document)

    assert scalar(db, f"select count(*) from {nm_ocd.PARTITION_TABLE}") == 0
    assert scalar(
        db,
        "select count(*) from lineage.derivations"
        " where operation = 'stage.parse' and status = 'failed'",
    ) == 1


def test_an_archive_that_does_not_hold_the_declared_member_halts(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
):
    archive = tmp_path / "wrong.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("something_else.xml", b"\xff\xfe")
    FakeFtp.payload = archive.read_bytes()
    monkeypatch.setattr(ftp_module, "FTP", FakeFtp)

    with open_ingest_run(
        db, source_id=SPINE_SOURCE, raw_root=raw_root, clock=FixedClock(DAY_ONE)
    ) as run:
        nm_ocd.fetch_table(run, SPINE)
        manifest = nm_ocd.head_manifest(db, SPINE_SOURCE)
        with pytest.raises(nm_ocd.SchemaDrift, match=r"wcproduction\.xml"):
            nm_ocd.stage_table(run, SPINE, manifest=manifest)


def test_a_truncated_member_halts_and_stages_nothing(
    db, seeded, raw_root, staging_root, tmp_path, monkeypatch
):
    """A partial artifact staged as if it were whole is the corruption this phase prevents.

    The reader hands on what parsed before naming where it stopped, so the rows are not lost to
    the caller; staging refuses them, because a promotion cannot tell a truncated member from a
    short one and would publish the difference as a decline.
    """
    whole = synthetic_document([full_record()] * 4).decode("utf-16")
    document = (whole[: whole.index("</root>")] + "<wcproduction><api_st_cde>").encode("utf-16")

    with pytest.raises(MalformedRecordStream, match="not well-formed"):
        stage(db, raw_root, tmp_path, monkeypatch, document=document, batch_rows=2)

    db.rollback()
    assert scalar(db, f"select count(*) from {nm_ocd.PARTITION_TABLE}") == 0
    assert list(staging_root.rglob("*.parquet")) == []


def test_the_serving_role_has_no_privilege_on_nm_staging(db, staged_spine):
    """SB-01 §3.1.4, with D1's pipeline grants; test_layer_boundary.py owns the schema-wide form."""
    granted = query(
        db,
        "select table_name, privilege_type from information_schema.table_privileges"
        " where grantee = 'glasswell_api' and table_schema = 'staging'",
    )

    assert granted == []
    assert (
        scalar(
            db,
            "select count(*) from information_schema.table_privileges"
            " where grantee = 'glasswell_pipeline' and table_schema = 'staging'"
            " and table_name = 'stg_nm_ocd_wcproduction__partitions'"
            " and privilege_type in ('SELECT', 'INSERT', 'DELETE')",
        )
        == 3
    )
