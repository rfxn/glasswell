# Basemap — build and serve

The basemap is a self-hosted [Protomaps](https://protomaps.com) PMTiles extract read over
HTTP range requests from this app's own origin. There is no API key, no third-party tile
endpoint, and no service contract — only a licence (ODbL for the OSM data, BSD for the
Protomaps software) and a checksummed file, which is the same shape as every other source
in the manifest.

## The region is a coverage decision, not a size decision

A reader zooms out. Every zoom level below the one the data lives at asks for tiles the
extract may not contain, and a missing tile is not an error — it is blank ground with no
message anywhere. The `nd-tx` extract shipped exactly that: at z3–z7 the map ended at the
Rockies and at Memphis, because those are the edges of the two basin boxes.

```
z5/5/11 California   nd-tx  0 B      conus  69,443 B
z5/9/11 Maine        nd-tx  0 B      conus  58,039 B
z6/12/23 Utah        nd-tx  0 B      conus  35,785 B
z4/3/5  North Dakota nd-tx  63,149 B conus  63,149 B   (identical — no detail was traded)
```

So the serving extract is **`conus`**, and the basin regions are inputs to it rather than
serving artifacts. `tests/unit/test_basemap_regions.py` asserts `conus` contains every one
of them, which is what makes the swap incapable of losing coverage.

## Build

The extract pulls from `build.protomaps.com` and the CONUS archive is 4.2 GB, so build it
wherever there is disk and bandwidth — that is the VM, not a laptop:

```bash
# Not a fixed /tmp path: two agents building at once would overwrite each other, and 4.2 GB
# is far more than a tmpfs /tmp wants (N-3).
build_dir="$(mktemp -d -t gw-basemap.XXXXXXXX)/basemap"
scripts/basemap-build.sh --region conus --maxzoom 13 --with-labels --out "$build_dir"
```

Measured against the 2026-08-17 planet build (`--dry-run`, no download):

| region  | z0–9 | z0–10 | z0–11 | z0–12 | z0–13 |
|---------|------|-------|-------|-------|-------|
| `nd`    | — | ~6 MB | — | 22 MB | 48 MB |
| `nd-tx` | — | 24 MB | — | 138 MB | 336 MB |
| `conus` | 155 MB | 380 MB | 826 MB | 1.9 GB | **4.2 GB** |
| world   | — | — | — | — | 45 MB at z0–6 · 187 MB at z0–7 |

Label assets (three Noto Sans stacks plus the dark and grayscale sprites) add ~14 MB.

Each zoom level roughly doubles the archive, so project from a low-maxzoom `--dry-run`
before committing to a size. z13 is the right ceiling: a lateral is legible well before
street-level detail matters. A two-archive scheme (world at z0–6, `conus` at z7–13) would
save ~3.9 GB and cost a MapLibre source change; at 4.2 GB against 1 TB of free disk, one
archive and no client change is the better trade.

The build is a long download over one CDN connection and has been reset by the edge
mid-transfer. Wrap it in a retry rather than watching it:

```bash
for try in 1 2 3; do
    scripts/basemap-build.sh --region conus --maxzoom 13 --with-labels --out "$build_dir" && break
    rm -f "$build_dir/basemap.pmtiles.new"
done
```

## Deploy

Swap the symlink, not the directory: the rename is atomic, the previous archive stays
readable, and rolling back is the same command with the old target.

```bash
# $build_dir from the build step above, staged onto the VM under /data
mv "$build_dir" /data/basemap-<region>-<vintage>
chown -R glasswell:glasswell /data/basemap-<region>-<vintage>
(cd /data/basemap-<region>-<vintage> && sha256sum -c MANIFEST.sha256)
ln -sfn /data/basemap-<region>-<vintage> /opt/glasswell/basemap.new
mv -T /opt/glasswell/basemap.new /opt/glasswell/basemap
```

No service restart is needed: Caddy resolves the symlink per request and uvicorn's mount
does the same. Keep the previous directory until a ranged GET and a zoom-out both verify.

`GLASSWELL_BASEMAP_ROOT=/opt/glasswell/basemap` in `/etc/glasswell/app.env` is what mounts
it in uvicorn; the Caddy handler roots on the same path. The directory holds:

```
basemap.pmtiles      the archive
manifest.json        vintage, sha256, bounds, region, maxzoom, whether labels are present
MANIFEST.sha256      `sha256sum -c` passes here with no arguments (SB-06 §rules 1-2)
fonts/               only when built --with-labels
sprites/             only when built --with-labels
```

`bounds` is in the manifest because the coverage claim has to be readable without opening
the archive — a too-narrow extract was invisible until someone zoomed out and looked.

## Serving

uvicorn's `StaticFiles` mount **does** answer range requests with a `206` — verified in
`tests/unit/test_basemap_mount.py`, which is the check that keeps this claim true. No
reverse proxy is required for the basemap to work.

The client refuses the archive unless a ranged GET returns exactly `206`
(`web/src/map/map.ts`, `archiveServesRanges`). A server that ignores `Range` and returns a
whole `200` would make every tile read pull the entire archive, so that case falls back to
OpenFreeMap rather than quietly costing 4.2 GB per read.

Both paths apply the same cache classes: `public, max-age=86400` on everything under
`/basemap/`, except `manifest.json`, which stays `no-cache` because it is how the client
notices a vintage swap. A swapped archive is therefore visible to a fresh session
immediately and to a warm cache within a day.

## Why Caddy serves this directly

Since the TLS cutover the request path is browser → Caddy → uvicorn, and that second hop
costs **~40 ms on every read smaller than 64 KB**. It is not Python and it is not the
filesystem:

- `uvicorn --workers N` (N > 1) creates its listening socket in `Config.bind_socket()` as
  `socket.socket(family=family)` — `proto` defaults to `0`, not `IPPROTO_TCP`.
- An accepted socket inherits that `proto`, and `asyncio.base_events._set_nodelay` only sets
  `TCP_NODELAY` when `sock.proto == socket.IPPROTO_TCP`. So **Nagle stays on**.
- uvicorn writes response headers and body as two `transport.write()` calls. On loopback the
  MSS is 65,483, so any body under that is a "small" segment held until the peer's delayed
  ACK — 40 ms later, every time, on every keep-alive request after the first.

`tcpdump -i lo` on the live service, second request of a keep-alive sequence: headers at
`t+0.1048`, the client's ACK at `t+0.1453`, the 4 KB body at `t+0.1453`. The same app run
with `--workers 1` (which takes the `create_server(host, port)` path, where `getaddrinfo`
supplies `proto=6`) sends the body 0.23 ms after the headers.

PMTiles reads are mostly directory and tile reads well under 64 KB, so the basemap paid this
on nearly every request. Measured from the LAN through `https://`, same archive:

| 64 KB tile ranges, LAN, one connection | via uvicorn | Caddy `file_server` |
|---|---|---|
| 4 KB range, sequential median | 48.7 ms | **5.9 ms** |
| 16 KB range, sequential median | 49.0 ms | **6.4 ms** |
| 64 KB range, sequential median | 9.4 ms | **6.2 ms** |
| 16 KB range, 8 concurrent, median | 49.6 ms | **7.6 ms** |

So `infra/caddy/Caddyfile` serves `/basemap/*` from a `handle_path` block with `root` +
`file_server`, and the uvicorn mount stays exactly where it was. Reverting the Caddy block
restores the proxied path with no other change, which is the only rollback this needs.

`scripts/tile-probe.py` is the tool those numbers come from; re-run it before changing
anything here. The same defect is still on **every proxied path** — `/v1/*` JSON and the
z≥10 vector tiles both sit under the 64 KB line — and the fix for those is upstream in
uvicorn or a `--uds` socket, not here.

A reverse proxy in front must preserve `Range`, `Accept-Ranges` and the `206`, and must not
buffer. Caddy's `file_server` does all three; `tests/unit/test_caddy_basemap_headers.py`
keeps the response policy identical between the two paths.

## Refresh cadence

Quarterly is generous for a basemap. Re-extract to a new directory and swap it in; do not
edit an archive in place. A client that is mid-session during a swap re-reads directory
offsets against new bytes, so swap during a quiet window or reload the page afterwards.

Record the `sha256` and `vintage` from `manifest.json` alongside the NDIC and DMR inputs
when the basemap enters the source manifest.

## What the client does when the archive is absent

1. `/basemap/manifest.json` is read; a missing manifest is a normal pre-deploy state.
2. A ranged GET of the archive must return `206`.
3. Otherwise the dark and light options fall back to OpenFreeMap (`positron` / `dark`,
   keyless, attribution required, no SLA) and a banner names what failed and what replaced
   it.
4. If that is unreachable too, the map draws the one-degree graticule, which is also the
   `?base=none` option a reader can choose deliberately.
