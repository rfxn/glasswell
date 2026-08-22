# tests/e2e — the browser path

Thirteen assertions a browser can make and `scripts/smoke.sh` cannot: that the app boots and
draws, that a deep link is a shareable state, that a figure's derivation handle reaches a
64-hex checksum and a `dmr.nd.gov` url **on screen**, that a hostile query string cannot put
the page outside the tile allowlist or off this origin, and that a visitor with no key is
refused honestly rather than shown an empty shell.

Read-only: it navigates and reads. It never writes through the API.

## Running it

```bash
export GLASSWELL_KEY_FILE=/etc/glasswell/owner.key   # a path, so the key itself never appears in a command
make test-e2e                         # against https://glasswell.lab.rpx.sh
GLASSWELL_BASE_URL=http://127.0.0.1:8000 make test-e2e    # on the VM, against the origin
```

| variable | meaning |
|---|---|
| `GLASSWELL_KEY_FILE` | a file whose content is the key; wins over `GLASSWELL_OWNER_KEY` |
| `GLASSWELL_OWNER_KEY` | the key, already in the environment; sent only as the `X-Glasswell-Key` header |
| `GLASSWELL_BASE_URL` | API root (default `https://glasswell.lab.rpx.sh`). The same name `scripts/smoke.sh` reads; `GW_BASE` is the retired alias |
| `GW_WELL` | the well every well-level assertion reads (default `3305310451`) |
| `GW_CHROME` | chromium executable; otherwise the newest build under `/root/.cache/ms-playwright` |
| `GW_SHOTS` | a directory to write screenshots to; unset writes none |
| `GLASSWELL_REQUIRE_E2E` | `1` turns "no browser" from a skip into a failure |
| `GW_RUNS` | `perf.mjs` only: runs per scenario (default 5). One run is an anecdote |
| `GW_PERF_JSON` | `perf.mjs` only: a path to write the full per-run distribution to |

## Authentication — the contract

The lib is the only auth path: it reads the key from the file named by
`GLASSWELL_KEY_FILE` (else from an already-populated `GLASSWELL_OWNER_KEY`) and injects it
as the `X-Glasswell-Key` header on every same-origin request a page makes — never as a
script argument, never in any url, fragment included. Every capture the lib journals or
prints passes through its redactor, which strips the key value wherever it appears. The
lib refuses to run, loudly and naming this rule, if the key is visible in `process.argv`
or in a navigation target.

The standing dispatch line: **visual runs authenticate header-only via lib.mjs**.

The header suffices for the web app too, not just the API: the app raises its key panel
only on a 403 (`web/src/main.ts`), so a context whose requests already carry a valid
header boots authenticated — the `#key=` fragment remains the *human* adoption path
SMOKE.md §2 describes, and automation never uses it.

## lib.mjs — the shared gate library

The machinery every DIR-11 visual gate used to re-derive under `work-output/` now lives in
`lib.mjs`: chromium discovery, `launch`, header auth (`authenticate`, `keyGuard`,
`guardTarget`, `redact` — the contract above), an instrumented page whose journal records
page errors, console noise, non-2xx responses, tile/API traffic and key leaks, the
`BREAKPOINTS` ladder (1600/1366/1024/820/390), screenshot helpers, a WCAG `contrastAudit`
sampler and a `frameProbe`. Gate scripts import it (`import { launch, instrumentedPage,
BREAKPOINTS } from "<repo>/tests/e2e/lib.mjs"`) and carry only their scenario. It is
import-safe: playwright is loaded lazily, so `smoke.mjs` shares it and still skips cleanly
when no browser exists. `lib.test.mjs` covers the auth path, the redactor and the guards;
`node --test` in this directory (or `npm test`) runs it with no browser and no install.

To judge a branch's own bundle against its own API (rather than the deployed instance),
`tests/support/serve_branch.py` stands up an ephemeral PostGIS, runs the branch's
migrations, loads the contract-tier seeds plus a quarantine-density and a two-pool shape,
and serves uvicorn on `127.0.0.1` — `GW_ROOT` points it at any worktree, `GW_SEED` names an
optional python file exec'd with `connection` for track-specific rows. `make serve-branch`
runs it; the printed key-file path carries the owner key.

Running `smoke.mjs` against a serve-branch instance is a useful boot check, but two of its
assertions read real ND data the fixture does not carry (viewport tile coverage and the
`dmr.nd.gov` acquisition url) — expect 11/13 there, 13/13 only against a deployed instance.

## perf.mjs — the frame harness

`perf.mjs` is SB-05 §8.5's harness pointed at the surfaces P-A built: an in-page
`requestAnimationFrame` sampler across a scripted deterministic interaction, reported as
p50/p95/max, dropped frames and the time spent beyond the display's cadence, over `GW_RUNS`
runs. It is not part of `make test-e2e` — it is a measurement a human takes and records in
`web/PERF.md`, which is also where the reference client, the honest reading of a
vsync-quantised distribution, and the reasons the map's S2 number is not in it are written
down.

```bash
GLASSWELL_BASE_URL=http://127.0.0.1:8161 GLASSWELL_KEY_FILE=/tmp/gw-c11/owner.key \
  GW_RUNS=5 GW_PERF_JSON=/tmp/perf.json node tests/e2e/perf.mjs
```

## Why this is its own npm project

`playwright-core` is a test dependency of the *browser path*, not of the shipped bundle.
Adding it to `web/package.json` would put it in the lockfile every UI track edits and in
every dependency audit of the product. This directory carries its own `package.json` and
lockfile, and `node_modules/` here is git-ignored like any other.

The chromium binary is **not** vendored: this tier reads whatever playwright build the host
already has. With no browser and no `GLASSWELL_REQUIRE_E2E`, the run prints why it skipped
and exits 0 — a green run that silently tested nothing is worse than a red one, which is why
CI sets the variable.
