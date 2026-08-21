# SB-05 — Map & UI

**Sub-blueprint. Status: draft for review. Owner: Ryan MacDonald.**
Scope: epic **E7 (map and UI)** and epic **E18 (glossary-as-data, UI half)** of
`blueprint-v0.6-draft.md`, plus the UI half of **E10** (the lineage drawer) and the
auditor surfaces of **E11**.

**The UI is Mandate B's classroom** (v0.6 §1.1). Every decision below is justified against
one of two questions: *does it make a number traceable*, or *does it teach the reader the
domain*. Anything that serves neither is in §13 (cut as gold-plating).

**Citation convention.** `v0.6 §N` = `blueprint-v0.6-draft.md` section N · `DIR-n` =
`work-output/direction-log.md` · `SB-06 §N` / `SB-07 §N` = sibling sub-blueprints.
Evidence key inherited from SB-06 so tags read the same across documents:

| Tag | Meaning |
|---|---|
| **[V]** | Verified — read from a file in this repo, or from a sibling SB that verified it |
| **[I]** | Inferred — conclusion from verified facts, reasoning stated inline |
| **[A]** | Assumed — general/external knowledge or an unmeasured estimate; must be confirmed before relied on |

**Every `[A]` in this document that touches a budget is converted into a P2 measurement
task in §9.** An estimate that never becomes a measurement is a guess wearing a costume.

---

## 0. Scope and obligations

### 0.1 What SB-05 owns

| Owns | Does not own |
|---|---|
| The browser application: build tooling, framework, bundle, routing, state | Any endpoint's implementation or response shape (SB-04, SB-07) |
| Map system: basemap, layer inventory, MapLibre/deck.gl split, S2 performance | Tile *source tables*, martin config, PostGIS geometry (SB-01, SB-06) |
| Chart system: library choice, chart-frame contract, chart spec artifact | Forecast/type-curve/valuation *content* (SB-02, SB-03) |
| Every UI surface in v0.6 §3.2 C13/C14: well card, type-curve builder, league table, scenario card, inventory view, lineage drawer, quarantine/scorecard/conformance views, notebook reader | The data those surfaces render |
| **The glossary hover system** — index fetch, highlighter, `<gw-term>`, popover, coverage CI hook (DIR-8, E18) | `glossary_terms` rows and their prose (SB-01), `/v1/glossary` endpoints (SB-04) |
| URL grammar and the "any view is shareable and reproducible" property | `as_of` semantics server-side (SB-07 §3) |
| CSP *content*, a11y, keyboard model, browser floor | Where the CSP header is emitted (SB-06 §4.5) |
| Frontend test suites (vitest, Playwright) and the UI perf harness | pytest tiers (DIR-10, SB-04/SB-07) |
| The `tiles.build` derivation *display* contract and layer-provenance UI | Emitting the derivation itself (job side: SB-01) |

### 0.2 Requirements this SB satisfies

| Requirement | Source | Satisfied in |
|---|---|---|
| **S2** 20k+ laterals, model-driven styling, interactive frame rates | v0.6 §2.4 | §2.3, §2.4, §8.5 |
| **S9** any UI number → raw manifest in ≤3 interactions and one `/explain` | v0.6 §2.4 | §4.2 |
| **S13** every surfaced term resolves through `/v1/glossary`, CI-proven | v0.6 §2.4, DIR-8 | §5 (whole section), §5.7 |
| **S1** a stranger with a guest key reproduces every number in the UI | v0.6 §2.4 | §3.1, §6.5 |
| **S3** scenario forecast + NPV under 3 s, felt as such | v0.6 §2.4 | §3.5 |
| **E7** map, well card, scenario card, builder, league, inventory, drawer, notes | v0.6 §5 | §2, §3, §4 |
| **E18** one tooltip component, auto-highlighting from the index, never hand-tagged | v0.6 §5, DIR-8 | §5.3, §5.5 |
| **R5** estimates are labelled — allocated/modelled/assumed, everywhere | v0.6 §3.3 | §3.1, §3.9.4 |
| **R6** every served figure carries a derivation handle | v0.6 §3.3 | §3.1, §8.2 |
| **R9** glossary coverage, CI-enforced | v0.6 §3.3 | §5.7 |
| **U1, U2, U3, U7, U10, U12, U13, U17, U18, U19, U21, U22** | v0.6 §6 | §3, §4, §5 |
| Anti-story *"no UI figure without an endpoint that reproduces it"* | v0.6 §6.1 | §3.1, §6.5, §8.2 |
| Anti-story *"no blended vintages inside one served series"* | v0.6 §6.1 | §3.9.3 |
| Anti-story *"no estimate presented as an observation"* | v0.6 §6.1 | §3.9.4 (a rendering rule with a test) |
| **DIR-1** boring and auditable; survives a hostile expert | direction log | §1.2, §3.9.1, §12 |
| **DIR-10** TDD, tests with or before implementation | direction log | §8 |
| `tiles.build` derivation surfaced; no naked map styling | SB-07 §12 | §2.7 |

### 0.3 The SB-04 dependency — stated, not assumed

**`SB-04-api-agent-gateway.md` did not exist when this document was authored** (checked
2026-08-20 **[V]**). The endpoint catalog used here is therefore **v0.6 §3.6.12 (41 rows)
plus SB-07 §9.4** for the lineage/quarantine/conformance surfaces. Where the two disagree,
§11 records it as errata rather than silently picking one.

The exposure is contained to **one module**, `ui/src/api/` — envelope parsing, path
construction, error mapping, pagination and `as_of` propagation live there and nowhere
else. Every other module consumes normalized view models. When SB-04 lands, reconciliation
is a diff against one directory, and §10 lists the exact seven contract points to re-check.
This is not defensive style for its own sake: the envelope is the single most likely thing
to move (§11 E-4), and a UI that spreads envelope knowledge across forty files cannot
absorb that move.

---

## 1. Frontend architecture

### 1.1 The decision table

| Layer | Choice | Why |
|---|---|---|
| Language | **TypeScript 5.x, `strict: true`, `noUncheckedIndexedAccess`** | The envelope, the handle grammar and the unit/granularity flags are exactly the things a type system should stop you getting wrong |
| Build | **Vite 6** (`base: '/'`, target `es2022`, no polyfills) | Boring, fast, static output, no SSR machinery to reason about |
| Framework | **Lit 3 + native custom elements**; no VDOM framework, no router library | §1.2 |
| Map | **MapLibre GL JS 5.x** + **deck.gl 9.x** via `@deck.gl/mapbox` `MapboxOverlay` (interleaved) | Pinned by v0.6 §3.1; interop path is the vendor-documented one **[A — confirm the overlay API at P2]** |
| Basemap | **Protomaps PMTiles regional extract**, self-hosted; graticule-only fallback | §2.1 |
| Charts | **uPlot 1.6** for time-series/band/decline; hand-rolled SVG (~200 lines) for tornado and small categorical charts | §3.9.1 |
| Tables | **`@tanstack/table-core` + `@tanstack/virtual-core`** (headless, framework-agnostic) | Sorting/filtering/virtualization are solved problems; both are framework-free, so they do not re-import a framework decision through the back door |
| Markdown | **markdown-it 14**, HTML disabled, custom token rules | §3.8 |
| Arrow IPC | **`apache-arrow` reader, dynamically imported** on first model-styled layer | §2.5; the cost is measured and has a stated fallback |
| Tests | **vitest** (unit + component, happy-dom) · **Playwright** (smoke, a11y, perf) · **MSW** (fixture serving) | §8 |
| Lint / format | **ESLint (flat config) + Prettier**, plus three project rules (§5.7, §3.1, §12) | The three custom rules are what make R6/R9 mechanical in the UI |
| Package manager | **npm** with a committed `package-lock.json`; lockfile SHA-256 recorded in the bundle recipe | R7 applies to the bundle (§1.4) |
| Runtime deps | **Zero CDNs. Zero web fonts. Zero analytics. Zero telemetry.** | Single origin (SB-06 §1.3), `connect-src 'self'` (§1.5), and a private PoC that phones nowhere |

### 1.2 Framework: Lit, and the honest cost

**Decision: Lit 3 with custom elements, light DOM by default.** This **diverges from
v0.6 §3.1's "React + TypeScript + Vite"**, which is change-controlled (v0.6 §10) — the
divergence is logged as errata E-1 and requires an SB-00 ratification or a reversal.

Four reasons, in order of weight:

1. **The glossary needs custom elements regardless of the framework.** Highlighted terms
   must appear inside markdown-rendered memo prose, inside chart-frame labels emitted next
   to a canvas, inside virtualized table cells, and inside conformance rationale text. The
   only component model that spans all four without a per-container adapter is a custom
   element (§5.5). Given that one custom element is mandatory, a second component model
   for everything else is a tax with no payer.
2. **A VDOM competes with the map for DOM ownership.** MapLibre and deck.gl are imperative,
   own a canvas and a container subtree, and hold a WebGL context whose lifecycle must not
   be governed by render-cycle heuristics. React's StrictMode double-invoke and effect
   re-run semantics are a well-known source of duplicated map instances and lost GL
   contexts **[A]**. Lit's `connectedCallback`/`disconnectedCallback` are DOM lifecycle,
   which is the lifecycle the map actually has.
3. **Auditability: the shipped bundle resembles the source.** Tagged template literals are
   not transformed into a foreign call shape; a reader diffing source against bundle is
   reading the same structure. Under DIR-1 that is worth real weight, and it is the same
   argument the blueprint makes for declarative chart specs (v0.6 §3.1).
4. **Weight.** Lit is ~6 KB gz **[A]** versus React+ReactDOM ~45 KB gz **[A]**. On the
   CONDITIONAL bandwidth branch (SB-06 §11 step 1, 10–25 Mbps) every kilobyte of shell is
   competing with tiles for the same uplink.

**What this costs, stated plainly.** No `react-map-gl`, no `@deck.gl/react`, no TanStack
React adapters, no component library. The interop we lose is exactly the thin part:
`new MapboxOverlay({interleaved: true, layers})` added as a MapLibre control is the
documented vanilla path and is *less* code than the React binding. The table headless cores
are framework-free by design. The router is ~120 lines of `URLPattern`-plus-`popstate`
(§6). The genuine loss is ecosystem familiarity if this ever stops being a solo build.

**Escape hatch, pre-decided so it is a lookup and not a negotiation (R-02 style):** if Lit
proves wrong, **Preact 10** replaces it behind the same custom-element boundary — every
surface is already `<gw-*>` elements with attribute/property inputs, so the swap is
per-element and incremental. React is *not* the escape hatch; if we are paying a VDOM cost
we pay the 10 KB one.

**Rejected:** Svelte (compiler magic is the opposite of "the bundle resembles the source"),
Angular (weight), htmx/server-rendered (the map and charts are client state by nature;
v0.6 §3.1 already says static), vanilla-only (we would re-implement reactive attribute
binding and template diffing badly — Lit *is* the boring version of that).

### 1.3 No SSR; static serving; the Caddy amendment SB-06 owes us

No SSR, no prerender, no service worker (§13). Output is hashed static assets under
`ui/dist/`, deployed to `/opt/glasswell/web/` (SB-06 §1.3 **[V]**).

SB-06 §1.3 promises static assets served by Caddy from `/opt/glasswell/web/`, but the
Caddyfile in SB-06 §4.5 routes only `/tiles/*` → martin and **everything else → uvicorn**
**[V]**. Those two statements are inconsistent, and as written a deep link like
`/wells/33053012340000` reaches FastAPI rather than the app shell. **Interface request to
SB-06** (errata E-9):

```
handle_path /tiles/*   { reverse_proxy 127.0.0.1:3000 }   # martin
handle /v1/*           { reverse_proxy 127.0.0.1:8000 }   # API
handle /openapi.json   { reverse_proxy 127.0.0.1:8000 }
handle /healthz        { reverse_proxy 127.0.0.1:8000 }
handle {                                                   # app shell
    root * /opt/glasswell/web
    try_files {path} /index.html
    file_server
    header /assets/* Cache-Control "public, max-age=31536000, immutable"
    header /index.html Cache-Control "no-cache"
}
```

`try_files … /index.html` is what makes every URL in §6 deep-linkable, which is what makes
"any view is shareable" true rather than aspirational. Hashed assets are immutable;
`index.html` is never cached, so a deploy is atomic from the browser's point of view.

### 1.4 The bundle is a lineage artifact

The UI is the surface S1's stranger reads. "Which UI rendered this screenshot" must be
answerable, so the build participates in the same regime as everything else (v0.6 §3.3 R7):

- `npm run build` emits `ui/dist/build-info.json`: git revision, `package-lock.json`
  SHA-256, node version, Vite version, output file list with SHA-256s, build timestamp.
- The deploy job records a **recipe** (SB-07 §4.1) for the bundle: entry point
  `ui:build`, determinism class **`value_equal`** — Vite output is not byte-stable across
  environments without pinning we are not paying for **[I]** — with the honest note that a
  `byte_exact` frontend build is achievable and deliberately not attempted (§13).
- The app shell renders the build revision in the footer and in `GET /v1/health`'s UI
  section, linked to the recipe. A UI whose provenance is unknown is a naked artifact.

**Bundle budgets** (measured in CI by `size-limit`, failing the build on regression):

| Chunk | Budget (gz) | Contents |
|---|---|---|
| shell | **60 KB** | Lit, router, api client, glossary scanner + index, figure chip, tooltip, tables |
| map | **520 KB** | MapLibre GL + deck.gl + pmtiles, lazy-loaded on map routes only **[A — measure at P2]** |
| charts | **60 KB** | uPlot + chart frame + SVG charts, lazy on first chart |
| arrow | **150 KB** | Arrow IPC reader, lazy on first model-styled layer **[A]**; §2.5 states the fallback if this is exceeded |

A well card with no map and no model-styled layer therefore costs shell + charts ≈ 120 KB
gz. That is the number that matters for the guest on a phone reading a notebook memo.

### 1.5 Browser floor, CSP, security posture

**Floor:** last two versions of Chrome, Firefox and Safari, **WebGL2 required** (deck.gl 9
hard requirement **[A]**). No IE, no polyfills, no transpile below es2022. If WebGL2 is
absent the app renders the **list-view equivalent** of every map surface (§2.6) rather than
a broken canvas — which is also the accessibility answer, so it is one mechanism serving
two obligations.

**CSP content** (SB-05 owns the content, SB-06 §4.5 emits the header **[V]**):

```
default-src 'none';
script-src 'self';
style-src 'self';
style-src-attr 'unsafe-inline';
img-src 'self' data: blob: https://basemap.nationalmap.gov;
font-src 'self';
connect-src 'self' https://basemap.nationalmap.gov;
worker-src 'self' blob:;
child-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none';
object-src 'none'; upgrade-insecure-requests
```

Notes and honesty: `style-src-attr 'unsafe-inline'` is required because MapLibre and
deck.gl set element `style` attributes directly **[A]**; it is the narrowest directive that
permits that and it does not permit inline `<style>` or inline event handlers.
`worker-src blob:` is listed because MapLibre has historically constructed its worker from
a blob URL **[A]** — **P2 task: verify against the pinned MapLibre build and delete `blob:`
if it is not needed.** `connect-src` is the machine-checkable expression of SB-06's "single
origin, so no CORS is required or permitted" **[V]**, with exactly one named exception:
`basemap.nationalmap.gov`, the USGS National Map imagery the satellite option draws from.
It is public domain and keyless — a third-party basemap *key* would still break this line,
which is §2.1's argument intact — and the requests happen only when a reader selects
satellite; the dark, light and none options remain zero-external, and a test holds them
there. The origin is named, never a wildcard, and it appears in `connect-src` and `img-src`
only, never in a directive that loads code. Amended by controller ruling under DIR-1
(`work-output/wave1-gate-findings.md`), which also requires that the imagery's declared
graticule fallback actually execute — a fallback the policy forbids is not a recovery.

Ship CSP in `Report-Only` for the first week of P2, then enforce. No `unsafe-eval`
anywhere: this rules out any charting or templating library that compiles at runtime,
which is a deliberate constraint on §3.9.1's options.

### 1.6 Repository layout

v0.6 §3.7.10 gives `ui/` one line ("React app, map, cards, drawer, glossary tooltip").
Expanded:

```
ui/
  index.html
  src/
    app/          router, shell, layout, theme, error boundary
    api/          envelope parsing, paths, errors, as_of, pagination   ← the SB-04 seam (§0.3)
    figure/       <gw-figure>, unit/granularity/vintage formatting
    glossary/     index client, trie scanner, <gw-term>, popover        (§5)
    lineage/      drawer, chain renderer, node cards, recipe/curl       (§4)
    map/          maplibre setup, deck layers, styles, attribute join   (§2)
    charts/       chart frame, uPlot adapters, ChartSpec, svg charts    (§3.9)
    tables/       headless table + virtualization + column kit          (§3.10)
    views/        well-card, typecurve-builder, league, scenario,
                  inventory, quarantine, scorecard, conformance,
                  notebook, glossary-browser, manifest
    labels.ts     the label() helper — the R9 enforcement point         (§5.7)
  test/
    unit/ component/ e2e/ fixtures/ perf/
  PERF.md         measured budgets, re-measured at each phase exit
```

---

## 2. Map system

### 2.1 Basemap: self-hosted PMTiles, with a graticule-only fallback

**Constraints:** no paid tiles; no API keys (a key is a credential in a public bundle and
breaks `connect-src 'self'`); single origin (SB-06 §1.3 **[V]**); must work on the LAN
break-glass path with Cloudflare unavailable (SB-06 §4.5 **[V]**); must degrade on the
10–25 Mbps CONDITIONAL branch (SB-06 §11 step 1 **[V]**).

**Decision: a Protomaps PMTiles extract of the ND + Permian bounding boxes, served as a
static file by Caddy from the same origin, read by MapLibre via the `pmtiles` protocol
handler with HTTP range requests, styled with the `protomaps-themes-base` dark and light
themes retuned to BRAND.md's palette.** **[A — extract size unmeasured; P2 task.]**

Why this and not the alternatives:

| Option | Verdict |
|---|---|
| **PMTiles extract, self-hosted** | **Chosen.** One immutable file, no key, no external origin, works offline and on the LAN listener, range requests are native to Caddy, and SB-06 §11 already names PMTiles as the CONDITIONAL-branch mitigation **[V]** — so the mitigation and the default are the same code path |
| `tile.openstreetmap.org` raster | Rejected: third-party origin (breaks `connect-src 'self'`), OSMF tile-usage policy discourages application use **[A]**, and it dies on the LAN break-glass path |
| MapTiler / Stadia free tier | Rejected: API key in the bundle, external origin, ToS exposure on a project that already has a licensing posture to defend (v0.6 §3.7.9) |
| No basemap at all | Kept as a **first-class toggle**, not as the default — see below |
| Rendering our own basemap from OSM data in PostGIS | Rejected as gold-plating: a basemap pipeline is a project, not a task |

**The graticule-only style is a shipped toggle** (`?base=none`), not a fallback nobody
tests: PLSS sections and townships, county boundaries and spacing units are themselves the
locational reference an upstream reader actually uses, and on the CONDITIONAL bandwidth
branch it removes the basemap from the uplink entirely. It is also the honest default for
screenshots in the notebook, where an OSM basemap adds noise and an attribution obligation.

**Attribution is non-negotiable and non-dismissable:** "© OpenStreetMap contributors" plus
the Protomaps/Natural Earth credit in the map's attribution control whenever the PMTiles
base is active. The basemap gets a row in `sources` with its licence status and evidence
URL, exactly like a regulator file (v0.6 §3.7.9) — it is the cheapest possible demonstration
that the licensing posture is a habit rather than a paragraph.

### 2.2 Layer inventory

| # | Layer | Geometry source | Engine | Styling driver | Lifecycle | Phase |
|---|---|---|---|---|---|---|
| L1 | Basemap | PMTiles static file | MapLibre native | Static theme | Rebuilt on demand (rarely) | P2 |
| L2 | PLSS sections / townships (`land_units`) | martin `/tiles/land_units` | MapLibre native (line + fill) | Static; `feature-state` for hover/select | On GIS refresh | P2 |
| L3 | Spacing units | martin `/tiles/spacing_units` | MapLibre native | Static by formation (categorical) | On GIS refresh | P2 |
| L4 | Well surface points | martin `/tiles/wells` | MapLibre native (circle) | Categorical: status, operator | On GIS refresh | P2 |
| L5 | **Laterals (the S2 layer)** | martin `/tiles/laterals` | **deck.gl `MVTLayer` (binary)** | **Continuous, model-driven, client-joined from the attribute bundle** | Geometry on GIS refresh; **styling on model publication, no tile rebuild** (v0.6 §3.5 **[V]**) | P2 (categorical), P3 (model-driven) |
| L6 | Bottomholes | martin `/tiles/wells` (same source, different layer) | MapLibre native | Categorical | On GIS refresh | P2 |
| L7 | Permits | martin `/tiles/permits` | MapLibre native | Categorical by status/date bucket | Daily | P5 |
| L8 | Activity / DUC heatmap | deck.gl `HeatmapLayer` over a permits aggregate | deck.gl | Continuous density | Weekly | P5 |
| L9 | AOI polygons | **`GET /v1/aois` GeoJSON** — never a tile (§2.8) | MapLibre native (source: geojson) | Owner-scoped | On mutation | P5 |
| L10 | Well sets | `GET /v1/wellsets/{id}` GeoJSON | MapLibre native | Owner-scoped | On mutation | P5 |
| L11 | Inventory slots | `GET /v1/inventory/runs/{id}/slots` GeoJSON | deck.gl `PolygonLayer`/`PathLayer` | NPV / training support, continuous | Per run | P8 |
| L12 | Selection + hover halo | client-side | MapLibre native | Ephemeral | — | P2 |
| L13 | Graticule / PLSS labels | martin (labels from `land_units`) | MapLibre native symbol | Static, zoom-gated | On GIS refresh | P2 |

Layer visibility, ordering and opacity are URL state (§6.1), so a shared link reproduces
the reader's exact map, not an approximation of it.

### 2.3 The rule: when MapLibre native, when deck.gl

Stated once, as a rule, so it does not get re-litigated per layer:

> **Native MapLibre** when the styling is expressible in the style spec from properties that
> are already inside the tile — categorical fills, status colours, zoom-gated widths, labels,
> hover/selection via `feature-state`.
> **deck.gl** when the styling is driven by a **continuous attribute joined client-side after
> the tile arrives** — i.e. anything from the model attribute bundle — or when the layer is
> a GPU aggregation (heatmap, large polygon sets).

Justification: v0.6 §3.5 pins that model output is **not baked into tiles** so that a model
rerun does not regenerate tiles **[V]**. That decision is precisely what makes native style
expressions insufficient for L5: the value is not in the tile. The two remaining options are
(a) `setFeatureState` for 20k features per bundle load, or (b) a deck.gl accessor closing
over a lookup map. We take (b) for L5 and keep `feature-state` for interaction only (L12),
because `setFeatureState` is a per-feature JS call and 20k of them on every model switch is
a stall of a size we would have to measure and defend **[I]**, while deck.gl's accessors run
once per tile load and are re-triggered declaratively via `updateTriggers`.

deck.gl is mounted **interleaved** (`new MapboxOverlay({interleaved: true})` added as a
MapLibre control) so deck layers z-order correctly against basemap and land-unit layers
rather than floating above everything in a second canvas. Non-interleaved overlay mode is
the fallback if interleaving costs frames **[A — measure at P2]**.

### 2.4 S2: the performance budget and the eight techniques

**v0.6 §2.4's S2 is untestable as written** — "interactive frame rates" names no number and
no reference machine, while v0.6 §3.7.8 makes every other budget a test **[V]**. Errata E-3.
SB-05 pins it:

> **S2 (pinned).** With **20,000 laterals in view at z=9** and model-driven styling active,
> a scripted pan-and-zoom on the reference client sustains **p95 frame time ≤ 22 ms
> (≈45 fps)** with **no frame > 100 ms**, and the map is interactive (first paint of L5)
> within **2.5 s** of route entry on a warm cache.
> **Reference client:** the owner's primary workstation, exact specification recorded in
> `ui/PERF.md` at P2. **Secondary floor:** a 2020-class laptop with integrated graphics, at
> p95 ≤ 33 ms (≈30 fps), reported but not gating.

Measurement is in §8.5, in CI, from P2 onward. ND has roughly 19–20k horizontal wells, so
this is a real workload, not a synthetic one **[I, from v0.6 §2.4's own framing]**.

The eight techniques, in the order they buy the most:

1. **Server-side simplification by zoom.** martin serves L5 from a PostgreSQL function
   source, not a table source, so tolerance is a function of `z`:
   `ST_AsMVTGeom(ST_SimplifyPreserveTopology(geom_3857, tol(z)), bounds, 4096, 64, true)`
   with `tol(z)` ≈ `40 m` at z≤8, `10 m` at z9–10, `2 m` at z11–12, `0` (no simplify) at
   z≥13 **[A — tune against measured tile bytes at P2]**. A Bakken lateral is ~2 miles; at
   z=9 it is a few dozen pixels, and vertex-level fidelity is invisible and unaffordable.
2. **Zoom-gated layer substitution.** Below z=8, L5 is not served at all: the map shows a
   section-level aggregate (count and median styling attribute per PLSS township) from a
   separate low-cardinality tile source. A 20k-line layer at z=6 is 20k sub-pixel strokes —
   pure cost, zero information.
3. **The attribute bundle, not fatter tiles** (v0.6 §3.5 **[V]**, contract in §2.5).
4. **`updateTriggers`, never layer re-creation.** Style changes (model switch, colour ramp,
   filter) mutate accessor inputs and bump an `updateTriggers` key; they never construct new
   layer instances. Re-creating an `MVTLayer` discards its tile cache — the single most
   common way to turn a 45 fps map into a 5 fps one **[I]**.
5. **Interaction is `feature-state` and `highlightedObjectIndex`, not data churn.** Hover
   and selection never touch the data path; picking is enabled only on L4/L5/L11 with
   `pickingRadius: 4`.
6. **Viewport-driven fetches are debounced (250 ms) and cancelled** via `AbortController`
   on the next move. A pan that issues 40 requests it will not use is the bandwidth failure
   mode SB-06 §11's threshold derivation is built on **[V]**.
7. **devicePixelRatio capped at 2**, `antialias: false` on the deck canvas unless measured
   to be free. A 4K display at DPR 3 quadruples fragment work for a line map.
8. **No text on the hot layer.** Labels live on L13 (zoom-gated, native symbol layer); L5
   renders no per-feature text at any zoom. Symbol layout is the usual hidden cost in a
   dense vector map **[A]**.

**Re-measure the whole budget at P7** when the Permian arrives — an order of magnitude more
laterals is OQ-14's open question, and §2.5's ceiling is where it lands first.

### 2.5 The attribute bundle contract (and a §3.5 correction)

v0.6 §3.5 says deck.gl "fetches a compact binary attribute bundle (Arrow IPC) for the
**current viewport's key set**" **[V]**. As written that is unbuildable and uncacheable:
the client cannot know the key set until the geometry tiles have loaded (chicken-and-egg),
and a per-viewport response has no stable cache key, so every pan re-downloads attributes
for wells it already has. Errata E-5. The buildable form:

> **Bundle identity is `(layer, basin, model_id, as_of)` — not the viewport.** The URL is
> `GET /v1/tiles/attributes?layer=laterals&basin=nd&model_id=mdl_…&as_of=…`, the response is
> immutable by construction (all four inputs are content-addressed or vintage-pinned), and it
> is served with `Cache-Control: public, max-age=31536000, immutable`. The client stores it in
> the Cache API keyed by that URL. One fetch per basin per model publication, ever.

Shape: Arrow IPC, one record batch, columns `api10` (uint64 or 10-byte fixed binary),
`value` (float32), `training_support` (float32), `bucket` (uint8), plus the schema-level
metadata `derivation_id`, `model_id`, `as_of_vintage`, `unit`, `granularity`. At 20k rows ×
~20 B that is ~400 KB uncompressed, well inside v0.6 §3.5's "a few hundred kilobytes"
**[I]**, and gzip on a columnar layout does better than that.

**The ceiling (OQ-14) becomes a measured trigger, not a surprise:** if a bundle exceeds
**2 MB gz**, the client switches to bbox-partitioned bundles keyed by a fixed tile-parent
grid (z=6 cells), which keeps immutability and cacheability while bounding size. The trigger
is checked in CI against the fixture basins and reported in `ui/PERF.md`.

**Arrow fallback:** if the lazily-imported Arrow reader exceeds the 150 KB gz budget
(§1.4), the fallback is a documented fixed-layout binary (`gwab/1`: JSON header +
little-endian typed arrays, ~40 lines of reader). This is stated now so that discovering
the cost at P2 is a decision, not a rewrite. Note that Arrow is preferred while it fits
because the *same bytes* are readable by DuckDB and Polars, which is what lets the CI check
in §8.4 assert that the styled values equal the served values.

### 2.6 Interaction, selection, and the non-map equivalent

- **Hover** on L5/L4: a lightweight inspector chip near the cursor — API-10, well name,
  operator, the styled value with its unit and granularity. Never a full card; hover must
  cost one lookup, not one request.
- **Click**: selects the well, pushes `/wells/{api10}` (§6.1), and opens the well card in
  the split layout. The map keeps its viewport — losing map context on selection is the
  most common map-app usability defect **[A]**.
- **Shift-drag**: box select → a well set candidate (P5).
- **Draw**: AOI polygon drawing (P5) via MapLibre's draw interaction, submitted to
  `POST /v1/aois`.
- **Every map-driven task has a keyboard- and screen-reader-reachable equivalent.** The
  **viewport list view** (`?view=list`) is a virtualized table of the wells currently in
  the viewport with every column the map encodes as colour or width, sortable and
  filterable. This is (a) the a11y answer for a canvas surface, (b) the WebGL2-absent
  fallback (§1.5), and (c) the honest expression of the anti-story *"no UI figure without
  an endpoint that reproduces it"* — if the map can show it, a table can list it and an
  endpoint served it.

### 2.7 Map provenance: styled numbers are numbers (SB-07 §12 obligation)

SB-07 §12 requires that a `tiles.build` derivation exist per layer build, that its
`derivation_id` ride in the TileJSON metadata, and that model-driven styling attributes
carry their own handles — otherwise map-styled numbers are naked numbers (API-09)
**[V]**. SB-05's half of that contract:

- Every layer's info affordance (the ⓘ in the legend row) shows: geometry build
  `derivation_id` (from TileJSON `metadata`), the styling `model_id` and `as_of` (from the
  bundle's Arrow schema metadata), the unit, and the granularity — each a chip that opens
  the lineage drawer (§4).
- The **colour ramp legend is a figure surface**: its stops carry the unit and the
  normalization (`per_1000ft` vs absolute, v0.6 D-2), and the legend header carries the
  bundle's `derivation_id`.
- **A model-styled layer cannot be enabled if the bundle lacks `derivation_id`** — the
  layer refuses to render and shows "styling provenance missing" instead. This is a rendering
  rule with a unit test (§8.2), not a convention.

### 2.8 Tile auth: the D-5 collision, and the resolution SB-05 proposes

v0.6 §3.6.8/D-5 specifies short-lived signed tile tokens minted at `POST /v1/tiles/token`
and validated by a proxy in front of martin **[V]**. SB-06 §1.3/§4.5 routes `/tiles/*`
straight from Caddy to martin and forbids SB-04 from defining routes under `/tiles/*`
**[V]**. Under SB-06's routing there is no component positioned to validate that token, and
Caddy has no HMAC-verification directive **[A]**. The two documents cannot both be built.
Errata E-2 / E-6.

**SB-05's proposed resolution, offered to SB-00/SB-04 for ratification:**

> **martin serves public reference geometry only.** Every principal-scoped geometry — AOIs,
> well sets, inventory slots, saved scenarios — is served as **GeoJSON from the API** (L9,
> L10, L11 above), where the existing `owner_principal`/`visibility` check already applies
> and where the object counts are small (a township inventory run is ~10²–10³ slots, not
> 10⁴ **[A]**). With no private tiled layer in v0.6, layer entitlement collapses to
> "authenticated principal", which Cloudflare Access plus the origin JWT check already
> guarantee (SB-06 §5 **[V]**). `POST /v1/tiles/token` and D-5 are therefore **not needed in
> v0.6** and should be either deleted or explicitly deferred with the reinstatement
> condition recorded: *the first tiled layer whose contents are not public data*.

Why this and not a `forward_auth`: an auth round-trip per tile request competes directly
with v0.6 §3.7.8's `tile p95 < 150 ms warm` budget **[V]**, and a 40-tile pan would issue 40
extra origin round-trips on a residential uplink whose capacity is the project's stated
placement risk (SB-06 §11 **[V]**). Paying that cost to protect data that is public by
definition is the sort of decision a hostile reviewer takes apart in one question (DIR-1).

Consequence for tile URLs: **`GET /tiles/{layer}/{z}/{x}/{y}.pbf`** (Caddy → martin), while
the attribute bundle stays at **`/v1/tiles/attributes`** (Caddy → uvicorn, since
`/v1/tiles/*` does not match `handle_path /tiles/*`). v0.6 §3.6.12 row 41's
`/v1/tiles/{layer}/{z}/{x}/{y}.pbf` is wrong under SB-06's routing — errata E-2.

---

## 3. UI surfaces

### 3.1 `<gw-figure>` — where "no naked numbers" is enforced in the browser

One component renders **every** number in the product. It is the UI's single enforcement
point for R5, R6 and DIR-3, and the reason those rules do not have to be re-remembered in
twelve views.

```html
<gw-figure
  value="128340" unit="bbl" granularity="observed" basis="oil+condensate"
  vintage="2026-08-01" handle="drv_7QK3M2XR4V9B#api10=33053012340000&col=cum12_oil"
  label="cum12 oil">
</gw-figure>
```

Rendering contract:

| Input | Rendering |
|---|---|
| `value` + `unit` | Formatted per §3.9.5; the unit is **always** rendered, never implied |
| `granularity=observed` | Plain |
| `granularity=allocated` | Hatched/dashed treatment + an **"allocated"** chip + `error_lo–error_hi` shown inline or on hover; `allocation_model_id` in the drawer (DIR-3, 4F.2) |
| `granularity=modelled` | "modelled" chip + the quantile it belongs to; never rendered in the same visual style as an observation |
| `granularity=assumed` | "assumed" chip (NRI at its 0.75 default is the canonical case, v0.6 §2.2) |
| `vintage` | Rendered when the view's `as_of` differs from the figure's, or when a restatement exists — the bitemporal tell (DIR-2) |
| `handle` | The whole chip is a button; activation opens the lineage drawer (§4) |
| `label` | Passes through the glossary path (§5) so "cum12" and "GOR" are hoverable |
| **`handle` missing** | Dev build: renders a red **NAKED** badge and logs; test build: **throws**. §8.2 asserts this |

The chip is the reason S1's stranger can work: every number on screen is one activation away
from the endpoint that produced it and the file it came from, and no view author has to
remember to make that true.

**"Copy as curl"** lives on the chip's drawer panel and on every view header: it emits the
exact request, including `as_of`, that produced the data on screen. That is S1 made
mechanical rather than aspirational (v0.6 §2.4) **[I]**.

### 3.2 Well card (U1, U13, U17, U18)

```
┌ WELL 33-053-01234-00-00 ─────────────────────────── as_of 2026-08-01 ▾ ─┐
│ SPOTTED HORSE 14-23H     CONTINENTAL RESOURCES ⓘalias   ACTIVE   BAKKEN │
│ McKenzie · 150N-96W-14 · TF1 · first prod 2019-04 · lateral 9,842 ft    │
├────────────────────────────────────────────────────────────────────────┤
│ PRODUCTION  [oil][gas][water]  [log ▾] [absolute | per 1,000 ft]        │
│  ┌ chart frame: title, axis labels, legend, units — all DOM ─────────┐  │
│  │  ▓▓ canvas (uPlot) ▓▓  P10–P90 band · extrapolation break at m24  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  series handles: oil drv_…  gas drv_…  water drv_…   [copy as curl]     │
├────────────────────────────────────────────────────────────────────────┤
│ GOR / WATER CUT   (derived server-side — never computed here)          │
├────────────────────────────────────────────────────────────────────────┤
│ COMPLETION DESIGN   lateral · proppant lb/ft · fluid bbl/ft · stages    │
│                     landing zone (via formation_aliases ⓘ)             │
│                     per-field null semantics rendered, never blank      │
├────────────────────────────────────────────────────────────────────────┤
│ FORECAST (P3)  P10/P50/P90 · model chip · training_support gauge ·      │
│                calibration coverage link                                │
│ ANALOGS (P3)   ten nearest by feature distance + their ACTUALS (U17)    │
│ NEIGHBORS      offsets, projected distances in ft, completion dates     │
│ ECONOMICS (P4) NPV P10/P50/P90 together (4B.7) · breakeven · tornado    │
└────────────────────────────────────────────────────────────────────────┘
```

Decisions worth naming:

- **Three streams on one chart, with the industry colours from BRAND.md** (oil green, gas
  red, water blue **[V]**) — these are data colours, not severity colours, and the chart
  legend says so once. Streams are also distinguished by dash pattern, so colour is never
  the sole encoding (§7).
- **GOR and water cut come from `/v1/wells/{api10}/production`** (v0.6 §3.6.12 row 6
  **[V]**), never from client arithmetic. Client-computed derived series would be naked
  numbers with no handle and would violate the anti-story directly.
- **Null semantics are rendered, not blanked**: `no_report`, `reported_zero` and `withheld`
  are three different marks with three different tooltips (v0.6 §3.0.3 **[V]**). A gap in a
  production chart that could mean any of three things is a teaching failure and a
  correctness failure at once.
- **Allocated TX series (U13)** render with the allocated treatment from §3.1 plus the
  error band, plus a link to the underlying lease observation. The card states the
  allocation method and its `allocation_id` above the chart, not buried in a tooltip.
- **`as_of` is a first-class control in the card header**, and changing it changes the URL
  (§6.1). Restated months are marked; the chart refuses to mix vintages within a series
  (§3.9.3).

### 3.3 Type-curve builder (U2, E7 acceptance)

E7's acceptance is explicit: *"builder produces a curve with band and n from any filter set
via `/v1/typecurves` only"* (v0.6 §5 **[V]**). So the builder is a thin, honest client:

- **Filter panel:** basin, formation (canonical, via aliases), operator (resolved, with
  rollup mode), county / land unit, vintage window, lateral-length bucket, spacing band,
  landing zone. Each filter states the count it would select **before** you run it.
- **`min_n` guard** is a visible input with a default, and a curve below it renders the
  refusal, not a curve. "n=3 type curve" is the classic confident-nonsense output.
- **Normalization toggle** (absolute | per 1,000 ft) implements D-2's "both, selected by
  role" and states which is in force on the chart and in the export **[V]**.
- **Well-count-by-month sparkline** under the curve: this is the censoring story (4A.4) made
  visual — the reader sees the curve thin out as wells drop below the horizon.
- **Result identity is the URL.** `POST /v1/typecurves` returns a content-addressed
  `type_curve_id`; the router replaces the URL with `/typecurves/{id}` (§6.2). A shared link
  reproduces the exact curve because the id *is* the filter set (v0.6 §3.4.4 **[V]**) — no
  filter serialization in the URL, no drift.
- **Compare mode:** up to four curves overlaid, each with its n and its band; the legend
  carries each curve's id.

### 3.4 League table (U7, D-17/DIR-5)

The table that is easiest to get dishonestly wrong, so the rules are structural:

- **Headline column is `residual_cum12` per 1,000 ft** (DIR-5, D-17 **[V]**), with a
  bootstrap CI rendered as a whisker, `n_wells` adjacent, and the expectation model's
  `model_id` as a chip in the **column header** — not in a footnote.
- **Raw `cum12_per_kft` is always shown alongside**, never optional (D-17 **[V]**).
- **`rollup_mode` (as_reported | parent_rollup) is a visible control whose current value is
  printed in the table caption.** v0.6 §3.4 is explicit that neither is silently the default
  **[V]**; a UI that hides the mode in a settings menu breaks that.
- **`min_wells` filter** is visible with its default; ranking a two-well operator first is
  the failure this prevents.
- Operator name hover → alias provenance (which source keys resolved to this operator, with
  confidence and method) — the operator-identity story from v0.6 §3.4 rendered where the
  reader is actually looking.
- `residual_cum12_design_adj` is available as a mode selector, never the default (D-17).
- Every cell is a `<gw-figure>`; row click → operator view.

### 3.5 Scenario card — shell now, live at P4 (U14, S3)

Specified now so P2's layout, routing and state model do not have to change later.

Left: design inputs (lateral length, proppant intensity, fluid intensity, stage count,
landing zone, spacing) + location (map pick or land unit) + deck + assumptions selectors,
with WI/NRI marked **assumed** at their defaults (v0.6 §2.2 **[V]**).
Right: forecast with band, NPV at P10/P50/P90 **together** (4B.7 — a single NPV is never
rendered alone, enforced by the valuation view model rejecting a one-quantile payload),
tornado, analog panel, `training_support` gauge with its k and metric stated (4A.10).

S3 (< 3 s p95) is a *felt* budget: the card renders its skeleton and the echoed design
immediately, streams the forecast in when it lands, and shows elapsed time past 1.5 s. If
the request returns `202` (v0.6 §3.6.7) the card switches to the job-polling presentation
(§6.4) rather than spinning forever. `Idempotency-Key` is set on every scenario POST so a
double-click creates one scenario (v0.6 §3.6.7 **[V]**).

### 3.6 Inventory view — shell now, live at P8 (U19, 4D)

Run form (land unit, spacing assumption, model, deck, assumptions) → `202` + job → slots
layer (L11) + rollup panel. Three rendering rules are hard-wired because 4D makes them
mandatory in the UI as well as the API (v0.6 §4D.3, §4D.5 **[V]**):

1. **The spacing assumption is printed in the rollup header**, in the export header, and in
   the map legend. Not a tooltip.
2. **The support distribution is rendered as a histogram beside the rollup**, not summarized
   to a mean.
3. **The `not_a_reserves_estimate` disclaimer renders as a persistent banner** on the view
   and in every export. The view will not render a slot count without it — a UI-level check
   with a test, because R-12 is a reputational risk and reputational risks do not get
   rescued by review discipline.

`dry_run=true` is exposed as a "preview plan" button (v0.6 §3.6.9 **[V]**), which is also the
cheapest teaching surface in the product: it shows the inputs that would produce the number.

### 3.7 Auditor surfaces (U10, U12, U21, S8, S11)

The auditor persona is first-class (v0.6 §2.2 **[V]**), so these are real views, not JSON
dumps behind a dev flag.

**Quarantine** (`/quarantine`): virtualized table — source, staging table, reason code,
rule, state, detected_at. Filter chips for `reason_code`, `state`, `source`. Row expands to
the raw payload in a JSON viewer with the offending field highlighted, the `rule_id` chip
(→ conformance detail), and the lifecycle state with its history. A summary bar shows share
by reason and by basin against the per-basin trigger (2% ND / 5% Permian, v0.6 §3.0.5
**[V]**) — over-trigger renders as a stated exceedance, not a red alarm, because nothing in
this system uses red for severity (BRAND.md **[V]**).

**Scorecard** (`/scorecard`): metric tiles grouped as source coverage & freshness ·
quarantine share by basin · withheld/confidential share · model calibration coverage by
slice · allocation error bounds · conformance rule coverage, staleness and **DOCUMENTED
share** (R-10's tracked metric) · glossary coverage (S13). Every tile is a `<gw-figure>`
with its derivation, and every tile has a sparkline across `as_of` vintages, because the
movement is the story.

**Conformance browser** (`/conformance`, `/conformance/{rule_id}`): rule list filterable by
source/entity/field/kind; detail shows `rule_text`, `rationale`, **evidence URL as an
external link**, effective dates, the supersession chain, and the **"applied by" reverse
index** (SB-07 §9.4's `include=applied_by` **[V]**) — the U21 path, rendered: *"why do ND and
TX 'oil' differ"* answered by two rules and their evidence.

**Manifest view** (`/manifests/{id}`): source URL, retrieval and declared vintages,
SHA-256, byte length, parser id and version, supersedes/superseded_by, and the derivations
that consumed it. This is the terminal screen of S9 and it is styled in **amber** per
BRAND.md's "amber = raw / immutable / manifest" convention **[V]** — the reader learns the
colour means "you have reached the bottom".

**Audit stream** (`/audit`): paginated event list with the hash-chain link rendered; a
broken chain is displayed as broken. An append-only log whose UI cannot show a break is
decorative.

### 3.8 Notebook / field notes (E15, C21)

`GET /v1/notebook` and `/v1/notebook/{slug}` return markdown (v0.6 §3.6.12 row 38 **[V]**).
Rendering:

- **markdown-it with `html: false`.** Regulator prose, rule rationale and memo text are
  rendered as text, never as HTML — no XSS surface, and it matches the CSP.
- **Live data links are a token rule, not an iframe.** A link of the form
  `[label](gw:/v1/wells/33053.../production?stream=oil#/series/oil_bbl)` is transformed at
  the token level into a `<gw-figure>` that fetches its value on view. A memo written in P1
  therefore still shows the *current* number, with the *current* derivation, and states its
  `as_of` — which is exactly the "findings memos with live data links" promise (v0.6 §2.5.7
  **[V]**) rather than a screenshot that silently rots.
- **The glossary highlighter runs on the markdown token stream**, not on the rendered DOM
  (§5.3) — so terms in memo prose are hoverable without any DOM mutation.
- Memos carry tags, and the honest-gap register is a filtered view (`?tag=honest-gap`),
  which makes E16's "gaps tagged data-unreachable or effort-unreachable" a browsable
  surface instead of a document appendix.

### 3.9 The chart system

#### 3.9.1 Library decision: uPlot, plus ~200 lines of SVG

**Decision: uPlot for every time-series, decline, band and distribution chart; a small
hand-rolled SVG renderer for tornado, ranked bars and coverage tables.** This **diverges
from v0.6 §3.1's "Observable Plot / Vega-Lite"** — change-controlled, errata E-1.

Against the alternatives, on this project's actual criteria:

| Option | Weight (gz) | Verdict |
|---|---|---|
| **uPlot** | **~14 KB [A]** | **Chosen.** Canvas, built for exactly this shape of data (aligned time series), native **`bands`** support for P10–P90 fills, log scales, cheap redraws, ~4k lines of readable source. Its API is small enough to hold in your head, which is the auditability property DIR-1 is asking for |
| ECharts | ~350 KB **[A]** | Rejected: a chart framework where we need a chart. Its declarative option object is genuinely attractive (it is an inspectable spec), but §3.9.2 gets that property without the weight |
| Vega-Lite | ~250 KB+ **[A]** | Rejected: the compiler is the point of Vega-Lite, and a runtime spec compiler is exactly what `script-src 'self'` without `unsafe-eval` is least comfortable with **[A — verify]**. Also, the "spec is an artifact" argument is satisfied by §3.9.2 |
| Observable Plot | ~120 KB **[A]** (+ d3) | Rejected: excellent for exploratory work, weaker for pinned interactive surfaces with custom bands, vintage marks and per-point handles |
| d3, hand-rolled | ~30 KB (subset) | Rejected **for time series**: we would hand-write canvas rendering, hit-testing, band fills and log axes — more of our own code to audit than uPlot's entire source, and slower. **Accepted for the small categorical charts**, where d3 is not needed at all and ~200 lines of SVG is less than any dependency |

**The v0.6 property we must not lose:** §3.1 wanted declarative chart specs because *"a
chart spec can carry the derivation IDs of the series it renders"* **[V]** and §11 flags
that as a `[D]` item constraining the charting choice. §3.9.2 keeps that property exactly,
without keeping the library — the property was the point, not Vega-Lite.

#### 3.9.2 `ChartSpec` — the inspectable artifact

Every chart in the product is constructed from a JSON-serializable `ChartSpec`:

```jsonc
{
  "kind": "timeseries",
  "title": "Monthly production",
  "x": { "field": "pm", "label": "Production month", "type": "month" },
  "y": { "label": "Volume", "unit": "bbl", "scale": "log" },
  "series": [
    { "field": "oil_bbl", "label": "Oil", "unit": "bbl", "basis": "oil+condensate",
      "granularity": "observed", "handle": "drv_7QK3M2XR4V9B",
      "keyColumns": ["api10", "pm"], "colorRole": "stream.oil" }
  ],
  "bands": [ { "lo": "p10", "hi": "p90", "of": "p50", "label": "P10–P90" } ],
  "annotations": [ { "kind": "break", "at": "m24", "label": "extrapolated (Arps)" } ],
  "as_of": "2026-08-01"
}
```

Consequences, all of them load-bearing:

- **Charts are snapshot-testable as data** (§8.2) — no pixel comparison, no flake.
- **Every series carries its handle**, so §3.9.6's point-level explain works.
- **Labels are in the spec**, so the glossary CI hook can extract them from source without
  parsing a minified bundle (§5.7).
- **Units and granularity are in the spec**, so a renderer cannot draw an allocated series
  as though it were observed (§3.9.4) — the check has something to check.
- A spec renders to uPlot *or* to SVG *or* to a CSV export from one description.

#### 3.9.3 Vintage discipline in charts

The anti-story is absolute: *"no blended vintages inside one served series — a chart never
mixes an XLSX-vintage month with a PDF-vintage month"* (v0.6 §6.1 **[V]**). The renderer
enforces it:

- The series view model asserts a single `report_vintage` per series, or the chart renders
  a stated warning band instead of the series. Mixed vintages are a defect, and the UI
  reports defects rather than smoothing them.
- Points whose value changed at a later vintage than the view's `as_of` render a small
  **restated** tick; hovering shows the prior value and the vintage it came from. This is
  DIR-2's whole point made visible in the one place a reader will actually meet it, and it
  is the cheapest demonstration of F11 in the product **[I]**.

#### 3.9.4 Granularity rendering is a rule with a test

> An `allocated` or `modelled` series **may not** be drawn with the same stroke treatment as
> an `observed` series in the same chart.

Implemented as a pure function `strokeFor(granularity, streamRole)` and asserted by a unit
test that fails if any two granularities map to identical treatments (§8.2). R5 and DIR-3
say estimates never pose as observations; in a chart, "posing" means looking the same.

#### 3.9.5 Number formatting

One module, exhaustively unit-tested (§8.2): significant figures by magnitude, thousands
separators, unit suffixes rendered from the served `unit` (never inferred), ft vs m never
silently converted (v0.6 §3.0.3's unit policy **[V]**), quantile labels that state the
convention (v0.6 §9 glossary: P90 is the high case for production and the conservative case
for value — the formatter renders `P90 (high)` / `P90 (conservative)` per context so the
reader is never left to guess).

#### 3.9.6 Point-level explain without payload bloat

SB-07 §9.1 sends **one handle per series** plus a per-point `report_vintage` column, because
per-point figure objects would triple the payload and break S2/S3 **[V]**. SB-07 §1.3 defines
a selector grammar over the output's key columns **[V]**. The UI joins the two:

> Clicking a point constructs the selector **client-side** from the series' declared
> `keyColumns` and the point's own key values —
> `drv_7QK3M2XR4V9B#api10=33053012340000&pm=2024-03&col=oil_bbl` — and opens the drawer on
> that handle.

One handle on the wire, point-level explain in the UI. This is the design payoff of SB-07's
selector grammar and it should be cited in the notebook as such.

### 3.10 The table system

One headless table (`@tanstack/table-core`) + one virtualizer (`@tanstack/virtual-core`) +
one column kit, used by the league table, the viewport list, quarantine, conformance,
scorecard detail, ledger, manifests and well sets. Column kit provides: figure column
(renders `<gw-figure>`), chip column (rule/model/manifest chips), text column (glossary
path applies, §5.4), timestamp column (vintage-aware), and numeric column with unit header.

Cursor pagination (v0.6 §3.6.4) is rendered as **"load more" plus a total-known-so-far
count**, never as page numbers — cursors have no page numbers, and inventing them is how a
UI starts lying about a contract it does not control.

---

## 4. The lineage drawer (S9)

### 4.1 What it is

A right-hand drawer, ~480 px, that opens over the current view **without navigating away** —
the number that prompted the question must stay visible while its chain is read. It is
URL-addressable (`?explain=<handle>`), so a chain is shareable: paste the URL, get the same
drawer over the same view.

### 4.2 The interaction budget, spent (S9: ≤3 interactions + one `/explain`)

| Step | Action | What renders | Cost |
|---|---|---|---|
| 1 | Activate a `<gw-figure>` chip | Drawer opens; **one** `GET /v1/explain?h=…&depth=full`; the whole chain renders **including terminal manifest records with their SHA-256s** | 1 interaction, **1 explain call** |
| 2 | Activate a terminal manifest node | Full manifest record: source URL, retrieval + declared vintage, byte length, parser id/version, supersession | 1 interaction |
| 3 | *(spare)* Activate a rule chip or the recipe | Conformance rule with rationale + evidence URL, or the recipe with its determinism class | 1 interaction |

S9 is satisfied **at step 1** — the checksum is on screen after one click — and steps 2–3
are depth, not cost. This mirrors SB-07 §1.8's budget exactly **[V]**, which is the point:
the spine and the UI agree on what "three interactions" means.

### 4.3 Wireframe

```
┌ LINEAGE ─────────────────────────────────────────── [dot] [curl] [×] ─┐
│ FIGURE  oil_bbl · 12,034 bbl · observed · vintage 2026-08-01          │
│         drv_7QK3M2XR4V9B#api10=33053…&pm=2024-03&col=oil_bbl          │
│         as_of 2026-08-01 · depth 5 · terminals 2 · determinism D1     │
├───────────────────────────────────────────────────────────────────────┤
│ ● canonical.promote          canonical.production_monthly             │
│ │   "Promoted ND MPR rows to canonical at vintage 2026-08-01."        │
│ │   code git:9f2c1ab · params sha256:… · rules:                       │
│ │   [cr_nd_format_vintage] [cr_liquids_policy] [cr_month_convention]  │
│ │                                                                     │
│ ├─● stage.parse              staging.nd_mpr_xlsx                      │
│ │ │   "Parsed 2024-03 MPR workbook; 12 rows quarantined." [12 →]      │
│ │ │                                                                   │
│ │ └─◆ MANIFEST  man_9c3f…                              (amber)        │
│ │       2024_03.xlsx · 4,182,331 bytes                                │
│ │       sha256 3f9a…c21d                          [verify] [open ↗]   │
│ │       fetched 2026-08-01T05:02:11Z · declared vintage 2024-03       │
│ │       parser nd_mpr_xlsx v3 · supersedes man_71ba…                  │
│ └─● crs.transform (if present) …                                      │
├───────────────────────────────────────────────────────────────────────┤
│ RECIPE rcp_5H2K…  determinism byte_exact   [view] [replay]            │
│ MODEL  — (none for an observation)                                    │
└───────────────────────────────────────────────────────────────────────┘
```

Rendering decisions:

- **An indented rail, not a force-directed graph.** Chains are shallow (depth ≤ 8, SB-07
  §1.8 **[V]**) and narrow; a node-link canvas would be less readable, unkeyboardable, and
  a week of work. Rejected in §12.
- **Node cards render the per-node `explanation` string** from SB-07 §9.3 **[V]** as their
  first line. SB-07 ships `nodes`/`edges` *and* `explanation` precisely so the drawer does
  not have to invent prose — the UI must not generate explanatory text of its own, because
  UI-authored prose is a second implementation of the compute path and drifts from it
  (v0.6 §3.6.9's rejected option (b) **[V]**).
- **Manifest nodes are amber and terminal-marked** (BRAND.md **[V]**), with `[verify]`
  displaying the recorded SHA-256 alongside byte length so the reader can check the file
  themselves, and `[open ↗]` linking the acquisition URL.
- **Rule chips, model chips and quarantine counts are all navigable**, which is what turns
  the drawer from a receipt into the teaching surface Mandate B needs.
- **`[dot]`** exports the chain via SB-07's `format=dot` **[V]**; **`[curl]`** copies the
  exact `/v1/explain` request. Both are for the auditor who does not trust the rendering —
  which is the correct instinct and should be served, not resented.
- **Failure is rendered honestly.** SB-07's `lineage_unresolved` problem body names the last
  resolvable node and the reason (`selector_ambiguous`, `depth_exceeded`, `unknown_id`)
  **[V]**; the drawer renders that as a broken-chain card at the point of failure, never as
  a generic error toast. An auditor who gets a bare 404 has learned nothing.

### 4.4 What the drawer must never do

Compute anything, summarize a chain into prose of its own, hide a node behind "show
advanced", or open in a modal that hides the number. All four are ways of making the glass
box slightly opaque for the sake of tidiness.

---

## 5. The glossary hover system (DIR-8, E18, S13) — flagship

DIR-8's requirement, restated as acceptance: *terms are auto-highlighted in rendered text
and in chart/table labels via the glossary index, **not hand-tagged per view**; hover gives
the short definition; click gives the expanded definition, related terms and where the term
appears; the agent and the UI read the same rows* **[V]**.

### 5.1 Two paths, one component

This is the central design decision, and it is what makes the system both correct and
affordable:

| Path | Where the term binding comes from | Used for |
|---|---|---|
| **Authoritative** | **`meta.labels`** in the response envelope (v0.6 §3.6.2 **[V]**): JSON-Pointer → `glossary_term_id`, produced by the server | Every server-supplied label: field names, chart axis labels driven by the payload, table headers, enum values, error titles |
| **Discovery** | The **client-side scanner** (§5.3) over free text and client-authored strings | Notebook prose, conformance rationale, quarantine reason text, tooltips' own text, and any label authored in the UI rather than served |

The authoritative path requires **no matching at all** — the server already said which term
this label is. That is why v0.6 §3.6.2 claims "hover text and tool documentation cannot
diverge" **[V]**, and it is the path that must be preferred wherever it exists. The scanner
exists for prose and for the residue.

**Both paths converge on one custom element, `<gw-term>`, and one popover instance.** DIR-8
says "a single tooltip/popover component" and this is how that survives contact with four
different containers.

> **Blocking dependency:** SB-07 §9.1's envelope does **not** include `meta.labels`
> **[V]** — it defines `d`, `_lineage`, `_units`, `_basis`, but no label binding. The
> authoritative path is therefore unspecified until SB-00/SB-04 reconcile the two envelopes.
> Errata **E-4**. Until then SB-05 runs discovery-only, behind the `ui/src/api/` seam, and
> S13's "CI proves coverage" is provable only for the discovery path.

### 5.2 Term index: fetch, shape, cache

The scanner needs the **whole** term set at boot; a paginated collection endpoint cannot
serve that (v0.6 §3.6.4: `limit` defaults 100, max 1000 **[V]**). Errata **E-7**; requested
endpoint:

```
GET /v1/glossary/index          →  { "index_hash": "sha256:…", "as_of": "…",
                                     "terms": [
                                       { "id": "term_gor", "forms": ["GOR", "gas-oil ratio",
                                         "gas oil ratio"], "mode": "acronym_exact|phrase|word",
                                         "short": "Gas volume per barrel of oil." } ] }
```

- **Immutable and cacheable:** the response is served with an ETag over `index_hash`, and
  the client stores it in IndexedDB keyed by that hash. One fetch per glossary change.
- **`short` is inlined** so a hover never costs a request. Expanded definition, related
  terms and where-used come from `GET /v1/glossary/{term}` on click.
- **Size:** v0.6 §9 seeds ~75 terms; with per-domain vernacular, expect 200–500 rows × ~120 B
  ≈ 25–60 KB **[A]** — trivially cacheable, and the reason inlining `short` is affordable.
- **Boot order:** the index loads in parallel with the first view; text renders unhighlighted
  and is re-scanned when the index arrives. Highlighting must never block first paint.

### 5.3 The scanner: word-start greedy trie, longest match

Implementation, deliberately small enough to audit in one sitting (~150 lines):

1. **Build once**: a trie over case-folded term *forms*, tokenized into words. Terms with
   `mode: acronym_exact` are stored case-sensitively.
2. **Scan**: tokenize the input into word/non-word runs. At each **word start** only, walk
   the trie greedily across following words to a maximum of **6 words**; keep the **longest
   match**. Complexity is O(n·k) with k ≤ 6 and independent of term count — no regex
   alternation over 500 terms, no backtracking, no catastrophic input.
3. **Emit** `Segment[]` = `{text}` | `{text, termId}`. **The scanner returns data, never
   DOM.** This is the invariant that makes the whole system framework-agnostic and safe:
   nothing ever mutates rendered DOM to add highlights, so nothing fights a render cycle,
   and markdown, tables, chart frames and Lit templates all consume the same segments.

**Exclusion rules** (each has a unit test, §8.2):

| Excluded | Why |
|---|---|
| Inside a `<gw-figure>` value, or any numeric run | "P90" in a value is data, not vocabulary |
| Inside monospace/identifier context — API-10s, ids, hashes, endpoint paths, table names, code spans | `drv_…`, `33053012340000`, `/v1/typecurves` are not terms |
| Inside an existing `<gw-term>` | No nesting, no double-wrapping |
| Inside link text that is already a navigation target | Two affordances in one word is a usability defect |
| Case-sensitive for `acronym_exact` forms | `GOR` matches; "gor" inside a word does not. Same for `EUR` (vs "Europe"), `IP90`, `WI`, `NRI`, `DUC` |
| Terms flagged `highlight: never` | For rows that exist for the agent/API but are noise in prose |

**First-occurrence-per-block by default.** A page where "type curve", "band", "vintage",
"deck", "slot" and "spacing" are all underlined is unreadable, and the underlining stops
being a signal. Default: highlight the **first** occurrence per block-level container; a
**"highlight all terms"** toggle (persisted per user, announced in the glossary browser)
turns on the full set for the learner persona. This is a pedagogy decision first and a
performance decision second, and both point the same way.

### 5.4 Performance in large tables

The scanner is fast, but "fast × 50,000 cells" is still slow. Four rules:

1. **Never scan numeric or identifier columns.** The column kit (§3.10) declares which
   columns are prose; scanning is opt-in per column, and figure columns are structurally
   ineligible.
2. **Scan only visible rows.** Virtualization already limits rendering to a window; scanning
   happens in the same render pass, for the same ~40 rows.
3. **Memoize per unique string** in an LRU (`Map<string, Segment[]>`, cap 2,000). Table
   columns are highly repetitive — reason codes, statuses, formations, operators — so hit
   rates are high and the second scroll pass costs nothing.
4. **Headers always, cells rarely.** Column headers are the vocabulary surface that matters
   (`cum12`, `GOR`, `training support`, `granularity`); cell values usually are not.

**Budget:** scanning contributes **≤ 2 ms per rendered row batch** on the reference client,
asserted in a vitest benchmark against a 40-row × 12-column fixture (§8.2).

### 5.5 `<gw-term>` and the shared popover

```html
<gw-term term-id="term_gor" tabindex="0" role="button"
         aria-describedby="gw-popover">GOR</gw-term>
```

- **One popover instance for the entire document**, not one per term — mounted once, moved
  and re-populated on demand. Hundreds of popover elements is the naive implementation and
  it is a memory and a11y disaster.
- **Hover** (150 ms open delay, 300 ms close grace): term, short definition, domain tags,
  and an "expand" affordance. Delay prevents flicker when the pointer crosses text.
- **Click / Enter / Space**: expanded panel — full definition, **related terms as navigable
  chips**, **where-used** (from `/v1/glossary/{term}`), source refs, and a link to the
  glossary browser entry. This is U22 exactly **[V]**.
- **Touch**: tap = expand (there is no hover on touch); the hover tier simply does not exist
  there, which is correct rather than a degradation.
- **Positioning**: the Popover API with CSS anchor positioning where available, falling back
  to a small positioning function **[A — check Safari support at P2]**. Always flips to stay
  in the viewport; never clipped by the drawer or a table's overflow.
- **Escape** closes; focus returns to the term; the popover is `aria-live`-free (it is
  described, not announced) and referenced via `aria-describedby`.
- **The visual treatment is a dotted underline in slate, not a colour change** — the stream
  and granularity colours are already doing semantic work in charts and must not be diluted
  (BRAND.md **[V]**).

### 5.6 Chart and table labels: the canvas constraint nobody stated

**A canvas-rendered axis label cannot be hovered, focused, or read by a screen reader.**
uPlot, ECharts and every other canvas charting library draw axis titles into the bitmap.
v0.6's E18/U22 promise ("hover any unfamiliar term **anywhere** in the product") is therefore
unachievable for chart labels under any canvas chart library, and the blueprint never states
this constraint. Errata **E-8**. The pinned resolution:

> **The chart frame is DOM; only the plot area is canvas.** A `<gw-chart-frame>` element
> renders the title, y-axis label with unit, x-axis label, legend entries, granularity and
> vintage chips, and the derivation chip as **real DOM** around the canvas. uPlot draws
> series, gridlines and tick numbers; it does **not** draw titles or axis labels — those are
> disabled in its config.

This single rule makes chart labels hoverable, keyboard-reachable, screen-reader-readable,
glossary-highlightable, extractable by the CI hook, and selectable as text. It costs a
little layout work and it is the only design that satisfies E18 and §7 simultaneously.
Tick *numbers* stay on canvas — they are values, not vocabulary.

Table headers are DOM by construction, so they need no special mechanism, only §5.4's rule
that headers are always scanned.

### 5.7 The coverage CI hook (R9, S13)

v0.6 §3.6.11 specifies the check as *"every UI label extracted from the built frontend
bundle … must resolve to a `glossary_terms` row"* **[V]**. **Extraction from a minified
bundle is not mechanically possible without a source-level convention** — errata **E-10**.
SB-05 supplies the convention and the extractor:

**The convention.** Every user-visible label string is authored through one helper:

```ts
label('cum12 oil')            // returns the string; registers it at build time
label.term('term_gor')        // an explicit term binding where the text differs
```

An ESLint rule (`glasswell/no-bare-label`) fails any bare string literal in a label position
(component `label`/`title`/`aria-label` attributes, `ChartSpec` label fields, column
definitions). This is what turns "remember to add a glossary row" into a build failure.

**The extractor.** A Vite plugin collects every `label()` call site at build time and emits
`ui/dist/labels.json`: `[{ text, file, line, termIds? }]`. No parsing of minified output, no
runtime instrumentation.

**The check** (a CI job, blocking, run against a live seeded instance):

1. **Static set** — every entry in `labels.json`: scan it; every matched term must exist in
   the glossary index; every **unmatched multi-word label whose words include a domain token**
   is reported for review against `ui/glossary-allowlist.yml` (checked in, each entry
   carrying a reason — the same reviewable-exemption pattern SB-07 §10 uses for
   non-figures **[V]**).
2. **Served set** — reuse **`glasswell.lineage.ci.walk_api()`** (SB-07 §10 explicitly
   exports it so there is one walker and two assertion sets **[V]**): every value in
   `meta.labels` must resolve to a `glossary_terms` row, and every response label string
   that the scanner matches must resolve too.
3. **Index integrity** — every `related_terms[]` id resolves; no orphan terms; every term
   with `mode: acronym_exact` has at least one uppercase form.
4. **Report** — the job prints the glossary coverage percentage, which is also a scorecard
   metric (v0.6 §3.2 C18 **[V]**). S13 is then a number on a public surface, not a claim.

**The authoring loop** (DIR-8: "grows as a routine part of every feature phase"): a new
surfaced term fails the build → the developer adds a `glossary_terms` row **in the same
commit** → the index hash changes → clients refetch. This is the mechanism that makes E18
survive the phases where nobody is thinking about the glossary.

---

## 6. State, routing and reproducibility

### 6.1 The URL is the state container

Glass-box ethos applied to the client: **if it changes what a number is, it is in the URL.**

| Path | View |
|---|---|
| `/` | Map, default basin |
| `/wells/{api10}` | Well card (map keeps context in the split layout) |
| `/typecurves/new` · `/typecurves/{type_curve_id}` | Builder · a content-addressed curve |
| `/league` | Operator league table |
| `/scenarios/{scenario_id}` | Scenario card |
| `/inventory/{run_id}` | Inventory run |
| `/quarantine` · `/conformance` · `/conformance/{rule_id}` · `/scorecard` · `/ledger` | Auditor surfaces |
| `/manifests/{manifest_id}` | Manifest record |
| `/notebook` · `/notebook/{slug}` | Field notes |
| `/glossary` · `/glossary/{term_id}` | Glossary browser (a real view — the learner's home) |

| Query parameter | Meaning |
|---|---|
| `as_of` | Propagated to every request from this view (v0.6 §3.6.6 **[V]**) |
| `map=z/lat/lon[/bearing/pitch]` | Viewport, 2-decimal zoom, 5-decimal coordinates |
| `layers=l2,l5,l7` · `base=pmtiles\|none` | Layer visibility and basemap mode |
| `model` · `deck` · `assum` | Artifact selections that change served values |
| `stream` · `norm=abs\|per_kft` · `rollup=as_reported\|parent` | View-mode selections that change what a number means |
| `f.operator=` · `f.formation=` · `f.vintage=` … | Filters, flat and readable |
| `explain=<handle>` | The lineage drawer, open on that handle |
| `view=map\|list` | Map or its list equivalent (§2.6) |

**Not in the URL:** theme (localStorage), drawer scroll position, "highlight all terms"
(localStorage), transient job polling state. None of them change a number.

**History policy:** `pushState` for navigations and for filter changes; **`replaceState`,
debounced 250 ms**, for map viewport changes — a back button that replays forty pan events
is a broken back button.

### 6.2 Long state goes server-side and comes back content-addressed

A type-curve filter set can exceed a comfortable URL (which is why v0.6 §3.6.12 row 12 has a
POST **[V]**). Rather than serialize it into the URL, the builder POSTs, receives a
content-addressed `type_curve_id`, and `replaceState`s to `/typecurves/{id}`. The URL is
short, the state is exact, and the shared link is *reproducible by identity* rather than by
re-derivation. Same pattern for scenarios, inventory runs and exports.

### 6.3 Data layer

A ~200-line fetch wrapper in `ui/src/api/`: `as_of` injection, `Idempotency-Key` on POSTs,
`AbortController` per view, in-flight de-duplication by URL, an LRU response cache keyed by
`(url, as_of)`, cursor pagination helpers, and RFC 9457 problem+json → typed error mapping
(v0.6 §3.6.3 **[V]**). No data-fetching framework: the surface is small, and the cache
semantics we need (`as_of` in the key, immutability by content address) are project-specific
enough that a general library would be configured into the same thing.

### 6.4 Async jobs (202) and freshness

`202 Accepted` responses (v0.6 §3.6.7 **[V]**) switch the view into a job presentation:
progress from `GET /v1/jobs/{id}` polled with backoff (1 s → 5 s cap), a cancel action
(`DELETE`), a `role="status"` live region for screen readers, and a failure rendering that
shows the job's error rather than a toast. `meta.source_freshness` renders in the app footer
per source; when `/v1/health` reports `degraded`, a persistent (dismissible-per-session)
banner states which source is stale and how stale — the freshness contract made visible
(v0.6 §3.7.4 **[V]**).

### 6.5 Session expiry, and reproducing a view

Cloudflare Access issues a redirect to its login for browser navigations; an `XHR`/`fetch`
cannot follow that usefully **[A]**. On `401`, or on a response that is not JSON where JSON
was expected, the client shows a modal — "your session expired; reload to sign in again" —
and performs a full-page reload, which re-enters the Access flow properly. Guest sessions are
1 h (SB-06 §5.4 **[V]**), so this path is exercised routinely and must not be an afterthought.

**"Reproduce this view"** in every view header emits: the view URL, the `as_of`, and the
ordered list of curl commands (with `--header` placeholders for the guest key) that produced
every figure on screen. That is S1 turned into a button — and it is also the fastest way to
find out that a UI figure has no endpoint behind it, which the anti-story forbids.

---

## 7. Accessibility and keyboard

Not a compliance exercise: the auditor and the learner personas are both keyboard-and-text
readers, and the map is a canvas.

- **Keyboard model:** skip link → landmarks (`header`/`nav`/`main`/`complementary` for the
  drawer). Tab order follows visual order. Every `<gw-figure>` and `<gw-term>` is focusable
  and activates on Enter/Space. Drawer traps focus while open, restores it on close.
  Shortcuts: `/` search, `g` then `w|l|q|s|n` for go-to-view, `?` shortcut help, `Esc`
  closes the topmost layer. All shortcuts listed in the help overlay; none override browser
  or screen-reader keys.
- **The map:** MapLibre's built-in keyboard pan/zoom is enabled; **selection and inspection
  happen in the list view** (§2.6), which is the accessible equivalent of every map task,
  reachable by `view=list` and by a visible control (not hidden behind a media query).
- **Colour is never the sole encoding.** Streams carry dash patterns as well as colour;
  granularity carries a chip and a stroke treatment; scorecard exceedances carry text.
  Verified against BRAND.md's palette for ≥ 4.5:1 text and ≥ 3:1 graphical contrast in both
  themes **[A — run the contrast check at P2]**.
- **Themes:** dark and light from BRAND.md, defaulting to `prefers-color-scheme`, with an
  explicit toggle. Charts and map styles both switch; the stream colours have per-theme
  values already specified **[V]**.
- **Motion:** `prefers-reduced-motion` disables drawer slide, map fly-to (jump instead) and
  chart transitions.
- **Zoom/reflow:** usable at 200% browser zoom; no fixed-height text containers.
- **Live regions:** job status, async errors and "copied to clipboard" only. Nothing else
  announces.
- **Testing:** axe-core runs against every view in Playwright, plus one full keyboard-only
  traversal of the S9 path (§8.3). Violations fail CI.

---

## 8. Test strategy (DIR-10)

TDD where practical: the highlighter, formatters, URL codec, envelope parsing and chart-spec
builders are pure functions written **test-first**. The map and the drawer are covered by
component and E2E tests written alongside.

### 8.1 Tiers

| Tier | Runner | Scope |
|---|---|---|
| Unit | vitest (node) | Pure functions: scanner, formatters, URL codec, envelope/selectors, ChartSpec builders, style functions, table math |
| Component | vitest + happy-dom | Custom elements in isolation: `<gw-figure>`, `<gw-term>` + popover, chart frame, chain renderer, virtualized table |
| Contract | vitest + MSW over **checked-in real response fixtures** | View models against actual API shapes, including error and partial-failure shapes |
| E2E smoke | Playwright vs a live instance seeded with the SB-07 §10 fixture DB | The usability-critical paths (§8.3) |
| A11y | Playwright + axe-core | Every view; keyboard-only traversal of the S9 path |
| Perf | Playwright + in-page rAF sampling | S2 (§8.5), bundle budgets, scanner benchmark |

**Fixture policy (DIR-10 **[V]**):** response fixtures are **recorded from the seeded fixture
database**, never hand-authored. Hand-written fixtures encode the shape we *believe* the API
has, which is exactly the belief a contract test exists to falsify. Refresh is a make target;
a stale fixture fails the contract tier.

### 8.2 Unit tests that must exist (the named list)

**Glossary scanner** — longest match wins over overlapping forms; multi-word forms up to 6
words; word boundaries with punctuation and hyphens; `acronym_exact` case sensitivity (`GOR`
yes, "gor" in "gorge" no; `EUR` yes, "Europe" no); no match inside numbers, ids, hashes,
paths, code spans, existing `<gw-term>`; first-occurrence-per-block vs highlight-all;
`highlight: never`; empty index (renders unhighlighted, never throws); index hot-swap;
LRU memoization correctness; a **benchmark** asserting ≤ 2 ms per 40×12 row batch.

**Formatters** — significant figures by magnitude; unit rendering never inferred; ft/m never
auto-converted; quantile convention labels; null semantics (`no_report` / `reported_zero` /
`withheld`) render three distinct outputs; vintage formatting.

**Envelope / selectors** — figure-object form and `_lineage` sidecar form both parse; JSON
Pointer coverage semantics (a pointer covers descendants, v0.6 §3.6.2 **[V]**); missing
handle → naked-number error; missing unit → error; `granularity=allocated` without
`error_bounds` → error (DIR-3); mixed `report_vintage` in one series → error (§3.9.3).

**Selector construction** — point key columns → SB-07 selector string, including escaping;
ambiguous selector rejected client-side before the request.

**URL codec** — property test: `parse(serialize(state)) === state` for randomized states;
viewport rounding stability (a re-serialize must not churn history); unknown params
preserved (forward compatibility with SB-04).

**Chart** — `strokeFor(granularity)` produces distinct treatments for all four values (the
§3.9.4 rule); ChartSpec snapshots; band construction from P10/P50/P90; extrapolation break
annotation present whenever a series crosses the trained horizon (4A.9).

**Map** — layer style functions given a bundle row; the "no `derivation_id` → refuse to
render" rule (§2.7); zoom→simplification/layer-substitution thresholds; attribute-join
lookup correctness against a fixture bundle.

**`<gw-figure>`** — NAKED badge in dev, **throws in test**, on a missing handle.

### 8.3 Playwright smoke — the usability-critical paths

**Path A (the flagship, and the S9 + S13 proof in one run):**

```
load map → 20k laterals render → click a lateral → well card renders with
production chart → hover a glossary term in a chart axis label → short definition
appears → click the term → expanded panel with related terms → click a figure chip →
lineage drawer opens → assert a terminal MANIFEST node with a sha256 is visible
WITHOUT further interaction (S9) → click the manifest → full record
```

Assertions: exactly **one** `/v1/explain` request was issued for the drawer open;
the manifest node shows a 64-character hex digest; the whole path completes in ≤ 3
interactions after the well card is open.

**Path B — reproducibility:** copy the URL mid-session, open in a fresh context, assert an
identical view (viewport, selection, as_of, filters, drawer state).

**Path C — builder:** filter set → curve with band and n → URL becomes
`/typecurves/{id}` → reload → identical curve.

**Path D — auditor:** quarantine row → rule chip → conformance detail with rationale and
evidence URL → back, state preserved.

**Path E — guest scope:** with a guest principal, read paths work; a mutation path (saving
an AOI) renders a clear "not permitted for this key" state rather than a stack trace; a
`401` triggers the reload modal (§6.5).

**Path F — keyboard only:** Path A again, no pointer events, plus axe-core clean.

### 8.4 Cross-checks that catch the expensive class of bug

- **Styled value equals served value.** For a sample of API-10s, assert the value used to
  colour the lateral (from the Arrow bundle) equals the value served by
  `/v1/wells/{api10}` for the same `model_id` and `as_of`. A map that styles from a stale
  or mis-joined bundle is a wrong number that looks right — the R-11 failure class, in the
  UI.
- **Glossary coverage** (§5.7) as a blocking job.
- **Bundle budgets** (§1.4) via `size-limit`.
- **No pixel-diff visual regression** — rejected in §13; ChartSpec snapshots cover the
  intent without the flake.

### 8.5 The S2 harness

In-page: install a `requestAnimationFrame` sampler, run a scripted deterministic pan/zoom
sequence at z=9 over a 20k-lateral extent with model styling active, collect frame
intervals, report p50/p95/max and the count of frames > 100 ms. Fail on p95 > 22 ms or any
frame > 100 ms on the reference client. Also record: tile bytes transferred, tile count,
bundle bytes, and time-to-first-paint of L5. Results are appended to `ui/PERF.md` at every
phase exit, so S2 has a trend rather than a single green check.

---

## 9. Phasing and exit criteria

Mapped onto v0.6 §7.1 **[V]**. P2's exit is what proves S2, S9-first-proof and partial S13.

| Phase | SB-05 contents | Exit criteria |
|---|---|---|
| **P0** | Nothing shipped. Two decisions ratified (§11 E-1 framework/charts; §1.3 Caddy amendment) so P2 does not start on contested ground | Errata answered by SB-00 |
| **P2** | App shell, router, URL state, api seam, `<gw-figure>`, tables, map (L1–L6, L12, L13), well card, production + GOR/water-cut charts, chart frame, **lineage drawer**, **glossary system end to end**, quarantine/conformance/manifest views, notebook reader | **S2 pinned budget met and recorded in `ui/PERF.md`**; **S9 demonstrated on a production number** (Path A green); **S13 green for existing surfaces** with the coverage job blocking; every UI figure has a reproducing endpoint (Path B + "copy as curl"); axe clean; CSP enforced; bundle budgets met; all `[A]` items in this document either measured or re-tagged |
| **P3** | Forecast band, model chip, `training_support` gauge, calibration link, analog panel, **model-driven map styling (L5 continuous) + attribute bundle** | Attribute bundle measured against §2.5's ceiling; styled-value = served-value cross-check green; extrapolation break renders |
| **P4** | Scenario card live, type-curve builder live, tornado, well-set rollups | S3 felt-budget behaviour; 4B.7 enforced (no lone NPV); builder acceptance from E7 |
| **P5** | Permits, activity/DUC heatmap, AOI drawing and digests, league table, well sets, ledger view | League table renders rollup mode and expectation model in the caption; AOI digest view states its freshness window |
| **P6** | Guest-scope hardening, session-expiry path, full a11y pass, S2 re-verification, **the outsider run** | S1: a stranger with a guest key reproduces every number in the UI; S13 full; Path E green |
| **P7** | Permian layers; allocated-series rendering (U13); bundle-size ceiling re-measurement (OQ-14) | Allocated series visually distinct and error-bounded everywhere it appears |
| **P8** | Inventory view live (L11), capability-matrix and notebook presentation polish | 4D banners and support histogram mandatory-rendered; S12 (conditional) |

**Scope realism note.** v0.6 §7.2 budgets P2 at **3 weekends** for tiles, attribute bundles,
well card, drawer and glossary component **[V]**. Against §9's P2 row that is optimistic:
the glossary system alone (index, scanner, element, popover, chart-frame refactor, CI hook)
is a weekend, and the S2 tuning loop is another. Honest re-estimate: **4–5 weekends**, or
P2 splits into P2a (shell, map, well card, drawer) and P2b (glossary system, auditor
surfaces). Flagged for SB-00 rather than absorbed silently — absorbing it silently is how
the ~31-weekend figure stops being true.

---

## 10. Interfaces

| SB | SB-05 consumes | SB-05 requires / emits |
|---|---|---|
| **SB-04 API** *(not yet authored)* | Envelope (figures, units, granularity, vintage, **labels**), error model, pagination, `as_of`, `/openapi.json` | **Seven contract points to re-check when SB-04 lands:** (1) envelope form (§11 E-4); (2) `meta.labels` presence (§5.1); (3) `/v1/glossary/index` (§5.2, E-7); (4) tile and attribute paths (§2.5, §2.8, E-2); (5) guest scope on pure compute POSTs (E-11); (6) `?explain=true` and `/v1/explain` parameter names (`h` vs `ref`, E-12); (7) GOR/water-cut derived-series shape |
| **SB-07 Lineage** | Chain JSON `nodes`/`edges`/per-node `explanation`; handle + selector grammar; `lineage_unresolved`; `/quarantine`, `/conformance`, `/manifests`, `/recipes` shapes; `ci.walk_api()` | Drawer that renders `explanation` rather than authoring prose; **the glossary CI job reuses `walk_api()`**; layer/legend provenance display (§2.7) |
| **SB-06 Infra** | `/opt/glasswell/web/`, single origin, `/tiles/*` → martin, `Cache-Control` classes, security headers, Access identity | **Caddy amendment for SPA deep links** (§1.3, E-9); range-request support for the PMTiles file; **CSP content** (§1.5) to emit; immutable cache headers on `/v1/tiles/attributes` |
| **SB-01 Data** | martin layer sources with `promoteId` on `api10`; TileJSON carrying `tiles.build` `derivation_id`; PMTiles extract build | Layer inventory (§2.2) as the tile-source requirement list; simplification-by-zoom function source (§2.4.1); attribute-bundle columns (§2.5) |
| **SB-02 Modeling** | `model_id`, `training_support` (with k and metric), calibration coverage by slice, quantile series | Rendering contract: support gauge, extrapolation break, band semantics |
| **SB-03 Econ/scenarios/inventory** | Valuation with all three quantiles, tornado rows, slots with support and admissibility, spacing assumption | 4B.7 and 4D.3/4D.5 rendered as mandatory, not optional |
| **SB-00 v0.6** | — | **Ratify or reverse §11 E-1 (framework, charts)**; resolve E-2/E-4/E-6/E-7/E-11; add glossary rows for the UI vocabulary this SB introduces: *figure chip, derivation handle, attribute bundle, basemap, viewport, list view, restated, first production tick* |

---

## 11. v0.6 errata

Defects, contradictions and omissions found while specifying against
`blueprint-v0.6-draft.md`. Severity: **P1** blocks a build decision · **P2** must be fixed
before the surface ships · **P3** correctness of the document.

| # | Sev | Section | Defect | Proposed resolution |
|---|---|---|---|---|
| **E-1** | P1 | §3.1 (change-controlled) | UI row pins **React**; Charts row pins **Observable Plot / Vega-Lite**. Both are re-decided here (Lit; uPlot + SVG) with reasons in §1.2 and §3.9.1 | SB-00 ratifies the change with a written rationale per §10 change control, or reverses it. §11's `[D]` flag on "chart specs carry derivation ids" is preserved either way — §3.9.2 keeps the *property* without the library |
| **E-2** | P1 | §3.6.12 row 41 | Tile bytes are specified at `/v1/tiles/{layer}/{z}/{x}/{y}.pbf`, which routes to FastAPI under SB-06 §4.5's Caddyfile, while SB-06 §1.3 reserves `/tiles/*` for martin and **forbids** SB-04 routes there. The two documents cannot both be built | Tiles at **`/tiles/{layer}/{z}/{x}/{y}.pbf`** (Caddy → martin); attribute bundle stays at `/v1/tiles/attributes` (Caddy → uvicorn). Update row 41 |
| **E-3** | P1 | §2.4 S2 | "20k+ laterals with model-driven styling at interactive frame rates" names no frame rate, no zoom, no reference machine — untestable, while §3.7.8 makes every other budget a test | Adopt §2.4's pinned form: 20k laterals at z=9, p95 frame time ≤ 22 ms, no frame > 100 ms, reference client recorded in `ui/PERF.md` |
| **E-4** | P1 | §3.6.2 vs SB-07 §9.1 | Two incompatible envelopes: `data`/`meta.derivations`(JSON Pointer)/`meta.units`/**`meta.labels`** versus figure objects with `d` plus `_lineage`/`_units`/`_basis`. **SB-07's form omits `meta.labels` entirely**, which is the authoritative binding S13's "hover text and tool documentation cannot diverge" depends on | SB-00/SB-04 pick one envelope **and keep a label binding in it**. SB-05 codes against the `ui/src/api/` seam until then and runs discovery-only highlighting (§5.1) |
| **E-5** | P2 | §3.5 | The attribute bundle is specified as "for the current viewport's key set" — the client cannot know the key set before tiles load, and a per-viewport response has no stable cache key, so every pan re-downloads | Bundle identity is `(layer, basin, model_id, as_of)`, immutable and long-cached; bbox partitioning only above the measured ceiling (OQ-14). §2.5 |
| **E-6** | P2 | §3.6.8 / D-5 | The tile-token entitlement pattern has no component positioned to validate it under SB-06's routing, and Caddy cannot verify an HMAC natively. D-5 is unbuildable as specified | Adopt §2.8: martin serves public geometry only; principal-scoped geometry is API GeoJSON; delete or defer `POST /v1/tiles/token` with its reinstatement condition recorded |
| **E-7** | P2 | §3.6.12 row 37 | `/v1/glossary` is a paginated collection (default 100, max 1000). The highlighter needs the **whole** index in one immutable cacheable response at boot; paging it is 3–5 round trips before any text can be highlighted | Add `GET /v1/glossary/index` (or `?form=index`) — unpaginated, ETag over an `index_hash`, `short` definitions inlined. §5.2 |
| **E-8** | P2 | §5 E18 / §6 U22 | "Hover any unfamiliar term **anywhere** in the product" is unachievable for chart axis labels under any canvas charting library; the blueprint never states the constraint or its resolution | Adopt §5.6's chart-frame rule: titles, axis labels, legends and unit chips are DOM; only the plot area is canvas. Record it as an E18 acceptance clause |
| **E-9** | P2 | *(SB-06 §1.3 vs §4.5)* | SB-06 promises Caddy serves static assets from `/opt/glasswell/web/`, but its Caddyfile routes everything except `/tiles/*` to uvicorn — no SPA deep-link fallback exists, so `/wells/{api10}` 404s from FastAPI | SB-06 adopts the `handle` block in §1.3 (`try_files {path} /index.html` + cache classes) |
| **E-10** | P2 | §3.6.11 | The glossary coverage check specifies "UI labels extracted from the built frontend bundle". Extraction from minified output is not mechanically possible; the check as written cannot be implemented | R9 gains the source convention: every label authored through `label()`, extracted at build time to `labels.json`, lint-enforced. §5.7 |
| **E-11** | P2 | §3.6.8 vs §2.4 S1 | The guest scope is **read-only**, but the type-curve builder requires `POST /v1/typecurves` (row 12, "POST for filter sets too long for a URL") and the scenario loop requires `POST /v1/scenarios`. **A read-only guest therefore cannot reproduce every number in the UI**, which is exactly what S1 promises | Split POSTs into **compute POSTs** (pure per R3, content-addressed, no mutable state: typecurves, valuations, sensitivities, exports) — allowed to `guest`, rate-limited — and **mutation POSTs** (scenarios, AOIs, well sets, inventory runs) — owner/agent-write only. Without this split, S1 is unreachable |
| **E-12** | P3 | §3.6.9 vs SB-07 §9.2/§9.4 | `/v1/explain?ref=…&depth=n` versus `/explain?h=…&depth=full` — different parameter name, different depth vocabulary, and SB-07's paths carry no `/v1` prefix | SB-04 pins one spelling; SB-05 isolates it in `ui/src/api/` |
| **E-13** | P3 | §3.4.4 vs §3.6.12 row 37 | Row 37 promises the endpoint returns "where each appears", but `glossary_terms` (§3.4.3) has only `first_surfaced_in` — no where-used column or index. U22 explicitly promises "where else it appears" | Either add a `term_usages` index (term_id, surface, view/endpoint ref, first_seen) populated by the §5.7 extractor — which is nearly free once `labels.json` exists — or narrow U22's promise. The extractor route is preferred: it makes where-used a *derived* fact, not a maintained list |
| **E-14** | P3 | §7.2 P2 row | 3 weekends for tiles, attribute bundles, well card, drawer **and** the glossary component underestimates the glossary system and the S2 tuning loop | Re-estimate to 4–5 weekends or split P2a/P2b (§9) |

---

## 12. Rejected alternatives

- **React / Next.js / any SSR** — §1.2; SSR buys nothing for a map app behind an identity
  edge, and adds a server rendering path with its own auth semantics.
- **Vega-Lite / ECharts** — §3.9.1; the inspectable-spec property is preserved by §3.9.2
  at a fraction of the weight, and a runtime spec compiler sits badly with a no-`unsafe-eval`
  CSP.
- **Hand-rolled d3 time-series charts** — more of our own canvas, hit-testing and band code
  to audit than uPlot's entire source, and slower.
- **Force-directed lineage graph** — chains are shallow and narrow; a node-link canvas is
  less readable, unkeyboardable, and a week of work (§4.3).
- **DOM-mutating glossary highlighter** (walk the DOM after render, wrap matches) — the
  obvious implementation and the wrong one: it fights every render cycle, double-wraps on
  re-render, breaks text selection, and cannot see canvas labels anyway. §5.3's segment
  model replaces it.
- **Regex-alternation highlighter** — a 500-term alternation degrades unpredictably and
  makes word-boundary and acronym rules fragile; the trie is smaller to read and O(n·k).
- **Per-term popover elements** — hundreds of live popovers; one shared instance instead.
- **A third-party basemap (MapTiler/Stadia/OSM raster)** — §2.1: keys in the bundle, an
  external origin that breaks `connect-src 'self'`, and a break-glass path that dies with
  the internet.
- **Baking model attributes into tiles** — explicitly rejected by v0.6 §3.5; it would make
  every model publication a tile regeneration.
- **`setFeatureState` for 20k model-styled laterals** — §2.3; kept for interaction only.
- **A data-fetching framework (react-query et al.)** — §6.3; the cache key we need is
  project-specific (`as_of` + content addresses).
- **Component library / design system** — BRAND.md plus ~600 lines of CSS is the whole
  visual system; a component library would import a second opinion about all of it.
- **Pixel-diff visual regression** — flake tax on a solo build; ChartSpec snapshots and axe
  cover the intent (§8.4).

## 13. Cut as gold-plating

Named so they are decisions, not oversights: service worker / offline mode; i18n (the domain
vocabulary is English-only and the glossary *is* the translation layer); mobile-optimized
layouts (responsive down to tablet, no phone-specific surfaces); user preferences beyond
theme and highlight-all; in-app onboarding tour (the glossary and the notebook are the
teaching surfaces); saved UI layouts; PDF export (CSV with the provenance header block is
the export contract, v0.6 §3.6.7); real-time updates / websockets (polling is correct for
weekly-cadence data); a byte-exact frontend build (§1.4); a lineage *explorer* beyond the
drawer (SB-07 §14 already cut it); 3D / gunbarrel views (a Petro.ai surface in the E16
matrix, not a v0.6 feature).

## 14. Open items handed back

1. **E-1, E-4, E-11 are blocking** — framework/chart ratification, the envelope + `meta.labels`
   decision, and the guest-scope POST split. E-11 in particular: S1 is currently unreachable
   as specified, and it is one of the two unconditional headline criteria.
2. **SB-04 reconciliation** — the seven contract points in §10, to be walked the day SB-04
   lands.
3. **Every `[A]` in this document becomes a P2 measurement**: PMTiles extract size, bundle
   budgets, Arrow reader cost, MapLibre worker/CSP requirements, interleaved-mode frame cost,
   deck.gl WebGL2 floor, contrast audit, Popover/anchor-positioning support in Safari.
4. **OQ-14 (attribute-bundle ceiling)** gets its trigger and its fallback here (§2.5); the
   measurement itself is P7 work and belongs in `ui/PERF.md`.
5. **Reference client specification** for S2 must be recorded at P2 or E-3's fix is only
   half-applied.
6. **E-13's `term_usages` index** — decide whether where-used is derived from the label
   extractor (preferred, near-free) or U22's promise narrows.
```
