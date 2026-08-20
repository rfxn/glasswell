# Changelog

All notable changes to glasswell. Newest first.

Blueprint versions and code versions are tracked separately: `blueprint.md` carries
its own version in its header, and its history is summarised in §3.1.

## Unreleased

### 2026-08-20 — Map canvas: basemap, layers, legend, interaction

- [New] Self-hosted basemap: a Protomaps PMTiles extract served from this origin at
      `/basemap` with a manifest carrying its vintage, region, maxzoom and sha256;
      `scripts/basemap-build.sh` builds it (ND measures 48 MB at z0–13, ND+TX 336 MB) and
      `infra/basemap/README.md` is the deployer runbook
- [New] Basemap switcher with four keyless options — brand-tuned dark, a grayscale light
      variant, USGS imagery and the graticule — reachable by `?base=`, remembered through a
      guarded lookup, with a collapsed attribution pill and a banner naming any source whose
      tiles fail and what was substituted
- [New] Layer registry drives the panel, the pills, the legend, the reset and the persisted
      `{on, known}` set from one table; wells, laterals and spacing units are registered,
      and EIA play outlines and USGS assessment units are registered as stubs stating that
      no ingest recipe exists yet
- [New] Layer panel with per-layer opacity, a search filter, provenance badges, the
      epistemic subtitle in the row, the geometry `derivation_id` read back out of the tile,
      and out-of-scale rows disabled with the zoom that brings them back
- [New] Legend rows are filter controls with live counts taken from what is rendered,
      collapsed to a title pill by default, patched in place, showing an em dash rather than
      a zero for a count the viewport cannot supply
- [New] Active-layer pill strip, scale bar, rotation disabled, and a hover card that
      identifies a well from the tile's own fields without a request
- [Fix] Well status symbology matches the data: the nine classes of `cr_nd_status_vocab_1`,
      each labelled, `producing` (which matched no well) removed, dry, expired and
      temporarily_abandoned added — 12,339 of 43,817 wells that rendered as an unlabelled
      grey — a struck-through modifier for the terminal classes per the ND DMR legend, an
      unmapped class in quarantine amber, and glass cyan reserved for selection
- [Fix] Wells render from zoom 4 rather than zoom 9, so the basin is visible at the app's
      own default viewport; culling is per status rather than a blanket minzoom, so active
      wells and drilling show statewide and the terminal classes arrive at zoom 9
- [Fix] Clicks hit-test a ±6 px box through one priority-sorted dispatcher instead of one
      exact-pixel handler per layer: measured on the same 195-point grid, 6.2 per cent of
      clicks selected a well before and 42.6 per cent after, wells outrank laterals, and the
      pointer cursor and hover card follow the same query
- [Change] Selection is `promoteId` plus `feature-state` rather than a duplicate
         `*-selected` filter layer per source, and data layers are inserted beneath the
         basemap's labels so town and county names stay readable over dense wells
- [Fix] Lateral width interpolates over `lateral_length_ft` coerced to a number: martin
      serves a Postgres `numeric` as an MVT string, so the ramp silently held its base value
- [New] The assembled style is validated against the official style spec in a test. MapLibre
      drops a layer that fails validation and reports it on the `error` event, which an
      `error` listener then swallows — an invalid paint expression reads as "the well layers
      do not appear" over a clean console, which is how it shipped during this phase

### 2026-08-20 — North Dakota spine and map slice

- [New] Lineage and reproducibility spine: content-addressed raw zone with sealed
      payloads and a colocated manifest per artifact, derivation capture with a
      pinned environment, knowledge-time vintages, append-only audit stream, and
      `resolve_chain` walking any served figure to its terminal manifest
- [New] Conformance registry and quarantine ledger: every cross-source mapping is a
      registered rule with a rationale and an evidence URL, and every rejected row
      is kept with a reason code instead of being dropped
- [New] ND monthly production ingest from the free NDIC MPR path: six months
      (2025-10 through 2026-03), append-only restatements with as-of reads,
      per-stream null semantics, and key collisions quarantined rather than
      swallowed by `on conflict do nothing`
- [New] ND DMR GIS ingest: horizontal laterals, well points and spacing units into
      PostGIS, with the source datum recorded per file and the transform registered
- [New] API subset over the canonical model: wells, production, explain, manifests,
      conformance, quarantine, glossary, health and a martin tile proxy, all in one
      envelope with in-band figures, `_lineage` sidecars, RFC 9457 problems and
      cursor pagination
- [New] Serving marts and vector tiles: lateral centrelines and surface points
      published through martin under the ids the map requests
- [New] Map UI: MapLibre basin view with status-coloured laterals and no basemap,
      well card, monthly production chart, lineage drawer that reaches a SHA-256 in
      one `/v1/explain` call, and glossary hover over highlighted terms
- [New] Single-VM deployment: systemd units for the API, ingest timer and failure
      alerts, an idempotent installer, and a 27-check `verify.sh`
- [New] SMOKE.md: the first-pass walkthrough from URL to SHA-256, with the known
      gaps and the morning queue stated plainly
- [Fix] `fetch_raw` reads the run's clock instead of the wall clock, so an injected
      clock moves the manifest fetch vintage and a restatement lands on the vintage
      the run declares (B2)
- [Fix] Map style no longer declares `glyphs` as undefined: MapLibre validated the
      present-but-empty property, refused the style, and left a blank canvas with
      no layers and no tile requests
- [Fix] Tile URL templates keep MapLibre's `{z}/{x}/{y}` placeholders literal
      instead of percent-encoding them, which made every tile request 422
- [Fix] Production chart reserves room for six-figure axis labels instead of
      clipping them
- [Fix] The owner key rides in the URL fragment, never the query string: a query
      string is written to uvicorn's access log verbatim and reached journald in
      cleartext, so the API now refuses a `key` query parameter on every path and
      redacts the pattern from the access logger; the live key was rotated and the
      journal vacuumed
- [Fix] The tile proxy serves the published mart layers only; martin runs with
      `auto_publish` on, so its catalogue is every relation with a geometry column
      and the proxy's allowlist is what holds "staging never serves"
- [Fix] One length conversion in `glasswell.units`, imported by the API, the tile
      marts and the GIS load: the served figure and the tile mart disagreed at
      6731.12 against 6731.13 ft because one path rounded per lateral before
      summing and the two constants were reciprocals sharing a name; rounding is
      round-final at the serving edge and the mart stores the conversion unrounded
- [Fix] Quarantine reason vocabulary admits `stream_not_promoted` and
      `unknown_status`, and the rows whose `rule_id` proves the reason are
      relabelled: 98.7 % of the ledger read `unknown_vocab` for a deliberate
      not-promoted decision, recorded as a `quarantine.relabelled` audit event
- [Fix] All three ingest paths resolve the environment through one helper, so the
      GIS load and the mart refresh carry the lockfile hash the unit exports
      instead of stamping an unpinned `env_cli`
- [Fix] `granularity` is one vocabulary at the store and at the wire: the CHECK
      admitted a value the only sanctioned serializer refused, which would have
      been an unhandled 500 on the first lease-level row
- [Fix] The production build ships no source map; `StaticFiles` was serving 2.7 MB
      of readable proprietary TypeScript
- [Change] Frontend test fixtures are recorded from the deployed API rather than
      derived from the router source, so a response-shape drift fails a test
      instead of the first click
- [Change] README describes a repository that runs rather than one that is
      pre-build, and points at SMOKE.md

### 2026-08-19 — repository bootstrap

- [New] blueprint.md (v0.5) committed as the product and engineering contract
- [New] README.md, ARCHITECTURE.md and ROADMAP.md derived from the blueprint
- [New] Brand system: logo mark, horizontal lockups, dark and light banners, share
      card, and the palette and usage rules in BRAND.md
- [New] Architecture collateral: layer diagram, glass-box lineage chain,
      forecast-to-dollars pipeline with its control group, and the phase roadmap —
      all hand-authored SVG
- [New] Repository hygiene: proprietary license, .gitattributes export-ignore
      rules, .gitignore, contributing guide, security policy, code of conduct,
      GitHub issue and pull-request templates, and a collateral CI check
- [Change] Licensing and attribution: proprietary, all rights reserved, attributed
      directly to Ryan MacDonald. glasswell does not carry the GNU GPL v2 and the
      R-fx Networks org attribution that the rest of the rfxn workspace uses
- [New] llms.txt orientation file for agent consumers

No application code yet. P0 (scaffold) has not started — see [ROADMAP.md](ROADMAP.md).
