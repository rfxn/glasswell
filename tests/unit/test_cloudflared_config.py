"""The ingress map is where "martin is not on the internet" is guaranteed.

Everything else about tile safety is a property of the application — the published-layer
allowlist, the session gate on `/v1/tiles/*`. This file holds the layer beneath them: the
connector publishes exactly one hostname to exactly one origin, and everything else is a 404.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

INFRA = Path(__file__).resolve().parents[2] / "infra"
CONFIG_PATH = INFRA / "cloudflared" / "config.yml"
UNIT_PATH = INFRA / "systemd" / "cloudflared.service"

MARTIN_PORT = "3000"
CADDY_TUNNEL_ORIGIN = "http://127.0.0.1:8080"


@pytest.fixture(scope="module")
def config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def raw() -> str:
    return CONFIG_PATH.read_text(encoding="utf-8")


def test_the_ingress_publishes_one_hostname_and_a_catch_all(config: dict) -> None:
    ingress = config["ingress"]

    hostnames = [rule for rule in ingress if "hostname" in rule]
    assert len(hostnames) == 1, f"expected exactly one published hostname, got {hostnames}"
    assert ingress[-1] == {"service": "http_status:404"}, "the catch-all is not a 404"


def test_the_ingress_names_no_tile_server_port(raw: str, config: dict) -> None:
    """SB-06 §4.5's /tiles/* block bypasses the allowlist and the session gate together."""
    for rule in config["ingress"]:
        assert MARTIN_PORT not in rule.get("service", "")
    directives = "\n".join(
        line for line in raw.splitlines() if not line.strip().startswith("#")
    )
    assert MARTIN_PORT not in directives


def test_the_ingress_names_no_database_and_no_ssh(config: dict) -> None:
    services = " ".join(rule.get("service", "") for rule in config["ingress"])

    for forbidden in ("5432", ":22", "ssh://", "postgres", "tcp://"):
        assert forbidden not in services, f"{forbidden} is published through the tunnel"


def test_the_origin_is_the_caddy_tunnel_listener(config: dict) -> None:
    published = next(rule for rule in config["ingress"] if "hostname" in rule)

    assert published["service"] == CADDY_TUNNEL_ORIGIN


def test_the_credentials_file_is_referenced_by_path_and_not_in_the_tree(config: dict) -> None:
    """A tunnel secret in the repository is a tunnel secret in every clone and archive."""
    assert config["credentials-file"].startswith("/etc/cloudflared/")

    assert list(CONFIG_PATH.parent.glob("*.json")) == []
    assert list(CONFIG_PATH.parent.glob("*.pem")) == []


def test_the_tracked_config_carries_a_placeholder_not_a_real_tunnel(config: dict) -> None:
    """install.sh substitutes it on the host from /etc/cloudflared/tunnel-id."""
    assert config["tunnel"] == "<tunnel-uuid>"


def test_the_metrics_listener_is_loopback_only(config: dict) -> None:
    assert config["metrics"].startswith("127.0.0.1:")


def test_the_unit_runs_as_its_own_user_and_drops_capabilities() -> None:
    unit = UNIT_PATH.read_text(encoding="utf-8")

    assert "User=cloudflared" in unit
    assert "CapabilityBoundingSet=" in unit
    assert "NoNewPrivileges=yes" in unit
    assert "ProtectSystem=strict" in unit
    assert "--no-autoupdate" in unit, "an auto-updating connector is an unreviewed binary"


def test_the_unit_does_not_reach_the_api_socket() -> None:
    """The connector talks to Caddy on loopback, never to the API socket directly -- so the
    trust headers Caddy sets cannot be bypassed by pointing the tunnel at uvicorn."""
    directives = "\n".join(
        line
        for line in UNIT_PATH.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("#")
    )

    assert "api.sock" not in directives
    assert "AF_UNIX" not in directives


def test_the_unit_does_not_wait_for_a_readiness_notification_cloudflared_never_sends() -> None:
    """`tunnel run` serves without sd_notify, so Type=notify kills a working tunnel.

    Observed on 2026.8.2 during the first cutover: four registered QUIC connections and
    `/ready` reporting `readyConnections=4`, while systemd held the unit in `activating`,
    timed the start out and restarted it — `NRestarts=49` against a tunnel that was up the
    whole time.
    """
    unit = UNIT_PATH.read_text(encoding="utf-8")
    lines = unit.splitlines()
    types = [line.split("=", 1)[1].strip() for line in lines if line.startswith("Type=")]
    assert types == ["exec"], f"expected a single Type=exec, found {types}"


def test_install_makes_the_connector_directory_traversable_by_its_group() -> None:
    """0640 root:cloudflared is unreadable through a 0700 root:root parent.

    The connector then fails with `open /etc/cloudflared/config.yml: permission denied`,
    naming the file rather than the directory that actually refused it.
    """
    install = (INFRA / "install.sh").read_text(encoding="utf-8")
    assert 'command chown root:cloudflared "$CLOUDFLARED_DIR"' in install
    assert 'command chmod 0750 "$CLOUDFLARED_DIR"' in install
