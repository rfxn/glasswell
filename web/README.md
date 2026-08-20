# web — the ND map, well card, lineage drawer and glossary

Vite 6 + TypeScript, no UI framework. `<gw-figure>` and `<gw-term>` are native custom
elements with the attribute surfaces SB-05 §3.1 and §5.5 define, so swapping the base
class to `LitElement` later touches two class declarations and no call site.

## Build and test

```bash
npm install
npm test            # vitest, unit + component tier
npm run build       # tsc && vite build -> dist/ with hashed asset names
npm run dev         # dev server, proxying /v1 to http://127.0.0.1:8000
```

Node 20.19 or newer is required by this toolchain. `dist/` is git-ignored: it is a build
artifact, shipped by rsync, never committed.

## Serving

The API serves the built bundle itself. Point `GLASSWELL_WEB_ROOT` at a directory holding
the contents of `dist/` and uvicorn mounts it at `/` with `html=True`; `/v1` and `/healthz`
are routed before the mount. There is no separate web server in this slice.

## Runtime configuration

| Input | Effect |
|---|---|
| `#key=<owner key>` | Stored in `localStorage` and stripped from the fragment; sent as `X-Glasswell-Key` on every `/v1` request, tiles included. A fragment is never sent to the server, so the key cannot reach the access log; the API refuses `?key=` outright |
| `VITE_GLASSWELL_KEY` | Build-time fallback key, for a kiosk build where no one types a URL |
| `VITE_API_BASE` | Base for API requests when the bundle is not served from the API's origin |
| `?laterals=` · `?wells=` | Tile source ids, when martin publishes them under names other than `nd_laterals` and `nd_wells` |

`GLASSWELL_ALLOW_ANON=1` on the API removes the need for a key entirely.

## URL state

`?map=<zoom>/<lat>/<lon>&well=<api10>&explain=<handle>`. Viewport changes use
`replaceState`; selections and drawer opens use `pushState`. Paths other than `/` are not
used, because the static mount has no SPA fallback and would 404 them.
