# P3 model-ready dataset

`mdv1.1` is the first accepted model-dataset semantic contract. It consumes the immutable `fv2.0`
feature matrix without changing feature semantics and persists four registered artifacts:
long-form cumulative labels, producing-month curves, coverage JSON, and row-level rejections.
The four annual origins each receive one content-addressed split for cum12 and cum24; oil,
gas, and water consume the same split id literally.

## Label contract

- Grain is `(api10, stream, horizon)` for oil, gas, and water at horizons 12 and 24.
- A producing month has positive volume in any stream, or `reported_zero` with positive
  `days_produced`. `no_report`, `withheld`, and zero-day zero-volume months do not advance.
- Withheld or confidential wells are excluded from every split partition and carry a
  `withheld` label status for every stream and horizon. They are never converted to zero.
- Wells short of the horizon are `incomplete`; wells with no producing month are
  `no_production`. Both remain in the curve/feature population where the contract permits.
- E-6 now measures the intermittency guard at 16 calendar months: p95 over 22,023 ND wells
  that reached a twelfth producing month. The same twelfth-month well class governs cum12
  and cum24; no separate cum24 threshold was invented.
- Cumulative targets remain DECIMAL. The curve sidecar retains each available producing
  month through month 24 so a control can include censored wells only through observed life.

## Control context

The artifact carries the minimum pinned peer dimensions: basin, formation group, county as
area, exact geodesic lateral length, the measured ND length bucket, and first-production
month. First-production month is split and peer-window metadata, never an ML feature. These
are `mdv1.1` dataset fields; `fv2.0` remains unchanged. The minor version appends the
self-describing `dataset_version` column to labels and curves without changing any label.

The ND bucket edges are exact: `<8000`, `8000–<10000`, `10000–10500`, and `>10500` ft.
Missing formation, area, or length remains explicit in `rejections.parquet` under the
`typecurve_control` scope instead of being silently dropped from the model-ready population.

## Vintage and split policy

Canonical well, geometry, and production rows are selected with manifest and derivation
knowledge cuts at the evaluation vintage. Historical rolling splits use the separately
labelled `source_reconstructed_not_glasswell_history` clock: the Hth producing month plus the
pinned 45-day MPR source proxy. The strict selected-row availability is retained beside it as
`label_source_available_on`; the two clocks are never presented as interchangeable.

Incomplete wells remain assigned to a partition but do not move its knowledge cutoff.
Completion anchors after first production, missing first production, and withheld or
confidential wells are excluded with named rejection rows. Surface ambiguity falls back to
an ungrouped singleton rather than selecting a coordinate arbitrarily.

## Resident replay

The 2026-08-26 Williston build consumes 17,563 anchored `fv2.0` subjects and writes:

| Artifact | Rows | SHA-256 |
|---|---:|---|
| `mdv1.1` labels | 105,378 | pending final resident replay |
| producing-month curves | 1,172,586 | pending final resident replay |
| rejections | 3,272 reason rows | `0b0434281a02f30c3b2ac94e6ebabbf579ab4e3cb362b1db3797ac47d02eb771` |
| coverage | one canonical JSON document | pending final resident replay |

Per stream, cum12 has 15,957 complete, 705 incomplete, 364 intermittent, 272
no-production, and 265 withheld labels. Cum24 has 15,130 complete, 1,552 incomplete, 344
intermittent, 272 no-production, and 265 withheld labels. Counts are identical across all
three streams, which independently checks the shared censoring policy.

The rejection artifact names 1,280 completion-after-production anchors, 522 missing first
production dates, 265 withheld/confidential subjects, 815 missing formations, 388 missing
lateral lengths, and the two known formation conflicts. Overlap is retained rather than
deduplicated away: 2,208 distinct subjects carry 3,272 reason rows. The split population is
15,749; 394 of those lack some control context, leaving 15,355 control-eligible split wells.

All eight splits have no plausibility flags. Their largest pad component is 30 wells
(`pad_group_max_share=0.001905`, below the 0.02 rejection threshold), and the group rule
reassigns 22–60 wells depending on origin. A second full build reproduced every labels,
curves, coverage, rejection, and split byte hash above.
