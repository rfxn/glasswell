# P3 matrix integrity

Verified **2026-08-26** against the resident North Dakota source population. This note owns
the formation policy, publication-lag measurement, coverage contract, and retrospective
vintage boundary for `fv2.0`.

## Canonical formation policy

`fv1.0` remains immutable: it resolves every pool observed for a well and refuses a
multi-group result. `fv2.0` is a semantic-major successor with a closed policy:

1. Select the earliest `production_month` carried by the well's as-of MPR completion rows.
2. Resolve only pools reported in that month through the as-of formation alias table.
3. Emit the one resolved group; emit null plus a conflict record when that month resolves to
   multiple groups; emit null plus a missing record when it resolves to none.
4. Ignore later pool observations for this feature and for its derivation input set. A
   backfill that supplies an earlier source month is new knowledge and belongs to a new
   `as_of_vintage`; it is not mutation of an existing partition.

The current `fv1.0` population has 10 anchored wells with groups from multiple source months.
Earliest-month selection resolves eight. Two remain genuine simultaneous-source conflicts:
API-10 `3300701199` reports BAKKEN and MADISON in 2015-05, and API-10 `3300701386` reports
MADISON and TYLER in 2015-05. `fv2.0` publishes both as conflicts and carries null rather than
choosing geology by code order.

## Publication lag

The MPR source-availability proxy is the production month plus 45 days: one reporting month
plus the regulator's approximate 15-day publication delay. End-to-end lag is measured from
the FracFocus completion anchor to that proxy, not assumed from the proxy alone.

| Cohort | n | Negative | p25 | p50 | p75 | p95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Completion on/after 2015-05-01 | 9,323 | 292 | 51 d | 80 d | 176 d | 223 d |
| Non-negative measurement cohort | 9,031 | 0 | 53 d | **82 d** | 177 d | 224 d |

The 292 negative values mean the FracFocus event postdates estimated first-MPR availability;
they are recompletion or source-ordering cases, not negative publication time, and are
excluded from the registry statistic. The measured `publication_lag_days_p50` is therefore
82. Matrix coverage also publishes formation-source timing: 7,245 source-left-truncated,
7,743 before the first pool-bearing source month, 1,385 in the same calendar month, 375
definitely after that month, and 815 without a pool-bearing formation source row. The last
state does not claim the well lacked production. Same-month ordering is indeterminate at
monthly grain; it is never promoted to a false exact sequence.

## Two vintage clocks

The matrix remains strict Glasswell history. Its `as_of_vintage` admits only manifests,
derivations, well versions, completion versions, and alias versions proven present by that
date. A cutoff before Glasswell acquired those manifests remains unavailable.

`geology.formation_group__source_available_on` is a separate reconstructed source clock for
retrospective benchmark eligibility. It means the regulator filing was expected to be
available then; it does **not** claim Glasswell possessed it then. Benchmark artifacts must
label this basis `source_reconstructed_not_glasswell_history`, and may never use it for the
live forecast ledger or serving history.

## Published coverage and replay

Every `fv2.0` partition carries canonical `coverage.json` bytes beside its Parquet file. The
sidecar reports resolved, missing, and conflict counts; missing subjects; conflict subjects and candidate
groups; anchor-timing counts; the lag measurement; and both vintage policies. Its hash is
registered in the feature recipe. Replaying the same source, registry, environment, version,
and vintage must reproduce both Parquet and coverage hashes and bytes.

The live-source scratch replay on 2026-08-26 emitted 17,563 rows: 16,746 resolved, 815
missing, and the two conflicts above. Two builds produced identical Parquet bytes
(`5220c2b23b6e196cf6e1cf74d2e3513760bb4930d750a097617e97ddd0bb5c3d`) and coverage bytes
(`c02a9ccb4487b2b8784f38e8b6c305c22eff2cecab9d2503014903a06567f5a8`). The migration and
lineage writes ran in a transaction that was rolled back after the comparison; the scratch
files were removed, so the proof did not persist pre-deploy branch state.

After merged migration 041 reached the VM, the persisted resident partition replayed with
the same 17,563-row coverage and byte-identical hashes: Parquet
`7b1031d2235a23e59b3743ff311ce30f3c79328b19634906bf5042c426170636` and coverage
`d9109dc7d6496bf399a8bbdf6148f48df02c9ea60a96cb77d76f122f70dfdb89`. The different
hashes from the scratch proof are expected: the derivation id embedded in the Parquet records
the persisted build identity. Replays compare like-for-like build identities, not just source
rows.
