"""The Colorado identity composition, at the level that needs no database.

The header's own API column is eight characters and carries no state code; the state appears
only inside API_Label. So the API-10 is built from two columns under
`cr_co_wells_api10_1`, and the literal lives in that rule's spec rather than in the module.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from glasswell.ingest import co_wells
from glasswell.seed.conformance_co import CO_RULES

pytestmark = pytest.mark.unit

IDENTITY = next(rule for rule in CO_RULES if rule["rule_id"] == "cr_co_wells_api10_1")
EFFECTIVE = next(rule for rule in CO_RULES if rule["rule_id"] == "cr_co_wells_effective_1")
SPEC = dict(IDENTITY["spec"])
EFFECTIVE_SPEC = dict(EFFECTIVE["spec"])
FALLBACK = date(2026, 9, 1)


def row(**overrides: object) -> dict[str, object]:
    base = {"api_county": "123", "api_seq": "24638", "api_label": "05-123-24638"}
    return {**base, **overrides}


def test_the_api10_is_composed_from_the_two_columns_that_carry_it() -> None:
    assert co_wells.build_api10(row(), SPEC) == "0512324638"


def test_each_segment_is_padded_before_the_join_and_not_after() -> None:
    """The failure this shape avoids: concatenating first and padding the result gives a
    different well. `05` + `1` + `5005` is 0501500005, never 0515005000."""
    built = co_wells.build_api10(row(api_county="1", api_seq="5005"), SPEC)

    assert built == "0500105005"
    assert len(built) == 10


def test_a_non_numeric_segment_has_no_key_and_is_not_guessed_at() -> None:
    assert co_wells.build_api10(row(api_county="12A"), SPEC) is None
    assert co_wells.build_api10(row(api_seq=None), SPEC) is None


def test_an_over_wide_segment_is_refused_rather_than_truncated() -> None:
    assert co_wells.build_api10(row(api_seq="246380"), SPEC) is None


def test_the_label_pattern_is_what_says_the_row_is_colorado() -> None:
    assert co_wells.label_conforms(row(), SPEC)
    assert not co_wells.label_conforms(row(api_label="99-999-99999"), SPEC)
    assert not co_wells.label_conforms(row(api_label=""), SPEC)


def test_no_state_code_is_written_in_the_module() -> None:
    """The claim the whole track rests on, read off the file: the literal lives in the rule."""
    source = Path(co_wells.__file__).read_text(encoding="utf-8")

    assert f'"{SPEC["state_code"]}"' not in source
    assert f"'{SPEC['state_code']}'" not in source
    assert 'identity.spec["state_code"]' in source


def test_the_valid_time_is_the_regulators_own_clock_and_falls_back_honestly() -> None:
    assert co_wells.effective_from(
        {"stat_date": "2019-04-11"}, EFFECTIVE_SPEC, FALLBACK
    ) == date(2019, 4, 11)
    assert co_wells.effective_from({"stat_date": ""}, EFFECTIVE_SPEC, FALLBACK) == FALLBACK
    assert co_wells.effective_from({"stat_date": None}, EFFECTIVE_SPEC, FALLBACK) == FALLBACK
    assert co_wells.effective_from(
        {"stat_date": "not a date"}, EFFECTIVE_SPEC, FALLBACK
    ) == FALLBACK
