# tests/fixtures/nm_ocd — provenance

Cut from the one polite FTP pull of 2026-08-20 (DIR-10, SB-01 §1.3). Truncation only: a kept
record is the exact character span it occupies in the source document, so the CHAR padding, the
per-record `xmlns` declaration and the element order are the regulator's, not this repository's.
The three single-cell amendments in `_amended` and the one in `_moddte` are listed below and are
the only differences from the base fixture.

Re-cut with `python tests/fixtures/nm_ocd/cut_fixtures.py --raw-root /data/raw`, which reads the
sealed raw zone and never the network.

## Upstream artifacts

Anonymous FTP, `164.64.106.6`, `/Public/OCD/OCD Interface v1.1/{core,volumes}/<table>/<table>.zip`.
Retrieved 2026-08-20, fetch vintage `2026-08-20` — **self-stamped**, because the filenames carry
no date and the server overwrites them nightly (`cr_nm_<table>_undated_vintage_1`).

| source_id | source_key | bytes | sha256 (16) | upstream MDTM |
|---|---|---|---|---|
| `nm_ocd_wcproduction` | `wcproduction.zip` | 968,419,426 | `4d3bceb6a5b79880` | 2026-08-20T00:22:40Z |
| `nm_ocd_wellhistory` | `wellhistory.zip` | 44,196,919 | `0c95fe732c8a99de` | 2026-08-19T22:59:08Z |
| `nm_ocd_wchistory` | `wchistory.zip` | 40,412,706 | `c5bc80b4d69a3d2b` | 2026-08-19T22:58:32Z |
| `nm_ocd_pod` | `pod.zip` | 3,357,422 | `eaa56dd7055e111d` | 2026-08-19T22:56:09Z |
| `nm_ocd_ogrid` | `ogrid.zip` | 2,730,032 | `7d4ebc35401543e7` | 2026-08-19T22:55:26Z |
| `nm_ocd_podwc` | `podwc.zip` | 2,323,036 | `58851e69f913fb6a` | 2026-08-19T22:56:31Z |
| `nm_ocd_property` | `property.zip` | 1,584,106 | `e1f50b5fab16f72c` | 2026-08-19T22:57:14Z |
| `nm_ocd_spacingunit` | `spacingunit.zip` | 1,018,753 | `d9b13ea7247fdc73` | 2026-08-19T22:57:58Z |
| `nm_ocd_pool` | `pool.zip` | 208,303 | `6b7bf5c1642deb59` | 2026-08-19T22:56:52Z |

`wcproduction.zip` full-artifact sha256:
`4d3bceb6a5b79880db518e00d933ae951d38232e54f8e81a4d60743491a7fb27`.

Every MDTM lands between 22:55 on 2026-08-19 and 00:22 on 2026-08-20 — a Wednesday night, hours
before the pull. The published `FTPDataSetDescriptions.pdf` says "the first Monday of every
month" with dated bundles; the server carries neither (`cr_nm_<table>_ftp_layout_1`).

## Document shape

```
<root xmlns:xsi="…"><xsd:schema targetNamespace="urn:schemas-microsoft-com:sql:SqlRowSet1" …>
  …inline schema…
</xsd:schema><wcproduction xmlns="urn:schemas-microsoft-com:sql:SqlRowSet1">…</wcproduction>…</root>
```

- **UTF-16LE with a BOM** (`ff fe`). Read and written as `utf-16`, never `utf-16-le`: the latter
  turns the BOM into a stray character in the first tag.
- **Namespaced records.** A bare-tag match returns zero records silently, which is why the
  namespace URI is pinned in the parse rule rather than inferred.
- No XML declaration. The root element is `<root>`, not `SqlRowSet1`.

## T1 answers, measured against the full artifact

`wcproduction.xml`, streamed once from the zip member with nothing extracted to disk
(24m51s wall clock, 32,261 records/s, peak RSS ~30 MB):

| question | answer |
|---|---|
| **T1-e** uncompressed bytes | **48,310,560,330** (48.31 GB, 49.9:1) |
| **T1-e** records | **48,104,334** |
| **T1-e** full-stream wall clock | **1,491.1 s** |
| **T1-e** rows inside DIR-12's 2015-01 window | **17,645,580** (36.7%), **80,624** entities |
| **T1-a** identity | `api_st_cde` + `api_cnty_cde` + `api_well_idn`, unpadded, × `pool_idn`. No completion suffix |
| **T1-b** streams | `prd_knd_cde` ∈ `{'G ', 'O ', 'W ', 'C '}` — **a fourth code exists** (below) |
| **T1-c** coordinates | **absent from `wcproduction`** — but **`wellhistory` carries `latitude`, `longitude`, `datum`** (below) |
| **T1-d** element inventory | 14 children, **all present on every one of the 48.1M records** |

### Element inventory and max widths

| element | max width | notes |
|---|---|---|
| `api_st_cde` | 2 | always `30`; 48,104,334 rows |
| `api_cnty_cde` | 2 | 1–2 digits, pads to 3 |
| `api_well_idn` | 6 | 5 digits or fewer on all but **one** row (below) |
| `pool_idn` | 5 | |
| `prodn_mth` | 2 | integer, unpadded (`7`, not `07`) |
| `prodn_yr` | 4 | 1973 → 2026 |
| `ogrid_cde` | 6 | operator, joins `ogrid` |
| `prd_knd_cde` | 2 | **CHAR(2), space-padded** |
| `eff_dte` | 23 | `YYYY-MM-DDT00:00:00` |
| `amend_ind` | 1 | ten distinct values, not a Y/N flag (below) |
| `c115_wc_stat_cde` | 1 | **undeclared in the plan**; eleven values including `' '` and a lowercase `p` |
| `prod_amt` | 8 | never absent, never blank |
| `prodn_day_num` | 2 | |
| `mod_dte` | 23 | 2015-04-07 → 2026-08-18 |

**Nothing is ever absent and nothing is ever blank.** `ever_absent` is empty, and both
`blank_key_component_rows` and `blank_prod_amt_rows` are 0 across 48.1M records — so
`key_incomplete` is a defensive exit for NM, not an observed one.

### The three findings that change later phases

1. **`prd_knd_cde` has a fourth value, `'C '` — condensate.** 3,398 rows across 277 wells, and
   every one of them falls in **1986–1993**. There are none inside the 2015-01 window, so the
   bounded first pass will see three codes and the eventual full backfill will see four. The
   stream vocabulary must admit it; `canonical.production_monthly` already does (migration 021).
2. **One row cannot compose an API-10.** `api_well_idn` widths are 1→620, 2→39,300, 3→493,572,
   4→7,927,412, 5→39,688,526 and **6→1**, that one being `30-15-256350`. A pad-to-five rule is
   right for 48,104,333 rows and impossible for one, which is exactly what the `key_incomplete`
   reason code exists for.
3. **`amend_ind` is a vocabulary, not a flag.** `N` 34,812,326 · `Y` 13,280,514 · `1` 5,959 ·
   `2` 5,252 · `4` 185 · `6` 72 · `9` 10 · `3` 8 · `X` 6 · `7` 2. Treating it as boolean would
   mis-read 11,494 rows.

`c115_wc_stat_cde` distribution: `P` 23,532,167 · `F` 20,557,177 · `S` 2,686,669 · `T` 734,301 ·
`G` 391,371 · `I` 97,456 · `A` 47,439 · `' '` 42,366 · `D` 15,375 · `p` 7 · `L` 6. The lowercase
`p` is a case trap for any exact-match vocabulary.

### `wellhistory` carries coordinates

`wellhistory`'s elements are `api_st_cde`, `api_cnty_cde`, `api_well_idn`, `eff_dte`,
`rec_termn_dte`, `ogrid_cde`, `well_name`, `prod_prop_idn`, `prop_fm_desc`, `well_nbr_idn`,
`well_typ_cde`, `lease_typ_cde`, `ocd_district`, `last_apd_status`, `last_apd_apr_date`,
`last_apd_cancel_date`, **`latitude`, `longitude`, `datum`**, `sdiv_twp_idn`, `sdiv_rng_idn`.

PLAN-NM §6 rules NM geometry OUT on the finding that coordinates are "confirmed absent in the
bytes". That is true of `wcproduction` and false of `wellhistory`, which D1 already fetches.
Nothing in D1 acts on it — `marts/**` is another track's and the ruling is the controller's —
but the premise behind D1b's "NM spatial from the ArcGIS Hub" no longer holds unqualified.

### NM county codes

`wellhistory` carries 31 distinct `api_cnty_cde` values, of which exactly one is even: `6`
(Cibola), on 23 wells. **The even-county fixture case P1.9 asks for is not present in the
production window and could only be manufactured**, so it is recorded here as a T1-d answer
rather than carried as a fabricated record. The padding case it was standing in for *is*
covered: the fixture holds county `5` (one digit) alongside `15` and `45`.

## `nm_wcproduction_300.xml` — 305,902 bytes, sha256 `a4d8dd635887a83ac96e991f67afba09ed60203fddcd1ed1fbb6e1399a3a91f0`

300 records, verbatim spans, in file order. `wcproduction` is ordered oldest-first and opens in
1973, so a cut from the head alone would carry nothing inside DIR-12's promotion window and
every window test would assert against an empty set. The fixture therefore straddles the
boundary:

| slice | records | source ordinals |
|---|---|---|
| head, pre-window | 20 | 0–19 (`prodn_yr` 1973) |
| window, from the first 2015 row onward | 280 | 30,360,859 onward (`prodn_yr` 2014 × 251, 2015 × 29) |

Coverage carried, and how it was chosen:

| case | present | note |
|---|---|---|
| `prd_knd_cde` `'G '`, `'O '`, `'W '` with the trailing space | yes | one row each at minimum |
| `prd_knd_cde` `'C '` | **no** | 1986–1993 only; neither slice reaches those years |
| county code needing a pad (`5` → `005`) | yes | with `15` and `45` |
| even county code | **no** | see above — 23 wells statewide, none producing here |
| one well-month reporting two pools | yes | `30-45-23968`, 2014-03, `'G '`, two `pool_idn` |
| zero volume | yes | 15 rows with `prod_amt` `0` |
| absent volume | **no** | never absent in 48.1M rows |
| absent key component | **no** | never absent in 48.1M rows |
| `amend_ind` set | yes | both `N` and `Y` appear; the numeric values do not |
| zero `prodn_day_num` | yes | |

## `nm_wcproduction_300_amended.xml` — sha256 `52081e6f83e066d475a3e6a7e859b8765fe4888e9d641601f4e0efa28b1a637c`

Arm A. **One record differs** (the last, source ordinal 30,361,280), in **three cells**:

| cell | base | amended |
|---|---|---|
| `prod_amt` | `2983` | `3983` |
| `amend_ind` | `N` | `Y` |
| `mod_dte` | `2015-04-07T07:37:04.160` | `2026-08-19T04:00:00.000` |

`amend_ind` is set because it is the regulator's own amendment flag; `mod_dte` moves with it
because a real amendment touches the row. Neither belongs in `value_hash` — that is Arm C.

## `nm_wcproduction_300_moddte.xml` — sha256 `6257aa25a769654961360435dbb0dc8e482467c57cada145139f9cff265340fb`

**SYNTHETIC.** `mod_dte` is set to `2026-08-19T04:00:00.000` on all 300 records and **no other
cell changes** — every `prod_amt` is byte-identical to the base fixture.

This file does not reproduce observed OCD behaviour. The probe found `mod_dte` preserved per row
(2015-04-07 through 2026-08-18) and a separate `amend_ind`, so a file-wide stamp bump is not
something NM has been seen to do. It is kept as a labelled invariant test: *a change in a
change-detection timestamp is not a restatement*. At 48.1M rows, a `mod_dte` semantics drift
that silently manufactured restatements would be unrecoverable, and this fixture is the
regression that catches it.

## The other tables — 300 records each

| fixture | bytes | sha256 (16) | selection |
|---|---|---|---|
| `nm_wchistory_300.xml` | 724,948 | `1ab915ab83140ca3` | 124 records naming a fixture well, rest from the head |
| `nm_podwc_300.xml` | 147,708 | `6d0153804c466325` | 71 records naming a fixture well, rest from the head |
| `nm_spacingunit_300.xml` | 148,172 | `70c24418d23b9969` | head — the table has no API columns to join on |
| `nm_property_300.xml` | 171,228 | `39bc8f17d483eac3` | head — keyed by `prod_prop_idn`, not by API |
| `nm_ogrid_300.xml` | 515,708 | `a75dfad686f81d70` | head — the operator registry, keyed by `ogrid_cde` |
| `nm_pool_300.xml` | 439,164 | `62d739936116ff6a` | every pool the production fixture names, then the head |

`nm_pool_300.xml` replaces the whole-table `nm_pool_full.xml` PLAN-NM P1.9 asked for. "0.2 MB
source" is the *compressed* zip; the member is 7.3 MB of UTF-16 XML, and a 300-record cut that
covers every pool the production fixture names carries the same test value at a twenty-fifth of
the repository cost.

`pool_nam` is space-padded to a fixed width in the source (`ACME;SAN ANDRES` followed by
eighteen spaces), so `prd_knd_cde` is not the only CHAR column that will need a declared trim.

## What is asserted about these files

`tests/unit/test_nm_fixtures.py` holds every property above that a careless re-cut could drop:
the BOM, the `SqlRowSet1` namespace on all 302 references, the trailing space on `prd_knd_cde`,
the unpadded key segments, both sides of the 2015 window, the two-pool well-month, the
three-cell restatement diff and the timestamp-only `_moddte` diff.
