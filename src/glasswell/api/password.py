"""Argon2id, at parameters sized against this host's RAM budget.

Every function here fails closed: a malformed or unreadable stored hash answers "no" rather
than raising, because the caller is a login route and an exception there is a 500 that
distinguishes one account from another.
"""

from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import (
    HashingError,
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

# 64 MiB x 2 uvicorn workers = 128 MiB peak, inside the budget infra/README.md sizes.
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65536
ARGON2_PARALLELISM = 2
ARGON2_HASH_LEN = 32
ARGON2_SALT_LEN = 16

ENCODED_PREFIX = "$argon2id$"


def _hasher(
    *,
    time_cost: int = ARGON2_TIME_COST,
    memory_cost: int = ARGON2_MEMORY_COST,
    parallelism: int = ARGON2_PARALLELISM,
) -> PasswordHasher:
    return PasswordHasher(
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
        hash_len=ARGON2_HASH_LEN,
        salt_len=ARGON2_SALT_LEN,
    )


_DEFAULT = _hasher()


def hash_password(
    password: str,
    *,
    time_cost: int = ARGON2_TIME_COST,
    memory_cost: int = ARGON2_MEMORY_COST,
    parallelism: int = ARGON2_PARALLELISM,
) -> str:
    """The keyword arguments exist so a test can produce a deliberately weak hash."""
    if (time_cost, memory_cost, parallelism) == (
        ARGON2_TIME_COST,
        ARGON2_MEMORY_COST,
        ARGON2_PARALLELISM,
    ):
        return _DEFAULT.hash(password)
    return _hasher(time_cost=time_cost, memory_cost=memory_cost, parallelism=parallelism).hash(
        password
    )


def verify_password(encoded: str, password: str) -> bool:
    """Constant-time by construction inside argon2; every failure class answers False."""
    if not encoded:
        return False
    try:
        return _DEFAULT.verify(encoded, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError, HashingError):
        return False


def needs_rehash(encoded: str) -> bool:
    """A hash this module cannot parse is one to replace, so it reports True rather than raise."""
    try:
        return _DEFAULT.check_needs_rehash(encoded)
    except (InvalidHashError, VerificationError):
        return True


# The unknown-user login path verifies against this so its cost matches a real account's.
# Generated per process from a random password, so it can never be verified by a caller.
DUMMY_HASH = _DEFAULT.hash(secrets.token_urlsafe(32))
