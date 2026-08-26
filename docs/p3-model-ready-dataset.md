# P3 model-ready dataset

`mdv1.4` is the first accepted model-dataset semantic contract. It consumes the immutable `fv2.0`
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
are `mdv1.4` dataset fields; `fv2.0` remains unchanged. The minor additions make labels and
curves self-describing and carry strict plus reconstructed month-level availability without
changing any label.
The bundle address also includes its vintage basis and a content-derived split-set id, so a
custom origin set cannot overwrite another build's coverage while sharing label bytes.

The ND bucket edges are exact: `<8000`, `8000–<10000`, `10000–10500`, and `>10500` ft.
Missing formation, area, or length remains explicit in `rejections.parquet` under the
`typecurve_control` scope instead of being silently dropped from the model-ready population.

## Vintage and split policy

Canonical well, geometry, and production rows are selected with manifest and derivation
knowledge cuts at the evaluation vintage. Historical rolling splits use the separately
labelled `source_reconstructed_not_glasswell_history` clock: the Hth producing month plus the
pinned 45-day MPR source proxy. The strict selected-row availability is retained beside it as
`label_source_available_on`; the two clocks are never presented as interchangeable.
Curve rows preserve the same distinction in `source_available_on` and
`source_reconstructed_available_on`, so the type-curve builder need not recreate availability
semantics. Formation carries its matrix availability fields. County and lateral geometry are
read at the evaluation vintage because their historical source availability is not represented;
the coverage artifact names that limitation rather than implying strict historical possession.

Incomplete wells remain assigned to a partition but do not move its knowledge cutoff.
Completion anchors after first production, missing first production, and withheld or
confidential wells are excluded with named rejection rows. Surface ambiguity falls back to
an ungrouped singleton rather than selecting a coordinate arbitrarily.

## Resident replay

The 2026-08-26 Williston build consumes 17,563 anchored `fv2.0` subjects and writes:

| Artifact | Rows | SHA-256 |
|---|---:|---|
| `mdv1.4` labels | 105,378 | `d2e1c911cf4d58acbe05034ed55a1d48266c801fc48f669916002b029506a38d` |
| producing-month curves | 1,172,586 | `a39f3d404143669196ed759bb0c48ecc24a56a633a3e113957fb07f647bb9275` |
| rejections | 3,272 reason rows | `0b0434281a02f30c3b2ac94e6ebabbf579ab4e3cb362b1db3797ac47d02eb771` |
| coverage | one canonical JSON document | `b3dc5dc5da98f8b28ffec5f3a8bc62a34c89cb8318371c90a402e17f07486d6a` |

The pre-merge `mdv1.3` candidate remains immutable. A column-for-column comparison after the
review fixes found identical label, curve, rejection, and coverage semantics; only registered
lineage identity changed. `mdv1.4` therefore advances the dataset identity without changing
`fv2.0` or relabelling the retained candidate.

The accepted bundle is `sset_c7bbb9a6932db76b`, derivation
`drv_eh2u6idkf5rtm4wsv3sa`, and recipe `rcp_02a21056b98fce720f960d98d9e97d8c`, built from
implementation commit `f04a565` under the reconstructed source-vintage basis.

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
