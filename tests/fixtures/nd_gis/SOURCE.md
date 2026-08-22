# ND DMR GIS fixtures

Cut from the real regulator downloads during phase P3 (DIR-10). Sanitized by
**record selection only** — no attribute value is edited, and each `.prj` is copied
byte-for-byte from the upstream archive because `cr_nd_datum_1` reads it.

Reproduce with:

```bash
for L in OGD_Wells OGD_Horizontals_Line OGD_DrillingSpacingUnits OGD_Directionals; do
  curl -sS -o /tmp/$L.zip https://gis.dmr.nd.gov/downloads/oilgas/shapefile/$L.zip
done
python tests/fixtures/nd_gis/cut_fixtures.py --downloads /tmp
```

## Upstream artifacts

Retrieved **2026-08-20T06:46:30Z** (`https_get`, anonymous, no click-wall). The
directional-survey artifact was retrieved **2026-08-21T22:37Z** for M1-5.

| Layer | URL | Bytes | Records | sha256 (full artifact) |
|---|---|---|---|---|
| `OGD_Wells` | <https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Wells.zip> | 3,688,384 | 43,812 | `a46d02682b8d60ca57cd09230860a4c21ad7432b40a64311fc84d3d6593dc725` |
| `OGD_Horizontals_Line` | <https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Horizontals_Line.zip> | 15,574,260 | 48,688 | `65c0a6e739a0c8e975dc787073ab2ed869baf75861835bf3385bdf829052bfc5` |
| `OGD_DrillingSpacingUnits` | <https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_DrillingSpacingUnits.zip> | 1,551,336 | 10,572 | `c38b211b26569c97735437bacf652b6a2fb457b43899d3f551626b78dfeddd4d` |
| `OGD_Directionals` | <https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Directionals.zip> | 3,410,367 | 52,579 stations | `6f2a21bc0218fd788749639ff333645baba76785d35fb1f1d506b6564d3de758` |

All four `.prj` files are byte-identical, 167 bytes, ESRI WKT for
`GCS_North_American_1983` → **EPSG:4269**.

`OGD_Directionals.zip` is the only one of the four that ships **two** shapefiles:
`OGD_Directionals` (52,579 station points) and `OGD_Directionals_Line` (586 line
features). The 586 lines are exactly the 586 `(api_wellno, well_sub)` segments the
station layer carries — ND's own rendering of the same stations — but they are a
**generalised** one: 11,358 vertices against the stations' 52,579, 585 of 586 features
carrying fewer vertices than their own segment, and up to `1.06e-4` degrees (~9 m) of
Hausdorff distance from the filed stations. The loader therefore selects the station
stem by suffix and assembles the trace itself.

## Truncation method

Each fixture keeps exactly four members — `.shp`, `.shx`, `.dbf`, `.prj`. The upstream
`.cpg`, `.sbn`, `.sbx` and `.shp.xml` are dropped; the reader locates members by
extension, and the survey loader additionally selects the layer by stem suffix, which
is why the survey fixture keeps the upstream member name `OGD_Directionals`.

| Fixture | Selection |
|---|---|
| `OGD_Horizontals_Line_300.zip` | source records 0–299. Records 0 and 1 are `33011003910000_LAT1` / `_LAT2`, the multi-lateral pair the seeded `cr_nd_multilateral_1` rationale cites |
| `OGD_Wells_300.zip` | every well whose API-10 appears in the lateral fixture (180), plus the first record carrying each of the 19 reported `status` values, padded with leading records to 300, in source order |
| `OGD_DrillingSpacingUnits_300.zip` | source records 0–299 |
| `OGD_Directionals_stations.zip` | 676 stations: **13 whole `(api_wellno, well_sub)` segments** over 10 wells, in source order. Never a partial segment — a segment cut mid-string would be a bore path this repository invented |

The wells fixture is a selection rather than the first 300 records because the file
is ordered by `fileno`: its first 300 rows are 1920s–1950s wildcats with no lateral
geometry and no `Confidential` status, so a head truncation would leave every
lateral an `orphan_fk` and the status vocabulary untested.

The survey fixture's 13 segments are each chosen for one thing a test has to be able
to assert against real data:

| Segment | Stations | Why it is in the fixture |
|---|---|---|
| `33007011660000_DIR` | 52 | API-10 also present in `OGD_Wells_300`, so the mart tier gets real traces |
| `33053019370000_DIR` | 19 | as above |
| `33053021020000_DIR` | 64 | as above |
| `33007003310000_STK1` | 199 | inclination `436` at station 8 — impossible, and interior |
| `33007006800000_DIR` | 57 | four stations whose TVD exceeds their own MD (0.12–0.77 ft) |
| `33075014950000_DIR` | 150 | azimuth `437`, and it is the **deepest** station: quarantining the row would truncate the trace at its toe |
| `33075011520000_DIR` | 2 | the shortest segment upstream; the `min_stations` floor with nothing to spare |
| `33105903760000_STK1/2/3/VERT` | 17 / 43 / 33 / 25 | a well with sidetracks and a vertical and no `DIR` at all |
| `33089006260000_STK4` | 12 | the only `STK4` upstream; completes the `well_sub` vocabulary |
| `33053105500000_VERT` | 3 | **deliberately given no well row** by the test, so the `orphan_fk` path runs on real data |

## Measured content (asserted by the tests, not assumed)

- laterals: 233 `_LAT`, 40 `_VERT`, 27 `_STK` segments over 180 API-10s; 42 of those
  API-10s carry more than one `_LAT` centreline. `_VERT` and `_STK` are **not**
  lateral centrelines — full-file counts are 23,236 `_LAT`, 21,304 `_VERT`,
  4,148 `_STK`.
- wells: 300 records, all 19 reported status values present including one
  `Confidential`; 4 records have an empty `spud_date`; the oldest is 1928-05-27.
- spacing units: 300 single-part polygons; `caseno`/`orderno` are `0` for all 300
  (10,463 of 10,572 upstream), which is why the canonical id carries a geometry
  digest.
- `SHAPE_Leng` on the lateral fixture ranges 0.0001–0.02 — degrees, never a length.
- surveys: 676 stations over 13 segments and 10 API-14s; all six `well_sub` labels the
  full file ships are present (`DIR`, `VERT`, `STK1`–`STK4`). Six values are
  physically impossible — one inclination of `436`, one azimuth of `437`, four TVDs
  0.12–0.77 ft deeper than their own measured depth. Upstream those same classes total
  seven values in 52,579 stations. Three of the 10 API-10s (`3300701166`,
  `3305301937`, `3305302102`) also appear in `OGD_Wells_300.zip`, which is what gives
  `test_marts_nd.py` real trace geometry without a second wells fixture.
