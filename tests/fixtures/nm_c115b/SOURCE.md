# NM OCD C-115B natural gas waste fixtures (M1-9)

Cut from the live NM EMNRD/OCD C-115B FeatureServer by **record selection only** — no
attribute value is edited. The layer-metadata document is a verbatim service response because
`arcgis_rest_paginate` reads `maxRecordCount`, `supportsPagination`, the object-id field and
the spatial reference from it.

The extract is two wells, `30-015-54573` (Eddy) and `30-045-38469` (San Juan), whose six rows
between them carry both waste types, four reporting periods and two counties — small enough
that a two-record page size exercises a real multi-page walk in tests. The live pull is never
used in tests (SB-01 §1.2.1 politeness; the full layer is 71,447 rows across ~24 pages and
belongs to the deployed timer).

Reproduce with:

```bash
python tests/fixtures/nm_c115b/cut_fixtures.py
```

## Upstream artifacts

Retrieved **2026-08-22** by anonymous query (no token, no click-wall) from
`https://gis.emnrd.nm.gov/arcgis/rest/services/OCDPUB/C115B_NaturalGasWaste/FeatureServer`.
The feature extract was cut **with `outSR=4269`** and `orderByFields=OBJECTID ASC`, the
parameters the paginator sends.

| File | What | sha256 |
|---|---|---|
| `layer_0.json` | layer 0 (C-115B Upstream by Well API) metadata, verbatim | `91b60314c0b5be20ca8ed0e932836b3fd1e11dbaf8c4db4d4bcaa8848ac0b22d` |
| `upstream_by_well.geojson` | 6 well-waste features, `outSR=4269` | `c9e8b3ea3de00948e939a4777fd3c2ea70facb44342fca0a4650c43c7aad2a3c` |

Layer 0 measured the same day: 71,447 features, `maxRecordCount` 3000, spatial reference
wkid 4269, `capabilities` `Query,Extract`, `copyrightText` empty.

## The OBJECTID trap this fixture does not reproduce

The layer is view-backed and assigns `OBJECTID` per query — `max(OBJECTID)` equals the row
count exactly, and the same three rows answered with OBJECTIDs 67199/59784/62372 and then
59844/61928/67791 seconds apart. An offset walk ordered by it re-reads and skips rows while
every count reconciles; two adjacent 2,000-row live pages shared 52 rows under `OBJECTID ASC`
and none under `id, reporting_period, waste_type`. That is `cr_nm_c115b_walk_order_1`. The
double in `tests/support/c115b_fake.py` serves a stable recorded page set and so cannot show
the defect — `tests/unit/test_nm_c115b_parse.py` pins the order the module declares, and the
`duplicate_row` quarantine is the tripwire that fires if the walk ever re-reads a row.

Licence: New Mexico public record served from an explicitly public ArcGIS endpoint with
Extract enabled; `copyrightText` is empty and no terms-of-use string is published
(`data-sources-infra.md` F2). EMNRD/OCD attributed as a courtesy.
