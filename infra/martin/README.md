# martin tile sources

Every published layer lives in `marts` and is served through the API at
`/v1/tiles/{layer}/{z}/{x}/{y}.pbf` (SB-04 E-12 — martin is never in public routing). The
roster is `glasswell.api.routers.tiles.PUBLISHED_LAYERS`, which `config.yaml` is asserted
equal to; this table covers the layers whose refresh is an operator command:

| layer id | relation | geometry | refreshed by |
|---|---|---|---|
| `nd_laterals` | `marts.nd_laterals_tile` | LINESTRING | `python -m glasswell.marts.nd_wells` |
| `nd_wells` | `marts.nd_wells_tile` | POINT | same |
| `nd_spacing_units` | `marts.nd_spacing_units_tile` (view over `canonical.spacing_units`) | MULTIPOLYGON | always current |
| `nm_wells` | `marts.nm_wells_tile` | POINT | `glasswell-nm-tiles` |
| `co_wells` | `marts.co_wells_tile` | POINT | `glasswell-tiles --jurisdiction CO` |

Colorado publishes a point layer and no lateral either, and for its own measured reason:
`cr_co_wells_geometry_scope_1` records that the two directional archives cover 37,482 of
124,392 wells, so promoting them would leave seven wells in ten with no path and no statement
of why. Its features carry two axes that are not the same axis. `geometry_provenance` says
which feature the point is, `surface` on every one; `loc_qual_class` says how good the
coordinate is, and 44.67% of them are `planned` -- a permit location on a well that may since
have been drilled somewhere else. `cr_co_wells_location_qualifier_1` is the row that classes
it, and a client that drew the two as one axis would be telling a reader a permit application
is a survey.

New Mexico publishes a point layer and no lateral: `cr_nm_wellhistory_geometry_scope_1` records
that neither in-scope source ships one. Every `nm_wells` feature carries its reported OCD letter
and, beside it, the class `cr_nm_wellhistory_status_vocab_2` resolves that letter to — resolved
at refresh from `lineage.nm_wellhistory_status_map`, because `canonical.wells.status_canonical`
is null for New Mexico and stays that way.

`ds_size_acres` is `double precision` and not `numeric` on purpose: ST_AsMVT has no numeric
encoding and would put the acreage on the wire as a string (N-2, migration 015's class).
`nd_laterals` declares `GEOMETRY` because migration 017 widened the column for multi-part
centrelines — the declaration follows `geometry_columns`, which is where martin looks.

Every layer carries `derivation_id` as a feature property. A tile is a served figure, and
"no naked numbers" has no exception for tiles.

## One set of ids, published once — the functions, declared

`refresh_all` and `install_tile_functions` create `marts.nd_laterals(z, x, y, query json)`
and its two siblings; each reads the `marts.tile_*` view of its layer. The MVT layer name
inside each tile equals the id, which is what MapLibre binds `source-layer` to.

**Unconfigured, martin finds them by itself — and finds far too much else.** Default
`auto_publish` discovers function sources under the function's own name, so the ids above
appear with no config file at all. It also discovers every *table* with a geometry column,
so the catalogue carries `staging` and `canonical` relations: eleven sources, three of them
`staging`. Nothing outside `glasswell.api.routers.tiles.PUBLISHED_LAYERS` is reachable
through the proxy, but the tile server is offering them.

**`config.yaml` is the adopted target.** It turns `auto_publish` off and declares the three
function sources explicitly, so the catalogue *is* the allowlist. The ids do not change, so
no URL changes.

Do not declare the same ids twice. A `tables:` block naming the `marts.tile_*` views would
collide with the functions that read them — and it would give up everything the next section
measures, because a table source has no `z` to key a simplify tolerance on. Measured on
VM 111 with the shipped views, publishing them as tables instead costs **+21% bytes at z7,
+35% at z9 and +42% at z11** on `nd_laterals` (1,777,155 → 2,151,024 B at `7/27/44`).

## What the function sources do that a table source cannot

Two things the tile functions carry that `config.yaml`'s table sources do not, both measured
on VM 111 against the live ND slice (`work-output/track-t-status.md`):

- **One `ST_AsMVTGeom` per row.** The body wraps the projection in `with … as materialized`.
  Inlined, the planner evaluates the geometry twice — once for the `is not null` test and
  again for the aggregate. Measured as the parameterised function martin calls, removing
  the second evaluation is −25% to −40% on `nd_laterals`, −5% to −16% on `nd_wells` and
  −8% to −35% on `nd_spacing_units`, from z4 to z13.

  **Measure the function, not the expanded statement.** With literal `z`/`x`/`y` the
  planner sees constants and picks different paths: benchmarked that way, `nd_wells` at z11
  looks like a 1213% regression, while the function itself improves 10.5% there and keeps
  its `Bitmap Index Scan on nd_wells_tile_geom_idx`.
- **Zoom-proportional thinning of the line layer.** `ST_Simplify` at four MVT units of the
  tile being built, so the discarded detail is a quarter of a rendered pixel at any zoom.
  At z7 that is 12.7% fewer bytes and 30% less time; at z9, 19.8% fewer bytes at no cost.
  Points have nothing to thin and the topology-safe polygon variant measured 171% slower
  for 3% fewer bytes, so neither of the other two layers is simplified.

`config.yaml` keeps both, because it publishes the functions rather than the views they
read. The privilege boundary is unchanged either way: the functions run with the caller's
rights, so the `martin` role reaches exactly the three `tile_*` views and nothing else.

## Compression: ask for zstd or ask for nothing

martin compresses on demand, and the default `Accept-Encoding` any HTTP client sends makes
it choose gzip. On the z7 laterals tile (2,037,023 B, the hottest tile in the access log):

| `Accept-Encoding` | martin | bytes on the wire |
|---|---|---|
| `identity` | 1.8 ms | 2,037,023 |
| `zstd` | 19 ms | 751,192 |
| `gzip` | 140 ms | 702,691 |
| `br` | 165 ms | 638,610 |

gzip buys 48 KB over zstd for 120 ms of a tile server every other request depends on. The
proxy therefore asks martin for `zstd` when the caller can take it and `identity` otherwise
(`glasswell.api.routers.tiles.UPSTREAM_ENCODINGS`), and passes the encoded body through
without decoding it. Anything that talks to martin directly should do the same.

martin answers `If-None-Match` with a `304` in 0.7 ms and no body, which is what makes the
proxy's revalidate cache class cheap.

## Adoption: one missing role, not a broken file (DR-05)

`config.yaml` works. Run against VM 111's own database it publishes all three sources and
nothing else:

```
$ martin --config config.yaml --listen-addresses 127.0.0.1:3999     # as OS user glasswell
INFO Published source source.id=nd_laterals       source.kind="table"
INFO Published source source.id=nd_spacing_units  source.kind="view"
INFO Published source source.id=nd_wells          source.kind="table"
$ curl -s 127.0.0.1:3999/catalog
{"tiles":{"nd_laterals":{...},"nd_spacing_units":{...},"nd_wells":{...}}}
```

The whole defect is the DSN. `postgresql:///glasswell?host=/var/run/postgresql` names no
user, `pg_hba.conf` has `local all all peer`, and so the connection authenticates as the PG
role named for the invoking OS user. `martin.service` runs `User=martin`:

```
$ sudo -u martin martin --config config.yaml
ERROR Failed to create postgres pool: FATAL: role "martin" does not exist
```

**Migration 026 creates it**, and gives it `usage` on `marts` plus `select` on three views —
`marts.tile_nd_laterals`, `tile_nd_wells`, `tile_nd_spacing_units` — and on nothing else. Each
view holds exactly the columns its layer publishes, so the *column list is the publication
boundary*: `marts.nd_laterals_tile.lateral_length_ft_exact` is `numeric`, ST_AsMVT can only
encode it as a 19-digit string, and it is simply not in the view. `staging` (blueprint §3.0.1),
`canonical` and `lineage` are denied at the schema.

That grant is the control, not the config: `auto_publish: true` could be set back on tomorrow
and martin still could not read a staging relation. `tests/integration/test_martin_publishes.py`
proves it by starting the binary with auto-publish on.

**It has to be a view with a table-level grant, and not a column-level grant on the mart.**
PostGIS's `geometry_columns` filters on `has_table_privilege(…, 'SELECT')`, which a column
grant does not satisfy, so martin discovers *"schema 'marts' exists but has no tables with a
geometry column"* and exits — and `Restart=on-failure` makes that a crash loop with every tile
down. That was Gate-O B-3, found by running the binary as the role rather than reading the
grant, which is why the test now does exactly that.

Publishing the functions rather than the views does not soften that. A `language sql` function
runs with the caller's rights, so the role still needs `select` on what the function reads:
pointed at the old `marts.nd_laterals_tile`, the same binary answers
`permission denied for table nd_laterals_tile` on every tile while starting cleanly, which is
a worse failure than not starting. The views are what the functions read, and that is what
makes the two halves compose.

### Adopting it (deployer, one time)

`./install.sh --with-martin-config` places the file at `/etc/martin/config.yaml` and a
drop-in that adds `--config` to the pre-existing `martin.service` — a drop-in, because that
unit belongs to the host and not to this directory. Then:

```bash
systemctl restart martin
curl -s 127.0.0.1:3000/catalog | python3 -m json.tool   # expect exactly three ids
./verify.sh                                             # the martin catalogue check goes ok
```

Migration 026 must be applied first, or martin cannot connect at all, and the tile functions
must have been installed from the code being deployed (`install_tile_functions`), because the
config resolves their signatures at startup and each one names the view it reads. Do not put a
`connection_string` naming a different user into the unit's environment: `DATABASE_URL` in
`/etc/glasswell/db.env` is the `glasswell` login, which can read everything, and the config's
DSN exists precisely to avoid using it.

The eleven-source catalogue is what auto-publish produces today — `nd_gis_laterals`,
`nd_gis_spacing_units` and `nd_gis_wells` are `staging` relations published by the tile
server. "Staging never serves" (blueprint §3.0.1) is held only by the `/v1/tiles` proxy
allowlist until this is adopted, and by the grant afterwards.

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
