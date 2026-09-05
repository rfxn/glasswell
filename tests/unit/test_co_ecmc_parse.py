"""The Colorado parsers, at the level that needs no database.

Two decisions carry this file: a production file resolves its columns from its own header and
never by ordinal, and the archives disagree about three spellings, a column's position, a date
format and a null token. Both are registry rules; these tests hold the parser to them using the
real headers, cut from the live files.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from glasswell.ingest import co_ecmc_production as production

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parents[1] / "fixtures" / "co_ecmc"
ROLLING = FIXTURES / "monthly_prod_sample.csv"
DRIFTED = FIXTURES / "prod_reports_2025_sample.csv"
UNDRIFTED = FIXTURES / "prod_reports_1999_sample.csv"

ALIASES = {
    "GasShrinkage": ["GasSrinkage"],
    "BomInvent": ["BOMInvent"],
    "EomInvent": ["EOMInvent"],
}
NULL_TOKENS = ["", "NULL"]
DATE_FORMATS = ["%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"]


def header_of(path: Path) -> list[str]:
    with path.open(newline="", encoding="latin-1") as handle:
        return next(csv.reader(handle))


def resolver() -> production.ColumnResolver:
    return production.ColumnResolver(aliases=ALIASES, null_tokens=NULL_TOKENS)


def test_the_drifted_archive_resolves_to_the_same_column_set_as_the_rolling_file() -> None:
    """The whole point of a header-driven parse: one file spells three columns differently and
    moves a fourth, and the staged column set is identical either way."""
    rolling = resolver().resolve(header_of(ROLLING))
    drifted = resolver().resolve(header_of(DRIFTED))

    assert set(rolling) == set(drifted)
    assert len(rolling) == len(header_of(ROLLING))


def test_the_undrifted_archive_proves_the_drift_is_one_file_and_not_the_archives() -> None:
    """`state-data-research.md` called the drift a property of the archives. Measured, 1999
    carries the rolling file's spellings exactly, so the rule is per file."""
    assert header_of(UNDRIFTED) == header_of(ROLLING)
    assert header_of(DRIFTED) != header_of(ROLLING)


def test_the_position_of_a_moved_column_is_never_read() -> None:
    """FlaredVented sits ahead of WaterProduced in the drifted file. A positional parse would
    read one file's water volumes as another's flared gas, which is the failure this refuses."""
    drifted = header_of(DRIFTED)
    rolling = header_of(ROLLING)

    assert drifted.index("FlaredVented") < drifted.index("WaterProduced")
    assert rolling.index("FlaredVented") > rolling.index("WaterProduced")
    assert resolver().resolve(drifted)["flaredvented"] == drifted.index("FlaredVented")
    assert resolver().resolve(rolling)["flaredvented"] == rolling.index("FlaredVented")


def test_an_unknown_column_is_a_refusal_naming_it_rather_than_a_silent_drop() -> None:
    header = [*header_of(ROLLING), "SomethingNew"]

    with pytest.raises(production.SchemaDrift) as refused:
        resolver().resolve(header)

    assert "SomethingNew" in str(refused.value)


def test_a_missing_column_is_a_refusal_too() -> None:
    header = [name for name in header_of(ROLLING) if name != "OilProduced"]

    with pytest.raises(production.SchemaDrift) as refused:
        resolver().resolve(header)

    assert "oilproduced" in str(refused.value).lower()


def test_the_literal_string_null_is_a_null_and_an_empty_field_still_is() -> None:
    """The drifted archive writes NULL where the rolling file writes nothing. Staging is text,
    so the difference has to be removed here or it reaches every consumer as two absences."""
    resolve = resolver()

    assert resolve.value("NULL") is None
    assert resolve.value("") is None
    assert resolve.value("  ") is None
    assert resolve.value("0") == "0"
    assert resolve.value(" 73 ") == "73"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("01/12/2026 00:00:00", date(2026, 1, 12)),
        ("2025-01-14 00:00:00.000", date(2025, 1, 14)),
        ("", None),
        ("NULL", None),
    ],
)
def test_both_date_formats_read_and_neither_is_guessed(raw: str, expected: date | None) -> None:
    assert production.accepted_date(raw, DATE_FORMATS, NULL_TOKENS) == expected


def test_an_unreadable_date_is_a_refusal_rather_than_a_silent_none() -> None:
    with pytest.raises(ValueError, match="14/14/2026"):
        production.accepted_date("14/14/2026 00:00:00", DATE_FORMATS, NULL_TOKENS)


def test_the_received_year_trap_is_in_the_fixture_and_not_only_in_the_rule() -> None:
    """The 2025 archive opens at ReportMonth 11, ReportYear 2024: the filename's year is the
    year ECMC accepted the report, so a loader keyed on it double-counts and drops months."""
    with DRIFTED.open(newline="", encoding="latin-1") as handle:
        first = next(csv.DictReader(handle))

    assert first["ReportYear"] == "2024"
    assert first["ReportMonth"] == "11"
    assert first["AcceptedDate"].startswith("2025-")


def test_every_gis_layer_is_selected_by_the_member_its_archive_ships() -> None:
    """R8 on the archive layout. Which member a layer is read from was a code constant, and it
    was wrong for two of the three archives: the loader looked for a stem ending in
    `directionalbottomholelocations` while ECMC ships `Directional_Bottomhole_Locations`.

    The names are rows now, and the loader reads them rather than restating them, so the
    fixtures under `co_ecmc/` and the layer specs cannot drift apart again.
    """
    from glasswell.ingest.co_ecmc_gis import LAYERS
    from glasswell.seed.conformance_co import CO_GIS_MEMBERS

    assert {layer.source_id: layer.layer_suffix for layer in LAYERS} == {
        "co_ecmc_wells_shp": "Wells",
        "co_ecmc_directional_bh": "Directional_Bottomhole_Locations",
        "co_ecmc_directional_lines": "Directional_Lines",
    }
    for layer in LAYERS:
        registered = CO_GIS_MEMBERS[layer.source_id]
        assert layer.layer_suffix == registered["member_stem"]
        assert layer.source_key == registered["source_key"]


@pytest.mark.parametrize(
    ("fixture", "stem"),
    [
        ("Wells_sample.zip", "Wells"),
        ("DirectionalBottomholeLocations_sample.zip", "Directional_Bottomhole_Locations"),
        ("DirectionalLines_sample.zip", "Directional_Lines"),
    ],
)
def test_the_gis_fixtures_carry_the_member_names_the_regulator_publishes(
    fixture: str, stem: str
) -> None:
    """`cut_fixtures.py` used to read the source archives by extension and write the cut under
    a stem typed in here, so the suite asserted a name this repository invented. A fixture that
    is wrong about the one thing the loader selects on cannot catch a selector that is wrong."""
    import zipfile

    with zipfile.ZipFile(FIXTURES / fixture) as archive:
        stems = {name.rpartition(".")[0] for name in archive.namelist()}

    assert stems == {stem}


def test_the_member_names_are_registered_rules_with_their_own_publication() -> None:
    """049's trigger refuses a rule whose publication is not registered, so the three rows and
    their evidence ship in one commit or the Colorado seeder raises on a fresh database."""
    from glasswell.seed.conformance_co import CO_RULES

    ids = [str(rule["rule_id"]) for rule in CO_RULES if str(rule["rule_id"]).endswith("_member_1")]
    migrations = Path(__file__).resolve().parents[2] / "src/glasswell/db/migrations"
    published = {
        rule_id
        for path in migrations.glob("*.sql")
        for rule_id in ids
        if f"'{rule_id}'" in path.read_text(encoding="utf-8")
    }

    assert sorted(ids) == sorted(published) == [
        "cr_co_directional_bh_member_1",
        "cr_co_directional_lines_member_1",
        "cr_co_wells_shp_member_1",
    ]


def test_the_blank_evidence_names_every_column_the_module_measured_a_blank_in() -> None:
    """gate-cofix M-3. `measured_blank_attributes` is served evidence, so it has to hold every
    blank this module counted rather than the one a gate happened to catch. The header archive
    measures two: Well_Class (1,176) and Loc_Qual (62). The rule applies to every text attribute
    either way -- what was wrong is the evidence, which understated what the file carries.
    """
    from glasswell.seed.conformance_co import (
        CO_GIS_BLANK_ATTRIBUTES,
        DEVIATION_DOMAIN,
        LINES_SOURCE_ID,
        LOC_QUAL_DOMAIN,
        WELL_CLASS_DOMAIN,
        WELLS_SOURCE_ID,
    )

    assert CO_GIS_BLANK_ATTRIBUTES[WELLS_SOURCE_ID] == {
        "Well_Class": WELL_CLASS_DOMAIN[""],
        "Loc_Qual": LOC_QUAL_DOMAIN[""],
    }
    assert CO_GIS_BLANK_ATTRIBUTES[LINES_SOURCE_ID] == {"Deviation": DEVIATION_DOMAIN[""]}
