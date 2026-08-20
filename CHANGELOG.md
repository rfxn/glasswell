# Changelog

All notable changes to glasswell. Newest first.

Blueprint versions and code versions are tracked separately: `blueprint.md` carries
its own version in its header, and its history is summarised in §3.1.

## Unreleased

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
- [New] Well search in the header over the `q` filter the API has always answered:
      250 ms debounce, one request in flight, `/` focuses it, rows read name ·
      API-10 · operator · status, and a pick opens the card and flies the map to
      the well. There was previously no text input anywhere in the application
- [New] In-app key recovery: a rejected or missing owner key raises a prompt with
      a key field and a "clear stored key" button, and every 403 routes to it. A
      wrong stored key used to fail every request with devtools as the only way
      back
- [New] Header rebuilt as a control surface: brand lockup, uppercase micro-strap,
      right-hand control cluster and a width-capped meta slot, with four status
      channels that never overwrite one another — resolved vintage, persistent
      status, transient toast and key state
- [New] Centralized focus management: one MutationObserver drives focus-in,
      focus-restore and `inert` for every panel, and Escape closes the topmost
      layer — drawer, then card, then the key prompt
- [New] The stylesheet's first media queries: below 900 px the card and drawer
      become full-width bottom sheets and the controls take a 44 px tap target;
      below 620 px the lockup becomes the square mark
- [New] The bundle is gzipped on the wire (1,153,996 to 322,718 bytes) and hashed
      assets carry `Cache-Control: public, max-age=31536000, immutable`, with
      `no-cache` on the shell that names them
- [Fix] Panels are capped flex columns with a fixed head and a scrolling body, and
      the card is positioned off the drawer's actual state: it sat at `right:
      480px` whether or not the drawer was open, clipped below 940 px, and was
      entirely off-screen at 390 px, so tapping a lateral on a phone appeared to
      do nothing
- [Fix] Chart y axes carry their unit and the series on them, month ticks read
      `Oct 2025`, volumes carry thousands separators and are rounded to whole
      units; a withheld or unreported month is a gap in the line rather than the
      number the wire carried for it, and the state strip gained its key
- [Fix] Error panels link to `/v1/errors/{code}` on this deployment: `problem.type`
      is absolute at `glasswell.rpx.sh`, which does not resolve, and it was both
      the href and the link text
- [Fix] Repeated warnings collapse to one panel with a count, and the lineage
      drawer's acquisition link opens in a new tab instead of navigating the app
      away to download a 3 MB XLSX
- [Change] `web/src/bus.ts` is the seam between the map module and the rest of the
           app: selection requests in, committed selection and camera moves out

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
