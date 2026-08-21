# Basemap — build and serve

The basemap is a self-hosted [Protomaps](https://protomaps.com) PMTiles extract read over
HTTP range requests from this app's own origin. There is no API key, no third-party tile
endpoint, and no service contract — only a licence (ODbL for the OSM data, BSD for the
Protomaps software) and a checksummed file, which is the same shape as every other source
in the manifest.

## Build

Run on the build host, not the VM — the extract pulls from `build.protomaps.com`:

```bash
# Not a fixed /tmp path: two agents building at once would overwrite each other, and the
# nd-tx extract is 336 MB, which is more than a tmpfs /tmp usually wants (N-3).
build_dir="$(mktemp -d -t gw-basemap.XXXXXXXX)/basemap"
scripts/basemap-build.sh --region nd --maxzoom 13 --with-labels --out "$build_dir"
```

Measured against the 2026-08-15 planet build (`--dry-run`, no download):

| region | z0–10 | z0–12 | z0–13 |
|--------|-------|-------|-------|
| `nd`   | ~6 MB | 22 MB | **48 MB** |
| `nd-tx`| 24 MB | 138 MB | 336 MB |

`nd` matches the current ingest footprint. `nd-tx` is the Permian-ready extract; build it
when TX lands, not before. Label assets (three Noto Sans stacks plus the dark and grayscale
sprites) add ~14 MB.

Each zoom level roughly doubles the archive, so project from a low-maxzoom `--dry-run`
before committing to a size. z13 is the right ceiling here: a lateral is legible well
before street-level detail matters.

## Deploy

```bash
# $build_dir from the build step above
rsync -a --delete "$build_dir"/ root@<vm>:/opt/glasswell/basemap/
chown -R glasswell:glasswell /opt/glasswell/basemap
systemctl restart glasswell-api
```

`GLASSWELL_BASEMAP_ROOT=/opt/glasswell/basemap` in `/etc/glasswell/app.env` is what mounts
it. The directory holds:

```
basemap.pmtiles      the archive
manifest.json        vintage, sha256, region, maxzoom, whether labels are present
fonts/               only when built --with-labels
sprites/             only when built --with-labels
```

## Serving

uvicorn's `StaticFiles` mount **does** answer range requests with a `206` — verified in
`tests/unit/test_basemap_mount.py`, which is the check that keeps this claim true. No
reverse proxy is required for the basemap to work.

The client refuses the archive unless a ranged GET returns exactly `206`
(`web/src/map/map.ts`, `archiveServesRanges`). A server that ignores `Range` and returns a
whole `200` would make every tile read pull the entire archive, so that case degrades to the
graticule rather than quietly costing 48 MB per read.

The app applies the cache classes itself: `public, max-age=86400` on everything under
`/basemap/`, except `manifest.json`, which stays `no-cache` because it is how the client
notices a vintage swap. A swapped archive is therefore visible to a fresh session
immediately and to a warm cache within a day.

Range serving is not the map's bottleneck, and was measured rather than assumed. On VM 111
against the deployed 336 MB archive, 64 KB ranges through uvicorn's two workers answered in
2.3 ms sequentially and 7.0 ms median / 11.9 ms p95 under an eight-way burst; the same
ranges taken while the tile proxy was saturated moved to 6.4 ms median / 15.2 ms p95. That
is head-of-line blocking, but of a size that does not justify `aiofiles`, `sendfile` or more
workers. Re-measure before adding any of them.

If a reverse proxy is put in front later, it must preserve `Range`, `Accept-Ranges` and the
`206`:

```nginx
location /basemap/ {
    alias /opt/glasswell/basemap/;
    # nginx serves Range/206 for static files natively; do not add anything that buffers.
}
```

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

There is no hosted runtime fallback. The client used to reach for
`https://tiles.openfreemap.org` at step 3 and it had never once worked: `connect-src 'self'`
refuses it. A fallback the policy forbids is a second failure wearing the label of a recovery.

## Satellite imagery, and the one origin the policy names

The satellite option is USGS National Map imagery — public domain, keyless, and inherently
somebody else's origin. `glasswell.api.security` allow-lists exactly
`https://basemap.nationalmap.gov` in `connect-src` and `img-src`, by name and never as a
wildcard. Nothing else external is allowed, and the dark, light and none options remain
provably zero-external (`web/src/map/map.test.ts`).

The requests happen only when a reader selects satellite, and the client asks the origin for
one tile before committing to it: if that tile does not arrive — the origin is down, the
policy refuses it, the network is gone — the map degrades to the graticule and the banner
names `basemap.nationalmap.gov` as what failed. The imagery credit goes with it, because an
attribution over a canvas with no imagery on it is a false statement about what was drawn.

Adding a second imagery origin means adding it to that allow-list in the same change. If the
list ever needs to exceed two hosts, that is a decision to take deliberately, not a widening
to slip in with a basemap.
