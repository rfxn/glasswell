# tests/e2e — the browser path

Thirteen assertions a browser can make and `scripts/smoke.sh` cannot: that the app boots and
draws, that a deep link is a shareable state, that a figure's derivation handle reaches a
64-hex checksum and a `dmr.nd.gov` url **on screen**, that a hostile query string cannot put
the page outside the tile allowlist or off this origin, and that a visitor with no key is
refused honestly rather than shown an empty shell.

Read-only: it navigates and reads. It never writes through the API.

## Running it

```bash
export GLASSWELL_OWNER_KEY=...        # read it on the VM; it is never logged
make test-e2e                         # against https://glasswell.lab.rpx.sh
GLASSWELL_BASE_URL=http://127.0.0.1:8000 make test-e2e    # on the VM, against the origin
```

| variable | meaning |
|---|---|
| `GLASSWELL_OWNER_KEY` | the key, adopted through the `#key=` fragment exactly as SMOKE.md §2 tells the owner to |
| `GLASSWELL_BASE_URL` | API root (default `https://glasswell.lab.rpx.sh`). The same name `scripts/smoke.sh` reads; `GW_BASE` is the retired alias |
| `GW_WELL` | the well every well-level assertion reads (default `3305310451`) |
| `GW_CHROME` | chromium executable; otherwise the newest build under `/root/.cache/ms-playwright` |
| `GW_SHOTS` | a directory to write screenshots to; unset writes none |
| `GLASSWELL_REQUIRE_E2E` | `1` turns "no browser" from a skip into a failure |

## lib.mjs — the shared gate library

The machinery every DIR-11 visual gate used to re-derive under `work-output/` now lives in
`lib.mjs`: chromium discovery, `launch`, an instrumented page whose journal records page
errors, console noise, non-2xx responses, tile/API traffic and key leaks, the `BREAKPOINTS`
ladder (1600/1366/1024/820/390), screenshot helpers, a WCAG `contrastAudit` sampler and a
`frameProbe`. Gate scripts import it (`import { launch, instrumentedPage, BREAKPOINTS } from
"<repo>/tests/e2e/lib.mjs"`) and carry only their scenario. It is import-safe: playwright is
loaded lazily, so `smoke.mjs` shares it and still skips cleanly when no browser exists.

To judge a branch's own bundle against its own API (rather than the deployed instance),
`tests/support/serve_branch.py` stands up an ephemeral PostGIS, runs the branch's
migrations, loads the contract-tier seeds plus a quarantine-density and a two-pool shape,
and serves uvicorn on `127.0.0.1` — `GW_ROOT` points it at any worktree, `GW_SEED` names an
optional python file exec'd with `connection` for track-specific rows. `make serve-branch`
runs it; the printed key-file path carries the owner key.

Running `smoke.mjs` against a serve-branch instance is a useful boot check, but two of its
assertions read real ND data the fixture does not carry (viewport tile coverage and the
`dmr.nd.gov` acquisition url) — expect 11/13 there, 13/13 only against a deployed instance.

## Why this is its own npm project

`playwright-core` is a test dependency of the *browser path*, not of the shipped bundle.
Adding it to `web/package.json` would put it in the lockfile every UI track edits and in
every dependency audit of the product. This directory carries its own `package.json` and
lockfile, and `node_modules/` here is git-ignored like any other.

The chromium binary is **not** vendored: this tier reads whatever playwright build the host
already has. With no browser and no `GLASSWELL_REQUIRE_E2E`, the run prints why it skipped
and exits 0 — a green run that silently tested nothing is worse than a red one, which is why
CI sets the variable.
