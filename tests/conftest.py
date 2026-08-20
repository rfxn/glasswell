from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.api import create_app
from glasswell.api.deps import ALLOW_ANON_ENV, OWNER_KEY_ENV, get_connection
from glasswell.api.examples import KEY_HEADER
from glasswell.db.migrate import migrate
from glasswell.lineage.fetch import RAW_ROOT_ENV
from glasswell.lineage.models import DeriveEnvironment

POSTGIS_IMAGE = "postgis/postgis:16-3.4"
TEMPLATE_DATABASE = "glasswell_template"
READY_TIMEOUT_SECONDS = 90
REQUIRE_DOCKER_ENV = "GLASSWELL_REQUIRE_DOCKER"
# DR-25/N-10: `make prune-test-volumes` sweeps on this label, so it must be on everything the
# harness creates and on nothing else. An anonymous volume is indistinguishable from a real one.
TEST_LABEL = "glasswell.test=1"
DATA_DIRECTORY = "/var/lib/postgresql/data"

FIXTURE_ENV_ID = "env_test"
LINEAGE_FIXTURE_ENV_ID = "env_lineage_fixture"
FIXTURE_SOURCES = ("nd_mpr_xlsx", "tx_pdq_dsv", "nm_ocd_wcproduction")
CONTRACT_OWNER_KEY = "contract-tier-owner-key"

_docker_environment: dict[str, str] | None = None
_docker_probe_error = ""
_session_container = ""
_session_volume = ""


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Tier markers follow the directory, so no test file has to remember to declare one."""
    for item in items:
        for tier in ("unit", "integration", "contract"):
            if f"/tests/{tier}/" in item.path.as_posix():
                item.add_marker(getattr(pytest.mark, tier))


def docker_environment() -> dict[str, str] | None:
    """Local socket first, then freedom's TLS endpoint."""
    global _docker_environment, _docker_probe_error
    if _docker_environment is not None:
        return _docker_environment

    candidates = [
        {},
        {
            "DOCKER_HOST": "tcp://127.0.0.1:2376",
            "DOCKER_TLS_VERIFY": "1",
            "DOCKER_CERT_PATH": str(Path.home() / ".docker" / "tls"),
        },
    ]
    failures = []
    for candidate in candidates:
        environment = {**os.environ, **candidate}
        try:
            subprocess.run(
                ["docker", "info"],
                env=environment,
                check=True,
                capture_output=True,
                timeout=30,
            )
        except (subprocess.SubprocessError, OSError) as error:
            failures.append(f"{candidate or 'local socket'}: {error}")
            continue
        _docker_environment = environment
        return environment

    _docker_probe_error = "; ".join(failures)
    return None


def _docker(environment: dict[str, str], *arguments: str) -> str:
    completed = subprocess.run(
        ["docker", *arguments],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    return completed.stdout.strip()


def _wait_until_ready(dsn: str) -> None:
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3):
                return
        except psycopg.Error as error:
            last_error = error
            time.sleep(0.5)
    raise RuntimeError(f"PostGIS container never accepted connections: {last_error}")


@pytest.fixture(scope="session")
def postgres_server() -> Iterator[str]:
    """Session-scoped PostGIS container. Yields a DSN template with a {database} slot."""
    environment = docker_environment()
    if environment is None:
        # CI sets this: a green run that skipped 414 of 677 tests is worse than a red one.
        if os.environ.get(REQUIRE_DOCKER_ENV):
            pytest.fail(f"{REQUIRE_DOCKER_ENV} is set but docker is unavailable"
                        f" ({_docker_probe_error})", pytrace=False)
        pytest.skip(f"docker unavailable, integration tier skipped ({_docker_probe_error})")

    global _session_container, _session_volume
    name = f"glasswell-test-{uuid4().hex[:8]}"
    volume = f"{name}-data"
    # A named volume rather than the image's anonymous one: `--rm` does not reclaim a volume
    # when the session is killed rather than exiting, which is how 151 of them accumulated.
    _docker(environment, "volume", "create", "--label", TEST_LABEL, volume)
    _docker(
        environment,
        "run", "-d", "--rm", "--name", name,
        "--label", TEST_LABEL,
        "-v", f"{volume}:{DATA_DIRECTORY}",
        "-e", "POSTGRES_USER=glasswell",
        "-e", "POSTGRES_PASSWORD=glasswell",
        "-e", "POSTGRES_DB=postgres",
        POSTGIS_IMAGE,
    )
    _session_container, _session_volume = name, volume
    try:
        # The bridge IP rather than a published port: docker-proxy is absent on this host,
        # and both supported daemon endpoints are local, so the bridge network is routable.
        address = _docker(
            environment,
            "inspect",
            "-f",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            name,
        )
        dsn_template = (
            f"postgresql://glasswell:glasswell@{address}:5432/{{database}}?connect_timeout=5"
        )
        _wait_until_ready(dsn_template.format(database="postgres"))
        yield dsn_template
    finally:
        subprocess.run(
            ["docker", "rm", "-f", "-v", name],
            env=environment,
            check=False,
            capture_output=True,
            timeout=120,
        )
        _remove_volume(environment, volume)


def _remove_volume(environment: dict[str, str], volume: str) -> None:
    """`docker rm` returns before the daemon has always released the mount; retry, then leave
    it labelled for the sweep rather than failing a green run on cleanup."""
    for _ in range(10):
        completed = subprocess.run(
            ["docker", "volume", "rm", volume],
            env=environment,
            check=False,
            capture_output=True,
            timeout=60,
        )
        if completed.returncode == 0:
            return
        time.sleep(0.5)


@pytest.fixture(scope="session")
def session_resources(postgres_server: str) -> tuple[str, str]:
    """The container and volume this session owns, so a test can audit what it leaves behind."""
    return _session_container, _session_volume


def _create_database(dsn_template: str, name: str, template: str | None = None) -> str:
    with psycopg.connect(dsn_template.format(database="postgres"), autocommit=True) as admin:
        clause = f' template "{template}"' if template else ""
        admin.execute(f'create database "{name}"{clause}')
    return dsn_template.format(database=name)


def _drop_database(dsn_template: str, name: str) -> None:
    with psycopg.connect(dsn_template.format(database="postgres"), autocommit=True) as admin:
        admin.execute(f'drop database if exists "{name}" with (force)')


@pytest.fixture(scope="session")
def migrated_template(postgres_server: str) -> str:
    """Migrations and shared fixture rows run once; every test database is cloned from here."""
    dsn = _create_database(postgres_server, TEMPLATE_DATABASE)
    with psycopg.connect(dsn) as connection:
        migrate(connection)
        connection.commit()
        _seed_fixture_rows(connection)
        connection.commit()
    return postgres_server


def _seed_fixture_rows(connection: psycopg.Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.environments (env_id, python_version, threads)"
            " values (%s, '3.12.10', 1)",
            (FIXTURE_ENV_ID,),
        )
        cursor.executemany(
            "insert into lineage.sources (source_id, name) values (%s, %s)",
            [(source, source.replace("_", " ")) for source in FIXTURE_SOURCES],
        )


@pytest.fixture
def db(migrated_template: str) -> Iterator[psycopg.Connection]:
    """A migrated database of its own, per test."""
    name = f"gw_test_{uuid4().hex[:12]}"
    dsn = _create_database(migrated_template, name, template=TEMPLATE_DATABASE)
    connection = psycopg.connect(dsn)
    try:
        yield connection
    finally:
        connection.close()
        _drop_database(migrated_template, name)


@pytest.fixture
def empty_db(postgres_server: str) -> Iterator[psycopg.Connection]:
    """An un-migrated database, for exercising the migration runner itself."""
    name = f"gw_empty_{uuid4().hex[:12]}"
    dsn = _create_database(postgres_server, name)
    connection = psycopg.connect(dsn)
    try:
        yield connection
    finally:
        connection.close()
        _drop_database(postgres_server, name)


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 8, 1, 5, 2, 11, tzinfo=UTC)


@pytest.fixture
def raw_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway raw zone; the env var keeps any resolver in the run away from /srv."""
    root = tmp_path / "raw"
    root.mkdir()
    monkeypatch.setenv(RAW_ROOT_ENV, str(root))
    return root


@pytest.fixture
def lineage_env(db: psycopg.Connection) -> DeriveEnvironment:
    """A pinned environment row, so derive()'s NOT NULL env_id FK is satisfiable."""
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.environments (env_id, python_version, threads, lockfile_sha256)"
            " values (%s, '3.12.10', 1, %s) on conflict (env_id) do nothing",
            (LINEAGE_FIXTURE_ENV_ID, "0" * 64),
        )
    return DeriveEnvironment(
        code_version="git:0000test", code_dirty=False, env_id=LINEAGE_FIXTURE_ENV_ID
    )


@pytest.fixture
def api_client(db: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The real app, with its connection dependency bound to this test's database."""
    monkeypatch.setenv(OWNER_KEY_ENV, CONTRACT_OWNER_KEY)
    monkeypatch.delenv(ALLOW_ANON_ENV, raising=False)
    application = create_app()
    application.dependency_overrides[get_connection] = lambda: db
    with TestClient(application, headers={KEY_HEADER: CONTRACT_OWNER_KEY}) as client:
        yield client
