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


def test_every_failure_path_in_authenticate_runs_a_verify() -> None:
    """Structural, so it holds without measuring: each early return that skips the real
    password comparison must run the dummy one first."""
    source = inspect.getsource(accounts.authenticate)
    before_returns = source.split("return None")

    # The final chunk is the success path; every earlier chunk is a failure exit.
    for index, chunk in enumerate(before_returns[:-1]):
        assert "verify_password(DUMMY_HASH" in chunk or "verify_user_password" in chunk, (
            f"failure path {index} in authenticate() returns without any password verify"
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
