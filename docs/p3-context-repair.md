# P3 context repair

This repair leaves `fv2.0`, `mdv1.4`, all eight split objects, and `tcv1.0` unchanged. It
corrects source population beneath those contracts and replays them at a new evaluation
vintage. The accepted 2026-08-28 publication is recorded below; no older content-addressed
partition was overwritten.

## Formation repair policy

Before migration 042, the 318 TEST subjects reported as missing formation had no row in
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

The accepted replay was required to:

1. build a new immutable `fv2.0` evaluation vintage after migration 042;
2. reproduce the eight resident split hashes and split-set id exactly;
3. build unchanged `mdv1.4` and `tcv1.0` twice with byte-identical outputs;
4. report control unavailability at or below 5%; and
5. publish residual missing/conflict counts without relabelling unavailable source facts.

The live publication met all five conditions at evaluation vintage 2026-08-28.

## Publication command and receipt

Run publication only from a clean tagged deployment after migrations 042 and 046 are resident.
The command does not accept caller-supplied environment or code identities. It requires the
root-written deployment stamp, verifies that stamp against `VERSION` and the deployed
`requirements.lock`, and requires the matching single-thread environment row already registered
in PostgreSQL:

```bash
set -a
. /etc/glasswell/code-version.env
set +a
# code-version.env carries the code identity and no DSN; this is the other half.
export GLASSWELL_DSN='postgresql:///glasswell?host=/var/run/postgresql'
cd /opt/glasswell/src
sudo --preserve-env=GLASSWELL_CODE_VERSION,GLASSWELL_LOCKFILE_SHA256,GLASSWELL_DSN \
  -u glasswell \
  /opt/glasswell/venv/bin/glasswell-p3-context-publish \
  --eval-vintage YYYY-MM-DD \
  --feature-root /var/lib/glasswell/features \
  --model-root /var/lib/glasswell/models
```

The evaluation vintage must advance beyond the sealed resident vintage and cannot be in the
future according to the database clock. The publisher takes an advisory lock and a
repeatable-read snapshot, verifies the resident recipe and all eight split hashes, runs the
feature, model-ready and unchanged control builders twice, compares every artifact byte, checks
coverage and rejection policy, then inserts one immutable content-addressed row in
`lineage.p3_publication_receipts` and a `publication.accepted` audit event in the same database
transaction. The JSON printed on success is a convenience copy; the database receipt is the
canonical publication record.

The candidate partitions must not exist before a run. A normal gate failure removes only the
inode-bound candidates claimed by that process and rolls back the receipt. After a hard process
kill, inspect and remove unreceipted candidate directories manually before retrying; the
publisher deliberately refuses to overwrite or silently adopt them.

## Accepted live publication

The tagged v0.59 deployment published immutable receipt
`p3pub_8b434525d8c621762e31b06ca660bfcd`, whose canonical document SHA-256 is
`8b434525d8c621762e31b06ca660bfcd89b67e70c9be58b08d65602ef9319e9b`. It pins code
`v0.59+b0be225`, environment `env_59334df47ed960e6`, split set
`sset_c7bbb9a6932db76b`, and unchanged `fv2.0`, `mdv1.4`, and `tcv1.0` identities.
The publisher ran every build twice under one repeatable-read snapshot; an independent read
then rehashed all eight artifacts and all eight split files against the receipt.

| Artifact | Rows | SHA-256 |
|---|---:|---|
| `fv2.0` matrix | 17,563 | `f6ab0c7d9bced4d67ceefa9202a1da36e3a98549ced82c79d95cae8578ddf10f` |
| feature coverage | one canonical JSON document | `7dd6340f0c06919f4e69372a5f5e4753068b5ee292187f51e6399b21177275bf` |
| `mdv1.4` labels | 105,378 | `94c9829b3fa7441da0a885b0bba00cf3755c24e6832db8df4744c25f3c9bab77` |
| producing-month curves | 1,172,586 | `a90cb98484dbd83c600558755f2055f9cd5a7f5b3eaa1e079b339a1ace69e22a` |
| model coverage | one canonical JSON document | `60bff930fd185aab2e76716fee054a47200307c9513032aaed3874fdb46bc845` |
| model rejections | 2,943 | `16bb1dbebfd798205e5a78789b76518e78c109662e9c54251fd0e572ed22c989` |
| `tcv1.0` controls | 2,300,400 | `b80b1142631820f495f6479bb23ba3a14e656b7d69979938cb9d6644e4e11f45` |
| control coverage | one canonical JSON document | `12d66f5b9fb05dba40999fff5ddc0ca85382cfd2826d3d35de0a2c42ad165c40` |

Feature coverage is 17,075 resolved, 486 missing and two simultaneous conflicts across
17,563 subjects. Across 21,300 TEST subject/split instances, 230 are unavailable
(`0.010798`): 222 missing-lateral and eight insufficient-peer mentions, with no
missing-formation mention. Every split passes its own 5% ceiling, the receipt records
`build_runs=2` and `byte_identical=true`, and the same transaction emitted the append-only
`publication.accepted` audit event.

## Pre-publication rollback rehearsal

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
`insufficient_peers`; missing formation is zero. The accepted publication above follows this
same source-faithful procedure without replacing the sealed 2026-08-26 partitions.
