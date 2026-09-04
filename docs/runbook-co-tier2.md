# Runbook — Colorado, the fifth jurisdiction's first load

Colorado is registered by the migration and the seed. This runbook is the **data** load that
follows: three GIS archives, one rolling production file, two promotions and a tile mart. It is
written for the first load on a host where none of it has run before.

**Read this first, because it changes what you do.** The scheduler does not run these jobs.
Every Colorado row resolves `launch_mode = 'observe'`, so an hourly tick computes the dependency
order, records what it would have run, and starts nothing; `launch` is the launch-flip track's
own act and no jurisdiction registers it for itself. The commands below are therefore the load,
not a way of watching one. `glasswell-scheduler --run --force` is the manual path and ignores
the posture entirely, which is what you use to drive one job under supervision.

## What this does, and what it deliberately does not

| | in scope | out of scope |
|---|---|---|
| production | the rolling `monthly_prod.csv` | the 1999-2025 archives, 2.49 GB and roughly 17.4M rows: **their own dispatch**, on the owner's ruling |
| geometry | the surface point layer | the bottom-hole and lateral archives, which stage and stop, because `cr_co_wells_geometry_scope_1` records that they cover 37,482 of 124,392 wells |
| status | resolved at read time through `canonical.status_resolution` | writing a class into `canonical.wells`, which would invent a valid time ECMC never filed |
| inventory | nothing | Colorado is a **registered refusal** under `cr_co_inventory_not_served_1`: no PLSS grid, no spacing-unit source, no support score, and Protocol 4D admits no slot without them |

### Where the numbers in this runbook come from

Every figure below was measured against the live ECMC files on 2026-09-02, and each file's byte
count matched the `content-length` its host served. They are what to expect, not what to accept:
a load that lands a different number is a finding, and the check that catches it says so.

| measured | value |
|---|---|
| header features / distinct API-10 | 124,410 / 124,392 |
| byte-identical duplicate rows | 18, fourteen `PR` and four `SI` |
| directional wellbores / wells covered | 39,049 each file / 37,482 |
| rolling production rows / distinct API-10 | 387,813 / 44,358 |
| points filed as permit locations | 55,570, which is 44.67% |

## Preconditions

```bash
# The registration resolves, and its rules are resident.
sudo -u postgres psql -d glasswell -Atc \
  "select identity_prefix, liquids_basis, wells_tile_layer_id
     from lineage.jurisdictions_as_of(current_date, current_date)
    where jurisdiction_code = 'CO'"
# one row, or STOP: migrate and seed first. A registration dated ahead of this host's today
# resolves nowhere, and Colorado would draw unmapped with every query below still passing.

sudo -u postgres psql -d glasswell -Atc \
  "select count(*) from lineage.conformance_rules where rule_id like 'cr_co_%'"
# 16, or STOP: run seed_all. lineage.conformance_rules is append-only and the seeder is
# idempotent for insert-only rows, so re-running it is safe.

sudo -u postgres psql -d glasswell -Atc \
  "select count(*) from lineage.co_facility_status_map"
# 13. Fewer is a half-applied migration, not a partial codebook.
```

**Memory.** Every Colorado job row sets `MemoryMax=6G` (`co_counts` 2G), which is the platform
norm rather than a Colorado figure. The host carries 16 GB with about 10.5 GB available and the
scheduler holds concurrency at 1, so one job at a time fits with room to spare. Hand-running a
step below while something else is resident is the case to watch: these steps are not run under
the scheduler and nothing bounds them to that envelope.

## Step 0 — baseline

Capture what the four resident jurisdictions hold **before** anything runs. The whole point of
the gates at the end is the diff against this.

```bash
mkdir -p ~/co-load && cd ~/co-load
sudo -u postgres psql -d glasswell -Atc \
  "select state_code, count(*) from canonical.wells_latest group by 1 order by 1" \
  | tee wells-by-state.before.txt
sudo -u postgres psql -d glasswell -Atc \
  "select state_code, count(*) from marts.well_cumulatives group by 1 order by 1" \
  | tee cumulatives-by-state.before.txt
sudo -u postgres psql -d glasswell -Atc \
  "select count(*) from marts.co_wells_tile" | tee co-tile-rows.before.txt
```

`co-tile-rows.before.txt` reads `0`. The wells file carries no `05` line.

## Step 1 — stage the three GIS archives

```bash
sudo -u glasswell GLASSWELL_DSN="$GLASSWELL_DSN" \
  /opt/glasswell/venv/bin/python -m glasswell.ingest.co_ecmc_gis --layer all
```

One pass, three manifests, because ECMC republishes all three within seconds of each other.
Staging is the terminus: the module can name no `canonical` relation, and a test asserts it.

```sql
select count(*) from staging.co_ecmc_wells;              -- 124,410
select count(*) from staging.co_ecmc_directional_bh;     -- 39,049
select count(*) from staging.co_ecmc_directional_lines;  -- 39,049
```

A refusal naming an EPSG code is the datum guard, not a transient: `cr_co_wells_datum_1` records
the code the archives ship, and a re-projected archive stops the load rather than being
re-plotted. Route it; do not re-fetch to repair it.

## Step 2 — stage the rolling production file

```bash
sudo -u glasswell GLASSWELL_DSN="$GLASSWELL_DSN" \
  /opt/glasswell/venv/bin/python -m glasswell.ingest.co_ecmc_production --file rolling
```

`--file all` exists and would pull twenty-seven archives. **Do not**, on this runbook. The
backfill is its own dispatch with its own baseline, and one of those files spells three columns
differently, which is registered but not exercised here.

```sql
select count(*) from staging.co_ecmc_production;  -- 387,813
```

A refusal naming a column is `cr_co_production_schema_drift_1` doing its job: ECMC published a
column this parse does not know, and the answer is to register the spelling, never to widen the
parse in place.

## Step 3 — promote the headers

```bash
sudo -u glasswell GLASSWELL_DSN="$GLASSWELL_DSN" /opt/glasswell/venv/bin/glasswell-co-wells
```

Expect `wells_appended: 124392`, and **exactly 18** quarantined `duplicate_row`. Any other
duplicate count means the archive changed shape; that is a finding and the load stops on it.

## Step 4 — promote the production

```bash
sudo -u glasswell GLASSWELL_DSN="$GLASSWELL_DSN" /opt/glasswell/venv/bin/glasswell-co-production
```

Two shapes land, and the second is what makes a well's chart render at all: one row per
completion, plus one row per well-month and stream carrying their exact sum, disclosed as
`aggregation = 'sum_over_pools'`. A month with one completion promotes as the well and carries
no aggregation, because relabelling it would signal a restatement that did not happen.

## Step 5 — the mart and the counts

```bash
sudo -u glasswell GLASSWELL_DSN="$GLASSWELL_DSN" \
  /opt/glasswell/venv/bin/glasswell-tiles --jurisdiction CO
sudo -u glasswell GLASSWELL_DSN="$GLASSWELL_DSN" \
  /opt/glasswell/venv/bin/python -m glasswell.marts.counts
```

One engine, one entry point. There is no `glasswell-co-tiles` and there is no
`marts/co_wells.py`: the jurisdiction is an argument and the profile it names is a row.

## Step 6 — verification gates

Four gates. **G-2 is the merge blocker.** A red gate stops the track; none is weakened to let
the next thing start.

### G-1 — Colorado's own numbers

| check | expected |
|---|---|
| `select count(*) from canonical.wells_latest where state_code = '05'` | 124,392 |
| `select count(*) from marts.co_wells_tile` | 124,392 |
| `select count(*) from lineage.quarantine_rows where reason_code = 'duplicate_row'` | 18 |
| `select count(distinct status_canonical) from marts.co_wells_tile` | 9 |
| `select count(*) from marts.co_wells_tile where loc_qual_class = 'planned'` | 55,570 |

Nine classes and not eleven is correct: `confidential` and `dry` receive no Colorado wells,
which is a fact about ECMC's vocabulary rather than a gap in the load.

### G-2 — the four resident jurisdictions are untouched. MERGE BLOCKER

```bash
sudo -u postgres psql -d glasswell -Atc \
  "select state_code, count(*) from canonical.wells_latest group by 1 order by 1" \
  | tee wells-by-state.after.txt
diff <(grep -v '^05' wells-by-state.after.txt) wells-by-state.before.txt
```

Empty, over **all five** states: the `05` line is new and every other line is byte-identical.
North Dakota, Texas, New Mexico and Montana unchanged is the pass, not an oversight — it is the
proof that a fifth jurisdiction is a registration and not a rewrite. A moved line on any of the
four is a hard stop, whatever the load's own numbers say.

One number does move by design, and it is not in this diff: `marts.well_cumulatives` is
rebuilt over a wider population, so its derivation address changes from `states 33` to
`states 05,33`. North Dakota's own totals are unchanged; the identity moves because a figure
built over a different population is a different figure. Check the totals, not the id:

```sql
select state_code, count(*), sum(cum_volume) filter (where stream = 'liquid')
  from marts.well_cumulatives group by 1 order by 1;
```

### G-3 — the status class comes from the resolver

```sql
select count(*) from canonical.wells where state_code = '05' and status_canonical is not null;
```

**Zero.** A non-zero here means something wrote a class at promotion, which is the failure
`cr_co_wells_status_vocab_1` exists to prevent. The class the map draws comes from
`canonical.status_resolution`, and G-1's nine-class count is what proves it arrives.

### G-4 — the map and the card

```bash
curl -fsS "$BASE/v1/tiles/co_wells/8/54/97.pbf" -o /dev/null && echo tile-ok
curl -fsS "$BASE/v1/jurisdictions" | jq -r '.data[] | select(.jurisdiction_code=="CO")
  | [.well_count, .measured_on] | @tsv'
```

A well count with a `measured_on` beside it means `marts.counts` ran. A null count is not a
failure of this runbook: it is the honest state of a registration nothing has measured yet, and
Step 5's second command is what closes it.

## Rollback

Every table this runbook writes is append-only, so there is no undo and none is wanted. To take
Colorado off the map without touching a row, restate the registration with a null
`wells_tile_layer_id` at a later `published_at`; the layer disappears and the history of why is
still readable. Deleting rows to hide a bad load destroys the evidence of the bad load.
