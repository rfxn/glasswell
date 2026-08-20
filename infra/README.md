# infra — what runs where

Config-as-code for the glasswell host, per SB-06 §9. This directory is authoritative; the
copies under `/etc` on the VM are placed by `install.sh` and are not edited in place.

## The host

| | |
|---|---|
| Host | `glasswell.lab.rpx.sh` → **192.168.2.111**, Proxmox VM 111 on forge |
| OS | Ubuntu 24.04.4 LTS, Python 3.12.3, Node 18.19.1 |
| Exposure | LAN only. `ufw` default-deny with 22, 8000 and 3000 open to `192.168.2.0/24` |
| Deploy root | `/opt/glasswell` — `venv/`, `src/` (rsynced repo), `web/` (built frontend) |
| Bulk volume | `/data` (1007 G): `raw/`, `staging/`, `parquet/`, `backups/` |

**SB-06 §4.5 and §11 say `192.168.2.61`. That is stale** — the DNS A record, forge's
restricted `authorized_keys` `from=` clause and every probe in this repo use `.111`.

## Units

| Unit | Runs as | Does |
|---|---|---|
| `glasswell-api.service` | `glasswell` | `uvicorn glasswell.api:app --host 0.0.0.0 --port 8000 --workers 2` — serves `/v1`, the `/v1/tiles` proxy, and the built frontend at `/` |
| `glasswell-ingest.service` + `.timer` | `glasswell` | Monthly ND pull: GIS layers, one production month, tile marts. Installed **disabled**; `install.sh --enable-ingest` arms it |
| `glasswell-alert@.service` | `glasswell` | `OnFailure=` target: logs to the journal and appends to `/var/lib/glasswell/health-events` |
| `martin.service` | `martin` | **Pre-existing, not owned by this directory.** Runs with `auto_publish` on, so its catalogue is every relation with a geometry column — `staging` and `canonical` included — on `127.0.0.1:3000`. The `/v1/tiles` proxy's allowlist, not martin, is what keeps staging off the wire |
| `postgresql@16-main` | `postgres` | Distro unit. `listen_addresses = 'localhost'`, socket peer auth |

`glasswell-backup.{service,timer}`, `glasswell-restore-drill.sh` and the forge-side vzdump
job were installed by the infra pass and live on the host, not here.

## Three decisions that differ from SB-06

**No Caddy, no TLS, no tunnel (C12).** Caddy is not installed on the VM, `ufw` closes 443,
and `8000/tcp` from the LAN is already open. uvicorn binds `0.0.0.0:8000` and serves the
frontend alongside `/v1`, so the LAN-only slice needs no firewall change and no certificate
warning in the owner's browser. The exposure is the firewall's job, which is where SB-06 put
it anyway. Caddy and the tunnel return when the deployment leaves the LAN.

**No `glasswell-martin.service`.** `martin.service` already exists, is enabled, runs as user
`martin` and reads `/etc/glasswell/db.env`. A second unit cannot bind `:3000`. martin reads
its source catalogue at startup, so a **restart** is required after `marts.refresh_all` first
creates the `marts.nd_*(z, x, y, query)` functions — that is a catalogue refresh, not a
reconfiguration. `infra/martin/config.yaml` is the documented morning target and must not be
enabled while auto-publish is on: it publishes the same ids as table sources and would
collide.

**`/data`, not `/srv/glasswell`.** The 1 TB volume is mounted at `/data`; `/srv/glasswell` is
an empty directory on the 145 GB root disk. Every path in these units follows the mount that
exists.

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

`marts.refresh_all` issues `create or replace function` in schema `marts`, so
`glasswell_pipeline` also needs `create on schema marts` — migration 009 grants only `usage`.

## Postgres tuning is shipped but not applied

`postgres/postgresql.conf.d/glasswell.conf` carries the SB-06 §2.3 sizing. `install.sh` places
it only under `--with-postgres`, because applying it needs a PostgreSQL restart and martin
holds a live connection. It deliberately does not set `listen_addresses`.

## Usage

```bash
./install.sh                     # place config, generate the owner key, enable glasswell-api
./install.sh --with-postgres     # additionally place the tuning drop-in (needs a PG restart)
./install.sh --enable-ingest     # additionally arm the monthly NDIC pull
systemctl start glasswell-api
./verify.sh                      # positive and negative checks, safe to run any time
```

`install.sh` generates `GLASSWELL_OWNER_KEY` into `/etc/glasswell/app.env` (`root:root 0600`)
on first run and never prints it. Read it on the VM when you need the demo link; it is not in
this repository and not in any log.

`load-nd-months.py` backfills a range of production months as **one** knowledge-time vintage.
`lineage.vintages` is unique on `(source_id, vintage_date)`, so six same-day CLI runs would
upsert one row reporting only the last month.
