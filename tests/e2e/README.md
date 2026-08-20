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

## Why this is its own npm project

`playwright-core` is a test dependency of the *browser path*, not of the shipped bundle.
Adding it to `web/package.json` would put it in the lockfile every UI track edits and in
every dependency audit of the product. This directory carries its own `package.json` and
lockfile, and `node_modules/` here is git-ignored like any other.

The chromium binary is **not** vendored: this tier reads whatever playwright build the host
already has. With no browser and no `GLASSWELL_REQUIRE_E2E`, the run prints why it skipped
and exits 0 — a green run that silently tested nothing is worse than a red one, which is why
CI sets the variable.
