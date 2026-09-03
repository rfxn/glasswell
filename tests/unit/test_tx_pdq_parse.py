"""The archive reader: what it refuses, what it keys on, and which sibling it takes.

Fixtureless except for the archives themselves, which are built to the published dictionary
and not cut from the dump — `tests/fixtures/tx_pdq/SOURCE.md` says so in its first sentence, so
every count below is a claim about those files and nothing more.
"""

from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from glasswell.ingest.tx_pdq import (
    COMPLETION_COLUMNS,
    LEASE_CYCLE_MEMBER,
    WELL_COMPLETION_MEMBER,
    ArchiveFormatError,
    FilesystemPrecheckError,
    _member_rows,
    _modified,
    api10_from,
    district_labels,
    lease_key,
    member_inventory,
    precheck_filesystems,
    production_window,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tx_pdq"
SAMPLE = FIXTURES / "PDQ_DSV_sample.zip"
RESTATED = FIXTURES / "PDQ_DSV_sample_restated.zip"


def test_the_lease_key_pads_before_any_comparison() -> None:
    """LEASE_NO is VARCHAR2(6) in PDQ, PIC 9(5) in the W-10 file and padded to six in the EWA
    export, so an unpadded comparison crosses leases silently."""
    assert lease_key("O", "08", "101") == "O-08-000101"
    assert lease_key("O", "08", "000101") == lease_key("O", "08", "101")
    # The oil-gas code is in the key because one wellbore can be on an oil and a gas lease.
    assert lease_key("G", "08", "101") != lease_key("O", "08", "101")


def test_the_api10_is_built_from_the_two_parts_the_manual_names() -> None:
    assert api10_from("003", "00001") == "4200300001"
    assert api10_from("3", "1") == "4200300001"
    assert api10_from("", "00001") is None
    assert api10_from("00X", "00001") is None


def test_the_member_inventory_is_read_from_the_central_directory() -> None:
    inventory = {member.name: member for member in member_inventory(SAMPLE)}

    assert len(inventory) == 6
    assert inventory[LEASE_CYCLE_MEMBER].uncompressed > inventory[LEASE_CYCLE_MEMBER].compressed
    assert all(member.uncompressed > 0 for member in inventory.values())


def test_the_dump_states_its_own_window_rather_than_being_assumed_to_cover_one() -> None:
    with zipfile.ZipFile(SAMPLE) as archive:
        assert production_window(archive) == ("202401", "202506")
    with zipfile.ZipFile(RESTATED) as archive:
        assert production_window(archive) == ("202401", "202507")


def test_the_district_file_carries_two_vocabularies_and_the_key_is_the_number() -> None:
    """District 10 is named 08 and district 08 is named 7B, so a join on the name silently
    crosses districts."""
    with zipfile.ZipFile(SAMPLE) as archive:
        labels = district_labels(archive)

    assert labels["10"] == "08"
    assert labels["08"] == "7B"
    assert labels["11"] == "8A"
    assert labels["20"] == "State Wide"


def test_a_member_whose_header_changed_width_refuses_rather_than_quarantining(
    tmp_path: Path,
) -> None:
    """A schema change invalidates the row mapping rather than one row, so nothing failed to
    parse: the file stopped being the file the rule describes."""
    drifted = tmp_path / "drifted.zip"
    with zipfile.ZipFile(SAMPLE) as source, zipfile.ZipFile(drifted, "w") as target:
        for name in source.namelist():
            text = source.read(name).decode()
            if name == WELL_COMPLETION_MEMBER:
                header, _, body = text.partition("\n")
                text = header + "}NEW_COLUMN\n" + body
            target.writestr(name, text)

    with zipfile.ZipFile(drifted) as archive, pytest.raises(ArchiveFormatError, match="columns"):
        list(_member_rows(archive, WELL_COMPLETION_MEMBER, COMPLETION_COLUMNS))


def test_a_row_that_does_not_fit_its_own_header_refuses_too(tmp_path: Path) -> None:
    ragged = tmp_path / "ragged.zip"
    with zipfile.ZipFile(SAMPLE) as source, zipfile.ZipFile(ragged, "w") as target:
        for name in source.namelist():
            text = source.read(name).decode()
            if name == WELL_COMPLETION_MEMBER:
                lines = text.splitlines()
                lines[1] = lines[1] + "}extra"
                text = "\n".join(lines) + "\n"
            target.writestr(name, text)

    with zipfile.ZipFile(ragged) as archive, pytest.raises(ArchiveFormatError, match="fields"):
        list(_member_rows(archive, WELL_COMPLETION_MEMBER, COMPLETION_COLUMNS))


def test_the_lease_member_is_keyed_by_the_four_columns_the_manual_declares_not_null() -> None:
    """N-31. FIELD_NO is nullable on OG_LEASE_CYCLE and a nullable column does not key a table,
    which is why field_no is in neither mart primary key. The fixture asserts the premise; the
    full-scale confirmation is the load's, on the real member."""
    with zipfile.ZipFile(SAMPLE) as archive:
        rows = list(_member_rows(archive, LEASE_CYCLE_MEMBER))

    keyed = {
        (row["OIL_GAS_CODE"], row["DISTRICT_NO"], row["LEASE_NO"], row["CYCLE_YEAR_MONTH"])
        for row in rows
    }
    assert len(keyed) == len(rows) == 12120
    assert len({(row["OIL_GAS_CODE"], row["LEASE_NO"]) for row in rows}) == 1000


def test_one_wellbore_carries_two_lease_keys_in_one_dump() -> None:
    """M-16 on the fixture: the case the mart's primary key exists for."""
    with zipfile.ZipFile(SAMPLE) as archive:
        rows = list(_member_rows(archive, WELL_COMPLETION_MEMBER))

    by_api: dict[str, set[str]] = {}
    for row in rows:
        api10 = api10_from(row["API_COUNTY_CODE"], row["API_UNIQUE_NO"])
        assert api10 is not None
        by_api.setdefault(api10, set()).add(
            lease_key(row["OIL_GAS_CODE"], row["DISTRICT_NO"], row["LEASE_NO"])
        )

    doubled = {api10: keys for api10, keys in by_api.items() if len(keys) > 1}
    assert doubled == {"4200300001": {"O-08-000101", "G-08-000303"}}


def test_the_restatement_moves_one_lease_month_and_nothing_else() -> None:
    """PDQ is a full monthly re-publication, so a revised volume is a second dump rather than
    an edit — which is what makes the canonical PK's report_vintage the whole mechanism."""
    def volumes(path: Path) -> dict[tuple[str, str], str]:
        with zipfile.ZipFile(path) as archive:
            return {
                (row["LEASE_NO"], row["CYCLE_YEAR_MONTH"]): row["LEASE_OIL_PROD_VOL"]
                for row in _member_rows(archive, LEASE_CYCLE_MEMBER)
            }

    first, second = volumes(SAMPLE), volumes(RESTATED)
    moved = {key: (first[key], second[key]) for key in first if first[key] != second[key]}

    assert moved == {("000101", "202401"): ("901", "1201")}


def test_the_precheck_refuses_a_staging_area_on_another_device(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fetch.py renames `.incoming` into place, and a rename cannot cross a device: on this
    host the alternative is /tmp, the 145 GB root disk, so a 3.65 GB fetch would fill the root
    volume and then fail the rename having already spent the download."""
    root = tmp_path / "raw"
    root.mkdir()
    real = __import__("os").stat

    def crossed(path, *args, **kwargs):
        result = real(path, *args, **kwargs)
        if str(path).endswith(".incoming"):
            class Elsewhere:
                st_dev = result.st_dev + 1
            return Elsewhere()
        return result

    monkeypatch.setattr("glasswell.ingest.tx_pdq.os.stat", crossed)
    with pytest.raises(FilesystemPrecheckError, match="different device"):
        precheck_filesystems(root)


def test_the_precheck_refuses_a_raw_zone_that_cannot_hold_the_artifact(tmp_path: Path) -> None:
    with pytest.raises(FilesystemPrecheckError, match="available"):
        precheck_filesystems(tmp_path / "raw", needed=1 << 62)


def test_the_precheck_reports_the_headroom_it_measured(tmp_path: Path) -> None:
    report = precheck_filesystems(tmp_path / "raw", needed=1)

    assert report["same_device"] is True
    assert report["available_bytes"] > 0
    assert report["needed_bytes"] == 1


def test_the_pgdata_gate_is_asserted_before_the_fetch_not_during_the_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """canonical is append-only, so a half-promoted vintage is a state somebody has to reason
    about. The runbook's own sentence is `< 40 GB available: stop, escalate`, and the headroom
    is faked rather than read: a workstation with a big disk would pass this by accident."""
    from glasswell.ingest.tx_pdq import PGDATA_GATE_BYTES

    assert PGDATA_GATE_BYTES == 40 * 1024**3
    monkeypatch.setattr(
        "glasswell.ingest.tx_pdq._available",
        lambda path: 1 << 40 if "raw" in str(path) else PGDATA_GATE_BYTES - 1,
    )
    with pytest.raises(FilesystemPrecheckError, match="stops and escalates"):
        precheck_filesystems(tmp_path / "raw", needed=1, pgdata=tmp_path / "pgdata")

    monkeypatch.setattr("glasswell.ingest.tx_pdq._available", lambda path: 1 << 40)
    report = precheck_filesystems(tmp_path / "raw", needed=1, pgdata=tmp_path / "pgdata")
    assert report["pgdata_available_bytes"] == 1 << 40


def test_the_portal_stamp_is_parsed_as_the_portal_writes_it() -> None:
    assert _modified("8/25/26 6:02:13 AM") == datetime(2026, 8, 25, 6, 2, 13, tzinfo=UTC)
    assert _modified("9/24/21 6:03:12 AM") == datetime(2021, 9, 24, 6, 3, 12, tzinfo=UTC)
    assert _modified("12/9/21 7:41:38 AM") < _modified("8/25/26 6:00:51 AM")
