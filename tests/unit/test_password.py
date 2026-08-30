"""Argon2id parameters are a security floor, not a default someone may lower."""

from __future__ import annotations

import pytest

from glasswell.api.password import (
    ARGON2_HASH_LEN,
    ARGON2_MEMORY_COST,
    ARGON2_PARALLELISM,
    ARGON2_SALT_LEN,
    ARGON2_TIME_COST,
    DUMMY_HASH,
    hash_password,
    needs_rehash,
    verify_password,
)

pytestmark = pytest.mark.unit


def test_the_parameters_never_drift_downward() -> None:
    """An explicit floor, so a later edit that weakens the cost fails rather than ships."""
    assert ARGON2_TIME_COST >= 3
    assert ARGON2_MEMORY_COST >= 65536
    assert ARGON2_PARALLELISM >= 2
    assert ARGON2_HASH_LEN >= 32
    assert ARGON2_SALT_LEN >= 16


def test_a_hash_round_trips_and_names_its_algorithm() -> None:
    encoded = hash_password("correct horse battery staple")

    assert encoded.startswith("$argon2id$")
    assert verify_password(encoded, "correct horse battery staple") is True


def test_a_wrong_password_is_refused_without_raising() -> None:
    encoded = hash_password("a")

    assert verify_password(encoded, "b") is False


def test_a_weaker_stored_hash_asks_to_be_rehashed() -> None:
    weak = hash_password("a", time_cost=1, memory_cost=8192, parallelism=1)

    assert needs_rehash(weak) is True
    assert needs_rehash(hash_password("a")) is False


def test_a_malformed_hash_is_refused_and_not_an_error_path() -> None:
    """A corrupt stored hash must answer False, never become a 500 on the login route."""
    assert verify_password("not-a-hash", "a") is False
    assert verify_password("", "a") is False


def test_a_malformed_hash_asks_to_be_rehashed_rather_than_raising() -> None:
    assert needs_rehash("not-a-hash") is True


def test_two_hashes_of_one_password_differ() -> None:
    """A per-hash salt, asserted rather than assumed."""
    assert hash_password("a") != hash_password("a")


def test_the_dummy_hash_verifies_against_nothing() -> None:
    """The unknown-user path runs a real verify against this, so it must be a real hash."""
    assert DUMMY_HASH.startswith("$argon2id$")
    assert verify_password(DUMMY_HASH, "") is False
    assert verify_password(DUMMY_HASH, "a") is False
