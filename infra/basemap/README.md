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
whole `200` would make every tile read pull the entire archive, so that case degrades to the
graticule rather than quietly costing 4.2 GB per read.

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
3. Otherwise the map draws the one-degree graticule — the same view `?base=none` offers
   deliberately — and a banner names what failed and what replaced it.

**There is no hosted runtime fallback, and this is deliberate.** The client used to reach for
`https://tiles.openfreemap.org` at step 3, and it had never once worked on any stack we run:
`connect-src 'self'` refuses it, which is the correct zero-external posture and is not being
widened for a fallback. A fallback the security policy forbids is not a recovery — it is a
second failure mode wearing the label of one, and it made the failure banner promise the reader
a substitute they could not receive. The degradation is now local, which means it works.

### OpenFreeMap as an operator step

If an operator decides to run against a hosted basemap — a demo before the archive is built, or
a stack where the archive genuinely cannot be served — it is a deliberate, documented change,
not something the browser does on its own:

1. Add `https://tiles.openfreemap.org` to `connect-src` in `glasswell.api.security`, **and** to
   the Caddy restatement of the same header, which must not drift from it.
2. Point the vector style at `https://tiles.openfreemap.org/styles/{dark,positron}` (keyless,
   attribution required, no SLA).
3. Understand what has been given up: the map now depends on someone else's uptime, and the
   app's origin is no longer the only origin a reader's browser talks to.

Steps 1 and 2 together are the whole change. Neither belongs in the shipped default.

## Satellite imagery, and the one origin the policy names

The satellite option is Esri World Imagery — keyless, and inherently somebody else's origin.
`glasswell.api.security` allow-lists exactly `https://services.arcgisonline.com` in
`connect-src` and `img-src`, by name and never as a wildcard. Nothing else external is
allowed, and the dark, light and none options remain provably zero-external
(`web/src/map/map.test.ts`). Terms of use are the owner's call, not this document's; what is
engineering's to get right is that the credit the service declares actually renders.

The requests happen only when a reader selects satellite or hybrid, and on **both** paths the
client asks the origin for one tile before committing to it: if that tile does not arrive —
the origin is down, the policy refuses it, the network is gone — satellite degrades to the
graticule and the hybrid keeps its labels over the app canvas. Either way the imagery source
is not added, so the imagery credit goes with it: an attribution over a canvas with no imagery
on it is a false statement about what was drawn.

Dropping the source is also what makes that probe mandatory rather than an optimisation. A
source MapLibre is never handed requests no tile and so raises no `error`, which leaves the
tile-error handler with nothing to report. The resolve path names the host itself instead —
and on the hybrid it names it without promising a substitution, because none was made.

Adding a second imagery origin means adding it to that allow-list in the same change. If the
list ever needs to exceed two hosts, that is a decision to take deliberately, not a widening
to slip in with a basemap.

### The zoom ceiling is measured per region, and there is no global one

The service advertises 24 levels and declares no `maxScale`. It does not have 24 levels of
imagery anywhere, and **it does not stop at the same level in two places.** Above wherever it
stops it answers `200` with a grey "Map data not yet available" placeholder — 2,521 B, md5
`f27d9de7f80c13501f470595e327aa6d` — not a `404`, so nothing in the client can tell that
apart from imagery.

Probed 2026-08-23, one tile per location per level, two passes with identical results:

| location | deepest level with real pixels | notes |
|---|---|---|
| Bakken — Watford City, Alexander, Killdeer, Tioga, New Town, rural McKenzie | **z19** | placeholder at z20 |
| Permian — Midland, Odessa, Pecos, Carlsbad, Big Spring, Loving Co | **z19** | placeholder at z20 |
| rural Nevada | z19 | placeholder at z20 |
| Brasilia · Amazon interior | z19 | placeholder at z20 |
| Denver CO · Dawson City YT | **z20** | deeper than the basins get |
| Utqiagvik AK | z18 | **placeholder at z19, real again at z20** — not monotonic |
| Inuvik NT · Sahara interior · central Australia | **z17** | placeholder from z18 up |

So the shortfall is neither global nor a fixed offset from CONUS: across this sample the
deepest usable level ranges **z17 to z20**, and at Utqiagvik a level that fails is bracketed
by two that work. "Ceiling" is the wrong model — coverage is per location per level.

`maxzoom` is therefore declared as **19** because that is what the twelve in-basin sites
carry, not because the service stops there. That declaration is load-bearing in the same way
the previous source's was: a source's `maxzoom` is what stops MapLibre requesting tiles above
it, so it overzooms real imagery instead of painting a placeholder across the basin.

**Adding a region means re-probing it.** A region whose imagery stops at z17 will paint the
grey placeholder from z18 to the map's own `maxZoom` with no error anywhere:

```bash
E=https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile
# {z}/{y}/{x} — MapServer writes row before column.
for t in 19/182680/111730 19/213013/106957 20/182680/111730; do curl -sS "$E/$t" | md5sum; done
```

## The hybrid: imagery with the archive's own labels over it

The hybrid option draws the same imagery with the symbol layers of the PMTiles archive
composited on top. **It adds no origin and no key**: the labels are the ones already in
`basemap.pmtiles`, served from this app's own origin, and the glyphs and sprites are the
assets `--with-labels` already ships.

It is declared `kind: "vector"` even though it draws raster imagery, and that is deliberate:
only the vector branch of `resolveStyle` registers the `pmtiles://` protocol and requires the
archive's `206`. A raster-kinded hybrid would hand MapLibre a `pmtiles://` url through a
protocol nothing had registered, and would do so only for readers whose first basemap of the
session was the hybrid.

**Two substrates, two independent failure modes, and they are not the same failure:**

| what fails | what the reader gets | what names it |
|---|---|---|
| the archive (no `206`) | the graticule | the banner, naming the archive path |
| the imagery | labels and data over the app canvas | the banner, naming the imagery host |
| the archive has no label assets | imagery alone, as the satellite option | nothing — this is a deploy state, not a fault |

The imagery source carries its own MapLibre source id, which is what lets a tile error be
attributed to the imagery rather than to the archive that happens to share the style.

**Three zoom ceilings meet in this option.** Labels come from an archive capped at z13,
imagery in these basins stops at z19, and the map's own `maxZoom` is 19 to reach it.
Overzooming a raster stretches finished pixels; overzooming a vector re-renders geometry and
re-rasterises glyphs, so past z13 the labels lose *content*, never sharpness. What the reader
sees:

| zoom | imagery | labels |
|---|---|---|
| z13 | native | native — the last zoom with new label content |
| z16 | native | z13 overzoomed 8×, still pixel-crisp; the arterial network, no new streets |
| z18 | native (the swap's gain — it was z16 stretched 4× before) | crisp, z13 content |
| z19 | native, and the deepest these basins carry | crisp, z13 content |

`maxZoom` and the source's `maxzoom` are held equal by `web/src/map/zoom-ceiling.test.ts`:
below it a level already being served is unreachable, above it the map paints the grey
placeholder. Over a region whose imagery stops shallower than 19 — see the probe table above —
the reader gets that placeholder with no error anywhere, which is why adding a region is a
re-probe and not a bounds edit.

**Label content is thinnest exactly where imagery is richest.** The archive's z13 geometry is
all there is at z18-z19, so what a viewport shows there is whatever named ground falls inside
it — which at a narrow breakpoint over a small town can be nothing at all. That is coverage,
not a rendering fault; the hybrid's argument is strongest at z13-z16, where the archive still
has new content to add.

At z13 the archive carries the arterial skeleton: through-streets, highways, county and state
routes, the locality name and named water. Not every residential street, and **lease roads are
not in OSM at any zoom**, so no archive depth would add them. For orienting a pad against the
county road, the highway and the nearest town that is the right content; say so plainly rather
than letting a reader discover the density by looking for a street that was never there.
