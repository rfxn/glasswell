# martin tile sources

Three published layers, all in `marts`, all served through the API at
`/v1/tiles/{layer}/{z}/{x}/{y}.pbf` (SB-04 E-12 — martin is never in public routing):

| layer id | relation | geometry | refreshed by |
|---|---|---|---|
| `nd_laterals` | `marts.nd_laterals_tile` | LINESTRING | `python -m glasswell.marts.nd_wells` |
| `nd_wells` | `marts.nd_wells_tile` | POINT | same |
| `nd_spacing_units` | `marts.nd_spacing_units_tile` (view over `canonical.spacing_units`) | MULTIPOLYGON | always current |

`ds_size_acres` is `double precision` and not `numeric` on purpose: ST_AsMVT has no numeric
encoding and would put the acreage on the wire as a string (N-2, migration 015's class).
`nd_laterals` declares `GEOMETRY` because migration 017 widened the column for multi-part
centrelines — the declaration follows `geometry_columns`, which is where martin looks.

Every layer carries `derivation_id` as a feature property. A tile is a served figure, and
"no naked numbers" has no exception for tiles.

## Two publication mechanisms, one set of ids — never both at once

**Function sources (what runs tonight).** `refresh_all` creates
`marts.nd_laterals(z, x, y, query json)` and its two siblings. martin's default
`auto_publish` discovers a function source under the function's own name, so the ids above
appear with **no config file and no unit change** (B7: `martin.service` is already running
and is not reconfigured). The MVT layer name inside each tile equals the id, which is what
MapLibre binds `source-layer` to.

`auto_publish` also discovers every *table* with a geometry column, so martin's catalogue
carries `staging` and `canonical` relations that are not published layers. They are not
reachable: `glasswell.api.routers.tiles.PUBLISHED_LAYERS` is the entitlement, derived from
`TILE_LAYERS`, and the proxy answers `not_found` for anything outside it before a request
reaches martin. S-C's fuller condition — CI asserting martin's own source list equals the
allowlist — needs the config path below and lands with the tunnel.

**Table sources (`config.yaml`, the documented target).** Pointing martin at this file
turns `auto_publish` off — which is the point: auto-publish exposes every geometry table in
`staging` and `canonical` as a tile source, and **staging never serves** (blueprint
§3.0.1). The ids and properties are identical to the function sources, so no URL changes.

Do not enable both. `config.yaml` publishes ids `nd_laterals`/`nd_wells`/`nd_spacing_units`
as tables; the functions publish the same ids. Running with the config and an added
`functions:` block would collide.

### Adoption is blocked on the file, not on the deployer (DR-05)

`config.yaml` was written against martin 0.x. **The installed binary is martin 1.14.0 and it
publishes nothing from this file** — measured, not assumed, against VM 111's own database:

```
$ martin --config config.yaml --listen-addresses 127.0.0.1:3999
ERROR martin: No tile sources found. Set sources by giving a database connection string
              on command line, env variable, or a config file.
```

It fails before it connects, so it is the file martin rejects, not the database. Dropping
the stray top-level `pool_size` does not change it. Point the same binary at a bare
connection string and it resolves eleven sources happily, so the binary and the database are
both fine.

The reference for the shape martin 1.14 does accept is martin's own resolved config:

```
martin --save-config - "postgresql:///glasswell?host=/var/run/postgresql" 2>/dev/null
```

which emits `postgres.tables.<id>` entries carrying `schema`, `table`, `srid`,
`geometry_column`, `bounds`, `geometry_type` and `properties`, and — worth noting for
DR-35 — resolves `marts.nd_spacing_units_tile` as `source.kind="view"` without complaint.
A view under `tables:` is not the defect; PostGIS lists it in `geometry_columns` and martin
discovers it there.

**Until the file is reconciled with the installed binary, do not point the unit at it.** The
`/v1/tiles` proxy allowlist remains the control that holds "staging never serves", and
`infra/verify.sh` asserts a staging layer is refused through the proxy. Adoption also needs
one thing this file cannot carry: the running unit takes `DATABASE_URL` from
`/etc/glasswell/db.env`, and a `connection_string` here would override it.

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
