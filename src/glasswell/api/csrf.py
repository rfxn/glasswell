"""Session-bound CSRF tokens, HMAC-signed rather than a bare double submit.

A bare double-submit cookie only proves the caller could write a cookie. Binding the token to
the session's own hash and signing it means a token minted for one session cannot be replayed
into another, and a party with no session cannot mint one at all.

This is layered with `SameSite=Lax`, not made redundant by it. `Lax` is a browser behaviour:
it does not cover a same-site attacker on another host under this zone reached over plain
http, it varies across browser versions, and it evaporates the day a future need forces
`SameSite=None`. The HMAC is an origin-side control that still holds when the cookie is sent.
"""

from __future__ import annotations

import base64
import hmac
import os
import secrets
from datetime import datetime, timedelta

CSRF_HEADER = "X-Glasswell-CSRF"
CSRF_COOKIE = "__Host-gw_csrf"
CSRF_KEY_ENV = "GLASSWELL_CSRF_KEY"
CSRF_WINDOW = timedelta(hours=4)
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

NONCE_BYTES = 16
TIMESTAMP_BYTES = 8
DIGEST_BYTES = 32
TOKEN_BYTES = NONCE_BYTES + TIMESTAMP_BYTES + DIGEST_BYTES

# The binding used before a session exists, for the login request itself.
PRE_SESSION_PREFIX = "pre:"


class CsrfKeyMissing(RuntimeError):
    """Raised at startup. A missing key must never mean a silently disabled check."""


def signing_key() -> bytes:
    key = os.environ.get(CSRF_KEY_ENV, "")
    if not key:
        raise CsrfKeyMissing(
            f"{CSRF_KEY_ENV} is unset: CSRF cannot be enforced, and a disabled check is not"
            " an acceptable degraded mode"
        )
    return key.encode("utf-8")


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode(token: str) -> bytes | None:
    try:
        padding = "=" * (-len(token) % 4)
        return base64.urlsafe_b64decode(token + padding)
    except (ValueError, TypeError):
        return None


def _digest(binding: str, nonce: bytes, stamp: bytes) -> bytes:
    message = binding.encode("utf-8") + nonce + stamp
    return hmac.digest(signing_key(), message, "sha256")


def mint(binding: str, *, now: datetime) -> str:
    nonce = secrets.token_bytes(NONCE_BYTES)
    stamp = int(now.timestamp()).to_bytes(TIMESTAMP_BYTES, "big")
    return _encode(nonce + stamp + _digest(binding, nonce, stamp))


def check(token: str, binding: str, *, now: datetime) -> bool:
    """Constant-time, and one False for a tampered, foreign, expired or malformed token."""
    if not token or not binding:
        return False
    raw = _decode(token)
    if raw is None or len(raw) != TOKEN_BYTES:
        return False
    nonce = raw[:NONCE_BYTES]
    stamp = raw[NONCE_BYTES : NONCE_BYTES + TIMESTAMP_BYTES]
    presented = raw[NONCE_BYTES + TIMESTAMP_BYTES :]
    if not hmac.compare_digest(presented, _digest(binding, nonce, stamp)):
        return False
    issued = int.from_bytes(stamp, "big")
    age = now.timestamp() - issued
    # A token from the future is as wrong as one that has expired; neither is accepted.
    return 0 <= age <= CSRF_WINDOW.total_seconds()


def mint_pre_session_nonce() -> str:
    """The value of the short-lived `__Host-gw_csrf` cookie the login flow binds against."""
    return secrets.token_urlsafe(NONCE_BYTES)


def pre_session_binding(nonce: str) -> str:
    return PRE_SESSION_PREFIX + nonce
