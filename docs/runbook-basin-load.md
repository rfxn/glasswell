# Runbook — loading the EIA basin and play boundaries

Two production steps against VM 111, in order, each with the numbers it must produce. Follow
this file; it does not assume you have read the plan behind it.

Every figure marked **measured** was read from a full run of the two shipped commands against
the live EIA archives into a throwaway PostGIS container on 2026-08-30. The evidence is
`work-output/real-archive-load.json`. If a step's actual differs from its expected, **stop and
reconcile before continuing** — the expectations come from the same bytes production will
fetch, so a divergence means the inputs are not the inputs.

**The two steps run as different users, and that is not cosmetic.** Step 1 runs as `glasswell`.
Step 2 runs as `postgres`. Running Step 2 as `glasswell` fails with
`InsufficientPrivilege: must be owner of function nd_laterals` — measured, not predicted. See
*Why Step 2 is postgres*.

---

## What this does

`marts.basin_boundaries_tile` is empty on the deployed host, so the `basins` and `plays` tile
layers answer **204** through the public edge. The v0.69 release shipped the tables, the tile
functions, the martin sources and both loaders; nothing ever ran them. This runbook runs them.

Afterwards the two layers serve **48 features** — 32 sedimentary basin outlines and 16 tight-oil
and shale play boundaries.

## What this does not do

- **It does not make the boundaries authoritative.** They are one publisher's interpretation at
  a stated vintage. The basin outlines are EIA's **May 2011** compilation; the play boundaries
  are **2015–2018**. `vintage_label` rides every served feature for exactly this reason. Nothing
  in these steps may be read, or allowed to imply, that the outlines are current.
- **It assigns no well to a basin.** `cr_eia_well_membership_1` registers the definition; no
  membership mart exists. `canonical.wells.basin` remains a per-source declared constant, not a
  geometric test.
- **It changes no web file.** The layers are in `TILE_LAYERS`, so the API already admits
  `/v1/tiles/basins/…` and `/v1/tiles/plays/…`; whether the map draws them, and whether it shows
  the vintage beside them, is the UX track's surface.
- **It needs no martin restart.** The tile functions were installed at deploy (step 6b2) and are
  replaced in place by Step 2. martin resolved both sources at startup, which is why the layers
  answer 204 rather than refusing to boot.

---

## Preconditions

1. **The release carrying the two console scripts is deployed.** v0.69 does not have them.

   ```bash
   ssh root@192.168.2.111 'ls -l /opt/glasswell/venv/bin/glasswell-eia-boundaries \
                                 /opt/glasswell/venv/bin/glasswell-basin-boundaries'
   ```

   Both present → use the commands as written. **Either missing → stop, or substitute the
   module form** shown under each step; both entry points are `python -m`-runnable from the same
   venv and take identical arguments.

2. **Schema head is at or past 063.**

   ```bash
   ssh root@192.168.2.111 "sudo -u postgres psql -d glasswell -tAc \
     'select max(version) from public.schema_migrations'"
   # >= 63, or run migrations first
   ```

3. **The eight `cr_eia_*` conformance rules are seeded.** The ingest reads every classing
   decision from the registry and refuses to invent one.

   ```bash
   ssh root@192.168.2.111 "sudo -u postgres psql -d glasswell -tAc \
     \"select count(*) from lineage.conformance_rules where rule_id like 'cr_eia_%'\""
   # exactly 8. Fewer -> run seed_all (deploy step 6b) before going on.
   ```

4. **A verified-fresh dump exists.** See *Rollback* — canonical is append-only, so the dump is
   the only complete undo.

   ```bash
   ssh root@192.168.2.111 'systemctl show glasswell-backup.service -p Result -p ExecMainStatus'
   #   Result=success  ExecMainStatus=0
   ssh root@192.168.2.111 'ls -la --time-style=full-iso /data/backups/pg/glasswell-*.dump | tail -3'
   #   newest < 24h old
   ```

5. **Egress to `www.eia.gov` works and `/data/raw` is writable by `glasswell`.** Both archives
   are plain anonymous HTTPS zips; neither goes through the ArcGIS host allowlist.

---

## Abort conditions

**Any one of them stops the run.**

### A — canonical already holds boundaries

```bash
ssh root@192.168.2.111 "sudo -u postgres psql -d glasswell -tAc \
  'select boundary_kind, count(*) from canonical.basin_boundaries group by 1'"
```

**Expect no rows.** If any exist, this is not the first load, and Step 1 is not an append: the
promotion is `on conflict (boundary_id) do nothing`, so a second run over the same bytes inserts
nothing and — if it owns no canonical row — quarantines the whole batch as `key_collision`
(DR-89). That is a correct ledger fact and a wasted production write. Stop and decide whether
you are re-running (use `--restage`) or recovering.

### B — `GLASSWELL_RAW_ROOT` is not set in your shell

`DEFAULT_RAW_ROOT` is the **relative** path `data/raw`. A manual ingest without the variable
writes the raw zone into whatever directory you happened to be in, and the sealed bytes end up
outside `/data/raw` with no manifest sidecar where anyone will look for it. The
`glasswell-ingest` unit supplies it; a hand-run command does not. Every Step 1 command below
sets it explicitly — do not drop it.

### C — no competing writer

```bash
ssh root@192.168.2.111 'systemctl is-active glasswell-ingest.service'   # inactive
ssh root@192.168.2.111 'pgrep -a pg_restore || echo "no restore drill running"'
```

`glasswell-restore-drill.timer` is Sundays 04:00 UTC with a 600 s jitter; avoid
**Sunday 03:45–05:00 UTC**.

---

## Step 1 — ingest both layers, as `glasswell`

Basins first, then plays, in one invocation. The order is load-bearing: a play whose `Basin`
string resolves nothing must mean the name did not resolve, never that the basin layer was
empty, and `--layer all` walks them in that order. Promoting plays first raises
`BasinLayerMissing` rather than writing false nulls.

`/etc/glasswell/code-version.env` is written by every deploy and holds
`GLASSWELL_CODE_VERSION` and `GLASSWELL_LOCKFILE_SHA256`; read them out and pass them as
`--setenv`, which is the form `scripts/deploy.sh` documents for a hand-run mart refresh.

```bash
ssh root@192.168.2.111 'set -a; . /etc/glasswell/code-version.env; set +a; \
  systemd-run --uid=glasswell --pipe --wait \
    --setenv=GLASSWELL_RAW_ROOT=/data/raw \
    --setenv=GLASSWELL_CODE_VERSION="$GLASSWELL_CODE_VERSION" \
    --setenv=GLASSWELL_LOCKFILE_SHA256="$GLASSWELL_LOCKFILE_SHA256" \
    --setenv=GLASSWELL_DSN='postgresql:///glasswell?host=/var/run/postgresql' \
    /opt/glasswell/venv/bin/glasswell-eia-boundaries \
      --layer all'
```

Without the two code-identity variables the run still succeeds, but every derivation it writes
is stamped `pkg:<version>` instead of the deployed tag, which weakens `?explain=true` for these
rows permanently — derivations are never rewritten.

Module form, if the console script is not yet deployed:

```
/opt/glasswell/venv/bin/python -m glasswell.ingest.eia_boundaries --layer all
```

It prints one JSON line per layer. **Expected, measured, exact:**

| Field | `basins` | `plays` |
|---|---|---|
| `manifest_id` | `man_02a017ccb84bdcc15726838098e3cfa7` | `man_20be8ea37727b05fc83e234a3257c069` |
| `staged_rows` | 32 | 16 |
| `promoted_rows` | 32 | 16 |
| `repaired` | 0 | 2 |
| `unlinked` | 0 | 4 |
| `quarantined.invalid_geometry` | 0 | 2 |
| every other `quarantined.*` | 0 | 0 |
| `unchanged` | false | false |

**Tolerance: none. These are exact.** The manifest id is a content address over the fetched
bytes, so a matching id proves production pulled byte-identical archives to the ones these
numbers came from. **A different manifest id means EIA republished** — every row count below is
then unverified, and you should stop and re-measure rather than accept a near miss.

The `repaired: 2` and `invalid_geometry: 2` are the Bakken and Three Forks play boundaries. Both
ship with a ring self-intersection; both are repaired at promotion by
`ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3))`, written to the quarantine ledger with
`ST_IsValidReason` as evidence, and then **released** under `cr_eia_geometry_repair_1`. A
released reject is the intended end state, not a leak.

The `unlinked: 4` are the four Niobrara rows whose `Basin` string the publisher's own basin file
does not carry: `Denver Basin`, `Park Basin`, `Piceance Basin`, `North-Central MT`. The link is
a case-folded exact name match with no suffix stripping and no fuzzy distance
(`cr_eia_basin_link_1`); four unresolved links are the registered, correct outcome, not a
partial load.

---

## Step 2 — refresh the tile mart, as `postgres`

```bash
ssh root@192.168.2.111 'set -a; . /etc/glasswell/code-version.env; set +a; \
  systemd-run --uid=postgres --pipe --wait \
    --setenv=GLASSWELL_CODE_VERSION="$GLASSWELL_CODE_VERSION" \
    --setenv=GLASSWELL_LOCKFILE_SHA256="$GLASSWELL_LOCKFILE_SHA256" \
    --setenv=GLASSWELL_DSN='postgresql:///glasswell?host=/var/run/postgresql' \
    /opt/glasswell/venv/bin/glasswell-basin-boundaries'
```

Module form: `/opt/glasswell/venv/bin/python -m glasswell.marts.basin_boundaries`

One JSON line. **Expected:**

```json
{"derivation_id": "drv_…", "layers": ["basins", "plays"],
 "row_counts": {"basin_boundaries_tile": 48}}
```

`row_counts.basin_boundaries_tile` must be **48**, exactly. The `derivation_id` will **not**
match the one measured locally and must not be compared to it: the content address includes
`code_version` and `env_id`, which differ between the deployed release and a workstation. It
must simply be present and non-empty — it is the handle `?explain=true` resolves.

### Why Step 2 is postgres

`refresh_basin_boundaries` calls `install_tile_functions`, which issues `create or replace
function` for **every** layer in `TILE_LAYERS`, not only the two it is refreshing. `create or
replace` on a function you do not own is refused, and the login role `glasswell` is a member of
`glasswell_pipeline` and `glasswell_api` but owns nothing it did not itself create.

Which role owns the deployed tile functions depends on which one first created each of them on
this host, and the tree says both: `scripts/deploy.sh` step 6b2 installs them as `postgres`,
while `infra/README.md` step 4 shows the same call under `--uid=glasswell`. **You do not need to
resolve that to run this runbook.** `postgres` is a superuser, so it can replace the functions
whichever role owns them — it is the unconditional choice, which is why Step 2 names it.

Measured, against a database whose tile functions were installed by a different role first:

| Run as | Step 1 ingest | Step 2 mart refresh |
|---|---|---|
| pipeline role (`glasswell` equivalent) | exit 0 | **exit 1** — `must be owner of function nd_laterals` |
| owner / superuser (`postgres` equivalent) | — | exit 0 |

The failure names `nd_laterals` because that is simply the first layer in the tuple. It is not
an ND problem; any layer would do. If Step 2 *does* succeed as `glasswell` on this host, that
tells you the functions are glasswell-owned there — it does not make running it as `glasswell`
the supported form.

---

## Verification

Run all four. **All four must pass before you call this done.**

```bash
# 1. canonical: 32 basins, 16 plays
sudo -u postgres psql -d glasswell -tAc \
  'select boundary_kind, count(*) from canonical.basin_boundaries group by 1 order by 1'
#   basin|32
#   play|16

# 2. the mart, and the three published relations agreeing
sudo -u postgres psql -d glasswell -tAc \
  'select (select count(*) from marts.basin_boundaries_tile),
          (select count(*) from marts.tile_basins),
          (select count(*) from marts.tile_plays)'
#   48|32|16

# 3. no naked numbers: every served row carries its derivation handle
sudo -u postgres psql -d glasswell -tAc \
  'select count(*) from marts.basin_boundaries_tile where derivation_id is null'
#   0

# 4. the repair is a released reject, not a silent edit nor an open one
sudo -u postgres psql -d glasswell -tAc \
  "select reason_code, state, count(*) from lineage.quarantine_rows
    where source_id in ('eia_sedimentary_basins','eia_shale_plays')
    group by 1,2 order by 1,2"
#   invalid_geometry|released|2
```

Then the wire, which is the only check that proves a reader sees anything:

```bash
curl -sf -o /dev/null -w '%{http_code} %{size_download}\n' \
  -H "X-Glasswell-Key: $owner_key" "$API/v1/tiles/plays/6/13/22.pbf"
#   200, ~2011 bytes.  204 means Step 2 did not land.
curl -sf -o /dev/null -w '%{http_code} %{size_download}\n' \
  -H "X-Glasswell-Key: $owner_key" "$API/v1/tiles/basins/6/13/22.pbf"
#   200, ~1410 bytes.
```

Tile `6/13/22` covers the Williston. Decoded locally from the mart, it carries — measured — a
`plays` sublayer of 3 features plus 2 label anchors, whose string pool contains `Bakken`,
`Three Forks` and `Niobrara`, and a `basins` sublayer of 2 features plus 1 label anchor carrying
`WILLISTON` and `POWDER RIVER`. Byte sizes will differ slightly under a different derivation id;
the status code is the assertion, the size is a sanity range.

### Telling success from partial

| Symptom | What happened | What to do |
|---|---|---|
| Step 1 printed one JSON line, not two | plays never ran | re-run Step 1; basins is idempotent and will report `unchanged: true` |
| `BasinLayerMissing` raised | plays promoted against an empty basin layer | run `--layer basins` first, then `--layer plays` |
| `promoted_rows: 0` with `unchanged: false` | every `boundary_id` collided | abort condition A was missed; canonical already held this layer |
| `unchanged: true` on a first run | the bytes were already sealed under this manifest | fine; add `--restage` to re-parse and re-promote from the stored bytes |
| Step 2 reports 48 but tiles still 204 | the API cached, or you probed a tile with no feature | probe `6/13/22`; check `marts.tile_plays` count directly |
| `LookupError: rule cr_eia_… is not seeded` | precondition 3 was missed | run `seed_all`, then re-run |
| `InsufficientPrivilege: must be owner of function` | Step 2 ran as `glasswell` | re-run Step 2 as `postgres`; nothing was written |

A **partial** load is any state where canonical holds basins but not plays, or holds both but
`marts.basin_boundaries_tile` is not 48. Both are recoverable by re-running the step that did
not finish — Step 1 is conflict-safe and Step 2 rebuilds rather than appends.

---

## Rollback

**Take the reversible step first.** The mart is rebuilt, never appended, so emptying it returns
the two layers to exactly the state they are in today — configured, resolvable by martin,
answering 204:

```bash
sudo -u postgres psql -d glasswell -c 'truncate marts.basin_boundaries_tile'
```

That is the whole undo for anything a reader can see. No martin restart, no deploy.

**Canonical cannot be rolled back in place.** `canonical.basin_boundaries` carries a
`basin_boundaries_append_only` trigger firing `lineage.reject_mutation()` on update and delete,
and `update, delete` are revoked from both `glasswell_pipeline` and `glasswell_api`. Deleting the
48 rows means disabling that trigger as the superuser, which defeats the guarantee the trigger
exists to make. **Do not do it as a cleanup.** If canonical genuinely must be returned to empty,
restore from the precondition-4 dump — that is why it is a precondition rather than a courtesy.

Raw bytes under `/data/raw` are never edited or removed as part of a rollback. They are the
evidence that the fetch happened, and re-running Step 1 against them with `--restage` is the
supported way to re-derive.

---

## Risks

- **The vintages are old and the map will not say so on its own.** 2011 basins, 2015–2018 plays.
  They are the current published EIA product — there is nothing newer to fetch — but a crisp
  outline next to 2026 production reads as current to anyone who does not check.
  `vintage_label` is on every served feature so the UI *can* say so; nothing in these two steps
  forces it to. Until the UX track surfaces it, this load makes an undated boundary visible.
- **The four unresolved links are invisible to a map reader.** A null parent reads as "no data"
  rather than "the publisher's two files disagree about a basin's name". `/conformance` carries
  the reasoning; the tile does not.
- **Boundaries are served overlapping, deliberately.** Six Permian plays share ground because
  they are stacked intervals, and Bakken and Three Forks sit over nearly the same footprint.
  Nothing is dissolved, clipped or given a precedence order (`cr_eia_boundary_overlap_1`). A
  reader who expects a partition of the map will read overlap as duplication.
- **Step 1 reaches the public internet from the production host.** It is the only step here that
  does. If egress is filtered, it fails at fetch and writes nothing.
