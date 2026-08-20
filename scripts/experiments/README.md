# Pre-P3 gate experiments

The experiments that turn the pre-P3 gate's undecided constants into measured ones.
Each script carries the decision rule from `work-output/pre-p3-gate.md` §2 in its header and
prints a `VERDICT|` line, so a re-run re-decides the constant mechanically rather than by a
second judgment call. Measured values and their resolutions live in
`work-output/pre-p3-gate-results.md`.

Every script is **read-only**: SELECTs on stdin, no DDL, no DML, no writes to the raw zone.

## Running

```bash
# against the live instance from a workstation
GLASSWELL_SSH=root@192.168.2.111 bash scripts/experiments/run-all.sh

# on the host itself, reading /etc/glasswell/db.env
bash scripts/experiments/run-all.sh

# or against any other instance
GLASSWELL_DSN=postgresql://user:pw@host/db bash scripts/experiments/e1-pad-grouping.sh
```

Transcripts land in `${GW_EXPERIMENT_OUT:-work-output/experiments/<utc-date>}`.

## What each one decides

| Script | Gate item | Constant it sets |
|---|---|---|
| `e1-pad-grouping.sh` | G-3 | `PAD_RADIUS_M`, `PAD_WINDOW_DAYS`, `pad_group_max_share` headroom |
| `e2-peer-availability.sh` | G-4 | `TC_MIN_N`, the vintage window, `control_unavailable_share` |
| `e3-length-buckets.sh` | G-4, Mondrian taxonomy | `lateral_length_bucket` cut points |
| `e6-calendar-guard.sh` | G-8 | `HORIZON_CALENDAR_GUARD_MONTHS`, `intermittent_share` |
| `e8-rolling-origins.sh` | G-4/G-5 power, OQ-1 | which rolling origins ship, and whether cum24 ships at P3 |
| `e9-survey-probe.py` | G-12 | station granularity YES/NO for `landing_tvd_ft` |
| `g13-formation-pools.sh` | G-13 | the `__other__` minimum count, and the size of the tail |

## E-0 is the precondition, and it is not here

`canonical.production_monthly` holds six production months at one report vintage. E-2, E-6 and
E-8 therefore run on a proxy (spud dates, or a producing-month rate scaled to twelve) and
their constants are **provisional** until the ND MPR back-load (E-0) lands. E-0 is an ingest
job, not a measurement: it loops `python -m glasswell.ingest.nd_mpr --month YYYY-MM` over
2015-05 … 2025-09 at a polite cadence. Re-run `run-all.sh` when it finishes.

## Not runnable before P3

`E-4` (analog IQR sharpness floor), `E-5` (`training_support` shape) and `E-7`
(`probe_tolerance_cross_env`) measure objects that P3 creates — the analog index and a
trained bundle in two pinned environments. Their decision rules are fixed in
`work-output/pre-p3-gate.md` §2 *before* anyone sees a number, which is the point of listing
them; the scripts join this directory when the artifacts exist.
