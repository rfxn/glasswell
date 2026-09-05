"""The two account decisions taken before any row exists: the token's entropy and the name fold.

Both lived beside the session and user tables in `tests/integration/`, and neither reads one.
`glasswell.api.accounts` is where they are decided, and a token minted with fewer bits or a
username that stopped folding is a defect the two-minute tier can name.
"""

from __future__ import annotations

import pytest

from glasswell.api.accounts import (
    SESSION_TOKEN_BYTES,
    SESSION_TOKEN_PREFIX,
    mint_session_token,
    normalise_username,
)

pytestmark = pytest.mark.unit


def test_a_minted_token_carries_256_bits() -> None:
    token = mint_session_token()

    assert token.startswith(SESSION_TOKEN_PREFIX)
    body = token[len(SESSION_TOKEN_PREFIX) :]
    # base64url of 32 bytes, unpadded.
    assert len(body) >= (SESSION_TOKEN_BYTES * 8 + 5) // 6
    assert mint_session_token() != mint_session_token()


def test_normalising_a_username_trims_and_folds() -> None:
    assert normalise_username("  Ryan  ") == "ryan"
