#!/usr/bin/env python3
"""DR-79 — prove migration 031 turns the `_latest` view's one-well read into an index scan.

`canonical.production_monthly_latest` re-ranked the whole table for a single api10 because
api10 was not in its PARTITION BY (d1-p5-status.md §7: 73 s warm / 156 s cold at 17.6M rows).
`glasswell_d1` no longer exists, so this builds the synthetic-volume proof the register asks
for: an ephemeral PostGIS container, the full migration chain, millions of synthetic rows,
then the same one-well EXPLAIN under 024's view text and under 031's — the AFTER definition
is executed from the migration file itself, not a copy. Output parity (count + row checksum
over the whole view) is asserted across the swap, because the fix must change the plan and
nothing else.

Prints a `VERDICT|` line; everything is created inside the container and removed on exit
(label glasswell.test=1, so `make prune-test-volumes` is the backstop).

    .venv/bin/python scripts/experiments/dr79-latest-view-proof.py [--wells 100000] [--keep]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))
from glasswell.db.migrate import MIGRATIONS_DIR, migrate

IMAGE = "postgis/postgis:16-3.4"
LABEL = "glasswell.test=1"
PROBE_API10 = "3300050000"
STREAMS = ("oil", "gas", "water")

# Migration 024's definition, verbatim — the BEFORE state (api10 absent from PARTITION BY).
VIEW_BEFORE = """
create or replace view canonical.production_monthly_latest as
select api10, production_month, stream, source_id, report_vintage, volume, unit, days_produced,
       granularity, value_hash, source_manifest_id, derivation_id, created_at, null_semantics,
       entity_type, entity_key, reporting_level, well_completion_pool, aggregation
  from (select p.*,
               row_number() over (
                   partition by entity_type, entity_key, production_month, stream, source_id
                   order by report_vintage desc) as vintage_rank
          from canonical.production_monthly p) ranked
 where vintage_rank = 1;
"""

PROBE = (
    "select * from canonical.production_monthly_latest where api10 = %(api10)s"
)

PARITY = """
select count(*),
       coalesce(sum(hashtext(concat_ws('|', api10, entity_type, entity_key, production_month,
                                       stream, source_id, report_vintage, volume))), 0)
  from canonical.production_monthly_latest
"""

SEED_PARENTS = """
insert into lineage.sources (source_id, name) values ('dr79_synth', 'DR-79 synthetic volume');
insert into lineage.environments (env_id) values ('env_dr79');
insert into lineage.manifests (manifest_id, sha256, bytes, source_id, source_key,
                               acquisition_url, acquisition_method, fetched_at, fetch_vintage)
values ('man_dr79', repeat('0', 64), 0, 'dr79_synth', 'synthetic',
        'https://invalid.example/dr79', 'https_get', now(), date '2026-08-01');
insert into lineage.derivations (derivation_id, operation, output_store, output_dataset,
                                 params_hash, code_version, env_id, created_at, correlation_id,
                                 status, determinism_class, ttl_class)
values ('der_dr79', 'canonical.promote', 'postgres', 'canonical.production_monthly',
        repeat('0', 64), 'dr79', 'env_dr79', now(), 'run_dr79', 'ok', 'D1', 'ephemeral');
"""

BULK_INSERT = """
insert into canonical.production_monthly
    (api10, production_month, stream, source_id, report_vintage, volume, unit, days_produced,
     granularity, value_hash, source_manifest_id, derivation_id,
     entity_type, entity_key, reporting_level)
select api10, month, stream, 'dr79_synth', date '2026-08-01', (w %% 5000)::numeric, 'bbl', 30,
       'well_observed', 'vh_' || w, 'man_dr79', 'der_dr79', 'well', api10, 'well'
  from (select w, '33' || lpad(w::text, 8, '0') as api10 from generate_series(1, %(wells)s) w) s,
       generate_series(date '2024-01-01', date '2024-01-01' + (%(months)s - 1) * interval '1 month',
                       interval '1 month') month,
       unnest(array['oil', 'gas', 'water']) stream
"""

# A restatement slice, so the window has real >1-row partitions to collapse.
SECOND_VINTAGE = """
insert into canonical.production_monthly
    (api10, production_month, stream, source_id, report_vintage, volume, unit, days_produced,
     granularity, value_hash, source_manifest_id, derivation_id,
     entity_type, entity_key, reporting_level)
select api10, date '2024-01-01', stream, 'dr79_synth', date '2026-08-15',
       (w %% 5000)::numeric + 1, 'bbl', 30, 'well_observed', 'vh2_' || w, 'man_dr79', 'der_dr79',
       'well', api10, 'well'
  from (select w, '33' || lpad(w::text, 8, '0') as api10
          from generate_series(1, %(wells)s, 10) w) s,
       unnest(array['oil', 'gas', 'water']) stream
"""


def run(*argv: str) -> str:
    return subprocess.run(argv, check=True, capture_output=True, text=True).stdout.strip()


def wait_ready(dsn: str, deadline_s: int = 120) -> None:
    deadline = time.monotonic() + deadline_s
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3):
                return
        except psycopg.Error:
            time.sleep(0.5)
    raise SystemExit("container never accepted connections")


def timed_probe(connection: psycopg.Connection, label: str) -> tuple[float, str]:
    with connection.cursor() as cursor:
        started = time.monotonic()
        cursor.execute("explain (analyze, buffers) " + PROBE, {"api10": PROBE_API10})
        elapsed = (time.monotonic() - started) * 1000
        plan = "\n".join(row[0] for row in cursor.fetchall())
    print(f"\n---- {label}: {elapsed:.1f} ms wall ----\n{plan}")
    return elapsed, plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wells", type=int, default=100_000)
    parser.add_argument("--months", type=int, default=20)
    parser.add_argument("--keep", action="store_true", help="leave the container running")
    arguments = parser.parse_args()

    name = f"gw-dr79-{uuid.uuid4().hex[:8]}"
    password = uuid.uuid4().hex
    # Bridge IP, not a published port: the local daemon path, same as tests/conftest.py.
    run("docker", "run", "-d", "--rm", "--name", name, "--label", LABEL,
        "-e", "POSTGRES_USER=glasswell",
        "-e", f"POSTGRES_PASSWORD={password}", "-e", "POSTGRES_DB=postgres", IMAGE)
    try:
        bridge = run("docker", "inspect", "-f",
                     "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", name)
        dsn = f"postgresql://glasswell:{password}@{bridge}:5432/postgres"
        wait_ready(dsn)
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute("create database dr79")
        dsn = dsn.rsplit("/", 1)[0] + "/dr79"

        with psycopg.connect(dsn) as connection:
            applied = migrate(connection)
            connection.commit()
            head = max(m.version for m in applied)
            print(f"migrated to head {head:03d} ({len(applied)} migrations)")
            with connection.cursor() as cursor:
                cursor.execute(SEED_PARENTS)
                started = time.monotonic()
                cursor.execute(BULK_INSERT, {"wells": arguments.wells,
                                             "months": arguments.months})
                cursor.execute(SECOND_VINTAGE, {"wells": arguments.wells})
                connection.commit()
                cursor.execute("analyze canonical.production_monthly")
                cursor.execute("select count(*) from canonical.production_monthly")
                total = cursor.fetchone()[0]
            print(f"seeded {total:,} rows in {time.monotonic() - started:.0f}s")

            with connection.cursor() as cursor:
                cursor.execute(VIEW_BEFORE)
                connection.commit()
            before_cold, before_plan = timed_probe(connection, "BEFORE (024 view), cold")
            before_warm, _ = timed_probe(connection, "BEFORE (024 view), warm")
            with connection.cursor() as cursor:
                cursor.execute(PARITY)
                parity_before = cursor.fetchone()

            migration_031 = next(MIGRATIONS_DIR.glob("031_*.sql"))
            with connection.cursor() as cursor:
                cursor.execute(migration_031.read_text())
                connection.commit()
            after_cold, after_plan = timed_probe(connection, f"AFTER ({migration_031.name}), cold")
            after_warm, _ = timed_probe(connection, f"AFTER ({migration_031.name}), warm")
            with connection.cursor() as cursor:
                cursor.execute(PARITY)
                parity_after = cursor.fetchone()

        pruned = bool(re.search(r"Index Cond:.*api10", after_plan))
        removed = re.search(r"Rows Removed by Filter: (\d+)", before_plan)
        parity = "identical" if parity_before == parity_after else "DIVERGED"
        print(f"\nparity before={parity_before} after={parity_after}")
        print(f"VERDICT|dr79|rows={total}|before_cold_ms={before_cold:.0f}"
              f"|before_warm_ms={before_warm:.0f}|after_cold_ms={after_cold:.0f}"
              f"|after_warm_ms={after_warm:.0f}"
              f"|before_rows_removed={removed.group(1) if removed else '0'}"
              f"|api10_pruned={'yes' if pruned else 'NO'}|parity={parity}")
        return 0 if pruned and parity == "identical" else 1
    finally:
        if arguments.keep:
            print(f"container kept: {name}")
        else:
            subprocess.run(["docker", "rm", "-f", "-v", name], check=False,
                           capture_output=True)


if __name__ == "__main__":
    raise SystemExit(main())
