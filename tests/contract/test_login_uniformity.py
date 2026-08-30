"""Every login failure answers the same thing, so nothing distinguishes the classes.

Unknown username, wrong password, disabled account and locked account are four different
server-side states. A caller who can tell them apart has a user-enumeration oracle, and the
lock class additionally leaks whether a password was correct. The bodies are compared
byte-for-byte with only `request_id` and `instance` removed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from glasswell.api.accounts import ACCOUNT_LOCK_AFTER
from glasswell.api.csrf import CSRF_HEADER
from glasswell.api.deps import SESSION_COOKIE
from tests.contract.conftest import (
    OWNER_PASSWORD,
    SESSION_BASE_URL,
    challenge,
    seed_user,
)

pytestmark = pytest.mark.contract

VOLATILE = ("request_id", "instance")


def attempt(client: TestClient, username: str, password: str) -> tuple[int, dict]:
    session = TestClient(client.app, base_url=SESSION_BASE_URL)
    token = challenge(session)
    response = session.post(
        "/v1/session",
        json={"username": username, "password": password},
        headers={CSRF_HEADER: token},
    )
    body = response.json()
    return response.status_code, {k: v for k, v in body.items() if k not in VOLATILE}


@pytest.fixture
def accounts_present(seeded) -> None:
    seed_user(seeded, username="live-account", password=OWNER_PASSWORD, role="owner")
    seed_user(seeded, username="dead-account", password=OWNER_PASSWORD, role="viewer")
    seed_user(seeded, username="locked-account", password=OWNER_PASSWORD, role="viewer")
    with seeded.cursor() as cursor:
        cursor.execute(
            "update lineage.users set disabled_at = now(), disabled_by = 'test'"
            " where username = 'dead-account'"
        )
        for index in range(ACCOUNT_LOCK_AFTER):
            cursor.execute(
                "insert into lineage.login_attempts (attempt_id, attempted_at,"
                " username_submitted, client_ip, outcome)"
                " values (%s, now(), 'locked-account', 'unknown', 'bad_credential')",
                (f"att_lock{index:04d}",),
            )
    seeded.commit()


def test_every_failure_class_is_byte_identical(client, accounts_present) -> None:
    unknown = attempt(client, "no-such-account", "whatever-they-typed")
    wrong = attempt(client, "live-account", "not-the-password")
    disabled = attempt(client, "dead-account", OWNER_PASSWORD)
    locked = attempt(client, "locked-account", OWNER_PASSWORD)

    assert unknown == wrong == disabled == locked, (
        "two login failure classes are distinguishable from the response alone"
    )


def test_every_failure_class_is_a_403_unauthenticated(client, accounts_present) -> None:
    for username, password in (
        ("no-such-account", "x"),
        ("live-account", "not-the-password"),
        ("dead-account", OWNER_PASSWORD),
        ("locked-account", OWNER_PASSWORD),
    ):
        status, body = attempt(client, username, password)

        assert status == 403
        assert body["type"] == "/v1/errors/unauthenticated"


def test_a_refusal_carries_no_detail_and_no_errors(client, accounts_present) -> None:
    """`detail` is where a helpful message would leak which of the four states applied."""
    _, body = attempt(client, "live-account", "not-the-password")

    assert "detail" not in body
    assert "errors" not in body


def test_a_refusal_never_echoes_the_submitted_username(client, accounts_present) -> None:
    _, body = attempt(client, "live-account", "not-the-password")

    assert "live-account" not in str(body)


def test_a_locked_account_with_the_right_password_is_refused(client, accounts_present) -> None:
    """Otherwise the lock answers "that was the correct password"."""
    status, _ = attempt(client, "locked-account", OWNER_PASSWORD)

    assert status == 403


def test_a_failed_login_sets_no_cookie(client, accounts_present) -> None:
    session = TestClient(client.app, base_url=SESSION_BASE_URL)
    token = challenge(session)

    response = session.post(
        "/v1/session",
        json={"username": "live-account", "password": "not-the-password"},
        headers={CSRF_HEADER: token},
    )

    emitted = [
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith(SESSION_COOKIE)
    ]
    assert emitted == []


def test_a_good_login_still_works_after_the_failures(client, accounts_present) -> None:
    """The floor under the uniformity tests: they would all pass if login never succeeded.

    Sent from its own resolvable address. Every other request in this file resolves to
    `unknown` and therefore shares one per-IP bucket, which the fixture's twenty seeded
    failures have already put into backoff -- correct behaviour, and exactly what a shared
    bucket is for, but it would otherwise mask whether login works at all.
    """
    session = TestClient(client.app, base_url=SESSION_BASE_URL)
    edge = {"X-Glasswell-Edge": "tunnel", "X-Glasswell-Client-Ip": "203.0.113.42"}
    token = challenge(session)

    response = session.post(
        "/v1/session",
        json={"username": "live-account", "password": OWNER_PASSWORD},
        headers={CSRF_HEADER: token, **edge},
    )

    assert response.status_code == 201, response.text
    assert session.get("/v1/health").status_code == 200


def test_a_failed_login_writes_no_session_row(client, accounts_present, seeded) -> None:
    attempt(client, "no-such-account", "x")
    attempt(client, "live-account", "not-the-password")

    with seeded.cursor() as cursor:
        cursor.execute("select count(*) from lineage.sessions")
        assert cursor.fetchone()[0] == 0
