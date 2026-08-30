"""The CSRF token itself: minting, binding, expiry and every malformed shape.

The wiring — which routes demand the header, and that the OpenAPI document declares it — is
asserted in tests/contract/test_csrf.py, where an app exists to exercise.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from glasswell.api.csrf import (
    CSRF_KEY_ENV,
    CSRF_WINDOW,
    SAFE_METHODS,
    TOKEN_BYTES,
    CsrfKeyMissing,
    check,
    mint,
    mint_pre_session_nonce,
    pre_session_binding,
    signing_key,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
SESSION = "a" * 64
OTHER_SESSION = "b" * 64


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CSRF_KEY_ENV, "0123456789abcdef0123456789abcdef")


def test_a_freshly_minted_token_checks_out() -> None:
    assert check(mint(SESSION, now=NOW), SESSION, now=NOW) is True


def test_a_token_bound_to_another_session_is_refused() -> None:
    """The property a bare double-submit cookie does not have."""
    token = mint(OTHER_SESSION, now=NOW)

    assert check(token, SESSION, now=NOW) is False


def test_a_token_older_than_the_window_is_refused() -> None:
    token = mint(SESSION, now=NOW)

    assert check(token, SESSION, now=NOW + CSRF_WINDOW - timedelta(seconds=1)) is True
    assert check(token, SESSION, now=NOW + CSRF_WINDOW + timedelta(seconds=1)) is False


def test_a_token_from_the_future_is_refused() -> None:
    """A clock moved backwards must not mint a token with a longer life than the window."""
    token = mint(SESSION, now=NOW + timedelta(hours=2))

    assert check(token, SESSION, now=NOW) is False


def test_a_tampered_token_is_refused() -> None:
    token = mint(SESSION, now=NOW)
    flipped = ("A" if token[0] != "A" else "B") + token[1:]

    assert check(flipped, SESSION, now=NOW) is False


def test_a_truncated_or_extended_token_is_refused_without_raising() -> None:
    token = mint(SESSION, now=NOW)

    assert check(token[:-4], SESSION, now=NOW) is False
    assert check(token + "AAAA", SESSION, now=NOW) is False


@pytest.mark.parametrize("token", ["", "   ", "!!!not-base64!!!", "AAAA", "z", "=" * 10])
def test_a_malformed_token_is_refused_without_raising(token: str) -> None:
    assert check(token, SESSION, now=NOW) is False


def test_an_empty_binding_is_refused() -> None:
    """No session and no pre-session nonce means nothing to bind to, so nothing is accepted."""
    assert check(mint(SESSION, now=NOW), "", now=NOW) is False


def test_two_tokens_for_one_session_differ() -> None:
    """A per-token nonce, so a token is not a stable value worth stealing once."""
    assert mint(SESSION, now=NOW) != mint(SESSION, now=NOW)


def test_the_token_decodes_to_the_declared_length() -> None:
    import base64

    raw = base64.urlsafe_b64decode(mint(SESSION, now=NOW) + "==")

    assert len(raw) == TOKEN_BYTES


def test_a_token_minted_before_a_session_rotation_fails_after_it() -> None:
    """Login mints a new session id, so its hash changes and the old token stops working."""
    before = mint(SESSION, now=NOW)

    assert check(before, OTHER_SESSION, now=NOW) is False


def test_the_pre_session_binding_is_namespaced_away_from_a_session_hash() -> None:
    """A login token must not be replayable as a session token, or vice versa."""
    nonce = mint_pre_session_nonce()
    token = mint(pre_session_binding(nonce), now=NOW)

    assert check(token, pre_session_binding(nonce), now=NOW) is True
    assert check(token, nonce, now=NOW) is False


def test_a_missing_key_raises_rather_than_disabling_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A disabled CSRF check is not an acceptable degraded mode."""
    monkeypatch.delenv(CSRF_KEY_ENV, raising=False)

    with pytest.raises(CsrfKeyMissing):
        signing_key()


def test_a_token_does_not_verify_under_a_different_key(monkeypatch: pytest.MonkeyPatch) -> None:
    token = mint(SESSION, now=NOW)
    monkeypatch.setenv(CSRF_KEY_ENV, "ffffffffffffffffffffffffffffffff")

    assert check(token, SESSION, now=NOW) is False


def test_the_safe_methods_are_the_ones_that_change_nothing() -> None:
    assert set(SAFE_METHODS) == {"GET", "HEAD", "OPTIONS", "TRACE"}
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert method not in SAFE_METHODS


def test_check_uses_a_constant_time_comparison() -> None:
    """Grep-shaped, which is the only kind of constant-time assertion that does not rot."""
    import inspect

    from glasswell.api import csrf

    source = inspect.getsource(csrf.check)

    assert "compare_digest" in source
    assert "==" not in source.replace("!=", "").replace(">=", "").replace("<=", "")
