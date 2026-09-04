"""The archive reader: what it refuses, what it keys on, and which sibling it takes.

Fixtureless except for the archives themselves, which are built to the published dictionary
and not cut from the dump — `tests/fixtures/tx_pdq/SOURCE.md` says so in its first sentence, so
every count below is a claim about those files and nothing more.
"""

from __future__ import annotations

import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from glasswell.ingest.tx_pdq import (
    COMPLETION_COLUMNS,
    LEASE_CYCLE_MEMBER,
    WELL_COMPLETION_MEMBER,
    ArchiveFormatError,
    FilesystemPrecheckError,
    MemberLayout,
    _member_rows,
    _modified,
    api10_from,
    district_labels,
    lease_key,
    member_inventory,
    member_layout,
    precheck_filesystems,
    production_window,
)
from glasswell.lineage.models import ConformanceRule
from glasswell.seed.conformance_tx import PDQ_MEMBER_LAYOUT, TX_RULES

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tx_pdq"
SAMPLE = FIXTURES / "PDQ_DSV_sample.zip"
RESTATED = FIXTURES / "PDQ_DSV_sample_restated.zip"

# What load() resolves from the database, built here from the same registry the rule row is
# published from, so a unit test needs no connection to be judged by the rule in force.
LAYOUT = MemberLayout("cr_tx_pdq_format_2", PDQ_MEMBER_LAYOUT)

# The six members' own first lines as measured on the 2026-09-04 fetch, written out here a
# third time on purpose. The registry publishes them and build_fixtures.py writes them into the
# archives; this block is neither, so the three transcriptions hold each other rather than one
# of them being derived from another and agreeing with itself.
MEASURED_HEADERS: dict[str, tuple[str, ...]] = {
    "GP_COUNTY_DATA_TABLE.dsv": (
        "COUNTY_NO", "COUNTY_FIPS_CODE", "COUNTY_NAME", "DISTRICT_NO", "DISTRICT_NAME",
        "ON_SHORE_FLAG", "ONSHORE_ASSC_CNTY_FLAG",
    ),
    "GP_DISTRICT_DATA_TABLE.dsv": (
        "DISTRICT_NO", "DISTRICT_NAME", "OFFICE_PHONE_NO", "OFFICE_LOCATION",
    ),
    "GP_DATE_RANGE_CYCLE_DATA_TABLE.dsv": (
        "OLDEST_PROD_CYCLE_YEAR_MONTH", "NEWEST_PROD_CYCLE_YEAR_MONTH",
        "NEWEST_SCHED_CYCLE_YEAR_MONTH", "GAS_EXTRACT_DATE", "OIL_EXTRACT_DATE",
    ),
    "OG_LEASE_CYCLE_DATA_TABLE.dsv": (
        "OIL_GAS_CODE", "DISTRICT_NO", "LEASE_NO", "CYCLE_YEAR", "CYCLE_MONTH",
        "CYCLE_YEAR_MONTH", "LEASE_NO_DISTRICT_NO", "OPERATOR_NO", "FIELD_NO", "FIELD_TYPE",
        "GAS_WELL_NO", "PROD_REPORT_FILED_FLAG", "LEASE_OIL_PROD_VOL", "LEASE_OIL_ALLOW",
        "LEASE_OIL_ENDING_BAL", "LEASE_GAS_PROD_VOL", "LEASE_GAS_ALLOW",
        "LEASE_GAS_LIFT_INJ_VOL", "LEASE_COND_PROD_VOL", "LEASE_COND_LIMIT",
        "LEASE_COND_ENDING_BAL", "LEASE_CSGD_PROD_VOL", "LEASE_CSGD_LIMIT",
        "LEASE_CSGD_GAS_LIFT", "LEASE_OIL_TOT_DISP", "LEASE_GAS_TOT_DISP",
        "LEASE_COND_TOT_DISP", "LEASE_CSGD_TOT_DISP", "DISTRICT_NAME", "LEASE_NAME",
        "OPERATOR_NAME", "FIELD_NAME",
    ),
    "OG_WELL_COMPLETION_DATA_TABLE.dsv": (
        "OIL_GAS_CODE", "DISTRICT_NO", "LEASE_NO", "WELL_NO", "API_COUNTY_CODE",
        "API_UNIQUE_NO", "ONSHORE_ASSC_CNTY", "DISTRICT_NAME", "COUNTY_NAME",
        "OIL_WELL_UNIT_NO", "WELL_ROOT_NO", "WELLBORE_SHUTIN_DT", "WELL_SHUTIN_DT",
        "WELL_14B2_STATUS_CODE", "WELL_SUBJECT_14B2_FLAG", "WELLBORE_LOCATION_CODE",
    ),
    "OG_REGULATORY_LEASE_DW_DATA_TABLE.dsv": (
        "OIL_GAS_CODE", "DISTRICT_NO", "LEASE_NO", "DISTRICT_NAME", "LEASE_NAME",
        "OPERATOR_NO", "OPERATOR_NAME", "FIELD_NO", "FIELD_NAME", "WELL_NO",
        "LEASE_OFF_SCHED_FLAG", "LEASE_SEVERANCE_FLAG",
    ),
}


def seeded_rule(rule_id: str) -> ConformanceRule:
    declared = next(row for row in TX_RULES if row["rule_id"] == rule_id)
    return ConformanceRule(
        rule_id=str(declared["rule_id"]),
        rule_family=str(declared["rule_id"])[:-2],
        source_id=str(declared["source_id"]),
        stage=str(declared["stage"]),
        rule_kind=str(declared["rule_kind"]),
        applies_to_fields=list(declared["applies_to_fields"]),  # type: ignore[arg-type]
        spec=dict(declared["spec"]),  # type: ignore[arg-type]
        rule=str(declared["rule"]),
        rationale=str(declared["rationale"]),
        effective_from=date(2026, 9, 4),
    )


def rewritten(path: Path, target: Path, member: str, header: tuple[str, ...]) -> Path:
    """The sample archive with one member's header line replaced and its rows untouched."""
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(target, "w") as sink:
        for name in source.namelist():
            body = source.read(name).decode()
            if name == member:
                body = "}".join(header) + "\n" + body.partition("\n")[2]
            sink.writestr(name, body)
    return target


def header_of(path: Path, member: str) -> tuple[str, ...]:
    with zipfile.ZipFile(path) as archive, archive.open(member) as handle:
        return tuple(handle.readline().decode().rstrip("\r\n").split("}"))


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
        assert production_window(archive, LAYOUT) == ("202401", "202506")
    with zipfile.ZipFile(RESTATED) as archive:
        assert production_window(archive, LAYOUT) == ("202401", "202507")


def test_the_district_file_carries_two_vocabularies_and_the_key_is_the_number() -> None:
    """District 10 is named 08 and district 08 is named 7B, so a join on the name silently
    crosses districts."""
    with zipfile.ZipFile(SAMPLE) as archive:
        labels = district_labels(archive, LAYOUT)

    assert labels["10"] == "08"
    assert labels["08"] == "7B"
    assert labels["11"] == "8A"
    assert labels["20"] == "State Wide"


@pytest.mark.parametrize("member", sorted(MEASURED_HEADERS))
def test_the_rule_publishes_the_header_that_was_measured(member: str) -> None:
    """R8's half of it: the layout is a registry row, so this is what a reader of /conformance
    is shown and what the parse is judged against."""
    assert tuple(PDQ_MEMBER_LAYOUT[member]["header"]) == MEASURED_HEADERS[member]


@pytest.mark.parametrize("member", sorted(MEASURED_HEADERS))
@pytest.mark.parametrize("archive", [SAMPLE, RESTATED], ids=["sample", "restated"])
def test_the_fixture_archives_carry_the_header_that_was_measured(
    archive: Path, member: str
) -> None:
    """Built, not cut -- so the one thing these archives must get right is the shape, and a
    fixture built to a transcription is what let a thirteen-column parser look correct."""
    assert header_of(archive, member) == MEASURED_HEADERS[member]


def test_a_renamed_consumed_column_refuses_where_a_width_check_would_not(
    tmp_path: Path,
) -> None:
    """The rename the old check could not see: same column count, a column the parse reads
    gone under a new name, and every row silently re-mapped."""
    header = tuple(
        "API_UNIQUE_NUM" if column == "API_UNIQUE_NO" else column
        for column in MEASURED_HEADERS[WELL_COMPLETION_MEMBER]
    )
    drifted = rewritten(SAMPLE, tmp_path / "renamed.zip", WELL_COMPLETION_MEMBER, header)

    with zipfile.ZipFile(drifted) as archive, pytest.raises(ArchiveFormatError) as refusal:
        list(_member_rows(archive, WELL_COMPLETION_MEMBER, LAYOUT))

    message = str(refusal.value)
    assert "does not carry API_UNIQUE_NO" in message
    assert "carries API_UNIQUE_NUM, which the rule does not list" in message
    assert "cr_tx_pdq_format_2" in message


def test_a_reordered_header_refuses_though_every_name_is_present(tmp_path: Path) -> None:
    """A reorder survives a dict-keyed read, so nothing would break today. It still refuses:
    the rule states an order it measured, and a member that reordered is a source that moved."""
    measured = MEASURED_HEADERS[WELL_COMPLETION_MEMBER]
    header = (measured[1], measured[0], *measured[2:])
    drifted = rewritten(SAMPLE, tmp_path / "reordered.zip", WELL_COMPLETION_MEMBER, header)

    with zipfile.ZipFile(drifted) as archive, pytest.raises(ArchiveFormatError) as refusal:
        list(_member_rows(archive, WELL_COMPLETION_MEMBER, LAYOUT))

    message = str(refusal.value)
    assert "reorders DISTRICT_NO where the rule has OIL_GAS_CODE" in message
    assert "cr_tx_pdq_format_2" in message


def test_a_consumed_column_that_vanished_refuses_naming_it(tmp_path: Path) -> None:
    header = tuple(
        column for column in MEASURED_HEADERS[LEASE_CYCLE_MEMBER]
        if column != "LEASE_CSGD_PROD_VOL"
    )
    drifted = rewritten(SAMPLE, tmp_path / "lost.zip", LEASE_CYCLE_MEMBER, header)

    with zipfile.ZipFile(drifted) as archive, pytest.raises(
        ArchiveFormatError, match="does not carry LEASE_CSGD_PROD_VOL"
    ):
        list(_member_rows(archive, LEASE_CYCLE_MEMBER, LAYOUT))


def test_the_lease_member_is_judged_too_and_was_read_against_nothing(tmp_path: Path) -> None:
    """The asymmetry this closed: OG_LEASE_CYCLE and the two GP members were read with no
    expected layout at all, so a renamed volume column reached the promotion as a KeyError
    rather than as a refusal naming the rule."""
    measured = MEASURED_HEADERS[LEASE_CYCLE_MEMBER]
    header = (*measured[:-1], "FIELD_NAME_2")
    drifted = rewritten(SAMPLE, tmp_path / "lease.zip", LEASE_CYCLE_MEMBER, header)

    with zipfile.ZipFile(drifted) as archive, pytest.raises(
        ArchiveFormatError, match="FIELD_NAME_2, which the rule does not list"
    ):
        list(_member_rows(archive, LEASE_CYCLE_MEMBER, LAYOUT))


def test_the_three_columns_the_parse_never_reads_are_carried_and_read_past() -> None:
    """The whole point of listing sixteen and consuming thirteen: the extra columns are the
    rule's, not the parser's, and the parse neither refuses them nor stages them."""
    with zipfile.ZipFile(SAMPLE) as archive:
        row = next(_member_rows(archive, WELL_COMPLETION_MEMBER, LAYOUT))

    assert len(row) == 16
    assert len(COMPLETION_COLUMNS) == 13
    unread = {"DISTRICT_NAME", "COUNTY_NAME", "OIL_WELL_UNIT_NO"}
    assert unread <= set(row)
    assert unread.isdisjoint(column.upper() for column in COMPLETION_COLUMNS)


def test_a_rule_that_publishes_no_layout_refuses_rather_than_parsing_unjudged() -> None:
    """The founding row is still resolvable, and a deploy whose published_vintage has not been
    reached leaves it in force. It describes no columns, so nothing may be parsed against it."""
    with pytest.raises(ArchiveFormatError, match="publishes no member layout"):
        member_layout(seeded_rule("cr_tx_pdq_format_1"))


def test_a_layout_this_tree_does_not_register_refuses_rather_than_reading_by_luck() -> None:
    """Two clocks reach a header. A database seeded by an older tree would judge the file
    against its layout and read the row against this one, and the disagreement would surface as
    a KeyError on a column nobody named."""
    stale = seeded_rule("cr_tx_pdq_format_2")
    members = {member: dict(layout) for member, layout in stale.spec["members"].items()}
    members[WELL_COMPLETION_MEMBER] = {
        "header": members[WELL_COMPLETION_MEMBER]["header"][:13],
        "consumed": members[WELL_COMPLETION_MEMBER]["consumed"],
    }
    stale = stale.model_copy(update={"spec": {**stale.spec, "members": members}})

    with pytest.raises(
        ArchiveFormatError, match="a layout this tree does not register, at OG_WELL_COMPLETION"
    ):
        member_layout(stale)


def test_a_member_the_rule_describes_no_layout_for_refuses() -> None:
    partial = MemberLayout(
        "cr_tx_pdq_format_2",
        {member: PDQ_MEMBER_LAYOUT[member] for member in (LEASE_CYCLE_MEMBER,)},
    )

    with pytest.raises(ArchiveFormatError, match="describes no layout for this member"):
        partial.header_for(WELL_COMPLETION_MEMBER)


def test_a_member_whose_header_grew_a_column_refuses_rather_than_quarantining(
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

    with zipfile.ZipFile(drifted) as archive, pytest.raises(
        ArchiveFormatError, match="NEW_COLUMN, which the rule does not list"
    ):
        list(_member_rows(archive, WELL_COMPLETION_MEMBER, LAYOUT))


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
        list(_member_rows(archive, WELL_COMPLETION_MEMBER, LAYOUT))


def test_the_lease_member_is_keyed_by_the_four_columns_the_manual_declares_not_null() -> None:
    """N-31. FIELD_NO is nullable on OG_LEASE_CYCLE and a nullable column does not key a table,
    which is why field_no is in neither mart primary key. The fixture asserts the premise; the
    full-scale confirmation is the load's, on the real member."""
    with zipfile.ZipFile(SAMPLE) as archive:
        rows = list(_member_rows(archive, LEASE_CYCLE_MEMBER, LAYOUT))

    keyed = {
        (row["OIL_GAS_CODE"], row["DISTRICT_NO"], row["LEASE_NO"], row["CYCLE_YEAR_MONTH"])
        for row in rows
    }
    assert len(keyed) == len(rows) == 12120
    assert len({(row["OIL_GAS_CODE"], row["LEASE_NO"]) for row in rows}) == 1000


def test_one_wellbore_carries_two_lease_keys_in_one_dump() -> None:
    """M-16 on the fixture: the case the mart's primary key exists for."""
    with zipfile.ZipFile(SAMPLE) as archive:
        rows = list(_member_rows(archive, WELL_COMPLETION_MEMBER, LAYOUT))

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
                for row in _member_rows(archive, LEASE_CYCLE_MEMBER, LAYOUT)
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
