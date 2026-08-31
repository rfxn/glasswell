# Runbook — promoting the New Mexico OCD spine

Four production steps against VM 111, in order, each with the numbers it must produce. Follow
this file; it does not assume you have read the plan behind it.

Every figure marked **measured** was read from the host or from the sealed bytes on
2026-08-29/30. If a step's actual differs from its expected, **stop and reconcile before
continuing** — the expectations come from a full run against a scratch database over the same
bytes, so a divergence means the inputs are not the inputs.

**Two databases, one letter apart.** `glasswell` is production. `glasswell_d1` is the
disposable scratch database on the same host. Every command below states its `--dsn` or `-d`
explicitly. If any command in the session omitted one, stop and re-verify what it touched.

---

## What this does not do

**Tier 1 does not open the gate.** After all four steps succeed, `GET /v1/wells/30…` still
returns **404** and no New Mexico figure is servable.

`src/glasswell/api/routers/wells.py` roots the well spine on `canonical.wells`, and
`api/routers/production.py` raises `not_found` for any API-10 that spine does not resolve.
Nothing in these four steps writes a `canonical.wells` row. Building that half — the header
promotion, the surface geometry, the marts, the tiles and the served rule handles — is Tier 2
of the same track.

Row count is not the acceptance criterion. `ROADMAP.md` N3 exit: *the gate opens on the spine,
not on the row count.* Step 5's G7-1 asserts that `canonical.wells` by state is **unchanged**
by this runbook, precisely to prove it.

Nor is any of this a re-acquisition. The OCD FTP is never pulled again; every byte these steps
read was sealed on 2026-08-20 and lives in `/data/raw/nm_ocd_*` with its `manifest.json`
sidecar and `MANIFEST.sha256`.

---

## Preconditions

1. **Owner authorisation, once, covering Steps 1 through 3.** Step 1 is the first production
   write in the sequence. A plan approval is not an owner cue.
2. **Run under `systemd-run`, never in an SSH session.** Step 3 is ~89 minutes; a dropped
   session mid-`insert … select` leaves a partial month.
3. **The repository's Phase 2 status-collector fix is in the deployed bytes** — see abort
   condition A. This is not optional and it is not reorderable.
4. **A verified-fresh dump exists** — see abort condition B. It is a precondition, not an
   undo; see *Rollback*.
5. **`scripts/ops/nm_reregister_manifests.py` is deployed** under `/opt/glasswell/src/`. Before
   this was vendored, the tool existed only at `/data/scratch/d1-p4/reregister.py`, untracked,
   inside a disposable tree.

---

## Abort conditions

Checked before Step 3. **Any one of them stops the run.**

### A — the status surface reports New Mexico as New Mexico

Until the Phase 2 fix is deployed, `status/collector.py` aggregates
`canonical.production_monthly` with no state filter and serves the result under a hardcoded
`"North Dakota"` jurisdiction. `glasswell-status.timer` is `OnCalendar=*:0/15` with
`Persistent=true`, so **within fifteen minutes of Step 3** the surface would publish
~24.8M rows and ~93,958 distinct wells under the wrong state, unattended, over rows that have
no well header at all. The status surface is append-only; a wrong figure there is fixed
forward, never withdrawn.

```bash
ssh root@192.168.2.111 \
  "grep -c 'canonical.production_monthly/nm' \
     /opt/glasswell/src/src/glasswell/status/collector.py"
# 1 or more = the split is in the deployed source, proceed.  0 = STOP.

curl -sf -H "X-Glasswell-Key: $owner_key" "$API/v1/status" \
  | python3 -c 'import json,sys
ids={d["dataset_id"] for d in json.load(sys.stdin)["data"]["datasets"]}
print(sorted(i for i in ids if "production_monthly" in i))'
# must print both /nd and /nm ids. A bare "canonical.production_monthly" means the running
# process predates the fix even if the file on disk carries it. STOP.
```

**Check for the fix's presence, not for the defect's absence.** The split query still ends
`" from canonical.production_monthly"`, so a grep for that fragment matches both the fixed and
the unfixed file and would refuse a correctly deployed host. The two checks above are positive:
the first proves the bytes, the second proves the process.

### B — a verified-fresh dump exists

```bash
systemctl show glasswell-backup.service -p Result -p ExecMainStatus
#   must read  Result=success  ExecMainStatus=0
ls -la --time-style=full-iso /data/backups/pg/glasswell-*.dump | tail -3
#   newest dump < 24h old AND within 10% of the previous dump's size, or STOP
```

`glasswell-backup.timer` is `*-*-* 02:00:00`, daily.

**What this condition does not give you: proof that a restore of the post-promotion schema
works.** `verify.sh` compares the live schema head to the restore-drill receipt, gated on a
drill completing after `max(applied_at)`. This track's migrations move the live head, and the
drill is weekly on Sundays at about 04:00 UTC — so between the deploy and the next drill the
receipt covers a schema that predates it. The gate is built to hold rather than fail in that
window, which is correct, but it means the newest restore proof is a proof about the *old*
schema. Do not read a green `verify.sh` in that window as restore coverage of these
migrations; wait for the drill that follows them.

### C — no competing writer

```bash
pgrep -a pg_restore || echo "no restore drill running"
systemctl is-active glasswell-ingest.service      # must be inactive
# The one-shot re-promotion units must be ABSENT, not merely inert. Zero, or STOP.
systemctl list-unit-files 'glasswell-repromote*' --no-pager
ls /etc/systemd/system/glasswell-repromote.* 2>&1        # expect: No such file or directory
ls /etc/systemd/system/ | grep -c '^glasswell-'          # expect 14, matching the tree
```

- `glasswell-restore-drill.timer` is `Sun *-*-* 04:00:00` with `RandomizedDelaySec=600`:
  **weekly, Sundays**. The window to avoid is **Sunday 03:45–05:00 UTC** and no other night.
- `glasswell-ingest.timer` is `*-*-05 04:30:00 UTC` with `RandomizedDelaySec=1800`: **monthly,
  day 5**. If the run falls on the 5th, wait for it or start before 04:00.
- **`glasswell-repromote.timer` and its service must not exist. Assert absence; do not mask,
  and do not re-create them.** They were a Wave-1 one-shot — `Description=One-shot S-E
  re-promotion (Wave-1 track A1b)`, a single `OnCalendar=2026-08-21 00:30:00 UTC`, a hardcoded
  log path, `Result=success` from its one run — installed on the host and never committed to
  `infra/systemd/`. They were removed on 2026-08-30; the host now carries exactly 14
  `glasswell-*` unit files, matching the tree, and `verify.sh` asserts host against tree in that
  direction. `systemctl mask` on a unit that does not exist is not the check you want.

  **The earlier framing of this as an armed timer was wrong, and the correction is measured
  rather than argued.** `Persistent=true` catch-up targets a calendar occurrence *after* the
  base time, and a single past instant has none: `systemd-analyze calendar '2026-08-21 00:30:00
  UTC'` returns `Next elapse: never`, and `NextElapseUSecRealtime` was empty on the host for
  that reason and not because a stamp file was suppressing it. The finding that survives is the
  one that mattered — a unit existed on the host that existed nowhere in the tree — and absence
  is what this condition now checks.

### D — the ordinary stops

- `df -h /var/lib/postgresql` shows < 40 GB available → stop, escalate.
- Any step exits **2** with a `refused: …` line → stop. That is the guard working. Do not
  delete rows, do not re-run the same day, do not pipe the step through `jq` — the refusal line
  is deliberately not JSON. Re-run on a later day.
- Any command that omitted an explicit `-d` / `--dsn` → stop and re-verify.

---

## Step 0 — baseline

Read-only. Save to `/data/scratch/t3-nm/baseline/` on the host and paste the results back into
this file's *Measured run* section when the run happens.

```bash
ssh root@192.168.2.111
sudo -u glasswell mkdir -p /data/scratch/t3-nm/baseline
cd /data/scratch/t3-nm/baseline || exit 1

sudo -u postgres psql -d glasswell -tAc \
  "select source_id, count(*) from canonical.production_monthly group by 1 order by 1" \
  > prod-by-source.before.txt
sudo -u postgres psql -d glasswell -tAc \
  "select source_id, count(*) from canonical.well_completions group by 1 order by 1" \
  > completions-by-source.before.txt
sudo -u postgres psql -d glasswell -tAc \
  "select state_code, count(*) from canonical.wells group by 1 order by 1" \
  > wells-by-state.before.txt
sudo -u postgres psql -d glasswell -tAc \
  "select count(*) from lineage.manifests m join lineage.sources s using (source_id)
    where s.jurisdiction='NM'" > nm-manifests.before.txt
sudo -u postgres psql -d glasswell -c \
  "explain (analyze, buffers) select * from canonical.production_monthly
    where api10 = '3305301633'" > explain-served-nd.before.txt
sudo -u postgres psql -d glasswell -c \
  "explain (analyze, buffers) select count(*) from canonical.production_monthly_latest
    where entity_type='well' and api10 is not null" > explain-latest-view.before.txt
df -h /var/lib/postgresql > disk.before.txt
free -m > mem.before.txt
sudo -u postgres psql -d glasswell -tAc \
  "select pg_size_pretty(pg_database_size('glasswell'))" > dbsize.before.txt
```

Expected, **measured 2026-08-29**. Any difference stops the run:

| file | expected |
|---|---|
| `prod-by-source.before.txt` | `nd_mpr_xlsx\|7223544`, one line |
| `completions-by-source.before.txt` | `nd_mpr_xlsx\|2395283`, one line |
| `wells-by-state.before.txt` | `33\|87634`, `42\|359421` — **no `30`** |
| `nm-manifests.before.txt` | `1` (the C-115B manifest) |
| `explain-served-nd.before.txt` | **Index Scan** using `production_monthly_api10_idx`, 0.378 ms, `shared hit=72` |
| `dbsize.before.txt` | `17 GB` |
| `disk.before.txt` | ≥ 100 GB available |

The two `explain` outputs are the **P5.7 merge-blocker baseline**. Step 5 re-runs both and
diffs **the plan node, not the timing** — timing moves with cache state, the node does not.

---

## Step 1 — re-register the nine manifests

**Production write. Runtime < 60 s. Owner cue required.**

Every canonical row the later steps insert carries a foreign key to `lineage.manifests`, and
those nine rows exist only in `glasswell_d1`. `manifest_id` is `man_` + the first 32 hex
characters of the sha256, so the same sealed bytes re-register under the same id: this is a
re-index, not a re-acquisition.

### 1a — dry run first

```bash
ssh root@192.168.2.111
SIDECARS=$(find /data/raw/nm_ocd_* -name manifest.json | sort)
echo "$SIDECARS" | wc -l          # must print 9

sudo -u glasswell /opt/glasswell/venv/bin/python \
  /opt/glasswell/src/scripts/ops/nm_reregister_manifests.py \
  --dsn 'postgresql:///glasswell?host=/var/run/postgresql' \
  --expect-database glasswell \
  --dry-run \
  $(for s in $SIDECARS; do printf ' --sidecar %s' "$s"; done)
```

**`--expect-database` is not optional here.** `glasswell` and `glasswell_d1` are one letter
apart and only one of them is production; without the flag the tool prints the database it
resolved and trusts you to read the line, and with it a mismatched `--dsn` exits 1 before any
statement runs. Confirm the first line of output reads `database=glasswell` as well — the flag
is the refusal, the line is the receipt.

Expected: nine `… would register …` lines, nine distinct `man_…` ids, and `lineage.manifests`
unchanged — the dry run holds a read-only connection, so it cannot write even if it tried. The
`wcproduction` id must be **`man_4d3bceb6a5b79880db518e00d933ae95`**. If it is not, **stop**:
the bytes are not the bytes that produced the scratch load.

### 1b — confirm integrity before writing

```bash
for d in /data/raw/nm_ocd_*/*/*/; do
  [ -f "$d/MANIFEST.sha256" ] && (cd "$d" && sha256sum -c MANIFEST.sha256)
done
```

Every line must read `OK`. A mismatch aborts the whole track.

### 1c — register

```bash
sudo -u glasswell /opt/glasswell/venv/bin/python \
  /opt/glasswell/src/scripts/ops/nm_reregister_manifests.py \
  --dsn 'postgresql:///glasswell?host=/var/run/postgresql' \
  --expect-database glasswell \
  $(for s in $SIDECARS; do printf ' --sidecar %s' "$s"; done)
```

Step 1a's command with `--dry-run` removed and **`--expect-database` still on it** — this is
the invocation that writes, so it is the one the refusal exists for. Expected: nine
`… registered …` lines, `supersedes=nothing` on each. An `already present` line is not an
error — record it.

### 1d — verify

```bash
sudo -u postgres psql -d glasswell -tAc \
  "select source_id, count(*) from lineage.manifests where source_id like 'nm_ocd%'
    group by 1 order by 1"
```

Expected: exactly nine rows — `nm_ocd_ogrid`, `nm_ocd_pod`, `nm_ocd_podwc`, `nm_ocd_pool`,
`nm_ocd_property`, `nm_ocd_spacingunit`, `nm_ocd_wchistory`, `nm_ocd_wcproduction`,
`nm_ocd_wellhistory`, each count **1**, each `fetch_vintage` **2026-08-20**.

### 1e — the `fetch_derivation_id` gap, decided on the record

Each sidecar carries a `fetch_derivation_id`, and the tool does not pass it: the NM `raw.fetch`
`lineage.derivations` rows live in `glasswell_d1`, so setting the column against production
would violate the foreign key. A re-registered manifest therefore resolves to its bytes and its
`acquisition_params` but **not** to the fetch that produced them.

**This is an owner decision and it must not be defaulted silently.** Either copy the three
`raw.fetch` derivation rows across from `glasswell_d1` with their inputs and rules and set the
column, **or** accept the gap and write it here, in one paragraph, where a reader of
`?explain=true` can find it. **Do not re-fetch to close it** — the FTP is pulled once, ever.

**Taken 2026-08-31, on the record: the gap is accepted, provisionally, and remains open for the
owner to close.** Nine manifests were registered at Step 1c with `fetch_derivation_id` unset, so
a reader who resolves one reaches its bytes, its sha256 and its `acquisition_params`, but not the
`raw.fetch` derivation that produced them. The alternative was taken seriously rather than waved
off: `glasswell_d1` still exists on the host and still holds all nine `raw.fetch` rows, so the
copy is available at any later date and nothing here forecloses it. It was not done tonight
because a cross-database derivation copy has to bring its own foreign-key closure —
`derivation_inputs`, `derivation_rules`, and whatever `environments`, `recipes` and `sources`
those reference — and a half-copied closure pollutes the lineage spine, which is the one table in
this system that must not be guessed at. Accepting a *stated* gap is recoverable; a wrong
derivation row is not, because `lineage.derivations` is append-only.

What this costs a reader, precisely: `?explain=true` on a New Mexico figure resolves the
conformance rules and the promotion derivation, and stops at the manifest. It does not claim a
fetch it cannot evidence. That is a smaller lie than none at all, which is the standard this
project holds — but it is still an incomplete chain, and it should be closed rather than left.

### 1f — the smoke-check trap

`/v1/health` smoke check 15 flips from 19/1 to 20/0 **at this step**, on the manifest rows
alone: `freshness_state` is a pure function of `max(manifests.fetch_vintage)` and does not
consult canonical. For roughly the next two hours it reads 20/0 with **zero** New Mexico
canonical rows. It is a fetch-freshness signal, not a promotion signal. Do not read it as
success.

### Rollback

**None, and none is needed.** `lineage.manifests` is append-only by trigger. A manifest row
with no canonical rows behind it is exactly the state this instance carries for
`nm_c115b_upstream` today, and it serves nothing. If the track is abandoned after this step,
leave the rows and note it in the register.

---

## Step 2 — stage the nine tables from the host cache

**Production write. Runtime ~35–40 min.** No socket is opened to OCD: `--stage-only` reads the
raw zone.

```bash
df -h /var/lib/postgresql       # need >= 40 GB avail; 105 GB observed 2026-08-29
pgrep -a pg_restore || echo "no restore drill running"

sudo systemd-run --unit=t3-nm-stage --collect \
  --property=User=glasswell --property=Group=glasswell \
  --property=TimeoutStartSec=7200 --property=MemoryMax=6G \
  --setenv=GLASSWELL_STAGING_ROOT=/data/staging \
  /opt/glasswell/venv/bin/python -m glasswell.ingest.nm_ocd \
    --stage-only --dsn 'postgresql:///glasswell?host=/var/run/postgresql'

journalctl -u t3-nm-stage -f
```

**Do not pass `--tables`.** Step 4 needs all eight siblings of `wcproduction`.

Expected: `staged_rows` for `wcproduction` = **17,645,580** — that is the Parquet partition
registry, not Postgres rows. Wall clock ~34 min for `wcproduction` plus a few minutes for the
eight siblings. Peak RSS ~2.24 GB, comfortably under the unit's `MemoryMax=6G`. Staging
footprint **≈ 448 MB**: `wchistory` 167 MB, `wellhistory` 150 MB, `podwc` 44 MB, `pod` 37 MB,
`property` 18 MB, `ogrid` 15 MB, `spacingunit` 14 MB, `pool` 2.7 MB,
`wcproduction__partitions` 32 kB.

```bash
sudo -u postgres psql -d glasswell -tAc "
select relname||' '||n_live_tup from pg_stat_user_tables
 where schemaname='staging' and relname like 'stg_nm_ocd%' order by 1"
du -sh /data/staging/nm_ocd_wcproduction        # ~234 MB, reused not rewritten
```

Expected non-zero: `stg_nm_ocd_wellhistory__records` **321,510**,
`stg_nm_ocd_wchistory__records` **426,529**, the six registry tables, and
`stg_nm_ocd_wcproduction__partitions`. **`stg_nm_ocd_wcproduction__records` stays 0 by
design** — that table is Parquet-staged, not Postgres-staged.

### Rollback

`staging.*` is not append-only-triggered and never serves, so this is the one step in this
runbook with a real undo. **Nine relations, not eight:**

```sql
begin;
truncate staging.stg_nm_ocd_pool__records,
         staging.stg_nm_ocd_ogrid__records,
         staging.stg_nm_ocd_property__records,
         staging.stg_nm_ocd_spacingunit__records,
         staging.stg_nm_ocd_podwc__records,
         staging.stg_nm_ocd_pod__records,
         staging.stg_nm_ocd_wchistory__records,
         staging.stg_nm_ocd_wellhistory__records,
         staging.stg_nm_ocd_wcproduction__partitions;
commit;
```

The ninth, `__partitions`, is the Parquet partition registry. A `<table>__records` pattern
excludes it and would leave a registry pointing at a store the truncate did not touch.

**Keep the Parquet store.** `/data/staging/nm_ocd_wcproduction` (234 MB) stays. It is
content-addressed, it cost 34 minutes to build, and a re-stage reproduces it byte-for-byte from
raw. **Truncate the registry, keep the store.**

**Truncate nothing under `canonical.` or `lineage.`.** Record the truncate, and the fact that
the Parquet was retained, below.

---

## Step 3 — promote the spine

**Production write. Runtime ~89 minutes (5,335 s measured).**

The flag is `--promote-only`. **There is no `--promote`** — the half-mode flags are a mutually
exclusive required group and the parser will reject the shorter spelling.

```bash
sudo systemd-run --unit=t3-nm-promote --collect \
  --property=User=glasswell --property=Group=glasswell \
  --property=TimeoutStartSec=14400 --property=MemoryMax=6G \
  --setenv=GLASSWELL_STAGING_ROOT=/data/staging \
  /opt/glasswell/venv/bin/python -m glasswell.ingest.nm_ocd \
    --promote-only --dsn 'postgresql:///glasswell?host=/var/run/postgresql'

journalctl -u t3-nm-promote -f
systemctl show t3-nm-promote -p Result -p ExecMainStatus   # after it exits
```

Expected, exactly. These are the scratch run's numbers over identical bytes, so they are
assertions rather than estimates:

| check | value |
|---|---|
| rows read | **17,645,580** |
| `promoted_rows` | **17,597,960** |
| `quarantined` | **47,620** — `key_collision` 45,182, `duplicate_row` 2,438 |
| reconciliation identity | 17,645,580 = 17,597,960 + 47,620 + 0 |
| months | **139**, 2015-01 → 2026-07 |
| promotion derivations | **139**, one per month |
| vintage | one; `rows_examined` 17,645,580, `rows_appended` 17,597,960 |
| distinct `entity_key` / `api10` / pools | 80,623 / 70,024 / 2,596 |
| canonical total after | 7,223,544 + 17,597,960 = **24,821,504** |
| stream split | gas 8,227,145 · oil 4,371,030 · water 4,999,785 |
| shape | `entity_type` / `reporting_level` = `well_completion_pool`, `granularity` = `well_observed`, one shape only |
| peak RSS | **653 MB** |
| table growth | **9,893 MB**, plus ~5 GB transient WAL (`max_wal_size` = 4,096 MB) |

Do not use the 17,996,363 canonical total that appears in `d1-p4-status.md`; it was computed
against 398,403 ND rows, before P3's back-load. Production holds 7,223,544 ND rows.

Check `df -h /var/lib/postgresql` mid-run.

### If it exits 2

It printed `refused: …` on stdout, a deliberately non-JSON line. **That is the guard.** The
diverging month lands nothing, no published row is rewritten or withdrawn, and months earlier
than the diverging one keep their appends. Re-run on a **later day**. Do not delete rows.
Cross-check:

```sql
select v.rows_appended,
       (select count(*) from canonical.production_monthly p
         where p.report_vintage = v.report_vintage
           and p.source_id = 'nm_ocd_wcproduction')
  from lineage.vintages v where v.source_id = 'nm_ocd_wcproduction';
```

The two numbers must be **equal**. An inequality on the refusal path is a defect report, not an
operator problem.

### Rollback

**There is none by design, and that is correct.** `canonical.production_monthly` carries an
append-only trigger and `update`/`delete` are revoked. Restatements are appended, never applied
as edits. If the promotion lands rows that must not stand, the remedy is a **restatement under
a new vintage**, authored as its own change — not a delete.

The nightly dump at `/data/backups/pg/glasswell-*.dump` is a **disaster-recovery option of
unrehearsed cost, not a step in this runbook.** `glasswell-restore-drill.service` restores into
`glasswell_restore_<epoch>`; that proves a dump is *loadable*. Nobody has ever restored one
*over* `glasswell`, and doing so would discard everything written since it was taken. **A
restore that has never been run in the direction it would be used is not a rollback.**

Abort condition B requires a verified-fresh dump **before** this step for exactly that reason:
the mitigation is the precondition, not the undo. Do not improvise a `delete`, and do not treat
a restore as routine.

---

## Step 4 — promote the dimensions

**Production write. Runtime ~47 s.**

### 4a — registry check: nothing to seed

Production already holds all **79** New Mexico rules: 74 `nm_ocd_*` plus 5 `nm_c115b_*`. Older
status files tell the operator to re-seed; that step is already satisfied.

```bash
sudo -u postgres psql -d glasswell -tAc \
  "select count(*) from lineage.conformance_rules where rule_id like 'cr\_nm\_%'"
# expect 79
```

If it is not 79, run `seed_all` first. `lineage.conformance_rules` is append-only, so `seed_all`
is safe and idempotent for insert-only rows.

### 4b — run

```bash
sudo systemd-run --unit=t3-nm-dims --collect \
  --property=User=glasswell --property=Group=glasswell \
  --property=TimeoutStartSec=1800 --property=MemoryMax=4G \
  /opt/glasswell/venv/bin/python -m glasswell.ingest.nm_dims \
    --dsn 'postgresql:///glasswell?host=/var/run/postgresql'
```

Expected: observations read **426,529**; quarantined **0**; identity 426,529 = 426,529 + 0;
rows appended **763,473**; operator aliases **31,696**, all at confidence 1.000; derivations
**2** (`canonical.well_completions`, `lineage.operator_aliases`); one vintage; peak RSS
**907 MB**; wall clock **46.6 s**; table growth **265 MB**.

### 4c — verify, and carry the two-grain warning forward

```sql
select count(*)                                          as rows,
       count(distinct completion_key)                    as completions,
       count(distinct api10)                             as wells,
       count(*) filter (where production_month is null)  as dimension_rows
  from canonical.well_completions where source_id = 'nm_ocd_wchistory';
```

Expected `763473 | 147975 | 121940 | 763473`.

**`count(*)` on this table is a count of completion × POD × effective-date observations, never
of completions.** Any query that assumed a completion row implies a production month is now
wrong; filter on `production_month is null` for the dimension grain.

### 4d

Do **not** run `nm_dims` twice on the same day expecting a fix. A re-run that agrees appends
nothing; one that disagrees exits 2 with a non-JSON `refused: …`.

### Rollback

Same as Step 3: append-only, restate rather than delete.

---

## Step 5 — verification gates

Four gates. **G7-2 is the merge blocker.** A red gate stops the track; none of them is
weakened to let the next tier start.

### G7-1 — counts reconcile

Re-run every Step 0 query with `.after.txt` suffixes and diff:

| file | expected after |
|---|---|
| `prod-by-source` | `nd_mpr_xlsx\|7223544`, `nm_ocd_wcproduction\|17597960` |
| `completions-by-source` | `nd_mpr_xlsx\|2395283`, `nm_ocd_wchistory\|763473` |
| `wells-by-state` | **unchanged** — `33\|87634`, `42\|359421`, still no `30` |
| `nm-manifests` | `10` |

**`wells-by-state` unchanged is a pass, not a failure.** It is the proof that this runbook is
mechanical and the gate is structural.

### G7-2 — the ND served path still index-scans. MERGE BLOCKER

```bash
sudo -u postgres psql -d glasswell -c \
  "explain (analyze, buffers) select * from canonical.production_monthly
    where api10 = '3305301633'" | tee explain-served-nd.after.txt
```

Pass: the plan contains `Index Scan using production_monthly_api10_idx` with
`Index Cond: (api10 = '3305301633'::text)`. Baseline: Index Scan, 0.378 ms,
`Buffers: shared hit=72`. **A Seq Scan is a hard stop.**

Then the same shape against a New Mexico key, which is the timing evidence that the path
returns NM rows at scale:

```bash
sudo -u postgres psql -d glasswell -c \
  "explain (analyze, buffers) select * from canonical.production_monthly p
    where p.api10 = '3002540209'" | tee explain-served-nm.after.txt
# expect Index Scan, ~16 ms, non-zero rows
```

The size-independent half of this gate runs in CI as
`tests/integration/test_nm_promotion_gates.py`: the served query applies its `api10` predicate
**below** the `WindowAgg` and the `_latest` view applies it **above**. That property is what
decides the timing, and it does not need 24.8M rows to be true.

### G7-3 — `production_monthly_latest` cost, measured not assumed

```bash
time sudo -u postgres psql -d glasswell -c \
  "explain (analyze, buffers) select count(*) from canonical.production_monthly_latest
    where entity_type='well' and api10 is not null" | tee explain-latest-view.after.txt

time sudo -u postgres psql -d glasswell -c "
explain (analyze, buffers)
select api10, sum(volume) filter (where stream in ('oil','condensate'))
  from canonical.production_monthly_latest
 where entity_type = 'well' and api10 is not null group by api10"
```

**There is no pass/fail threshold here.** The gate is that the number is *recorded* with its
before/after pair and that a decision is written down.

The view has two consumers under `src/`, not one: `ingest/nd_mpr.py` and
`marts/land_metrics.py`'s `prod` CTE, which has no state filter and runs on
`glasswell-ingest.timer`. It measured 73,069 ms warm / 156,370 ms cold at 17.6M rows and will
span ~24.8M after Step 3. If the measured figure pushes `glasswell-ingest.service` past its
`TimeoutStartSec=3600`, that is a **stop-and-fix**, and the fix is the `prod` CTE restriction
that Tier 2 lands.

**The cadence, honestly:** `glasswell-ingest.timer` is `*-*-05 04:30:00 UTC` — **monthly, day
5**, not nightly. This is a real cost on a real job with up to 31 days to fix it, not a
same-night emergency.

### G7-4 — deployed verification suites

```bash
sudo /opt/glasswell/src/infra/verify.sh
sudo /opt/glasswell/src/scripts/smoke.sh
```

Both must pass. Read smoke check 15 with Step 1f in mind.

### G7-5 — the status surface reports New Mexico as New Mexico

Wait one `glasswell-status.timer` tick (≤ 15 min) or force it with
`systemctl start glasswell-status.service`, then:

```bash
curl -sf -H "X-Glasswell-Key: $owner_key" "$API/v1/status" \
  | python3 -c '
import json,sys
ds={d["dataset_id"]: d for d in json.load(sys.stdin)["data"]["datasets"]}
assert "canonical.production_monthly" not in ds, "unqualified id still served"
nd, nm = ds["canonical.production_monthly/nd"], ds["canonical.production_monthly/nm"]
assert nd["scope"] == "North Dakota" and nm["scope"] == "New Mexico"
m = lambda d: {x["metric_id"]: x["value"] for x in d["metrics"]}
assert m(nd)["rows"] == 7223544, m(nd)
assert m(nm)["rows"] == 17597960, m(nm)
print("G7-5 pass:", m(nd)["rows"], "ND /", m(nm)["rows"], "NM")'
```

**Pass condition: New Mexico production is reported under a New Mexico dataset, or it is not
reported at all. Never under North Dakota.** A failure here means the Phase 2 fix did not reach
the deployed bytes. It is a stop: the output is append-only and the timer will keep
republishing it.

### Record the run

Write every measured number, every `explain` output, the Step 1e decision and the G7-3
disposition to `work-output/t3-tier1-status.md`. Gates write reports to disk; both survive the
session.

---

## Measured run

*(Fill in when the ops window opens. Nothing here yet: as of this file's authoring the four
production steps have not been run.)*

| step | run at | result | notes |
|---|---|---|---|
| 1 manifests | — | — | — |
| 2 staging | — | — | — |
| 3 promotion | — | — | — |
| 4 dimensions | — | — | — |
| 5 gates | — | — | — |

> Copyright (C) 2026 Ryan MacDonald &lt;ryan@rfxn.com&gt; &#183; All rights reserved
