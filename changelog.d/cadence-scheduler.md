- [New] The schedule is data: `lineage.{refusal_codes, scheduled_jobs, job_sources,
      job_schedules, job_dependencies, job_runs}`, append-only and on two clocks, with a
      `cr_job_cadence_*` conformance rule and published evidence behind every cadence
- [New] `glasswell-scheduler` on an hourly timer, running as root and dropping per transient
      unit to a CHECK-constrained uid; it resolves the registry, computes what is due from the
      freshness rule `/v1/health` reads, orders by dependency, reconciles on `ActiveState`,
      holds a per-job advisory lock and defers what will not fit the tick budget
- [New] v0.78 ships observing: every seeded row records what it would have run and launches
      nothing, while the guard that survives the flip is the narrower one that no `launch` row
      may name an entry point an installed timer already drives
- [New] `/v1/schedules` and `/v1/schedules/{job_id}`, `as_of`-aware over both clocks, serving
      each job's sources, dependencies, cadence rule, recent runs and refusal vocabulary
- [New] `marts.counts` gets a `main` and a registered daily cadence, so the jurisdiction
      well-count ledger has a writer to turn on; like every row this release seeds it observes,
      so the ledger still advances only when someone runs it
- [Change] `/v1/status` generates its job rows from the registry instead of six literal
           blocks, and carries each job's kind, jurisdiction, cadence, next due, duration,
           last outcome, the reason a failed run recorded, and refusal class with its
           severity
- [Change] The Status page splits scheduled work into data jobs grouped by jurisdiction behind
           a disclosure and platform jobs below them, opening any group that holds a fault
- [Change] `--dsn` is optional on `glasswell.marts.counts` with the `GLASSWELL_DSN` /
           `DATABASE_URL` fallback the API and collector already use
- [Change] `deploy.sh` installs the tree's Caddyfile and reloads caddy when it differs, which
           `install.sh` only ever did under `--with-caddy`
- [Fix] The two EIA boundary sources had no poll policy at all, so freshness served them
      `cadence: null` and `pending` forever; the guard that should have caught it was blind
      twice over, missing two seed registries and unable to see a one-row insert
- [Fix] Three sources carried a null poll interval that made their jobs permanently not due
- [Fix] The jurisdiction repoint guard asserted its literals were present only while the tag
      was still UNRELEASED, so the correct repoint turned it red
