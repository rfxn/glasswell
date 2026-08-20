# Basemap — build and serve

The basemap is a self-hosted [Protomaps](https://protomaps.com) PMTiles extract read over
HTTP range requests from this app's own origin. There is no API key, no third-party tile
endpoint, and no service contract — only a licence (ODbL for the OSM data, BSD for the
Protomaps software) and a checksummed file, which is the same shape as every other source
in the manifest.

## Build

Run on the build host, not the VM — the extract pulls from `build.protomaps.com`:

```bash
scripts/basemap-build.sh --region nd --maxzoom 13 --with-labels --out /tmp/basemap
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
rsync -a --delete /tmp/basemap/ root@<vm>:/opt/glasswell/basemap/
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
whole `200` would make every tile read pull the entire archive, so that case falls back to
OpenFreeMap rather than quietly costing 48 MB per read.

If a reverse proxy is put in front later, it must preserve `Range`, `Accept-Ranges` and the
`206`, and should add a long cache lifetime, since the archive is immutable for the life of
a vintage:

```nginx
location /basemap/ {
    alias /opt/glasswell/basemap/;
    add_header Cache-Control "public, max-age=86400";
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
3. Otherwise the dark and light options fall back to OpenFreeMap (`positron` / `dark`,
   keyless, attribution required, no SLA) and a banner names what failed and what replaced
   it.
4. If that is unreachable too, the map draws the one-degree graticule, which is also the
   `?base=none` option a reader can choose deliberately.
