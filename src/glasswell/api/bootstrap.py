"""Create the first owner account, and recover from a lockout. Both run as root over ssh.

There is no default credential at any point. `install.sh` deliberately does not call this:
an unattended installer that mints a credential is precisely how default credentials get
shipped, and a generated password printed at install time lands in the installer's stdout,
which lands in a deploy log — the class `access_log.py` exists to prevent.

The password is read from **stdin only**. Never `argv`, which is visible in `/proc` to every
local user and lands in shell history; never an environment variable, which is visible in
`systemctl show -p Environment` and in a child's `/proc/*/environ`.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

import psycopg

from glasswell.api.accounts import (
    PASSWORD_MIN,
    USERNAME_MAX,
    USERNAME_MIN,
    create_user,
    find_user,
    normalise_username,
    revoke_user_sessions,
    set_password,
)
from glasswell.api.principal import utc_now

DEFAULT_DSN = "postgresql:///glasswell?host=/var/run/postgresql"
ACTOR = "glasswell-owner-bootstrap"
RESET_ACTOR = "glasswell-owner-reset"


def _parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--dsn", default=os.environ.get("GLASSWELL_DSN", DEFAULT_DSN))
    parser.add_argument("--username", required=True)
    return parser


def read_password(stream=None) -> str:
    """stdin only. The absence of any other source is the point, and is tested."""
    source = stream if stream is not None else sys.stdin
    password = source.read().strip()
    if len(password) < PASSWORD_MIN:
        raise SystemExit(f"the password must be at least {PASSWORD_MIN} characters")
    return password


def _validate_username(username: str) -> str:
    name = normalise_username(username)
    if not USERNAME_MIN <= len(name) <= USERNAME_MAX:
        raise SystemExit(f"the username must be {USERNAME_MIN}-{USERNAME_MAX} characters")
    return name


def enabled_owner_exists(connection: psycopg.Connection) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "select exists (select 1 from lineage.users"
            " where role = 'owner' and disabled_at is null)"
        )
        return bool(cursor.fetchone()[0])


def bootstrap_main(argv: Sequence[str] | None = None, *, stdin=None) -> int:
    parser = _parser("Create the first owner account. Refuses if one already exists.")
    arguments = parser.parse_args(argv)
    username = _validate_username(arguments.username)
    password = read_password(stdin)

    with psycopg.connect(arguments.dsn) as connection:
        if enabled_owner_exists(connection):
            raise SystemExit(
                "an enabled owner already exists: use glasswell-owner-reset to set a password"
            )
        if find_user(connection, username) is not None:
            raise SystemExit(f"the account {username} already exists")
        create_user(
            connection,
            username=username,
            password=password,
            role="owner",
            created_by=ACTOR,
            now=utc_now(),
        )
        connection.commit()
    # The username and nothing else. Printing the password would put it in the deploy log.
    print(f"created owner account {username}")
    return 0


def reset_main(argv: Sequence[str] | None = None, *, stdin=None) -> int:
    parser = _parser("Set an account's password and clear its lockout. The break-glass path.")
    parser.add_argument("--role", choices=("owner", "viewer"), default=None)
    arguments = parser.parse_args(argv)
    username = _validate_username(arguments.username)
    password = read_password(stdin)
    now = utc_now()

    with psycopg.connect(arguments.dsn) as connection:
        user = find_user(connection, username)
        if user is None:
            raise SystemExit(f"no account {username}")
        set_password(connection, user.user_id, password=password, now=now)
        with connection.cursor() as cursor:
            # Re-enable, and clear the failure history that arms the account lock. The lock
            # is time-boxed and would expire on its own; this is for the operator who cannot
            # wait fifteen minutes.
            cursor.execute(
                "update lineage.users set disabled_at = null, disabled_by = null"
                " where user_id = %s",
                (user.user_id,),
            )
            if arguments.role is not None:
                cursor.execute(
                    "update lineage.users set role = %s where user_id = %s",
                    (arguments.role, user.user_id),
                )
            cursor.execute(
                "delete from lineage.login_attempts where username_submitted = %s", (username,)
            )
        revoked = revoke_user_sessions(
            connection, user.user_id, reason="password_changed", now=now, keep=None
        )
        connection.commit()
    print(f"reset {username}; revoked {revoked} session(s)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(bootstrap_main())
