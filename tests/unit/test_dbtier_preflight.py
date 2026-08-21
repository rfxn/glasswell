"""A reachable daemon is not a usable database tier.

`make test-anvil` sends the suite to a daemon across the LAN. The daemon answers a control
request in tens of milliseconds while the path underneath it stalls a bulk transfer for half a
minute, so `docker info` succeeding proves nothing about whether the tier can run. The
preflight is the difference between one sentence naming the path and a wall of identical
psycopg errors — see work-output/anvil-dbtier-status.md.
"""

from __future__ import annotations

import subprocess

import psycopg
import pytest

from tests.support import dbtier_preflight
from tests.support.dbtier_preflight import (
    PROBE_ATTEMPTS,
    SLOW_PROBE_BUDGET,
    SLOW_PROBE_MS,
    is_path_stall,
    path_verdict,
    preflight_message,
    probe,
    should_probe,
    stop_reason,
)


@pytest.mark.parametrize(
    "environment",
    [{}, {"DOCKER_HOST": ""}, {"DOCKER_HOST": "unix:///var/run/docker.sock"}],
)
def test_a_local_daemon_is_not_probed(environment):
    """The bridge network is routable on the daemon's own host, so there is no path to fail."""
    assert should_probe(environment) is None


def test_a_loopback_tcp_daemon_is_not_probed():
    assert should_probe({"DOCKER_HOST": "tcp://127.0.0.1:2376"}) is None


def test_a_remote_daemon_is_probed_and_named():
    assert should_probe({"DOCKER_HOST": "tcp://anvil:2376"}) == "anvil"


def test_the_probe_is_skippable_by_environment():
    environment = {"DOCKER_HOST": "tcp://anvil:2376", "GLASSWELL_SKIP_DBTIER_PREFLIGHT": "1"}
    assert should_probe(environment) is None


def test_a_quiet_path_passes():
    assert path_verdict([59.0, 66.0, 71.0, 73.0, 88.0], failures=0) is None


def test_a_single_hard_failure_fails_the_path():
    """A control request that does not complete is a path fault, not a slow one."""
    reason = path_verdict([59.0, 66.0, 71.0], failures=1)
    assert reason is not None
    assert "1 of 4" in reason


def test_slow_round_trips_within_budget_pass():
    durations = [60.0] * 19 + [SLOW_PROBE_MS + 1]
    assert path_verdict(durations, failures=0) is None


def test_slow_round_trips_over_budget_fail():
    """Loss on the path shows up as round-trips an order of magnitude off the median."""
    durations = [60.0] * 15 + [1200.0] * 5
    reason = path_verdict(durations, failures=0)
    assert reason is not None
    assert "5 of 20" in reason
    assert str(int(SLOW_PROBE_MS)) in reason


def test_the_budget_is_a_fraction_not_a_count():
    small = [60.0] * 8 + [1200.0] * 2
    large = [60.0] * 80 + [1200.0] * 20
    assert path_verdict(small, failures=0) is not None
    assert path_verdict(large, failures=0) is not None
    assert SLOW_PROBE_BUDGET < 0.2


def test_an_empty_probe_is_a_failure_not_a_pass():
    """No samples means the probe itself could not run; a green verdict would be a lie."""
    assert path_verdict([], failures=0) is not None


def test_an_unreachable_daemon_costs_one_attempt_not_all_of_them(monkeypatch):
    """An unreachable daemon at the full attempt count would outlast the wall of errors the
    preflight exists to replace."""
    calls = []

    def refuse(*_args, **kwargs):
        calls.append(kwargs.get("timeout"))
        raise subprocess.TimeoutExpired("docker", 15)

    monkeypatch.setattr(dbtier_preflight.subprocess, "run", refuse)
    durations, failures = probe({})
    assert (durations, failures) == ([], 1)
    assert len(calls) == 1


def test_a_reachable_daemon_is_sampled_to_the_attempt_count(monkeypatch):
    monkeypatch.setattr(
        dbtier_preflight.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, b"29.3.1", b""),
    )
    durations, failures = probe({})
    assert failures == 0
    assert len(durations) == PROBE_ATTEMPTS


@pytest.mark.parametrize(
    "message",
    [
        "consuming input failed: could not receive data from server: Connection timed out",
        "server closed the connection unexpectedly",
        "connection timeout expired",
    ],
)
def test_a_libpq_network_error_is_recognised_as_a_path_stall(message):
    """These are the shapes four chunks reported. Recognising them is what turns a wall of
    tracebacks into one abort."""
    assert is_path_stall(psycopg.OperationalError(message)) is True


@pytest.mark.parametrize(
    "message",
    [
        'relation "wells" does not exist',
        "duplicate key value violates unique constraint",
        "source database is being accessed by other users",
    ],
)
def test_an_ordinary_database_error_is_not_a_path_stall(message):
    """Aborting a run on a real test failure would hide the bug it just found."""
    assert is_path_stall(psycopg.OperationalError(message)) is False


def test_a_non_database_exception_is_not_a_path_stall():
    assert is_path_stall(ValueError("could not receive data from server")) is False


REMOTE = {"DOCKER_HOST": "tcp://anvil:2376"}
STALL = psycopg.OperationalError(
    "consuming input failed: could not receive data from server: Connection timed out"
)


def test_a_stall_against_a_remote_daemon_stops_the_run():
    """One stall in a session-scoped fixture produced 1063 errors and 545 passes in 6m40s."""
    reason = stop_reason(STALL, REMOTE)
    assert reason is not None
    assert "anvil" in reason
    assert "work-output/anvil-dbtier-status.md" in reason


def test_a_stall_against_a_local_daemon_does_not_stop_the_run():
    """The workstation's own daemon has no path to blame, so a stall there is a real failure."""
    assert stop_reason(STALL, {}) is None


def test_an_ordinary_failure_never_stops_the_run():
    assert stop_reason(psycopg.OperationalError('relation "wells" does not exist'), REMOTE) is None


def test_the_skip_override_also_suppresses_the_stop():
    """`run anyway` has to mean the whole run, or the override would be a lie."""
    forced = {**REMOTE, "GLASSWELL_SKIP_DBTIER_PREFLIGHT": "1"}
    assert stop_reason(STALL, forced) is None


def test_the_message_names_the_host_the_reason_and_the_way_out():
    message = preflight_message("anvil", "5 of 20 daemon round-trips exceeded 250 ms")
    assert "anvil" in message
    assert "5 of 20" in message
    assert "work-output/anvil-dbtier-status.md" in message
    assert "make test-local" in message
    assert "GLASSWELL_SKIP_DBTIER_PREFLIGHT" in message
