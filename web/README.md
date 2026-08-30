# web — Map, Explore, Status, well card, lineage and glossary

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

`public/brand/` holds copies of the hand-authored SVGs in the repository's `assets/`;
refresh them by copying, never by editing the copy (BRAND.md is the source of truth).
`public/favicon-32.png` and `public/og-card.png` are rendered derivatives copied the same
way — regenerate the source in `assets/` per BRAND.md, then re-copy.

## Serving

The API serves the built bundle itself. Point `GLASSWELL_WEB_ROOT` at a directory holding
the contents of `dist/` and uvicorn mounts it at `/` with `html=True`; `/v1` and `/healthz`
are routed before the mount. There is no separate web server in this slice.

## Runtime configuration

| Input | Effect |
|---|---|
| `GLASSWELL_PUBLIC_ORIGIN` | Build-time. The origin `og:image` and `twitter:image` are resolved against, because Open Graph consumers do not reliably follow a relative one. Unset leaves them root-relative, which is the LAN deployment |
| `VITE_API_BASE` | Base for API requests when the bundle is not served from the API's origin |
| `?laterals=` · `?wells=` | Tile source ids, when martin publishes them under names other than `nd_laterals` and `nd_wells` |

The browser signs in at `POST /v1/session` and rides a `__Host-gw_session` cookie from there;
state-changing calls echo the `GET /v1/session/challenge` token in `X-Glasswell-CSRF`. There is
no browser-side API key: `X-Glasswell-Key` is the machine path, and the Explore pane's
copy-as-curl snippets are the only place the web tier names it.

## URL state

`?view=map|explore|status&map=<zoom>/<lat>/<lon>&well=<api10>&explain=<handle>`. Viewport changes use
`replaceState`; selections and drawer opens use `pushState`. Paths other than `/` are not
used, because the static mount has no SPA fallback and would 404 them.

Status is a first-class surface backed by keyed `GET /v1/status`. It renders live API and
PostgreSQL reachability beside a sanitized scheduled host snapshot, exact or explicitly
estimated dataset inventory, scheduled jobs, and registered-artifact age. Runtime validation
rejects malformed successful responses, and stale telemetry suppresses prior green states.
