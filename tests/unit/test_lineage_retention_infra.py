from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / "infra"
SERVICE = INFRA / "systemd" / "glasswell-lineage-retention.service"
TIMER = INFRA / "systemd" / "glasswell-lineage-retention.timer"


def _setting(path: Path, name: str) -> str:
    prefix = f"{name}="
    values = [
        line.split("=", 1)[1]
        for line in path.read_text().splitlines()
        if line.startswith(prefix)
    ]
    assert len(values) == 1
    return values[0]


def test_retention_service_is_unprivileged_socket_only_and_bounded() -> None:
    assert _setting(SERVICE, "User") == "glasswell"
    assert _setting(SERVICE, "Group") == "glasswell"
    assert _setting(SERVICE, "ExecStart") == (
        "/opt/glasswell/venv/bin/python -m glasswell.lineage.retention"
    )
    assert _setting(SERVICE, "RestrictAddressFamilies") == "AF_UNIX"
    assert _setting(SERVICE, "NoNewPrivileges") == "yes"
    assert _setting(SERVICE, "CapabilityBoundingSet") == ""
    assert _setting(SERVICE, "TimeoutStartSec") == "300"


def test_retention_timer_is_nightly_persistent_and_alerted() -> None:
    assert _setting(TIMER, "OnCalendar") == "*-*-* 03:30:00"
    assert _setting(TIMER, "Persistent") == "true"
    assert _setting(TIMER, "Unit") == "glasswell-lineage-retention.service"
    assert _setting(TIMER, "WantedBy") == "timers.target"
    assert _setting(TIMER, "OnFailure") == "glasswell-alert@%n.service"


def test_retention_is_installed_armed_after_migrations_and_verified() -> None:
    install = (INFRA / "install.sh").read_text()
    deploy = (ROOT / "scripts" / "deploy.sh").read_text()
    verify = (INFRA / "verify.sh").read_text()

    assert "glasswell-lineage-retention.service glasswell-lineage-retention.timer" in install
    assert "systemctl enable glasswell-lineage-retention.timer" in install
    assert "systemctl enable --now glasswell-lineage-retention.timer" not in install
    migration = deploy.index("if (( with_migrations ))")
    timer = deploy.index('remote "systemctl start glasswell-lineage-retention.timer"')
    service = deploy.index('remote "systemctl start glasswell-lineage-retention.service"')
    collect = deploy.index('remote "systemctl start glasswell-status.service"')
    assert migration < timer < service < collect
    for fragment in (
        "systemctl is-enabled glasswell-lineage-retention.timer",
        "systemctl is-active glasswell-lineage-retention.timer",
        "systemctl show glasswell-lineage-retention.service -p Result --value",
    ):
        assert fragment in verify


def test_status_collector_names_the_retention_job() -> None:
    collector = (ROOT / "src" / "glasswell" / "status" / "collector.py").read_text()

    assert '"lineage_retention"' in collector
    assert '"glasswell-lineage-retention.timer"' in collector
    assert '"glasswell-lineage-retention.service"' in collector
