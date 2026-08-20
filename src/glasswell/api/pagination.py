"""Cursor pagination (SB-04 §2.3, M17). No offset parameter exists on any collection.

The cursor is base64url of `{k, t, v, q}`: sort key, tiebreak id, resolved `as_of`, and a
fingerprint of the rest of the query. Without `q`, changing a filter mid-traversal
silently returns a page from a different result set.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlencode

import orjson

from glasswell.api.errors import ProblemError
from glasswell.lineage.serialization import canonical_json

DEFAULT_LIMIT = 100
WELLS_LIMIT_CAP = 1000
SPINE_LIMIT_CAP = 200
FINGERPRINT_LENGTH = 8
_CURSOR_FIELDS = frozenset({"k", "t", "v", "q"})


@dataclass(frozen=True, slots=True)
class Cursor:
    key: str
    tiebreak: str
    as_of: str | None


def query_fingerprint(params: Mapping[str, Any]) -> str:
    """Covers every parameter except `cursor` and `limit` (SB-04 §2.3)."""
    normalised = {
        name: sorted(str(item) for item in value)
        if isinstance(value, (list, tuple, set))
        else str(value)
        for name, value in sorted(params.items())
        if name not in {"cursor", "limit"} and value not in (None, "", [], ())
    }
    return hashlib.sha256(canonical_json(normalised)).hexdigest()[:FINGERPRINT_LENGTH]


def encode_cursor(*, key: Any, tiebreak: Any, as_of: date | None, fingerprint: str) -> str:
    payload = {
        "k": _text(key),
        "t": _text(tiebreak),
        "v": as_of.isoformat() if as_of else None,
        "q": fingerprint,
    }
    return base64.urlsafe_b64encode(canonical_json(payload)).decode("ascii").rstrip("=")


def decode_cursor(raw: str, *, fingerprint: str) -> Cursor:
    try:
        decoded = orjson.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except (binascii.Error, orjson.JSONDecodeError, ValueError) as error:
        raise ProblemError("cursor_malformed", detail=f"cursor is not decodable: {error}") from None
    if not isinstance(decoded, dict) or set(decoded) != _CURSOR_FIELDS:
        raise ProblemError("cursor_malformed", detail="cursor does not carry k, t, v and q")
    if not isinstance(decoded["k"], str) or not isinstance(decoded["t"], str):
        raise ProblemError("cursor_malformed", detail="cursor sort key and tiebreak must be text")
    if decoded["q"] != fingerprint:
        raise ProblemError(
            "cursor_query_mismatch",
            detail="this cursor was minted against a different filter set",
        )
    return Cursor(key=decoded["k"], tiebreak=decoded["t"], as_of=decoded["v"])


def next_link(path: str, params: Mapping[str, Any], cursor: str) -> str:
    """The `links.next` a client follows without assembling anything itself."""
    pairs: list[tuple[str, str]] = []
    for name, value in sorted(params.items()):
        if name == "cursor" or value in (None, "", [], ()):
            continue
        if isinstance(value, (list, tuple, set)):
            pairs.extend((name, str(item)) for item in value)
        else:
            pairs.append((name, str(value)))
    pairs.append(("cursor", cursor))
    return f"{path}?{urlencode(pairs)}"


def page(rows: Sequence[Any], limit: int) -> tuple[list[Any], bool]:
    """Collections read `limit + 1` rows; the extra row is what proves there is a next page."""
    return list(rows[:limit]), len(rows) > limit


def _text(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
