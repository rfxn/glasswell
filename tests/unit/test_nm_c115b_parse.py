"""The C-115B parse contract: dashed-API-10 identity, the F/V vocabulary, the walk order."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from glasswell.ingest.nm_c115b import (
    COLUMNS,
    WALK_ORDER,
    api10_from_dashed,
    month_from_reporting_period,
    parse_features,
    volume_or_none,
    waste_type_code,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "nm_c115b" / "upstream_by_well.geojson"


@pytest.mark.parametrize(
    ("dashed", "api10"),
    [
        ("30-015-03890", "3001503890"),
        ("30-025-27933", "3002527933"),
        ("30-045-38469", "3004538469"),
    ],
)
def test_the_dashed_id_normalises_onto_the_api10_spine(dashed, api10):
    assert api10_from_dashed(dashed) == api10


@pytest.mark.parametrize(
    "value",
    [
        "",
        None,
        "3001503890",  # already undashed: the service never ships this, so it is not the contract
        "30-015-0389",
        "30-15-03890",
        "30-015-038901",
        "30-015-0389A",
        "AB-015-03890",
        "30-015-03890-0000",
    ],
)
def test_an_id_that_is_not_a_dashed_api10_refuses_rather_than_guessing(value):
    with pytest.raises(ValueError, match="is not a dashed API-10"):
        api10_from_dashed(value)


def test_the_waste_vocabulary_admits_exactly_flared_and_vented():
    assert waste_type_code("F") == "F"
    assert waste_type_code("V") == "V"
    assert waste_type_code(" v ") == "V"
    for unknown in ("", None, "X", "FV", "flared"):
        assert waste_type_code(unknown) is None


@pytest.mark.parametrize(
    ("value", "month"),
    [(202507, date(2025, 7, 1)), ("202601", date(2026, 1, 1)), (202612, date(2026, 12, 1))],
)
def test_the_reporting_period_reads_as_the_month_it_names(value, month):
    assert month_from_reporting_period(value) == month


@pytest.mark.parametrize("value", [None, "", 2026, 202600, 202613, "2026-07", "abcdef", 20260700])
def test_a_reporting_period_that_is_not_a_yyyymm_is_refused(value):
    assert month_from_reporting_period(value) is None


@pytest.mark.parametrize(("value", "expected"), [(250, 250), ("0", 0), (0, 0)])
def test_a_reported_volume_is_kept_as_the_integer_the_regulator_filed(value, expected):
    assert volume_or_none(value) == expected


@pytest.mark.parametrize("value", [None, "", -1, "1.5", "many"])
def test_a_volume_that_is_not_a_non_negative_integer_is_refused(value):
    assert volume_or_none(value) is None


def test_the_walk_order_is_the_stable_key_and_never_the_object_id():
    """The layer's OBJECTID is assigned per query, so an OID-ordered offset walk duplicates
    and skips rows silently. Measured 2026-08-22: two adjacent 2,000-row pages shared 52 rows
    under OBJECTID ASC and none under this order."""
    assert WALK_ORDER == "id ASC, reporting_period ASC, waste_type ASC"
    assert "OBJECTID" not in WALK_ORDER


def test_the_recorded_fixture_parses_into_staging_rows_with_no_rejects():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    parsed = parse_features([(ordinal, f) for ordinal, f in enumerate(payload["features"])])
    assert len(parsed.rows) == 6
    assert parsed.rejects == []
    first = parsed.rows[0]
    assert set(first) == {"manifest_id", "source_row_ordinal", "geom_wkt", *COLUMNS}
    assert first["id"] == "30-045-38469"
    assert first["waste_type"] == "V"
    assert first["reporting_period"] == "202605"
    assert first["geom_wkt"].startswith("POINT (")
    assert {row["waste_type"] for row in parsed.rows} == {"F", "V"}
    assert {row["reporting_period"] for row in parsed.rows} == {
        "202507",
        "202508",
        "202604",
        "202605",
    }


def _feature(**properties: object) -> dict[str, object]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    template = payload["features"][0]
    return {**template, "properties": {**template["properties"], **properties}}


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"id": "not-an-api"}, "key_incomplete"),
        ({"waste_type": "X"}, "unknown_vocab"),
        ({"reporting_period": 202613}, "out_of_range_date"),
        ({"volume": -4}, "unreliable_numeric"),
    ],
)
def test_a_row_that_fails_a_declared_rule_is_held_with_its_reason_and_still_staged(
    override, reason
):
    """Never dropped: staging is source-faithful, so the row lands verbatim and the reject is
    the quarantine fact beside it."""
    parsed = parse_features([(0, _feature(**override))])
    assert len(parsed.rows) == 1
    assert [reject["reason_code"] for reject in parsed.rejects] == [reason]
    assert parsed.rejects[0]["source_row_ordinal"] == 0


def test_a_feature_carrying_no_point_is_staged_without_geometry_and_held():
    parsed = parse_features([(0, {**_feature(), "geometry": None})])
    assert parsed.rows[0]["geom_wkt"] is None
    assert [reject["reason_code"] for reject in parsed.rejects] == ["parse_error"]


def test_a_repeated_identity_key_within_one_harvest_is_held_as_a_duplicate():
    """The tripwire for the walk-order defect: an offset walk over an unstable OBJECTID
    re-reads rows, and a re-read row is a duplicate identity key, not new data."""
    parsed = parse_features([(0, _feature()), (1, _feature())])
    assert len(parsed.rows) == 2
    assert [reject["reason_code"] for reject in parsed.rejects] == ["duplicate_row"]
    assert parsed.rejects[0]["source_row_ordinal"] == 1
