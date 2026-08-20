# Changelog

All notable changes to glasswell. Newest first.

Blueprint versions and code versions are tracked separately: `blueprint.md` carries
its own version in its header, and its history is summarised in §3.1.

## Unreleased

### 2026-08-20 — wave 1

- [New] `scripts/smoke.sh`: nineteen read-only assertions over a deployed instance —
      both refusals, the key refused in a query string, the card's unit and derivation
      handle, per-point production lineage, the chain that ends at a 64-hex sha256 and a
      `dmr.nd.gov` url, every conformance rule's rationale and evidence url, a tile
      derived from the well's own surface point, staging refused through the proxy, and
      every committed OpenAPI path present on the instance
- [New] `tests/e2e/`: twelve browser assertions and `make test-e2e` — the app boots and
      draws, a deep link resolves to the well it names, a handle reaches a checksum and a
      regulator url on screen, a hostile query string puts the page outside neither the
      tile allowlist nor this origin, and a visitor with no key is refused honestly. Its
      own npm project, so `playwright-core` never enters the web bundle's lockfile
- [New] `tests/integration/test_tile_wire_types.py` audits every published tile
      declaration against the relation it reads — property types, geometry type and srid
      against `geometry_columns`, and the attributes read back out of the protobuf
- [New] `make prune-test-volumes`, run by `make test`, and a labelled named volume the
      PostGIS fixture removes itself; `tests/integration/test_harness_hygiene.py` asserts
      every mount the harness attaches carries the sweep label
- [New] CI gained a shell job (`bash -n` and `shellcheck` over every tracked `.sh`) and a
      named step asserting martin's configured source list equals the tile allowlist
- [New] `install.sh` creates `/data/staging` and `/data/scratch`, SB-07 §2.3's zones under
      the volume that exists; `verify.sh` asserts all three roots, asserts the deploy root
      carries no git-excluded working file, and checks all three published layers rather
      than two
- [Fix] `ds_size_acres` was published as `numeric`, so `ST_AsMVT` put the acreage on the
      wire as the string `"640"` and a MapLibre expression compared it lexicographically —
      the defect migration 015 fixed for `lateral_length_ft`, one layer over. The same
      audit found the martin declaration still calling `nd_laterals` a `LINESTRING` after
      migration 017 widened the column
- [Fix] `create on schema marts` existed only because it was typed on the deployed host
      during P7; it is held by a migration now, with the spacing-unit view granted to the
      API role that migration 009's blanket grant could not reach
- [Fix] The pmtiles install hint and the basemap runbook told every operator to write the
      same `/tmp` path; both use `mktemp -d` now
- [Change] `infra/martin/config.yaml` is reference-only until it matches the installed
         binary: martin 1.14.0 resolves no source from it and fails before it connects,
         measured against VM 111. The same run settles the view-under-`tables:` question —
         martin resolves the spacing-unit view as `source.kind="view"` without complaint
- [Change] SMOKE.md re-read against the instance that ran migrations 014-019: the hero
         lateral is 15,065.44 ft, there are 17 conformance rules, the quarantine ledger is
         292,972 rows with `unknown_vocab` and `out_of_range_date` at zero, and "292,394
         rejected rows" is corrected — 98.7 % of the ledger is deliberate non-promotion
         and true source-row rejection is 0.79 %

### 2026-08-20 — fix cycle: data truth, guardrails, panels and map

- [New] The well card discloses what the map cannot show and the ingest held back:
      `below_tile_resolution` for laterals no zoom can render, and
      `geometry_not_promoted` for a well whose only horizontal trace is a
      sidetrack (audit A3-F5, A3-F3)
- [New] CI runs the code: a `python` job (ruff, then the full pytest suite against
      a PostGIS container the suite starts itself) and a `web` job (vitest,
      `tsc --noEmit`, production build), alongside the collateral job that was the
      only one before; `GLASSWELL_REQUIRE_DOCKER` turns a missing daemon into a
      failure, so a suite that skipped two of its three tiers can no longer report
      green
- [New] The raw zone verifies itself: `MANIFEST.sha256` is written beside the
      payload and `manifest.json` before a vintage directory is sealed, so
      `sha256sum -c` passes inside a restored directory with no arguments and no
      database (SB-06 §3.3 rule 2)
- [New] The naked-number allowlist has a minimality gate: every served figure is
      re-walked against every exemption, so a broad pattern such as `/**` fails
      the walker instead of silencing it
- [New] The naked-number walker reaches past the published examples: every handle
      a response carries is resolved to its derivation record and checked there too
- [New] `install.sh` places `glasswell-backup.{service,timer}` and the two backup
      scripts, adopted byte-for-byte from the host that was already running them;
      `--enable-backup` arms the timer, which stays disabled by default like the
      ingest timer
- [New] `verify.sh` checks the shipped Postgres tuning against the running server,
      driven by the drop-in itself so the check cannot drift from the file it
      verifies
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
- [New] Self-hosted basemap: a Protomaps PMTiles extract served from this origin
      at `/basemap` with a manifest carrying its vintage, region, maxzoom and
      sha256; `scripts/basemap-build.sh` builds it (ND measures 48 MB at z0–13,
      ND+TX 336 MB) and `infra/basemap/README.md` is the deployer runbook
- [New] Basemap switcher with four keyless options — brand-tuned dark, a grayscale
      light variant, USGS imagery and the graticule — reachable by `?base=`,
      remembered through a guarded lookup, with a collapsed attribution pill and a
      banner naming any source whose tiles fail and what was substituted
- [New] Layer registry drives the panel, the pills, the legend, the reset and the
      persisted `{on, known}` set from one table; wells, laterals and spacing units
      are registered, and EIA play outlines and USGS assessment units are
      registered as stubs stating that no ingest recipe exists yet
- [New] Layer panel with per-layer opacity, a search filter, provenance badges, the
      epistemic subtitle in the row, the geometry `derivation_id` read back out of
      the tile, and out-of-scale rows disabled with the zoom that brings them back
- [New] Legend rows are filter controls with live counts taken from what is
      rendered, collapsed to a title pill by default, patched in place, showing an
      em dash rather than a zero for a count the viewport cannot supply
- [New] Active-layer pill strip, scale bar, rotation disabled, and a hover card
      that identifies a well from the tile's own fields without a request
- [New] The assembled style is validated against the official style spec in a test.
      MapLibre drops a layer that fails validation and reports it on the `error`
      event, which an `error` listener then swallows — an invalid paint expression
      reads as "the well layers do not appear" over a clean console, which is how
      it shipped during this phase
- [Fix] A production point cites the derivation that promoted its own month.
      `sorted(derivations)[-1]` put one handle on a whole column, and ND publishes
      one workbook a month, so 327,924 of 394,278 served numbers explained to a
      regulator file that does not contain them; `_lineage` now keys a handle per
      point once a column's months disagree (audit D3)
- [Fix] The tile ships `lateral_length_ft` as a double rounded to the cent instead
      of a twenty-digit protobuf string a MapLibre expression compared
      lexicographically; the exact conversion stays in `lateral_length_ft_exact`
      (audit A3-F4)
- [Fix] A month NDIC pools as CONFIDENTIAL is quarantined as
      `confidential_withheld` instead of `out_of_range_date`, and rides the series
      axis with a null value and `withheld` semantics rather than vanishing:
      1,055 well-months, relabelled from their own payload (audit D2 / A5-F7)
- [Fix] The horizontals segment vocabulary is a rule and a reference table, not a
      literal in the loader; its 24,872 held-back rows carry
      `segment_not_promoted` and the rule that decided them instead of
      `unknown_vocab`, which claimed the ingest could not read a segment it had
      parsed itself (audit A5-F6)
- [Fix] Multi-part centrelines are stored as published rather than filed as
      `parse_error` with a NULL geometry; six real laterals were dropped by a
      staging column that declared LineString (audit A5-F8)
- [Fix] A month whose API-10 filed in more than one pool is withdrawn as
      `multi_pool_pending` with the ledger's own numbers in `meta.warnings`,
      instead of serving one pool's row as `well_observed` and `reported_zero`:
      78 wells, 454 well-months, 139,644 bbl (audit D1, interim guard)
- [Fix] `applied_rows` counts the rows a rule touched. `cr_nd_land_unit_1` was
      recorded as applied to 22,223 production rows by an executor that only
      checks three column names (audit D4)
- [Fix] `run.as_of` and the manifest `fetch_vintage` no longer diverge across UTC
      midnight: the vintage is read once when the lineage session opens, and a
      fetch stamps the day its run opened rather than the day its bytes happened
      to land
- [Fix] The pre-built `links.explain` percent-encodes the handle: a cell handle
      carries `#`, so the unencoded link sent the selector and `depth=full` as a
      URL fragment the server never received
- [Fix] The contract fixture seeds a derivation with numeric params, which the R6
      walker had never seen; `params={}` on every fixture derivation is why
      `/params/compute_epsg` shipped unexamined, and `/params/**` is now an
      exemption with a written reason
- [Fix] The published well example is a well that carries figures on a deployed
      instance, and the four content-addressed examples state in their OpenAPI
      description that they are the fixture's ids and where to obtain a live one
- [Fix] SMOKE.md gap 16 said 24,875 `unknown_vocab` rows where §5 and the database
      say 24,872
- [Fix] Panels are capped flex columns with a fixed head and a scrolling body, and
      the card is positioned off the drawer's actual state: it sat at `right:
      480px` whether or not the drawer was open, clipped below 940 px, and was
      entirely off-screen at 390 px, so tapping a lateral on a phone appeared to
      do nothing
- [Fix] Chart y axes carry their unit and the series on them, month ticks read
      `Oct 2025`, volumes carry thousands separators and are rounded to whole
      units; a withheld or unreported month is a gap in the line rather than the
      number the wire carried for it, and the state strip gained its key
- [Fix] Error panels link to `/v1/errors/{code}` on this deployment:
      `problem.type` is absolute at `glasswell.rpx.sh`, which does not resolve,
      and it was both the href and the link text
- [Fix] Repeated warnings collapse to one panel with a count, and the lineage
      drawer's acquisition link opens in a new tab instead of navigating the app
      away to download a 3 MB XLSX
- [Fix] Well status symbology matches the data: the nine classes of
      `cr_nd_status_vocab_1`, each labelled, `producing` (which matched no well)
      removed, dry, expired and temporarily_abandoned added — 12,339 of 43,817
      wells that rendered as an unlabelled grey — a struck-through modifier for the
      terminal classes per the ND DMR legend, an unmapped class in quarantine
      amber, and glass cyan reserved for selection
- [Fix] Wells render from zoom 4 rather than zoom 9, so the basin is visible at the
      app's own default viewport; culling is per status rather than a blanket
      minzoom, so active wells and drilling show statewide and the terminal classes
      arrive at zoom 9
- [Fix] Clicks hit-test a ±6 px box through one priority-sorted dispatcher instead
      of one exact-pixel handler per layer: measured on the same 195-point grid,
      6.2 per cent of clicks selected a well before and 42.6 per cent after, wells
      outrank laterals, and the pointer cursor and hover card follow the same query
- [Fix] Lateral width interpolates over `lateral_length_ft` coerced to a number:
      martin serves a Postgres `numeric` as an MVT string, so the ramp silently
      held its base value
- [Fix] The chart reads a handle per point, so a column whose months span promote
      derivations explains each point to its own month's workbook instead of
      reading `null`; the recorded web fixtures carry the percent-encoded explain
      links the API now emits
- [Fix] The pipeline role may clear a staging table, so `--restage` runs on the
      deployed database: migration 009 granted select and insert only, and the
      restage path added with migration 017 failed with `permission denied` on the
      VM while passing in a test tier whose connection owns every table
- [Change] Lateral length is measured geodesically on the WGS84 ellipsoid under
         `cr_nd_compute_crs_2`, which supersedes the UTM 14N rule rather than
         editing it. 97.6 % of ND laterals lie outside zone 14N, which overstated
         the fleet by 144,378.78 ft (+0.0709 %); the new method agrees with an
         independent pyproj geodesic to 8e-8 ft over a 100-lateral sample spanning
         the state (audit A3-F1)
- [Change] `[Change]` continuation lines indent nine spaces to the tag width, and
         the markdown variant of the rule is recorded rather than left to be
         re-derived
- [Change] infra/README.md carries a deploy runbook, including the two one-time
         steps that are still outstanding: applying the Postgres tuning, and
         dropping the `3000/tcp` LAN rule that sits in front of a loopback-only
         martin
- [Change] `web/src/bus.ts` is the seam between the map module and the rest of
         the app: selection requests in, committed selection and camera moves out
- [Change] Selection is `promoteId` plus `feature-state` rather than a duplicate
         `*-selected` filter layer per source, and data layers are inserted beneath
         the basemap's labels so town and county names stay readable over dense
         wells
- [Change] One selection bus: `map-bus.ts` is gone and the map subscribes to
         `bus.ts` itself, so the header search and the map cannot hold different
         ideas of what is selected, and a search that asks for zoom 12 gets it
         rather than the map's hardcoded floor
- [Change] The web fixtures are re-recorded from the migrated instance: the card's
         lateral length reads 15,065.44 ft where the projected rule said 15,073.98,
         the oil column carries a handle per month, and `compute_crs` reports the
         CRS the length is defined on beside the new `length_method`

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

At the close of that day there was no application code and P0 had not started — see
[ROADMAP.md](ROADMAP.md). The entries above this section are what changed since.
