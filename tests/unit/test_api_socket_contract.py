"""The Caddy→uvicorn hop is a unix socket, and four files have to agree about it.

`tmpfiles.d/glasswell.conf` creates the directory, `glasswell-api.service` binds the socket in
it, the Caddyfile dials it, and `verify.sh` probes it. A disagreement between any two of them
is a 502 that no unit test would otherwise catch, because each file is individually valid.

The `--forwarded-allow-ips *` assertion is the load-bearing one. Over AF_UNIX uvicorn leaves
`scope["client"]` as `None` (`get_remote_addr` returns None for a non-INET peer), and
`_TrustedHosts.__contains__` answers False for `None` — so a numeric allow-list silently stops
trusting `X-Forwarded-Proto` and every response loses `upgrade-insecure-requests` from its CSP.
Measured against uvicorn 0.52.4 on the deployed host; see work-output/uds-status.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

INFRA = Path(__file__).resolve().parents[2] / "infra"
UNIT_FILE = INFRA / "systemd" / "glasswell-api.service"
CADDYFILE = INFRA / "caddy" / "Caddyfile"
VERIFY = INFRA / "verify.sh"
TMPFILES = INFRA / "tmpfiles.d" / "glasswell.conf"


def exec_start() -> str:
    """The ExecStart line with systemd's trailing-backslash continuations folded out."""
    text = UNIT_FILE.read_text().replace("\\\n", " ")
    for line in text.splitlines():
        if line.startswith("ExecStart="):
            return line
    raise AssertionError(f"no ExecStart= in {UNIT_FILE}")


def unit_setting(name: str) -> str:
    for line in UNIT_FILE.read_text().splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    raise AssertionError(f"no {name}= in {UNIT_FILE}")


def socket_from_unit() -> str:
    match = re.search(r"--uds\s+(\S+)", exec_start())
    assert match, "glasswell-api.service does not bind a unix socket"
    return match.group(1)


def socket_from_caddyfile() -> str:
    match = re.search(r"reverse_proxy\s+unix/(\S+)", CADDYFILE.read_text())
    assert match, "the Caddyfile does not proxy to a unix socket"
    return match.group(1)


def test_the_unit_and_the_caddyfile_name_the_same_socket():
    assert socket_from_unit() == socket_from_caddyfile()


def test_verify_probes_the_socket_the_unit_binds():
    match = re.search(r"^API_SOCKET=(\S+)", VERIFY.read_text(), re.MULTILINE)
    assert match, "verify.sh does not define API_SOCKET"
    assert match.group(1) == socket_from_unit()


def tmpfiles_entry() -> list[str]:
    for line in TMPFILES.read_text().splitlines():
        if line.startswith("d "):
            return line.split()
    raise AssertionError(f"no directory entry in {TMPFILES}")


def test_tmpfiles_creates_the_socket_s_parent_directory():
    kind, path, *_ = tmpfiles_entry()
    assert kind == "d"
    assert Path(path) == Path(socket_from_unit()).parent


def test_the_socket_directory_is_caddy_readable_and_nothing_else():
    # uvicorn chmods the socket 0666 itself and offers no way to change it, so the directory
    # is the only access control there is.
    _, _, mode, owner, group, *_ = tmpfiles_entry()
    assert mode == "0750", f"mode {mode} would let any local user dial the API"
    assert owner == "glasswell"
    assert group == "caddy", "caddy could not traverse the directory to reach the socket"


def test_the_unit_does_not_declare_the_socket_directory_as_a_runtime_directory():
    # systemd re-applies exec-directory ownership on every exec invocation, so a
    # RuntimeDirectory= here would silently revert the tmpfiles group to glasswell and Caddy
    # would 502. This is the regression that cost a deploy.
    settings = [
        line for line in UNIT_FILE.read_text().splitlines() if not line.lstrip().startswith("#")
    ]
    assert not [line for line in settings if line.startswith("RuntimeDirectory")]


def test_the_unit_can_write_the_socket_directory_under_protectsystem_strict():
    parent = str(Path(socket_from_unit()).parent)
    assert "ProtectSystem=strict" in UNIT_FILE.read_text()
    assert parent in unit_setting("ReadWritePaths").split()


def test_a_stale_socket_is_removed_before_the_bind():
    # uvicorn's bind() returns EADDRINUSE on an existing path and it exits; with no
    # RuntimeDirectory= to delete the directory, an unclean stop would wedge every restart.
    socket_path = socket_from_unit()
    pre = [line for line in UNIT_FILE.read_text().splitlines() if line.startswith("ExecStartPre=")]
    assert any("rm" in line and socket_path in line for line in pre)


def test_a_unix_socket_forces_a_wildcard_forwarded_allow_ips():
    command = exec_start()
    assert "--uds" in command
    match = re.search(r"--forwarded-allow-ips\s+(\S+)", command)
    assert match, "--proxy-headers without --forwarded-allow-ips trusts 127.0.0.1 only"
    assert match.group(1).strip("'\"") == "*", (
        "over AF_UNIX the peer has no address, so a numeric allow-list drops the proxy headers"
        " and the CSP silently loses upgrade-insecure-requests"
    )


def test_the_unit_does_not_also_claim_a_tcp_bind():
    # uvicorn ignores --host/--port entirely when --uds is set. Leaving them in would read as
    # a listener that does not exist.
    command = exec_start()
    assert "--host" not in command
    assert "--port" not in command


def test_the_caddyfile_has_no_tcp_upstream_left():
    assert "reverse_proxy 127.0.0.1:8000" not in CADDYFILE.read_text()
