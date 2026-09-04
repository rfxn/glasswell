"""Deployment contract for the scheduled, sanitized status snapshot.

The collector implementation lives with the application. These tests hold the independently
deployed systemd units, installer, deploy runner, and host verifier to one operational contract
without executing systemd or reading host credentials.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / "infra"
SERVICE = INFRA / "systemd" / "glasswell-status.service"
TIMER = INFRA / "systemd" / "glasswell-status.timer"
INSTALL = INFRA / "install.sh"
DEPLOY = ROOT / "scripts" / "deploy.sh"
VERIFY = INFRA / "verify.sh"
SMOKE = ROOT / "scripts" / "smoke.sh"
README = INFRA / "README.md"
# What the collector reads at `status/collector.py:730-738`, and nothing else.
UNIT_ENVIRONMENT = {"GLASSWELL_STATUS_PGDATA", "GLASSWELL_STATUS_PGDATA_MIN_BYTES"}
# `DSN` alone misses the two names this codebase actually reads a connection string from:
# `DATABASE_URL` (`status/collector.py:64`) and a libpq `PGPASSFILE`. The sibling ExecStart
# test refuses `DATABASE` for the same reason.
CREDENTIAL_NAME = re.compile(r"KEY|SECRET|TOKEN|PASSWORD|PGPASS|DSN|DATABASE|URL")


def active_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def settings(path: Path, name: str) -> list[str]:
    prefix = f"{name}="
    return [line.split("=", 1)[1] for line in active_lines(path) if line.startswith(prefix)]


def one_setting(path: Path, name: str) -> str:
    values = settings(path, name)
    assert len(values) == 1, f"expected one {name}= in {path}, found {values}"
    return values[0]


def test_service_runs_the_collector_as_the_unprivileged_product_user():
    assert one_setting(SERVICE, "Type") == "oneshot"
    assert one_setting(SERVICE, "User") == "glasswell"
    assert one_setting(SERVICE, "Group") == "glasswell"
    assert one_setting(SERVICE, "ExecStart") == (
        "/opt/glasswell/venv/bin/python -m glasswell.status.collector"
    )
    assert one_setting(SERVICE, "CapabilityBoundingSet") == ""
    assert one_setting(SERVICE, "NoNewPrivileges") == "yes"


def test_service_loads_runtime_identity_without_putting_secrets_on_the_command_line():
    assert settings(SERVICE, "EnvironmentFile") == [
        "/etc/glasswell/db.env",
        "-/etc/glasswell/code-version.env",
    ]
    command = one_setting(SERVICE, "ExecStart")
    assert "${" not in command
    assert "DATABASE" not in command
    assert "KEY" not in command
    assert "DSN" not in command


def test_no_secret_bearing_name_can_enter_the_units_tracked_environment_lines():
    names = {value.split("=", 1)[0] for value in settings(SERVICE, "Environment")}

    # This unit is in git and installed 0644 root:root, so anything set here is public by
    # construction — the reason the test above keeps credentials off ExecStart as well.
    assert names == UNIT_ENVIRONMENT
    # Live against whatever the set above grows into, not just against today's two names.
    assert [name for name in UNIT_ENVIRONMENT if CREDENTIAL_NAME.search(name)] == []


def test_service_is_bounded_and_only_the_state_directory_is_writable():
    assert one_setting(SERVICE, "TimeoutStartSec") == "120"
    assert one_setting(SERVICE, "StateDirectory") == "glasswell"
    assert one_setting(SERVICE, "StateDirectoryMode") == "0750"
    assert one_setting(SERVICE, "UMask") == "0027"
    assert one_setting(SERVICE, "ProtectSystem") == "strict"
    assert one_setting(SERVICE, "ReadWritePaths").split() == ["/var/lib/glasswell"]


def test_service_sandbox_keeps_only_required_peer_and_network_families():
    required = {
        "ProtectHome=yes",
        "PrivateTmp=yes",
        "PrivateDevices=yes",
        "ProtectKernelTunables=yes",
        "ProtectKernelModules=yes",
        "ProtectKernelLogs=yes",
        "ProtectControlGroups=yes",
        "RestrictNamespaces=yes",
        "RestrictSUIDSGID=yes",
        "LockPersonality=yes",
    }
    assert required <= set(active_lines(SERVICE))
    assert one_setting(SERVICE, "RestrictAddressFamilies").split() == [
        "AF_UNIX",
        "AF_INET",
        "AF_INET6",
    ]


def test_service_and_timer_failures_are_alerted():
    alert = "glasswell-alert@%n.service"
    assert one_setting(SERVICE, "OnFailure") == alert
    assert one_setting(TIMER, "OnFailure") == alert


def test_timer_runs_after_boot_and_each_quarter_hour_persistently():
    assert one_setting(TIMER, "OnBootSec") == "2min"
    assert one_setting(TIMER, "OnCalendar") == "*:0/15"
    assert one_setting(TIMER, "Persistent") == "true"
    assert one_setting(TIMER, "Unit") == "glasswell-status.service"
    assert one_setting(TIMER, "WantedBy") == "timers.target"


def test_installer_places_and_enables_the_timer_without_racing_migrations():
    text = INSTALL.read_text()
    assert "glasswell-status.service glasswell-status.timer" in text
    assert "systemctl enable glasswell-status.timer" in text
    assert "systemctl enable --now glasswell-status.timer" not in text
    assert "enable_status" not in text


def test_deploy_collects_after_restarts_and_before_verification():
    text = DEPLOY.read_text()
    api_restart = text.index('remote "systemctl restart glasswell-api"')
    martin_restart = text.index('remote "systemctl restart martin"')
    collect = text.index('remote "systemctl start glasswell-status.service"')
    timer = text.index('remote "systemctl start glasswell-status.timer"')
    verify = text.index('remote "$DEPLOY_SRC/infra/verify.sh"')
    migration = text.index("if (( with_migrations ))")
    assert api_restart < collect
    assert martin_restart < collect
    assert migration < timer < collect
    assert collect < verify
    assert "refuse \"glasswell-status did not produce a fresh snapshot\"" in text


def test_verify_checks_schedule_snapshot_safety_and_keyed_route_without_dumping_values():
    text = VERIFY.read_text()
    for fragment in (
        "systemctl is-enabled glasswell-status.timer",
        "systemctl is-active glasswell-status.timer",
        "systemctl show glasswell-status.service -p Result --value",
        'test -f "$STATUS_SNAPSHOT"',
        'test -L "$STATUS_SNAPSHOT"',
        "valid_status_snapshot",
        "status_snapshot_omits_private_environment",
        "status_api_serves_current_snapshot",
        '"$API/v1/status"',
    ):
        assert fragment in text
    assert 'cat "$STATUS_SNAPSHOT"' not in text
    assert 'json.tool "$STATUS_SNAPSHOT"' not in text
    status_request = text.split('assert "GET /v1/status', 1)[1].split("# B-1:", 1)[0]
    assert "-o /dev/null" in status_request
    assert '-H "X-Glasswell-Key: $owner_key"' in status_request
    assert "status.json" not in status_request
    assert "set -x" not in text

    freshness_check = text.split("status_api_serves_current_snapshot() {", 1)[1].split(
        "\n}", 1
    )[0]
    assert 'data["snapshot_state"] == "current"' in freshness_check
    assert 'data["datasets"]' in freshness_check
    assert 'item["state"] in {"degraded", "unavailable"}' in freshness_check
    assert 'item["state"] == "degraded"' in freshness_check


def test_verify_compares_private_environment_bytes_without_printing_them():
    text = VERIFY.read_text()
    function = text.split("status_snapshot_omits_private_environment() {", 1)[1].split("\n}", 1)[0]
    assert "/etc/glasswell/db.env" in function
    assert "/etc/glasswell/app.env" in function
    assert "len(value) >= 8" in function
    assert "if value in snapshot" in function
    assert "raise SystemExit(1)" in function
    assert "print(" not in function
    assert 'bad "$label" "$detail"' not in function


def test_infrastructure_runbook_describes_the_non_optional_snapshot_contract():
    text = README.read_text()
    assert "## Units" in text
    assert "### Status snapshot" in text
    assert "every 15 minutes" in text
    assert "systemctl enable glasswell-status.timer" in text
    assert "start it only after migrations" in text
    assert "systemctl start glasswell-status.service" in text
    assert "/v1/status" in text


def test_verify_asserts_the_session_surface_is_closed() -> None:
    """The three anonymous probes are the deploy gate's half of finding F-2 and O-2's
    closed-by-default ruling: a regression that reopened them would pass every unit test."""
    script = VERIFY.read_text(encoding="utf-8")

    for probe in ("/v1/wells?limit=1", "$API/docs", "$API/openapi.json"):
        assert probe in script, f"verify.sh no longer probes {probe} anonymously"
    assert "an anonymous /v1 request is refused" in script
    assert "at least one enabled owner account exists" in script
    assert "no default credential shipped" in script



def test_verify_skips_rather_than_fails_the_tunnel_section_before_cutover() -> None:
    """Otherwise every pre-cutover deploy goes red on probes for a hostname that
    deliberately does not resolve yet. The `ok` in the else branch keeps the count honest."""
    script = VERIFY.read_text(encoding="utf-8")

    assert "the tunnel section is intentionally skipped" in script
    assert "GLASSWELL_PUBLIC" in script


def test_smoke_never_takes_a_password_on_argv() -> None:
    """argv is visible in /proc to every local user and lands in shell history."""
    script = SMOKE.read_text(encoding="utf-8")

    assert "GLASSWELL_SMOKE_PASSWORD" in script
    assert "--password" not in script


def test_the_owner_console_commands_are_documented_runnable_as_written() -> None:
    """A procedure that does not run as written is worse than none: the next reader trusts it.

    Both entry points connect over the unix socket with peer authentication, so run as root
    the connection arrives as the role `root`, which does not exist, and psycopg fails before
    the password prompt. The documented command has to carry `runuser -u glasswell`.
    """
    docs = {
        "infra/README.md": README.read_text(encoding="utf-8"),
        "SMOKE.md": (ROOT / "SMOKE.md").read_text(encoding="utf-8"),
    }

    for name, text in docs.items():
        for line in text.splitlines():
            stripped = line.strip()
            names = ("glasswell-owner-bootstrap", "glasswell-owner-reset")
            if not any(name in stripped for name in names):
                continue
            # Only lines a reader pastes; prose and inline references are not commands.
            if not stripped.startswith(("runuser", "/opt")):
                continue
            assert "runuser -u glasswell" in stripped, (
                f"{name}: a pasteable owner command omits runuser and fails as root: {stripped}"
            )
