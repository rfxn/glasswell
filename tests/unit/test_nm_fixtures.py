"""The NM fixtures carry the traps the parser has to survive (PLAN-NM M1, M2, B5, DIR-10).

Every property here is one a re-cut could silently drop: the byte-order mark, the namespace,
the CHAR padding on `prd_knd_cde`, both sides of DIR-12's window, and the single documented
cell that separates the restatement fixture from its base.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "nm_ocd"
NAMESPACE = "urn:schemas-microsoft-com:sql:SqlRowSet1"
PRODUCTION = FIXTURES / "nm_wcproduction_300.xml"
RECORD = re.compile(r"<wcproduction .*?</wcproduction>", re.S)
CELL = re.compile(r"<(\w+)>([^<]*)</\1>")

ALL_FIXTURES = sorted(FIXTURES.glob("*.xml"))


def cells(record: str) -> dict[str, str]:
    return dict(CELL.findall(record))


def records(path: Path) -> list[str]:
    return RECORD.findall(path.read_text(encoding="utf-16"))


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda path: path.name)
def test_every_fixture_is_a_utf16_sqlrowset_document(path: Path):
    raw = path.read_bytes()
    text = raw.decode("utf-16")
    assert raw[:2] == b"\xff\xfe"
    assert text.startswith("<root")
    assert text.endswith("</root>")
    assert "<xsd:schema" in text
    assert text.count(NAMESPACE) == 302  # the schema header, plus one per record


def test_the_production_fixture_carries_three_hundred_records():
    assert len(records(PRODUCTION)) == 300


def test_the_stream_code_keeps_the_trailing_space_that_would_quarantine_every_row():
    """B5: `prd_knd_cde` is CHAR(2). A fixture stripped to 'O' would hide the whole trap."""
    kinds = {cells(record)["prd_knd_cde"] for record in records(PRODUCTION)}
    assert kinds == {"G ", "O ", "W "}


def test_the_key_segments_are_unpadded_and_need_two_three_five():
    """M3: the API-10 is composed, not read — the file carries 30 / 5 / 20178, not 3000520178."""
    widths = {
        column: {len(cells(record)[column]) for record in records(PRODUCTION)}
        for column in ("api_st_cde", "api_cnty_cde", "api_well_idn")
    }
    assert widths["api_st_cde"] == {2}
    assert widths["api_cnty_cde"] == {1, 2}
    assert max(widths["api_well_idn"]) <= 5
    assert all(cells(record)["api_st_cde"] == "30" for record in records(PRODUCTION))


def test_the_fixture_straddles_the_promotion_window():
    """DIR-12 opens promotion at 2015-01, so the window test needs rows on both sides."""
    years = [int(cells(record)["prodn_yr"]) for record in records(PRODUCTION)]
    assert min(years) == 1973
    assert sum(year >= 2015 for year in years) >= 20
    assert sum(year < 2015 for year in years) >= 20


def test_one_well_month_reports_two_pools():
    """The S-E grain in one case: without it a fixture cannot show why api10 keying collapses."""
    filings: dict[tuple[str, ...], set[str]] = {}
    for record in records(PRODUCTION):
        row = cells(record)
        key = (
            row["api_st_cde"],
            row["api_cnty_cde"],
            row["api_well_idn"],
            row["prodn_yr"],
            row["prodn_mth"],
            row["prd_knd_cde"],
        )
        filings.setdefault(key, set()).add(row["pool_idn"])
    assert [key for key, pools in filings.items() if len(pools) > 1]


def test_the_restatement_fixture_differs_by_one_documented_record():
    base = records(PRODUCTION)
    amended = records(FIXTURES / "nm_wcproduction_300_amended.xml")
    changed = [(left, right) for left, right in zip(base, amended, strict=True) if left != right]

    assert len(changed) == 1
    before, after = (cells(record) for record in changed[0])
    assert (before["prod_amt"], after["prod_amt"]) == ("2983", "3983")
    assert (before["amend_ind"], after["amend_ind"]) == ("N", "Y")
    assert before["mod_dte"] != after["mod_dte"]
    assert {key for key in before if before[key] != after[key]} == {
        "prod_amt",
        "amend_ind",
        "mod_dte",
    }


def test_the_moddte_fixture_moves_only_the_timestamp():
    """Arm C's synthetic invariant: a change-detection stamp is not a restatement."""
    base = records(PRODUCTION)
    moved = records(FIXTURES / "nm_wcproduction_300_moddte.xml")
    stamps = {cells(record)["mod_dte"] for record in moved}

    assert len(stamps) == 1
    assert [cells(record)["prod_amt"] for record in base] == [
        cells(record)["prod_amt"] for record in moved
    ]
    assert all(
        cells(left)["mod_dte"] != cells(right)["mod_dte"]
        for left, right in zip(base, moved, strict=True)
    )
