# Runbook — loading Montana on the deployed host

Written for someone who has not read the plan behind it. Every command is given in full, with
the user it runs as. Nothing here needs a decision at the keyboard: where a choice exists, the
runbook makes it and says why.

**What this does.** Montana's conformance rules, staging tables and marts already exist on the
deployed database. No Montana *data* does. This loads it: two GIS archives
into `canonical.well_spatial` and `canonical.wells`, one production archive into
`staging` and `canonical.production_monthly`, then the tile marts that put it on the map.

**Time and size.** The GIS step is minutes. The production step downloads 74 MB, stages 7.4M
rows and is the long pole — budget an hour, and see [Disk](#disk-check-before-you-start) first.

---

## Layout

| | |
|---|---|
| venv | `/opt/glasswell/venv` |
| source | `/opt/glasswell/src` |
| DSN | `postgresql:///glasswell?host=/var/run/postgresql` |
| ingest runs as | `glasswell` |
| superuser work runs as | `postgres` |
| raw bytes | `/data/raw/` |

Two shell variables used throughout, set them once per session:

```bash
export DSN='postgresql:///glasswell?host=/var/run/postgresql'
export VENV=/opt/glasswell/venv
```

---

## Disk check before you start

The production archive's well member is 573 MB uncompressed. **It is never extracted** — the
parser streams from inside the zip — but staging 7.4M text rows grows the database by roughly
2 GB, and the raw zone keeps the 74 MB archive.

```bash
df -h /var/lib/postgresql /data/raw /
```

Refuse to start below **4 GB free** on the PostgreSQL data filesystem. A staging load that runs
out of space aborts its transaction and leaves nothing behind, so it is recoverable — but it
costs the download and the hour.

---

## Step 0 — confirm the schema is ready

As `postgres`:

```bash
sudo -u postgres psql -d glasswell -c \
  "select max(version) as head from public.schema_migrations"
sudo -u postgres psql -d glasswell -c \
  "select count(*) from lineage.conformance_rules where source_id like 'mt\_%'"
sudo -u postgres psql -d glasswell -c \
  "select count(*) from staging.mt_bogc_well
   union all select count(*) from staging.mt_bogc_pru
   union all select count(*) from staging.mt_gis_wells
   union all select count(*) from staging.mt_gis_well_paths"
```

Expected: head **at or above the migration that adds `marts.mt_wells_tile`** (the Montana marts
migration — the integrator renumbers it at the merge train, so check the table exists rather
than a number); **47** Montana conformance rules; four zeros.

If the head is short, apply migrations first — as `postgres`, `$VENV/bin/glasswell-migrate
--dsn "$DSN"` — and re-run this step. If the rule count is 46 rather than 47, the release
predates `cr_mt_paths_length_scope_1`; run `seed_all` (deploy step 6b) before continuing.

If any staging count is **not** zero, Montana has been loaded before. Stop and read
[Re-running](#re-running-and-how-to-undo).

---

## Step 1 — the GIS archives

Both layers, one command. This is what puts Montana on the map; the production step does not.

```bash
sudo -u glasswell $VENV/bin/glasswell-mt-gis --dsn "$DSN" --raw-root /data/raw
```

It prints one line per archive. Expected, from the 2026-08-18 artifacts:

```
Wells.zip: staged 42027, geometry 42026, headers 40626, quarantined {'unknown_status': 1400}
WellPaths.zip: staged 4173, geometry 4172, headers 0, quarantined {'parse_error': 1}
```

| Figure | Expect | Tolerance | If it differs |
|---|---|---|---|
| `Wells.zip` staged | 42,027 | ±2% | MBOGC republishes; a drift under 2% is normal growth |
| `Wells.zip` geometry | staged − 1 | exact offset | The one duplicate API-10 point `cr_mt_gis_api_identity_1` measured. A larger gap means more duplicates — record it, do not stop |
| `Wells.zip` headers | 40,626 | ±3% | Headers = staged − `unknown_status`. The two must reconcile exactly |
| `unknown_status` | 1,400 | ±20% | The six MBOGC statuses `cr_mt_gis_status_vocab_1` does not promote. A jump means a new status value — see below |
| `WellPaths.zip` staged | 4,173 | ±5% | |
| `WellPaths.zip` geometry | staged − 1 | ±3 | |

**`unknown_status` is not a failure.** A water well and a construction milestone are not
regulatory producing states; mapping them onto one would put a plugged well on the map as
producing. Those rows are in the quarantine ledger with their reason, recoverable:

```bash
sudo -u postgres psql -d glasswell -c \
  "select row_payload->>'status' as status, count(*)
     from lineage.quarantine_rows
    where reason_code = 'unknown_status' and source_id = 'mt_gis_wells'
    group by 1 order by 2 desc"
```

If a status appears here that is not one of *Water Well, Released · Completed · Unknown ·
Domestic · Other · Water Well, Completed*, MBOGC has added a value. Record it and hand it back
for a `cr_mt_gis_status_vocab_*` superseding row — do not map it at the keyboard.

Verify what landed:

```bash
sudo -u postgres psql -d glasswell -c \
  "select count(*) filter (where geom_type='surface') as surface,
          count(*) filter (where geom_type='lateral')  as paths
     from canonical.well_spatial where left(api10,2) = '25'"
sudo -u postgres psql -d glasswell -c \
  "select count(*) from canonical.wells where state_code = '25'"
sudo -u postgres psql -d glasswell -c \
  "select count(*) from canonical.wells where state_code = '25' and basin is not null"
```

Expected **42,026 / 4,172**, **40,626**, and **0**. The last one is not decoration:
`cr_mt_basin_scope_1` keeps Montana out of the type-curve peer ladder, and a non-zero answer
means something tagged it. Stop and hand it back if it is not zero.

---

## Step 2 — the production archive

The long one. Run it under `screen`, `tmux` or `systemd-run --scope`; an SSH drop mid-run
aborts the transaction and you start over.

```bash
sudo -u glasswell $VENV/bin/glasswell-mt-bogc --dsn "$DSN" --raw-root /data/raw
```

Expected, from the 2026-08-17 artifact:

```
MT_HistoricalWellProduction.tab: staged 5809608, months 488, appended <n>, quarantined {'out_of_range_date': 7, 'impossible_volume': 3}
MT_HistoricalPRUProduction.tab:  staged 1603216, months 308, appended <n>, quarantined {'impossible_volume': 2}
```

| Figure | Expect | Tolerance |
|---|---|---|
| well grain staged | 5,809,608 | ±2% |
| lease (PRU) grain staged | 1,603,216 | ±2% |
| quarantined, either grain | 12 rows total | under 100 |

Staged counts more than 2% low mean a truncated download. Check the archive's byte length
against `Content-Length` and re-run; `fetch_raw` is content-addressed, so a re-run over
identical bytes re-uses the manifest rather than re-fetching.

**A narrower run.** `--month YYYY-MM` (repeatable) promotes only the named production months.
Staging is unconditional and full either way. Use it to smoke the path before committing the
hour:

```bash
sudo -u glasswell $VENV/bin/glasswell-mt-bogc --dsn "$DSN" --raw-root /data/raw \
  --month 2026-06 --month 2026-07
```

**Liquids.** Every Montana oil figure is **oil plus condensate** — MBOGC publishes one combined
column and there is no separate condensate stream to withhold (`cr_mt_liquids_policy_1`). The
basis travels on the served figure; do not compare a Montana oil number to a state that reports
the two separately without saying so.

---

## Step 3 — the marts, which is what reaches the map

```bash
sudo -u glasswell $VENV/bin/python -m glasswell.marts.mt_wells --dsn "$DSN"
```

One JSON line:

```
{"derivation_id": "drv_...", "layers": ["mt_wells", "mt_paths"], "row_counts": {"mt_paths_tile": 4172, "mt_wells_tile": 42026}}
```

The row counts must equal the geometry counts from step 1. **Record the `derivation_id`** — it
is the handle every Montana panel figure resolves through, and `web/src/map/status.ts` carries
a measured status distribution that should be re-read at this refresh.

The neighbour mart is separate and already multi-state; refresh it so Montana geometry enters
the cross-border edges the v0.69 repair opened:

```bash
sudo -u glasswell $VENV/bin/glasswell-neighbors --dsn "$DSN"
```

This is the step with the standing risk: the supported longitude domain now covers all of
Montana, but until this load no real geometry had ever been measured in UTM 11N. If it raises
`RuntimeError` naming an unsupported zone, that is the guard working — capture the message and
hand it back rather than widening the domain.

---

## Step 4 — publish

```bash
sudo -u postgres $VENV/bin/python -c "import psycopg
from glasswell.marts.tiles import install_tile_functions
c = psycopg.connect('postgresql:///glasswell?host=/var/run/postgresql')
print(len(install_tile_functions(c)), 'tile functions'); c.commit(); c.close()"
sudo systemctl restart martin
sudo systemctl start glasswell-status.timer
```

`install_tile_functions` is create-or-replace and reads each layer's own relation, so it is safe
to run at any time. **martin refuses to start if any configured source is unresolvable**, which
is how v0.69 lost every tile layer to three empty ones — so run it before the restart, not after.

---

## Verify

```bash
curl -sf localhost:3000/catalog | grep -o 'mt_[a-z]*'
curl -sf 'http://127.0.0.1:8000/v1/wells/status-summary?bbox=-105.0,47.5,-104.0,48.2' \
  | python3 -m json.tool | head -40
```

Then in a browser: **Well paths (Montana)** appears in the layer panel's Well spine group, and
**Montana** appears under the **Wells** parent — open that row to see it. Montana is on by
default and draws mostly plugged grey over eastern Montana.

Four things to confirm by eye, each of which is a rule doing its job:

1. A Montana well card shows **no basin** and **no lateral length** — `length_method` reads
   `not_served` and `links.length_rule` points at `cr_mt_paths_length_scope_1`. A number there
   would be measured under North Dakota's rule.
2. Montana wells are **coloured by status**, unlike New Mexico's, which are all unmapped.
3. Clicking a path shows `geometry_class: map_stick` and a `vertex_count` — usually 2 or 3.
   These are cartographic centrelines, **not directional surveys**
   (`cr_mt_paths_geometry_class_1`), and nothing in the UI may imply otherwise.
4. `/status` lists **Current Montana wells** and **Published Montana map layers**.

---

## Success versus partial

**Success** — all of: 42,026 surface and 4,172 path geometries; 40,626 well headers; zero
Montana wells carrying a basin; both grains staged within 2% of the table above; both tile
marts non-empty with matching counts; martin's catalogue lists `mt_wells` and `mt_paths`; the
map draws both.

**Partial, and acceptable to leave overnight** — step 1 complete and step 2 not. Montana is on
the map with headers, statuses and geometry; it has no production. Nothing served is wrong: the
well card shows no production series and says so. Finish step 2 the next day.

**Partial, and not acceptable to leave** — step 2 complete and step 3 not. Montana is in
canonical and absent from every mart, so `/status` reports rows the map cannot show. Run step 3.

**Stop and hand back** — any of: a Montana well carrying a basin; an `unknown_status` value
outside the known six; staged counts more than 2% below the table; `glasswell-neighbors`
raising an unsupported-zone error; martin refusing to start after step 4.

---

## Re-running, and how to undo

**Re-running is safe.** Both ingests are idempotent over identical bytes: staging is guarded by
an already-staged check, geometry inserts are `on conflict do nothing`, and the mart refresh
rebuilds rather than appends. A second run adds nothing.

**Undo, in reverse order.** Raw bytes and manifests are never deleted — the raw zone is
append-only and a manifest is the evidence a fetch happened.

```bash
# 3. the marts — the map goes back to three states, nothing else changes
sudo -u postgres psql -d glasswell -c \
  "truncate marts.mt_wells_tile, marts.mt_paths_tile"

# 2. canonical — headers, geometry and production
sudo -u postgres psql -d glasswell -c \
  "delete from canonical.well_spatial where left(api10,2) = '25';
   delete from canonical.wells where state_code = '25';
   delete from canonical.production_monthly where left(api10,2) = '25'"

# 1. staging
sudo -u postgres psql -d glasswell -c \
  "truncate staging.mt_bogc_well, staging.mt_bogc_pru,
            staging.mt_gis_wells, staging.mt_gis_well_paths"
```

Then re-run `install_tile_functions` and restart martin, so the empty layers answer 204 rather
than leaving martin holding a stale catalogue.

**The lease grain is not deleted by the production statement above.** `canonical.production_monthly`
rows from the PRU grain carry a lease `entity_key` and **no api10**, so `left(api10,2) = '25'`
does not reach them. Delete them by their source instead:

```bash
sudo -u postgres psql -d glasswell -c \
  "delete from canonical.production_monthly
    where source_manifest_id in (select manifest_id from lineage.manifests
                                  where source_id = 'mt_bogc_pru_production')"
```

Getting this wrong leaves orphaned lease rows that no state filter can see — it is the one
undo step that is not symmetric with its load.

---

## Sources

All four are `https://bogfiles.dnrc.mt.gov`, pinned as constants under `cr_mt_host_pin_1`. The
listing root answers **403**, so there is nothing to scrape and no path is discovered at run
time. Where a listing *is* consulted by hand, note that the host emits **backslash** path
separators — do not paste one into a URL.

| Artifact | Path |
|---|---|
| production, both grains | `/Reporting/Production/Historical/MT_Historical_Production.zip` |
| GIS surface points | `/GISData/WellSurface/Wells.zip` |
| GIS well paths | `/GISData/WellPaths/WellPaths.zip` |

Each is registered with a 35-day poll cadence. The ingest is **not** on the timer: the archives
are large and the cadence is monthly, so it is run from this page.
