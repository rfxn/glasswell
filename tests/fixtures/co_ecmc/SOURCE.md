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

Re-cut with:

    python tests/fixtures/co_ecmc/cut_fixtures.py /path/to/scratch
