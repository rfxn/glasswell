# ND DMR GIS fixtures

Cut from the real regulator downloads during phase P3 (DIR-10). Sanitized by
**record selection only** — no attribute value is edited, and each `.prj` is copied
byte-for-byte from the upstream archive because `cr_nd_datum_1` reads it.

Reproduce with:

```bash
for L in OGD_Wells OGD_Horizontals_Line OGD_DrillingSpacingUnits; do
  curl -sS -o /tmp/$L.zip https://gis.dmr.nd.gov/downloads/oilgas/shapefile/$L.zip
done
python tests/fixtures/nd_gis/cut_fixtures.py --downloads /tmp
```

## Upstream artifacts

Retrieved **2026-08-20T06:46:30Z** (`https_get`, anonymous, no click-wall).

| Layer | URL | Bytes | Records | sha256 (full artifact) |
|---|---|---|---|---|
| `OGD_Wells` | <https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Wells.zip> | 3,688,384 | 43,812 | `a46d02682b8d60ca57cd09230860a4c21ad7432b40a64311fc84d3d6593dc725` |
| `OGD_Horizontals_Line` | <https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Horizontals_Line.zip> | 15,574,260 | 48,688 | `65c0a6e739a0c8e975dc787073ab2ed869baf75861835bf3385bdf829052bfc5` |
| `OGD_DrillingSpacingUnits` | <https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_DrillingSpacingUnits.zip> | 1,551,336 | 10,572 | `c38b211b26569c97735437bacf652b6a2fb457b43899d3f551626b78dfeddd4d` |

All three `.prj` files are byte-identical, 167 bytes, ESRI WKT for
`GCS_North_American_1983` → **EPSG:4269**.

## Truncation method

Each fixture keeps 300 records and exactly four members — `.shp`, `.shx`, `.dbf`,
`.prj`. The upstream `.cpg`, `.sbn`, `.sbx` and `.shp.xml` are dropped; the reader
locates members by extension, never by name.

| Fixture | Selection |
|---|---|
| `OGD_Horizontals_Line_300.zip` | source records 0–299. Records 0 and 1 are `33011003910000_LAT1` / `_LAT2`, the multi-lateral pair the seeded `cr_nd_multilateral_1` rationale cites |
| `OGD_Wells_300.zip` | every well whose API-10 appears in the lateral fixture (180), plus the first record carrying each of the 19 reported `status` values, padded with leading records to 300, in source order |
| `OGD_DrillingSpacingUnits_300.zip` | source records 0–299 |

The wells fixture is a selection rather than the first 300 records because the file
is ordered by `fileno`: its first 300 rows are 1920s–1950s wildcats with no lateral
geometry and no `Confidential` status, so a head truncation would leave every
lateral an `orphan_fk` and the status vocabulary untested.

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
