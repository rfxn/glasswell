"""Timing must not separate the login failure classes (spec §7.7, threat T03).

The regression this guards is concrete: someone deletes the dummy verify on the unknown-user
path, and an unknown username starts answering in microseconds while a wrong password still
costs a full Argon2id verify. That is a username oracle measurable from the internet.

The assertion is **relative** — the medians must sit inside the spread the classes already
show against themselves. An absolute millisecond threshold is flaky on shared CI and gets
disabled within a month, which is worse than no test.
"""

from __future__ import annotations

import inspect
import statistics
import time

import pytest

from glasswell.api import accounts
from glasswell.api.password import DUMMY_HASH, hash_password, verify_password

pytestmark = pytest.mark.unit

SAMPLES = 25
PASSWORD = "a-sufficiently-long-password"


def _durations(encoded: str, password: str, count: int = SAMPLES) -> list[float]:
    timings = []
    for _ in range(count):
        started = time.perf_counter()
        verify_password(encoded, password)
        timings.append(time.perf_counter() - started)
    return timings


def test_medians_do_not_separate() -> None:
    """Unknown user (dummy hash) against wrong password (real hash), same parameters."""
    real = hash_password(PASSWORD)

    unknown_user = _durations(DUMMY_HASH, "whatever-they-typed")
    wrong_password = _durations(real, "whatever-they-typed")

    separation = abs(statistics.median(unknown_user) - statistics.median(wrong_password))
    jitter = max(
        statistics.pstdev(unknown_user),
        statistics.pstdev(wrong_password),
        # A floor, so a suspiciously quiet machine cannot make the bound impossible to meet.
        statistics.median(wrong_password) * 0.10,
    )

    assert separation < 3 * jitter, (
        f"unknown-user and wrong-password medians separate by {separation * 1000:.1f} ms"
        f" against a {jitter * 1000:.1f} ms within-class spread"
    )


def test_the_unknown_user_path_costs_a_real_verify() -> None:
    """The power behind the test above: a removed dummy verify would be ~1000x faster."""
    real = hash_password(PASSWORD)
    dummy = statistics.median(_durations(DUMMY_HASH, "x", count=5))
    genuine = statistics.median(_durations(real, "x", count=5))

    assert dummy > genuine / 2


def test_every_credential_failure_path_costs_a_verify_and_every_refusal_does_not() -> None:
    """Structural, so it holds without measuring.

    The uniformity that matters is between the classes a caller reaches *with* a credential
    attempt -- unknown user, wrong password, disabled account. Each of those must cost a real
    Argon2id verify, or the cheap one is a username oracle.

    The limiter-refused paths are deliberately the other way. A caller already refused by the
    limiter has been told so, and running a 64 MiB memory-hard verify for them would let an
    unauthenticated flood buy that work per request. They pad instead.
    """
    source = inspect.getsource(accounts.authenticate)
    exits = source.split("return None")[:-1]  # the last chunk is the success path

    for index, chunk in enumerate(exits):
        limited = 'outcome="rate_limited"' in chunk or 'outcome="locked"' in chunk
        verifies = "verify_password(DUMMY_HASH" in chunk or "verify_user_password" in chunk
        pads = "sleep(LOCKED_PAD_SECONDS)" in chunk

        if limited:
            assert pads, f"limiter-refused path {index} does not pad"
            assert not verifies, (
                f"limiter-refused path {index} runs a memory-hard verify; an unauthenticated"
                " flood would buy 64 MiB of work per refused request"
            )
        else:
            assert verifies, (
                f"credential path {index} returns without a password verify, so its timing"
                " separates it from the others"
            )


def test_the_login_floor_pads_a_fast_handler() -> None:
    slept: list[float] = []
    started = time.monotonic()

    padding = accounts.enforce_login_floor(started, floor=0.250, sleep=slept.append)

    assert padding > 0.2
    assert len(slept) == 1
    assert slept[0] == padding


def test_the_login_floor_never_pads_a_slow_handler_negative() -> None:
    """A handler already past the floor is not delayed further, and never sleeps a negative."""
    slept: list[float] = []

    padding = accounts.enforce_login_floor(time.monotonic() - 5.0, floor=0.250, sleep=slept.append)

    assert padding == 0.0
    assert slept == []


def test_the_login_floor_is_pinned_because_uniformity_now_depends_on_it() -> None:
    """An equality, not a floor, and the reason is new.

    The two exit classes no longer cost the same work: a limiter-refused attempt pads for
    LOCKED_PAD_SECONDS while a credential attempt runs a full Argon2id verify. What makes
    them indistinguishable is that `enforce_login_floor` pads *both* out to the same wall
    time, so the floor has to stay above the slower one. Lower it below the verify cost and
    the classes separate again -- silently, because every other test here would still pass.
    """
    assert accounts.LOGIN_FLOOR_SECONDS == 0.250
    assert accounts.LOCKED_PAD_SECONDS < accounts.LOGIN_FLOOR_SECONDS


def test_the_floor_still_exceeds_what_a_real_verify_costs() -> None:
    """The floor is only load-bearing while it is above the work it is masking. If Argon2id
    at the shipped parameters ever costs more than the floor, the floor stops hiding the
    difference and this fails rather than degrading quietly."""
    real = hash_password(PASSWORD)
    verify_cost = statistics.median(_durations(real, "wrong-password", count=5))

    assert verify_cost < accounts.LOGIN_FLOOR_SECONDS, (
        f"an Argon2id verify costs {verify_cost * 1000:.0f} ms against a"
        f" {accounts.LOGIN_FLOOR_SECONDS * 1000:.0f} ms floor; the floor no longer masks it"
    )
