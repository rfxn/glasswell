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
| `glasswell-ingest.service` + `.timer` | `glasswell` | Monthly ND pull: GIS layers, one production month, tile marts. Installed **disabled**; `install.sh --enable-ingest` arms it |
| `glasswell-c115b.service` + `.timer` | `glasswell` | Monthly NM C-115B natural-gas-waste capture, staging terminus. The 12th, `Persistent=true`: `reporting_period` is a rolling ~13-month window and a month that rolls out is unrecoverable from the endpoint. Installed **disabled**; `install.sh --enable-c115b` arms it |
| `glasswell-alert@.service` | `glasswell` | `OnFailure=` target: logs to the journal and appends to `/var/lib/glasswell/health-events` |
| `glasswell-backup.service` + `.timer` | `root` | Nightly `pg_dump` plus an rsync of the raw zone to forge, via `/usr/local/sbin/glasswell-backup.sh`. Installed **disabled**; `install.sh --enable-backup` arms it. **VM 111 has it enabled already** — the units here were adopted from that host byte-for-byte |
| `martin.service` | `martin` | **Pre-existing, not owned by this directory** — configured through a drop-in. Runs with `auto_publish` on until runbook step 9, so its catalogue is every relation with a geometry column, `staging` and `canonical` included, on `127.0.0.1:3000`. Adopting `martin/config.yaml` cuts it to the three published layers; migration 026's `martin` role, which holds select on three `marts.tile_*` views and nothing else, is what makes the rest unreachable either way |
| `postgresql@16-main` | `postgres` | Distro unit. `listen_addresses = 'localhost'`, socket peer auth |

`backup/glasswell-backup.sh` and `backup/glasswell-restore-drill.sh` are placed in
`/usr/local/sbin` by `install.sh`. They need `/root/.ssh/id_glasswell_backup` and a matching
`authorized_keys` entry on forge, which `install.sh` does not create. The forge-side vzdump
job is provisioning-owned and is not in this directory.

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
`canonical` relations. It declares the same three function sources auto-publish would have
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

# 4. reinstall the tile functions if src/glasswell/marts/tiles.py moved, then restart and
#    check. Create-or-replace on the three function bodies; it rewrites no row, which is
#    what separates it from `python -m glasswell.marts.nd_wells` (that mints a mart.refresh
#    derivation for what may be a code-only change). martin publishes these functions, so a
#    stale body is a stale tile source.
systemd-run --uid=glasswell --pipe --wait --quiet /opt/glasswell/venv/bin/python \
    -c 'import psycopg, glasswell.marts.tiles as t
c = psycopg.connect("postgresql:///glasswell?host=/var/run/postgresql")
print(t.install_tile_functions(c)); c.commit()'
systemctl restart glasswell-api && systemctl restart martin && ./verify.sh

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
cd /opt/glasswell/src && rm -rf CLAUDE.md PLAN.md AUDIT.md MEMORY.md docs work-output \
    .claude .rdf                    # the set verify.sh's deploy-hygiene check enumerates
./verify.sh                         # the "deploy hygiene" and "zones" checks must now be ok
```

```bash
# 9. ONE-TIME — adopt the martin config so the tile server stops publishing staging (DR-05).
#    Migration 026 first, without exception: the config's DSN peer-auths as the OS user
#    martin, and both that role and the three marts.tile_* views it may read are created
#    there. martin.service carries Restart=on-failure, so adopting the config against a
#    database that lacks them is a crash loop, not a failed start. The tile functions the
#    config publishes must also be installed from the code being deployed (step 4).
./install.sh --with-martin-config
systemctl restart martin
curl -s 127.0.0.1:3000/catalog | python3 -m json.tool   # expect exactly three ids
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
allowlist and nothing else` failures in `verify.sh` are pointing at. Everything else in the
file passes today.

`verify.sh` derives its tuning expectations from the shipped drop-in, so the check cannot
drift from the file. Step 6 has no counterpart in `verify.sh`: `ufw status` needs root and
the script is written to run unprivileged. The whole `tls` block is red until step 10 runs,
and its certificate check stays honest afterwards — it fails at 20 days remaining, ten days
after Caddy should have renewed.

## Usage

```bash
./install.sh                     # place config, generate the owner key, enable glasswell-api
./install.sh --with-postgres     # additionally place the tuning drop-in (needs a PG restart)
./install.sh --with-caddy        # additionally place the Caddyfile and caddy.service, validated
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
