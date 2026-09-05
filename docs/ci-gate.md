# Runbook — the merge gate, the nightly control, and `make test`

The Python job used to be one process running the whole suite on every push and every pull
request: 26–33 minutes, paid again on the merge commit for a tree that had already passed. This
is what replaced it, what each piece refuses to do, and what to do when one of them is red.

## What gates a merge

`.github/workflows/ci.yml`, on `pull_request` and on `push` to `main`.

| job | what it is | when it is skipped |
|---|---|---|
| `changes` | classifies the diff and asks whether this exact tree is already green | never |
| `python-lint` | ruff, the martin/tile-allowlist gate, shard parity, the unit tier | tree already green |
| `python-db` ×4 | contract + integration, `pytest -n 4` over one quarter of the collection | no `src/`, `tests/`, `requirements.lock`, `Makefile` or workflow change |
| `harness-hygiene` | `test_harness_hygiene.py` alone, on the self-managed container path | same as `python-db` |
| `web`, `e2e-guards`, `map-chrome` | vitest, tsc, the bundle, the browserless guards, the chrome geometry | no `web/` or `tests/e2e/` change |
| `shell` | `bash -n` and shellcheck over `git ls-files '*.sh'` | no `infra/`, `scripts/` or `*.sh` change |
| `collateral` | changelog grammar, SVG well-formedness and accessibility, local links, AI attribution, the IP carve-out | no docs, assets, changelog or blueprint change |
| **`ci` — "CI complete"** | the one required status check: red if any needed job failed | **never** |

`CI complete` is the only context branch protection should require. Every other job can be
filtered out by the diff, and a required check that never reports leaves the pull request
waiting forever. Repointing protection is an integrator action, in the same hour this merges:

```bash
gh api -X PATCH repos/rfxn/glasswell/branches/main/protection/required_status_checks \
  -f 'contexts[]=CI complete'
gh api repos/rfxn/glasswell/branches/main/protection --jq '.required_status_checks.contexts'
```

### Two mechanisms that decide not to run something

**The path filter (`changes.filter`).** Any doubt answers "run it": an unreachable base, a force
push, a first push and an unrecognised path all fall through to running everything. The unit tier
is never filtered — seven of its files read `CHANGELOG.md`, `VERSION`, `infra/` and `scripts/`
rather than importing anything, so no diff is provably outside it, and it costs 43 s.

**The tree-identity skip (`changes.covered`).** A merge commit whose tree equals a parent's tree
*is* that parent's tree, `ci.yml` included, so a green run at that parent is a green run of this
workflow on this content. It requires all three of: a `push` event, `tree(HEAD) == tree(parent)`,
and a `ci.yml` run at that parent with `status=success`. Any `gh api` failure runs the gate. When
it fires it writes `::notice::tree <sha> already green at <sha>` — that notice is the audit trail;
if a merge was skipped and you cannot find the notice, the skip did not happen for this reason.

It must never fire on a `pull_request`: the merge ref has no such parent, and the step exits
before looking.

## Shards, and the two things that keep them honest

`pytest-split` divides the contract and integration collection into four groups by
`tests/.durations.json`, and each shard runs its group under `pytest -n 4 --dist loadfile`. Two
failure modes come with that, and each has its own check.

**A file in no group stops running and nothing goes red.** `python-lint` collects the whole
database collection and then each of the four groups, and asserts the four sum to the whole. It
runs on every gate, including when `python-db` is filtered out.

**A test that only passed in file order.** xdist redistributes; `--dist loadfile` keeps a file on
one worker, which bounds it but does not remove it. The control is the nightly run below.

### Refreshing the durations

The committed file balances the shards; a stale one costs wall time on the slowest shard, never
correctness. `Nightly` measures a fresh one and uploads it as the `durations` artifact rather
than pushing it — a scheduled job with write access to `main` is a larger change than shard
balance is worth. To land it:

```bash
gh run download --name durations --dir .          # writes tests/.durations.json
git add tests/.durations.json && git commit
```

Or measure it locally with `make durations` (serial, and slow: `--store-durations` is unsupported
under xdist, which is why the nightly run is serial too).

## What runs nightly

`.github/workflows/nightly.yml`, 09:00 UTC and on `workflow_dispatch`. The whole suite, once, in
one process, in collection order, with no shards, no worker split, and no path filter — the
control for everything the gate's shape cannot see. It then re-runs the parity comparison against
its own collection.

**The probes that need the deployed instance are deliberately not there**: `tests/e2e/smoke.mjs`
against the public host, `infra/verify.sh`, and the restore-drill receipt. They need the owner
key, this repository holds no secrets, and the key belongs in `X-Glasswell-Key` on a host that
already has it. They run on VM 111 from its own timer. If they ever move here it is with an
environment-scoped secret and that header, never a URI parameter.

## Locally

```bash
make test         # the tests this diff can reach, -n 4, with the selection printed
make test-scope   # print the selection and run nothing
make test-full    # the whole suite, -n 4 — before pushing a release train
make test-unit    # the pure-function tier, no docker
make durations    # refresh tests/.durations.json
```

`scripts/test-scope.py` reaches a test three ways — it imports a changed module through the
transitive import graph, it is `test_<stem>.py` for a changed `src/**/<stem>.py`, or the change is
one the tool refuses to reason about. `tests/conftest.py`, `tests/support/**`, `tests/fixtures/**`,
`requirements.lock`, `Makefile`, `.github/workflows/**`, any non-`.py` file under `src/` (which is
where the migrations live) and a `pyproject.toml` edit that is more than the version string each
fall back to the whole suite. The unit tier always runs. The excluded count and the rule that
excluded it are printed on stderr, so a narrowed run is never silent.

**Selection is local only, on measurement.** The same graph run over the last six merges selected
the whole suite on five of them: real branches here touch two to four migrations and a high-fan-in
module, and one edit to `glasswell.lineage.serialization` (51 importers) reaches nearly every test.
Per-commit iteration is the opposite distribution — 0–1 test files on 8 of 18 commits — and that is
the case this serves. **CI never uses it.**

## When it is red

| symptom | what it means |
|---|---|
| `CI complete` red, every other job green or skipped | a job returned `cancelled` or `failure`; the aggregate prints `not green: <job>=<result>` |
| a pull request waits forever on a check | branch protection still pins a job name that the diff filtered out — repoint it to `CI complete` |
| `shards collect N of M`, N ≠ M | a file fell out of every group. Do not re-run; the durations file or the split arguments disagree with the collection |
| one shard much slower than the others | stale `tests/.durations.json`. Cosmetic until it pushes the wall past the budget |
| `test_release_tooling.py`'s evidence probe fails | `fetch-depth: 0` un-skipped the R8 publication-evidence probe, which had never run in CI. It is a finding, not a flake. Do not re-shallow the checkout to make it green |
| a merge on `main` skipped every test job | expected when its tree equals a green parent's. Check the `::notice::tree … already green at …` annotation on the `changes` job |
