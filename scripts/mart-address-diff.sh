#!/usr/bin/env bash
# Prove that parameterising the four tile marts moved no derivation id.
#
# `lineage/ids.py` hashes the operation, the input refs, hash_payload(params), the code version,
# the env id, ruleset_hash(rule_ids), the output dataset and its partition. Two of those -- the
# params key set and the rule list -- differ four ways between the resident jurisdictions, so a
# refactor that unified either would move every address. This runs the four mains twice against
# ONE database, once from a checkout of the base and once from this tree, with the build
# identity pinned on both sides so the diff cannot be an artifact of the version string.
#
# Running both against one database buys a second proof for free: lineage/store.py's reconcile()
# raises DeterminismViolation when a content-addressed id repeats with a different output hash,
# so a refactor that preserved the address and changed what it wrote fails there, naming both
# hashes, before this script compares anything.
#
#   scripts/mart-address-diff.sh [--baseline-ref v0.76] [--out <path>]
#
# Needs docker. Everything it creates carries glasswell.test=1 and is removed on exit.
set -euo pipefail

BRANCH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASELINE_REF="${GW_BASELINE_REF:-v0.76}"
OUT="${GW_BASELINE_OUT:-/root/admin/work/proj/glasswell/work-output/seam-mart-baseline.json}"
IMAGE="postgis/postgis:16-3.4"
LABEL="glasswell.test=1"
PY="${GW_PYTHON:-$BRANCH_ROOT/.venv/bin/python}"
JURISDICTIONS=(ND TX NM MT)

while [ $# -gt 0 ]; do
    case "$1" in
        --baseline-ref) BASELINE_REF="$2"; shift 2 ;;
        --out) OUT="$2"; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

WORK="$(mktemp -d)"
CONTAINER="glasswell-address-$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
VOLUME="$CONTAINER-data"

# shellcheck disable=SC2317  # invoked by the EXIT trap, which shellcheck cannot see
cleanup() {
    docker rm -f -v "$CONTAINER" >/dev/null 2>&1 || true   # best effort: the run may have failed before `docker run`
    docker volume rm "$VOLUME" >/dev/null 2>&1 || true     # same, and the volume outlives a killed container
    command rm -rf "$WORK"
}
trap cleanup EXIT

echo "baseline ref  : $BASELINE_REF"
echo "branch root   : $BRANCH_ROOT"
echo "baseline out  : $OUT"

# A `git archive` extraction rather than a worktree: this must not touch git state in any
# checkout, and the baseline is only ever read.
BASELINE_ROOT="$WORK/baseline"
mkdir -p "$BASELINE_ROOT"
git -C "$BRANCH_ROOT" archive "$BASELINE_REF" | tar -x -C "$BASELINE_ROOT"

PASSWORD="$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
docker volume create --label "$LABEL" "$VOLUME" >/dev/null
docker run -d --rm --name "$CONTAINER" --label "$LABEL" \
    -v "$VOLUME:/var/lib/postgresql/data" \
    -e POSTGRES_USER=glasswell -e "POSTGRES_PASSWORD=$PASSWORD" -e POSTGRES_DB=glasswell \
    "$IMAGE" >/dev/null
ADDRESS="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$CONTAINER")"
DSN="postgresql://glasswell:$PASSWORD@$ADDRESS:5432/glasswell"

# A real connection, not pg_isready: initdb answers the local socket well before the server
# is listening on TCP, and the first client of a "ready" container then fails on refused.
"$PY" - "$DSN" <<'READY'
import sys
import time

import psycopg

for _ in range(120):
    try:
        with psycopg.connect(sys.argv[1], connect_timeout=2):
            raise SystemExit(0)
    except psycopg.OperationalError:
        time.sleep(1)
raise SystemExit("postgis never became ready")
READY

# Migrated and seeded from THIS tree, so the registry carries the decisions the engine reads.
# The baseline code takes its basin and its length source from its own module constants and is
# unaffected by the extra rows, which is exactly the equivalence under test.
PYTHONPATH="$BRANCH_ROOT/src:$BRANCH_ROOT" "$PY" - "$DSN" <<'PLANT'
import sys
from datetime import date

import psycopg

from glasswell.db.migrate import migrate
from glasswell.seed import seed_all
from tests.support.seed import seed_derivation, seed_well, seed_well_spatial

SURFACE = "POINT(-103.2 47.8)"
LATERAL = "LINESTRING(-103.2 47.8, -103.18 47.79)"
TRACE = "LINESTRING(-103.2 47.8, -103.19 47.795, -103.18 47.79)"
# One well per registered prefix, with the geometry classes each mart projects. Fixed strings
# and fixed dates: the digest each side computes must be a function of the data alone.
POPULATION = (
    ("ND", "33", "3305300001", ("surface", "lateral", "survey_trace")),
    ("TX", "42", "4230100001", ("surface", "lateral")),
    ("NM", "30", "3001500001", ("surface",)),
    ("MT", "25", "2508300001", ("surface", "lateral")),
)

dsn = sys.argv[1]
with psycopg.connect(dsn) as connection:
    migrate(connection)
    connection.commit()
    seed_all(connection)
    with connection.cursor() as cursor:
        # derive()'s env_id is a NOT NULL foreign key, and the fixture helpers below record
        # under the harness's own environment rather than a fingerprinted one.
        cursor.execute(
            "insert into lineage.environments (env_id, python_version, threads)"
            " values ('env_test', '3.12.10', 1) on conflict (env_id) do nothing"
        )
        cursor.executemany(
            "insert into lineage.sources (source_id, name, jurisdiction)"
            " values (%s, %s, %s) on conflict (source_id) do nothing",
            [("nd_mpr_xlsx", "nd mpr xlsx", "ND")],
        )
    connection.commit()
    derivation = seed_derivation(connection)
    for _code, prefix, api10, kinds in POPULATION:
        seed_well(
            connection,
            api10=api10,
            derivation_id=derivation,
            state_code=prefix,
            status_reported="A",
            completion_date=date(2020, 3, 4),
            basin="williston" if prefix == "33" else None,
        )
        for kind in kinds:
            key = {
                "surface": "surface",
                "lateral": f"{api10}0000_LAT1",
                "survey_trace": f"{api10}0000_1",
            }[kind]
            seed_well_spatial(
                connection,
                api10=api10,
                geom_type=kind,
                geom_key=key,
                wkt={"surface": SURFACE, "lateral": LATERAL, "survey_trace": TRACE}[kind],
                derivation_id=derivation,
            )
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into canonical.well_survey_stations (api10, api14, wellbore_segment,"
            " segment_kind, station_ordinal, measured_depth_ft, true_vertical_depth_ft,"
            " inclination_deg, azimuth_deg, geom, source_datum, source_manifest_id,"
            " derivation_id)"
            " select %(api10)s, %(api14)s, '1', 'lateral', n, 100.0 * n, 90.0 * n, 5.0, 275.0,"
            "        st_setsrid(st_makepoint(-103.2, 47.8), 4326), 'EPSG:4269',"
            "        (select source_manifest_id from canonical.well_spatial"
            "          where api10 = %(api10)s limit 1), %(derivation)s"
            "   from generate_series(1, 3) as n",
            {"api10": "3305300001", "api14": "33053000010000", "derivation": derivation},
        )
    connection.commit()
print("fixture planted")
PLANT

capture() {
    local root="$1" label="$2" out="$3"
    : > "$out"
    for code in "${JURISDICTIONS[@]}"; do
        local module
        case "$code" in
            ND) module="glasswell.marts.nd_wells" ;;
            TX) module="glasswell.marts.tx_wells" ;;
            NM) module="glasswell.marts.nm_wells" ;;
            MT) module="glasswell.marts.mt_wells" ;;
        esac
        echo "  $label $code via $module"
        PYTHONPATH="$root/src" "$PY" -m "$module" --dsn "$DSN" \
            --code-version gw-mart-address-probe --env-id env_probe > "$WORK/$label-$code.json"
    done
    # The branch's own tree for the read-back: the profiles name the projections, and the
    # baseline checkout has no such declaration to ask.
    PYTHONPATH="$BRANCH_ROOT/src" "$PY" - "$DSN" "$WORK" "$label" "$out" <<'READBACK'
import json
import sys

import psycopg

from glasswell.marts.wells import MART_PROFILES

dsn, work, label, out = sys.argv[1:5]
# Every projection each profile publishes, not just the wells one. Reading back a single table
# left ND's laterals and survey traces, TX's laterals and MT's paths visible only as a row
# count, and a row count cannot see a reordered or renamed column -- which is difference #13,
# the one `md5(p::text)` makes load-bearing. `set_output_hash` does span them, but it is only
# consulted when an id repeats, so a run where the address moved for an unrelated reason would
# have left the secondary projections unchecked in the very run that needed it most.
tables = {
    profile.jurisdiction_code: [p.table for p in profile.projections]
    for profile in MART_PROFILES
}
capture = {}
with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
    for code, projections in tables.items():
        report = json.loads(open(f"{work}/{label}-{code}.json", encoding="utf-8").read())
        # The digest is NOT in the address (capture.py) and is not in to_dict() either, so a
        # refactor that preserved the id and reordered a published column would pass a
        # to_dict() diff. It is read back from the marts themselves.
        digests = {}
        for table in projections:
            cursor.execute(
                f"select md5(string_agg(t::text, '' order by api10)) from marts.{table} t"
            )
            digests[table] = cursor.fetchone()[0]
        capture[code] = {**report, "tile_digests": digests}
print(json.dumps(capture, indent=2, sort_keys=True), file=open(out, "w", encoding="utf-8"))
READBACK
}

echo "running the baseline mains"
capture "$BASELINE_ROOT" baseline "$WORK/baseline.json"
echo "running the branch mains"
capture "$BRANCH_ROOT" branch "$WORK/branch.json"

mkdir -p "$(dirname "$OUT")"
cp "$WORK/baseline.json" "$OUT"

status=0
for code in "${JURISDICTIONS[@]}"; do
    if diff -u \
        <("$PY" -c "import json,sys;print(json.dumps(json.load(open(sys.argv[1]))[sys.argv[2]],indent=2,sort_keys=True))" "$WORK/baseline.json" "$code") \
        <("$PY" -c "import json,sys;print(json.dumps(json.load(open(sys.argv[1]))[sys.argv[2]],indent=2,sort_keys=True))" "$WORK/branch.json" "$code") \
        > "$WORK/$code.diff"
    then
        echo "$code: empty diff"
    else
        echo "$code: DIFFERS"
        cat "$WORK/$code.diff"
        status=1
    fi
done

echo "baseline written to $OUT"
exit "$status"
