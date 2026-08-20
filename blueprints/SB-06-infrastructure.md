# SB-06 — Infrastructure & deployment

**Status:** execution-grade. This is the first glasswell component to be built; §11 is
the runbook a competent operator follows mechanically next session.
**Normative inputs:** `work-output/direction-log.md` DIR-1, DIR-4, DIR-6, DIR-7, DIR-9;
`work-output/assessment-infra.md`; `blueprint.md` §2.4, §3.5, §8.1.
**Authored:** 2026-08-20. Live forge state re-verified same day (Appendix A).

Where this document diverges from `assessment-infra.md`, the divergence is stated
explicitly with its reason (§13). Where the direction log is silent, a decision is made
and justified. Where a fact could not be verified, it is carried as a **VERIFY gate** in
§11 and is never assumed resolved.

**Evidence key** (inherited from the assessment so tags read the same across documents):

| Tag | Meaning |
|---|---|
| **[V]** | Verified — read from a file (`path:line`) or returned by a read-only live command |
| **[I]** | Inferred — conclusion drawn from verified facts, reasoning stated inline |
| **[A]** | Assumed — external/general knowledge or unverified estimate; must be confirmed before relied on |

**Secrets discipline.** No file under `.secrets/`, no `*.env`, `*.key`, `*.pem`, and no
Ansible vault content was opened while authoring this document. Secret *paths* are named;
secret *values* are not.

---

## 1. Scope & dependencies

### 1.1 What SB-06 owns

| Domain | Owned surface |
|---|---|
| Compute | Proxmox VM 111 `glasswell` on forge: creation, sizing, lifecycle, host RAM budget rule |
| OS baseline | Ubuntu 24.04 LTS install, users, sshd, nftables, unattended-upgrades, swap, guest agent |
| Storage | zvol layout, in-guest filesystems, the raw-zone directory contract, quotas, tablespaces |
| Network | Static LAN IP, `glasswell.lab.rpx.sh`, `glasswell.rpx.sh`, cloudflared tunnel, ingress map |
| Identity edge | Cloudflare Access application + policies; the origin-side JWT verification *contract* |
| TLS | Caddy on the VM: DNS-01 cert for the LAN listener; plaintext loopback for the tunnel listener |
| Supervision | systemd units and timers for api, martin, cloudflared, postgres, ingest, alerts, backup |
| Backup / DR | vzdump of VM 111, in-VM nightly dump + push to forge, snapshot retention, restore tests |
| Secrets | On-VM secret placement, ownership, modes; what lives in `rfxn-lab/.secrets/`; repo exclusions |
| Monitoring | Disk/RAM alarms, tunnel health probe, Postgres connection cap, origin rate limiting |
| Config home | `glasswell/infra/` as the authoritative deploy-config tree (§9) |
| Runbooks | §11 build runbook; restore, rotate, break-glass and guest-grant procedures |

### 1.2 What SB-06 does not own

Schema DDL and the `api_keys` / `glossary_terms` tables (SB-01). Endpoint code, the Access
dependency *implementation*, key issuance handlers (SB-04). Browser bundle, CSP content,
tooltip component (SB-05). Model training code (SB-02/03). SB-06 supplies the socket, the
path, the unit file and the identity contract; it does not supply application logic.

### 1.3 Interfaces promised to other sub-blueprints

These are contracts. Changing one requires a note in this file and in the consuming SB.

**To SB-01 (data model / storage):**

| Promise | Value |
|---|---|
| PostgreSQL | 16 (Ubuntu 24.04 default) + PostGIS 3.4, unix socket `/var/run/postgresql`, `listen_addresses = ''` |
| Database / role | db `glasswell`, role `glasswell`, `peer` auth over the socket — **no password anywhere** |
| Admin role | `glasswell_admin` (owner of DDL), also peer, used only by migration jobs |
| Data directory | `/var/lib/postgresql/16/main` on the SSD zvol |
| Bulk tablespace | `bulk` → `/srv/glasswell/pgbulk` on the HDD zvol, for staging tables only |
| Parquet root | `/srv/glasswell/parquet/{canonical,marts}` |
| Raw zone root | `/srv/glasswell/raw/<source>/<dataset>/<vintage>/` — contract in §3.3 |
| DuckDB home | `/var/lib/glasswell/duckdb/` on **SSD** (spill files); Parquet is read from HDD |
| Connection budget | `max_connections = 60`; SB-01 migrations may use at most 5 |

**To SB-04 (API / agent gateway):**

| Promise | Value |
|---|---|
| Deploy target | `/opt/glasswell/` (venv + code), `glasswell-api.service`, run as user `glasswell` |
| Bind | `127.0.0.1:8000` (uvicorn). Nothing else may bind a public interface |
| Identity contract | `request.state.principal` — see §5.5. SB-04 consumes it; SB-06 specifies it |
| Config file | `/etc/glasswell/access.env` (team name, AUD tag — not secret), `/etc/glasswell/app.env` |
| Key store | `api_keys` table (SB-01 owns DDL, §8.3 owns the shape) |
| Rate limits | Keyed on `principal.id`, never on client IP (§10.4) |
| Health path | `GET /healthz` — behind Access like everything else; unauthenticated only on the LAN listener |
| Tile prefix | `/tiles/*` is reserved for martin; SB-04 must not define routes under it |

**To SB-05 (UI):**

| Promise | Value |
|---|---|
| Public origin | `https://glasswell.rpx.sh` — single origin, so **no CORS is required or permitted** |
| LAN origin | `https://glasswell.lab.rpx.sh` — identical routing, identical paths |
| Static assets | Served by Caddy from `/opt/glasswell/web/` at `/` with immutable cache headers on hashed files |
| Tiles | `https://glasswell.rpx.sh/tiles/{z}/{x}/{y}` |
| Security headers | Caddy owns `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `X-Robots-Tag`. SB-05 owns CSP *content*; SB-06 owns where it is emitted (§4.5) |

### 1.4 Upstream dependencies SB-06 has on others

None blocking. SB-06 can be executed end-to-end against a stub FastAPI app that returns
`{"ok": true}` — and §11 does exactly that, so the whole identity and exposure path is
proven before a single row of regulator data exists (blueprint §2.5.3, and assessment C18:
"backups exist before the data does").

---

## 2. VM provisioning spec

### 2.1 Host state, re-verified 2026-08-20

| VMID | Name | Status | memory | balloon | cores | onboot | agent |
|---|---|---|---|---|---|---|---|
| 100 | kiln | running | 18432 | `0` | 8 | 1 | enabled=1 |
| 101 | anvil | running | 16384 | *(unset)* | 8 | 1 | enabled=1 |
| 102 | pw-bridge | **stopped** | 2048 | *(unset)* | 2 | **0** | enabled=1 |
| 110 | arena | **stopped** | 16384 | `0` | 6 | **0** | enabled=1 |

All **[V]** (`qm list`, `qm config {100,101,102,110}` on forge, 2026-08-20). `free -g` →
total **62**, used **31**, available **31**, **swap 0** **[V]**. This confirms DIR-7: pw-bridge
and arena are down and onboot-disabled, and ~31 GiB is free.

Pools **[V]** (`zpool list`, `zfs list -o name,used,avail`): `ssd-pool` 744 G, **302 G AVAIL**;
`hdd-pool` 10.9 T, **8.70 T AVAIL**; `rpool` 472 G, 451 G AVAIL; `usb-pool` 9.09 T, empty.
`pveversion` → **pve-manager/9.1.1**, kernel 6.17.2-1-pve **[V]**.

`/etc/pve/storage.cfg` **[V]**: `ssd-pool` and `hdd-pool` are both declared as
`zfspool` with `content rootdir,images` and **no `sparse` flag** — so zvols on either pool are
**thick** (a `refreservation` equal to `volsize` is taken at creation). This matters for §2.4.

### 2.2 The RAM budget rule (record this; it is load-bearing)

forge has **62 GiB usable and zero swap** **[V]**. A swapless host that overcommits does not
degrade — the OOM killer takes an entire VM.

```
host + PVE            ~2 GiB
ZFS ARC                4 GiB   (zfs_arc_max=4294967296) [V]
kiln     (100)        18 GiB   balloon:0 — cannot balloon (see below)
anvil    (101)        16 GiB   balloon unset => floor == ceiling => no reclaim
glasswell(111)        16 GiB   ceiling; 8 GiB floor
------------------------------------------------------------------
committed with the above running:  56 GiB / 62 GiB   -> OK, ~6 GiB margin
+ arena  (110)        16 GiB  ->  72 GiB / 62 GiB   -> OVERCOMMIT
+ pw-bridge (102)      2 GiB  ->  74 GiB / 62 GiB   -> OVERCOMMIT
```

**RULE (must be checked before any `qm start 110` or `qm set 110 --onboot 1`):**
arena and glasswell must not both run at ceiling. Resolve by one of —
(a) `qm set 111 --memory 8192 --balloon 8192` (glasswell drops to a fixed 8 GiB), or
(b) `qm set 110 --memory 8192 --balloon 4096` (arena shrinks and gains a floor), or
(c) replace 8×8 GB with 8×16 GB DDR4-2133 UDIMMs — all 8 DIMM slots are populated **[V]**,
so this is a *replacement*, ~$120-220 **[A]**, and requires checking the ASUS X99-DELUXE
BIOS-3902 QVL for 16 GB UDIMM support **[A]** before purchase.

This rule belongs in `rfxn-lab/homelab.md` at the end of §11; a rule that only lives in a
sub-blueprint will not be read by the person who restarts arena.

### 2.3 Ballooning: why glasswell differs from kiln and arena

`balloon: 0` **disables the virtio-balloon device entirely**. It is set on kiln and arena
**[V]**, and the two cases are not the same:

- **kiln** passes through both RX 6800 XTs via VFIO (`homelab.md:235-243`). QEMU must pin
  the guest's entire address space for device DMA, so ballooning is technically impossible
  there, not merely undesirable. **[I]**
- **arena** has no passthrough **[V]** — its `balloon: 0` is a *guarantee* for a
  latency-sensitive game host, a policy choice.

glasswell is neither. It has no passthrough, and its latency criterion (blueprint S3,
scenario in <3 s) is CPU-bound, not RAM-residency-bound: the assessment's own arithmetic puts
20k wells × ~200 monthly rows ≈ 4M rows, i.e. a working set in the low hundreds of MB, with
peaks only during batch training and monthly ingest (`assessment-infra.md:47-51` **[I]**).

So: `--memory 16384 --balloon 8192`. Semantics **[I, from PVE `qm.conf`]**: `memory` is the
ceiling, `balloon` is the **floor**; `pvestatd` shrinks the guest toward the floor when the
host crosses its pressure threshold. **If `balloon` is omitted it defaults to `memory`,
meaning no reclaim ever happens** — which is why anvil, described in the assessment as
"ballooning enabled", in fact never gives memory back **[V/I]**. Setting the floor is not
optional; omitting it silently converts the design into `balloon: 0` behaviour.

Two consequences that must be honoured downstream:

1. **Size PostgreSQL against the floor, not the ceiling.** `shared_buffers = 2GB` (25 % of
   8 GiB), `effective_cache_size = 6GB`. Sizing against 16 GiB and then ballooning to 8 GiB
   is a guest OOM.
2. **The guest needs swap even though the host has none.** A 4 GiB swapfile on the SSD disk
   turns balloon pressure into slowdown instead of an OOM kill.

### 2.4 Disks

| Disk | Storage | Size | Flags | Contents |
|---|---|---|---|---|
| `scsi0` | `ssd-pool` | 150 G | `discard=on,iothread=1,ssd=1` | OS, PGDATA, DuckDB spill, venv, static assets |
| `scsi1` | `hdd-pool` | 1000 G | `discard=on,iothread=1,backup=0` | raw zone, Parquet, staging tablespace, local dump landing |

Flags mirror arena's `scsi0` exactly (`ssd-pool:vm-110-disk-0,discard=on,iothread=1,size=100G,ssd=1`) **[V]**.
`ssd=1` is omitted on `scsi1` because the backing vdev is spinning rust; advertising a
rotational device as non-rotational would suppress the guest's readahead heuristics **[I]**.

**`backup=0` on `scsi1` is mandatory, not cosmetic.** Without it, every weekly `vzdump` of
VM 111 would attempt to read a 1 TB disk. With it, the vzdump payload is the ~150 GB system
disk only, and the bulk zone is protected by the separate in-VM path in §7.2.

**Thick provisioning is real here.** Neither pool sets `sparse 1` **[V]**, so creation takes
`refreservation = volsize` immediately: 150 G off `ssd-pool`'s 302 G AVAIL → ~152 G remaining;
1000 G off `hdd-pool`'s 8.70 T → ~7.7 T remaining. Both are comfortable. Do **not** "fix" this
by enabling sparse on the shared storage definition — that would change behaviour for kiln,
anvil, pw-bridge and arena as a side effect.

### 2.5 zvol vs dataset for the bulk zone — decision and justification

**Decision: a second zvol (`scsi1`) on `hdd-pool`. Not a dataset over virtiofs, not NFS.**

| Option | Verdict |
|---|---|
| **zvol as `scsi1`** | **Chosen.** `hdd-pool` is already a PVE `zfspool` storage with `content rootdir,images` **[V]** — zero new host plumbing. Every other VM on forge uses zvols **[V]**, so the operational muscle memory, the `qm` commands, and the vzdump semantics are all the ones already in use. `backup=0` cleanly excludes it. Guest owns the filesystem, so `fstab`, quotas and permissions behave normally. |
| dataset + virtiofs | Rejected for now. PVE 9 supports directory mappings, but **no VM in this fleet uses it** **[V]** — it would be the second brand-new technology in a build that already introduces cloudflared and Zero Trust (`assessment-infra.md:167-172`). It also adds a start-time dependency: a missing mapping blocks VM start. Its real advantage (host-side per-file `zfs send` of the raw zone) is delivered instead by §7.2's rsync-to-`hdd-pool/backups/glasswell` path, which additionally survives the VM being unbootable. |
| dataset + NFS | Rejected. Puts an NFS server on the hypervisor, adds a network hop, another service to harden, and a failure mode where a stalled mount hangs the guest's I/O. |

The honest cost of the chosen option: a zvol snapshot is block-level and crash-consistent,
so recovering one file from it means cloning the snapshot and mounting it. That cost is paid
once, rarely, and §7.2 gives file-granular recovery for the data that actually matters.

### 2.6 Identity, boot and agent

| Attribute | Value | Note |
|---|---|---|
| VMID | **111** | `pvesh get /cluster/nextid` returns **103** **[V]**, i.e. the lowest free ID. 111 is chosen deliberately per DIR-7 to keep the `11x` "long-lived application VM" band next to arena (110) rather than reusing pw-bridge's decommissioned neighbourhood. |
| name | `glasswell` | matches DNS label |
| cpu | `host`, 8 cores, 1 socket, `numa 1` | arena and kiln both use `cpu: host` **[V]**. 24 of 27 threads are already allocated **[V]**, but CPU overcommit on a bursty fleet is safe — kiln and anvil idle most of the time **[I]** |
| ostype | `l26` | |
| scsihw | `virtio-scsi-single` | matches arena **[V]** |
| net0 | `virtio,bridge=vmbr0` | flat lab /24 |
| serial0 / vga | `socket` / `serial0` | matches arena **[V]**; makes `qm terminal 111` work when the network is broken — this is the console-of-last-resort for a mis-set nftables rule |
| onboot | **1** | kiln and anvil are `onboot: 1` **[V]**; glasswell must come back after a forge reboot (forge rebooted 1 h before this document was written **[V]**, `uptime` 1:08) |
| agent | `enabled=1,fstrim_cloned_disks=1` | **and the in-guest package** — see below |

**qemu-guest-agent is REQUIRED, and the lesson is sharper than "graceful shutdown".**

The host-side flag is *not* the whole story. VM 102 (pw-bridge) has `agent: enabled=1` in its
config **[V]** — yet `rfxn-infra/HANDOFF-powerwall.md:148-151` records that `qm reboot 102`
"is a no-op here — the guest ignores ACPI (no agent/acpid), the request is dropped and uptime
never resets", forcing `qm stop && qm start`, a hard power-cycle. The defect was the **missing
in-guest `qemu-guest-agent` package**, with the host flag set and lying about it. **[V/I]**

For glasswell the agent is load-bearing three times over:

1. **`vzdump --mode snapshot` uses the agent to issue `guest-fsfreeze`.** Without it the backup
   is crash-consistent only — recoverable for ext4, but a PostgreSQL restore from a torn
   snapshot is a bad way to find out. This is the strongest reason.
2. **Graceful shutdown on forge reboot / UPS event.** Without the agent, `qm shutdown` falls back
   to ACPI, and a guest that ignores ACPI gets power-cut — exactly pw-bridge's failure.
3. **Accurate free-memory reporting to `pvestatd`**, which is what drives auto-ballooning (§2.3).

Verification is a runbook gate, not an assumption: `qm agent 111 ping` must return before the
build proceeds (§11 step 12).

### 2.7 Provisioning commands

Cloud-init is the path: `/var/lib/vz/template/iso/noble-cloudimg.img` is present on forge and
is a **QCOW2 v3, 3.5 GB virtual** Ubuntu 24.04 (noble) cloud image **[V]**, and arena was built
the same way (`ide2: ssd-pool:vm-110-cloudinit,media=cdrom`, `ciuser: ryan`,
`ipconfig0`, `nameserver: 192.168.2.1`, `searchdomain: lan`) **[V]**.

Run on forge as root. `qm disk import` and `qm disk resize` are the PVE 9 spellings — both
confirmed present **[V]** (`qm help`).

```bash
IMG=/var/lib/vz/template/iso/noble-cloudimg.img
LANIP=192.168.2.61

qm create 111 --name glasswell --ostype l26 --cpu host --sockets 1 --cores 8 --numa 1 \
  --memory 16384 --balloon 8192 \
  --scsihw virtio-scsi-single --net0 virtio,bridge=vmbr0 \
  --serial0 socket --vga serial0 --agent enabled=1,fstrim_cloned_disks=1 --onboot 1

qm disk import 111 "$IMG" ssd-pool
qm set 111 --scsi0 ssd-pool:vm-111-disk-0,discard=on,iothread=1,ssd=1
qm disk resize 111 scsi0 150G

qm set 111 --scsi1 hdd-pool:1000,discard=on,iothread=1,backup=0
qm set 111 --ide2 ssd-pool:cloudinit --boot order=scsi0

qm set 111 --ciuser ryan --ciupgrade 0 \
  --sshkeys /root/.ssh/authorized_keys \
  --ipconfig0 "ip=${LANIP}/24,gw=192.168.2.1" \
  --nameserver 192.168.2.1 --searchdomain lan

qm start 111
```

`--cipassword` is deliberately omitted: key-only from first boot. If a console password is
wanted for the `serial0` fallback, set it interactively with `qm set 111 --cipassword` and
never place it in a script or this file.

`--ciupgrade 0` matches arena **[V]** and keeps first boot deterministic; §11 runs the upgrade
explicitly as its own verifiable step.

---

## 3. Storage layout on the VM

### 3.1 Filesystems

```
/dev/sda  (scsi0, ssd-pool, 150 G, thick)
  /                       ext4, noatime          ~15 G  OS + packages
  /var/lib/postgresql     (on /)                        PGDATA — canonical + marts + staging DDL
  /var/lib/glasswell/duckdb                             DuckDB databases and SPILL files
  /opt/glasswell                                        venv, application code, web/ bundle
  /swapfile               4 G                           balloon-pressure relief (§2.3)

/dev/sdb  (scsi1, hdd-pool, 1000 G, thick)
  /srv/glasswell          xfs, noatime
```

ext4 on `/` (matches the cloud image default; nothing gains from changing it). **xfs on
`/srv/glasswell`** because the bulk zone is a small number of very large sequentially-read
files (Parquet, regulator ZIP/CSV) and xfs handles large extents and parallel large-file I/O
better than ext4 at this shape **[I]**. Mount both `noatime` — every Parquet scan otherwise
issues metadata writes to a spinning pool for no benefit.

**DuckDB spill goes on the SSD.** DuckDB reads Parquet from `/srv/glasswell/parquet` (HDD,
sequential — fine) but spills hash joins and sorts to its temp directory. Pointing that at a
raidz1 of spinners would make every out-of-core aggregation pathologically slow **[I]**. Set
`SET temp_directory = '/var/lib/glasswell/duckdb/tmp'` in the connection bootstrap and give
SB-01 that path in §1.3.

### 3.2 Blueprint zone → mount mapping

Blueprint §3.0.1 pins three layers (staging source-faithful, canonical conformed, marts
serving) plus the raw zone (§2.5.3, §8.1 item 6). Physical placement:

| Blueprint zone | Lives at | Device | Why |
|---|---|---|---|
| **Raw zone** | `/srv/glasswell/raw/` | HDD | Never-deleted, sequentially read, and the one artifact whose loss is unrecoverable for some sources (§7.3). ~15 GB projected (DIR-9) |
| **Staging** | PostgreSQL tablespace `bulk` → `/srv/glasswell/pgbulk` | HDD | Transient. DIR-9 projects a 60-90 GB peak; parking that on a 150 GB SSD would starve everything else. Staging never serves (blueprint §3.0.1), so HDD latency is irrelevant. **Truncate after promotion** — the peak is an ingest peak, not a resident cost |
| **Canonical** | PostgreSQL default tablespace | SSD | Served through canonical→marts derivation; latency matters |
| **Marts** | PostgreSQL default tablespace + `/srv/glasswell/parquet/marts/` | SSD (PG) / HDD (Parquet) | martin reads marts from PostGIS on SSD; DuckDB reads Parquet marts from HDD |
| **Parquet canonical** | `/srv/glasswell/parquet/canonical/` | HDD | Single-digit GB (DIR-9); read sequentially by DuckDB |
| **DuckDB spill** | `/var/lib/glasswell/duckdb/tmp/` | SSD | See §3.1 |
| **Local dump landing** | `/srv/glasswell/backups/` | HDD | Staging area before the nightly push to forge (§7.2) |

SSD budget check: 15 (OS) + 4 (swap) + 5 (venv/web) + ~60 (PGDATA at maturity: canonical
4M production rows, marts, indexes, WAL) + 20 (DuckDB spill headroom) ≈ 104 G of 150 G,
leaving ~45 G. Comfortable **[I]**. If PGDATA outgrows it, the escape is a third zvol, not a
resize of the bulk disk.

### 3.3 The checksummed raw-zone contract

This is a contract, not a suggestion: blueprint §2.5.1 ("no naked numbers"), §2.5.3
("reproducibility is an output") and `glasswell/CLAUDE.md:23-24` ("raw is never edited in
place") all terminate here. If the raw zone is not self-verifying, the glass box is
decorative.

**Layout — manifests live with the files, always:**

```
/srv/glasswell/raw/<source>/<dataset>/<vintage>/
    MANIFEST.sha256       sha256sum-format, one line per file, LC_ALL=C sorted, relative paths
    FETCH.json            provenance record (below)
    <payload files ...>
```

- `<source>` — regulator short code: `ndic`, `nmocd`, `txrrc`, `fracfocus`.
- `<dataset>` — the regulator's own artifact name, not an interpreted one.
- `<vintage>` — **self-stamped by the ingester**, `YYYY-MM-DDTHHMMSSZ`, because DIR-9
  establishes that NM OCD refreshes nightly with **undated filenames** and TX RRC sits behind
  an **opaque-GUID MFT portal**. The filename cannot be trusted to carry the vintage, and
  DIR-2 makes the vintage a first-class dimension of every observation.

**`FETCH.json` minimum fields** (SB-01 mirrors these into a table; the file is the source of
truth because a restored directory must verify without a database):

```json
{
  "source": "nmocd",
  "dataset": "wells-production",
  "vintage": "2026-09-01T031500Z",
  "url": "ftp://...",
  "resolved_id": "<RRC MFT GUID, or null>",
  "http_last_modified": "...",
  "http_etag": "...",
  "fetched_at_utc": "2026-09-01T03:15:07Z",
  "fetcher_version": "glasswell-ingest 0.1.0",
  "bytes": 481203712,
  "sha256_of_manifest": "..."
}
```

**Rules:**

1. A vintage directory is **sealed** after `MANIFEST.sha256` is written: files become `0444`,
   the directory `0555`, owner `root:glasswell`. The ingest user cannot rewrite a sealed
   vintage. A re-fetch creates a *new* vintage directory — never an update (DIR-2).
2. `sha256sum -c MANIFEST.sha256` inside the directory must pass with no arguments and no
   external state. This is the property that makes a restored backup trustworthy.
3. A partially-written vintage lives at `<vintage>.partial/` and is renamed into place only
   after the manifest verifies. A crashed fetch therefore leaves no half-sealed vintage.
4. `glasswell-raw-verify.timer` (weekly) re-verifies a rotating slice, full-pool pass monthly,
   and writes results where SB-01 can serve them. Silent bit-rot on a raidz1 is unlikely but
   the point of the glass box is not to require trust.
5. Nothing outside the ingester writes under `/srv/glasswell/raw/`. Enforced by ownership,
   asserted by the weekly verify.

### 3.4 PostgreSQL on ZFS — three notes that prevent later surprises

- **Keep `full_page_writes = on`.** The 8 KiB-atomic-write argument for turning it off applies
  to a ZFS *dataset* holding PGDATA. Here PGDATA is ext4 on a zvol, and ext4 makes no such
  guarantee to PostgreSQL. Disabling it would trade a torn page for a corrupt cluster **[I]**.
- **`volblocksize` is 16 K on existing zvols** **[V]** (`ssd-pool/vm-101-disk-0`). PostgreSQL
  writes 8 K pages, so there is read-modify-write amplification through the guest ext4. This
  is acceptable at glasswell's write volume (monthly batch ingest, not OLTP). If WAL write
  amplification is measured as a problem at P1 exit, the fix is a **third** zvol created with
  `volblocksize=8K` mounted at `/var/lib/postgresql` — not a rebuild.
- **Do not enable ZFS compression expectations on top of Parquet.** `hdd-pool` runs lz4 pool-wide
  (`homelab.md:179`) **[V]**; Parquet is already compressed, so budget the bulk zone at its
  uncompressed-on-disk size and treat any lz4 gain as a bonus.

---

## 4. Network & exposure

### 4.1 Topology

```
                internet
                   |
         Cloudflare edge  (Access evaluates EVERY request first)
                   |  proxied CNAME  glasswell.rpx.sh -> <uuid>.cfargotunnel.com
                   |
        [ outbound-initiated QUIC/HTTPS from the VM — NO inbound port ]
                   |
   VM 111  cloudflared (systemd, user cloudflared)
                   |  http://127.0.0.1:8080
              Caddy  ------------------------------  https://192.168.2.61:443
                   |                                  ^ LAN break-glass, DNS-01 cert
        /tiles/* -> 127.0.0.1:3000 martin             |  glasswell.lab.rpx.sh
        /*       -> 127.0.0.1:8000 uvicorn            |
                   |
              PostgreSQL  (unix socket only — listen_addresses = '')
```

### 4.2 DNS records

| FQDN | Type | Proxy | Value | TTL | Purpose |
|---|---|---|---|---|---|
| `glasswell.lab.rpx.sh` | A | **DNS-only (grey)** | `192.168.2.61` *(VERIFY free — §11 step 4)* | 300 | LAN plane: SSH, browsing, break-glass |
| `glasswell.rpx.sh` | CNAME | **Proxied (orange)** | `<tunnel-uuid>.cfargotunnel.com` | auto | Access-gated public entry point |

Both per DIR-6. Create the A record **before** the VM (`dns.md:31`: "New services get a DNS
record before deployment — name-first, not IP-first") **[V]**; the CNAME cannot exist until the
tunnel UUID does, so it is created at §11 step 20.

**Why the bare zone.** DIR-6 settles it: Cloudflare Universal SSL covers the apex and one label
(`rpx.sh`, `*.rpx.sh`) but **not** two labels deep, so `app.glasswell.lab.rpx.sh` would need
Advanced Certificate Manager (paid) to be proxied **[A — confirm on the dashboard, §11 step 2]**.
Also note assessment C13: an Access-gated hostname with a public certificate appears in
Certificate Transparency logs. **The hostname is not a secret and must not be treated as one.**
Do not pick an obscure name; rely on Access.

### 4.3 What is exposed and what is not

| Surface | Reachable from | Never reachable from |
|---|---|---|
| `https://glasswell.rpx.sh/*` | internet, **after** Access | — |
| `https://glasswell.lab.rpx.sh/*` | lab LAN only (RFC1918) | internet |
| SSH (22) | lab LAN only, key-only | internet, tunnel ingress map |
| PostgreSQL | **unix socket only** — not even 127.0.0.1 | everywhere else |
| martin (3000) | 127.0.0.1 only, via Caddy | LAN, internet |
| uvicorn (8000) | 127.0.0.1 only, via Caddy | LAN, internet |
| Proxmox console / `qm terminal` | forge, over lab LAN | internet |

**Zero inbound port forwards on the residential router.** The tunnel is outbound-initiated.
§11 step 28 verifies the negative from outside the LAN — the assessment's C1 and C17, and
responder's "verify the negative" habit (`responder/ARCHITECTURE.md:137-139`).

**Do not create a Cloudflare Access *Bypass* policy for the home WAN IP.** It is tempting
(`home.lab.rpx.sh` → the WAN egress already exists, `dns.md:41-43` **[V]**) and it is wrong twice:
it makes the public hostname unauthenticated for anyone sharing that residential IP or able to
spoof into that path, and residential IPs rotate — `home.lab.rpx.sh` exists precisely *because*
they rotate **[V]**. The LAN break-glass is a **separate hostname on a separate listener that
Cloudflare never sees**. That is the whole design.

### 4.4 cloudflared ingress map

`/etc/cloudflared/config.yml`, owner `cloudflared:cloudflared`, mode `0640`:

```yaml
tunnel: <tunnel-uuid>
credentials-file: /etc/cloudflared/<tunnel-uuid>.json
metrics: 127.0.0.1:20241
originRequest:
  connectTimeout: 10s
  noTLSVerify: false
  httpHostHeader: glasswell.rpx.sh
ingress:
  - hostname: glasswell.rpx.sh
    service: http://127.0.0.1:8080
  - service: http_status:404
```

One hostname, one origin, catch-all 404. **No Postgres, no martin port, no SSH, no second
hostname** (assessment C7/C9). Routing between the API and tiles happens in Caddy, not here —
one place to reason about path policy, and it is the same place the LAN listener uses, so both
paths exercise identical routing (§4.5).

### 4.5 Caddy: why a local reverse proxy at all

cloudflared can path-route by itself, so "no proxy" is a real option. It is rejected for one
decisive reason and three supporting ones:

**Decisive:** the LAN break-glass must be *the same application*. cloudflared does not serve the
LAN, so without Caddy the break-glass path would be different plumbing from the tunnel path —
and a break-glass you have not exercised on the same code path is not a break-glass. With Caddy,
testing one path validates the routing of both.

Supporting: (i) request-size and timeout caps belong at a proxy, and quench's hardened
`Caddyfile.j2:25-37` (`read_header 10s`, bounded `read_body`, `idle 60s`) is a proven template
**[V]**; (ii) static-asset serving with cache classes, responder-style (`_headers:1-63`) **[V]**;
(iii) org precedent — Caddy is already the reverse proxy on quench and on anvil
(`dns.md:32`, `rfxn-lab/CLAUDE.md:43`) **[V]**.

**Trap:** the stock Caddy apt package does **not** include the Cloudflare DNS provider; a
`tls { dns cloudflare ... }` block fails at parse time with an unknown-directive error. Use a
custom build with `caddy-dns/cloudflare` (the caddyserver.com download page produces one; pin
the sha256 in `infra/`) **[A — confirm the module list at build time]**. Fallback if you would
rather keep any Cloudflare credential off the VM entirely: `tls internal` on the LAN listener
and install Caddy's local CA on the two operator machines. Recommended: the custom build with a
**zone-scoped** token (Zone:DNS:Edit on `rpx.sh` only), which is exactly quench's posture
(`Caddyfile.j2:3-7`, token loaded from `caddy_env_file` via systemd `EnvironmentFile`) **[V]**.
Note that ACME renewal depends on Cloudflare, but a 90-day cert renewed at ~30 days remaining
means a Cloudflare outage does not break break-glass **[I]**.

**The two listeners, and the marker header.** The LAN path bypasses Access entirely, so the
origin cannot demand an Access JWT there or break-glass fails. The mode is carried by a header
that Caddy controls:

```
# tunnel-facing — Access is upstream; the client must never be able to claim LAN
http://127.0.0.1:8080 {
	request_header -X-Glasswell-Origin
	handle_path /tiles/* { reverse_proxy 127.0.0.1:3000 }
	handle { reverse_proxy 127.0.0.1:8000 }
}

# LAN break-glass — Access never sees this listener
https://glasswell.lab.rpx.sh {
	tls { dns cloudflare {env.CF_API_TOKEN} }
	request_header X-Glasswell-Origin lan
	handle_path /tiles/* { reverse_proxy 127.0.0.1:3000 }
	handle { reverse_proxy 127.0.0.1:8000 }
}
```

The `request_header -X-Glasswell-Origin` **delete on the tunnel block is the entire security
property** — it strips any client-supplied value before the set can matter. This is the same
shape as quench's `trusted_proxies cloudflare` + `client_ip_headers Cf-Connecting-Ip`
(`Caddyfile.j2:15-24` **[V]**): a header is trusted *because of which proxy delivered it*.

It is also a single line that a future edit could delete, so it is converted into a **tested
invariant**: §11 step 27 sends `X-Glasswell-Origin: lan` through the tunnel from outside and
asserts 403. If that test is ever awkward to keep green, the fallback is a second uvicorn
process bound to the LAN IP with `GLASSWELL_AUTH_MODE=lan`, where the mode is a property of the
process rather than of a header — costs ~250 MB RSS and a second unit **[I]**.

Also on both listeners: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, and **`X-Robots-Tag: noindex, nofollow` on everything** —
responder sets it on `/api/*` (`_headers:34-41`) **[V]**; a private, IP-gated PoC
(blueprint §8.2) sets it globally. CSP content is SB-05's; the header is emitted here.

### 4.6 `rfxn-lab/dns.md` amendment — paste-ready

Apply both hunks in one commit. **`rfxn-lab/CLAUDE.md:44` carries the same rule verbatim
("No bare `rpx.sh` records for lab infra — always under `lab.`") and must be amended in the
same commit** — a convention that exists in two files and is amended in one becomes drift.

Hunk 1 — add to the `## Records` table:

```markdown
| glasswell.lab.rpx.sh | 192.168.2.61 | glasswell | glasswell origin (VM 111 on forge) — LAN break-glass |
```

Hunk 2 — replace the third `## Conventions` bullet and append a new section after it:

```markdown
- **All lab records** live under `lab.rpx.sh` — no bare `rpx.sh` records for infra.
  **Exception — tunnel-published applications:** an application published through a
  Cloudflare Tunnel and gated by Cloudflare Access may take a bare `{app}.rpx.sh`
  proxied record. It is not lab infra: it has no RFC1918 address, it is unreachable
  without an Access policy, and Universal SSL covers only one label deep, so a
  `{app}.lab.rpx.sh` proxied record would require Advanced Certificate Manager.
  Every such record is listed under "Tunnel-published applications" below, with its
  Access application and its LAN break-glass twin.

## Tunnel-published applications

Bare-zone, proxied (orange) records whose target is a Cloudflare Tunnel connector, not
an IP address. Every request is evaluated by Cloudflare Access before it reaches the
tunnel, and the origin independently validates the Access JWT. **No inbound port forward
exists for any record in this table**, and none may be added.

| FQDN | Type | Proxy | Target | Access app | LAN break-glass |
|------|------|-------|--------|------------|-----------------|
| glasswell.rpx.sh | CNAME | proxied | `<tunnel-uuid>.cfargotunnel.com` | `glasswell` (path `*`) | glasswell.lab.rpx.sh |
```

---

## 5. Cloudflare Access design

Design principle from the assessment §3, itself derived from blueprint §2.3 ("multi-tenant
auth — design only") and §1.3 ("Not multi-user"): **glasswell never grows a user table.**
Identity is enforced at the edge; the origin *verifies* the edge's assertion and separately
carries a narrow key system for machines.

### 5.1 The application

One Access application, self-hosted, domain `glasswell.rpx.sh`, **path `*`**. Not a set of
per-path apps. This is assessment C3: the UI, `/api/*`, `/tiles/*`, `/explain`, `/conformance`,
`/glossary` (DIR-8) and the agent gateway are all inside it, with **no "just the tiles are
public" carve-out** — blueprint §8.1 item 5 already resolved "tile entitlement pattern" **[V]**.

Record the application's **AUD tag** at creation. It is not a secret, it is an origin config
value (`/etc/glasswell/access.env`), and the origin's `aud` check is worthless without it.

### 5.2 The four classes

| Class | Access mechanism | Session | Expiry mechanism | Origin sees |
|---|---|---|---|---|
| **Owner** | Allow, Include → Emails → `rfxnryan@gmail.com` | **24 h** | none (permanent grant) | JWT with `email` claim |
| **Guest** | Allow, Include → Emails → `<one named address>`; login method restricted to **One-time PIN** | **1 h** | dated policy name + calendar-backed removal (§5.4) | JWT with `email` claim |
| **Agent / API** | **Service Auth**, Include → Service Token → `glasswell-agent` | n/a | token rotation + independent app-key revocation | JWT with `common_name` claim, **plus** an app API key header |
| **LAN break-glass** | **none — Cloudflare is not in this path** | n/a | n/a | no JWT; `X-Glasswell-Origin: lan` from the LAN listener |

Notes that a reviewer will ask about:

- **One-time PIN needs no account and no IdP.** The guest receives a code at the specific address
  named in the policy. This is stronger than a shareable link, and it is exactly the "grant a
  named outsider access without making it public" primitive requested **[A — Cloudflare product
  behaviour; §11 step 2 verifies it exists on the Free plan]**.
- **There is no native "shareable magic URL"** in Access. If one is ever wanted for a stranger,
  build it as a separate, deliberately narrow signed-URL surface over *pre-rendered artifacts* —
  never by weakening the policy on the live app **[I]**.
- **Service Auth is a distinct policy action**, not an Allow policy with a token in it. Access
  evaluates Bypass → Service Auth → Allow/Block **[A — confirm the current precedence in the
  dashboard, §11 step 2 item 6]**. If Service Auth is not available on the Free plan, the
  fallback is: keep the agent path behind the owner's identity via a headless browser-less
  flow — impractical — or accept that the agent path runs on the LAN only until a paid seat is
  bought. **Do not** work around it by carving `/api/*` out of the Access app.
- **The three expiry knobs are independent** and a guest grant sets all three: Access *session*
  duration (how long a login lasts), Access *policy* lifetime (when the right to log in ends),
  and app-level API-key revocation (machine path). Forgetting one leaves a door open.

### 5.3 Origin JWT validation — FastAPI dependency (assessment C4)

The origin validating the JWT is the difference between defense-in-depth and a single point of
failure. Without it, anyone who reaches the origin by any other route — a future second
hostname, a mis-scoped tunnel ingress rule, a stale DNS entry — is unauthenticated-but-served.

**Specification (SB-04 implements; this is the contract):**

| Item | Value |
|---|---|
| Header | `Cf-Access-Jwt-Assertion` **only**. The `CF_Authorization` cookie is not consulted — cloudflared forwards the header on every request, and accepting a cookie widens the surface for nothing |
| Algorithms | Pin to `["RS256"]`. Reject `alg: none` and any HMAC alg explicitly, not by omission |
| JWKS URL | `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs` |
| `iss` | must equal `https://<team>.cloudflareaccess.com` |
| `aud` | must contain the configured AUD tag; compare exact strings, never prefix-match |
| `exp` / `nbf` / `iat` | enforced, leeway ≤ 60 s |
| Principal | `email` claim → human; `common_name` claim → service token. Exactly one must be present |
| Failure | 403 with no detail body. Never fall back to anonymous (assessment C6; responder's fail-safe gate, `functions/api/push/admin/util.js:1-4`) **[V]** |
| Bypass | Skipped entirely when `X-Glasswell-Origin: lan` is present — which only the LAN listener can set (§4.5) |

**JWKS fetch and cache behaviour — specify it, because the naive version is a lockout or a DoS:**

1. **Do not fetch at import time and do not fail startup on fetch failure.** The unit must start
   when Cloudflare is unreachable, or a CF outage takes the LAN break-glass down with it.
2. Cache in-process, TTL **3600 s**. Refresh lazily on first request after expiry.
3. **Serve stale on refresh failure for up to 24 h.** Cloudflare rotates Access signing keys on
   the order of weeks **[A]**, so 24 h of stale keys is safe and prevents a transient CF blip
   from locking the owner out. Past 24 h stale → `503`, never "allow".
4. **Unknown `kid` triggers at most one out-of-band refresh per 300 s** (token bucket). Without
   this, a flood of forged tokens with random `kid` values turns the origin into an outbound
   request amplifier against Cloudflare, and saturates residential upstream doing it.
5. HTTP client: 5 s total timeout, TLS verification **on**, redirects disabled, response body
   capped at 256 KiB.
6. `503` on "no usable keys" is distinguishable in logs from `403` on "invalid token". Conflating
   them makes the first real outage undiagnosable.

Sketch (SB-04 owns the final form):

```python
async def access_principal(request: Request) -> Principal:
    if request.headers.get("X-Glasswell-Origin") == "lan":
        return Principal(kind="lan", id="lan")
    token = request.headers.get("Cf-Access-Jwt-Assertion")
    if not token:
        raise HTTPException(403)
    key = await jwks.key_for(jwt.get_unverified_header(token)["kid"])  # 503 if unavailable
    claims = jwt.decode(token, key, algorithms=["RS256"],
                        audience=settings.access_aud, issuer=settings.access_iss)
    return Principal.from_claims(claims)
```

### 5.4 Guest grant and revocation procedure

Because a native policy `valid_until` field may not exist (VERIFY, §11 step 2 item 6), expiry is
operational and must be mechanical:

1. Name the policy `guest-<firstname>-expires-YYYY-MM-DD`. The expiry is in the name, so the
   policy list is self-auditing.
2. Set the policy session duration to 1 h.
3. Add the removal date to the operator calendar **at the same time as the policy**.
4. `glasswell-access-audit.timer` (weekly, on the VM) parses policy names from the Cloudflare API
   and warns on any `expires-` date in the past. A grant that outlives its name is the failure
   mode this catches.
5. Revocation = delete the policy, then **verify the negative**: the guest's next request must
   land on the login page and their existing session must not survive (test it, §11 step 30).

### 5.5 Principal contract handed to SB-04

```
request.state.principal = {
  "kind": "owner" | "guest" | "service" | "lan",
  "id":   <email> | <service token common_name> | "lan",
  "aud":  <access aud tag> | None,
  "exp":  <int epoch> | None,
}
```

`owner` vs `guest` is decided by matching `email` against `GLASSWELL_OWNER_EMAILS` in
`/etc/glasswell/app.env` — **config, not a table**. That keeps blueprint §1.3 ("Not
multi-user") and §2.3 ("multi-tenant auth — design only") honest **[V]**.

`kind == "service"` requires an app-level API key in addition (§8.3). `kind == "lan"` does not:
the LAN listener is physically gated.

### 5.6 First-time Zero Trust setup checklist — every step is verify-before-proceed

The organisation has **never used Zero Trust**: a repo-wide grep across `rfxn-lab`,
`rfxn-infra`, `responder` and `glasswell` for `cloudflared|cloudflare tunnel|trycloudflare|
cf-access-jwt|CF_Authorization|zero trust` returned zero hits, and `cloudflared` is not installed
on freedom **[V, assessment §1.2]**. Nothing below may be assumed.

| # | Verify | Gate — do not proceed until |
|---|---|---|
| 1 | Which Cloudflare account holds zone `rpx.sh` (dash → Websites → rpx.sh → Overview → Account ID) | The account ID is recorded. If `rpx.sh` and `rfxn.com` are in **different** accounts, Zero Trust must be enabled on the account holding `rpx.sh` |
| 2 | Zero Trust onboarding: choose the team name → `<team>.cloudflareaccess.com` | The exact team name is recorded. It is an input to `iss` and to the JWKS URL, and renaming it later invalidates both |
| 3 | Plan page shows **Zero Trust Free** active; note the seat count | The plan is Free and active, and no payment method was required. Seat count ≫ 2 (expected 50 **[A]**) |
| 4 | Settings → Authentication shows a **One-time PIN** login method | OTP is present and enabled. The guest class (§5.2) has no fallback if it is not |
| 5 | Access → Service Auth → Service Tokens: can a token be created on this plan? | A token can be created. If not, §5.2's note applies — resolve before designing the agent path |
| 6 | Policy editor: which session-duration and expiry fields exist; policy evaluation precedence (Bypass / Service Auth / Allow) | The available field names are written into `infra/README.md`. If no `valid_until` exists, §5.4's operational procedure is adopted explicitly, not silently |
| 7 | Networks → Tunnels: "Create a tunnel" is available; note the connector install command offered | The flow is reachable. **Do not run the connector install yet** — §11 step 18 does it from the VM |
| 8 | When creating the Access app, `glasswell.rpx.sh` is selectable from the hostname dropdown | The hostname appears — this is the practical proof that the zone and the Zero Trust org are the same account |
| 9 | Logs → Access shows login events after the first successful login | An event appears with the owner's email. An identity edge with no audit trail is not one |
| 10 | Free-plan behaviour for Access-gated responses and edge caching | Behaviour recorded. This is assessment U5 and it determines whether §12 / Option 4 becomes relevant. Do not assume tiles are edge-cached |

---

## 6. Service supervision

All units live in `glasswell/infra/systemd/` and are installed by `infra/install.sh` (§9).

### 6.1 Unit inventory

| Unit | Type | User | Binds / does |
|---|---|---|---|
| `postgresql.service` | distro | `postgres` | Unmodified Ubuntu unit. `listen_addresses = ''` in `postgresql.conf` — socket only |
| `glasswell-api.service` | service | `glasswell` | `uvicorn glasswell.api:app --host 127.0.0.1 --port 8000 --workers 2` |
| `glasswell-martin.service` | service | `glasswell` | `martin --listen-addresses 127.0.0.1:3000 --pool-size 10` over the PG socket |
| `caddy.service` | packaged | `caddy` | 127.0.0.1:8080 (tunnel) + 192.168.2.61:443 (LAN). `AmbientCapabilities=CAP_NET_BIND_SERVICE` |
| `cloudflared.service` | service | `cloudflared` | Outbound only. `Restart=always`, `RestartSec=5s` |
| `glasswell-ingest.timer` | timer | `glasswell` | Monthly regulator pull → raw zone → staging → promote (blueprint C3/C4) |
| `glasswell-alerts.timer` | timer | `glasswell` | Weekly AOI digest (blueprint C23: "systemd timer plus one table") **[V]** |
| `glasswell-backup.timer` | timer | `root` | Nightly `pg_dump` + rsync push to forge (§7.2) |
| `glasswell-raw-verify.timer` | timer | `glasswell` | Weekly rotating `sha256sum -c` over the raw zone (§3.3 rule 4) |
| `glasswell-access-audit.timer` | timer | `glasswell` | Weekly guest-policy expiry check (§5.4) |

`glasswell-ingest` and any batch-training unit get `MemoryMax=6G` so a runaway job cannot push
the guest past the balloon floor and trigger an OOM (§2.3).

### 6.2 Hardening baseline

Every `glasswell-*` unit carries this block; deviations are noted per-unit, never silently:

```ini
[Service]
User=glasswell
Group=glasswell
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
RestrictSUIDSGID=yes
LockPersonality=yes
CapabilityBoundingSet=
ReadWritePaths=/srv/glasswell /var/lib/glasswell
```

`ProtectSystem=strict` makes the whole filesystem read-only except `ReadWritePaths` — which is
why `/srv/glasswell/raw` being writable *only* by the ingest unit is enforceable rather than
aspirational. The ingest unit adds `/srv/glasswell/raw` to `ReadWritePaths`; the API and martin
units do not.

`cloudflared.service`: the vendor package ships a root unit. Replace it with a drop-in setting
`User=cloudflared`, `Group=cloudflared`, `CapabilityBoundingSet=`, `AmbientCapabilities=` — the
connector needs no capabilities because it only dials outbound (assessment C2). Credentials
file `0600 cloudflared:cloudflared`.

`glasswell-backup.service` runs as root (it reads PGDATA-adjacent paths and the ssh key) and
therefore drops `ProtectSystem=strict` for `ProtectSystem=full` plus an explicit
`ReadWritePaths=/srv/glasswell/backups`.

Every timer gets `Persistent=true` (so a missed run after a forge reboot fires on boot) and a
`RandomizedDelaySec=` so timers do not all land on the same minute.

`OnFailure=glasswell-alert@%n.service` on every unit and timer — a one-shot that logs the
failure with `logger -t glasswell-alert` and appends to the health file read by §10.

---

## 7. Backup & DR

The assessment's most consequential finding is that **the documented backup story does not
exist** (`homelab.md:184-190` describes hourly/daily snapshot retention that is not running).
Re-verified 2026-08-20 **[V]**:

- **No `vzdump` job.** `/etc/pve/jobs.cfg` does not exist; `/etc/cron.d/vzdump` contains only the
  auto-generated header; `/var/lib/vz/dump` is empty.
- **No VM zvol snapshots.** 299 snapshots exist on forge, all under `hdd-pool/backups/freedom/*`.
- **The one snapshot cron that exists has produced nothing since 2026-07-03** — 48 days as of
  2026-08-20. The crontab entry is present and correct (`5 3 * * *`, tag `freedom-zfs-snap`) and
  `cron` is `active`, yet `journalctl -t freedom-zfs-snap --since "60 days ago"` returns
  "No entries". Root cause undetermined (journal storage may be volatile; forge rebooted 1 h
  before this check) **[V]**.

**FLAG — out of SB-06 scope, needs its own task:** the forge `freedom-zfs-snap` cron and the
`freedom → forge` backup chain that feeds it have been silent for 48 days. That is an org-wide
data-protection gap on the host glasswell is moving onto, and it is *older* than glasswell. It
must be fixed as a separate rfxn-lab/rfxn-infra task. SB-06 does not depend on it, does not fix
it, and does not reuse its mechanism — §7.2 builds an independent chain deliberately.

### 7.1 Layer A — Proxmox vzdump of VM 111

```bash
# on forge, once
zfs create -o compression=zstd -o atime=off hdd-pool/vzdump
pvesm add dir vzdump-hdd --path /hdd-pool/vzdump --content backup --prune-backups \
  keep-daily=0,keep-weekly=4,keep-monthly=3

pvesh create /cluster/backup --id glasswell-weekly --vmid 111 \
  --storage vzdump-hdd --schedule "sun 02:30" --mode snapshot --compress zstd \
  --notes-template "glasswell VM 111 weekly" --enabled 1
```

- **`--mode snapshot` requires the in-guest agent** for `guest-fsfreeze` — see §2.6. Without it
  the dump is crash-consistent only.
- **`backup=0` on `scsi1`** (§2.4) keeps the 1 TB bulk disk out of the dump. Expected payload:
  ~150 GB disk, zstd-compressed to roughly 20-40 GB **[A]**, against 8.70 T AVAIL.
- Retention: 4 weekly + 3 monthly ≈ 7 archives ≈ 150-280 GB **[A]**.
- The dump lands on `hdd-pool`, the same pool as the bulk zone. That is **not** a second copy in
  any meaningful sense if the pool dies. Accepted for a PoC; the mitigation is `usb-pool`
  replication, noted below.

**Verify job** — vzdump on `dir` storage has no built-in verification (that is a PBS feature), so
build one. `glasswell-vzdump-verify` on forge, weekly, an hour after the dump:

```bash
newest=$(ls -1t /hdd-pool/vzdump/dump/vzdump-qemu-111-*.vma.zst | head -1)
[ -n "$newest" ] || { echo "FAIL: no vzdump archive for 111"; exit 1; }
find "$newest" -mtime -8 | grep -q . || { echo "FAIL: newest vzdump older than 8 days"; exit 1; }
zstd -t "$newest" || { echo "FAIL: zstd integrity check"; exit 1; }
zstdcat "$newest" | vma config - >/dev/null || { echo "FAIL: vma header unreadable"; exit 1; }
echo "OK: $newest"
```

`zstd -t` proves the compressed stream; `vma config -` proves the archive header parses and
lists the expected disks. Neither proves the guest boots — §7.4 does that.

**Replication (optional, recommended):** `usb-pool` is 9.09 T, healthy, and essentially empty
**[V]**. `homelab.md:349` records a standing objection to USB-attached ZFS ("USB-to-SATA bridge
chips lie about flush commands") that was never retracted **[V]**. Treat `usb-pool` as a
**replication target only, never primary**: a weekly `zfs send -I` of `hdd-pool/vzdump` to
`usb-pool/vzdump-replica`. A lying flush cache is a real risk for a live database and an
acceptable one for a third copy of an archive that is itself verified elsewhere **[I]**.

### 7.2 Layer B — in-VM nightly logical backup

Independent of Layer A by design: different mechanism, different granularity, different failure
mode. `glasswell-backup.timer` nightly at 02:00:

1. `pg_dump -Fc -Z6 -f /srv/glasswell/backups/glasswell-$(date -u +%Y%m%dT%H%M%SZ).dump glasswell`
   — custom format, so a single table can be restored with `pg_restore -t`.
2. `pg_dumpall --globals-only` alongside it (roles and grants are not in a per-database dump).
3. Prune local dumps to the last 7.
4. `rsync -aH --delete` push to forge:

```
forge:/hdd-pool/backups/glasswell/
    pgdump/        last 7 custom-format dumps + globals
    raw/           full mirror of /srv/glasswell/raw  (~15 GB projected, DIR-9)
    parquet/       canonical + marts Parquet
    infra/         /etc/glasswell, /etc/cloudflared/config.yml, unit files, Caddyfile
                   (config only — NO credential files, NO tunnel JSON)
```

5. On forge, `hdd-pool/backups/glasswell` is snapshotted daily with a 30-day prune. This mirrors
   the existing `hdd-pool/backups/freedom/{etc,home,proj,root,usr-local}` dataset + daily-snapshot
   convention **[V]** — the same *shape*, an independent *implementation*, since the existing one
   is the chain that has been silent for 48 days.

**Why the raw zone is rsynced in full and not just referenced:** §7.3. The projected 15 GB (DIR-9)
makes it trivially affordable, and it is the artifact whose loss cannot be undone.

**SSH key:** generated on VM 111, public key installed on forge with a restricted
`authorized_keys` entry (`command="rrsync -wo /hdd-pool/backups/glasswell",no-pty,
no-agent-forwarding,no-port-forwarding,from="192.168.2.61"`). Write-only into one directory,
from one IP. A compromised glasswell VM must not be able to read forge's other backups.

### 7.3 RPO/RTO, stated honestly per data class

The brief's framing — "the raw zone is re-fetchable from regulators" — **is not true for all
sources, and DIR-9 is why.** NM OCD "refreshes nightly with undated filenames"; TX RRC bulk
"sits behind an opaque-GUID MFT portal" **[V, DIR-9]**. So:

> **A lost NM OCD vintage cannot be re-obtained.** The regulator overwrote it the following
> night. Under DIR-2 every observation carries a report-vintage and restatements are new
> vintages, so a destroyed vintage is a permanent hole in the bitemporal record — it is not a
> file you re-download, it is history you no longer have.

| Data class | RPO | RTO | Re-derivable? | Notes |
|---|---|---|---|---|
| **Raw zone — dated sources** (NDIC monthly XLSX, FracFocus) | 24 h | hours | Yes, from the regulator | Loss is inconvenience |
| **Raw zone — rolling/undated sources** (NM OCD FTP, TX RRC MFT) | **24 h, and loss is PERMANENT** | 24 h | **No** | The highest-value thing on the VM. Justifies both Layer A and Layer B |
| PostgreSQL canonical + marts | 24 h | 1-2 h (`pg_restore`) | Yes, from raw + pinned code | |
| Parquet canonical + marts | 24 h | minutes-hours | Yes, from canonical | |
| Staging | **none — not backed up** | n/a | Yes, from raw | Transient by design (blueprint §3.0.1); truncated after promotion |
| DuckDB spill / tmp | none | n/a | Yes | Scratch |
| OS + packages | 7 d (vzdump) | 1-2 h (restore) | Mostly, from `infra/` | |
| Deploy config | **0** — it is in git | minutes | Yes | §9 |
| Secrets | see §8 | n/a | **No** — regenerate, do not restore | Tunnel credentials and tokens are re-issued, never restored from backup |

Worst realistic case (VM destroyed at 01:59, one minute before the nightly run): up to 24 h of
raw-zone fetches lost. For monthly regulator data that is at most one ingest cycle, and the
ingest is idempotent by vintage — *except* for a rolling source refreshed in that window. That
residual risk is accepted, and the mitigation is cheap: **the ingest job pushes newly sealed
vintages to forge immediately on seal**, rather than waiting for the nightly run. Add that to
the ingest unit (SB-01/SB-06 boundary: SB-06 provides the target path and key; SB-01's ingest
calls it).

### 7.4 Restore-test cadence — a backup is a hypothesis until restored

| Test | Cadence | Procedure | Pass criterion |
|---|---|---|---|
| **pg_dump restore** | Monthly, automated | `pg_restore` newest dump into scratch db `glasswell_restoretest`, run row-count assertions per table, drop | Counts within expected bounds; zero errors |
| **Raw-zone manifest verify** | Weekly rotating slice, monthly full | `sha256sum -c MANIFEST.sha256` across vintages | Zero mismatches |
| **vzdump integrity** | Weekly, automated | §7.1 verify job | `zstd -t` and `vma config` both clean |
| **Full VM restore** | **Quarterly, manual** | `qmrestore` newest archive to VMID **199**, boot with the NIC detached, log in, `systemctl --failed`, `psql -c "select count(*) from ..."`, then `qm destroy 199` | Boots, units start, database answers |
| **Break-glass drill** | Quarterly, manual | `systemctl stop cloudflared`, reach the LAN URL, restart | LAN path serves; public path returns Cloudflare's error, not the app |

The **first** restore test is not quarterly — it is §11 step 24, before any regulator data lands.
A restore path proven only after the irreplaceable data exists is not a proven restore path.

---

## 8. Secrets handling

Convention inherited from `rfxn-lab/CLAUDE.md:18-22` **[V]**: secrets live in `.secrets/`,
`chmod 600`, excluded via `.git/info/exclude`, never hardcoded, always sourced.

### 8.1 On the VM

| Secret | Path | Owner / mode | Notes |
|---|---|---|---|
| Tunnel credentials | `/etc/cloudflared/<uuid>.json` | `cloudflared:cloudflared` **0600** | Written by `cloudflared tunnel create`. **Never** backed up (§7.3) — a lost tunnel is re-created in 2 minutes; a leaked credential is a live ingress |
| Tunnel `cert.pem` (account cert) | **not on the VM** | — | `cloudflared tunnel login` runs on **freedom**; only the per-tunnel JSON is copied to the VM. The account cert can create tunnels for the whole zone and has no business on an application host |
| Caddy CF DNS token | `/etc/caddy/cf.env` | `root:caddy` **0640** | Zone-scoped (`Zone:DNS:Edit` on `rpx.sh` only), **distinct from** the token in `rfxn-lab/.secrets/cloudflare.env`. Loaded via systemd `EnvironmentFile`, matching quench (`Caddyfile.j2:5`) **[V]** |
| Access AUD tag + team name | `/etc/glasswell/access.env` | `root:glasswell` **0640** | **Not secret.** Listed here so nobody hides it in a secret store and then cannot find it |
| App config | `/etc/glasswell/app.env` | `root:glasswell` **0640** | Owner email list, rate-limit constants, paths |
| PostgreSQL password | **does not exist** | — | App, martin and backup all connect over the unix socket with `peer` auth as role `glasswell`. **The best-handled secret is the one that was never created** |
| Backup SSH key | `/root/.ssh/id_glasswell_backup` | `root:root` **0600** | Restricted `authorized_keys` on forge (§7.2) |
| App API keys | **PostgreSQL `api_keys` table, sha256 only** | — | §8.3 |

`/etc/glasswell/` is `root:glasswell 0750`. Nothing under it is world-readable. `infra/`
ships `*.env.example` templates only; the real files are rendered at install time and are
listed in `.git/info/exclude`.

### 8.2 In `rfxn-lab/.secrets/`

Per that repo's convention (`rfxn-lab/CLAUDE.md:18-22`, `dns.md:7`) **[V]**:

| File | Contents | Used by |
|---|---|---|
| `cloudflare.env` *(exists)* | `CF_API_TOKEN`, `CF_ZONE` for `rpx.sh` | DNS record creation from freedom (§11 steps 5, 20). **Stays on freedom** |
| `glasswell-access.env` *(new)* | `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET` for the `glasswell-agent` service token | Agent/API callers and the smoke tests. These are **client** credentials — the origin never needs them |
| `glasswell-apikey.env` *(new)* | The cleartext app API key issued to the agent, once | Agent callers. The origin holds only its sha256 |

Nothing glasswell-related goes into `rfxn-infra`'s Ansible vault: glasswell is not managed from
that repo (§9), and adding a PoC secret to the vault that guards production widens that vault's
blast radius for no benefit **[I]**.

### 8.3 App API keys — reuse the shape that already exists

Do not invent this. `rfxn-infra` already defines it and documents the lifecycle:
`vault.yml.example:42-48` stores `<sha256-of-token>  <label>` lines, and
`docs/runbooks/per-company-token-issuance.md` specifies `kind=intake` vs `kind=api`, labelled
issuance, "copy the cleartext token immediately — it is shown once and not stored in plaintext",
plus rotate (old auto-revoked at issuance of the new) and revoke **[V]**.

glasswell's version, in the `api_keys` table (SB-01 owns DDL):

| Column | Purpose |
|---|---|
| `key_id` | surrogate |
| `sha256` | **only** representation at rest — cleartext is never stored, never logged |
| `label` | `<consumer>-<purpose>-<year>`, e.g. `agent-mcp-2026` |
| `kind` | `api` (read) or `admin` (issue/rotate/ingest control). Coarse by design — per-row ACLs are the deferred multi-tenant work (blueprint §2.3) **[V]** |
| `created_at`, `revoked_at`, `last_used_at` | lifecycle + a usable revocation audit |

**Header only, never a query parameter.** responder states the reason in-source: a query-param
token "leaks through access logs and referrers"
(`responder/functions/api/team/admin/util.js:9`) **[V]**. Header name: `X-Glasswell-Key`.

Fail-safe: if no key rows exist, deny — never default-open
(`responder/functions/api/push/admin/util.js:1-4`) **[V]**.

### 8.4 Repo hygiene

`glasswell/.git/info/exclude` gains: `infra/**/*.env`, `infra/**/*.json` (except `*.example.json`),
`infra/**/*.key`, `infra/**/*.pem`. The existing `collateral` CI job already "rejects AI-assistant
attribution strings" (`glasswell/CLAUDE.md:79-81`) **[V]** — extend it with a grep gate that fails
on anything resembling a Cloudflare token, a private key header, or a `CF_ACCESS_CLIENT_SECRET=`
line with a non-empty value in `infra/`.

---

## 9. Config-as-code home — decision

**Decision: `glasswell/infra/` in the glasswell repo is authoritative.** `rfxn-lab` gets pointer
records only. `rfxn-infra` gets nothing.

```
glasswell/infra/
  README.md              what runs where; the VERIFY answers from §5.6; the AUD tag; team name
  cloud-init/
    user-data.yaml       packages, users, sshd, nftables, swap, guest agent
  systemd/
    glasswell-api.service  glasswell-martin.service  glasswell-backup.{service,timer}
    glasswell-ingest.{service,timer}  glasswell-alerts.{service,timer}
    glasswell-raw-verify.{service,timer}  glasswell-access-audit.{service,timer}
    glasswell-alert@.service
    cloudflared.service.d/override.conf
  caddy/Caddyfile
  cloudflared/config.yml.example
  postgres/{postgresql.conf.d/glasswell.conf,pg_hba.conf.fragment}
  env/{app.env.example,access.env.example,cf.env.example}
  forge/{vzdump-job.sh,vzdump-verify.sh,snapshot-glasswell.cron}
  install.sh             idempotent: render, place, chown, chmod, daemon-reload, enable
  verify.sh              the §11 negative tests, runnable any time
```

**Why not an `rfxn-infra` Ansible role:**

1. **OS-family mismatch is structural, not cosmetic.** `rfxn-infra/CLAUDE.md:20` states
   "RHEL-family only (AlmaLinux 10 / Rocky 9)" **[V]**. glasswell is Ubuntu 24.04 (DIR-7,
   and the best PostGIS/martin package availability **[I]**). Folding it in means forking
   `base`, `firewall` and `webserver` across two package managers, two firewall stacks and two
   service-name conventions — for one non-production host.
2. **State blast radius.** `tofu/quench.tf:16-19` guards the production origin with
   `prevent_destroy = true` **[V]**, and `rfxn-infra/CLAUDE.md:114` forbids apply from CI **[V]**.
   Attaching a PoC to that state raises the stakes of every `tofu apply` run from freedom.
3. **Explicit-not-recursive manifests are a known footgun there.** `rfxn-infra/CLAUDE.md:51-55`
   documents that new files under a managed directory silently do not ship and `require_once`
   dies on prod after a green playbook **[V]**. glasswell will add files continuously through
   P0-P7; that failure mode would fire repeatedly.
4. **Governance weight.** `rfxn-infra/CLAUDE.md:26-39` mandates an out-of-band deploy
   verification ritual for every change to that host **[V]**. Correct for a production origin,
   a tax on an exploratory build.

**Why not `rfxn-lab/services/glasswell/` as the authoritative home** (the assessment's
recommendation, §5.3 step 5 — this is a deliberate divergence):

`rfxn-lab/services/*` is documentation-shaped: `pw-bridge/` is a README only;
`pypowerwall-server/` is README + `docker-compose.yml` + `pw.env.example`;
`powerwall-monitor/` is README + Dockerfile + `app.py` + env example **[V]**. It is a fleet
*record*, not a deployment mechanism — it has no installer, no CI, and no test path
(`rfxn-lab/CLAUDE.md:3-5`: "Not a software project — no build system, no tests, no releases"
**[V]**).

**And the decisive argument:** blueprint §2.5.3 requires that "every artifact carries the recipe
that regenerates it byte-for-byte" **[V]**. A systemd unit that pins the uvicorn worker count, or
a `postgresql.conf` that pins `shared_buffers` and `work_mem`, **is part of that recipe** — the
same benchmark run under different `work_mem` is a different run. Splitting the recipe across two
repos destroys single-commit atomicity between an application change and the runtime parameter it
depends on, and makes "reproduce this number" a two-repo archaeology exercise. Under DIR-1, that
is indefensible.

**What `rfxn-lab` gets** (so the fleet record stays true — assessment step 23):

- `dns.md`: the two rows and the convention exception (§4.6).
- `CLAUDE.md:44`: the matching exception.
- `homelab.md`: VM 111 in the forge VM table, plus the §2.2 RAM rule.
- `services/glasswell/README.md`: ~20 lines — what it is, VMID, IPs, both URLs, where the
  Access app lives, the break-glass procedure, and **"deploy config lives in
  `glasswell/infra/` — this file is a pointer, not a source"**.

---

## 10. Monitoring & limits

Minimal and honest: there is no Prometheus in this lab that could be verified, so this does not
pretend there is one **[V — no monitoring stack found in `rfxn-lab`]**.

### 10.1 Host-level metrics

`glasswell-health.timer`, every 5 minutes, appends one line of `vmstat`, `df`, load, and
`pg_stat_activity` counts to `/var/log/glasswell/health.log` (logrotate, 30 days). Cheap,
greppable, and does not add a service to harden. If a real metrics stack ever lands on anvil,
`prometheus-node-exporter` bound to the LAN IP is the upgrade — a two-line change, not a
redesign.

### 10.2 Disk-space alarms

Two thresholds per filesystem, checked by the same timer, because the failure modes differ:

| Filesystem | WARN | CRIT | Why it matters |
|---|---|---|---|
| `/` (SSD, 150 G) | 75 % | 88 % | PGDATA + WAL live here. A full PGDATA is a hard PostgreSQL stop |
| `/srv/glasswell` (HDD, 1 T) | 80 % | 92 % | A full bulk zone corrupts an in-flight ingest — mitigated by the `.partial` rule (§3.3) |
| forge `hdd-pool` | 85 % | 92 % | Checked by the forge-side verify job; a full pool stops vzdump *and* the nightly push simultaneously |

CRIT additionally stops `glasswell-ingest.timer` — better to skip an ingest cycle than to fill
the disk mid-write.

### 10.3 Tunnel health

Two independent probes, because the interesting failure is "the tunnel process is alive and the
path is broken":

1. **On the VM:** `cloudflared` metrics on `127.0.0.1:20241/ready`, polled by the health timer.
   Plus `Restart=always` in the unit.
2. **From freedom (the one that matters):** a cron that curls
   `https://glasswell.rpx.sh/healthz` with the service-token headers from
   `rfxn-lab/.secrets/glasswell-access.env` and alerts on non-200. This exercises DNS, the
   Cloudflare edge, Access, the tunnel, Caddy and uvicorn in one request — the only probe that
   tests what the owner actually experiences.

### 10.4 Limits

**PostgreSQL:** `max_connections = 60`, `superuser_reserved_connections = 3`. Budget:
api pool 10 (+5 overflow), martin pool 10, ingest/batch 5, SB-01 migrations 5, human `psql` 3,
leaving ~19 headroom. Sized against the **balloon floor** (§2.3), not the ceiling.

**Origin rate limiting — and the gotcha that makes the obvious implementation useless:**

> Every request arrives at uvicorn from **127.0.0.1**, because cloudflared connects to Caddy over
> loopback. **IP-keyed rate limiting therefore puts the entire internet in one bucket.** **[I]**

Key on `principal.id` (§5.5) instead — the Access email or the service-token `common_name`.
Access has already established identity, so the limiter gets a strong key for free. Log
`Cf-Connecting-Ip` (forwarded by cloudflared) for forensics, but never key on it.

| Bucket | Limit | Reason |
|---|---|---|
| interactive (`owner`, `guest`) | 120 req/min | Generous for a map UI; catches a runaway client |
| `service` | 60 req/min | An agent should be deliberate; blueprint S5 is a 10-question suite, not a crawler |
| `/tiles/*` (any principal) | 600 req/min | Tiles are inherently bursty — a pan can issue 20-40 requests |
| global concurrency | 32 in-flight | Protects the <3 s scenario SLO (blueprint S3) from a valid-but-runaway caller |

Plus Cloudflare-side rate limiting on `/api/*` and `/tiles/*` as the outer layer (assessment
C10) — it costs residential upstream nothing because it rejects at the edge.

**Request caps at Caddy**, mirroring quench's hardening (`Caddyfile.j2:25-37`) **[V]**:
`read_header 10s`, `read_body 2m` (glasswell has no 2 GiB upload path — quench's 30 m is sized
for intake bundles and would be a slow-loris gift here), `write 60s`, `idle 60s`, and
`request_body { max_size 8MB }`.

---

## 11. Ordered execution runbook

Each step: what to run, and how you know it worked. **VERIFY** steps are gates — a gate that does
not pass stops the build; it is never assumed resolved. Estimated total: one focused day.

### Stage 0 — measure and verify (no changes made)

**1. VERIFY — measure forge's residential upstream. This is the placement gate.**

Run on forge (not in a VM), three samples, **at least one between 19:00 and 22:00 local**, since
evening congestion is when the owner will actually use it. This consumes ~300 MB of upstream.

```bash
command dd if=/dev/zero of=/tmp/gw-up.bin bs=1M count=100 status=none
for i in 1 2 3; do
  curl -s -o /dev/null -w '%{speed_upload}\n' -X POST \
    --data-binary @/tmp/gw-up.bin https://speed.cloudflare.com/__up
  sleep 30
done
command rm -f /tmp/gw-up.bin
```

Output is **bytes/s**; Mbps = `bytes_per_s * 8 / 1000000`. Measure against Cloudflare specifically
— the tunnel egresses to a Cloudflare POP, so a Cloudflare-path measurement is the representative
one **[I]**. Record the median of the three, and the evening sample separately.

**The gate — derivation, so the number is arguable rather than asserted:**

```
tiles per viewport change (deck.gl / MapLibre, typical desktop viewport)   ~20   [A]
median MVT tile size, 20k laterals with model-driven styling               ~50 KB [A]
payload per viewport change                                              ~1.0 MB
target time for a viewport change to feel interactive (blueprint S2)       1.5 s
  -> 5.3 Mbps per user mid-interaction
two concurrent users (owner + one guest; blueprint is not multi-user)     10.7 Mbps
TLS + QUIC/tunnel framing overhead, +15 %                                 12.3 Mbps
glasswell may claim at most 50 % of the household/lab uplink — the rest is
  freedom->forge backup pushes (capped 10 MB/s, PLAN.md:557 [V]), quench->forge
  cold archive (PLAN.md:538 [V]), and ordinary household use
  -> 24.6 Mbps  ==  THRESHOLD 25 Mbps sustained upstream
```

| Measured sustained upstream | Decision |
|---|---|
| **< 10 Mbps** | **HARD FAIL — trigger the Vultr fallback (§12) before building.** Below 10 Mbps a single 1 MB viewport refresh is ~0.8 s of pure transfer with zero headroom, two interacting users saturate the link, and every other lab transit competes directly. blueprint S2 (interactive frame rates) and S3 (<3 s scenarios) are not achievable through the tunnel |
| **10 - 25 Mbps** | **CONDITIONAL — proceed on forge**, with two mitigations mandatory before SB-05's map work: (a) confirm whether Access-gated responses are edge-cacheable (assessment U5, §5.6 item 10) and enable it for immutable tile paths if so; (b) if not, adopt the assessment's Option 4 static/PMTiles split for the basemap-ish layers. Tighten the `/tiles/*` bucket (§10.4) to 300 req/min |
| **>= 25 Mbps** | **CLEAR — proceed with no tile-specific mitigation** |

**Re-measure the assumptions at P1 exit.** The 20-tiles/50 KB figures are `[A]`. Once real ND
tiles exist, measure actual tile sizes and per-interaction request counts and revisit this table.
A threshold derived from estimates is a starting position, not a finding.

**2. VERIFY — Cloudflare Zero Trust first-time setup.** Work through all ten rows of §5.6. Write
each answer into `infra/README.md` as you go. Do not proceed with any unanswered row.

**3. VERIFY — forge RAM budget.** `qm list; free -g` on forge. Confirm 102 and 110 are `stopped`
with `onboot: 0`, and that committed RAM matches §2.2. Add the §2.2 rule to
`rfxn-lab/homelab.md`. Gate: the rule is written down before the VM exists, not after.

**4. VERIFY — the LAN IP is free.** Proposed `192.168.2.61`. Confirm it is unused and outside the
router's DHCP pool:

```bash
ping -c2 -W1 192.168.2.61          # expect 100% loss
arping -c3 -I vmbr0 192.168.2.61   # expect 0 replies
ip neigh | grep -w 192.168.2.61    # expect no output
```

Gate: all three negative, **and** the router's DHCP range checked by hand. A silent DHCP
collision surfaces weeks later as an intermittent outage.

### Stage 1 — DNS, name-first

**5.** Create `glasswell.lab.rpx.sh` A → `192.168.2.61`, **DNS-only (grey)**, TTL 300, using
`CF_API_TOKEN` from `rfxn-lab/.secrets/cloudflare.env` on freedom.
*Verify:* `dig +short glasswell.lab.rpx.sh` → `192.168.2.61`; the Cloudflare dashboard shows a
grey cloud. `dns.md:31` requires the record before deployment **[V]**.

**6.** Apply the §4.6 amendment to `rfxn-lab/dns.md` **and** `rfxn-lab/CLAUDE.md:44` in one commit.
*Verify:* `grep -rn "no bare" rfxn-lab/` shows the exception in both files.

### Stage 2 — VM and OS baseline

**7.** Create VM 111 with the §2.7 command block.
*Verify:* `qm config 111` shows `memory: 16384`, `balloon: 8192`, `onboot: 1`,
`agent: enabled=1`, `scsi0` on `ssd-pool` with `ssd=1`, `scsi1` on `hdd-pool` with `backup=0`.

**8.** `qm start 111`; watch first boot on `qm terminal 111`.
*Verify:* `ssh ryan@192.168.2.61` succeeds with the key, no password prompt.

**9.** Install the guest agent and baseline packages; reboot once.
*Verify:* **`qm agent 111 ping` returns from forge.** This is the §2.6 gate — do not proceed
without it. Then `qm shutdown 111 && qm start 111` and confirm uptime actually reset (the exact
check that failed on pw-bridge, `HANDOFF-powerwall.md:148-151` **[V]**).

**10.** OS baseline: `apt full-upgrade`, `unattended-upgrades`, timezone UTC, 4 GiB swapfile,
sshd key-only (`PasswordAuthentication no`, `PermitRootLogin no`), nftables default-deny inbound
with 22/80/443 open **to the LAN /24 only**, create the `glasswell` system user.
*Verify:* `sshd -T | grep -E 'passwordauthentication|permitrootlogin'`; `swapon --show` shows 4 G;
`nft list ruleset` shows no rule permitting a non-RFC1918 source.

**11.** Filesystems: `mkfs.xfs /dev/sdb`, mount at `/srv/glasswell` by UUID in `/etc/fstab` with
`noatime`, create the §3.1/§3.3 directory tree with correct ownership.
*Verify:* `findmnt /srv/glasswell` shows xfs + noatime; `df -h` shows ~1 T; a reboot re-mounts it.

**12.** Record the balloon behaviour baseline: `free -m` in the guest, `qm monitor 111` →
`info balloon` on the host.
*Verify:* the guest sees ~16 G and the balloon device is present. If the guest reports a fixed
8 G, `--balloon` was misread as the ceiling — stop and fix (§2.3).

### Stage 3 — data services

**13.** PostgreSQL 16 + PostGIS 3.4. Set `listen_addresses = ''`, `shared_buffers = 2GB`,
`effective_cache_size = 6GB`, `max_connections = 60`, `full_page_writes = on`. Create role
`glasswell` (peer) and db `glasswell`; create tablespace `bulk` at `/srv/glasswell/pgbulk`.
*Verify:* `ss -ltnp | grep 5432` returns **nothing**; `psql -U glasswell -d glasswell -c '\dx'`
works over the socket and lists postgis; `psql -c "\db"` lists `bulk`.

**14.** martin, pinned release binary to `/usr/local/bin` with a recorded sha256; unit per §6.
*Verify:* `curl -s 127.0.0.1:3000/health` → 200; `ss -ltnp | grep 3000` shows 127.0.0.1 only.

**15.** Deploy target + **a stub API**: `/opt/glasswell` venv, a FastAPI app whose only route is
`GET /healthz` → `{"ok": true}` behind the §5.3 dependency, `glasswell-api.service` per §6.
*Verify:* `curl -s 127.0.0.1:8000/healthz` → **403** (no JWT, no LAN header — fail-closed is the
correct answer here and proving it now is the point).

### Stage 4 — reverse proxy

**16.** Caddy (custom build with `caddy-dns/cloudflare`, §4.5), `/etc/caddy/cf.env` with the
zone-scoped token, the two site blocks from §4.5, security headers, §10.4 caps.
*Verify:* `caddy validate --config /etc/caddy/Caddyfile`;
`curl -sk https://glasswell.lab.rpx.sh/healthz` from the LAN → **200** (LAN header set);
`curl -s -H 'X-Glasswell-Origin: lan' http://127.0.0.1:8080/healthz` → **403** (the tunnel block
stripped it). Both assertions in one step — the second is the security property.

### Stage 5 — tunnel

**17.** On **freedom**: `cloudflared tunnel login`, authorise the `rpx.sh` zone. The account
`cert.pem` stays on freedom (§8.1).

**18.** On **freedom**: `cloudflared tunnel create glasswell`. Record the UUID. Copy **only**
`<uuid>.json` to VM 111 at `/etc/cloudflared/`, `chown cloudflared:cloudflared`, `chmod 0600`.
*Verify:* `cloudflared tunnel list` shows `glasswell`; the JSON on the VM is 0600 and the
account cert is **not** present (`ls /etc/cloudflared` shows exactly two files).

**19.** Install `cloudflared` on the VM, write `/etc/cloudflared/config.yml` (§4.4), apply the
non-root drop-in (§6.2), enable and start.
*Verify:* `systemctl show cloudflared -p User` → `cloudflared`;
`curl -s 127.0.0.1:20241/ready` → healthy; `journalctl -u cloudflared` shows registered
connections to ≥ 2 edge locations.

**20.** Create the proxied CNAME `glasswell.rpx.sh` → `<uuid>.cfargotunnel.com` (orange).
*Verify:* `dig +short glasswell.rpx.sh` returns Cloudflare anycast addresses (not the
`cfargotunnel.com` name — proxied records resolve to the edge); the dashboard shows orange.
`curl -sI https://glasswell.rpx.sh/healthz` now returns something **from Cloudflare**. It should
**not** yet return 200 — Access is not configured, so this is expected to reach the origin.
That is precisely why step 21 happens immediately and not later.

### Stage 6 — Access

**21.** Create the Access application: self-hosted, `glasswell.rpx.sh`, **path `*`**, session
24 h. **Record the AUD tag.**
*Verify:* an off-Access `curl -sI https://glasswell.rpx.sh/healthz` now returns a redirect to the
Cloudflare login page. The window between step 20 and here is the only moment the origin is
reachable unauthenticated — keep it to minutes and do not walk away in between.

**22.** Policy 1 `owner`: Allow, Include → Emails → `rfxnryan@gmail.com`.
*Verify:* browse to `https://glasswell.rpx.sh/healthz` from off-LAN, complete login, receive
`{"ok": true}`. Confirm the login event appears in Zero Trust → Logs → Access.

**23.** Policy 2 `agent-api`: **Service Auth**, Include → Service Token → create
`glasswell-agent`. Store client id/secret in `rfxn-lab/.secrets/glasswell-access.env`.
Write the team name and AUD tag into `/etc/glasswell/access.env`; restart `glasswell-api`.
*Verify:*
```bash
curl -s -o /dev/null -w '%{http_code}\n' https://glasswell.rpx.sh/healthz \
  -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
  -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}"   # expect 200
curl -s -o /dev/null -w '%{http_code}\n' https://glasswell.rpx.sh/healthz  # expect 302 or 403
```

### Stage 7 — backup, before any data exists

**24.** On forge: `hdd-pool/vzdump` dataset, `vzdump-hdd` storage, the weekly job (§7.1). Run it
once by hand now.
*Verify:* an archive exists in `/hdd-pool/vzdump/dump/`; the §7.1 verify script prints `OK`.

**25.** On forge: `hdd-pool/backups/glasswell` dataset + daily snapshot cron + the restricted
`authorized_keys` entry for the VM's backup key (§7.2).
*Verify:* from the VM, `rsync` a test file in — succeeds; `ssh forge 'ls /'` with the same key —
**fails** (the forced command is doing its job).

**26.** On the VM: `glasswell-backup.{service,timer}`; run once with
`systemctl start glasswell-backup.service`.
*Verify:* `forge:/hdd-pool/backups/glasswell/pgdump/` holds a dump and a globals file;
`zfs list -t snapshot hdd-pool/backups/glasswell` shows today's snapshot after the cron hour.

**27. Restore test #1 — before regulator data lands.** `pg_restore` the dump into
`glasswell_restoretest`, confirm extensions and (empty) schema restore cleanly, drop it.
*Verify:* zero errors. §7.4's rationale: a restore path proven after the irreplaceable data
exists is not a proven restore path.

### Stage 8 — verify the negative, then hand off

**28.** Unauthenticated, from a network outside the LAN and outside any Access session, for
**every** class of path: `/`, `/healthz`, `/api/…`, `/tiles/0/0/0`, `/conformance`.
*Verify:* every one returns a Cloudflare login redirect or 403. **Zero return 200.** Record the
output — this is assessment C17 and responder's strip-and-verify habit
(`ARCHITECTURE.md:137-139`) **[V]**.

**29.** Header-spoof negative: through the tunnel, from outside, with a valid service token,
send `X-Glasswell-Origin: lan`.
*Verify:* the response is identical to the run without the header — the Caddy strip (§4.5) held.
This test is the reason the single-process design is acceptable; keep it in `infra/verify.sh`.

**30.** WAN port scan of the residential IP from outside.
*Verify:* no new listening port versus the pre-build baseline. Take the baseline **before**
step 7 so the comparison is meaningful.

**31.** Break-glass drill: `systemctl stop cloudflared`.
*Verify:* `https://glasswell.lab.rpx.sh/healthz` from the LAN → 200;
`https://glasswell.rpx.sh/healthz` → a Cloudflare edge error, not an app response.
`systemctl start cloudflared`, confirm recovery.

**32.** Guest roundtrip: add `guest-test-expires-<tomorrow>` for a throwaway address, log in via
one-time PIN from a clean browser profile, confirm access, **delete the policy**, confirm the next
request is denied and the existing session does not survive.
*Verify:* both halves. Testing only the grant proves half a control (workspace rule: CLI
operations must be symmetric — test with a roundtrip).

**33.** Enable the freedom-side tunnel-health cron (§10.3), the health/disk timers, and the
`glasswell-raw-verify` / `glasswell-access-audit` timers.
*Verify:* `systemctl list-timers 'glasswell-*'` shows all with a next elapse.

**34.** Write the record: `rfxn-lab/services/glasswell/README.md` (pointer form, §9),
`homelab.md` VM table + RAM rule, and the §5.6 VERIFY answers into `glasswell/infra/README.md`.
Commit `glasswell/infra/` in full.
*Verify:* `grep -rn "glasswell" rfxn-lab/*.md` shows dns, homelab and services entries; the
glasswell repo has no file matching `infra/**/*.env` staged.

---

## 12. Vultr fallback delta

Triggered by step 1 measuring **< 10 Mbps** sustained upstream, or by forge RAM becoming
unavailable. Everything in §3, §5, §6, §8, §9, §10 is unchanged — **only placement moves.**
That is the point of putting the config in `glasswell/infra/` (§9): the fallback is a
placement change, not a rewrite.

| Area | Delta |
|---|---|
| Provisioning | `rfxn-infra/tofu/glasswell.tf`, mirroring `quench.tf`'s 20-line shape **[V]**. Omit `prevent_destroy` — the guard exists for *imported production* resources (`rfxn-infra/CLAUDE.md:115` **[V]**); a PoC has real destroy intent. Consider a separate tofu workspace so the PoC does not share the state file that guards production (`tofu/backend.tf` **[V]**) |
| Sizing | `var.default_plan` = `vhp-8c-16gb-amd` in `dfw` **[V]** matches DIR-7's 8 vCPU / 16 GB. Ballooning does not exist in the cloud — the guest gets a fixed 16 GB, so §2.3's "size Postgres against the floor" becomes "size against 16 GB": `shared_buffers = 4GB` |
| OS | `var.default_os_id` is AlmaLinux 10 **[V]**. Override to Ubuntu 24.04 to keep the stack identical, which **breaks** `rfxn-infra/CLAUDE.md:20`'s RHEL-family-only rule **[V]** — so document a scoped exception, or use Rocky 9 (arena's OS, `docs/runbooks/gameserver.md:12` **[V]**) and accept re-testing PostGIS/martin packaging. Recommendation: Ubuntu + documented exception; re-validating the stack costs more than the exception does **[I]** |
| Bulk storage | The plan's included NVMe (~360 GB **[A]**) does not hold 1 TB of raw zone + Parquet. Add a Vultr Block Storage volume, ~500 GB, mounted at `/srv/glasswell`. §3's layout is otherwise unchanged |
| Break-glass | **Lost.** There is no LAN. `glasswell.lab.rpx.sh` does not exist, and §4.5's `X-Glasswell-Origin` marker has no listener to originate it. Replace with: SSH restricted by APF's deny-by-default allowlist + DDNS-FQDN pattern with the 10-minute `apf -r` re-resolve (`firewall/tasks/configure.yml:89-97`, `host_vars/quench.rfxn.com.yml:16-23` **[V]**), and accept that the *application* has no non-Cloudflare path. This is a genuine reduction in resilience — Cloudflare becomes a hard single point of failure for all access, not just remote access |
| Backups | No vzdump, no `hdd-pool`. Vultr instance snapshots (paid) for layer A; layer B inverts — the nightly push goes **to forge** (a download for forge, so residential upstream is not the constraint) into the same `hdd-pool/backups/glasswell` dataset. Data gravity flips: ingest gets faster, backup egress becomes metered |
| Firewall | APF joins the stack (`ansible/playbooks/site.yml` **[V]**), and its deny-by-default allowlist becomes load-bearing rather than a nicety. Note `rfxn-infra/CLAUDE.md` records that allowlist edits risk operator lockout — keep `apf_devel_mode: 1` on this host, unlike quench's production lock (`host_vars/quench.rfxn.com.yml:26-30` **[V]**) |
| Cost | Instance ~$96/mo ≈ **$1,150/yr** **[A]**. **The assessment's ~$1.1k/yr figure covers the instance only** (`assessment-infra.md:344-347`) — it omits the block storage the raw zone requires: ~500 GB at ~$0.10/GB/mo ≈ $50/mo ≈ **$600/yr** **[A]**. Realistic total **~$1.75k/yr**, plus bandwidth-overage exposure. All `[A]` — verify against current Vultr pricing before committing spend |
| Also inherited | Vultr blocked outbound port 25 until it was unblocked for quench (`rfxn-lab/HANDOFF.md` Phase 0 **[V]**) — a new instance inherits provider-level policy friction |

The hybrid escape valve (assessment Option 4: static frontend on Cloudflare Pages, origin behind
the tunnel) remains available **independently** of this fallback and is the cheaper first move if
the problem turns out to be tile bandwidth specifically rather than transit generally. It is
explicitly *not* initial scope (`assessment-infra.md:408-411`).

---

## 13. Divergences, corrections and open items

**Divergences from `assessment-infra.md`** (deliberate, with reasons):

| # | Assessment said | SB-06 says | Why |
|---|---|---|---|
| D1 | §5.3 step 5: config home = `rfxn-lab/services/glasswell/` | `glasswell/infra/` | `rfxn-lab/services/*` is documentation-shaped with no installer, no CI, no tests **[V]**; and blueprint §2.5.3 byte-for-byte reproducibility requires runtime parameters to version with the code (§9) |
| D2 | §5.1: "#1 pre-build action" is anvil's balloon floor or trimming arena | No action needed now | Superseded by DIR-7 — pw-bridge and arena are already stopped and `onboot: 0` **[V]**. The constraint returns only if arena returns; §2.2 records the rule |
| D3 | §5.2 offered naming options (a)/(b) as an owner decision | Settled: `glasswell.rpx.sh` | DIR-6 decided it; §4.6 supplies the amendment text |
| D4 | Cost of the Vultr escape hatch ≈ $1.1k/yr | ≈ $1.75k/yr | The assessment costed the instance only; the raw zone needs block storage (§12) |
| D5 | §5.3 step 1: re-open Option 2 below ~10 Mbps | 10 Mbps hard fail, **25 Mbps** clear, 10-25 conditional-with-mitigations | A single threshold hides the middle case, which is the likely one. §11 step 1 shows the arithmetic |

**Corrections to inputs:**

- **The brief's "pw-bridge lacked a guest agent" is imprecise.** VM 102 has `agent: enabled=1`
  in its Proxmox config **[V]**; the missing piece was the **in-guest package**, with the host
  flag set and misleading (`HANDOFF-powerwall.md:148-151` **[V]**). The lesson is therefore
  "verify `qm agent <id> ping`, not `qm config`" — §2.6, gated at §11 step 9.
- **The assessment's "anvil — ballooning enabled (no `balloon: 0`)" is technically incomplete.**
  With `balloon` unset it defaults to `memory`, so the device exists but never reclaims **[V/I]**.
  Any future "set anvil's floor to 8 GB" action is `qm set 101 --balloon 8192`, not a no-op
  confirmation.
- **The brief's "the raw zone is re-fetchable from regulators" is false for two of four
  sources.** DIR-9 establishes NM OCD's nightly undated refresh and TX RRC's opaque-GUID portal
  **[V]**; combined with DIR-2's vintage-bearing observations, a lost vintage is a permanent hole.
  §7.3 states RPO accordingly, and this is the strongest justification for the whole backup design.

**Carried VERIFY gates** (never assumed resolved; each is a numbered gate in §11):

| Gate | Item | Step |
|---|---|---|
| G1 | Residential upstream bandwidth (assessment U2) | 1 |
| G2 | Zero Trust account topology, team name, Free-plan feature set, OTP, Service Auth, policy-expiry fields, Access evaluation precedence (assessment U3, U4) | 2 (§5.6, ten rows) |
| G3 | Whether Access-gated responses are edge-cacheable (assessment U5) | 2, row 10 |
| G4 | Universal SSL one-label-deep limit, as DIR-6 asserts | 2, row 8 |
| G5 | `192.168.2.61` free and outside the DHCP pool | 4 |
| G6 | In-guest qemu-guest-agent actually responds | 9 |
| G7 | Balloon floor behaves as floor, not ceiling | 12 |
| G8 | Caddy build includes `caddy-dns/cloudflare` | 16 |
| G9 | The `X-Glasswell-Origin` strip holds through the tunnel | 16, 29 |

**Flagged for separate tasks (explicitly out of SB-06 scope):**

1. **forge `freedom-zfs-snap` cron silent for 48 days** and the `freedom → forge` chain behind it
   (§7). Cron is `active`, the entry is present and correct, the newest snapshot is 2026-07-03,
   the journal has no matching entries **[V]**. Org-wide data-protection gap, predates glasswell.
2. **`homelab.md` drift:** still documents `lab.rfxn.com` (`:87-108`) where `dns.md` and
   `rfxn-lab/CLAUDE.md` establish `lab.rpx.sh`; documents `scope` and `vault` VMs that do not
   exist; omits `pw-bridge`, `arena` and `usb-pool`; and its §"VM resource budget" (`:274-285`)
   claims ~12 GB headroom against a live figure of ~6 GB at ceiling **[V]**.
3. **`usb-pool` (9.09 T, healthy, empty) is undocumented** and contradicts `homelab.md:349`'s
   standing USB-ZFS prohibition **[V]**. Decide its sanctioned role (§7.1 proposes
   replication-target-only) and reconcile the doc.
4. **DDNS client for `home.lab.rpx.sh` has no located host** (assessment U9) **[V]**. Not
   blocking for glasswell — the tunnel makes the WAN IP irrelevant — but load-bearing for
   quench's APF path-in, and load-bearing for §12 if placement ever flips.

---

## Appendix A — live read-only reconnaissance, 2026-08-20

All read-only; nothing was modified. Run against `root@192.168.2.205` (forge) over SSH with
`BatchMode=yes`:

```
hostname; qm list; free -g
qm config {100,101,102,110}
zpool list; zfs list -o name,used,avail
zfs list -t snapshot -s creation -o name,creation | tail -5
cat /etc/pve/storage.cfg
qm help | grep -E 'disk import|disk resize'
ls -la /var/lib/vz/template/iso; file /var/lib/vz/template/iso/noble-cloudimg.img
zfs get volsize,refreservation,volblocksize ssd-pool/vm-101-disk-0
pvesh get /cluster/nextid; ls /etc/pve/jobs.cfg; cat /etc/cron.d/vzdump
crontab -l; ls /etc/cron.d/; systemctl is-active cron
journalctl -t freedom-zfs-snap --since '60 days ago'
pveversion; uptime; ip -br a
```

Notable results: VM 102 and 110 `stopped` / `onboot: 0`; `free -g` available **31**, swap **0**;
`pvesh get /cluster/nextid` → **103**; `/etc/pve/jobs.cfg` absent; `/var/lib/vz/dump` empty;
newest snapshot on the box **2026-07-03**; `noble-cloudimg.img` is a QCOW2 v3 Ubuntu 24.04 cloud
image; `qm disk import` / `qm disk resize` both present; neither `ssd-pool` nor `hdd-pool` sets
`sparse`; forge uptime 1:08 at time of check.

## Appendix B — primary citations

**glasswell:** `blueprint.md` §1.3, §2.3, §2.4 (S2, S3, S5), §2.5.1-.3, §3.0.1, §3.5, §3.2 (C23),
§8.1 item 5, §8.2; `CLAUDE.md:23-24, 79-81`; `work-output/direction-log.md` DIR-1, DIR-4, DIR-6,
DIR-7, DIR-9; `work-output/assessment-infra.md` §0, §1.2, §1.3, §3, §4 (C1-C18), §5.1-5.3, §6.

**rfxn-lab:** `dns.md:1-7, 13-24, 26-32, 34-43`; `CLAUDE.md:3-5, 18-22, 36-44, 75-77`;
`homelab.md:164-190, 235-285, 349`; `PLAN.md:46-47, 538, 557`; `HANDOFF.md` Phase 0;
`services/{pw-bridge,pypowerwall-server,powerwall-monitor}/`.

**rfxn-infra:** `CLAUDE.md:20-21, 26-39, 51-55, 114-115`; `tofu/quench.tf:1-20`;
`tofu/variables.tf:1-16`; `tofu/backend.tf`; `ansible/playbooks/site.yml`;
`ansible/inventory/host_vars/quench.rfxn.com.yml:16-30`;
`ansible/inventory/group_vars/all/vault.yml.example:42-48`;
`ansible/roles/webserver/templates/Caddyfile.j2:1-45`;
`ansible/roles/firewall/tasks/configure.yml:89-97`;
`docs/runbooks/per-company-token-issuance.md`; `docs/runbooks/gameserver.md:12`;
`HANDOFF-powerwall.md:142-160`.

**responder:** `ARCHITECTURE.md:137-139`; `_headers:34-41`;
`functions/api/team/admin/util.js:4-10`; `functions/api/push/admin/util.js:1-8`.
