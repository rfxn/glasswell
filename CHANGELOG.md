# Changelog

All notable changes to glasswell. Newest first.

Blueprint versions and code versions are tracked separately: `blueprint.md` carries
its own version in its header, and its history is summarised in §3.1.

## Unreleased

### 2026-08-20 — wave 1: the S-E production key

- [New] The S-E production key: `canonical.production_monthly` is keyed by
      `(entity_type, entity_key, production_month, stream, source_id, report_vintage)`
      with `reporting_level` alongside and `api10` kept denormalised, so a Texas lease
      row and the two pool filings one API-10 makes in a month both have somewhere to
      live (reconciliation §S-E, DR-04)
- [New] `canonical.well_completions`, the `well_completion_pool` entity the §3.4.3 enum
      named and no table defined; New Mexico reports at exactly this grain, so the gap
      blocked P7a rather than P7b (SB-01 E5)
- [New] `cr_nd_pool_rollup_1`, the legislated sum that replaces D1's interim withdrawal:
      a well that filed in two pools promotes one row per pool plus a well row carrying
      their exact sum, disclosed as `aggregation = sum_over_pools`, with days taken as
      the maximum over pools and never their sum; 78 wells and 139,644 bbl that were
      served as zeroes are served as what the regulator filed
- [New] `cr_nd_entity_key_1` and the `key_composite` executor that runs it — the last
      rule kind with no implementation apart from `code_ref`; it also unblocks NM's
      well-completion key and TX's `(OIL_GAS_CODE, DISTRICT_NO, LEASE_NO)` lease key,
      neither of which may be built by a literal in a parser (R8, DR-40)
- [New] `glasswell.ingest.repromote`, which re-promotes every staged month under the new
      key from staging rather than from the workbook, appends a vintage instead of
      rewriting one, is idempotent, and closes the `key_collision` ledger rows whose
      collision no longer exists
- [New] `GET /v1/wells/{api10}/production/pools`, the per-pool breakdown behind a summed
      well series, and `links.pools` / `links.aggregation_rule` on the well series that
      point at it and at the rule
- [New] `condensate` enters the canonical stream vocabulary and `key_incomplete` the
      quarantine reason vocabulary, both for the states that need them (C7, SB-01 §2.10)
- [Change] A well series whose months were summed across pools says so per point in
         `*_aggregation`, carries `reporting_level = well_completion_pool`, and resolves
         to an aggregation derivation taken over the pool rows — never a serve-time sum,
         which would be a figure with no derivation to cite (DIR-3, R6)
- [Change] The `production_monthly_latest` window partitions on the entity key and needs
         no tiebreak at all: the primary key holds every column the window partitions and
         orders on, so a report-vintage tie inside a partition is unrepresentable, and
         believing otherwise is what made a same-vintage re-promotion look safe (SB-01 H2)
- [Change] A canonical row's composed granularity token is checked against its
         `reporting_level` by the database, and `lease_allocated` is refused outright
         because allocation is a derived artifact and never a canonical observation
         (S-B, DIR-3)
- [Change] A promotion's `output_sha256` covers what it computed rather than the
         change-only subset it appended, so re-running one over the same bytes no longer
         trips the determinism detector with a hash that depended on prior state
- [Fix] `tests/support/seed.py` stamps the unit its stream declares instead of `bbl` on
      every row, takes `days_produced`, `null_semantics` and `value_hash`, and can seed
      any entity level; a fixture that made every gas row read `bbl` is a fixture that
      made the unit column untestable (DR-46)
- [Fix] A re-promotion at a vintage that already answers is refused rather than swallowed.
      `report_vintage` is the wall-clock day, so running the correction on the day the fleet
      was last promoted put every well aggregate on the primary key of the row it corrects;
      `on conflict do nothing` discarded them all while the collision ledger closed anyway,
      restoring the zero-producer defect with its only disclosure deleted. A repeat run that
      computes what is already recorded is still a no-op, as the derivation store's
      reconcile() is (SB-07 §1.3)
- [Fix] A well row that becomes a disclosed sum is appended even when its value did not move.
      The change key is `value_hash` plus `reporting_level` and `aggregation`; `value_hash`
      itself keeps migration 008's definition, so an unaffected well still appends nothing,
      but a well whose sibling pool contributed no volume no longer keeps an undisclosed head
      row and serves a cross-pool sum as a single-pool observation
- [Fix] A released ledger row carries `released_at_vintage`, and the withdrawal and
      withholding queries read it as of the vintage being asked for. An as-of replay of a
      date before the release disclosed nothing and answered with an affirmative regulator
      zero; it now answers what that date answered (DIR-2)
- [Fix] Collisions are superseded only for the well-months whose aggregate actually landed,
      and `RepromotionReport.rows_appended` counts rows that landed rather than rows that
      were computed
- [Fix] A no-op re-run no longer overwrites the vintage ledger row with zeroes, and two
      staged manifests for one workbook are refused up front rather than resolved by
      insertion order half-way through a run
- [Change] `entity_type` and `reporting_level` are checked against each other, so a lease row
         can no longer assert it was observed at the well. Latent today — every row is
         consistent — and load-bearing when the lease and pool writers arrive at P7a/P7b

### 2026-08-20 — wave 1: the /v1 freeze, keys and security headers

- [New] `/v1/keys` issues, lists, revokes and rotates API keys at owner, agent or
      guest scope: the cleartext is returned once and never stored, only its sha256
      reaches the table, issuance and revocation append `key.issued` / `key.revoked`
      to the audit stream, and an unknown key, a revoked key and an empty key table
      all answer identically so no caller can use the refusal as an oracle
      (SB-06 §8.3, DR-67)
- [New] Security response headers on every surface: a Content-Security-Policy that
      admits the MapLibre worker's blob URL and same-origin PMTiles range fetches and
      nothing else, plus `X-Content-Type-Options`, `X-Frame-Options: DENY`,
      `Referrer-Policy: no-referrer` and `X-Robots-Tag`; the policy was verified in a
      headless browser against the real bundle, and re-verified by removing `blob:`
      and watching the map die (SB-05 §1.5, N-6)
- [New] `/v1/vintages` and `/v1/vintages/{vintage_id}` serve the promotion records
      `as_of` resolves against, and `/v1/derivations` serves the collection the
      service index had been linking to since it was written (S-K, DR-65)
- [New] `/v1/manifests/{manifest_id}/bytes` serves the archived copy of a fetched
      artifact to the owner, or to any key when the source's terms mark it
      redistributable; a `storage_uri` that resolves outside the raw zone serves
      nothing (SB-07 §9.6)
- [New] The OpenAPI document states its own freeze terms in `info`, and a differ
      classifies any change against the committed snapshot as additive or breaking —
      a removed path, a withdrawn response guarantee or a newly required request
      field is reported as the `/v2` event §3.6.1 says it is
- [New] The auth matrix is a committed test: every served operation against
      anonymous, invalid, revoked, guest, agent and owner, with a coverage check that
      fails when an endpoint arrives without an entry
- [Remove] `/v1/explain?ref=` is refused with `parameter_removed` instead of being
      accepted and ignored, and `storage_uri` is absent from every manifest response
      below owner scope. Both are removals, so both had to happen before the S1
      freeze published the surface (S-A, S-K, DR-02, DR-33)
- [Change] `problem.type` is origin-relative, so it resolves on the LAN name, the
         tunnel name and localhost alike; the previous absolute host answered on
         only one of the three and was a dead link from the other two (N-9)

### 2026-08-20 — wave 1 merge train: the pre-train batch fix

- [Fix] The read slot stops shearing the bottom rule off the key chip and the
      degraded pill (gate-v M-1). The slot budgets a 20 px line, a 4 px gap and a
      16 px signal line; the layout came to 21 + 4 + 18, so 1.5 px fell off each end
      at 1600 and 1024 and the amber pill read as an open bracket. Two mechanisms,
      neither of them the `line-height` the finding named — that was already 16 px:
      the as_of row baseline-aligned a 10.56 px eyebrow inside a 12 px mono strut,
      and the pill's 1 px border added to an auto-height inline-block. The row is
      centred and the pill's rule is an inset ring; measured 20 + 4 + 16 = 40 px with
      zero overflow at 1600, 1024 and 390
- [Fix] The theme control ships `hidden` and the wiring unhides it when
      `VITE_GW_THEME_TOGGLE` is on (gate-v m-3). The module script is deferred, so
      the flag-off build painted an inert control for the pre-hydration window and
      then removed it

### 2026-08-20 — wave 1 fix round: the rail holds still

- [Fix] The rail's find and act groups no longer move when state changes. The read
      slot was `max-width`-capped inside a right-packed row, so every word the
      status gained shoved search and the buttons sideways — 117 px at 1600 between
      idle and a degraded source, 100 px on a rejected key, which landed on the
      first thing a new reader does. The slot is a fixed column per breakpoint now
      and the key chip moved into it, so the two groups have one position in every
      state; measured spread across all four states at 1600, 1024 and 390, both
      themes, is 0.00 px
- [Change] The theme toggle is behind `VITE_GW_THEME_TOGGLE`, off by default, until
         the map can follow the theme: `map.css` hardcodes a dark overlay surface
         while taking `color: var(--paper)`, so light rendered the legend and the
         tile-failure toast black-on-black, and the basemap has no light variant
         wired at all. The theme, its tests and `applyTheme` all stay; only the way
         in is closed, and dark is forced past a preference stored before the flag
- [Fix] The wordmark accent takes the text-safe cyan rather than the swatch cyan: at
      390 the wordmark is 18.4 px, under WCAG's large-text threshold, where the
      swatch measured 3.25:1 on light against a 4.5 floor. Now 4.82:1
- [Fix] The phone rail says "tap ⌾ for source" instead of truncating "Click any ⌾ to
      see where a number came from." to a stub that spent width to say nothing; the
      long form stays as the tooltip. The brief vocabulary lives in `chrome/status.ts`
      beside the slot it has to fit

### 2026-08-20 — wave 1: visual chrome and brand

- [New] The brand faces are self-hosted and same-origin: Inter 4.1 and JetBrains
      Mono 2.304, subset to latin as variable WOFF2 (73 KB / 20 KB) under
      `web/public/fonts/`, plus a 1 KB two-codepoint face carrying `U+233E ⌾` and
      `U+2715 ✕`, which Inter does not have. Both upstreams are SIL OFL 1.1 with no
      Reserved Font Name and both licences ship beside the files. No font CDN: a
      `gstatic` request would publish a page view past Access to an origin the
      reader never agreed to
- [New] `web/public/fonts/README.md` records the substitution the faces represent
      and parks it for owner sign-off: BRAND.md §Typography specifies `system-ui`
      and `ui-monospace` and forbids font loading, VF-4 asks the app for a loaded
      brand face, and the two are reconciled by scope — collateral keeps the
      generic stacks, the served app pins Inter and JetBrains Mono. BRAND.md is
      not edited; until sign-off it remains the contract and the README is the
      recorded divergence
- [New] A light theme built from BRAND.md's light column, with a control in the
      rail's action group; the choice persists per reader. Dark stays the default
      because the default basemap is dark. Every text colour that is also a data
      colour gained a text-safe cousin, so a sentence clears AA where the swatch
      beside it does not have to
- [New] Type tokens — `--gw-font-display`, `--gw-font-body`, `--gw-font-mono`, a
      size and weight scale, `--gw-radius-*`, a spacing scale and a seven-rung
      z-index ladder — all in `:root` and consumed everywhere; `map.css` takes the
      same tokens and declares no face of its own
- [Change] The header is a designed rail rather than an image and a control row:
         the wordmark is live text at 24 px with `well` in the accent, the lockup
         SVG that was being drawn at 32 px tall is gone, the strap is a brand
         element with a perforation-tick rule, and the right cluster is three
         labelled groups — find, act, read — on one 40 px band, hairline-separated
         (VF-1, VF-2, VF-3)
- [Change] The brand face flows through panel titles, drawer headers, the glossary
         popover, the well card's API-10, chart axis labels and the null-semantics
         key; identifiers, hashes and figures are set in the mono face with tabular
         figures, and `cv05`/`cv08` disambiguate `l`, `I` and `1` in operator names
         (VF-4)
- [Change] The production plot reads the theme's palette instead of a hard-coded
         dark grid, and repaints when the theme changes — a canvas inherits no CSS
- [Change] The chart's title moved into the card's frame, outside the element the
         plot replaces, so the placeholder and the error state keep it; it was also
         being rendered twice
- [Fix] The search results panel was anchored to the field and hung 79 px off the
      left edge of a 390 px viewport, clipping every operator name; at that width
      it now belongs to the viewport
- [Fix] Glossary terms are announced as buttons and activate on Enter and Space,
      but pointed with `cursor: help`; they now point like the control they are
- [Fix] One `:focus-visible` rule for the whole app, and a quieter dashed ring for
      the `tabindex="-1"` headings that are focus landing spots rather than controls
- [Remove] The `.gw-legend` rules, dead since the legend moved to `map.css` under
      `.gw-lg*`. `.gw-swatch` stays — the chart legend still uses it

### 2026-08-20 — wave 1: map legibility and the client's half of the tile contract

- [Fix] Every text-bearing layer and context line is coloured for the basemap under
      it rather than for the dark one it was drawn against: the spacing-unit label
      measured 2.04:1 on light and 1.58:1 on imagery (VF-5). 34 styled layers across
      the four variants and 127 measured cells, each against its WCAG floor, with
      the one sub-floor reading disclosed as a harness artifact — satellite z9, a
      cell where the label's own `minzoom: 11` means it cannot draw
- [New] The active basemap variant is published as `data-basemap` on the root and on
      the map container, so the styling pass and the stylesheet key on the same fact
      rather than each deciding it
- [New] `?legend=0` closes the legend for a screenshot or a shared link
- [Fix] A source id from `?wells=`, `?laterals=` or `?spacing=` is matched against
      `/^[a-z][a-z0-9_]{0,63}$/` before it becomes a tile path, an MVT
      `source-layer` and a `promoteId` key, and falls back on anything else; 24
      hostile values are pinned, including the traversal Track O reproduced (N-5)
- [Change] Each vector source declares the lowest zoom any of its own layers draws
         at, so the spacing source stops fetching the z0-z7 tiles nothing could
         render — the 568 KB z7 one included. The rest of the z7 cliff needs the
         PLSS-township substitute and is an owner decision, not a client one
- [New] The tile request is held to the cache contract the server now offers: the
      url is byte-identical on a repeat fetch, no `cache` or `credentials` flag is
      set, no explicit `Accept-Encoding` is sent, and the tile stays same-origin so
      the key does not turn every tile into a preflight. `maxzoom: 14` is pinned to
      `TILE_MAX_ZOOM` with the coupling named, so the two move together or not at all
- [Change] Map identifiers take `--gw-font-mono` rather than a literal stack, so the
         hover card and the layer readouts are set in the same face as identifiers
         everywhere else

### 2026-08-20 — tile serving: the zoom cost, measured and cut

- [New] The laterals function source thins its geometry in proportion to the zoom it
      is building for, four MVT units of tile extent, so the discarded detail stays
      a quarter of a rendered pixel: 12.8% fewer bytes at z7, 20.6% at z9, 28.2% at
      z11. Points and the spacing-unit polygons are left alone, where the same
      change measured as a cost with no return (SB-05 §2.4.1 pins a fixed metre
      ladder and marks it for tuning against measured tile bytes; this is the tuned
      form)
- [New] `/basemap/*` is served `public, max-age=86400` — the archive is immutable
      for the life of a vintage — with `manifest.json` held at `no-cache`, since it
      is how the client notices a swap
- [Fix] Every tile evaluated `ST_AsMVTGeom` twice per row — once for the null test,
      once for the aggregate — because the planner flattened the subquery. The
      function sources materialise it, which is 5–40% off every layer at every zoom
      measured on the live ND slice, most of it where the tiles are largest
- [Fix] The tile proxy asked martin to gzip every tile, because that is what the
      default `Accept-Encoding` of any HTTP client says. martin obliges: 140 ms of
      tile-server CPU on the hottest tile in the access log, to save 48 KB over
      zstd's 19 ms — after which the proxy decoded the result and shipped the 2 MB
      form anyway. It now asks for `zstd` when the caller can take it and
      `identity` otherwise, and passes the body through in whatever encoding martin
      chose rather than decoding it
- [Fix] Tiles carried no cache class at all, so a browser re-fetched every one:
      5,903 tile requests over 1,050 distinct tiles in 24 hours, one z7 tile 109
      times. Responses now carry martin's strong `ETag`, `Cache-Control: private,
      no-cache` and `Vary: Accept-Encoding`, and `If-None-Match` is forwarded, so a
      repeat costs martin's 0.7 ms `304` and no body; an empty `204` tile is
      cacheable on the same terms

### 2026-08-20 — Wave 1: the pre-P3 gate

- [Change] The blueprint is **v0.6-rc2**: the twenty amendments of the pre-P3 gate
         are applied, nine of them change-controlled with their rationale in the
         commit that landed them, plus G-13. Section 11 stays open — amendment 35
         is owner-gated and G-13 added a row to the table rather than removing one
- [Change] Eight constants stopped being assumptions and became measurements against
         the live ND data: `PAD_RADIUS_M` and `PAD_WINDOW_DAYS` ratified at 150 m /
         180 days with `pad_group_max_share` at 0.0008 against a 0.02 guard;
         `TC_MIN_N` at 20 with 89.3% of subjects on rung 1 and 2.5% with no control;
         the lateral-length buckets **moved** to {<8000, 8000-10000, 10000-10500,
         >10500} ft because the old cuts held 6.2% and 58.5% of wells in two of
         four; and `FORMATION_GROUP_MIN_COUNT` at 100, where nine ND groups cover
         97.15% of wells
- [New] `formation_group` becomes conformed data (G-13): a LOOKUP rule per reported
      pool, a canonical column on `canonical.well_completions`, and a feature
      registry row. The peer group, the Mondrian calibration taxonomy and the analog
      space all keyed on a column that existed in no table in the database
- [New] G-12 is answered with evidence rather than deferred: a 206 KB ranged read of
      the 321 MB ND survey archive found 5,470,017 stations carrying MD, inclination,
      azimuth and TVD, so ND keeps `landing_tvd_ft` and `structural_residual_ft`, with
      units and datum shipped as conformance rules rather than assumptions
- [New] A `modelled` figure gets a wire token. R5's composition table is complete over
      all four granularity values, 3.6.2 defines the forecast figure and a closed list
      of qualifier blocks, and the registry, calibrator and forecast DDL are reconciled
      against the tables that actually ship
- [New] P3 states its entry gate — the ND MPR back-load — instead of discovering it.
      Six production months are loaded and a cum12 label needs twelve after a rolling
      origin, so every origin measures zero test wells today
- [New] `scripts/experiments/` ships seven runnable, read-only experiments, each
      carrying its decision rule and printing a verdict, so the four provisional
      constants refresh mechanically when the back-load lands

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
