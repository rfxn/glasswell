"""DR-25 / N-10: the test harness must not leave storage behind it.

Anonymous volumes from the session container filled `/home` to 100 % twice in one session,
across two agents, and turned 398 integration tests red with `PANIC: could not write to
pg_wal`. Every volume this harness attaches therefore carries a label, so a sweep can find
them without guessing and without touching anything else on the host.
"""

from __future__ import annotations

import json
import multiprocessing
import subprocess
from uuid import uuid4

import psycopg
import pytest

from tests.conftest import (
    DATA_DIRECTORY,
    TEST_LABEL,
    create_cluster_roles,
    daemon_address,
    docker_environment,
)


def inspect(what: str, name: str) -> dict:
    environment = docker_environment()
    assert environment is not None, "the postgres_server fixture proved docker is reachable"
    completed = subprocess.run(
        ["docker", what, "inspect", name],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(completed.stdout)[0]


@pytest.fixture
def resources(session_resources: tuple[str, str]) -> tuple[str, str]:
    container, volume = session_resources
    assert container, "the session fixture published no container name"
    assert volume, "the session fixture published no volume name"
    return container, volume


def test_the_session_container_carries_the_sweep_label(resources):
    container, _ = resources
    labels = inspect("container", container)["Config"]["Labels"] or {}
    key, value = TEST_LABEL.split("=")
    assert labels.get(key) == value


def test_every_volume_the_harness_attaches_is_labelled(resources):
    """An unlabelled volume is one a sweep cannot distinguish from a real one."""
    container, _ = resources
    key, value = TEST_LABEL.split("=")
    mounts = inspect("container", container)["Mounts"]

    assert mounts, "the container mounted nothing, so postgres wrote to its writable layer"
    for mount in mounts:
        assert mount["Type"] == "volume", f"{mount['Destination']} is a {mount['Type']}"
        labels = inspect("volume", mount["Name"])["Labels"] or {}
        assert labels.get(key) == value, f"{mount['Name']} would survive every sweep"


def test_the_data_directory_is_the_mount_that_is_labelled(resources):
    container, volume = resources
    attached = inspect("container", container)["Mounts"]
    mounts = {mount["Destination"]: mount["Name"] for mount in attached}
    assert mounts.get(DATA_DIRECTORY) == volume


def test_the_container_publishes_its_port_exactly_when_the_daemon_is_remote(resources):
    """DIR-14: the same suite has to run on freedom's socket and on anvil's TLS endpoint. A
    bridge IP answers only on the first, a published port is needed for the second."""
    container, _ = resources
    published = inspect("container", container)["NetworkSettings"]["Ports"].get("5432/tcp")
    if daemon_address(docker_environment()) is None:
        assert not published, "a local daemon reaches the bridge, so publishing exposes it"
    else:
        assert published, "a remote daemon's bridge network is not routable from here"


def test_the_client_dsn_and_the_container_dsn_agree_about_locality(
    resources, postgres_server: str, database_address_for_containers: str
):
    container, _ = resources
    remote = daemon_address(docker_environment())
    client_host = postgres_server.format(database="postgres").split("@")[1].split(":")[0]
    bridge_host = database_address_for_containers.split(":")[0]

    assert bridge_host == inspect("container", container)["NetworkSettings"]["IPAddress"]
    if remote is None:
        assert client_host == bridge_host
    else:
        assert client_host == remote != bridge_host


def test_a_write_through_db_ro_never_reaches_the_database(
    db_ro: psycopg.Connection, postgres_server: str
) -> None:
    """`db_ro` trades a database per test for a transaction per test, so its commits cannot be
    real ones: every test after it reads the shared database the fixture handed the first."""
    db_ro.execute(
        "insert into lineage.environments (env_id, python_version, threads)"
        " values ('env_db_ro_probe', '3.12.10', 1)"
    )
    db_ro.commit()

    with psycopg.connect(postgres_server.format(database=db_ro.info.dbname)) as observer:
        landed = observer.execute(
            "select count(*) from lineage.environments where env_id = 'env_db_ro_probe'"
        ).fetchone()[0]

    assert landed == 0, "a db_ro write outlived its transaction, so the tier is order-dependent"
    assert db_ro.execute(
        "select count(*) from lineage.environments where env_id = 'env_db_ro_probe'"
    ).fetchone()[0] == 1, "the test cannot read its own write, so db_ro is unusable"


# Four sessions, the shard count, each creating the same eight roles at the same instant. The
# window is between the unique index's probe and its insert, so it is opened once per role per
# round: 4 x 8 x 6 = 192 chances for two sessions to both pass the check.
RACE_SESSIONS = 4
RACE_ROLES = 8
RACE_ROUNDS = 6


def _create_in_a_race(dsn_template: str, names: list[str], barrier, results, index: int) -> None:
    declared = dict.fromkeys(names, "nologin")
    barrier.wait()
    try:
        create_cluster_roles(dsn_template, declared)
        results[index] = "ok"
    except Exception as error:  # the point of the test is which class arrives here
        results[index] = f"{type(error).__name__}({getattr(error, 'sqlstate', None)}): {error}"


def test_four_sessions_creating_the_same_roles_do_not_collide(postgres_server: str) -> None:
    """A role is cluster-global and `if not exists` is not a lock, so the first sharded CI run
    errored 843 tests on `pg_authid_rolname_index`. The race is forced here rather than waited
    for: every session issues its CREATEs on one barrier, and any of them raising is the defect.
    """
    context = multiprocessing.get_context("fork")
    for _ in range(RACE_ROUNDS):
        names = [f"gw_race_{uuid4().hex[:10]}_{n}" for n in range(RACE_ROLES)]
        barrier = context.Barrier(RACE_SESSIONS)
        outcomes = context.Manager().list([""] * RACE_SESSIONS)
        workers = [
            context.Process(
                target=_create_in_a_race,
                args=(postgres_server, names, barrier, outcomes, index),
            )
            for index in range(RACE_SESSIONS)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(120)

        failures = [outcome for outcome in outcomes if outcome != "ok"]
        with psycopg.connect(postgres_server.format(database="postgres"), autocommit=True) as admin:
            created = {
                row[0]
                for row in admin.execute(
                    "select rolname from pg_roles where rolname = any(%s)", (names,)
                ).fetchall()
            }
            for name in names:
                admin.execute(f'drop role if exists "{name}"')

        assert not failures, failures
        assert created == set(names), sorted(set(names) - created)
