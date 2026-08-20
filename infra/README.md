# infra — what runs where

Config-as-code for the glasswell host, per SB-06 §9. This directory is authoritative; the
copies under `/etc` on the VM are placed by `install.sh` and are not edited in place.

## The host

| | |
|---|---|
| Host | `glasswell.lab.rpx.sh` → **192.168.2.111**, Proxmox VM 111 on forge |
| OS | Ubuntu 24.04.4 LTS, Python 3.12.3, Node 18.19.1 |
| Exposure | LAN only. `ufw` default-deny with 22 and 8000 open to `192.168.2.0/24` |
| Deploy root | `/opt/glasswell` — `venv/`, `src/` (rsynced repo), `web/` (built frontend) |
| Bulk volume | `/data` (1007 G): `raw/`, `staging/`, `scratch/`, `parquet/`, `backups/`, `basemap/` |

**SB-06 §4.5 and §11 say `192.168.2.61`. That is stale** — the DNS A record, forge's
restricted `authorized_keys` `from=` clause and every probe in this repo use `.111`.

## Units

| Unit | Runs as | Does |
|---|---|---|
| `glasswell-api.service` | `glasswell` | `uvicorn glasswell.api:app --host 0.0.0.0 --port 8000 --workers 2` — serves `/v1`, the `/v1/tiles` proxy, and the built frontend at `/` |
| `glasswell-ingest.service` + `.timer` | `glasswell` | Monthly ND pull: GIS layers, one production month, tile marts. Installed **disabled**; `install.sh --enable-ingest` arms it |
| `glasswell-alert@.service` | `glasswell` | `OnFailure=` target: logs to the journal and appends to `/var/lib/glasswell/health-events` |
| `glasswell-backup.service` + `.timer` | `root` | Nightly `pg_dump` plus an rsync of the raw zone to forge, via `/usr/local/sbin/glasswell-backup.sh`. Installed **disabled**; `install.sh --enable-backup` arms it. **VM 111 has it enabled already** — the units here were adopted from that host byte-for-byte |
| `martin.service` | `martin` | **Pre-existing, not owned by this directory** — configured through a drop-in. Runs with `auto_publish` on until runbook step 9, so its catalogue is every relation with a geometry column, `staging` and `canonical` included, on `127.0.0.1:3000`. Adopting `martin/config.yaml` cuts it to the three published layers; migration 020's `martin` role is what makes the rest unreadable to it either way |
| `postgresql@16-main` | `postgres` | Distro unit. `listen_addresses = 'localhost'`, socket peer auth |

`backup/glasswell-backup.sh` and `backup/glasswell-restore-drill.sh` are placed in
`/usr/local/sbin` by `install.sh`. They need `/root/.ssh/id_glasswell_backup` and a matching
`authorized_keys` entry on forge, which `install.sh` does not create. The forge-side vzdump
job is provisioning-owned and is not in this directory.

## Three decisions that differ from SB-06

**No Caddy, no TLS, no tunnel (C12).** Caddy is not installed on the VM, `ufw` closes 443,
and `8000/tcp` from the LAN is already open. uvicorn binds `0.0.0.0:8000` and serves the
frontend alongside `/v1`, so the LAN-only slice needs no firewall change and no certificate
warning in the owner's browser. The exposure is the firewall's job, which is where SB-06 put
it anyway. Caddy and the tunnel return when the deployment leaves the LAN.

**No `glasswell-martin.service`.** `martin.service` already exists, is enabled, runs as user
`martin` and reads `/etc/glasswell/db.env`. martin binds `127.0.0.1:3000`, so no firewall
rule belongs in front of it — the `3000/tcp` LAN allow the infra pass added is inert today
and becomes a real exposure the moment the bind address changes. Removing it from the live
VM is a deployer step (see "Deploy runbook"). A second unit cannot bind `:3000`. martin reads
its source catalogue at startup, so a **restart** is required after `marts.refresh_all` first
creates the `marts.nd_*(z, x, y, query)` functions — that is a catalogue refresh, not a
reconfiguration. `infra/martin/config.yaml` is the documented target and adopting it is runbook step 9:
it turns auto-publish off, which is what stops the tile server publishing `staging` and
`canonical` relations. It needs the PG role `martin` that migration 020 creates — its DSN
peer-authenticates as the unit's OS user — and it must not be enabled alongside the
function sources, which publish the same ids.

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

## Postgres tuning is shipped but not applied

`postgres/postgresql.conf.d/glasswell.conf` carries the SB-06 §2.3 sizing, against the 8 GiB
balloon floor rather than the 16 GiB ceiling. It is the file that should apply: nine settings,
no `listen_addresses` (the running value is `localhost` and martin reaches PostgreSQL over
loopback TCP — SB-06 §1.3's `''` would take tiles down). `install.sh` places it only under
`--with-postgres`, because applying it needs a PostgreSQL restart and martin holds a live
connection. Applying it is a deployer step; see the runbook below.

## Deploy runbook

Steps 1–4 are the routine deploy. Steps 5 and 6 are one-time and currently outstanding —
`verify.sh` reports the tuning as failed until step 5 runs.

```bash
# 1. sync the tree and rebuild the frontend (tar over ssh; rsync --delete stalls here)
# 2. place config and units — idempotent, safe on every deploy
cd /opt/glasswell/src/infra && ./install.sh

# 3. run migrations as the postgres superuser (migration 001 does create role)
sudo -u postgres /opt/glasswell/venv/bin/glasswell-migrate \
    --dsn "postgresql:///glasswell?host=/var/run/postgresql"

# 4. restart and check
systemctl restart glasswell-api && ./verify.sh

# 5. ONE-TIME — apply the Postgres tuning (DR-20). Needs a restart; martin reconnects.
./install.sh --with-postgres
systemctl restart postgresql@16-main
systemctl restart martin            # martin's pooled connections do not survive the restart
sudo -u postgres psql -d glasswell -c 'show shared_buffers'   # expect 2GB
./verify.sh                         # the "postgres tuning" block must now be all ok

# 6. ONE-TIME — drop the inert LAN rule in front of loopback-only martin (DR-29)
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
cd /opt/glasswell/src && rm -rf CLAUDE.md PLAN.md AUDIT.md MEMORY.md docs work-output
./verify.sh                         # the "deploy hygiene" and "zones" checks must now be ok
```

```bash
# 9. ONE-TIME — adopt the martin config so the tile server stops publishing staging (DR-05).
#    Migration 020 first: the config's DSN peer-auths as the OS user martin, and that role
#    does not exist until the migration creates it.
./install.sh --with-martin-config
systemctl restart martin
curl -s 127.0.0.1:3000/catalog | python3 -m json.tool   # expect exactly three ids
./verify.sh                                             # the martin catalogue check goes ok
```

Steps 7, 8 and 9 are what the three `zones` / `deploy hygiene` / `martin publishes the
allowlist and nothing else` failures in `verify.sh` are pointing at. Everything else in the
file passes today.

`verify.sh` derives its tuning expectations from the shipped drop-in, so the check cannot
drift from the file. Step 6 has no counterpart in `verify.sh`: `ufw status` needs root and
the script is written to run unprivileged.

## Usage

```bash
./install.sh                     # place config, generate the owner key, enable glasswell-api
./install.sh --with-postgres     # additionally place the tuning drop-in (needs a PG restart)
./install.sh --enable-ingest     # additionally arm the monthly NDIC pull
./install.sh --enable-backup     # additionally arm the nightly backup (needs the forge key)
systemctl start glasswell-api
./verify.sh                      # positive and negative checks, safe to run any time
```

`install.sh` generates `GLASSWELL_OWNER_KEY` into `/etc/glasswell/app.env` (`root:root 0600`)
on first run and never prints it. Read it on the VM when you need the demo link; it is not in
this repository and not in any log.

`load-nd-months.py` backfills a range of production months as **one** knowledge-time vintage.
`lineage.vintages` is unique on `(source_id, vintage_date)`, so six same-day CLI runs would
upsert one row reporting only the last month.
