#!/usr/bin/env bash
# Runs every runnable pre-P3 gate experiment and writes one transcript per experiment.
# The point of the transcripts is mechanical refresh: after the E-0 backfill lands, re-run
# this script and the provisional constants in work-output/pre-p3-gate-results.md are
# re-decided by the same decision rules, not by a second judgment call.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${GW_EXPERIMENT_OUT:-work-output/experiments/$(date -u +%Y%m%d)}"
mkdir -p "$OUT_DIR"

experiments=(
    g13-formation-pools.sh
    e1-pad-grouping.sh
    e2-peer-availability.sh
    e3-length-buckets.sh
    e6-calendar-guard.sh
    e8-rolling-origins.sh
)

status=0
for experiment in "${experiments[@]}"; do
    name="${experiment%.sh}"
    printf '==> %s\n' "$name"
    if ! bash "$SCRIPT_DIR/$experiment" >"$OUT_DIR/$name.txt" 2>&1; then
        printf '    FAILED — see %s\n' "$OUT_DIR/$name.txt"
        status=1
    fi
    grep '^VERDICT|' "$OUT_DIR/$name.txt" || true
done

printf '==> e9-survey-probe\n'
if ! python3 "$SCRIPT_DIR/e9-survey-probe.py" >"$OUT_DIR/e9-survey-probe.txt" 2>&1; then
    printf '    FAILED — see %s\n' "$OUT_DIR/e9-survey-probe.txt"
    status=1
fi
grep '^VERDICT|' "$OUT_DIR/e9-survey-probe.txt" || true

printf 'transcripts in %s\n' "$OUT_DIR"
exit "$status"
