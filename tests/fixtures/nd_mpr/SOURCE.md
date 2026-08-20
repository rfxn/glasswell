# tests/fixtures/nd_mpr — provenance

Cut from a real NDIC download during P2 (DIR-10). Truncation only: no value is edited,
nothing is anonymized, and the one changed cell in the restatement fixture is recorded
below and is the only difference between the two files.

## Upstream artifact

| Field | Value |
|---|---|
| URL | `https://www.dmr.nd.gov/oilgas/mpr/2026_03.xlsx` |
| Retrieved | 2026-08-20T06:49:29Z |
| HTTP status | 200 |
| `content-type` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| `last-modified` | Thu, 14 May 2026 13:12:00 GMT |
| `etag` | `"050923fa3e3dc1:0"` |
| Bytes (full artifact) | 3266540 |
| sha256 (full artifact) | `6a630718800ce674f98551d540487eb5a6bc1b842315401a4f8b87b9681dcfd9` |
| Sheets | `Oil` (A1:U22273 → 22272 data rows), `SkimmedCrudeRecovery` (A1:U19644) |
| Header (row 1, A–U) | ReportDate, API_WELLNO, FileNo, Company, WellName, Quarter, Section, Township, Range, County, FieldName, Pool, Oil, Wtr, Days, Runs, Gas, GasSold, Flared, Lat, Long |

## `2026_03_truncated.xlsx` — 30,423 bytes, sha256 `dd1c548a2725b9474810d88332e826f9939c1827eeeacf27e7322774f85d2ff0`

Truncation method, with `openpyxl` against the full artifact:

```python
wb = openpyxl.load_workbook('/tmp/nd_2026_03.xlsx')
oil = wb['Oil']
oil.delete_rows(2900, oil.max_row - 2899)   # everything after the window
oil.delete_rows(2, 2698)                    # everything before the window
wb['SkimmedCrudeRecovery'].delete_rows(2, wb['SkimmedCrudeRecovery'].max_row - 1)
wb.save('tests/fixtures/nd_mpr/2026_03_truncated.xlsx')
```

Result: both sheet names preserved, header preserved on both sheets, `Oil` carries
**200 data rows** (`max_row == 201`), `SkimmedCrudeRecovery` carries header only.

### Why the window is rows 2700–2899 and not the first 200

PLAN.md P2.3 requires a quarantine share above zero from **naturally occurring** rows —
"do not fabricate a bad row" — and the first 200 data rows of the 2026-03 file are
entirely clean. Measured over all 22,272 data rows: 0 negative volumes, 0 empty cells,
and **173 rows where NDIC writes the literal string `NULL`** into Oil, Wtr, Days, Gas and
Flared (GasSold still carries a number). The first is sheet row 2381.

The window 2700–2899 is the smallest contiguous 200-row slice that carries a useful
cluster of them, keeping the fixture at 30 KB rather than the ~350 KB an extension from
row 1 to row 2787 would cost. The five rows are, by API_WELLNO:

| Fixture data row | API_WELLNO | Oil | Days | Gas | GasSold |
|---|---|---|---|---|---|
| 84 | 33105064520000 | NULL | NULL | NULL | 0 |
| 85 | 33105063460000 | NULL | NULL | NULL | 0 |
| 86 | 33105064510000 | NULL | NULL | NULL | 0 |
| 87 | 33105064500000 | NULL | NULL | NULL | 0 |
| 88 | 33105064530000 | NULL | NULL | NULL | 0 |

They quarantine at the validate stage under `cr_nd_days_range_1` (`out_of_range_date`):
`NULL` is not a day count in 0–31, and a row the predicate cannot judge is quarantined
rather than assumed (SB-07 §6.1). They are the "no report filed" state of §3.0.3 as the
regulator actually writes it.

The second measured quarantine path is `cr_nd_stream_vocab_1` (`stream_not_promoted`):
GasSold and Flared are dispositions of produced gas, not streams, so every row's two
disposition columns quarantine with a reason. That batch is conflict C7's measured
evidence and is why the promotion never invents a fourth stream.

## `2026_03_restated.xlsx` — 30,423 bytes, sha256 `5580c70e2579d768dd418939fb17a962d8b9e3a4673190ce5e2850150cf349ae`

A byte-for-byte copy of `2026_03_truncated.xlsx` with **one** cell changed, standing in
for an NDIC amendment of an already-published month:

| Cell | API_WELLNO | api10 | Column | Before | After |
|---|---|---|---|---|---|
| `Oil!M2` | 33105040370000 | 3310504037 | Oil (bbl) | 304 | 337 |

Nothing else differs — same 200 rows, same header, same sheet names. `test_nd_restatement.py`
ingests the two files under two clocks a day apart and asserts the March row for
`3310504037` is appended at the later vintage while the 304 bbl row survives untouched at
the earlier one.
