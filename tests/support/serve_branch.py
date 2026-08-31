#!/usr/bin/env python3
"""Stand a branch up locally — ephemeral PostGIS, migrations, contract-tier seeds, uvicorn —
so a browser gate judges the branch's own bundle against the branch's own API.

    GW_ROOT=/root/admin/work/proj/gw-<track> GW_PORT=8130 \
      python tests/support/serve_branch.py

Prints the base URL and the key-file path, never the key. GW_SEED names an optional python
file exec'd with `connection` bound, after the base seeds, for track-specific shapes.
Everything docker creates carries glasswell.test=1 (CADENCE N-10) and is removed on exit.
"""

from __future__ import annotations

import atexit
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

# GW_ROOT first on sys.path so a worktree's own `glasswell` and `tests` packages are the
# ones imported — the copy in the main checkout can serve any branch's source and bundle.
ROOT = Path(os.environ.get("GW_ROOT", Path(__file__).resolve().parents[2])).resolve()
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402

from glasswell.db.migrate import migrate  # noqa: E402
from glasswell.lineage.vintages import open_vintage  # noqa: E402
from glasswell.seed import seed_all  # noqa: E402
from tests.contract.conftest import (  # noqa: E402
    _INSERT_QUARANTINE,
    EARLIER_VINTAGE,
    GIS_SHA256,
    MPR_SHA256,
    PRODUCTION_MONTHS,
    REPORT_VINTAGE,
    _promotion_derivation,
    _seed_production,
    _seed_quarantine,
    _spatial_derivation,
)
from tests.support.seed import (  # noqa: E402
    seed_conformance_rule,
    seed_glossary_term,
    seed_manifest,
    seed_production,
    seed_well,
    seed_well_spatial,
)

IMAGE = "postgis/postgis:16-3.4"
LABEL = "glasswell.test=1"
PORT = int(os.environ.get("GW_PORT", "8130"))
WEB_ROOT = Path(os.environ.get("GW_WEB_ROOT", ROOT / "web" / "dist")).resolve()
KEY_FILE = Path(os.environ.get("GW_KEY_FILE", "/tmp/gw-serve/owner.key"))
EXTRA_SEED = os.environ.get("GW_SEED", "")
SOURCES = ["nd_mpr_xlsx", "nd_gis_wells"]
WELL = "3305310451"
OTHER_WELLS = tuple(f"330530000{index}" for index in range(1, 7))
POOLED_WELL = "3305302532"
# Without a registered control artifact every type-curve route answers 409 and the two new
# rail entries render an error, which is not a surface anyone can judge.
MODEL_ROOT = Path(os.environ.get("GW_MODEL_ROOT", "/tmp/gw-serve/models")).resolve()


def docker(*arguments: str) -> str:
    return subprocess.run(
        ["docker", *arguments], check=True, capture_output=True, text=True, timeout=180
    ).stdout.strip()


def start_database() -> tuple[str, str, str]:
    name = f"glasswell-serve-{uuid.uuid4().hex[:8]}"
    volume = f"{name}-data"
    password = uuid.uuid4().hex
    docker("volume", "create", "--label", LABEL, volume)
    # No published port: this workstation's daemon has no `docker-proxy`, so `-p` fails at
    # `docker run`. conftest.py takes the bridge address for the same reason.
    docker(
        "run", "-d", "--rm", "--name", name, "--label", LABEL,
        "-v", f"{volume}:/var/lib/postgresql/data",
        "-e", "POSTGRES_USER=glasswell",
        "-e", f"POSTGRES_PASSWORD={password}",
        "-e", "POSTGRES_DB=glasswell",
        IMAGE,
    )
    address = docker(
        "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", name
    )
    dsn = f"postgresql://glasswell:{password}@{address}:5432/glasswell"
    for _ in range(120):
        try:
            with psycopg.connect(dsn, connect_timeout=2):
                return name, volume, dsn
        except psycopg.OperationalError:
            time.sleep(1)
    raise SystemExit("postgis never became ready")


def _seed_pinned_control(connection, *, manifest_id: str) -> None:
    from tests.contract.conftest import CONTROL_SUBJECTS
    from tests.support.typecurve_fixture import register_pinned_control, write_control_artifact

    # rmtree on a path from the environment: refuse anything that is not the leaf this
    # harness owns, so a mistyped GW_MODEL_ROOT cannot delete a tree somebody wanted.
    if MODEL_ROOT.exists() and MODEL_ROOT.name != "models":
        raise SystemExit(f"GW_MODEL_ROOT {MODEL_ROOT} must end in /models; refusing to remove it")
    shutil.rmtree(MODEL_ROOT, ignore_errors=True)
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    artifact = write_control_artifact(MODEL_ROOT, subjects=CONTROL_SUBJECTS)
    register_pinned_control(connection, artifact, manifest_id=manifest_id)
    connection.commit()


def seed(dsn: str) -> None:
    with psycopg.connect(dsn) as connection:
        migrate(connection)
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute(
                # `env_test` is what tests/support/seed.py's derive() session records under.
                "insert into lineage.environments (env_id, python_version, threads)"
                " values ('env_test', '3.12.10', 1) on conflict do nothing"
            )
            cursor.executemany(
                "insert into lineage.sources (source_id, name) values (%s, %s)"
                " on conflict do nothing",
                [(source, source.replace("_", " ")) for source in SOURCES],
            )
        connection.commit()

        seed_all(connection)
        mpr = seed_manifest(connection, sha256=MPR_SHA256, source_key="2026_06.xlsx")
        gis = seed_manifest(
            connection, sha256=GIS_SHA256, source_id="nd_gis_wells", source_key="OGD_Wells.zip"
        )
        promotion = _promotion_derivation(connection, mpr)
        spatial = _spatial_derivation(connection, gis)

        _seed_pinned_control(connection, manifest_id=mpr)
        seed_well(connection, api10=WELL, manifest_id=mpr, derivation_id=promotion)
        for index, api10 in enumerate(OTHER_WELLS):
            seed_well(
                connection,
                api10=api10,
                manifest_id=mpr,
                derivation_id=promotion,
                well_name=f"EXPLORER {index + 1}H",
                status_canonical="plugged" if index % 2 else "active",
                operator_name_reported="CONTINENTAL RESOURCES, INC" if index % 2 else "HESS",
            )
        seed_well(connection, api10=POOLED_WELL, manifest_id=mpr, derivation_id=promotion,
                  well_name="BIRDBEAR DUPEROW 1H")
        seed_well_spatial(connection, api10=WELL, manifest_id=gis, derivation_id=spatial)

        _seed_production(connection, mpr, promotion)
        _seed_quarantine(connection, mpr)
        seed_quarantine_density(connection, mpr)
        seed_pools(connection, mpr, promotion)

        for index, source in enumerate(SOURCES):
            open_vintage(
                connection,
                source_id=source,
                vintage_date=REPORT_VINTAGE,
                manifest_ids=[mpr if source == "nd_mpr_xlsx" else gis],
                opened_at=datetime(2026, 8, 1, 5, 2, 11, tzinfo=UTC),
                promotion_derivation_id=promotion,
                rows_examined=120_000 + index,
                rows_appended=119_000 + index,
                months_touched=[month.isoformat() for month in PRODUCTION_MONTHS],
            )
        for term in ("report vintage", "null semantics", "reporting level", "lateral length"):
            seed_glossary_term(connection, term=term)
        for rule in ("cr_nd_stream_vocab_1", "cr_tx_lease_alloc_1"):
            # Migration 049 refuses a rule with no first-publication evidence, and these are
            # fixture ids no migration seeds evidence for.
            connection.execute(
                "insert into lineage.conformance_rule_publications"
                " (rule_id, published_vintage, evidence_tag, evidence_commit)"
                " values (%s, date '2026-01-01', 'serve-branch-fixture', %s)"
                " on conflict (rule_id) do nothing",
                (rule, "0" * 40),
            )
            seed_conformance_rule(connection, rule_id=rule)

        if EXTRA_SEED:
            source_path = Path(EXTRA_SEED)
            # The operator names the file; exec is the extension point, not an injection.
            exec(
                compile(source_path.read_text(), str(source_path), "exec"),
                {"connection": connection},
            )
        connection.commit()


def seed_quarantine_density(connection: psycopg.Connection, manifest: str) -> None:
    """The contract fixture's three rows are a correctness sample, not a grid worth judging.

    DIR-11's reviewer is asked about row density and column proportion, and three rows cannot
    answer either question — nor can they mint a cursor. These are the same shapes, in volume.
    """
    # The vocabulary the check constraint actually allows (migration 027), not four
    # plausible-sounding codes: an invented reason_code is a seed that will not insert.
    reasons = ["unknown_vocab", "impossible_volume", "datum_undetermined", "key_collision"]
    # Cycle lengths 4/3/5 rather than 4/4/4: aligned cycles make every (reason, stage, state)
    # combination a single row, and a three-facet frame then shows a grid one row tall.
    stages = ["conform", "validate", "parse"]
    states = ["open", "open", "open", "released", "accepted_loss"]
    rows = [
        {
            "quarantine_id": f"qr_01explorer{index:04d}",
            "fingerprint": f"fp_explorer_{index:04d}",
            "source_id": SOURCES[index % len(SOURCES)],
            "staging_table": "staging.nd_mpr_oil",
            "stage": stages[index % len(stages)],
            "reason_code": reasons[index % len(reasons)],
            "rule_id": "cr_nd_stream_vocab_1",
            "payload": Jsonb({"row": index, "stream_raw": "GasSold"}),
            "seen_at": datetime(2026, 8, 1, 5, index % 60, 11, tzinfo=UTC),
            "manifest_id": manifest,
            "occurrences": (index * 7) % 340 + 1,
            "state": states[index % len(states)],
        }
        for index in range(1, 91)
    ]
    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(_INSERT_QUARANTINE, row)


def seed_pools(connection: psycopg.Connection, manifest: str, derivation: str) -> None:
    """The contract fixture's well files in one pool; this one files in two, which is the
    only shape that exercises pooled row ids and per-pool pivots."""
    for pool, factor in (("BIRDBEAR", 300), ("DUPEROW", 3585)):
        for ordinal, month in enumerate(PRODUCTION_MONTHS):
            for stream, scale in (("oil", 1), ("gas", 2), ("water", 3)):
                seed_production(
                    connection,
                    api10=POOLED_WELL,
                    production_month=month,
                    report_vintage=REPORT_VINTAGE if ordinal else EARLIER_VINTAGE,
                    volume=Decimal(factor * scale * (ordinal + 1)),
                    manifest_id=manifest,
                    derivation_id=derivation,
                    stream=stream,
                    entity_type="well_completion_pool",
                    entity_key=f"{POOLED_WELL}:{pool}",
                    reporting_level="well_completion_pool",
                    well_completion_pool=pool,
                    null_semantics="no_report"
                    if (ordinal == 2 and stream == "water")
                    else "reported",
                )


def main() -> None:
    if not WEB_ROOT.is_dir():
        raise SystemExit(f"{WEB_ROOT} is not a directory — run `npm --prefix web run build` first")
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32)
    KEY_FILE.write_text(key)
    KEY_FILE.chmod(0o600)

    name, volume, dsn = start_database()
    api: subprocess.Popen[bytes] | None = None

    def teardown(*_: object) -> None:
        if api and api.poll() is None:
            api.terminate()
        subprocess.run(["docker", "rm", "-f", "-v", name], check=False, capture_output=True)
        subprocess.run(["docker", "volume", "rm", volume], check=False, capture_output=True)

    atexit.register(teardown)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    seed(dsn)
    api = subprocess.Popen(
        [
            sys.executable,
            "-m", "uvicorn", "glasswell.api:app",
            "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning",
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT / "src"),
            "GLASSWELL_DSN": dsn,
            "GLASSWELL_OWNER_KEY": key,
            "GLASSWELL_WEB_ROOT": str(WEB_ROOT),
            "GLASSWELL_MODEL_ROOT": str(MODEL_ROOT),
        },
    )
    print(f"ready http://127.0.0.1:{PORT} key-file {KEY_FILE}", flush=True)
    api.wait()


if __name__ == "__main__":
    main()
