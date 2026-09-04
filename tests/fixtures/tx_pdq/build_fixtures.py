"""Build the PDQ fixture archives.

Built, not cut. The dump is 3.65 GB behind a GoAnywhere postback that ignores `Range`, so
there is no partial fetch and no development worktree holds a copy: the archive lands on the
deployed host once, through the runbook. Every column name, width, nullability and delimiter
here is read from the published data dictionary (`SOURCE.md` records the URL, the byte count
and the sha256 of the PDF it was read from); the rows are constructed to exercise the cases
`cr_tx_allocation_v0_1` decides. A count taken from these files is a fact about these files.

    python tests/fixtures/tx_pdq/build_fixtures.py
"""

from __future__ import annotations

import zipfile
from pathlib import Path

DELIMITER = "}"
VINTAGE_ONE = "PDQ_DSV_sample.zip"
VINTAGE_TWO = "PDQ_DSV_sample_restated.zip"

# In-scope: Andrews (003) and Ector (135) are both in PERMIAN_COUNTY_CODES. Anderson (001) is
# not, which is what gives the promotion an out-of-scope row to count rather than quarantine.
IN_SCOPE_COUNTY = "003"
SECOND_COUNTY = "135"
OUT_OF_SCOPE_COUNTY = "001"

LEASE_CYCLE_HEADER = (
    "OIL_GAS_CODE", "DISTRICT_NO", "LEASE_NO", "CYCLE_YEAR_MONTH", "OPERATOR_NO", "FIELD_NO",
    "FIELD_TYPE", "GAS_WELL_NO", "PROD_REPORT_FILED_FLAG", "LEASE_OIL_PROD_VOL",
    "LEASE_GAS_PROD_VOL", "LEASE_COND_PROD_VOL", "LEASE_CSGD_PROD_VOL", "LEASE_NAME",
    "OPERATOR_NAME", "FIELD_NAME",
)
WELL_COMPLETION_HEADER = (
    "OIL_GAS_CODE", "DISTRICT_NO", "LEASE_NO", "WELL_NO", "API_COUNTY_CODE", "API_UNIQUE_NO",
    "ONSHORE_ASSC_CNTY", "WELL_ROOT_NO", "WELLBORE_SHUTIN_DT", "WELL_SHUTIN_DT",
    "WELL_14B2_STATUS_CODE", "WELL_SUBJECT_14B2_FLAG", "WELLBORE_LOCATION_CODE",
)
REGULATORY_LEASE_HEADER = (
    "OIL_GAS_CODE", "DISTRICT_NO", "LEASE_NO", "DISTRICT_NAME", "LEASE_NAME", "OPERATOR_NO",
    "OPERATOR_NAME", "FIELD_NO", "FIELD_NAME", "WELL_NO", "LEASE_OFF_SCHED_FLAG",
    "LEASE_SEVERANCE_FLAG",
)
COUNTY_HEADER = (
    "COUNTY_NO", "COUNTY_FIPS_CODE", "COUNTY_NAME", "DISTRICT_NO", "DISTRICT_NAME",
    "ON_SHORE_FLAG", "ONSHORE_ASSC_CNTY_FLAG",
)
DISTRICT_HEADER = ("DISTRICT_NO", "DISTRICT_NAME", "OFFICE_PHONE_NO", "OFFICE_LOCATION")
DATE_RANGE_HEADER = (
    "OLDEST_PROD_CYCLE_YEAR_MONTH", "NEWEST_PROD_CYCLE_YEAR_MONTH",
    "NEWEST_SCHED_CYCLE_YEAR_MONTH", "GAS_EXTRACT_DATE", "OIL_EXTRACT_DATE",
)

# Measured on the live 2026-08-27 archive and quoted in the spec: the district file carries two
# vocabularies, so a join on the name silently crosses districts.
DISTRICTS = (
    ("01", "01"), ("02", "02"), ("03", "03"), ("04", "04"), ("05", "05"), ("06", "06"),
    ("07", "6E"), ("08", "7B"), ("09", "7C"), ("10", "08"), ("11", "8A"), ("12", "12"),
    ("13", "09"), ("14", "10"), ("20", "State Wide"),
)

MONTHS = tuple(
    f"{year}{month:02d}" for year in (2024, 2025) for month in range(1, 13)
)
BULK_LEASE_COUNT = 990


def _row(values: tuple[str, ...]) -> str:
    return DELIMITER.join(values)


def _member(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    return "\n".join([_row(header), *(_row(row) for row in rows)]) + "\n"


def _lease_cycle_row(
    code: str,
    lease_no: str,
    month: str,
    *,
    oil: str = "",
    gas: str = "",
    cond: str = "",
    csgd: str = "",
    gas_well_no: str = "",
    filed: str = "Y",
    field_no: str = "00123456",
) -> tuple[str, ...]:
    return (
        code, "08", lease_no, month, "123456", field_no, "OI" if code == "O" else "GA",
        gas_well_no, filed, oil, gas, cond, csgd, f"LEASE {lease_no}", "SAMPLE OPERATOR",
        "SAMPLE FIELD",
    )


def _completion_row(
    code: str,
    lease_no: str,
    well_no: str,
    county: str,
    unique_no: str,
    *,
    shutin: str = "",
    status_14b2: str = "",
) -> tuple[str, ...]:
    return (
        code, "08", lease_no, well_no, county, unique_no, "", f"W{unique_no}", "", shutin,
        status_14b2, "N" if not status_14b2 else "Y", "1",
    )


def _regulatory_row(code: str, lease_no: str) -> tuple[str, ...]:
    return (
        code, "08", lease_no, "7B", f"LEASE {lease_no}", "123456", "SAMPLE OPERATOR",
        "00123456", "SAMPLE FIELD", "", "N", "N",
    )


def _build(restated: bool) -> dict[str, str]:
    lease_rows: list[tuple[str, ...]] = []
    completions: list[tuple[str, ...]] = []
    leases_seen: list[tuple[str, str]] = []

    def lease(code: str, lease_no: str) -> None:
        leases_seen.append((code, lease_no))

    # 000101 — a multi-well oil lease, three wells, and the lease whose January 2024 volume is
    # restated in the second vintage. 900 bbl over three wells divides exactly; 901 does not,
    # which is what exercises the remainder.
    lease("O", "000101")
    for month in MONTHS:
        oil = "900"
        if month == "202401":
            oil = "1201" if restated else "901"
        lease_rows.append(_lease_cycle_row("O", "000101", month, oil=oil, csgd="4500"))
    for index, unique in enumerate(("00001", "00002", "00003"), start=1):
        completions.append(_completion_row("O", "000101", f"{index:06d}", IN_SCOPE_COUNTY, unique))

    # 000202 — a gas lease: one gas well, condensate and gas-well gas, passed through observed.
    lease("G", "000202")
    for month in MONTHS:
        lease_rows.append(
            _lease_cycle_row("G", "000202", month, gas="12000", cond="45", gas_well_no="000401")
        )
    completions.append(_completion_row("G", "000202", "000401", IN_SCOPE_COUNTY, "00010"))

    # 000303 — the dual-lease wellbore. API 42-003-00001 is already on oil lease 000101, and it
    # is completed on this gas lease as well, so one API-10 carries two lease keys in one dump.
    lease("G", "000303")
    for month in MONTHS:
        lease_rows.append(
            _lease_cycle_row("G", "000303", month, gas="3000", cond="12", gas_well_no="000501")
        )
    completions.append(_completion_row("G", "000303", "000501", IN_SCOPE_COUNTY, "00001"))

    # 000404 — two wells, one with a filed plug date mid-history: the EWA export carries the
    # date, and this lease is what makes excluded_after_plug and its redistribution visible.
    lease("O", "000404")
    for month in MONTHS:
        lease_rows.append(_lease_cycle_row("O", "000404", month, oil="500"))
    completions.append(_completion_row("O", "000404", "000001", IN_SCOPE_COUNTY, "00020"))
    completions.append(_completion_row("O", "000404", "000002", IN_SCOPE_COUNTY, "00021"))

    # 000505 — two wells, one plugged with no filed date. It stays eligible and its months are
    # labelled rather than deleted, which is the whole of M-18's undated arm.
    lease("O", "000505")
    for month in MONTHS:
        lease_rows.append(_lease_cycle_row("O", "000505", month, oil="640"))
    completions.append(_completion_row("O", "000505", "000001", SECOND_COUNTY, "00030"))
    completions.append(
        _completion_row("O", "000505", "000002", SECOND_COUNTY, "00031", status_14b2="P")
    )

    # 000606 — a negative correction month. floor(-7/2) is -4 twice, so a split on the signed
    # value hands the lowest API-10 well a positive barrel in a correction month.
    lease("O", "000606")
    for month in MONTHS:
        oil = "-7" if month == "202406" else "300"
        lease_rows.append(_lease_cycle_row("O", "000606", month, oil=oil))
    completions.append(_completion_row("O", "000606", "000001", IN_SCOPE_COUNTY, "00040"))
    completions.append(_completion_row("O", "000606", "000002", IN_SCOPE_COUNTY, "00041"))

    # 000707 — volume filed, no crosswalk row at all: the no_eligible_well ledger cause.
    lease("O", "000707")
    for month in MONTHS:
        lease_rows.append(_lease_cycle_row("O", "000707", month, oil="120"))

    # 000808 — filed zeros and unfiled months, which null_semantics must keep apart.
    lease("O", "000808")
    for month in MONTHS:
        if month.endswith(("07", "08")):
            lease_rows.append(_lease_cycle_row("O", "000808", month, oil="", filed="N"))
        else:
            lease_rows.append(_lease_cycle_row("O", "000808", month, oil="0", filed="Y"))
    completions.append(_completion_row("O", "000808", "000001", IN_SCOPE_COUNTY, "00050"))

    # 000909 — every well outside the 55-county scope. Counted at promotion, never quarantined.
    lease("O", "000909")
    for month in MONTHS:
        lease_rows.append(_lease_cycle_row("O", "000909", month, oil="800"))
    completions.append(_completion_row("O", "000909", "000001", OUT_OF_SCOPE_COUNTY, "00060"))

    # 001010 — a volume that is not a number, and one that overflows numeric(18,3).
    lease("O", "001010")
    for month in MONTHS:
        oil = "300"
        if month == "202402":
            oil = "N/A"
        elif month == "202403":
            oil = "9" * 19
        lease_rows.append(_lease_cycle_row("O", "001010", month, oil=oil))
    completions.append(_completion_row("O", "001010", "000001", IN_SCOPE_COUNTY, "00070"))

    # The bulk, to a thousand leases: single-well oil leases over twelve months each, so the
    # key question is asked of a population rather than of the ten cases above.
    for index in range(BULK_LEASE_COUNT):
        lease_no = f"{2000 + index:06d}"
        lease("O", lease_no)
        for month in MONTHS[:12]:
            lease_rows.append(_lease_cycle_row("O", lease_no, month, oil=str(100 + index)))
        completions.append(
            _completion_row("O", lease_no, "000001", IN_SCOPE_COUNTY, f"{1000 + index:05d}")
        )

    extract = "27-AUG-26" if restated else "19-AUG-26"
    newest = "202507" if restated else "202506"
    return {
        "GP_COUNTY_DATA_TABLE.dsv": _member(
            COUNTY_HEADER,
            [
                (IN_SCOPE_COUNTY, "003", "ANDREWS", "08", "7B", "Y", "N"),
                (SECOND_COUNTY, "135", "ECTOR", "08", "7B", "Y", "N"),
                (OUT_OF_SCOPE_COUNTY, "001", "ANDERSON", "06", "06", "Y", "N"),
            ],
        ),
        "GP_DATE_RANGE_CYCLE_DATA_TABLE.dsv": _member(
            DATE_RANGE_HEADER, [("202401", newest, "202509", extract, extract)]
        ),
        "GP_DISTRICT_DATA_TABLE.dsv": _member(
            DISTRICT_HEADER,
            [(number, name, "5124630000", "AUSTIN") for number, name in DISTRICTS],
        ),
        "OG_LEASE_CYCLE_DATA_TABLE.dsv": _member(LEASE_CYCLE_HEADER, lease_rows),
        "OG_WELL_COMPLETION_DATA_TABLE.dsv": _member(WELL_COMPLETION_HEADER, completions),
        "OG_REGULATORY_LEASE_DW_DATA_TABLE.dsv": _member(
            REGULATORY_LEASE_HEADER,
            [_regulatory_row(code, lease_no) for code, lease_no in leases_seen],
        ),
    }


def write(directory: Path) -> None:
    for name, restated in ((VINTAGE_ONE, False), (VINTAGE_TWO, True)):
        members = _build(restated)
        target = directory / name
        # A fixed date_time and no compression timestamp, so a rebuild is byte-identical and a
        # diff on the archive means the data moved rather than the clock did.
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for member, text in members.items():
                info = zipfile.ZipInfo(member, date_time=(2026, 8, 27, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, text)


if __name__ == "__main__":
    write(Path(__file__).parent)
