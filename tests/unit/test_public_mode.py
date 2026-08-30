"""`GLASSWELL_PUBLIC=1` turns two configurations into a refusal to start.

`Restart=on-failure` makes each of these a unit that will not come up. That is the intended
outcome: a public origin serving with authentication disabled is worse than a down one.
"""

from __future__ import annotations

import pytest

from glasswell.api import create_app
from glasswell.api.csrf import CSRF_KEY_ENV
from glasswell.api.deps import ALLOW_ANON_ENV, PUBLIC_ENV

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PUBLIC_ENV, raising=False)
    monkeypatch.delenv(ALLOW_ANON_ENV, raising=False)
    monkeypatch.setenv(CSRF_KEY_ENV, "0123456789abcdef0123456789abcdef")


def test_allow_anon_aborts_startup_when_public(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PUBLIC_ENV, "1")
    monkeypatch.setenv(ALLOW_ANON_ENV, "1")

    with pytest.raises(RuntimeError, match="authentication disabled"):
        create_app()


def test_allow_anon_is_permitted_when_not_public(monkeypatch: pytest.MonkeyPatch) -> None:
    """It survives as the documented dev and kiosk break-glass; it is only public mode that
    makes it a refusal."""
    monkeypatch.setenv(ALLOW_ANON_ENV, "1")

    assert create_app() is not None


def test_a_missing_csrf_key_aborts_startup_when_public(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PUBLIC_ENV, "1")
    monkeypatch.delenv(CSRF_KEY_ENV, raising=False)

    with pytest.raises(RuntimeError, match=CSRF_KEY_ENV):
        create_app()


def test_a_public_instance_with_a_key_and_no_anon_flag_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The floor: the two refusals must be about the unsafe combinations, not about public
    mode generally."""
    monkeypatch.setenv(PUBLIC_ENV, "1")

    assert create_app() is not None


def test_the_anonymous_principal_is_a_viewer_not_an_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It used to resolve to owner scope with no credential presented, which reached
    storage_uri, non-redistributable manifest bytes and GET /v1/keys. A flag must not."""
    from starlette.requests import Request

    from glasswell.api.deps import require_principal

    monkeypatch.setenv(ALLOW_ANON_ENV, "1")
    request = Request({"type": "http", "headers": [], "method": "GET", "path": "/"})

    principal = require_principal(request, None, None, None)

    assert principal.kind == "anonymous"
    assert principal.role == "viewer"
    assert principal.scope == "guest"
