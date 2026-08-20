"""Build an MPR workbook in the real header shape, so a pool case can be stated in a test.

The committed fixtures are cuts of a real NDIC file and carry no multi-pool well; adding a
binary for one would hide the case being tested inside a blob nobody can read.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl

HEADER = (
    "ReportDate", "API_WELLNO", "FileNo", "Company", "WellName", "Quarter", "Section",
    "Township", "Range", "County", "FieldName", "Pool", "Oil", "Wtr", "Days", "Runs", "Gas",
    "GasSold", "Flared", "Lat", "Long",
)

_DEFAULTS: dict[str, Any] = {
    "FileNo": 31100,
    "Company": "HESS BAKKEN INVESTMENTS II, LLC",
    "WellName": "ND STATE 6-16",
    "Quarter": "NWNE",
    "Section": 14,
    "Township": 155,
    "Range": 96,
    "County": "WIL",
    "FieldName": "BEAVER LODGE",
    "Runs": 0,
    "GasSold": 0,
    "Flared": 0,
    "Lat": 48.2536174266782,
    "Long": -102.985851631881,
}


def filing(
    *,
    api14: str,
    month: datetime,
    pool: str | None,
    oil: Any,
    water: Any = 0,
    gas: Any = 0,
    days: Any = 31,
    **overrides: Any,
) -> dict[str, Any]:
    return {
        **_DEFAULTS,
        "ReportDate": month,
        "API_WELLNO": api14,
        "Pool": pool,
        "Oil": oil,
        "Wtr": water,
        "Gas": gas,
        "Days": days,
        **overrides,
    }


def write_workbook(path: Path, filings: list[dict[str, Any]], *, sheet: str = "Oil") -> Path:
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = sheet
    worksheet.append(list(HEADER))
    for row in filings:
        worksheet.append([row.get(column) for column in HEADER])
    workbook.create_sheet("SkimmedCrudeRecovery")
    workbook.save(path)
    return path
