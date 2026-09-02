"""GW_SEED for the Accounts gate: one throwaway owner, and enough rows to judge a list by.

    GW_ACCOUNTS_PASSWORD=$(openssl rand -base64 24) GW_PORT=8130 \
      GW_SEED=tests/support/serve_seed_accounts.py python3 tests/support/serve_branch.py

The password is never written down: the operator mints one, this file hashes it, and the gate
reads the same variable. The database it lands in is the ephemeral one `serve_branch.py`
destroys on exit, and the gate resets this account's password to a server-minted value nobody
reads before it finishes.

`connection` is bound by serve_branch.py; everything else is imported here.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from glasswell.api.accounts import create_session, create_user, find_user

OWNER_USERNAME = "gate-owner"
STANDBY_USERNAME = "gate-standby"
VIEWER_USERNAME = "gate-reader"
PASSWORD_ENV = "GW_ACCOUNTS_PASSWORD"

password = os.environ.get(PASSWORD_ENV, "")
if not password:
    raise SystemExit(f"{PASSWORD_ENV} is unset: the gate signs in as a real account")

now = datetime.now(UTC)
# A second owner so the floor is a rule the gate can exercise rather than one it trips over.
for username, role in (
    (OWNER_USERNAME, "owner"),
    (STANDBY_USERNAME, "owner"),
    (VIEWER_USERNAME, "viewer"),
):
    create_user(
        connection,  # noqa: F821 -- bound by serve_branch.py
        username=username,
        password=password,
        role=role,
        created_by="serve-branch-gate",
        now=now,
    )

# Two sessions the list has something to say about: one live and one already ended. Neither
# token is kept, so neither is a credential anyone holds.
reader = find_user(connection, VIEWER_USERNAME)  # noqa: F821
if reader is not None:
    create_session(
        connection,  # noqa: F821
        user=reader,
        now=now - timedelta(hours=3),
        client_ip="192.168.2.41",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like"
            " Gecko) Chrome/140.0.0.0 Safari/537.36"
        ),
    )
    ended, _ = create_session(
        connection,  # noqa: F821
        user=reader,
        now=now - timedelta(days=2),
        # A globally routable address on purpose: python's `is_private` counts the RFC 5737
        # documentation ranges as private, so 203.0.113.9 would render `lan` and the gate would
        # never photograph the class it exists to distinguish.
        client_ip="8.8.8.8",
        user_agent="Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
    )
    with connection.cursor() as cursor:  # noqa: F821
        cursor.execute(
            "update lineage.sessions set revoked_at = %s, revoked_reason = 'logout'"
            " where session_id = %s",
            (now - timedelta(days=1), ended.session_id),
        )
