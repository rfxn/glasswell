# EIA basin and play boundary fixtures

Cut from the real EIA downloads. Sanitized by **feature and member selection only** —
no attribute value is edited, no geometry is repaired, and each `.prj` is copied
byte-for-byte from the upstream archive because `cr_eia_boundary_datum_1` reads it.

Reproduce with:

```bash
curl -sS -o /tmp/SedimentaryBasins_US_EIA.zip \
  https://www.eia.gov/maps/map_data/SedimentaryBasins_US_EIA.zip
curl -sS -o /tmp/TightOil_ShaleGas_IndividualPlays_Lower48_EIA.zip \
  https://www.eia.gov/maps/map_data/TightOil_ShaleGas_IndividualPlays_Lower48_EIA.zip
python tests/fixtures/eia_boundaries/cut_fixtures.py --downloads /tmp
```

## Upstream artifacts

Retrieved **2026-08-30T15:52Z** (`https_get`, anonymous, no click-wall, no
terms-of-use interstitial).

| Archive | URL | Bytes | Features | Upstream `Last-Modified` | sha256 (full artifact) |
|---|---|---|---|---|---|
| Sedimentary basins | <https://www.eia.gov/maps/map_data/SedimentaryBasins_US_EIA.zip> | 440,871 | 32 | 2016-03-10T16:39:22Z | `02a017ccb84bdcc15726838098e3cfa73450b9655cf06e28d2eca6f3c04edcff` |
| Individual plays | <https://www.eia.gov/maps/map_data/TightOil_ShaleGas_IndividualPlays_Lower48_EIA.zip> | 2,931,129 | 16 boundary features over 12 shapefiles | 2019-01-22T18:17:21Z | `20be8ea37727b05fc83e234a3257c069df5e5771b74501f40fc0828a7195c84b` |

Terms: US federal government work (17 U.S.C. §105). Neither archive carries a licence
string, a terms-of-use page or a redistribution clause; the shipped FGDC metadata
carries an accuracy disclaimer only. Recorded on `lineage.sources` as
`eia_sedimentary_basins` and `eia_shale_plays`.

The individual-play archive also ships elevation and isopach contour shapefiles. Only
members whose stem holds `_Boundary` are read (`LayerSpec.member_marker`), so the
contours are neither cut nor ingested.

## What is kept, and what each feature is here for

`SedimentaryBasins_US_EIA_cut.zip` — 8 of 32 features, one shapefile.

| `NAME` | Why it is kept |
|---|---|
| `WILLISTON` | The Bakken and Three Forks parent; the basin ND wells sit in |
| `PERMIAN` | The Wolfcamp and Delaware parent; a multi-play basin |
| `WESTERN GULF`, `APPALACHIAN` | Basins with no fixture play: a basin row that no play links to |
| `POWDER RIVER` | The one Niobrara row whose `Basin` string does resolve |
| `UINTA-PICEANCE` | The near-match `cr_eia_basin_link_1` refuses for `Piceance Basin` |
| `DENVER` | The near-match refused for `Denver Basin` |
| `NORTH PARK` | The near-match refused for `Park Basin` |

`TightOil_ShaleGas_IndividualPlays_Lower48_EIA_cut.zip` — 9 of 16 features over 5 of
the 12 boundary shapefiles, every member kept whole.

| Member | Features | Why it is kept |
|---|---|---|
| `ShalePlay_Bakken_Boundary_EIA_Aug2015_v2` | 1 | Invalid: `Ring Self-intersection` at −101.784379615, 48.9030813580001. The repair case, and the Williston play the product exists for |
| `ShalePlay_ThreeForks_Boundary__EIA_Aug2015_v2` | 1 | Invalid: `Ring Self-intersection` at −103.224838549, 46.7023706000001, and the one whose `ST_MakeValid` returns a collection. Double underscore in the stem is the publisher's |
| `ShalePlay_Wolfcamp_Boundary_EIA_201809` | 1 | The only feature with a `SubBasin`, a different vintage token, and extra `Shape_Leng`/`Shape_Area` fields the staging map ignores |
| `ShalePlay_Delaware_Boundary_EIA_Aug2015_v2` | 1 | Overlaps Wolfcamp inside the Permian: the overlap `cr_eia_boundary_overlap_1` refuses to dissolve |
| `ShalePlay_Niobrara_Boundary_EIA_Aug2015_v2` | 5 | One play name over five `Basin` strings — the reason the minted key is the pair. Four of the five do not resolve |

The fixture reproduces the production link ratio exactly: every unresolved play in the
full archive is a Niobrara row, so the cut carries 4 unresolved links out of 9 features
where the full archive carries 4 out of 16.
