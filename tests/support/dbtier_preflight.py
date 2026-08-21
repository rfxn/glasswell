"""Refuse to start the database tiers on a daemon whose path cannot carry them.

`docker info` is a control request of a few hundred bytes; the tiers move megabytes per test
over the same path. On a degraded LAN hop the first succeeds and the second stalls until
psycopg's `tcp_user_timeout` aborts it, and because the container fixture is session-scoped
pytest replays that one exception for every database-backed test in the run. This module turns
that wall into one sentence. Measurements and the physical cause are in
work-output/anvil-dbtier-status.md.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import warnings
from collections.abc import Mapping, Sequence

import psycopg

SKIP_ENV = "GLASSWELL_SKIP_DBTIER_PREFLIGHT"
PROBE_ATTEMPTS = 24
PROBE_TIMEOUT_SECONDS = 15
# The point of the preflight is to be quicker than the failure it prevents, so it stops at the
# first verdict it cannot improve on and never outlasts one stalled psycopg connection.
PROBE_DEADLINE_SECONDS = 25
# A healthy remote round-trip measured 59-88 ms; a lost packet costs a retransmit timer, which
# is an order of magnitude more. The budget is what a run tolerates before the tiers are unsafe.
SLOW_PROBE_MS = 250.0
SLOW_PROBE_BUDGET = 0.10
# libpq's wording for "the connection died under me". Everything else psycopg raises is a real
# result the run should keep, so this list stays narrow.
PATH_STALL_MARKERS = (
    "could not receive data from server",
    "could not send data to server",
    "server closed the connection unexpectedly",
    "connection timeout expired",
    "connection is lost",
)


def should_probe(environment: Mapping[str, str]) -> str | None:
    """The remote host worth probing, or None when there is no path between test and container."""
    if environment.get(SKIP_ENV):
        return None
    # Imported here so a preflight run does not carry the app's import graph, or its warnings.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from tests.conftest import daemon_address
    return daemon_address(environment)


def is_path_stall(error: BaseException) -> bool:
    """True for a libpq error that means the path died, not that the query was wrong."""
    if not isinstance(error, psycopg.OperationalError):
        return False
    return any(marker in str(error) for marker in PATH_STALL_MARKERS)


def stop_reason(error: BaseException, environment: Mapping[str, str]) -> str | None:
    """Why the run should stop here, or None to let it carry on.

    A stall against a remote daemon has already cost the run: it is landing in session-scoped
    fixtures, and pytest replays that one exception for every test that follows.
    """
    if not is_path_stall(error):
        return None
    host = should_probe(environment)
    if host is None:
        return None
    return preflight_message(host, "a database connection stalled mid-run")


def path_verdict(durations_ms: Sequence[float], failures: int) -> str | None:
    """None when the path is fit to carry the tiers, else the reason it is not."""
    attempts = len(durations_ms) + failures
    if attempts == 0:
        return "the daemon probe produced no samples"
    if failures:
        return f"{failures} of {attempts} daemon round-trips did not complete"
    slow = sum(1 for duration in durations_ms if duration > SLOW_PROBE_MS)
    if slow > SLOW_PROBE_BUDGET * attempts:
        return f"{slow} of {attempts} daemon round-trips exceeded {int(SLOW_PROBE_MS)} ms"
    return None


def preflight_message(host: str, reason: str) -> str:
    return (
        f"{host} cannot carry the database tier: {reason}.\n"
        "The tiers move megabytes per test through published ports (tests/conftest.py), so a\n"
        "path this degraded stalls connections; each stall costs 30 s, and one inside the\n"
        "session-scoped container fixture is replayed for every database test in the run.\n"
        "See work-output/anvil-dbtier-status.md for the measurements and the physical fix.\n"
        f"Run `make test-local`, or set {SKIP_ENV}=1 to run against this daemon anyway."
    )


def probe(
    environment: Mapping[str, str], attempts: int = PROBE_ATTEMPTS
) -> tuple[list[float], int]:
    """Time `docker version` round-trips: the cheapest request that crosses the whole path."""
    durations: list[float] = []
    failures = 0
    deadline = time.monotonic() + PROBE_DEADLINE_SECONDS
    for _ in range(attempts):
        started = time.monotonic()
        try:
            completed = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                env=dict(environment),
                check=False,
                capture_output=True,
                timeout=PROBE_TIMEOUT_SECONDS,
            )
        except (subprocess.SubprocessError, OSError):
            return durations, failures + 1
        if completed.returncode != 0:
            return durations, failures + 1
        durations.append((time.monotonic() - started) * 1000)
        if time.monotonic() > deadline:
            break
    return durations, failures


def main() -> int:
    host = should_probe(os.environ)
    if host is None:
        return 0
    durations, failures = probe(os.environ)
    reason = path_verdict(durations, failures)
    if reason is None:
        median = sorted(durations)[len(durations) // 2]
        print(f"dbtier preflight: {host} ok ({len(durations)} round-trips, median {median:.0f} ms)")
        return 0
    print(preflight_message(host, reason), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
