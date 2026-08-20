"""DR-25 / N-10: the test harness must not leave storage behind it.

Anonymous volumes from the session container filled `/home` to 100 % twice in one session,
across two agents, and turned 398 integration tests red with `PANIC: could not write to
pg_wal`. Every volume this harness attaches therefore carries a label, so a sweep can find
them without guessing and without touching anything else on the host.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from tests.conftest import DATA_DIRECTORY, TEST_LABEL, docker_environment


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
