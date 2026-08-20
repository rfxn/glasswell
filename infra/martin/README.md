# martin tile sources

Three published layers, all in `marts`, all served through the API at
`/v1/tiles/{layer}/{z}/{x}/{y}.pbf` (SB-04 E-12 — martin is never in public routing):

| layer id | relation | geometry | refreshed by |
|---|---|---|---|
| `nd_laterals` | `marts.nd_laterals_tile` | LINESTRING | `python -m glasswell.marts.nd_wells` |
| `nd_wells` | `marts.nd_wells_tile` | POINT | same |
| `nd_spacing_units` | `marts.nd_spacing_units_tile` (view over `canonical.spacing_units`) | MULTIPOLYGON | always current |

Every layer carries `derivation_id` as a feature property. A tile is a served figure, and
"no naked numbers" has no exception for tiles.

## Two publication mechanisms, one set of ids — never both at once

**Function sources (what runs tonight).** `refresh_all` creates
`marts.nd_laterals(z, x, y, query json)` and its two siblings. martin's default
`auto_publish` discovers a function source under the function's own name, so the ids above
appear with **no config file and no unit change** (B7: `martin.service` is already running
and is not reconfigured). The MVT layer name inside each tile equals the id, which is what
MapLibre binds `source-layer` to.

**Table sources (`config.yaml`, the documented target).** Pointing martin at this file
turns `auto_publish` off — which is the point: auto-publish exposes every geometry table in
`staging` and `canonical` as a tile source, and **staging never serves** (blueprint
§3.0.1). The ids and properties are identical to the function sources, so no URL changes.

Do not enable both. `config.yaml` publishes ids `nd_laterals`/`nd_wells`/`nd_spacing_units`
as tables; the functions publish the same ids. Running with the config and an added
`functions:` block would collide.

## Operational notes

- martin reads its catalogue at startup. Layers created after it started are invisible
  until it restarts, so after the first `refresh_all` on a fresh database check
  `curl -s 127.0.0.1:3000/catalog` and restart martin only if the ids are absent — the unit
  file and its `EnvironmentFile` stay untouched either way.
- The martin role needs `usage` on schema `marts`; `execute` on the tile functions is
  PUBLIC by default. Migration 009 grants schema usage to `glasswell_pipeline` and
  `glasswell_api`; if martin connects as neither, grant it explicitly.
- `connection_string` here uses the postgres socket. The running unit takes `DATABASE_URL`
  from `/etc/glasswell/db.env` over loopback TCP instead; both reach the same database.
