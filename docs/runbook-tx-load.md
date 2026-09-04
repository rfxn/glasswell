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

**`GLASSWELL_RAW_ROOT` must be declared, and it and its `.incoming` must be one device.**
`lineage/fetch.py` writes to `<root>/.incoming` and then `os.replace`s into place; a rename
cannot cross a device. Had the temporary file been on `/tmp` — the 145 GB root disk on this
host — a 3.65 GB fetch would fill the root volume and then fail the rename, having already
spent the download. The precheck refuses rather than discovering it at the end.

There is no longer a fallback for the root itself: an undeclared raw zone refuses with
`RawRootUnset` instead of resolving the relative `data/raw` against whatever directory the
process was started in. Every unit below therefore passes it explicitly, and so must any
hand-run ingest.

```bash
grep GLASSWELL_RAW_ROOT /etc/glasswell/app.env      # expect /data/raw
```

---

## Step 1 — fetch and stage, promoting nothing

**Production write to the raw zone and to staging. Runtime: 1–5 hours, almost all of it the
fetch.**

```bash
sudo systemd-run --unit=t1-tx-pdq-stage --wait \
  --property=User=glasswell --property=Group=glasswell \
  --property=Environment=GLASSWELL_DSN=postgresql:///glasswell?host=/var/run/postgresql \
  --property=Environment=GLASSWELL_RAW_ROOT=/data/raw \
  --property=EnvironmentFile=-/etc/glasswell/code-version.env \
  --property=TimeoutStartSec=600 --property=RuntimeMaxSec=21600 \
  --property=MemoryMax=6G \
  /opt/glasswell/venv/bin/python -m glasswell.ingest.tx_pdq \
    --stage-only --pgdata /var/lib/postgresql

# --wait returns the real exit status to this shell. If the SSH session drops, the unit keeps
# running: re-attach with `journalctl -u t1-tx-pdq-stage -f`.
journalctl -u t1-tx-pdq-stage --no-pager -o cat | tail -n 20
systemctl reset-failed t1-tx-pdq-stage    # only after reading it; this is what unloads the unit
```

**Three properties, and what each of them bounds.**

- `--wait`, not `--collect`. `--collect` unloads the unit the moment it exits, and
  `systemctl show <unit> -p Result -p ExecMainStatus` on an unloaded unit answers
  `Result=success ExecMainStatus=0` — measured on the **failed** unit at 2026-09-04 19:42:51Z,
  with `LoadState=not-found`, and documented as exactly this trap in
  `scheduler/runner.py:35-38`. A step whose success check cannot see a failure is not a check.
  With `--wait` the shell gets the status and a failed unit stays loaded for `systemctl status`.
- `RuntimeMaxSec` is the runtime budget. `TimeoutStartSec` is **not**: on a `Type=simple`
  transient unit the service is "started" as soon as the process is forked, so the start
  timeout has nothing left to bound. Measured on a workstation 2026-09-04 20:40Z —
  `systemd-run --wait -p TimeoutStartSec=1 sleep 4` exited 0 after four seconds, and the same
  command with `-p RuntimeMaxSec=1` was killed after one.
- `GLASSWELL_RAW_ROOT` is now mandatory: `lineage/fetch.py` refuses with `RawRootUnset` rather
  than falling back to a relative `data/raw`. It used to resolve against the unit's working
  directory, which under `systemd-run` is `/` — so this step wrote to `/data/raw` by accident
  rather than by declaration, and the same command run by hand from a home directory would
  have written the raw zone there instead.

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

### If it refuses: `ArchiveFormatError` on a member's header

```
OG_WELL_COMPLETION_DATA_TABLE.dsv: the header carries FOO, which the rule does not list
(cr_tx_pdq_format_2)
```

**This is the rule working, not the load failing.** `cr_tx_pdq_format_2` carries the measured
header of every member read, and a member that gained, lost, renamed or reordered a column is
no longer the member the rule describes: the row mapping is invalid, so nothing failed to parse
and there is nothing to quarantine. Read it as a change at the RRC, not as a bug here.

What to do: open `/conformance/cr_tx_pdq_format_2`, compare its `members` entry for the named
member against the archive's own first line, and restate the rule as `cr_tx_pdq_format_3` with
the new header and a rationale that says what was measured and when. Never widen the check to
get the load through — the refusal is what stops thirteen columns of a sixteen-column row being
staged as if they were the row.

**The fetch is kept.** The manifest is committed the moment the bytes are placed, so a refusal
here leaves a recorded artifact rather than an orphan: the archive stays sealed under
`/data/raw/tx_pdq_dsv/pdq-dsv-zip/`, `lineage.manifests` holds its sha256 and byte count, and
`lineage.fetch_attempts` records the poll that produced it. Nothing was promoted and staging is
empty, because the parse rolled back and the fetch did not.

**What `/status` says afterwards, and why it is not "current".** The poll finalises `new`, and
that is true — the bytes landed. It is *not* the whole answer, so the refusal is recorded as a
`staging.load_failed` audit event against the manifest and the manifest's `staging_load_ref` is
left null, and `/v1/status` reads the source as **stale**:

> The poll succeeded but the artifact it registered was never loaded into staging; a fetch is
> not a parse, and freshness is refused until one reads the artifact through.

Colorado answers the same way for the same class of refusal, by a different route — its
`MalformedArchive` rolls the manifest back, so its latest key poll is `failed` with
`malformedarchive`. Two different facts, one served state. Check it after a refusal, and again
after the re-run:

```bash
curl -s "$GLASSWELL_BASE_URL/v1/status" -H "X-Glasswell-Key: $KEY" \
  | jq '.data.sources[] | select(.source_id=="tx_pdq_dsv") | {state, freshness_reason}'
```

The source returns to `current` when — and only when — a stage reads the archive through and
stamps `staging_load_ref` on its manifest. A re-run that refuses again leaves it stale.

**The re-run.** There is no resume — the portal ignores `Range` — so re-running Step 1 after
the rule is restated spends the whole fetch again, 1–5 hours. What it does **not** do is place
a second 3.65 GB copy: identical bytes resolve to the slot the first fetch already registered
(`lineage/fetch.py` `stage_payload` → `owning_slot`), and the run reports `unchanged`. Check
before re-running that exactly one directory exists for the sha:

```bash
ls -1 /data/raw/tx_pdq_dsv/pdq-dsv-zip/
sudo -u postgres psql -d glasswell -Atc \
  "select manifest_id, sha256, size_bytes, storage_uri from lineage.manifests
    where source_id = 'tx_pdq_dsv' order by fetched_at"
```

**The one artifact this does not cover.** The 2026-09-04 19:39Z fetch predates the commit that
made the manifest durable, so its bytes at
`/data/raw/tx_pdq_dsv/pdq-dsv-zip/2026-09-04T193918Z-add29ef717e4/payload.zip` are 3.65 GB with
no `lineage.manifests` row, and no re-run can adopt them: `owning_slot` reads that table, and
there is no supported path that registers an artifact already on disk. Reconcile it by hand
before the next Step 1 — it is an unindexed copy, not a retained vintage, and the raw zone's
accretion policy is about vintages that have a manifest:

```bash
sudo -u postgres psql -d glasswell -Atc \
  "select count(*) from lineage.manifests
    where sha256 = 'add29ef717e430e0...'"      # must be 0 before removing anything
sudo chmod -R u+w /data/raw/tx_pdq_dsv/pdq-dsv-zip/2026-09-04T193918Z-add29ef717e4
sudo rm -rf     /data/raw/tx_pdq_dsv/pdq-dsv-zip/2026-09-04T193918Z-add29ef717e4
```

Substitute the sha the directory name carries, and run the count first: a directory whose sha
**is** in `lineage.manifests` is a live artifact that derivations resolve to, and removing it
breaks every handle that reaches it.

---

## Step 2 — the plug dates, from bytes already on disk

**Production write. Runtime: 5–15 minutes. No socket is opened to the RRC.**

The allocation needs a right bound. A well the Commission filed a W-3 for in 2015 has a
completion date before every month of its lease's history and no end signal, so without this it
takes an equal share every month to the present while the same card serves
`status_canonical = plugged`.

```bash
sudo systemd-run --unit=t2-tx-plug-dates --wait \
  --property=User=glasswell --property=Group=glasswell \
  --property=Environment=GLASSWELL_DSN=postgresql:///glasswell?host=/var/run/postgresql \
  --property=Environment=GLASSWELL_RAW_ROOT=/data/raw \
  --property=EnvironmentFile=-/etc/glasswell/code-version.env \
  --property=TimeoutStartSec=600 --property=RuntimeMaxSec=3600 \
  --property=MemoryMax=6G \
  /opt/glasswell/venv/bin/python -m glasswell.ingest.tx_wellbore \
    --repromote-plug-dates

journalctl -u t2-tx-plug-dates --no-pager -o cat | tail -n 10
systemctl reset-failed t2-tx-plug-dates
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
sudo systemd-run --unit=t3-tx-promote-1993 --wait \
  --property=User=glasswell --property=Group=glasswell \
  --property=Environment=GLASSWELL_DSN=postgresql:///glasswell?host=/var/run/postgresql \
  --property=Environment=GLASSWELL_RAW_ROOT=/data/raw \
  --property=EnvironmentFile=-/etc/glasswell/code-version.env \
  --property=TimeoutStartSec=600 --property=RuntimeMaxSec=7200 \
  --property=MemoryMax=6G \
  /opt/glasswell/venv/bin/python -m glasswell.ingest.tx_pdq \
    --pgdata /var/lib/postgresql --year 1993 --year 1994

journalctl -u t3-tx-promote-1993 --no-pager -o cat | tail -n 10
systemctl reset-failed t3-tx-promote-1993
```

A transient unit rather than `sudo -u glasswell`, for the same reason Step 1 is one: the
code-version file has to be in the environment or `ingest/base.py:37-44` falls back to
`pkg:<version>` and every derivation this step writes is stamped `pkg:0.80` instead of
`v0.80+<commit>` — a build identity that names a package version rather than the tree that
produced it. Give each year-batch its own unit name; `systemctl reset-failed` after reading it.

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
for mart in tx_allocation allocation_backtest cumulatives; do
  sudo systemd-run --unit="t4-tx-$mart" --wait \
    --property=User=glasswell --property=Group=glasswell \
    --property=Environment=GLASSWELL_DSN=postgresql:///glasswell?host=/var/run/postgresql \
    --property=EnvironmentFile=-/etc/glasswell/code-version.env \
    --property=TimeoutStartSec=600 --property=RuntimeMaxSec=3600 \
    --property=MemoryMax=2G \
    "/opt/glasswell/venv/bin/python" -m "glasswell.marts.$mart" || break
  journalctl -u "t4-tx-$mart" --no-pager -o cat | tail -n 5
  systemctl reset-failed "t4-tx-$mart"
done
```

`|| break` because the three are ordered: the cumulative refresh reads the allocated mart, so
running it after a failed allocation would publish a total over a mart that did not rebuild.
The units carry the code-version file for the same reason Step 3's does — a mart derivation
stamped `pkg:0.80` cannot be traced to the tree that computed it.

**The allocation refuses rather than publishing when conservation fails.** The split is exact by
construction, so a non-zero difference on an allocated lease-month is a defect in the module and
not a residual to report — V-1 gates the deploy at tolerance zero. If it raises, do not re-run
it: read the lease key it names.

The cumulative refresh runs last because Texas writes its well-grain cumulative row from the
allocated mart.

---

## Step 5 — check what it says about itself

```bash
# The one name every tier reads: this file, scripts/smoke.sh and tests/e2e.
export GLASSWELL_BASE_URL=https://glasswell.lab.rpx.sh
curl -s "$GLASSWELL_BASE_URL/v1/validators/allocation?jurisdiction=TX" | jq '.data.blocks[] | {name, outcome}'
curl -s "$GLASSWELL_BASE_URL/v1/wells/<api10>/production?explain=true&explain_depth=4" | jq '.data.allocation'
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
