"""The first owner account, and the recovery path. No default credential at any point.

The password source is the whole design here. `argv` is visible in `/proc` to every local
user and lands in shell history; an environment variable is visible in
`systemctl show -p Environment` and in a child's `/proc/*/environ`. stdin is neither.
"""

from __future__ import annotations

import inspect
import io

import psycopg
import pytest

from glasswell.api import bootstrap
from glasswell.api.accounts import (
    PASSWORD_MIN,
    create_session,
    create_user,
    find_user,
    record_attempt,
    resolve_session,
    verify_user_password,
)
from glasswell.api.principal import utc_now

pytestmark = pytest.mark.integration

PASSWORD = "a-sufficiently-long-password"
OTHER = "another-sufficiently-long-password"


@pytest.fixture(autouse=True)
def _password_in_the_environment(
    postgres_password: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ConnectionInfo.dsn` never carries the password, and these entry points reconnect
    from the DSN alone, exactly as they do on the host over a unix socket with peer auth."""
    monkeypatch.setenv("PGPASSWORD", postgres_password)


def run_bootstrap(db: psycopg.Connection, username: str, password: str) -> int:
    return bootstrap.bootstrap_main(
        ["--dsn", db.info.dsn, "--username", username], stdin=io.StringIO(password)
    )


def test_bootstrap_creates_the_first_owner(db: psycopg.Connection) -> None:
    assert run_bootstrap(db, "ryan", PASSWORD) == 0

    user = find_user(db, "ryan")
    assert user is not None
    assert user.role == "owner"
    assert user.enabled is True
    assert verify_user_password(user, PASSWORD) is True


def test_bootstrap_refuses_when_an_enabled_owner_exists(db: psycopg.Connection) -> None:
    create_user(
        db, username="first", password=PASSWORD, role="owner", created_by="t", now=utc_now()
    )
    db.commit()

    with pytest.raises(SystemExit, match="already exists"):
        run_bootstrap(db, "second", PASSWORD)


def test_bootstrap_proceeds_when_the_only_owner_is_disabled(db: psycopg.Connection) -> None:
    """A deployment whose sole owner was disabled has no way back in otherwise."""
    create_user(
        db, username="gone", password=PASSWORD, role="owner", created_by="t", now=utc_now()
    )
    with db.cursor() as cursor:
        cursor.execute(
            "update lineage.users set disabled_at = now(), disabled_by = 't'"
            " where username = 'gone'"
        )
    db.commit()

    assert run_bootstrap(db, "replacement", PASSWORD) == 0


def test_bootstrap_reads_the_password_from_stdin_only() -> None:
    source = io.StringIO(f"  {PASSWORD}  \n")

    assert bootstrap.read_password(source) == PASSWORD


def test_bootstrap_refuses_a_password_argument() -> None:
    """Grep-shaped so it cannot regress: the argparse surface must offer no such option."""
    source = inspect.getsource(bootstrap)

    assert "--password" not in source
    assert "add_argument(\"--password" not in source
    for forbidden in ("GLASSWELL_OWNER_PASSWORD", "GLASSWELL_PASSWORD"):
        assert forbidden not in source, "the password must not come from the environment"


def test_bootstrap_enforces_a_minimum_length() -> None:
    with pytest.raises(SystemExit, match=str(PASSWORD_MIN)):
        bootstrap.read_password(io.StringIO("short"))


def test_bootstrap_never_prints_the_password(
    db: psycopg.Connection, capsys: pytest.CaptureFixture
) -> None:
    run_bootstrap(db, "quiet", PASSWORD)

    captured = capsys.readouterr()
    assert PASSWORD not in captured.out
    assert PASSWORD not in captured.err
    assert "quiet" in captured.out


def test_no_default_credential_exists_before_bootstrap(db: psycopg.Connection) -> None:
    """The accounts migration creates three empty tables. With no users, login fails
    uniformly -- the same fail-closed shape DeniedKeyStore already uses for keys."""
    with db.cursor() as cursor:
        cursor.execute("select count(*) from lineage.users")
        assert cursor.fetchone()[0] == 0


def test_reset_clears_the_lock_and_sets_a_new_hash(db: psycopg.Connection) -> None:
    create_user(
        db, username="locked", password=PASSWORD, role="owner", created_by="t", now=utc_now()
    )
    for _index in range(25):
        record_attempt(
            db,
            username="locked",
            client_ip="203.0.113.9",
            outcome="bad_credential",
            session_id=None,
            now=utc_now(),
        )
    db.commit()

    assert bootstrap.reset_main(
        ["--dsn", db.info.dsn, "--username", "locked"], stdin=io.StringIO(OTHER)
    ) == 0

    user = find_user(db, "locked")
    assert verify_user_password(user, OTHER) is True
    assert verify_user_password(user, PASSWORD) is False
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.login_attempts where username_submitted = 'locked'"
        )
        assert cursor.fetchone()[0] == 0, "the failure history that arms the lock survived"


def test_reset_revokes_every_session_for_the_account(db: psycopg.Connection) -> None:
    create_user(
        db, username="compromised", password=PASSWORD, role="owner", created_by="t",
        now=utc_now(),
    )
    user = find_user(db, "compromised")
    _, first = create_session(db, user=user, now=utc_now())
    _, second = create_session(db, user=user, now=utc_now())
    db.commit()

    bootstrap.reset_main(
        ["--dsn", db.info.dsn, "--username", "compromised"], stdin=io.StringIO(OTHER)
    )

    assert resolve_session(db, first, now=utc_now()) is None
    assert resolve_session(db, second, now=utc_now()) is None


def test_reset_re_enables_a_disabled_account(db: psycopg.Connection) -> None:
    create_user(
        db, username="shut-out", password=PASSWORD, role="owner", created_by="t", now=utc_now()
    )
    with db.cursor() as cursor:
        cursor.execute(
            "update lineage.users set disabled_at = now(), disabled_by = 't'"
            " where username = 'shut-out'"
        )
    db.commit()

    bootstrap.reset_main(
        ["--dsn", db.info.dsn, "--username", "shut-out"], stdin=io.StringIO(OTHER)
    )

    assert find_user(db, "shut-out").enabled is True


def test_reset_refuses_an_unknown_account(db: psycopg.Connection) -> None:
    with pytest.raises(SystemExit, match="no account"):
        bootstrap.reset_main(
            ["--dsn", db.info.dsn, "--username", "nobody"], stdin=io.StringIO(OTHER)
        )


def test_the_installer_does_not_call_bootstrap() -> None:
    """An unattended installer that mints a credential is how default credentials ship."""
    from pathlib import Path

    install = Path(__file__).resolve().parents[2] / "infra" / "install.sh"

    assert "glasswell-owner-bootstrap" not in install.read_text(encoding="utf-8")
