# P3 pinned type-curve control

`tcv1.0` is the first accepted semantic contract for the fixed P3 benchmark control. It
consumes the immutable `mdv1.4` model-ready bundle and its eight content-addressed split
objects without changing `fv1.0`, `fv2.0`, or `mdv1.4`. A future semantic change appends a
new control major; it does not reinterpret `tcv1.0`.

## Peer and split contract

- Subjects are TEST assignments from the persisted split object. Peers are TRAIN union CAL
  assignments from that exact object; TEST wells never enter a peer set.
- Pad groups must remain indivisible, and every subject's pad members are excluded again at
  peer resolution. The redundant exclusion makes the control fail closed if a malformed
  split bypasses the first check.
- Peers first produced within the 36 months before the split origin and have at least one
  producing month available at the split knowledge cutoff.
- The ordered, closed ladder is formation + county + measured length bucket, then formation
  + county, then formation + basin, then `control_unavailable`. `TC_MIN_N=20`; no fourth
  widening exists.
- The model coverage document must name exactly cum12 and cum24 for each origin, with oil,
  gas, and water in the pinned order. Every split byte hash and the split-set identity are
  revalidated before a row is built.

The resolved peer set is one subject-level decision shared by all streams and both
normalizations. A missing gas observation therefore reduces gas `peer_count` for that month;
it does not change the peer ladder or let the absolute and per-foot arms compare different
populations.

## Curves and bands

Both arms are always materialized:

- `typecurve_per_kft` divides each peer by its own lateral length in thousands of feet,
  computes the empirical curve, and scales it by the subject's lateral length.
- `typecurve_absolute` uses peer volumes directly and never scales the subject.

For each producing-month index, the artifact records monthly and cumulative peer counts and
equal-weight empirical P10, P50, and P90 using percentile-cont linear interpolation. A month
with fewer than 20 valid observations is `insufficient`, not extended. Cumulative quantiles
are quantiles of each peer's own cumulative volumes; they are never sums of monthly
quantiles. Statistical-ascending P10/P50/P90 is the only convention in `tcv1.0`.

## Vintage boundary

The control inherits the model bundle's explicit
`source_reconstructed_not_glasswell_history` split basis. Peer curve rows use their
reconstructed source-availability dates at the split cutoff, and peer formation observations
must be source-available by that cutoff. Subject formation is the anchor-time matrix feature,
whose measured publication lag is reported rather than suppressed under SB-02's feature
contract. County and lateral length retain `mdv1.4`'s named limitation: their historical
source availability is not represented, so they are read at the evaluation vintage rather
than described as strict historical possession.

## Artifacts and registration

The primary Parquet artifact is keyed by control version, dataset version, basin, evaluation
vintage, feature version, vintage basis, split-set id, and its SHA-256. Every row carries the
control derivation, source dataset derivation, split id and hash, normalization, fallback
level, peer-set id, monthly counts, statuses, quantiles, and any pipe-delimited sorted set of
terminal reasons. The coverage JSON publishes overlapping reason mentions, fallback counts,
per-split coverage, and acceptance flags.

`typecurve.build` registers one permanent D1 lineage derivation and one content-addressed
recipe over the labels, curves, coverage document, and all eight exact split hashes. It does
not insert a misleading row into the incomplete `lineage.models` shape: that table still
lacks the blueprint's `kind=typecurve` discriminator and writer. No control number is served
yet, so the registry migration remains an explicit prerequisite to model serving rather than
an implied capability.

## Resident replay

The resident 2026-08-26 Williston artifact consumes `mdv1.4` bundle
`sset_c7bbb9a6932db76b` and was built twice from implementation commit `19f754c` in the
pinned VM environment. Both runs produced byte-identical results:

| Artifact | Rows | SHA-256 |
|---|---:|---|
| `tcv1.0` controls | 2,300,400 | `fd300dc2995a4a8ffc7fc0bc63aff2367fabb551527cc9a453ce4218ba0efbe4` |
| coverage JSON | one canonical document | `30eb07d2dec6da64f861f8c88e89c1b3a28d964d728b42a4213142e3e7da5b29` |

The identity is `tc_ima4gxkkhy5hvhhxdhyq`, derivation
`drv_tbye5ygbgmhgeuktsxiq`, and recipe `rcp_1a8669bb7ee5e61d9393f4857a70227b`.
The committed two-run resident gate completed in 3:02 wall time, peaked at 2.64 GiB RSS,
and did not swap.

Across 21,300 TEST subject/split instances, 17,404 resolve at rung one (81.7089%), 226
at formation + county, 912 at formation + basin, and 2,758 are unavailable. All available
monthly and cumulative rows clear `TC_MIN_N`; the terminal population contains only eight
insufficient-peer instances, representing one unique subject across the paired horizons and
four origins.

## Honest gate result

The measured rung-one floor passes: 81.7089% is above 60%. The control-unavailability gate
does not: 12.9484% is above the pinned 5% ceiling, and every split fails separately, from
9.8721% at the 2021 origin to 21.1403% at the 2024 origin. `tcv1.0` records both
plausibility flags and does not widen the peer ladder or remove those subjects.

This is a context-readiness miss, not evidence that 20 peers or 36 months is too strict. The
coverage artifact records 2,544 missing-formation mentions, 222 missing-lateral mentions,
and eight insufficient-peer mentions; reason mentions overlap. Over the 3,596 unique TEST
subjects, 355 are unavailable: 318 lack formation, 38 lack lateral length, one lacks enough
peers, and two carry both context gaps. The next repair target is therefore those source
fields, with no inferred formation and no spud-date substitution, followed by the same exact
replay and 5% gate. Model training may be developed, but P3 cannot claim control readiness
while this acceptance result is red.
