# BLM CadNSDI PLSS fixtures (M1-4)

Cut from the live BLM national CadNSDI NAD83 MapServer by **record selection only** — no
attribute value is edited. The two layer-metadata documents are verbatim service responses
because `arcgis_rest_paginate` reads `maxRecordCount`, `supportsPagination`, the object-id
field and the spatial reference from them.

The extract is two townships (`152N 95W`, `153N 95W`, PLSSIDs `ND051520N0950W0` /
`ND051530N0950W0`) and four of their sections — small enough that a two-record page size
exercises a real multi-page walk in tests. The live pull is never used in tests (SB-01
§1.2.1 politeness; the full ND slice is 2,067 townships / 71,486 sections).

Reproduce with:

```bash
python tests/fixtures/blm_plss/cut_fixtures.py
```

## Upstream artifacts

Retrieved **2026-08-22** by anonymous query (no token, no click-wall) from
`https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI_NAD83/MapServer`.

| File | What | sha256 |
|---|---|---|
| `layer_1.json` | layer 1 (PLSS Township) metadata, verbatim | `9a316b71a487910a22f67945bba00e0727b948c52474099f1ff773ca0cdd08f6` |
| `layer_2.json` | layer 2 (PLSS Section) metadata, verbatim | `e19b389cd399ce6a4da9e8a9797f183c5498d28fd2d4f03974ae474a9904449f` |
| `nd_townships.geojson` | 2 township features, `orderByFields=OBJECTID ASC` | `1be9debe9c352e681ff8ec436f48f7047038cd531bc2e9e135a878e12a279c4f` |
| `nd_sections.geojson` | 4 section features, `orderByFields=OBJECTID ASC` | `7a65453033eb091dd9d5878d30cb3674d8ea98f5515b54f5f83a8ff553ad3a3c` |

Licence: US federal government work (17 U.S.C. §105); the service publishes no licence or
terms-of-use string and no redistribution clause was found (`data-sources-land.md` A1).
