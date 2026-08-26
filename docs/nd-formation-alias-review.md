# ND formation alias review

Reviewed **2026-08-26** against every non-null `well_completion_pool` in the deployed
`nd_mpr_xlsx` production head. The full population contains **40** labels; the earlier count
of 23 came from `canonical.well_completions`, whose promoter had registered only multi-pool
filings. That was a pipeline defect, not a smaller source vocabulary.

`formation` is a lossless normalized label. `formation_group` is the peer-group vocabulary
shared by `fv1.0` and `fv2.0`; `fv2.0` changes which source month is eligible, not these alias
judgments. Exact
principal targets with measured support retain a group; explicit Three Forks stays distinct
even though its current support is sparse; ambiguous composites and sub-threshold targets use
`__other__` rather than inheriting an unsupported geological judgment.

| Reported pool | Distinct API-10s | Canonical formation | fv1.0 group | Confidence |
|---|---:|---|---|---:|
| BAKKEN | 19,135 | bakken | bakken | 1.000 |
| MADISON | 2,364 | madison | madison | 1.000 |
| SANISH | 418 | sanish | sanish | 1.000 |
| RED RIVER | 220 | red_river | red_river | 1.000 |
| PIERRE | 164 | pierre | pierre | 1.000 |
| SOUTH RED RIVER B | 155 | red_river_b | red_river | 0.950 |
| DUPEROW | 134 | duperow | duperow | 1.000 |
| SPEARFISH/CHARLES | 134 | spearfish_charles | spearfish_charles | 0.900 |
| SPEARFISH | 123 | spearfish | spearfish | 1.000 |
| NORTH RED RIVER B | 120 | red_river_b | red_river | 0.950 |
| BIRDBEAR | 116 | birdbear | birdbear | 1.000 |
| DEVONIAN | 66 | devonian | __other__ | 1.000 |
| TYLER | 59 | tyler | __other__ | 1.000 |
| SILURIAN | 58 | silurian | __other__ | 1.000 |
| BAKKEN/THREE FORKS | 57 | bakken_three_forks | __other__ | 1.000 |
| SPEARFISH/MADISON | 57 | spearfish_madison | __other__ | 1.000 |
| ORDOVICIAN | 56 | ordovician | __other__ | 1.000 |
| STONEWALL | 56 | stonewall | __other__ | 1.000 |
| HEATH | 51 | heath | __other__ | 1.000 |
| MIDALE/NESSON | 43 | midale_nesson | __other__ | 1.000 |
| LODGEPOLE | 35 | lodgepole | __other__ | 1.000 |
| RED RIVER B | 30 | red_river_b | red_river | 0.950 |
| WEST RED RIVER | 23 | red_river | red_river | 0.950 |
| WINNIPEGOSIS | 23 | winnipegosis | __other__ | 1.000 |
| DAKOTA | 21 | dakota | __other__ | 1.000 |
| RED RIVER UNIT | 12 | red_river | red_river | 0.950 |
| DAWSON BAY | 6 | dawson_bay | __other__ | 1.000 |
| WINNIPEG/DEADWOOD | 5 | winnipeg_deadwood | __other__ | 1.000 |
| RATCLIFFE | 4 | ratcliffe | __other__ | 1.000 |
| THREE FORKS | 4 | three_forks | three_forks | 1.000 |
| TYLER A | 4 | tyler_a | __other__ | 1.000 |
| MINNELUSA | 3 | minnelusa | __other__ | 1.000 |
| CAMBRO/ORDOVICIAN | 2 | cambro_ordovician | __other__ | 1.000 |
| GUNTON | 2 | gunton | __other__ | 1.000 |
| WINNIPEG | 2 | winnipeg | __other__ | 1.000 |
| DEADWOOD | 1 | deadwood | __other__ | 1.000 |
| Dakota | 1 | dakota | __other__ | 1.000 |
| MISSION CANYON | 1 | mission_canyon | __other__ | 1.000 |
| SOURIS RIVER | 1 | souris_river | __other__ | 1.000 |
| UnknownXML | 1 | unknown | __other__ | 1.000 |

The registry rows use `effective_from = created_vintage = 2026-08-26`. A later correction is
a new row at a new knowledge vintage; the old judgment remains queryable and historical feature
builds hydrate the mapping that existed at their own `as_of` date.
