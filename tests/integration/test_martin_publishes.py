"""Gate-O B-3: start the tile server as the role it runs as, and read its catalogue.

The config and the grant were each verified alone and were mutually exclusive together — a
column-level grant does not satisfy the `has_table_privilege` filter inside PostGIS's
`geometry_columns`, so martin found an empty schema and exited, and `Restart=on-failure` would
have turned the documented adoption step into a crash loop with every tile down.

Nothing short of running the binary catches that class, so this runs the binary: the shipped
`infra/martin/config.yaml`, changed only where it must be (the bind address and the DSN's host),
against a migrated database, connecting as `martin`.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import psycopg
import psycopg.sql
import pytest
import yaml

from tests.conftest import REQUIRE_DOCKER_ENV, TEST_LABEL, docker_environment

# Pinned: `latest` resolves to 1.14.0 today and would move under this test silently, leaving
# it verifying a binary the VM does not run (gate-o m-6). `v1.14.0` is not a published tag.
MARTIN_IMAGE = "ghcr.io/maplibre/martin:1.14.0"  # the version VM 111 runs
MARTIN_CONFIG = Path(__file__).resolve().parents[2] / "infra" / "martin" / "config.yaml"
MARTIN_ROLE = "martin"
MARTIN_PASSWORD = "martin-test-only"
READY_TIMEOUT_SECONDS = 45
PUBLISHED = {"nd_laterals", "nd_wells", "nd_spacing_units"}
# Whatever else the catalogue holds, none of it may name a relation outside `marts`.
FORBIDDEN_FRAGMENTS = ("staging", "nd_gis", "well_spatial", "quarantine", "production")


def _docker(environment: dict[str, str], *arguments: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["docker", *arguments],
        env=environment,
        check=check,
        capture_output=True,
        text=True,
        timeout=180,
    )
    return completed.stdout.strip()


def _image_available(environment: dict[str, str]) -> bool:
    if _docker(environment, "images", "-q", MARTIN_IMAGE):
        return True
    pull = subprocess.run(
        ["docker", "pull", MARTIN_IMAGE],
        env=environment,
        check=False,
        capture_output=True,
        timeout=600,
    )
    return pull.returncode == 0


def _catalog(address: str) -> dict:
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://{address}:3000/catalog", timeout=5) as response:
                return json.load(response)
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as error:
            last = error
            time.sleep(0.5)
    raise AssertionError(f"martin never served /catalog: {last}")


def _serve(environment: dict[str, str], directory: Path, name: str) -> str:
    """Run martin on the same bridge network the database is on, and return its address."""
    _docker(
        environment,
        "run", "-d", "--rm", "--name", name,
        "--label", TEST_LABEL,
        "-v", f"{directory}:/cfg:ro",
        MARTIN_IMAGE,
        "--config", "/cfg/config.yaml",
    )
    return _docker(
        environment,
        "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", name
    )


@pytest.fixture
def martin_ready(db: psycopg.Connection, tmp_path: Path) -> dict:
    """The shipped config, pointed at this test's database, served by the real binary."""
    environment = docker_environment()
    if environment is None:
        pytest.skip("docker unavailable")
    if not _image_available(environment):
        # CI sets GLASSWELL_REQUIRE_DOCKER, and this is the one test that would have caught a
        # tile server that cannot start. Skipping it there is worse than failing.
        if os.environ.get(REQUIRE_DOCKER_ENV):
            pytest.fail(f"{REQUIRE_DOCKER_ENV} is set but {MARTIN_IMAGE} is unavailable",
                        pytrace=False)
        pytest.skip(f"{MARTIN_IMAGE} unavailable")

    # The deployed unit authenticates over a socket by peer; a container has to use TCP, so the
    # role needs a password here. Nothing else about the connection changes: it is still the
    # `martin` role, which is what the privileges under test hang on.
    with db.cursor() as cursor:
        # ALTER ROLE takes no parameters; the literal is a test-only password, quoted by libpq.
        cursor.execute(
            psycopg.sql.SQL("alter role {} password {}").format(
                psycopg.sql.Identifier(MARTIN_ROLE), psycopg.sql.Literal(MARTIN_PASSWORD)
            )
        )
    db.commit()

    parameters = db.info.get_parameters()
    dsn = (
        f"postgresql://{MARTIN_ROLE}:{MARTIN_PASSWORD}"
        f"@{parameters['host']}:{parameters.get('port', '5432')}/{db.info.dbname}"
    )
    shipped = yaml.safe_load(MARTIN_CONFIG.read_text())
    return {"config": shipped, "dsn": dsn, "directory": tmp_path, "environment": environment}


def _run(martin_ready: dict, config: dict, name: str) -> dict:
    directory, environment = martin_ready["directory"], martin_ready["environment"]
    (directory / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    try:
        return _catalog(_serve(environment, directory, name))
    finally:
        subprocess.run(
            ["docker", "rm", "-f", "-v", name],
            env=environment,
            check=False,
            capture_output=True,
            timeout=120,
        )


def _adapted(martin_ready: dict, **overrides) -> dict:
    """The shipped file with only the two host-specific keys changed."""
    config = json.loads(json.dumps(martin_ready["config"]))
    config["listen_addresses"] = "0.0.0.0:3000"
    config["postgres"]["connection_string"] = martin_ready["dsn"]
    config["postgres"].update(overrides)
    return config


def test_the_shipped_config_publishes_the_allowlist_and_nothing_else(martin_ready):
    """The adoption step, run rather than described."""
    catalog = _run(martin_ready, _adapted(martin_ready), "gw-martin-allowlist")

    assert set(catalog["tiles"]) == PUBLISHED
    for source in catalog["tiles"].values():
        assert source.get("schema", "marts") == "marts"


def test_no_configuration_change_can_publish_staging(martin_ready):
    """The privilege, not the declaration: auto-publish turned back on finds nothing to add,
    because the role holds select on three views in `marts` and on nothing else."""
    catalog = _run(
        martin_ready,
        _adapted(martin_ready, auto_publish=True),
        "gw-martin-autopublish",
    )

    published = " ".join(catalog["tiles"]).lower()
    for fragment in FORBIDDEN_FRAGMENTS:
        exposed = sorted(catalog["tiles"])
        assert fragment not in published, f"auto-publish exposed {fragment}: {exposed}"


def test_the_config_under_test_differs_from_the_shipped_one_only_where_it_must(martin_ready):
    """Otherwise the two tests above prove something about a file nobody deploys."""
    shipped = martin_ready["config"]
    adapted = _adapted(martin_ready)

    assert adapted["postgres"]["tables"] == shipped["postgres"]["tables"]
    assert adapted["postgres"]["auto_publish"] == shipped["postgres"]["auto_publish"] is False
    differing = {
        key for key in adapted if key != "postgres" and adapted[key] != shipped.get(key)
    } | {
        f"postgres.{key}"
        for key in adapted["postgres"]
        if adapted["postgres"][key] != shipped["postgres"].get(key)
    }
    assert differing == {"listen_addresses", "postgres.connection_string"}
