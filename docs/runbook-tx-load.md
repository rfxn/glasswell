# Runbook — the Texas PDQ load

**What this does.** Fetches the RRC Production Data Query dump once to the raw zone, parses it
from disk in two passes, promotes the lease volumes into canonical at their native grain, and
rebuilds the allocated mart, the conservation ledger and the method study. At the end a Texas
well's card draws a production chart whose every point says whether it is an observation or a
share.

**What it is not.** It is not reversible. `canonical.production_monthly` is append-only, so a
promotion that should not have run is a vintage somebody has to reason about rather than a row
somebody can delete. Read Step 0 before Step 1.

**Runtime.** Estimated 2–6 hours end to end, dominated by the fetch. There is no resume: the
portal ignores `Range` (measured 2026-09-03 — a range request answered `200` with the full
length and no `content-range`), so a fetch interrupted at 90 percent starts again at zero.

**Where the DSN comes from.** Every step below sets `GLASSWELL_DSN` in the unit's environment
or exports it. **No step passes the DSN on a command line**: an argument is visible in `/proc`
to every user on the box and lands in shell history, which is the whole reason
`glasswell/db/dsn.py` makes the flag optional. `db.env` is not used anywhere.

**The window between the deploy and Step 4.** From `make deploy` until Step 4 completes, the
allocation mart is empty: the deploy's own smoke reports the Texas block as skipped, the
cumulative refresh publishes no Texas row, and a Texas well's production surface serves the
pending-allocation disclosure naming the rule that closes it. The deploy exits 0 on that basis;
the Texas block turns from skipped to asserted at Step 5.

**What runs before any of this.** The deploy's own sequence, not this file's: DR-B6 step 5,
one synchronous `systemctl start glasswell-scheduler.service`, whose plan is computed and
recorded and which launches nothing because every seeded row registers `launch_mode: observe`;
and then `infra/verify.sh` green. The load below starts after both. The Texas job rows this
train registers are on that same posture, so nothing here is started by a tick: every step is
run by hand, in this order.

---

## Step 0 — the two prechecks, before anything is spent

Both are asserted by `ingest/tx_pdq.py` itself and both are worth reading first, because the
one that fails after the download is the expensive one.

```bash
df -h /data /var/lib/postgresql
```

**`/data` must hold the archive and the vintage beside it.** The measured `Content-Length` is
3,652,221,981 B and the raw zone accretes on purpose — nothing sweeps an artifact, so a monthly
cadence adds about 43.8 GB a year. The precheck wants twice the archive free and refuses below
it. Under 4E.5 this is correct behaviour, not a leak: history not snapshotted cannot be
reconstructed from any of these four regulators.

**`/var/lib/postgresql` is the runbook's gate: under 40 GB available, stop and escalate.** It
is asserted before the fetch and again before each calendar year's promotion, because canonical
is append-only and a half-promoted vintage is a state somebody has to reason about.

**`GLASSWELL_RAW_ROOT` and its `.incoming` must be one device.** `lineage/fetch.py` writes to
`<root>/.incoming` and then `os.replace`s into place; a rename cannot cross a device. Had the
temporary file been on `/tmp` — the 145 GB root disk on this host — a 3.65 GB fetch would fill
the root volume and then fail the rename, having already spent the download. The precheck
refuses rather than discovering it at the end.

```bash
grep GLASSWELL_RAW_ROOT /etc/glasswell/app.env      # expect /data/raw
```

---

## Step 1 — fetch and stage, promoting nothing

**Production write to the raw zone and to staging. Runtime: 1–5 hours, almost all of it the
fetch.**

```bash
sudo systemd-run --unit=t1-tx-pdq-stage --collect \
  --property=User=glasswell --property=Group=glasswell \
  --property=Environment=GLASSWELL_DSN=postgresql:///glasswell?host=/var/run/postgresql \
  --property=TimeoutStartSec=21600 --property=MemoryMax=6G \
  --property=EnvironmentFile=-/etc/glasswell/code-version.env \
  /opt/glasswell/venv/bin/python -m glasswell.ingest.tx_pdq \
    --stage-only --pgdata /var/lib/postgresql

journalctl -u t1-tx-pdq-stage -f
systemctl show t1-tx-pdq-stage -p Result -p ExecMainStatus   # after it exits
```

`--stage-only` stages every member and promotes no lease row, so the expensive, irreversible
half is a separate decision from the unrepeatable one. What lands: one manifest with the
archive's sha256 and byte count, the member inventory read from the central directory, the
crosswalk and lease dimension in staging, the lease member in staging, and
`canonical.lease_membership` — which is append-only but adds no production.

**Read the output before Step 2.** It prints the member sizes, the in-scope lease count, the
share of API-10s carrying more than one lease record, and the window the dump states for
itself. If the in-scope lease population is materially larger than the envelope allows, narrow
the county scope before promoting: a county-scoped load stays explainable and a truncated
history does not (R-5).

---

## Step 2 — the plug dates, from bytes already on disk

**Production write. Runtime: 5–15 minutes. No socket is opened to the RRC.**

The allocation needs a right bound. A well the Commission filed a W-3 for in 2015 has a
completion date before every month of its lease's history and no end signal, so without this it
takes an equal share every month to the present while the same card serves
`status_canonical = plugged`.

```bash
sudo systemd-run --unit=t2-tx-plug-dates --collect \
  --property=User=glasswell --property=Group=glasswell \
  --property=Environment=GLASSWELL_DSN=postgresql:///glasswell?host=/var/run/postgresql \
  --property=TimeoutStartSec=3600 --property=MemoryMax=6G \
  /opt/glasswell/venv/bin/python -m glasswell.ingest.tx_wellbore \
    --repromote-plug-dates
```

It reads `staging.tx_wellbore_ewa` and never re-fetches the 1.3 M-record export. It appends a
vintage and rewrites none, and a well whose promoted values are unchanged appends nothing. The
report states the appended row count against its two bounds — the whole 359,421-row spine as
the ceiling if the skip were not implemented, and the plugged APIs as the floor — and the count
of wells whose `status_canonical` moved. **Read that second number.** A status that moves under
a track about production is a thing to be told about rather than to discover.

---

## Step 3 — promote the lease volumes, one calendar year at a time

**Production write, irreversible. Runtime: 30–90 minutes.**

```bash
export GLASSWELL_DSN=postgresql:///glasswell?host=/var/run/postgresql
sudo --preserve-env=GLASSWELL_DSN -u glasswell \
  /opt/glasswell/venv/bin/python -m glasswell.ingest.tx_pdq \
    --pgdata /var/lib/postgresql --year 1993 --year 1994
```

The `--year` flag is repeatable and the promotion asserts the PGDATA gate before each year, so
a stop lands on a year boundary with a recorded high-water year rather than in the middle of
one. Omitting `--year` promotes every year the staged member covers, which is the normal
monthly run once the history is in.

Relation growth is calibrated at roughly 0.68 GB per million canonical rows, and
`max_wal_size = 4GB` peaks at about double during a promotion. Rows are
`in_scope_lease_months × streams_filed`; the load reports the actual count and it is that
number, not the estimate, that goes in `STATUS.md`.

---

## Step 4 — the marts

**Production write, rebuilt rather than appended. Runtime: 20–60 minutes.**

```bash
sudo --preserve-env=GLASSWELL_DSN -u glasswell \
  /opt/glasswell/venv/bin/python -m glasswell.marts.tx_allocation
sudo --preserve-env=GLASSWELL_DSN -u glasswell \
  /opt/glasswell/venv/bin/python -m glasswell.marts.allocation_backtest
sudo --preserve-env=GLASSWELL_DSN -u glasswell \
  /opt/glasswell/venv/bin/python -m glasswell.marts.cumulatives
```

**The allocation refuses rather than publishing when conservation fails.** The split is exact by
construction, so a non-zero difference on an allocated lease-month is a defect in the module and
not a residual to report — V-1 gates the deploy at tolerance zero. If it raises, do not re-run
it: read the lease key it names.

The cumulative refresh runs last because Texas writes its well-grain cumulative row from the
allocated mart.

---

## Step 5 — check what it says about itself

```bash
curl -s "$GLASSWELL_URL/v1/validators/allocation?jurisdiction=TX" | jq '.data.blocks[] | {name, outcome}'
curl -s "$GLASSWELL_URL/v1/wells/<api10>/production?explain=true&explain_depth=4" | jq '.data.allocation'
```

Three blocks, always. `conservation` is `measured` and its `share_unallocated` is below the
0.005 `cr_tx_allocation_v0_1` records, or the Status row reads degraded and that is a data
question. `crosswalk` reports and does not gate. `independent_truth` returns
`no_independent_truth` with three reasons, which is the honest answer and not a failure.

`infra/verify.sh` and `scripts/smoke.sh` both exit 0 before this is called done.

---

## After the run

Record in `STATUS.md`, on the day: the canonical row count, the relation growth, the measured
unallocated share, the appended `plug_date` rows, and the count of wells whose status moved.
Every one of those is measured by the run and none of them is estimated here.
