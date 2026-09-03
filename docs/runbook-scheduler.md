# Runbook — the cadence-driven scheduler

The schedule is rows. `lineage.scheduled_jobs` says what exists, `lineage.job_schedules` says
what drives each one and on whose decision, `lineage.job_runs` says what every tick observed,
and `lineage.refusal_codes` says what a refusal means. Adding a scheduled job is an insert;
it has not been a unit-file edit since v0.78.

## What runs, and what does not

`glasswell-scheduler.timer` fires hourly with a five-minute jitter and `Persistent=true`, so a
tick missed while the host was down is taken on the next boot. The service runs as `root` and
drops per job to the uid the registry names — root is not a preference: `systemd-run` without
`--user` calls `StartTransientUnit` on the system manager, polkit gates that at
`auth_admin_keep`, and a `Type=oneshot` service has no session to authenticate in.

**Every row this release seeds is `launch_mode='observe'`.** A tick resolves the registry,
computes what is due, and appends a `would_run` row. It launches nothing. The two pipeline
units, `glasswell-ingest` and `glasswell-c115b`, are still armed and are still what actually
runs those eleven invocations; each observing row names the unit driving it in `legacy_unit`,
and the Status page shows that unit's evidence beside the plan so a row never claims the
scheduler ran something it did not.

Turning a job over is one appended row with `launch_mode='launch'`, and that row belongs to
the launch-flip track alone: no jurisdiction registers it for itself, because a launching row is
an unattended run on the next tick and the deploy re-arms the timer every time.
The guard that survives the flip is narrower than the posture: **no
`launch` row may name an entry point an installed timer already drives.**

## Reading the plan

```
sudo -u postgres psql -d glasswell -c \
  "select job_id, trigger, launch_mode, cadence_note, enabled
     from lineage.job_schedules_as_of(current_date, current_date) order by job_id"
```

Or over the wire, which also serves the sources, the dependency edges, the recent runs and the
rule behind the cadence:

```
curl -s -H "X-Glasswell-Key: $KEY" https://glasswell.rpx.sh/v1/schedules
curl -s -H "X-Glasswell-Key: $KEY" https://glasswell.rpx.sh/v1/schedules/ingest_nd_gis
```

`/v1/schedules` is `as_of`-aware over both clocks: a cadence corrected later is not visible
under an earlier knowledge cut.

## Running one job by hand

```
glasswell-scheduler --run <job_id> [--force] [--wait-for-lock <seconds>]
```

`--run` is the manual path and ignores `launch_mode` entirely. It takes a per-job advisory
lock first; if the lock is held it **refuses and exits non-zero** rather than skipping
quietly, because an exit-0 skip is what lets a release believe it refreshed a mart it did not.
`--force` bypasses the due test and `enabled`. It does not bypass the per-job lock, the
dependency order, the ceilings, or an `external_timer` row: forcing one of those refuses
`externally_timed`, because that unit is still armed and `record_vintage_day` is an unlocked
read-then-write.

`--dry-run` computes the plan and writes nothing. `--timer-owned`, `--read-relations` and
`--double-run-check` are the read-only introspections the deploy gate joins its assertions to.

## Refusal codes

Three severity classes, and which class a code carries is a row rather than a list in the
page — a standing condition an operator already knows about must not redden a deploy.

| Class | Codes | What the page shows |
|---|---|---|
| `informational` | `manual_only`, `disabled`, `externally_timed`, `requires_superuser` | Refused, with the sentence; the platform reads no worse than partial |
| `waiting` | `run_in_flight`, `dependency_never_ran`, `deferred` | Pending; it resolves on its own |
| `fault` | `dependency_failed`, `dependency_cycle`, `upstream_unavailable`, `entry_point_missing`, `scheduler_lost_unit` | Degraded; something needs attention |

`refused`, `failed` and `interrupted` are three different facts. A refusal says the job did not
start and why; a failure says it started and did not finish; an interruption says it started
and its unit vanished before anything could read the outcome.

## Registering a job

Four inserts, in `src/glasswell/seed/schedules.py` and
`src/glasswell/seed/conformance_schedules.py`, plus one publication row in the migration that
carries the new rule ids:

1. `scheduled_jobs` — one row per **entry point**. A track with two commands registers two
   jobs and an edge between them, which is what keeps the ceilings, the timeout, the transient
   unit and the run ledger one-to-one with a process.
2. `job_sources` — every source the job polls. The cadence interval is `min` over these, so a
   shorter policy on any one of them shortens the job.
3. `job_schedules` — the decision, referencing a `cr_job_cadence_<job_id>_1` rule. Only an
   `external_timer` row may leave `rule_id` null, because its cadence lives in that unit's
   `OnCalendar=`.
4. `job_dependencies` — what it waits on, and why.

The parity gates refuse the rest: a registered source with no job, a jurisdiction mart with no
ingest edge of its own jurisdiction, a cadence the due rule can produce no instant for, a rule
with no publication evidence, and a served row that disagrees with the seed tuple.

## The control connection

`/etc/glasswell/scheduler.env` holds one line, `root:root 0600`, and no secret: a password-free
socket DSN naming the `glasswell_scheduler` role. That role is created by migration, granted
only the relations the tick reads and the ledger it writes, and holds no `glasswell_pipeline`
membership — it cannot write `canonical`, `staging` or `marts` even by mistake. OS root reaches
it through the `pg_ident` map at `infra/postgres/pg_ident.d/glasswell.conf`, which `install.sh`
places, points `pg_hba.conf` at, and **reloads PostgreSQL for**; without the reload the map is
written and not in force, and the first tick fails peer authentication an hour after a deploy
that exited 0.

The map carries a regex self-map beside the new line. Naming a map removes PostgreSQL's
implicit self-mapping, so without it `glasswell`, `postgres` and `martin` would all stop
authenticating. `verify.sh` proves all four identities still connect.

## When something is wrong

- **The gate says a launch row names a timer-owned entry point.** Two drivers for one job.
  Either retire the unit in the same release, or append an `observe` row.
- **A job is never due.** Its sources carry no `expected_poll_interval`, so the due rule can
  compute no instant. Give the source an interval or make the job `manual` with the reason in
  `cadence_note`; the contract gate refuses the middle ground.
- **A run row is open with no unit.** The next tick closes it `interrupted` /
  `scheduler_lost_unit`. That is evidence, not an error to clear by hand.
- **A tick exits 0 having done nothing.** A previous tick still holds the session lock. The
  follower is silent on purpose: the running job's open row is the evidence.
