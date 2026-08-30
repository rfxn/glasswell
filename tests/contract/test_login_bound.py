"""The bound on unauthenticated work at the login routes, and the order it runs in.

This is the control from MAJOR-5: without it one address can buy a 64 MiB Argon2id verify
and a threadpool slot per request on `POST /v1/session`. The bound is only worth anything if
it runs **before** the CSRF check and **before** any hashing, so that is what these assert —
deleting either `consume_login_bucket` call turns this file red.

Each test drives its own address. The rate window is keyed on `(principal_id, operation)` and
every test gets its own database, so buckets do not leak between tests; the explicit address
keeps that true within a test too, and documents which bucket is being exercised.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from glasswell.api.csrf import CSRF_HEADER
from glasswell.api.deps import SESSION_COOKIE
from glasswell.api.rate_limit import BUCKETS
from tests.contract.conftest import (
    OWNER_PASSWORD,
    SESSION_BASE_URL,
    challenge,
    seed_user,
)

pytestmark = pytest.mark.contract

LOGIN_LIMIT = BUCKETS["login"]
CHALLENGE_LIMIT = BUCKETS["challenge"]


def edge(address: str) -> dict[str, str]:
    """A resolvable client address, as Caddy would set it on the tunnel listener."""
    return {"X-Glasswell-Edge": "tunnel", "X-Glasswell-Client-Ip": address}


def caller(client: TestClient) -> TestClient:
    return TestClient(client.app, base_url=SESSION_BASE_URL)


def post_login(session: TestClient, address: str, *, csrf: str | None, password: str):
    headers = dict(edge(address))
    if csrf is not None:
        headers[CSRF_HEADER] = csrf
    return session.post(
        "/v1/session",
        json={"username": "bounded", "password": password},
        headers=headers,
    )


@pytest.fixture
def account(seeded) -> None:
    seed_user(seeded, username="bounded", password=OWNER_PASSWORD, role="owner")


def fill_bucket(connection, address: str, *, bucket: str, count: int) -> None:
    """Seed the window to `count` for this address, in the window the next request lands in.

    Driving a bucket to its limit through the route costs a real Argon2id verify plus the
    250 ms floor per attempt -- around 7 s for twenty -- and the window is a truncated UTC
    minute. A run that straddles a minute boundary resets the counter and the assertion
    evaporates. Seeding removes the wall-clock race while still exercising the real route for
    the request that matters.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.api_rate_windows"
            " (principal_id, operation, window_started_at, requests)"
            " values (%s, %s, date_trunc('minute', clock_timestamp()), %s)"
            " on conflict (principal_id, operation) do update"
            "    set window_started_at = excluded.window_started_at,"
            "        requests = excluded.requests",
            (f"ip:{address}", bucket, count),
        )
    connection.commit()


def test_login_is_refused_once_the_address_bucket_is_spent(client, account, seeded) -> None:
    session = caller(client)
    address = "203.0.113.10"
    token = challenge(session)
    fill_bucket(seeded, address, bucket="login", count=LOGIN_LIMIT - 1)

    allowed = post_login(session, address, csrf=token, password="wrong")
    refused = post_login(session, address, csrf=token, password="wrong")

    assert allowed.status_code != 429, "the bucket refused before reaching its limit"
    assert refused.status_code == 429, "login was never bounded"


def test_the_limiter_runs_before_the_csrf_check(client, account) -> None:
    """The ordering assertion, and the reason it is observable.

    Every request here carries **no** CSRF token, so the CSRF check would answer 403 for all
    of them. Seeing a 429 proves the limiter ran first. Move `consume_login_bucket` below the
    CSRF check and every status becomes 403, which fails this test.
    """
    session = caller(client)
    address = "203.0.113.11"

    statuses = [
        post_login(session, address, csrf=None, password="wrong").status_code
        for _ in range(LOGIN_LIMIT + 1)
    ]

    assert statuses[0] == 403, "the first tokenless attempt should fail CSRF"
    assert statuses[-1] == 429, (
        "a tokenless caller was never rate limited, so the limiter runs after the CSRF"
        f" check and buys nothing: {statuses}"
    )


def test_the_limiter_runs_before_any_password_hashing(client, account, seeded) -> None:
    """A correct credential presented past the bucket must answer 429, not 201.

    A 201 would mean the request reached `authenticate` -- and therefore an Argon2id verify --
    after the bound was already spent, which is exactly the amplification the bound exists to
    stop. It also proves the limiter precedes authentication rather than following it.
    """
    session = caller(client)
    address = "203.0.113.12"
    fill_bucket(seeded, address, bucket="login", count=LOGIN_LIMIT)

    refused = post_login(session, address, csrf=challenge(session), password=OWNER_PASSWORD)

    assert refused.status_code == 429
    assert SESSION_COOKIE not in refused.cookies


def test_the_challenge_route_is_bounded_on_the_address(client, seeded) -> None:
    session = caller(client)
    address = "203.0.113.13"
    fill_bucket(seeded, address, bucket="challenge", count=CHALLENGE_LIMIT)

    refused = session.get("/v1/session/challenge", headers=edge(address))

    assert refused.status_code == 429, "the challenge route is unbounded"


def test_two_addresses_do_not_share_a_login_bucket(client, account, seeded) -> None:
    """The floor under the tests above: they must bound an *address*, not the route."""
    session = caller(client)
    fill_bucket(seeded, "203.0.113.14", bucket="login", count=LOGIN_LIMIT)
    spent = post_login(session, "203.0.113.14", csrf=challenge(session), password="wrong")

    other = post_login(session, "203.0.113.15", csrf=challenge(session), password="wrong")

    assert spent.status_code == 429
    assert other.status_code != 429


def test_the_refusal_carries_retry_after_and_names_no_bucket(client, account, seeded) -> None:
    session = caller(client)
    address = "203.0.113.16"
    token = challenge(session)
    fill_bucket(seeded, address, bucket="login", count=LOGIN_LIMIT)

    refused = post_login(session, address, csrf=token, password="wrong")

    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) % 30 == 0
    body = refused.text
    for name in BUCKETS:
        assert name not in body, f"the refusal names the {name} bucket"


def test_an_unresolvable_address_is_bounded_rather_than_exempt(client, account, seeded) -> None:
    """No edge marker means the address is `unknown`, which shares one bucket -- never none."""
    session = caller(client)
    token = challenge(session)
    fill_bucket(seeded, "unknown", bucket="login", count=LOGIN_LIMIT)

    refused = session.post(
        "/v1/session",
        json={"username": "bounded", "password": "wrong"},
        headers={CSRF_HEADER: token},
    )

    assert refused.status_code == 429, "an unresolvable address escaped the login bound"
