"""DIR-14: the harness has to run against anvil, not just against this workstation.

A container's bridge IP is routable only from the daemon's own host, so the address the test
process connects to and the address a sibling container connects to are the same thing only
when the daemon is local. `daemon_address` is the one decision that separates them.
"""

from __future__ import annotations

import pytest

from tests.conftest import daemon_address, docker_candidates


@pytest.mark.parametrize(
    "endpoint",
    ["", "unix:///var/run/docker.sock", "fd://", "npipe:////./pipe/docker_engine"],
)
def test_a_socket_daemon_is_local(endpoint):
    assert daemon_address({"DOCKER_HOST": endpoint}) is None


def test_an_unset_docker_host_is_local():
    assert daemon_address({}) is None


@pytest.mark.parametrize(
    "endpoint",
    ["tcp://127.0.0.1:2376", "tcp://localhost:2376", "tcp://[::1]:2376"],
)
def test_a_loopback_tcp_daemon_is_still_local(endpoint):
    """freedom's own TLS endpoint is TCP but not remote: the bridge network is routable."""
    assert daemon_address({"DOCKER_HOST": endpoint}) is None


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("tcp://anvil:2376", "anvil"),
        ("tcp://192.168.2.190:2376", "192.168.2.190"),
        ("ssh://root@anvil", "anvil"),
        ("tcp://anvil.lab.rpx.sh:2376", "anvil.lab.rpx.sh"),
    ],
)
def test_a_remote_daemon_is_addressed_by_its_own_host(endpoint, expected):
    assert daemon_address({"DOCKER_HOST": endpoint}) == expected


def test_an_explicit_docker_host_has_no_fallback():
    """A `make test-anvil` that fell back to this workstation would report a full suite
    against a host it never ran on."""
    assert docker_candidates({"DOCKER_HOST": "tcp://anvil:2376"}) == [{}]


def test_without_a_docker_host_the_local_endpoints_are_tried_in_turn():
    candidates = docker_candidates({})
    assert candidates[0] == {}
    assert daemon_address(candidates[-1]) is None
