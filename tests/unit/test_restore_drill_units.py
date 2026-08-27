"""Installation and failure-reporting contract for backup protection units."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SYSTEMD = ROOT / "infra" / "systemd"
INSTALL = ROOT / "infra" / "install.sh"
ALERT = "OnFailure=glasswell-alert@%n.service"


def text(name: str) -> str:
    return (SYSTEMD / name).read_text(encoding="utf-8")


def test_backup_and_restore_services_and_timers_alert_on_failure() -> None:
    units = (
        "glasswell-backup.service",
        "glasswell-backup.timer",
        "glasswell-restore-drill.service",
        "glasswell-restore-drill.timer",
    )

    assert all(ALERT in text(unit) for unit in units)


def test_restore_timer_is_weekly_persistent_and_runs_only_the_drill_service() -> None:
    timer = text("glasswell-restore-drill.timer")

    assert "OnCalendar=Sun *-*-* 04:00:00" in timer
    assert "Persistent=true" in timer
    assert "Unit=glasswell-restore-drill.service" in timer
    assert "WantedBy=timers.target" in timer


def test_restore_service_is_bounded_private_and_writes_only_product_state() -> None:
    service = text("glasswell-restore-drill.service")

    assert "ExecStart=/usr/local/sbin/glasswell-restore-drill.sh" in service
    assert "TimeoutStartSec=4h" in service
    assert "NoNewPrivileges=yes" in service
    assert "ProtectSystem=strict" in service
    assert "ProtectHome=yes" in service
    assert "PrivateTmp=yes" in service
    assert "ReadWritePaths=/var/lib/glasswell" in service


def test_installer_places_both_units_and_preserves_an_armed_backup_schedule() -> None:
    script = INSTALL.read_text(encoding="utf-8")

    assert "glasswell-restore-drill.service glasswell-restore-drill.timer" in script
    condition = (
        "if [[ $enable_backup -eq 1 ]] || systemctl is-enabled --quiet glasswell-backup.timer"
    )
    enabled_block = script.split(condition, 1)[1].split("fi", 1)[0]
    assert "systemctl enable glasswell-backup.timer glasswell-restore-drill.timer" in enabled_block
    assert "systemctl enable glasswell-restore-drill.timer" not in script.replace(enabled_block, "")


def test_deploy_starts_restore_timer_only_when_it_is_enabled() -> None:
    script = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")

    condition = 'if remote "systemctl is-enabled --quiet glasswell-restore-drill.timer"'
    enabled_block = script.split(condition, 1)[1].split("fi", 1)[0]
    assert 'remote "systemctl start glasswell-restore-drill.timer"' in enabled_block


def test_live_verifier_requires_both_protection_timers_active() -> None:
    script = (ROOT / "infra" / "verify.sh").read_text(encoding="utf-8")

    assert 'assert "restore-drill timer follows backup enablement"' in script
    assert "if [[ $backup_enabled == enabled ]]" in script
    for unit in ("glasswell-backup.timer", "glasswell-restore-drill.timer"):
        assert f'assert "{unit} active" active' in script
