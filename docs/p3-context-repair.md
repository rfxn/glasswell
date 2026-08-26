# P3 context repair

This repair leaves `fv2.0`, `mdv1.4`, all eight split objects, and `tcv1.0` unchanged. It
corrects source population beneath those contracts and then replays them at a new evaluation
vintage. An old content-addressed partition is never overwritten.

## Formation repair policy

The 318 TEST subjects reported as missing formation have no row in
`canonical.well_completions`, but every one has a source `BAKKEN` pool observation in
`staging.nd_mpr_oil`. Migration 040 backfilled only production rows that already carried
`well_completion_pool`; historical single-pool rows predate that field.

Migration 042 restores a completion observation only when the staged pool and canonical
well-month carry the same manifest and API-10. It copies the canonical production month,
report vintage, source manifest, and promotion derivation. A pool from another workbook,
another API, or an unpromoted staging row cannot enter the repair. The insert is idempotent
and append-only.

The resident false-positive audit found `CONFIDENTIAL` staging rows for 234 of the 318 wells,
but none joined to the canonical production manifest used by the repair. The earliest exact
source observation for all 318 is therefore `BAKKEN`; the repair creates no simultaneous
formation conflict and adds no alias.

## Lateral disposition

The 38 TEST subjects labelled `missing_lateral_length` do not contain 38 recoverable measured
laterals. All have a surface, 24 have a state GIS line, and 15 have filed directional survey
stations. None has a canonical `lateral` geometry or a source `LAT*` segment: the available
GIS line keys are `STK*` or `VERT`. Fourteen have no state line at all.

That evidence resolves the data question as **source-confirmed no reported lateral**, not as a
length to fill. A survey trace is a filed path fact and migration 030 explicitly prohibits
substituting it for a state lateral. The 38 subjects remain explicit `missing_lateral_length`
terminal cases under unchanged `tcv1.0`; no survey endpoint, vertical segment, spud date, peer
ladder widening, or subject removal is used to make the gate pass.

## Replay gate

The accepted replay must:

1. build a new immutable `fv2.0` evaluation vintage after migration 042;
2. reproduce the eight resident split hashes and split-set id exactly;
3. build unchanged `mdv1.4` and `tcv1.0` twice with byte-identical outputs;
4. report control unavailability at or below 5%; and
5. publish residual missing/conflict counts without relabelling unavailable source facts.

Resident hashes and measured counts are appended here only after the migration is applied and
the two-run replay completes.

## Rollback rehearsal

The 2026-08-26 VM rehearsal executed migration 042 and both complete artifact builds inside one
database transaction, then rolled it back. It inserted 131,893 exact completion-month
observations in the transaction, restored all 318 TEST formations, left zero TEST formation
conflicts, and reduced matrix-wide missing formation from 815 to 486. The residual 486 have no
canonical-production observation joined to their staged source manifest and are therefore not
eligible for this repair.

Both runs produced the same bytes:

| Artifact | SHA-256 |
|---|---|
| `fv2.0` matrix | `39d4ba3bdfeeff962a9d2e2f0e11349d4aad7198dace08eb8ddc7ac044df19d6` |
| feature coverage | `b86504d213e6bb0cc0b2b91ef8e796b758cfc2f346bc0e415b32b1a8cc0da6f0` |
| `mdv1.4` labels | `adbebc6feb36fc92a6c32a24b5ffe353a31626311aa39635fa429c4be0770951` |
| producing-month curves | `8fae9fa2753b407a6a8ea75d1c02187ded85306ee1b1caec6fc896edf9058802` |
| model coverage | `251e811f2da298c754b46d1958b07cae7bb60b8d99c2aa2519a95d0ca58b83f9` |
| model rejections | `16bb1dbebfd798205e5a78789b76518e78c109662e9c54251fd0e572ed22c989` |
| `tcv1.0` controls | `19e7fddf6c543db2c615e1800baff7c956a4385df71a2f61cfef8366259335c2` |
| control coverage | `4387bafb9fc5062bfa75b6bf6905b5bd6f91c2912cdd5a4b0b94a3b1e08e394a` |

The split-set remains `sset_c7bbb9a6932db76b`; all eight split files byte-compare to the
resident `mdv1.4` inputs. Across 21,300 TEST subject/split instances, 230 remain unavailable
(`0.010798`), all splits pass separately, rung-one coverage rises to `0.926573`, and no
plausibility flag remains. Residual mentions are 222 `missing_lateral_length` and eight
`insufficient_peers`; missing formation is zero. The published resident replay follows the
same procedure after deployment at a new evaluation vintage rather than replacing the sealed
2026-08-26 partitions.
