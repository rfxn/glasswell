# Colorado ECMC fixtures — where every row came from

Cut by `cut_fixtures.py` from the live ECMC files on 2026-09-02, whose byte counts matched the
`content-length` the host served for each one. Nothing here is synthetic: every row is a row
ECMC published, and the cut is stated so a reader can tell what the fixtures do and do not
cover.

| Fixture | Cut from | What the cut guarantees |
|---|---|---|
| `Wells_sample.zip` | `WELLS_SHP.ZIP`, 124,410 features | 118 rows: every well the production sample names, at least four of each of the twelve status codes present in the data, all four location-qualifier classes including the blank one, and **both byte-identical duplicate pairs** — all eighteen extra rows, so the deduplication rule has its whole subject |
| `DirectionalBottomholeLocations_sample.zip` | `DIRECTIONAL_BOTTOMHOLE_LOCATIONS_SHP.ZIP`, 39,049 | 61 rows including one API-10 carrying two wellbores, which is the multi-wellbore share blueprint §3.0.5 sets a trigger on |
| `DirectionalLines_sample.zip` | `DIRECTIONAL_LINES_SHP.ZIP`, 39,049 | 60 rows, same guarantee |
| `monthly_prod_sample.csv` | `monthly_prod.csv`, 387,813 rows | 312 rows over 24 API-10s, 195 well-months of which 87 carry more than one completion — so the dual write has both a well-month to aggregate and a one-completion month that must carry no `aggregation` |
| `prod_reports_2025_sample.csv` | `2025_prod_reports.csv`, by range request | The drifted header: `GasSrinkage`, `BOMInvent`/`EOMInvent`, `FlaredVented` ahead of `WaterProduced`, ISO timestamps and the literal string `NULL`. It opens at `ReportMonth 11, ReportYear 2024`, which is the received-year trap `cr_co_production_vintage_1` exists for |
| `prod_reports_1999_sample.csv` | `1999_prod_reports.csv`, by range request | The same header as the rolling file, which is what makes the drift a property of one archive rather than of the archives |

The three GIS archives ship `NAD_1983_UTM_Zone_13N` in their `.prj`, and the cut copies that
file verbatim, so `epsg_from_prj` resolves the fixtures exactly as it resolves the originals.

## The member names, and the one thing these fixtures used to get wrong

**Corrected 2026-09-04.** Until that date the two directional fixtures carried members named
`DirectionalBottomholeLocations.*` and `DirectionalLines.*`, and neither name was ECMC's.
`cut_fixtures.py` read each source archive **by extension only** — it never recorded the stem —
and then wrote the cut under a stem passed in as a literal argument, so the names were invented
here rather than measured. ECMC ships `Directional_Bottomhole_Locations.*` and
`Directional_Lines.*`, measured on VM 111 at 2026-09-04 20:06:30Z from
`DIRECTIONAL_BOTTOMHOLE_LOCATIONS_SHP.ZIP` (1,901,641 B, sha256 `cb294d5bf6fc…`, members dated
2026-09-03 07:56). The wells archive matched by luck: its member is `Wells.*` and the layer is
selected as `wells`, a single word with nothing to separate.

The consequence was a suite green on a claim about this repository rather than about the
regulator: `co_ecmc_gis --layer all` staged 124,410 wells on the host and then raised
`MalformedArchive: payload.ZIP has no .shp, .shx, .dbf member matching
'directionalbottomholelocations'`, a half-loaded vintage.

The cutter now carries each archive's own stem from the read to the write, and the three names
are conformance rows — `cr_co_wells_shp_member_1`, `cr_co_directional_bh_member_1`,
`cr_co_directional_lines_member_1` — so the name a layer is selected by is a decision with a
rationale rather than a constant. `shapefile.py` compares both sides with case and separators
removed, so the regulator's punctuation is no longer something a fixture can get wrong.

| Fixture | Bytes | sha256 |
|---|---|---|
| `Wells_sample.zip` | 15862 | `1d386f559370d7821f042d06c202fce8a7843e6c6a966243eb021a9dc4e8d1c7` |
| `DirectionalBottomholeLocations_sample.zip` | 4267 | `853ae2d3c734a464d1f7adfa90ad3d2995584b52be68dbd0ed3c1bd998a799b7` |
| `DirectionalLines_sample.zip` | 4146 | `9f5e38979af890c336b5d08c3163f27b16227788c74aa7e155cedc23bf2f81b6` |

The two directional archives were rewritten in place with the measured member names and
otherwise byte-identical payloads, which is exactly what a re-cut produces: `_write` varies
nothing but the stem. The filenames of the fixture archives themselves are unchanged — they are
this repository's names for its own files, not ECMC's for theirs.

Re-cut with:

    python tests/fixtures/co_ecmc/cut_fixtures.py /path/to/scratch
