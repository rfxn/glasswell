from __future__ import annotations

import contextlib
import os
import re
import subprocess
import time
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.api import create_app
from glasswell.api.csrf import CSRF_KEY_ENV
from glasswell.api.deps import ALLOW_ANON_ENV, OWNER_KEY_ENV, get_connection
from glasswell.api.examples import KEY_HEADER
from glasswell.db.migrate import discover_migrations, migrate
from glasswell.lineage.fetch import RAW_ROOT_ENV
from glasswell.lineage.models import DeriveEnvironment

POSTGIS_IMAGE = "postgis/postgis:16-3.4"
TEMPLATE_DATABASE = "glasswell_template"
READY_TIMEOUT_SECONDS = 90
REQUIRE_DOCKER_ENV = "GLASSWELL_REQUIRE_DOCKER"
# A server the workflow owns, shared by the shards' xdist workers, instead of one container per
# worker. Set, the harness starts nothing and cleans up nothing but its own databases.
SERVER_DSN_ENV = "GLASSWELL_TEST_SERVER_DSN"
# DR-25/N-10: `make prune-test-volumes` sweeps on this label, so it must be on everything the
# harness creates and on nothing else. An anonymous volume is indistinguishable from a real one.
TEST_LABEL = "glasswell.test=1"
DATA_DIRECTORY = "/var/lib/postgresql/data"
PULL_TIMEOUT_SECONDS = 600
# A server that is destroyed at the end of the session has nothing to recover, so every fsync
# it performs is bought and never read. The suite creates and drops a database per test, and
# each of those is a WAL flush the defaults make durable for no one.
EPHEMERAL_SERVER_SETTINGS = (
    "fsync=off",
    "synchronous_commit=off",
    "full_page_writes=off",
    "wal_level=minimal",
    "max_wal_senders=0",
    "max_wal_size=2GB",
    "checkpoint_timeout=30min",
)
# A LAN connection that loses a burst of packets backs off to a multi-minute RTO and never
# recovers inside a test; without these the session hangs rather than failing. They fire only
# on unacknowledged data, so a slow query is unaffected.
CONNECTION_PARAMETERS = (
    "connect_timeout=5&keepalives=1&keepalives_idle=10&keepalives_interval=5"
    "&keepalives_count=3&tcp_user_timeout=30000"
)
LOCAL_DAEMON_SCHEMES = ("", "unix", "fd", "npipe")
LOCAL_DAEMON_HOSTS = ("localhost", "127.0.0.1", "::1")

FIXTURE_ENV_ID = "env_test"
LINEAGE_FIXTURE_ENV_ID = "env_lineage_fixture"
# Jurisdictions included: these rows are inserted before seed_sources, whose `on conflict do
# nothing` then cannot repair them, so anything left null here is null for the whole suite.
FIXTURE_SOURCES = (("nd_mpr_xlsx", "ND"), ("tx_pdq_dsv", "TX"), ("nm_ocd_wcproduction", "NM"))
CONTRACT_OWNER_KEY = "contract-tier-owner-key"
CONTRACT_CSRF_KEY = "contract-tier-csrf-signing-key-0123456789"

_docker_environment: dict[str, str] | None = None
_docker_probe_error = ""
_session_container = ""
_session_volume = ""
_session_container_address = ""
_session_password = ""


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Tier markers follow the directory, so no test file has to remember to declare one."""
    for item in items:
        for tier in ("unit", "integration", "contract"):
            if f"/tests/{tier}/" in item.path.as_posix():
                item.add_marker(getattr(pytest.mark, tier))


def pytest_exception_interact(node, call, report) -> None:
    """Stop the run the first time the path to a remote daemon stalls.

    The stall lands in a session-scoped fixture, whose exception pytest caches and re-raises for
    every test that requests it, so carrying on reports the same fault a thousand times.
    """
    from tests.support.dbtier_preflight import stop_reason

    reason = stop_reason(call.excinfo.value, os.environ)
    session = getattr(node, "session", None)
    if reason is not None and session is not None and not session.shouldstop:
        session.shouldstop = reason


def daemon_address(environment: Mapping[str, str]) -> str | None:
    """The host a published container port answers on, or None when the daemon is local.

    DIR-14 sends full suites to anvil. A container's bridge IP is routable only from the
    daemon's own host, so a remote daemon has to publish and be addressed by name.
    """
    endpoint = environment.get("DOCKER_HOST", "")
    parsed = urlsplit(endpoint)
    if parsed.scheme in LOCAL_DAEMON_SCHEMES:
        return None
    host = parsed.hostname
    if host is None or host in LOCAL_DAEMON_HOSTS:
        return None
    return host


def docker_candidates(environ: Mapping[str, str]) -> list[dict[str, str]]:
    """An explicit DOCKER_HOST is the only candidate: `make test-anvil` that quietly ran here
    instead would be a full suite reported against the wrong host."""
    if environ.get("DOCKER_HOST"):
        return [{}]
    return [
        {},
        {
            "DOCKER_HOST": "tcp://127.0.0.1:2376",
            "DOCKER_TLS_VERIFY": "1",
            "DOCKER_CERT_PATH": str(Path.home() / ".docker" / "tls"),
        },
    ]


def docker_environment() -> dict[str, str] | None:
    """An inherited DOCKER_HOST, or the local socket, or the workstation's TLS endpoint."""
    global _docker_environment, _docker_probe_error
    if _docker_environment is not None:
        return _docker_environment

    candidates = docker_candidates(os.environ)
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


def _ensure_image(environment: dict[str, str]) -> None:
    """A remote daemon that has never run this suite has no image, and the pull outlasts the
    ordinary command timeout on a residential uplink."""
    present = subprocess.run(
        ["docker", "image", "inspect", POSTGIS_IMAGE],
        env=environment,
        check=False,
        capture_output=True,
        timeout=60,
    )
    if present.returncode == 0:
        return
    subprocess.run(
        ["docker", "pull", POSTGIS_IMAGE],
        env=environment,
        check=True,
        capture_output=True,
        timeout=PULL_TIMEOUT_SECONDS,
    )


def _container_address(environment: dict[str, str], name: str) -> str:
    """host:port the test process connects to: the published port on a remote daemon, the
    bridge IP on a local one."""
    host = daemon_address(environment)
    if host is None:
        bridge = _docker(
            environment,
            "inspect",
            "-f",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            name,
        )
        return f"{bridge}:5432"
    mapping = _docker(environment, "port", name, "5432/tcp")
    return f"{host}:{mapping.splitlines()[0].rsplit(':', 1)[1]}"


def _bridge_address(environment: dict[str, str], name: str) -> str:
    """host:port a sibling container connects to. Always the bridge network, wherever the
    test process happens to be."""
    bridge = _docker(
        environment,
        "inspect",
        "-f",
        "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
        name,
    )
    return f"{bridge}:5432"


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


ROLE_DECLARATION = re.compile(r"create role (\w+)((?: (?:no)?login)?)\s*;")


def ensure_cluster_roles(dsn_template: str) -> None:
    """Create every role the migrations declare, before any worker migrates.

    A role is cluster-global, not per-database. 001, 026 and 076 each create theirs inside a
    `if not exists (select 1 from pg_roles ...)` block, and four xdist workers migrating their
    own template against one shared server all pass that check in the same instant and then all
    issue the CREATE. The first sharded CI run errored 843 tests on
    `duplicate key value violates unique constraint "pg_authid_rolname_index"`. Every migration
    that runs afterwards -- the templates, and the `empty_db` tests that migrate from scratch --
    finds the roles present and never takes the branch. The names and their login attribute are
    read from the migrations rather than restated here, so a new role needs no edit.
    """
    declared: dict[str, str] = {}
    for migration in discover_migrations():
        for name, attributes in ROLE_DECLARATION.findall(migration.sql):
            declared[name] = attributes.strip()
    with psycopg.connect(dsn_template.format(database="postgres"), autocommit=True) as admin:
        for name, attributes in declared.items():
            # Another worker winning the same race is the expected outcome, not a failure;
            # autocommit means the connection survives it and the next role still runs.
            with contextlib.suppress(psycopg.errors.DuplicateObject):
                admin.execute(f"create role {name} {attributes}".strip())


def worker_scoped(name: str) -> str:
    """A fixed database name, made unique per xdist worker.

    Session fixtures run once per worker, so `glasswell_template` is created four times over
    on one server -- a collision, not a race the workers survive. A worker that owns its own
    container is unaffected either way.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    return f"{name}_{worker}" if worker else name


@pytest.fixture(scope="session")
def postgres_server() -> Iterator[str]:
    """Session-scoped PostGIS container. Yields a DSN template with a {database} slot."""
    provided = os.environ.get(SERVER_DSN_ENV)
    if provided:
        # The workflow starts and removes the server the shards share, because a worker's
        # teardown is not guaranteed and a leaked container outlives the job that made it.
        _wait_until_ready(provided.format(database="postgres"))
        ensure_cluster_roles(provided)
        yield provided
        return
    environment = docker_environment()
    if environment is None:
        # CI sets this: a green run that skipped 414 of 677 tests is worse than a red one.
        if os.environ.get(REQUIRE_DOCKER_ENV):
            pytest.fail(f"{REQUIRE_DOCKER_ENV} is set but docker is unavailable"
                        f" ({_docker_probe_error})", pytrace=False)
        pytest.skip(f"docker unavailable, integration tier skipped ({_docker_probe_error})")

    global _session_container, _session_volume, _session_container_address, _session_password
    _ensure_image(environment)
    name = f"glasswell-test-{uuid4().hex[:8]}"
    volume = f"{name}-data"
    # Published on a remote daemon, so the credential is per-session rather than a known pair
    # on a LAN-reachable port.
    password = _session_password = uuid4().hex
    # A named volume rather than the image's anonymous one: `--rm` does not reclaim a volume
    # when the session is killed rather than exiting, which is how 151 of them accumulated.
    _docker(environment, "volume", "create", "--label", TEST_LABEL, volume)
    _docker(
        environment,
        "run", "-d", "--rm", "--name", name,
        "--label", TEST_LABEL,
        *(["-p", "5432"] if daemon_address(environment) else []),
        "-v", f"{volume}:{DATA_DIRECTORY}",
        "-e", "POSTGRES_USER=glasswell",
        "-e", f"POSTGRES_PASSWORD={password}",
        "-e", "POSTGRES_DB=postgres",
        POSTGIS_IMAGE,
        *(argument for setting in EPHEMERAL_SERVER_SETTINGS for argument in ("-c", setting)),
    )
    _session_container, _session_volume = name, volume
    try:
        _session_container_address = _bridge_address(environment, name)
        address = _container_address(environment, name)
        dsn_template = (
            f"postgresql://glasswell:{password}@{address}/{{database}}?{CONNECTION_PARAMETERS}"
        )
        _wait_until_ready(dsn_template.format(database="postgres"))
        ensure_cluster_roles(dsn_template)
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
    if os.environ.get(SERVER_DSN_ENV):
        pytest.skip(
            f"{SERVER_DSN_ENV} names the server, so this session owns no container;"
            " the self-managed path runs as its own CI job"
        )
    return _session_container, _session_volume


@pytest.fixture(scope="session")
def postgres_password(postgres_server: str) -> str:
    """`ConnectionInfo.dsn` never carries the password, so anything that reconnects from one
    needs it out of band."""
    return _session_password


@pytest.fixture(scope="session")
def database_address_for_containers(postgres_server: str) -> str:
    """What a container started by a test puts in its DSN. Not the same host:port the test
    process uses once the daemon is remote."""
    return _session_container_address


def create_database(dsn_template: str, name: str, template: str | None = None) -> str:
    with psycopg.connect(dsn_template.format(database="postgres"), autocommit=True) as admin:
        # file_copy only beats the wal_log default because EPHEMERAL_SERVER_SETTINGS makes the
        # checkpoints it forces free; at the shipped durability settings it is twice as slow.
        clause = f' template "{template}" strategy file_copy' if template else ""
        admin.execute(f'create database "{name}"{clause}')
    return dsn_template.format(database=name)


def drop_database(dsn_template: str, name: str) -> None:
    with psycopg.connect(dsn_template.format(database="postgres"), autocommit=True) as admin:
        admin.execute(f'drop database if exists "{name}" with (force)')


@pytest.fixture(scope="session")
def migrated_template(postgres_server: str) -> Iterator[str]:
    """Migrations and shared fixture rows run once; every test database is cloned from here."""
    name = worker_scoped(TEMPLATE_DATABASE)
    dsn = create_database(postgres_server, name)
    with psycopg.connect(dsn) as connection:
        migrate(connection)
        connection.commit()
        _seed_fixture_rows(connection)
        connection.commit()
    yield postgres_server
    drop_database(postgres_server, name)


def _seed_fixture_rows(connection: psycopg.Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.environments (env_id, python_version, threads)"
            " values (%s, '3.12.10', 1)",
            (FIXTURE_ENV_ID,),
        )
        cursor.executemany(
            "insert into lineage.sources (source_id, name, jurisdiction) values (%s, %s, %s)",
            [
                (source, source.replace("_", " "), jurisdiction)
                for source, jurisdiction in FIXTURE_SOURCES
            ],
        )


SCOPE_SAVEPOINT = "gw_test_scope"


def scoped_transaction(connection: psycopg.Connection) -> Iterator[psycopg.Connection]:
    """Yield a shared connection whose whole test is one transaction, rolled back at the end.

    `commit` and `rollback` are rebound to a savepoint pair for the duration, so code under
    test keeps the per-request atomicity it was written against while nothing it writes
    outlives the test. A test whose writes must be visible to a second connection -- anything
    that reconnects, forks a client, or asserts on another session -- needs `db` instead.
    """
    committed, rolled_back = connection.commit, connection.rollback
    connection.execute(f"savepoint {SCOPE_SAVEPOINT}")
    connection.commit = lambda: _restart_scope(connection, release=True)
    connection.rollback = lambda: _restart_scope(connection, release=False)
    try:
        yield connection
    finally:
        connection.commit, connection.rollback = committed, rolled_back
        connection.rollback()


def _restart_scope(connection: psycopg.Connection, *, release: bool) -> None:
    verb = "release" if release else "rollback to"
    connection.execute(f"{verb} savepoint {SCOPE_SAVEPOINT}")
    connection.execute(f"savepoint {SCOPE_SAVEPOINT}")


def build_template(dsn_template: str, name: str, seed: Callable[[psycopg.Connection], None]) -> str:
    """A database seeded once and left closed, for other databases to be cloned from.

    Postgres refuses to clone a template anything is connected to, so the connection is closed
    before the name is returned.
    """
    drop_database(dsn_template, name)
    dsn = create_database(dsn_template, name, template=worker_scoped(TEMPLATE_DATABASE))
    with psycopg.connect(dsn) as connection:
        seed(connection)
        connection.commit()
    return name


@pytest.fixture(scope="module")
def module_template(
    migrated_template: str,
) -> Iterator[Callable[[str, Callable[[psycopg.Connection], None]], str]]:
    """Build a module's shared data once, into a template its tests clone per test.

    A fixture that inserts the same rows into an empty clone for every test in a file pays the
    whole build per test: A-timing measured 2.7-7.4 s of it on each Texas load, against the
    145 ms the clone itself costs.
    """
    built: list[str] = []

    def build(label: str, seed: Callable[[psycopg.Connection], None]) -> str:
        name = build_template(migrated_template, worker_scoped(f"gw_tpl_{label}"), seed)
        built.append(name)
        return name

    yield build
    for name in built:
        drop_database(migrated_template, name)


@pytest.fixture
def clone(migrated_template: str) -> Iterator[Callable[[str], psycopg.Connection]]:
    """A database of this test's own, cloned from a named template and dropped after it."""
    opened: list[tuple[str, psycopg.Connection]] = []

    def make(template: str) -> psycopg.Connection:
        name = f"gw_test_{uuid4().hex[:12]}"
        connection = psycopg.connect(create_database(migrated_template, name, template=template))
        opened.append((name, connection))
        return connection

    yield make
    for name, connection in opened:
        connection.close()
        drop_database(migrated_template, name)


@pytest.fixture(scope="session")
def shared_database(migrated_template: str) -> Iterator[psycopg.Connection]:
    """One migrated database, and one connection to it, for the whole worker."""
    name = worker_scoped("gw_shared")
    connection = psycopg.connect(
        create_database(migrated_template, name, template=worker_scoped(TEMPLATE_DATABASE))
    )
    try:
        yield connection
    finally:
        connection.close()
        drop_database(migrated_template, name)


@pytest.fixture
def db_ro(shared_database: psycopg.Connection) -> Iterator[psycopg.Connection]:
    """The worker's shared database, inside a transaction this test cannot commit.

    1.1 ms against the 145 ms a clone costs (A-timing.md 2). For read-only tests: the writes a
    test makes to set itself up are visible to it and to nothing else, ever.
    """
    yield from scoped_transaction(shared_database)


@pytest.fixture
def db(migrated_template: str) -> Iterator[psycopg.Connection]:
    """A migrated database of its own, per test."""
    name = f"gw_test_{uuid4().hex[:12]}"
    dsn = create_database(migrated_template, name, template=worker_scoped(TEMPLATE_DATABASE))
    connection = psycopg.connect(dsn)
    try:
        yield connection
    finally:
        connection.close()
        drop_database(migrated_template, name)


@pytest.fixture
def empty_db(postgres_server: str) -> Iterator[psycopg.Connection]:
    """An un-migrated database, for exercising the migration runner itself."""
    name = f"gw_empty_{uuid4().hex[:12]}"
    dsn = create_database(postgres_server, name)
    connection = psycopg.connect(dsn)
    try:
        yield connection
    finally:
        connection.close()
        drop_database(postgres_server, name)


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


@pytest.fixture(scope="module")
def module_raw_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One raw zone for a whole module, for the files whose load runs once into a template.

    A second load a test makes then addresses the same content-addressed store the first one
    wrote to, which is where it wrote when both ran inside a single test.
    """
    return tmp_path_factory.mktemp("raw")


@pytest.fixture
def shared_raw_root(module_raw_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`module_raw_root`, with the env var pointed at it for the length of the test."""
    monkeypatch.setenv(RAW_ROOT_ENV, str(module_raw_root))
    return module_raw_root


def install_lineage_env(connection: psycopg.Connection) -> DeriveEnvironment:
    """The pinned environment row derive()'s NOT NULL env_id FK needs, and its handle."""
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.environments (env_id, python_version, threads, lockfile_sha256)"
            " values (%s, '3.12.10', 1, %s) on conflict (env_id) do nothing",
            (LINEAGE_FIXTURE_ENV_ID, "0" * 64),
        )
    return DeriveEnvironment(
        code_version="git:0000test", code_dirty=False, env_id=LINEAGE_FIXTURE_ENV_ID
    )


@pytest.fixture
def lineage_env(db: psycopg.Connection) -> DeriveEnvironment:
    """A pinned environment row, so derive()'s NOT NULL env_id FK is satisfiable."""
    return install_lineage_env(db)


@pytest.fixture
def api_client(db: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The real app, with its connection dependency bound to this test's database."""
    monkeypatch.setenv(OWNER_KEY_ENV, CONTRACT_OWNER_KEY)
    monkeypatch.setenv(CSRF_KEY_ENV, CONTRACT_CSRF_KEY)
    monkeypatch.delenv(ALLOW_ANON_ENV, raising=False)
    application = create_app()
    application.dependency_overrides[get_connection] = lambda: db
    with TestClient(application, headers={KEY_HEADER: CONTRACT_OWNER_KEY}) as client:
        yield client
