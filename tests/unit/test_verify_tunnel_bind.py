"""The tunnel-bind assertion, executed rather than read.

It shipped as an unconditional existence check and failed the v0.66 deploy on a host with
nothing bound to 8080, reporting "8080 is bound off-loopback" — not merely a failing
assertion but a false statement about the host. Two claims were conflated: *if* a tunnel
listener exists it must be loopback-only, which is true everywhere, and *a tunnel listener
exists*, which is true only where a tunnel is configured.

These run the real function out of `verify.sh` under a stubbed `ss`, so they test the shell
that ships rather than a restatement of it. The LAN case is first because it is the one that
broke and the one every non-public deploy hits.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

VERIFY = Path(__file__).resolve().parents[2] / "infra" / "verify.sh"
NEEDED = ("ok", "bad", "assert_true", "assert_false", "listening_on", "assert_tunnel_listener_bind")


def extract(name: str) -> str:
    """Pull one function definition out of verify.sh by name.

    The file defines every function at column zero and closes it at column zero, either as a
    one-liner or as a block, which is what makes this reliable rather than clever.
    """
    source = VERIFY.read_text(encoding="utf-8")
    oneline = re.search(rf"^{re.escape(name)}\(\) \{{.*\}}$", source, re.MULTILINE)
    if oneline:
        return oneline.group(0)
    start = re.search(rf"^{re.escape(name)}\(\) \{{$", source, re.MULTILINE)
    assert start, f"{name}() is not defined in verify.sh"
    end = source.index("\n}\n", start.start())
    return source[start.start() : end + 3]


def run_with(listeners: list[str]) -> tuple[int, int, str]:
    """Run the assertion against a synthetic `ss -ltn` table. Returns (passed, failed, output)."""
    table = "\n".join(
        f"LISTEN 0      4096       {address}      0.0.0.0:*" for address in listeners
    )
    script = "\n".join(
        [
            "set -uo pipefail",
            "passed=0",
            "failed=0",
            # The only stub. `listening_on` and every assert below are the shipped code.
            f"ss() {{ printf '%s\\n' 'State Recv-Q Send-Q Local Address:Port' {table!r}; }}",
            *(extract(name) for name in NEEDED),
            "assert_tunnel_listener_bind",
            'printf "RESULT %s %s\\n" "$passed" "$failed"',
        ]
    )
    finished = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=60
    )
    assert finished.returncode == 0, finished.stderr
    tallies = re.search(r"RESULT (\d+) (\d+)", finished.stdout)
    assert tallies, finished.stdout
    return int(tallies.group(1)), int(tallies.group(2)), finished.stdout


def test_a_host_with_nothing_on_8080_passes() -> None:
    """The v0.66 deploy failure. Every LAN deploy is this case."""
    passed, failed, output = run_with(["127.0.0.1:3000", "0.0.0.0:443"])

    assert failed == 0, output
    assert passed == 2
    # The point is not just that it passes: an unconditional check *failed* here, and its
    # message asserted a binding the host did not have.
    assert "FAIL" not in output, "a host with nothing on 8080 must not report a failure"


def test_a_host_with_nothing_on_8080_says_so_rather_than_claiming_a_binding() -> None:
    _, _, output = run_with([])

    assert "nothing is listening on 8080" in output


def test_a_loopback_tunnel_listener_passes() -> None:
    passed, failed, output = run_with(["127.0.0.1:8080", "127.0.0.1:3000"])

    assert failed == 0, output
    assert passed == 2


def test_a_tunnel_listener_on_every_interface_fails_both_ways() -> None:
    """The property the assertion exists for."""
    _, failed, output = run_with(["0.0.0.0:8080"])

    assert failed == 2, output
    assert "8080 is bound off-loopback" in output
    assert "8080 is on 0.0.0.0" in output


def test_a_tunnel_listener_on_a_named_interface_still_fails() -> None:
    """The subtle one: bound to the LAN address, so the `0.0.0.0` negative alone would miss it
    and the conditional positive is what catches it."""
    _, failed, output = run_with(["192.168.2.111:8080"])

    assert failed == 1, output
    assert "8080 is bound off-loopback" in output


def test_the_negative_holds_when_nothing_is_listening_at_all() -> None:
    """It is unconditional on purpose: "not on every interface" is true of an empty host, so it
    keeps proving the property before any exposure exists."""
    _, failed, output = run_with([])

    assert failed == 0
    assert "not on every interface" in output


def test_a_similar_port_is_not_mistaken_for_the_tunnel() -> None:
    """`:8080` must not match `:18080`, or an unrelated service would trigger the check."""
    _, failed, output = run_with(["0.0.0.0:18080"])

    assert failed == 0, output
    assert "nothing is listening on 8080" in output
