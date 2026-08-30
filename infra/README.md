# infra — what runs where

Config-as-code for the glasswell host, per SB-06 §9. This directory is authoritative; the
copies under `/etc` on the VM are placed by `install.sh` and are not edited in place.

## The host

| | |
|---|---|
| Host | `glasswell.lab.rpx.sh` → **192.168.2.111**, Proxmox VM 111 on forge |
| OS | Ubuntu 24.04.4 LTS, Python 3.12.3, Node 18.19.1 |
| Exposure | LAN only. `ufw` default-deny with 22, 80 and 443 open to `192.168.2.0/24`; the API has no TCP listener at all — Caddy reaches it over `/run/glasswell/api.sock` (DIR-13) |
| Deploy root | `/opt/glasswell` — `venv/`, `src/` (rsynced repo), `web/` (built frontend) |
| Bulk volume | `/data` (1007 G): `raw/`, `staging/`, `scratch/`, `parquet/`, `backups/`, `basemap/` |

**SB-06 §4.5 and §11 say `192.168.2.61`. That is stale** — the DNS A record, forge's
restricted `authorized_keys` `from=` clause and every probe in this repo use `.111`.

## Units

| Unit | Runs as | Does |
|---|---|---|
| `caddy.service` | `caddy` | TLS front door: `https://glasswell.lab.rpx.sh` → `unix//run/glasswell/api.sock`, certificate from Let's Encrypt over Cloudflare DNS-01. Config `caddy/Caddyfile`, binary and token are host state — see `caddy/README.md` |
| `glasswell-api.service` | `glasswell` | `uvicorn glasswell.api:app --uds /run/glasswell/api.sock --workers 2 --proxy-headers` — serves `/v1`, the `/v1/tiles` proxy, and the built frontend at `/`, behind Caddy. The socket, not a port: see "Why the API has no port" below |
| `glasswell-status.service` + `.timer` | `glasswell` | Builds `/var/lib/glasswell/status.json` shortly after boot and every 15 minutes for the keyed `/v1/status` surface. The timer is always enabled by `install.sh`; status visibility is a serving prerequisite, not an optional pipeline schedule |
| `glasswell-lineage-retention.service` + `.timer` | `glasswell` | Nightly removal of successful, unreferenced `ephemeral` derivations older than 90 days. Failed, permanent, recent, and referenced derivations remain. The timer is always enabled and is shown on Status |
| `glasswell-ingest.service` + `.timer` | `glasswell` | Monthly ND pull: GIS layers, one production month, tile marts. Installed **disabled**; `install.sh --enable-ingest` arms it |
| `glasswell-c115b.service` + `.timer` | `glasswell` | Monthly NM C-115B natural-gas-waste capture, staging terminus. The 12th, `Persistent=true`: `reporting_period` is a rolling ~13-month window and a month that rolls out is unrecoverable from the endpoint. Installed **disabled**; `install.sh --enable-c115b` arms it |
| `glasswell-alert@.service` | `glasswell` | `OnFailure=` target: logs to the journal and appends to `/var/lib/glasswell/health-events` |
| `glasswell-backup.service` + `.timer` | `root` | Nightly custom-format `pg_dump`, globals and strict sidecar manifest plus an rsync of the dump and raw zones to forge, via `/usr/local/sbin/glasswell-backup.sh`. Dump and manifest counts share one exported repeatable-read snapshot. Installed **disabled**; `install.sh --enable-backup` arms it. **VM 111 has it enabled already** |
| `glasswell-restore-drill.service` + `.timer` | `root:glasswell` | Weekly same-cluster logical restore of the newest private dump into a unique scratch database. It verifies archive identity, schema version, critical counts, representative reads and scratch cleanup, then atomically publishes `/var/lib/glasswell-restore-drill/result.json` from a dedicated root-owned, Status-readable state directory. It follows backup enablement and is not full VM/raw-zone disaster recovery |
| `martin.service` | `martin` | **Pre-existing, not owned by this directory** — configured through a drop-in. Runs with `auto_publish` on until runbook step 9, so its catalogue is every relation with a geometry column, `staging` and `canonical` included, on `127.0.0.1:3000`. Adopting `martin/config.yaml` cuts it to the ten published layers; the `martin` role created by migration 026, which holds select on the ten `marts.tile_*` views granted across 026–035 and nothing else, is what makes the rest unreachable either way |
| `postgresql@16-main` | `postgres` | Distro unit. `listen_addresses = 'localhost'`, socket peer auth |

`backup/glasswell-backup.sh` and `backup/glasswell-restore-drill.sh` are placed in
`/usr/local/sbin` by `install.sh`. Only the backup script's off-box rsync needs
`/root/.ssh/id_glasswell_backup` and a matching `authorized_keys` entry on forge; the restore
drill reads the local logical backup. `install.sh` does not create that key. The forge-side
vzdump job is provisioning-owned and is not in this directory.

### Status snapshot

`glasswell-status.service` runs
`/opt/glasswell/venv/bin/python -m glasswell.status.collector` as `glasswell`. It loads only the
database and deploy-stamped code-version environments; the owner key and application paths do
not enter the collector process. PostgreSQL inventory runs in one repeatable-read, read-only
snapshot. The oneshot has a two-minute runtime ceiling, no capabilities, strict filesystem
protection, and only `/var/lib/glasswell` writable.

The collector atomically replaces `/var/lib/glasswell/status.json`. Its `0027` umask and the
state-directory contract keep the file at `glasswell:glasswell` with mode `0600` or `0640`.
The snapshot is sanitized product data: it must not contain credentials, DSNs, configured
filesystem roots, or internal service URLs. `verify.sh` parses it without printing its values,
checks those private environment values are absent, and then proves the keyed `/v1/status`
route serves it. A collector or timer failure invokes `glasswell-alert@.service`.

## The TLS front door (DIR-13)

Caddy is in, which re-converges with SB-06 §4.5 and closes P7's C12 ("no Caddy, no TLS"):
uvicorn binds `/run/glasswell/api.sock`, Caddy terminates `https://glasswell.lab.rpx.sh` on
`:443`, redirects `:80`, and the LAN reaches the app through the name with no port and no
certificate warning. Still no tunnel and no Access — that is the next step, and it points a
`cloudflared` at the same origin.

`caddy/README.md` carries the three decisions worth arguing about: why the binary is a
download.caddyserver.com custom build rather than the distro package or an xcaddy build, why
neither compression nor security headers are configured at the edge (the origin owns both,
and a second `header` would append rather than replace), and how renewal is watched.

### Why the API has no port

The hop was `127.0.0.1:8000` and cost **~40 ms on every proxied response under 64 KB**.
`uvicorn --workers 2` builds its listener as `socket.socket(family=family)`, leaving `proto`
at `0`; `asyncio.base_events._set_nodelay` only sets `TCP_NODELAY` when `proto` is
`IPPROTO_TCP`, so it never fired, and uvicorn writes headers and body as two `transport.write`
calls. On loopback the MSS is 65,483, so every smaller body was a Nagle-held segment waiting
on the peer's delayed ACK. The root-cause `tcpdump` is in
`work-output/tileperf-r2-status.md` §1.

AF_UNIX has no Nagle, so moving the hop to a socket removes the defect rather than tuning
around it. Three consequences worth knowing:

- **`--forwarded-allow-ips` must be `*`.** A unix peer has no address, so uvicorn leaves
  `scope["client"]` as `None` and a numeric allow-list stops trusting `X-Forwarded-Proto` —
  which would silently drop `upgrade-insecure-requests` from every CSP. `*` is safe here
  because the socket has exactly one reachable peer.
- **The directory is the access control.** uvicorn chmods the socket `0666` and offers no
  knob for it, so `/run/glasswell` at `0750 glasswell caddy` is what keeps everyone else out.
  It is created by `tmpfiles.d/glasswell.conf`, **not** by `RuntimeDirectory=`: systemd
  re-applies exec-directory ownership on every exec invocation, so a `chgrp` from
  `ExecStartPre` is reverted before `ExecStart` runs and Caddy 502s. Verified on the host —
  `caddy` can connect, `martin` gets `EACCES`.
- **The stale socket is removed explicitly.** `RuntimeDirectory=` used to guarantee a clean
  path by deleting the directory on stop. A tmpfiles directory persists, and uvicorn's
  `bind()` returns `EADDRINUSE` on an existing path and exits, so `ExecStartPre=rm -f` is
  load-bearing: without it one `SIGKILL` wedges every subsequent start.
- **`ufw`'s 8000 rule is now irrelevant to the API.** Caddy still binds `192.168.2.111:8000`
  for the courtesy redirect to `https://`; that block is Caddy's and is unaffected.

`tests/unit/test_api_socket_contract.py` holds the unit file, the Caddyfile and `verify.sh`
to the same socket path, because a disagreement between any two of them is a 502 that each
file passes its own reading of.

## Two decisions that differ from SB-06

**No `glasswell-martin.service`.** `martin.service` already exists, is enabled, runs as user
`martin` and reads `/etc/glasswell/db.env`. martin binds `127.0.0.1:3000`, so no firewall
rule belongs in front of it — the `3000/tcp` LAN allow the infra pass added is inert today
and becomes a real exposure the moment the bind address changes. Removing it from the live
VM is a deployer step (see "Deploy runbook"). A second unit cannot bind `:3000`. martin reads
its source catalogue at startup, so a **restart** is required after `marts.refresh_all` first
creates the `marts.nd_*(z, x, y, query)` functions — that is a catalogue refresh, not a
reconfiguration. `infra/martin/config.yaml` is the documented target and adopting it is runbook step 9:
it turns auto-publish off, which is what stops the tile server publishing `staging` and
`canonical` relations. It declares the same ten function sources auto-publish would have
found, so the ids do not move; what it must not carry is a second `tables:` block naming the
views those functions read, which would collide on the same ids. It needs the PG role
`martin` that migration 026 creates — its DSN peer-authenticates as the unit's OS user.

**`/data`, not `/srv/glasswell`.** The 1 TB volume is mounted at `/data`; `/srv/glasswell` is
an empty directory on the 145 GB root disk. Every path in these units follows the mount that
exists. SB-07 §2.3's three zones are therefore `/data/raw`, `/data/staging` and
`/data/scratch` (DR-06); `install.sh` creates the last two and `verify.sh` asserts all
three.

## Roles and the separation that is not enforced tonight

Migration 001 creates `glasswell_pipeline` and `glasswell_api` as `nologin` group roles, and
the login role `glasswell` is granted **both**. That collapses the pipeline/API separation
SB-07 §11 asks for: the API's connection could write canonical rows. Real separation needs
two login identities, which needs a second OS user or a `pg_ident` map. **Known gap**, not a
guarantee — see SMOKE.md §5.

Migrations run as the `postgres` superuser over the socket, because migration 001 executes
`create role` and `glasswell` has neither `CREATEROLE` nor `SUPERUSER`:

```bash
sudo -u postgres /opt/glasswell/venv/bin/glasswell-migrate \
    --dsn "postgresql:///glasswell?host=/var/run/postgresql"
```

`marts.refresh_all` issues `create or replace function` and `create or replace view` in
schema `marts`, so `glasswell_pipeline` needs `create` there. Migration 009 grants only
`usage`; the privilege was applied by hand on this host during P7 and is now held by a
migration (DR-21), which is what makes a rebuild on a fresh database possible.

`GLASSWELL_RAW_ROOT=/data/raw` has to be exported for **manual** ingest commands. The
`glasswell-ingest` unit supplies it, so the runbook in `fix-data-truth-status.md` omits it
and a hand-run fetch would otherwise write the raw zone to a relative `data/raw`.

## Postgres tuning

`postgres/postgresql.conf.d/glasswell.conf` is sized for VM 111 as it runs: **8 vCPU,
16 GiB resident, PGDATA on the ssd-pool, no swap**. It still sets no `listen_addresses` —
the running value is `localhost` and martin reaches PostgreSQL over loopback TCP, so
SB-06 §1.3's `''` would take tiles down. `install.sh` places it only under
`--with-postgres`, because applying it needs a PostgreSQL restart and martin holds live
connections.

### What is actually on the host

**The previous nine-setting sizing was applied on 2026-08-20; this file's claim that it was
not is what went stale.** `postgresql@16-main` was restarted at 15:25:57 that day to apply
it, with the terminated connections in its log, and an independent gate read
`shared_buffers = 262144 × 8 kB = 2 GB` back off the running server the same afternoon.
A 2026-08-23 measurement confirms five of the nine live. Runbook step 6 was done in the
same window. The stale sentence outlived the fact by eight days because the deploy note
that recorded it said "`infra/README.md` next time that file is touched" and nobody
touched it.

The three records behind that paragraph are internal deploy and gate reports under
`work-output/`, which is git-excluded and so is not resolvable from a repository checkout.
Anyone re-deriving this from the host should re-run the Measure section rather than take
the paragraph on trust.

Two things nobody has established, so this file no longer asserts them. **No verbatim
`postgres tuning` block output exists anywhere** — every recorded `verify.sh` run is a
summary count — and `superuser_reserved_connections`, `full_page_writes`, `random_page_cost`
and `effective_io_concurrency` have never been read back from the host. **The revision below
is not applied**; the block is red until step 5 runs again.

### Why the sizing basis moved

**The old basis was half right.** SB-06 §2.3 says "size PostgreSQL against the floor, not
the ceiling", and for *allocations* that still holds: the balloon reclaims page cache and
free memory, never the shared-memory segment. It does not hold for *planner hints*, which
allocate nothing — sizing `effective_cache_size` against 8 GiB bought no safety and cost
index-scan plans on tables that have since grown 18×. This revision splits the two.
Allocations are sized so the process survives a squeeze to the 8 GiB floor; planner hints
are sized against the 16 GiB the guest actually has. The one measurement on record shows
`15991 MB total` with the balloon never observed inflated, and SB-06 §11 already names
`shared_buffers = 4GB` as the 16 GiB answer.

**The mitigation SB-06 paired with the floor was never built.** §2.3 asks for a 4 GiB
swapfile so balloon pressure becomes slowdown rather than an OOM kill. The host has
`Swap: 0`, confirmed twice. Create it before applying this revision — it is what makes the
16 GiB basis safe, and step 5 starts with it.

### The settings

| setting | was | now | why |
|---|---|---|---|
| `shared_buffers` | 2GB | **4GB** | 25 % of the 16 GiB the guest holds. At 2GB it was 12.5 % of real RAM, not the 25 % SB-06 intended |
| `effective_cache_size` | 6GB | **12GB** | A planner hint that allocates nothing. 75 % of 16 GiB. `canonical.production_monthly` alone projects to ~12 GB post-NM, so under-reporting cache pushes the planner off its indexes |
| `maintenance_work_mem` | 512MB | **1GB** | `marts/neighbors.py` builds a GiST index plus a PK and a btree on temp tables each refresh. 1GB is the ceiling worth buying — PG16 caps VACUUM's dead-tuple array at 1GB regardless |
| `autovacuum_work_mem` | −1 | **256MB** | Decouples autovacuum from the line above. At −1 it inherits `maintenance_work_mem`, so raising that to 1GB would have taken the recorded 1.5 GB autovacuum burst to 3 GB; 256MB **cuts** it to 0.75 GB |
| `work_mem` | 32MB | **64MB** | The z ≤ 7 overplot thinning in `marts/tiles.py` sorts every feature in the envelope with an md5 per row; on `tx_wells` that is ~150–360 k rows, which spills at 32MB on the hottest tiles. Arithmetic below |
| `temp_buffers` | 8MB | **64MB** | Temp *tables*, not sort spill: `neighbors.py` holds three `on commit drop` tables and `nm_ocd.py` COPYs ~127 k rows/month into one. Only backends that use them pay it |
| `max_connections` | 60 | **80** | There is no pool — one connection per request, plus a second during auth. Twelve tile-proxy requests from one map pan take 12–24, and martin's pool takes 10 of the 57 usable. 80 moves the crossing point without making the cap useless |
| `wal_buffers` | −1 (→16MB) | **64MB** | The auto-cap is 16MB. NM's promotion is 89 minutes at 10.6 % CPU — "the rest is Postgres writing" |
| `min_wal_size` / `max_wal_size` | 80MB / 1GB | **1GB / 4GB** | 17.6 M rows × (~335 B heap + 6 index entries) ≈ 12 GB of relation data against a 1GB checkpoint trigger, re-arming full-page writes on six indexes each time |
| `checkpoint_timeout` | 5min | **15min** | A page's full-page image is written once per checkpoint cycle, so tripling the cycle is a bigger WAL-volume lever than `max_wal_size`. Costs crash-recovery time, covered by nightly dump and weekly restore drill |
| `default_statistics_target` | 100 | **200** | Heavy skew on `state_code` (42 vs 33), `api10` prefixes and `formation`, over a table going to ~24.8 M rows. Needs an `ANALYZE` to take effect |
| `max_parallel_workers_per_gather` | 2 | **4** | Four workers plus the leader is exactly blueprint C26's five-of-eight-vCPU cap for batch work. `max_parallel_workers` stays at its default 8, which is what bounds the total |
| `max_parallel_maintenance_workers` | 2 | **4** | Index builds in the mart refresh and the weekly restore drill. Costs no extra memory — `maintenance_work_mem` is divided among leader and workers, not multiplied |
| `autovacuum_vacuum_scale_factor` | 0.2 | **0.05** | For `marts.*_tile`, which `DELETE` and re-`INSERT` a whole generation every refresh |
| `autovacuum_vacuum_insert_scale_factor` | 0.2 | **0.05** | The one that matters for `canonical.*`: `lineage.reject_mutation()` makes UPDATE and DELETE impossible there, so the risk is insert-driven freezing and visibility-map staleness, not bloat |
| `autovacuum_analyze_scale_factor` | 0.1 | **0.02** | 10 % of 24.8 M rows is 2.5 M inserts before re-analyze — plans go stale mid-load, exactly when the table grows fastest |
| `autovacuum_vacuum_cost_limit` | −1 (→200) | **1000** | The default throttles to a few MB/s on an SSD. The limit is *divided* among workers, so raising it is the lever; raising `autovacuum_max_workers` without it gains nothing, and it is left alone |
| `superuser_reserved_connections`, `full_page_writes`, `random_page_cost`, `effective_io_concurrency` | — | **unchanged** | `random_page_cost` and `effective_io_concurrency` are right for PGDATA on the ssd-pool. The other two restate PG16 defaults and are kept as explicit anti-footgun guards |

**Considered and rejected**, because every line here becomes a live `verify.sh` assertion:
`checkpoint_completion_target` and `hash_mem_multiplier` (already 0.9 and 2.0 by default in
PG16 — a line that restates a default is an assertion for no behaviour change);
`maintenance_io_concurrency` (default is already 10, unlike `effective_io_concurrency`'s 1);
`max_locks_per_transaction` (the lock pool is `64 × max_connections`, ample for `pg_dump`
over the partitioned `lineage.audit_events`); `jit = off` (standard PostGIS advice, but
plan-dependent and unmeasured here — an A/B for the runbook, not a guess);
`wal_compression` and `shared_preload_libraries = pg_stat_statements` (**both can stop the
server from starting** if the build lacks LZ4 or the contrib library is absent, and neither
is verifiable from here — both are runbook steps with a pre-check instead).

### `work_mem` arithmetic

`work_mem` is per sort/hash node per worker, not per connection, so the nominal figure is
never the exposure. The naive bound — `max_connections` × nodes × `work_mem`, or 80 × 4 ×
64MB = 20 GB — exceeds RAM at *any* setting above about 8MB, which is why `max_connections`
is the guard and `work_mem` is not. The bound that governs is narrower:

- **Heavy spatial sorts run on martin's connections, not the API's.** Tile SQL executes
  through `martin.service`, whose `pool_size` is 10. 10 leaders × 2 nodes × 64MB = **1.3 GB**.
- **Parallel workers are capped cluster-wide** by `max_parallel_workers`, left at 8.
  8 × 2 × 64MB = **1.0 GB**, no matter how many gathers are running.
- **API sorts are index-driven with `LIMIT`.** Say 10 concurrently active: **0.6 GB**.

**≈ 2.9 GB realistic ceiling**, which the budget below carries. What 64MB does *not* buy is
the bulk path: `canonical.production_monthly_latest` re-ranks the whole table through a
`WindowAgg` (measured 73 s warm at 17.6 M rows) and `marts/land_metrics.py` reads it. No
globally safe `work_mem` reaches that. Give it to the one role that needs it instead —
`ALTER ROLE glasswell_pipeline SET work_mem` in step 5, which is one monthly connection and
multiplies by nothing.

### Memory budget at the revised values

```
  15.6 GB  physical, no swap
 - 4.0 GB  shared_buffers, resident for the life of the postmaster
 - 1.1 GB  other resident services (uvicorn x2, martin, node, OS)
 - 0.75 GB autovacuum burst: 3 workers x autovacuum_work_mem 256MB  (was 1.5 GB at 512MB)
 - 2.9 GB  backend work_mem, per the arithmetic above
 - 0.3 GB  idle backend overhead across 80 connections
 - 1.0 GB  page-cache floor below which PostgreSQL's write path crawls
 = 5.5 GB  left for ingest
```

`glasswell-ingest.service` caps at `MemoryMax=6G`, 0.5 GB above what this leaves — a guard,
not a reservation, and its measured peak across the whole 125-month back-load was 297 MB.
**Do not run a bulk promotion while the balloon is inflated**: at the 8 GiB floor the
resident total above is ~6.4 GB, which survives serving but not a concurrent 6 GB ingest.

### Measure before trusting any of this

Every number above is derived from the repository and from evidence already on disk. **No
database-size, cache-hit, connection high-water or checkpoint telemetry exists for this
host** — `pg_database_size` is collected by `status/collector.py` but no emitted value is
recorded anywhere. Capture it, then revisit the four settings named at the end.

```bash
sudo -u postgres psql -d glasswell <<'SQL'
\pset pager off
-- Database, and the ten largest relations with their index share.
select pg_size_pretty(pg_database_size(current_database())) as database;
select n.nspname||'.'||c.relname as relation,
       pg_size_pretty(pg_total_relation_size(c.oid)) as total,
       pg_size_pretty(pg_relation_size(c.oid))       as heap,
       pg_size_pretty(pg_indexes_size(c.oid))        as indexes,
       c.reltuples::bigint                           as est_rows
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
 where c.relkind in ('r','m','p') and n.nspname not like 'pg\_%'
 order by pg_total_relation_size(c.oid) desc limit 10;

-- Cache hit ratio. Below ~0.99 on a read path this size means shared_buffers is short.
select round(100.0 * sum(blks_hit) / nullif(sum(blks_hit + blks_read), 0), 2) as cache_hit_pct,
       sum(temp_files) as temp_files, pg_size_pretty(sum(temp_bytes)) as temp_bytes
  from pg_stat_database where datname = current_database();

-- Connections now, and the ceiling. temp_bytes above is the work_mem spill evidence.
select state, count(*) from pg_stat_activity where datname = current_database() group by state;
select setting as max_connections from pg_settings where name = 'max_connections';

-- Checkpoints. checkpoints_req materially above checkpoints_timed means max_wal_size is short.
select checkpoints_timed, checkpoints_req, buffers_checkpoint, buffers_clean, buffers_backend
  from pg_stat_bgwriter;

-- Autovacuum reach on the append-heavy tables.
select relname, n_live_tup, n_dead_tup, n_mod_since_analyze, last_autovacuum, last_autoanalyze
  from pg_stat_user_tables
 where relname in ('production_monthly','quarantine_rows','wells','well_spatial')
    or relname like '%_tile' order by n_live_tup desc;
SQL

# Free space where PGDATA and pg_wal live — max_wal_size 4GB peaks at roughly double.
df -h /var/lib/postgresql; free -m; swapon --show
```

Optional, and worth doing once — `pg_stat_statements` is the only way to rank this workload
by real cost. It is **not** in the drop-in because naming a library the build lacks stops
the server from starting. Check first, then add it by hand:

```bash
ls /usr/lib/postgresql/16/lib/pg_stat_statements.so    # must exist before the next line
sudo -u postgres psql -d glasswell -c "alter system set shared_preload_libraries = 'pg_stat_statements'"
systemctl restart postgresql@16-main && systemctl restart martin
sudo -u postgres psql -d glasswell -c 'create extension if not exists pg_stat_statements'
```

**Re-check these four once real numbers come back.** `shared_buffers` — raise toward 6GB
only if cache hit sits below 99 % *and* `free -m` still shows idle RAM. `work_mem` — the
`temp_files` and `temp_bytes` counters are the direct evidence; confirm the tile claim with
`explain (analyze, buffers)` on a z6 `tx_wells` tile and look for `Sort Method: external
merge`. `max_connections` — the `pg_stat_activity` high-water mark is what would justify
lowering it back toward 60, which would in turn buy `work_mem` headroom. `max_wal_size` —
if `checkpoints_req` still dominates during a promotion, raise it; it is `sighup`-reloadable,
so `select pg_reload_conf()` applies it without a restart and it can go back down after.

## Deploy runbook

Steps 1–4 are the routine deploy. Step 5 applies a revised tuning drop-in and is outstanding
whenever `postgres/postgresql.conf.d/glasswell.conf` has moved since the last PostgreSQL
restart — it is outstanding now, for the revision above. Step 6 was done on 2026-08-20 in
the same window as the first tuning apply and is kept for the record.

```bash
# 1. sync the tree and rebuild the frontend (tar over ssh; rsync --delete stalls here)
# 2. place config and units — idempotent, safe on every deploy
cd /opt/glasswell/src/infra && ./install.sh

# 3. run migrations as the postgres superuser (migration 001 does create role)
sudo -u postgres /opt/glasswell/venv/bin/glasswell-migrate \
    --dsn "postgresql:///glasswell?host=/var/run/postgresql"

# 4. reinstall the tile functions if src/glasswell/marts/tiles.py moved, then restart and
#    check. Create-or-replace on the ten function bodies; it rewrites no row, which is
#    what separates it from `python -m glasswell.marts.nd_wells` (that mints a mart.refresh
#    derivation for what may be a code-only change). martin publishes these functions, so a
#    stale body is a stale tile source.
systemd-run --uid=glasswell --pipe --wait --quiet /opt/glasswell/venv/bin/python \
    -c 'import psycopg, glasswell.marts.tiles as t
c = psycopg.connect("postgresql:///glasswell?host=/var/run/postgresql")
print(t.install_tile_functions(c)); c.commit()'
systemctl restart glasswell-api && systemctl restart martin
systemctl start glasswell-status.timer     # migrations are complete; arm the schedule now
systemctl start glasswell-lineage-retention.timer
systemctl start glasswell-lineage-retention.service  # prove this release can sweep safely
systemctl start glasswell-status.service   # block until this release's snapshot is written
./verify.sh

# 5. Apply the Postgres tuning. Run whenever the drop-in has moved since the last restart.
#    5a. The swapfile SB-06 2.3 asked for and provisioning never created. Do this FIRST:
#        it is what makes sizing against 16 GiB safe against the 8 GiB balloon floor.
#        Step 5 reruns whenever the drop-in moves, so both halves are guarded: fallocate
#        would fail on a swapfile already in use, and a second append gives /etc/fstab a
#        duplicate entry that survives every reboot after it.
swapon --show                       # expect empty on the first run — that is the gap
if ! swapon --show=NAME --noheadings | grep -qx /swapfile; then
    fallocate -l 4G /swapfile && chmod 0600 /swapfile && mkswap /swapfile && swapon /swapfile
fi
grep -q '^/swapfile[[:space:]]' /etc/fstab \
    || printf '/swapfile none swap sw 0 0\n' >> /etc/fstab   # survives reboot
#    5b. Capture the "before" numbers — the Measure section above is the full set.
sudo -u postgres psql -d glasswell -c 'select * from pg_stat_bgwriter' > /tmp/pg-before.txt
#    5c. Place and restart. martin's pooled connections do not survive the restart.
cd /opt/glasswell/src/infra && ./install.sh --with-postgres
systemctl restart postgresql@16-main
systemctl restart martin
#    5d. default_statistics_target only bites after a re-analyze; nothing else needs this.
sudo -u postgres vacuumdb --analyze-only --all --jobs 4
#    5e. The bulk path's work_mem, which the global value deliberately does not carry.
sudo -u postgres psql -d glasswell \
    -c "alter role glasswell_pipeline set work_mem = '512MB'" \
    -c "alter role glasswell_pipeline set maintenance_work_mem = '2GB'"
sudo -u postgres psql -d glasswell -c 'show shared_buffers'   # expect 4GB
./verify.sh                         # the "postgres tuning" block must now be all ok

# 6. DONE 2026-08-20 — drop the inert LAN rule in front of loopback-only martin (DR-29)
ufw status numbered | grep 3000     # confirm the rule is there and nothing else uses 3000
ufw delete allow from 192.168.2.0/24 to any port 3000
ss -ltn | grep 3000                 # still 127.0.0.1:3000 — the rule was never reachable

# 7. ONE-TIME — the two missing zone roots (DR-06). install.sh creates them; /data/raw and
#    /data/staging already exist, /data/scratch does not.
./install.sh                        # then: ls -ld /data/raw /data/staging /data/scratch

# 8. ONE-TIME — clear the rsync-era leftovers from the deploy root (DR-28). The deploy is
#    `git archive HEAD | ssh tar -x`, which cannot carry a git-excluded file, so these are
#    stale. docs/product-*.md are IP carve-out material (blueprint 8.2) and should not sit
#    on a LAN-reachable host at all.
cd /opt/glasswell/src && rm -rf CLAUDE.md PLAN.md AUDIT.md MEMORY.md docs work-output \
    .claude .rdf                    # the set verify.sh's deploy-hygiene check enumerates
./verify.sh                         # the "deploy hygiene" and "zones" checks must now be ok
```

```bash
# 9. ONE-TIME — adopt the martin config so the tile server stops publishing staging (DR-05).
#    Migration 026 first, without exception: the config's DSN peer-auths as the OS user
#    martin, and both that role and the marts.tile_* views it may read are created
#    there. martin.service carries Restart=on-failure, so adopting the config against a
#    database that lacks them is a crash loop, not a failed start. The tile functions the
#    config publishes must also be installed from the code being deployed (step 4).
./install.sh --with-martin-config
systemctl restart martin
curl -s 127.0.0.1:3000/catalog | python3 -m json.tool   # expect the TILE_LAYERS roster, ten ids
./verify.sh                                             # the martin catalogue check goes ok
```

```bash
# 10. ONE-TIME — the TLS front door (DIR-13). The binary and the token file are host state;
#     the Caddyfile and the unit come from this directory. Order matters: Caddy must be
#     serving before uvicorn drops its LAN bind, or the app is unreachable in between.
curl -fsSL -o /usr/local/bin/caddy \
  'https://caddyserver.com/api/download?os=linux&arch=amd64&p=github.com/caddy-dns/cloudflare'
chmod 0755 /usr/local/bin/caddy && caddy list-modules | grep dns.providers.cloudflare
install -m 0600 /dev/null /etc/caddy/cloudflare.env   # then write CF_API_TOKEN=... into it
./install.sh --with-caddy && systemctl start caddy
curl -sI https://glasswell.lab.rpx.sh/ | head -1      # 200 before anything else moves
systemctl restart glasswell-api                       # now the bind drops to the unix socket
ufw allow proto tcp from 192.168.2.0/24 to any port 80,443
ufw delete allow from 192.168.2.0/24 to any port 8000
./verify.sh                                           # the `tls` block must be all ok
```

Steps 7, 8 and 9 are what the three `zones` / `deploy hygiene` / `martin publishes the
allowlist and nothing else` failures in `verify.sh` are pointing at. The `postgres tuning`
block joins them until step 5 applies the revised drop-in.

`verify.sh` derives its tuning expectations from the shipped drop-in, so the check cannot
drift from the file — and every line in that file is therefore a live assertion against the
host, which is why the drop-in carries only settings that change behaviour. The parser
tolerates an inline comment and a digit in a setting name, and now fails when the drop-in
yields *no* matching line: a file reformatted to `key=value` used to produce output
indistinguishable from a pass (F28). Step 6 had no counterpart in `verify.sh`: `ufw status`
needs root and the script is written to run unprivileged. The whole `tls` block is red until step 10 runs,
and its certificate check stays honest afterwards — it fails at 20 days remaining, ten days
after Caddy should have renewed.

## Accounts, the tunnel, and the public cutover

Authentication is the application's own session login. Cloudflare Access is **not** used and
is not enabled on the account; SB-06 §5 records the amendment and the reason. `api_keys` is
unchanged and remains the non-interactive path.

### The first account

There is no default credential at any point, and `install.sh` deliberately does not create
one — an unattended installer that mints a credential is how default credentials get
shipped, and a generated password printed at install time lands in the deploy log.

```bash
/opt/glasswell/venv/bin/glasswell-owner-bootstrap \
    --dsn 'postgresql:///glasswell?host=/var/run/postgresql' --username <name>
# password on stdin, then Ctrl-D. Never argv (visible in /proc and in shell history),
# never an environment variable (visible in systemctl show -p Environment).
```

It refuses if an enabled owner already exists. With an empty `users` table the login route
fails uniformly, which is the same fail-closed shape `DeniedKeyStore` uses for keys.

### Lockout recovery — the break-glass

Account locks are time-boxed to fifteen minutes and always expire on their own; no
administrative unlock is required. Three paths exist for an operator who cannot wait:

```bash
/opt/glasswell/venv/bin/glasswell-owner-reset \
    --dsn 'postgresql:///glasswell?host=/var/run/postgresql' --username <name>
```

It sets a new password, clears the failure history that arms the lock, re-enables a disabled
account and revokes every session it holds. The other two are the LAN listener with the
static owner key, which the login limiter does not gate, and the fact that a lock does not
apply from an address that account has logged in from in the last thirty days.

### The tunnel

The connector is installed and running **before** the hostname resolves. That ordering is the
point: the last step is the DNS record, and until it exists the origin is not on the internet.

```bash
# 1. owner, once: create the tunnel and leave its id and credentials on the host
cloudflared tunnel login
cloudflared tunnel create glasswell
install -o cloudflared -g cloudflared -m 0640 \
    ~/.cloudflared/<uuid>.json /etc/cloudflared/<uuid>.json
printf '%s\n' '<uuid>' > /etc/cloudflared/tunnel-id

# 2. place the config and the unit; refuses if the two files above are absent
cd /opt/glasswell/src/infra && ./install.sh --with-cloudflared

# 3. start the connector. The hostname still does not resolve; it reaches nothing.
systemctl enable --now cloudflared

# 4. turn on public mode: HSTS, the static-owner-key refusal on the tunnel listener,
#    and GLASSWELL_ALLOW_ANON=1 becomes a refusal to start
sed -i 's/^GLASSWELL_PUBLIC=0/GLASSWELL_PUBLIC=1/' /etc/glasswell/app.env
systemctl restart glasswell-api

# 5. verify. The tunnel section now runs; its three DNS-dependent probes fail because the
#    CNAME does not exist yet. That is expected and is the last checkpoint before exposure.
./verify.sh

# 6. THE CUTOVER. From here the origin is on the internet.
cloudflared tunnel route dns glasswell glasswell.rpx.sh
```

The credentials file is host state and is never in this repository. `infra/cloudflared/config.yml`
carries a `<tunnel-uuid>` placeholder that `install.sh` substitutes from
`/etc/cloudflared/tunnel-id`, and the ingress publishes exactly one hostname to Caddy's
`127.0.0.1:8080` listener with `http_status:404` for everything else — no martin, no
PostgreSQL, no SSH.

### Rollback — three levels, each independently sufficient

| Level | Action | Time | Effect |
|---|---|---|---|
| L1 | delete the proxied CNAME | seconds | the hostname stops resolving; connector and LAN path untouched |
| L2 | `systemctl stop cloudflared` | ~1 min | origin is LAN-only again; host-side, no dashboard needed |
| L3 | `GLASSWELL_PUBLIC=0`, revert the merge, redeploy | one deploy | pre-session behaviour |

L3 works **because the key path was retained**: reverting the session code leaves a
deployment whose only credential path is the one that was never removed.

**Stated non-reversible residue.** There are no down-migrations (`db/migrate.py` has no
`down` concept). A revert leaves `lineage.users`, `lineage.sessions` and
`lineage.login_attempts` in place, unused. Harmless, and recorded here so it is stated
rather than discovered.

## Usage

```bash
./install.sh                     # place config, generate the owner key, enable glasswell-api
./install.sh --with-postgres     # additionally place the tuning drop-in — 22 settings sized
                                 # for 16 GiB / 8 vCPU; needs a PG restart and a martin restart
./install.sh --with-caddy        # additionally place the Caddyfile and caddy.service, validated
./install.sh --enable-ingest     # additionally arm the monthly NDIC pull
./install.sh --enable-backup     # arm nightly backup and weekly logical restore timers
systemctl start glasswell-api
systemctl start glasswell-status.timer    # arm only after migrations complete
systemctl start glasswell-lineage-retention.timer
systemctl start glasswell-lineage-retention.service
systemctl start glasswell-status.service  # optional immediate refresh
./verify.sh                      # positive and negative checks, safe to run any time
```

Unlike ingest, backup and restore timers, `glasswell-status.timer` and
`glasswell-lineage-retention.timer` have no enable flag. Every install enables both; start them only
after migrations so neither can race a required schema grant or function. `deploy.sh` starts both
automatically and executes one retention sweep before collecting Status; a manual install must do
the same after migration. Status schedules an early boot collection and refreshes each quarter
hour. Retention runs nightly at 03:30 with `Persistent=true`; it removes only successful,
unreferenced `ephemeral` derivations older than 90 days.

The installer performs `systemctl enable glasswell-status.timer` and
`systemctl enable glasswell-lineage-retention.timer`; it deliberately does not start either one.
For `glasswell-status.timer`, start it only after migrations; the same ordering applies to
retention because its sweep function arrives with the schema.

The restore timer is enabled whenever backup is newly enabled or was already enabled, so an
upgrade cannot leave protection at the old backup-only state. A passing result must be no more
than eight days old and must identify a dump no more than two days old or Status degrades it.
Failures are durable too. The drill restores PostgreSQL logical content on the production host;
it does not consume the off-box copy, restore globals or raw files, or boot a replacement VM.
Enabling timers is not execution evidence. After first activation or a protection change, prove
the path immediately and refresh the served snapshot:

```bash
systemctl start glasswell-backup.service
systemctl start glasswell-restore-drill.service
systemctl start glasswell-status.service
systemctl show glasswell-backup.service glasswell-restore-drill.service -p Result
```

`install.sh` generates `GLASSWELL_OWNER_KEY` into `/etc/glasswell/app.env` (`root:root 0600`)
on first run and never prints it. Read it on the VM when you need the demo link; it is not in
this repository and not in any log.

`load-nd-months.py` backfills a range of production months as **one** knowledge-time vintage.
`lineage.vintages` is unique on `(source_id, vintage_date)`, so six same-day CLI runs would
upsert one row reporting only the last month.
