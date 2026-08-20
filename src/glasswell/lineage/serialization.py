"""Stable serialization. Every hash in the spine is taken over these bytes."""

from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal
from typing import Any

import orjson

_OPTIONS = orjson.OPT_SORT_KEYS | orjson.OPT_NON_STR_KEYS


def _fallback(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    # orjson replaces this message with its own; the raise is what signals refusal.
    raise TypeError(type(value).__name__)


def _reject_naive_datetimes(value: Any) -> None:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"datetime {value!r} must be timezone-aware")
    elif isinstance(value, dict):
        for key, item in value.items():
            _reject_naive_datetimes(key)
            _reject_naive_datetimes(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_naive_datetimes(item)


def canonical_json(value: Any) -> bytes:
    """Sorted keys, no whitespace, Decimal as string, dates as ISO-8601."""
    _reject_naive_datetimes(value)
    return orjson.dumps(value, default=_fallback, option=_OPTIONS)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_payload(value: Any) -> str:
    return sha256_hex(canonical_json(value))


def json_ready(value: Any) -> Any:
    """Round-trip through canonical JSON so jsonb columns never see a Decimal or a date."""
    return orjson.loads(canonical_json(value))
