# Runbook — Tier 2, the New Mexico spine and the map

Four production steps against VM 111, in order, each with the numbers it must produce. Follow
this file; it does not assume you have read the plan behind it.

This is the sibling of `docs/runbook-nm-promotion.md`, which is **Tier 1**. Read the scope
boundary below before running anything: the two runbooks share a raw zone and two of their
preconditions, and they are not interchangeable.

**Two databases, one letter apart.** `glasswell` is production. `glasswell_d1` is the
disposable scratch database on the same host. Every command below takes its database from
`GLASSWELL_DSN`, or states `-d` where it is a `psql` invocation; no command carries a DSN on
its own argument list, because an argument list is readable in `/proc` and lands in shell
history. Export the variable once, check it with `echo "$GLASSWELL_DSN"` before you start, and
if any command in the session ran against the wrong one, stop and re-verify what it touched.

---

## What this does, and what it deliberately does not

**Tier 2 opens the gate.** `src/glasswell/api/routers/wells.py` roots the well spine on
`canonical.wells`, and `api/routers/production.py` raises `not_found` for any API-10 that spine
does not resolve. Step 3 writes the first prefix-30 `canonical.wells` row, and from that
statement onward `GET /v1/wells/30…` resolves and every New Mexico figure behind it becomes
servable. Step 4 puts the wells on the map.

**Tier 2 loads no production history.** It writes `canonical.wells`, `canonical.well_spatial`
and `marts.nm_wells_tile` and nothing else. `canonical.production_monthly` is Tier 1's Step 3 —
~89 minutes and ~24.8M appended rows — and it is governed by `runbook-nm-promotion.md` under
its own owner authorisation. **Nothing in this file runs it, shortens it or prepares for it.**
That is also why `glasswell.ingest.nm_ocd` and `glasswell.ingest.nm_dims` keep their
`python -m` spelling while Tier 2's two steps are console scripts: an entry point is a form of
encouragement.

A New Mexico well card after Tier 2 alone therefore resolves, carries its geometry provenance
and its status vocabulary rule, and reports **no production series**. That is the correct
answer for a spine with no history behind it, and `cr_nm_wcproduction_pool_rollup_1` plus the
`production_reported_at_pool_grain` disclosure are what say so on the surface rather than
rendering an empty chart.

Nor is any of this a re-acquisition. The OCD FTP is never pulled again; every byte these steps
read was sealed on 2026-08-20 and lives in `/data/raw/nm_ocd_*` with its `manifest.json`
sidecar and `MANIFEST.sha256`.

### Where Tier 2 touches Tier 1, stated rather than hidden

Steps 1 and 2 below are **strict subsets** of Tier 1's Steps 1 and 2, narrowed to the one
table Tier 2 reads:

| | Tier 1 | Tier 2 |
|---|---|---|
| manifests registered | nine sidecars | one — `nm_ocd_wellhistory` |
| tables staged | all nine, `wcproduction` included (~35–40 min) | `wellhistory` only |
| Parquet store built | yes, 234 MB, ~34 min | no |
| canonical rows written | ~24.8M production, 763,473 completions | ~321,510 headers, ~141,778 points |

Running Tier 2's Steps 1 and 2 **does not advance Tier 1**: `--tables wellhistory` leaves
`stg_nm_ocd_wcproduction__partitions` empty, so Tier 1's Step 3 remains blocked on its own
Step 2 exactly as it is today. If Tier 1 has already run, Tier 2's Steps 1 and 2 are recorded
no-ops — `lineage.manifests` is idempotent on the sha256 and the staging insert is keyed —
and you start at Step 3.

---

## Number provenance, so no figure here is mistaken for another

Three kinds of number appear below and each is labelled where it appears:

- **sealed** — measured over all 321,510 records of the 2026-08-20 artifact and stored in the
  conformance registry. `cr_nm_wellhistory_coordinate_1.spec.measured` and
  `cr_nm_wellhistory_effective_1` are the rows; `/v1/conformance/cr_nm_wellhistory_coordinate_1`
  serves them. These are assertions, not estimates: a divergence means the inputs are not the
  inputs.
- **estimated** — an analogy from a comparable measured run, named at the point of use. Never
  an acceptance criterion.
- **record it** — no expectation is published because none was measured. Write the number down;
  a runbook that invents a threshold is worse than one that admits it has none.

Nothing in this file is derived from `tests/fixtures/nm_ocd/`. The repository's fixture-driven
proof of this chain is `tests/integration/test_nm_tier2_end_to_end.py`; its counts are 28
records and 22 tile rows and they are **not** a production forecast.

---

## Preconditions

Each one is a command with a pass condition. All seven, before Step 1.

```bash
ssh root@192.168.2.111
API=https://glasswell.rpx.sh          # or the LAN name, whichever this window uses
GLASSWELL_DSN='postgresql:///glasswell?host=/var/run/postgresql'
```

**1 — the deployed tree carries this track.** The two console scripts are installed by
`scripts/deploy.sh`'s editable reinstall, which runs on every deploy whether or not the lockfile
moved.

```bash
ls -l /opt/glasswell/venv/bin/glasswell-nm-wells /opt/glasswell/venv/bin/glasswell-nm-tiles
# both present, or STOP: deploy first. Neither has ever existed on this host before this track.
```

**2 — the relations and the tile function exist.** Named, never version-numbered: a migration
number is not a contract.

```bash
sudo -u postgres psql -d glasswell -tAc "
select to_regclass('canonical.wells'), to_regclass('canonical.well_spatial'),
       to_regclass('marts.nm_wells_tile'), to_regclass('marts.tile_nm_wells'),
       (select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
         where n.nspname='marts' and p.proname='nm_wells')"
# four non-null names and a 1, or STOP.
```

**3 — the conformance rows the promotion reads are seeded.** The promotion loads them by
family from the registry and carries no state-code literal, so an absent row is a hard failure
at the first batch, not a silent default.

```bash
sudo -u postgres psql -d glasswell -tAc \
  "select count(*) from lineage.conformance_rules where rule_id like 'cr\_nm\_wellhistory\_%'"
# expect 10. Fewer: run seed_all first — lineage.conformance_rules is append-only and the
# seeder is idempotent for insert-only rows.
```

**4 — the sealed wellhistory bytes are present and intact.**

```bash
find /data/raw/nm_ocd_wellhistory -name manifest.json | sort   # must print exactly 1
for d in /data/raw/nm_ocd_wellhistory/*/*/; do
  [ -f "$d/MANIFEST.sha256" ] && (cd "$d" && sha256sum -c MANIFEST.sha256)
done
# every line OK. A mismatch aborts the whole track — do not re-fetch to repair it.
```

**5 — the executing role owns what Step 4 replaces.** Step 4 rewrites a mart table *and* runs
`create or replace` over every tile function, and `create or replace function` requires
ownership rather than a grant. A function first installed by the deploy as `postgres` refuses
the next refresh with `must be owner of function …`; `scripts/deploy.sh` step 6b3 exists to
reassign every `marts` function to the pipeline role after installing it as superuser. Whether
that step has run against this host is a fact, not a guess — read it, asked as the user that
will run Step 4 so the answer is about that user and not about a role name assumed here:

```bash
sudo -u glasswell psql -d glasswell -tAc "
select current_user,
       has_table_privilege('marts.nm_wells_tile','insert')
   and has_table_privilege('marts.nm_wells_tile','delete') as can_rewrite,
       (select pg_get_userbyid(proowner) from pg_proc p
          join pg_namespace n on n.oid=p.pronamespace
         where n.nspname='marts' and p.proname='nm_wells') as function_owner"
# can_rewrite must be t. If function_owner is not current_user, deploy step 6b3 has not run
# against this host and Step 4's create-or-replace will be refused — take the alternate
# invocation given at Step 4, and route the ownership drift to the deploy that caused it.
```

**6 — a verified-fresh dump exists.** Tier 1's abort condition B, unchanged and for the same
reason: `canonical.wells` and `canonical.well_spatial` carry append-only triggers
(`wells_append_only`, `well_spatial_append_only`), so the mitigation is the precondition and
not the undo.

```bash
systemctl show glasswell-backup.service -p Result -p ExecMainStatus
#   must read  Result=success  ExecMainStatus=0
ls -la --time-style=full-iso /data/backups/pg/glasswell-*.dump | tail -3
#   newest dump < 24h old AND within 10% of the previous dump's size, or STOP
```

**7 — no competing writer.**

```bash
pgrep -a pg_restore || echo "no restore drill running"
systemctl is-active glasswell-ingest.service      # must be inactive
systemctl list-unit-files 'glasswell-repromote*' --no-pager   # must be empty
ls /etc/systemd/system/ | grep -c '^glasswell-'   # expect 14, matching the tree
df -h /var/lib/postgresql                         # < 40 GB available: stop, escalate
```

`glasswell-restore-drill.timer` is `Sun *-*-* 04:00:00` with `RandomizedDelaySec=600`: avoid
**Sunday 03:45–05:00 UTC**. `glasswell-ingest.timer` is `*-*-05 04:30:00 UTC`,
`RandomizedDelaySec=1800`: if the run falls on the 5th, wait for it or start before 04:00. That
unit's fifth `ExecStart` is `python -m glasswell.marts.nm_wells`, which is Step 4 by another
name — it must not fire mid-run.

---

## Abort conditions

Checked before Step 3. **Any one of them stops the run.**

### A — the status surface reports New Mexico as New Mexico

Tier 1's condition A concerns `canonical.production_monthly`. **Tier 2 needs the other half of
the same fix**, and it is a different query: `_inventory` reads `canonical.wells_latest` with
`filter (where state_code = '33')` and `'42'`, and it reads the map layers from
`marts.nd_wells_tile` and `marts.tx_wells_tile`. Both gained their `'30'` and
`marts.nm_wells_tile` arms in the same v0.69 release.

The pre-fix failure mode for Tier 2 is **omission, not misattribution**: an unfixed collector
counts state codes 33 and 42 only, so 142,000 New Mexico wells would be reported nowhere rather
than under North Dakota. That is a weaker hazard than Tier 1's and it is still a stop, because
`scripts/smoke.sh` keys its entire New Mexico block on `canonical.wells_latest/nm` — without
that dataset the smoke suite cannot distinguish "not promoted yet" from "regressed", and Step
5's gates go blind at the moment they are most needed.

```bash
grep -c "canonical.wells_latest/nm" \
  /opt/glasswell/src/src/glasswell/status/collector.py
grep -c "marts.nm_wells_tile) as nm_wells" \
  /opt/glasswell/src/src/glasswell/status/collector.py
# 1 or more on both = the split is in the deployed source, proceed. 0 = STOP.

curl -sf -H "X-Glasswell-Key: $owner_key" "$API/v1/status" \
  | python3 -c 'import json,sys
ids={d["dataset_id"] for d in json.load(sys.stdin)["data"]["datasets"]}
want={"canonical.wells_latest/nm","marts.published_map_layers/nm"}
print(sorted(want & ids) or "STOP: the running process predates the fix")'
# must print both ids. A file on disk that carries the fix while the process does not is the
# case this second check exists for.
```

**Check for the fix's presence, not for the defect's absence.** Both greps above are positive.

### B — the operator-name ordering decision, taken before Step 3 and not after

`canonical.wells.operator_name_reported` is resolved at promotion time from
`lineage.operator_aliases`, which only Tier 1's Step 4 (`nm_dims`) writes. It is **not** one of
the attributes `_HEADER_DIVERGENCE` compares, so a later re-run finds no divergence, appends
nothing through the `(api10, effective_from)` anti-join, and leaves every name null. The table
is append-only. **A name absent at Step 3 is absent permanently for that header**, and the only
route back is a restatement under a new effective row, authored as its own change.

```bash
sudo -u postgres psql -d glasswell -tAc \
  "select count(*) from lineage.operator_aliases where source_id = 'nm_ocd_ogrid'"
```

- **Non-zero** — proceed. Every promoted header will carry its operator name, and so will the
  tile.
- **Zero** — this is an owner decision and it must not be defaulted silently. Either accept that
  every New Mexico well card and every `nm_wells` tile feature shows a null operator until a
  restatement supplies one, and **write that acceptance here before Step 3**, or defer Tier 2
  until Tier 1's Step 4 has run. Tier 1's Step 4 is a Tier 1 step under Tier 1's
  authorisation; this runbook does not run it.

`tests/integration/test_nm_tier2_end_to_end.py` asserts both halves of this — the absent name
that stays absent across a re-run, and the present name that reaches the header and the tile.

### C — the ordinary stops

- Any step exits **2** with a `refused: …` line → stop. That is the guard working. The line is
  deliberately not JSON; do not pipe the step through `jq`. Do not delete rows, do not re-run
  the same day.
- Any command that ran with the wrong `GLASSWELL_DSN` or `-d` → stop and re-verify what it
  touched.

---

## Step 0 — baseline

Read-only. Save to `/data/scratch/t3-nm-tier2/baseline/` on the host and paste the results into
this file's *Measured run* section when the run happens.

```bash
sudo -u glasswell mkdir -p /data/scratch/t3-nm-tier2/baseline
cd /data/scratch/t3-nm-tier2/baseline || exit 1

sudo -u postgres psql -d glasswell -tAc \
  "select state_code, count(*) from canonical.wells group by 1 order by 1" \
  > wells-by-state.before.txt
sudo -u postgres psql -d glasswell -tAc \
  "select left(api10,2), geom_type, count(*) from canonical.well_spatial group by 1,2 order by 1,2" \
  > spatial-by-state.before.txt
sudo -u postgres psql -d glasswell -tAc \
  "select count(*) from marts.nm_wells_tile" > nm-tile-rows.before.txt
sudo -u postgres psql -d glasswell -tAc \
  "select count(*) from lineage.manifests m join lineage.sources s using (source_id)
    where s.jurisdiction='NM'" > nm-manifests.before.txt
sudo -u postgres psql -d glasswell -tAc \
  "select reason_code, count(*) from lineage.quarantine_rows
    where source_id = 'nm_ocd_wellhistory' group by 1 order by 1" \
  > nm-quarantine.before.txt
sudo -u postgres psql -d glasswell -c \
  "explain (analyze, buffers) select * from canonical.production_monthly
    where api10 = '3305301633'" > explain-served-nd.before.txt
curl -sf -H "X-Glasswell-Key: $owner_key" "$API/v1/status" > status.before.json
df -h /var/lib/postgresql > disk.before.txt
sudo -u postgres psql -d glasswell -tAc \
  "select pg_size_pretty(pg_database_size('glasswell'))" > dbsize.before.txt
```

Expected. Any difference stops the run:

| file | expected |
|---|---|
| `wells-by-state.before.txt` | `33\|87634`, `42\|359421` — **no `30`** |
| `spatial-by-state.before.txt` | no `30` line |
| `nm-tile-rows.before.txt` | `0` |
| `nm-quarantine.before.txt` | empty |
| `nm-manifests.before.txt` | `1` if Tier 1 has not run (the C-115B manifest); `10` if it has |
| `explain-served-nd.before.txt` | **Index Scan** using `production_monthly_api10_idx` |
| `disk.before.txt` | ≥ 40 GB available |

`explain-served-nd` is carried from Tier 1's baseline for one reason: Step 5 re-runs it to prove
Tier 2 did not disturb the served North Dakota path. Diff **the plan node, not the timing**.

---

## Step 1 — register the wellhistory manifest

**Production write. Runtime < 10 s. Owner cue required — this is the first write.**

Every canonical row Step 3 inserts carries a foreign key to `lineage.manifests`.
`manifest_id` is `man_` + the first 32 hex characters of the sha256, so the same sealed bytes
re-register under the same id: this is a re-index, not a re-acquisition.

```bash
SIDECAR=$(find /data/raw/nm_ocd_wellhistory -name manifest.json)
echo "$SIDECAR" | wc -l          # must print 1

sudo --preserve-env=GLASSWELL_DSN -u glasswell /opt/glasswell/venv/bin/python \
  /opt/glasswell/src/scripts/ops/nm_reregister_manifests.py \
  --expect-database glasswell --dry-run --sidecar "$SIDECAR"
```

**`--expect-database` is not optional here.** `glasswell` and `glasswell_d1` are one letter
apart and only one of them is production; with the flag a mismatched `GLASSWELL_DSN` exits 1
before any statement runs. Confirm the first line reads `database=glasswell` as well — the flag is the
refusal, the line is the receipt.

Expected: one `… would register …` line, one `man_…` id, `lineage.manifests` unchanged (the dry
run holds a read-only connection, so it cannot write even if it tried).

Then the same command with `--dry-run` removed and **`--expect-database` still on it**:

```bash
sudo --preserve-env=GLASSWELL_DSN -u glasswell /opt/glasswell/venv/bin/python \
  /opt/glasswell/src/scripts/ops/nm_reregister_manifests.py \
  --expect-database glasswell --sidecar "$SIDECAR"

sudo -u postgres psql -d glasswell -tAc \
  "select source_id, fetch_vintage from lineage.manifests where source_id = 'nm_ocd_wellhistory'"
```

Expected: `nm_ocd_wellhistory|2026-08-20`, one row. An `already present` line is not an error —
record it; that is what Tier 1 having run first looks like.

**The `fetch_derivation_id` gap.** The sidecar carries one and the tool does not pass it: the
NM `raw.fetch` `lineage.derivations` rows live in `glasswell_d1`, so setting the column against
production would violate the foreign key. A re-registered manifest resolves to its bytes and its
`acquisition_params` but not to the fetch that produced them. Tier 1's Step 1e is where that
decision is recorded; if it has already been taken, this step inherits it. **Do not re-fetch to
close it** — the FTP is pulled once, ever.

**The smoke-check trap.** `/v1/health`'s fetch-freshness check moves at this step, on the
manifest row alone: `freshness_state` is a pure function of `max(manifests.fetch_vintage)` and
consults no canonical table. For the next hour it reads better with **zero** New Mexico
canonical rows. Record what it reads; do not read it as success.

### Rollback

**None, and none is needed.** `lineage.manifests` is append-only by trigger. A manifest row with
no canonical rows behind it is exactly the state this instance carries for `nm_c115b_upstream`
today, and it serves nothing. If the track is abandoned here, leave the row and note it in the
register.

---

## Step 2 — stage the header table, and only it

**Production write. Runtime: estimated 2–5 minutes.** No socket is opened to OCD:
`--stage-only` reads the raw zone.

```bash
sudo systemd-run --unit=t3-nm-t2-stage --collect \
  --property=User=glasswell --property=Group=glasswell \
  --property=TimeoutStartSec=3600 --property=MemoryMax=6G \
  --property=EnvironmentFile=-/etc/glasswell/code-version.env \
  --setenv=GLASSWELL_STAGING_ROOT=/data/staging \
  /opt/glasswell/venv/bin/python -m glasswell.ingest.nm_ocd \
    --stage-only --tables wellhistory

journalctl -u t3-nm-t2-stage -f
systemctl show t3-nm-t2-stage -p Result -p ExecMainStatus   # after it exits
```

**`--tables wellhistory` is the Tier 2 boundary and it is load-bearing.** Tier 1's Step 2 says
"do not pass `--tables`" because Tier 1's Steps 3 and 4 need all nine. Tier 2 needs one, and
passing one is what keeps this runbook from staging the 17,645,580-record production spine and
its 34-minute Parquet build.

Verify:

```bash
sudo -u postgres psql -d glasswell -tAc "
select relname||' '||n_live_tup from pg_stat_user_tables
 where schemaname='staging' and relname like 'stg_nm_ocd%' order by 1"
```

| check | value | provenance |
|---|---|---|
| `stg_nm_ocd_wellhistory__records` | **321,510** | sealed |
| `stg_nm_ocd_wcproduction__partitions` | **0** — unchanged, and it must stay 0 | Tier 2 boundary |
| every other `stg_nm_ocd_*` | unchanged from Step 0 | |
| staging footprint added | ~150 MB | estimated, from Tier 1's measured `wellhistory` 150 MB |

### Rollback

`staging.*` is not append-only-triggered and never serves, so this is the one step in this
runbook with a real undo:

```sql
begin;
truncate staging.stg_nm_ocd_wellhistory__records;
commit;
```

**One relation, not nine.** Truncating the siblings would undo Tier 1's Step 2 if it has run.
Truncate nothing under `canonical.` or `lineage.`.

---

## Step 3 — promote the headers and the surface geometry

**Production write. This is the statement that opens the gate.**
**Runtime: estimated 1–5 minutes** — Tier 1's Step 4 measured 46.6 s and 907 MB peak RSS over
426,529 observations of comparable shape, and this reads 321,510. If it passes **30 minutes**,
stop and investigate rather than waiting.

```bash
sudo systemd-run --unit=t3-nm-t2-headers --collect \
  --property=User=glasswell --property=Group=glasswell \
  --property=TimeoutStartSec=3600 --property=MemoryMax=6G \
  --property=EnvironmentFile=-/etc/glasswell/code-version.env \
  /opt/glasswell/venv/bin/glasswell-nm-wells

journalctl -u t3-nm-t2-headers -f
systemctl show t3-nm-t2-headers -p Result -p ExecMainStatus   # after it exits
```

On success the step prints one JSON object. Expected, exactly:

| field | value | provenance |
|---|---|---|
| `staged_rows` | **321,510** | sealed |
| `header_rows` | **321,510** — every record yields a header | sealed |
| `geometry_rows` | **318,720** usable pairs | sealed |
| `quarantined.coordinate_absent` | **1,893** | sealed |
| `quarantined.coordinate_sentinel` | **897** | sealed |
| reconciliation, records | 321,510 = 321,510 + 0 unkeyed + 0 undated | enforced in code |
| reconciliation, geometry | 321,510 = 318,720 + 2,790 refusals | enforced in code |
| `geometry_appended` | **141,778** — one surface point per API-10 | sealed |
| `headers_appended` | between 142,000 and 321,510 | record it |
| `vintage_id` | one, `vin_nm_ocd_wellhistory_<today>` | |

`headers_appended` has no published expectation because none was measured: the append is
`distinct on (api10, effective_from)` and the count of distinct pairs in the artifact was never
counted. 142,000 distinct API-10s is the floor and the record count is the ceiling. **Write the
number down** — `lineage.vintages.rows_appended` carries it and Step 5 reconciles against it.

**A refused coordinate never suppresses a header.** Both reconciliations are on counted
populations rather than on subtraction, and the second is the one that says so: a header is a
point or a refusal, never neither and never both. If either raises `RowCountMismatch` the step
fails without committing.

Then verify against the store rather than against the step's own report:

```bash
sudo -u postgres psql -d glasswell -tAc "
select (select count(*) from canonical.wells where state_code='30')            as headers,
       (select count(distinct api10) from canonical.wells where state_code='30') as wells,
       (select count(*) from canonical.wells
         where state_code='30' and status_canonical is not null)                as invented_status,
       (select count(*) from canonical.well_spatial where left(api10,2)='30')  as points,
       (select count(*) from canonical.well_spatial
         where left(api10,2)='30' and geom_type <> 'surface')                  as non_surface,
       (select count(*) from canonical.well_spatial
         where left(api10,2)='30' and (st_x(geom)=0 or st_y(geom)=0))          as on_a_zero"
```

Expected: `headers` equals the reported `headers_appended`; `wells` = **142,000** (sealed);
`invented_status` = **0**; `points` = **141,778** (sealed); `non_surface` = **0**; `on_a_zero` =
**0**.

**Check the smoke suite's probe key now, not at G2-4.** `scripts/smoke.sh` defaults
`nm_api10=3002540209`, and once `/v1/status` reports a non-zero NM header count that branch
becomes an assertion rather than a skip: a header count above zero with a non-200 answer for
that key is reported `bad`, and the suite fails on a key rather than on the track.

```bash
sudo -u postgres psql -d glasswell -tAc \
  "select count(*) from canonical.wells where api10 = '3002540209'"
# 1 or more: nothing to do. 0: pick a promoted key and pass it as
#   scripts/smoke.sh --nm-api10 <key>
# at G2-4, and use the same key in G2-3.
```

`invented_status = 0` is not incidental, and it stays 0 after the status mapping landed.
`cr_nm_wellhistory_status_vocab_2` resolves the OCD letter to a canonical class at read time,
in `marts.nm_wells_tile` and on the serving path; it writes nothing back, because
`canonical.wells` is append-only and a backfill would have to invent a valid time the OCD never
filed. Any non-zero here is a rule violation, not a data improvement.

`on_a_zero = 0` is the direct form of the reason the coordinate policy is a pair rule: four
records carry a good New Mexico latitude and a longitude of exactly zero, and a latitude-only
check would have given those four wells a valid point in the Gulf of Guinea, about 9,000 km
away, in an append-only table, on a published tile layer.

### If it exits 2

It printed `refused: …` on stdout. That is `VintageAlreadyPromoted`: a header already published
at this `(api10, effective_from)` key carries different attributes, and a restatement is a new
effective row rather than a rewrite of one already published. The transaction rolled back;
nothing was written. Do not delete rows. Cross-check what is already resident and treat a
disagreement as a defect report, not an operator problem.

### Rollback

**There is none by design, and that is correct.** `canonical.wells` and
`canonical.well_spatial` carry append-only triggers from migration 009 and `update`/`delete` are
revoked. If the promotion lands rows that must not stand, the remedy is a **restatement under a
new effective row**, authored as its own change.

The nightly dump is a disaster-recovery option of unrehearsed cost, not a step in this runbook.
`glasswell-restore-drill.service` proves a dump is *loadable*; nobody has restored one *over*
`glasswell`, and doing so would discard everything written since it was taken. **A restore that
has never been run in the direction it would be used is not a rollback.** Precondition 6 exists
for that reason: the mitigation is the precondition.

---

## Step 4 — refresh the tile mart

**Production write, and the only reversible one.** Runtime: **record it** — the mart rebuilds
~141,778 point rows and reinstalls the tile functions. Estimated under two minutes.

**Run it in the same window as Step 3, back to back.** `glasswell-status.timer` is
`OnCalendar=*:0/15`; a tick that lands between the two publishes an internally inconsistent
pair — 142,000 current New Mexico wells beside 0 New Mexico map features — on the keyed status
surface. Unlike Tier 1's production figures, this one is not permanent: the collector atomically
replaces `/var/lib/glasswell/status.json` and the next tick after Step 4 corrects it. It is
still avoidable, and avoiding it costs nothing.

```bash
sudo systemd-run --unit=t3-nm-t2-tiles --collect \
  --property=User=glasswell --property=Group=glasswell \
  --property=TimeoutStartSec=1800 --property=MemoryMax=4G \
  --property=EnvironmentFile=-/etc/glasswell/code-version.env \
  /opt/glasswell/venv/bin/glasswell-nm-tiles

journalctl -u t3-nm-t2-tiles -f
```

If precondition 5 reported a `function_owner` other than the running user, or this exits with
`must be owner of function …`, run the same command with `--uid=postgres` in place of the two
`User=`/`Group=` properties. `postgres` is a superuser and can replace any of them. Running as
`postgres` changes the derivation's recorded environment, not its output — and the ownership
drift is a deploy-side defect to route, not a thing to work around every month.

Expected JSON: `layers` = `["nm_wells"]`, `row_counts` = `{"nm_wells_tile": 141778}` (sealed),
one `derivation_id`.

**Two side effects worth knowing before you run it.** `refresh_all` rebuilds rather than
appends, so the mart holds exactly one `derivation_id` afterwards. And it calls
`install_tile_functions`, which runs `create or replace` over **every** published layer's
function body, not only New Mexico's — from the deployed `tiles.py`. That rewrites no row and
is how the deploy runbook installs them too, but a New Mexico step that silently refreshes the
North Dakota tile source is worth knowing about rather than discovering.

```bash
sudo -u postgres psql -d glasswell -tAc "
select (select count(*) from marts.nm_wells_tile)                       as rows,
       (select count(distinct derivation_id) from marts.nm_wells_tile)  as derivations,
       (select count(*) from marts.nm_wells_tile where left(api10,2)<>'30') as foreign_rows,
       (select count(*) from marts.nm_wells_tile where status_canonical is not null) as invented,
       (select count(*) from marts.nm_wells_tile where derivation_id is null) as naked"
```

Expected: `141778 | 1 | 0 | 0 | 0`. The last two are the R8 and the no-naked-numbers checks in
their cheapest form: a tile is a served figure and every feature carries its handle.

### Rollback

Real, and the only one in this file:

```sql
begin;
delete from marts.nm_wells_tile;
commit;
```

`marts.nm_wells_tile` carries no append-only trigger and migration 061 grants
`delete, truncate` to `glasswell_pipeline`, because the mart is rebuilt rather than appended.
An empty mart makes `/v1/tiles/nm_wells/…` answer **204**, which is what it answers today.
**Do not delete anything under `canonical.` or `lineage.` to undo this step.** The mart
derivation stays in `lineage.derivations`; that is a record of what happened, not a leak.

---

## Step 5 — verification gates

Five gates. **G2-2 is the merge blocker.** A red gate stops the track; none of them is weakened
to let the next thing start.

### G2-1 — counts reconcile

Re-run every Step 0 query with `.after.txt` suffixes and diff:

| file | expected after | provenance |
|---|---|---|
| `wells-by-state` | `30\|<headers_appended>`, `33\|87634`, `42\|359421` | ND and TX unchanged |
| `spatial-by-state` | `30\|surface\|141778`, no other `30` geom_type | sealed |
| `nm-tile-rows` | `141778` | sealed |
| `nm-quarantine` | `coordinate_absent\|1893`, `coordinate_sentinel\|897` | sealed |
| `nm-manifests` | one more than before | |

**North Dakota and Texas unchanged is a pass, not an oversight.** It is the proof that this
runbook is state-scoped.

```sql
select v.rows_appended,
       (select count(*) from canonical.wells w where w.state_code = '30')
  from lineage.vintages v where v.source_id = 'nm_ocd_wellhistory';
```

The two numbers must be **equal**. An inequality is a defect report, not an operator problem.

### G2-2 — the served North Dakota path still index-scans. MERGE BLOCKER

```bash
sudo -u postgres psql -d glasswell -c \
  "explain (analyze, buffers) select * from canonical.production_monthly
    where api10 = '3305301633'" | tee explain-served-nd.after.txt
```

Pass: the plan contains `Index Scan using production_monthly_api10_idx` with
`Index Cond: (api10 = '3305301633'::text)`. **A Seq Scan is a hard stop.** Diff the node, not
the timing.

Then the New Mexico half of the same shape, which Tier 2 is what makes answerable at all:

```bash
sudo -u postgres psql -d glasswell -c \
  "explain (analyze, buffers) select * from canonical.wells where state_code = '30'
    and api10 = '3002540209'" | tee explain-served-nm.after.txt
# expect an index scan and a non-zero row count; 3002540209 is scripts/smoke.sh's NM probe key
```

### G2-3 — the gate is open on the served surface

```bash
curl -sf -o /dev/null -w '%{http_code}\n' \
  -H "X-Glasswell-Key: $owner_key" "$API/v1/wells/3002540209"
# 200. Before Step 3 this was 404, and nothing else in the system changed it.

curl -sf -H "X-Glasswell-Key: $owner_key" \
  "$API/v1/wells/3002540209?explain=true" | python3 -c 'import json,sys
d=json.load(sys.stdin)
card=d["data"]
assert card["state_code"]=="30", card
assert card["geometry_provenance"], "a served figure with no provenance is a naked number"
assert card["status_canonical"] is None, "no canonical status may be invented for New Mexico"
assert d.get("_explain"), "?explain=true resolved nothing"
print("G2-3 pass:", card["api10"], card["status_reported"], card["geometry_provenance"])'
```

If `3002540209` is not among the promoted headers, pass `--nm-api10` to smoke below and use the
same key here; take it from `select api10 from canonical.wells where state_code='30' limit 1`.

A tile over the same well's own surface point:

```bash
curl -sf -o /dev/null -w '%{http_code} %{size_download}\n' \
  -H "X-Glasswell-Key: $owner_key" \
  "$API/v1/tiles/nm_wells/12/<x>/<y>.pbf"
# 200 and non-zero bytes. Compute x and y from the card's surface_point the way
# scripts/smoke.sh does; a 204 here means the mart is empty and Step 4 did not run.
```

### G2-4 — deployed verification suites

```bash
sudo /opt/glasswell/src/infra/verify.sh
sudo /opt/glasswell/src/scripts/smoke.sh
```

Both must pass. `smoke.sh`'s New Mexico block **stops skipping at this step**: it is keyed on
`canonical.wells_latest/nm` from `/v1/status`, so force a status tick first with
`systemctl start glasswell-status.service` or the block will still report
`skip  New Mexico spine: /v1/status reports 0 NM headers`. Read the fetch-freshness check with
Step 1's trap in mind.

**A caveat on `verify.sh`, carried from Tier 1 and still true.** It compares the live schema
head to the restore-drill receipt, gated on a drill completing after `max(applied_at)`. Tier 2
applies no migration, so this window is narrower than Tier 1's — but if this track lands
alongside one that does, the newest restore proof is a proof about the *old* schema. Do not read
a green `verify.sh` in that window as restore coverage.

### G2-5 — the status surface reports New Mexico as New Mexico

Wait one `glasswell-status.timer` tick (≤ 15 min) or force it, then:

Capture the North Dakota figure **before** Step 3 as well — this gate compares against the
baseline, not against a number written here, because `canonical.wells_latest` ranks one row per
API-10 and is not the same count as `canonical.wells`:

```bash
# at Step 0, alongside the other baselines
curl -sf -H "X-Glasswell-Key: $owner_key" "$API/v1/status" > status.before.json
```

```bash
systemctl start glasswell-status.service
curl -sf -H "X-Glasswell-Key: $owner_key" "$API/v1/status" > status.after.json
python3 -c '
import json,sys
load = lambda p: {d["dataset_id"]: d for d in json.load(open(p))["data"]["datasets"]}
before, after = load("status.before.json"), load("status.after.json")
m = lambda ds,i: {x["metric_id"]: x["value"] for x in ds[i]["metrics"]}
assert after["canonical.wells_latest/nm"]["scope"] == "New Mexico"
assert after["marts.published_map_layers/nm"]["scope"] == "New Mexico"
nd = "canonical.wells_latest/nd"
assert m(after, nd)["rows"] == m(before, nd)["rows"], "North Dakota moved"
assert m(after, "marts.published_map_layers/nm")["nm_wells"] == 141778
print("G2-5 pass:", m(after, "canonical.wells_latest/nm")["rows"], "NM current wells,",
      m(after, "marts.published_map_layers/nm")["nm_wells"], "NM map features")'
```

**Pass condition: New Mexico is reported under a New Mexico dataset, or it is not reported at
all. Never under North Dakota, and never as a change to North Dakota's own figure.**

`canonical.wells_latest/nm` reports **current** wells — one latest effective row per API-10, so
**142,000** (sealed), not the ~321,510 accumulated header revisions. The two are different
questions and the dataset's `grain` says which one it answers. Do not reconcile them by
subtraction.

### Record the run

Write every measured number, every `explain` output, the abort condition B decision and the
Step 3 `headers_appended` figure to `work-output/nm-tier2-run.md`. Gates write reports to disk;
both survive the session.

---

## The biggest risk, stated once

It is not a count and it is not the runtime. It is **abort condition B**: the operator name is
decided at Step 3 and cannot be repaired by re-running anything. A run that goes perfectly on
every number in this file and skips that check leaves 142,000 New Mexico wells permanently
unattributed on their cards and on the map, with no error, no refusal and no failing gate — the
promotion exits 0 and every reconciliation closes. Check it before Step 3 or accept it in
writing before Step 3. There is no after.

---

## Measured run

*(Fill in when the ops window opens. Nothing here yet: as of this file's authoring the four
production steps have not been run.)*

| step | run at | result | notes |
|---|---|---|---|
| 1 manifest | — | — | — |
| 2 staging | — | — | — |
| 3 headers and geometry | — | — | — |
| 4 tile mart | — | — | — |
| 5 gates | — | — | — |

Abort condition B decision: —

> Copyright (C) 2026 Ryan MacDonald &lt;ryan@rfxn.com&gt; &#183; All rights reserved
