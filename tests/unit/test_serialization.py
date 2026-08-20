from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from glasswell.lineage.serialization import canonical_json, hash_payload, sha256_hex


def test_keys_are_sorted_regardless_of_insertion_order():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})
    assert canonical_json({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_nested_keys_are_sorted():
    assert canonical_json({"z": {"b": 1, "a": 2}}) == b'{"z":{"a":2,"b":1}}'


def test_decimals_serialize_as_strings_preserving_scale():
    assert canonical_json({"v": Decimal("12034.000")}) == b'{"v":"12034.000"}'


def test_dates_and_datetimes_serialize_as_iso_utc():
    payload = {"d": date(2024, 3, 1), "t": datetime(2026, 8, 1, 5, 2, 11, tzinfo=UTC)}
    assert canonical_json(payload) == b'{"d":"2024-03-01","t":"2026-08-01T05:02:11+00:00"}'


def test_naive_datetimes_are_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        canonical_json({"t": datetime(2026, 8, 1, 5, 2, 11)})


def test_hash_payload_is_stable_and_order_independent():
    assert hash_payload({"a": 1, "b": 2}) == hash_payload({"b": 2, "a": 1})
    assert hash_payload({"a": 1}) != hash_payload({"a": 2})
    assert hash_payload({"a": 1}) == sha256_hex(b'{"a":1}')


def test_a_type_with_no_canonical_form_is_refused():
    with pytest.raises(TypeError, match="serializable"):
        canonical_json({"v": {1, 2}})
