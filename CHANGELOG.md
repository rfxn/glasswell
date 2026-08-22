# Changelog

All notable changes to glasswell. Newest first.

Blueprint versions and code versions are tracked separately: `blueprint.md` carries
its own version in its header, and its history is summarised in §3.1.

## Unreleased

<a id="v0.30"></a>
## v0.30 — 2026-08-22

- [New] ND disposal and injection wells as a map layer (M1-7): a teal ring over the
      status dot for wells NDIC types SWD, WI, CO2I, AI, GI, SFI, MWUI or INJP —
      1,989 of 43,824 wells; off by default, gated at z8 with the thinned tiles,
      hover states the code as filed, legend names the class and its rule
- [New] cr_nd_well_type_disposal_1: the injection-class membership as a conformance
      row served at /v1/conformance, cited by the layer instead of owned by web code;
      seeded for fresh and deployed databases alike (migration 032)
- [Change] the ND wells tile mart, view and MVT now publish well_type_reported;
         nd_gis conform pass skips code_ref policy rows the same way nd_mpr does
- [Change] layer opacity sliders can name their paint property per style layer, so
         the disposal ring's slider drives its stroke rather than a transparent fill

<a id="v0.29"></a>
## v0.29 — 2026-08-22

- [Fix] web: the header as_of chip honours a pinned route at boot — a reader
      arriving on ?as_of= sees their own pin beside the knowledge-time control
      instead of the latest published vintage, so the two claims agree on
      multi-vintage deployments; unpinned routes keep today's behaviour
      (gate-c12 R5, visual F3; approved frozen main.ts edit under CADENCE §2.2)
- [Fix] map: the layer crossing's off-state title names its true cause — an
      unticked Map view node says the toggle widened the box, and only a
      genuinely too-wide viewport blames the view's width (gate-m12 F1)
- [Fix] map: the extent row's tooltip flips with the node — in-view coverage
      while it is on, everything ingested while it is off — instead of
      asserting in-view coverage in both states (gate-m12 F2)
- [Fix] web: the vintages facet test derives its control list from the committed
      snapshot instead of a hand-written copy, so v0.27's additive explain and
      explain_depth parameters no longer redden the suite

<a id="v0.28"></a>
## v0.28 — 2026-08-22

- [Fix] canonical.production_monthly_latest re-ranked the whole table for a one-well read
      (73 s warm / 156 s cold at 17.6M rows) because api10 was not in its PARTITION BY;
      migration 031 adds it, so an api10 predicate now prunes to the index — no output
      row changes, a well's entity_key is its api10 by 020's trigger (DR-79)
- [Fix] A second same-day ND run understated the vintage ledger: repromote, monthly
      ingest and every GIS layer wrote one run's totals under an upsert keyed per
      vintage-day; counters now accumulate onto the day's row and a no-op run leaves it
      alone, the shape NM's D2 fix set (DR-78)
- [New] ND completion rows are pinned to the month grain: a guard test asserts every
      nd_mpr well_completions row carries a production_month and no effective_from
      under migration 029's two-grain CHECK (DR-80, gate-nm-p5 round-2 O1)

<a id="v0.27"></a>
## v0.27 — 2026-08-22

- [Fix] explain links: the envelope is now the only author of links.explain — a
      router-supplied link naming handles is refused, /v1/derivations/{id} and the
      vintages pair advertise their handles through the envelope's own selection, and
      router-written _lineage sidecars feed the same list `_explain` inlines, closing
      gate-apix ADV-1's two-carrier divergence before ?explain=true reached those paths
- [Fix] status-summary truncation warning now counts distinct handles the way the
      link selection counts them, so a repeated handle can no longer claim a truncation
      the link does not have
- [Fix] explain chains order root-first with the terminal manifests closing the node
      list: a root whose manifest was its first-ord input served the manifest mid-chain
      ahead of deeper derivations, so the drawer's bottom node was a derivation under a
      header counting terminal manifests (DR-83); pinned by a contract test on a chain
      that reproduces the live input ordering
- [Fix] the contract fixture's vintage now states the restatement its own seed performs,
      so the R6 walker serves a restatement count and the restatement-exemption gate
      guards data it actually meets (DR-82)
- [New] ?explain=true[&explain_depth=N] extends to every remaining figure-bearing GET:
      /v1/derivations/{id}, /v1/vintages, /v1/vintages/{id} and
      /v1/wells/{api10}/production/pools, each with annotated parameters, contract
      coverage and auth-matrix rows; the OpenAPI delta is 16 changes, all additive

<a id="v0.26"></a>
## v0.26 — 2026-08-22

- [New] map: the viewport is a named, counted filter node (MAP-ROADMAP M1-2) — the
      legend's filter list opens with a Map view row carrying the population's own
      count and derivation handle, joined to the status rows by a visible and/any-of;
      unticking it widens the counts to every ingested well with the widened
      population stated on the key and on the collapsed pill, the predicate lives in
      the URL as ?extent=0 so a shared link reconstructs the population, and the
      drawn-versus-in-view line withdraws while the node is off rather than compare
      the canvas against two basins
- [Change] map: the legend's vocabulary note names the orchid survey trace beside the
         laterals sentence that says what laterals are not (visual-m15web N2)
- [Fix] map: a selection now survives a source removed without a style swap — the
      removal pass skips a written reference whose source is gone (DR-81), pinned by
      a test that fails without the hasSource guard

<a id="v0.25"></a>
## v0.25 — 2026-08-21

- [New] map: ND directional-survey traces as a toggleable layer — the bore path ND
      filed as MD/INC/AZI/TVD stations, drawn from marts.nd_survey_traces_tile in a
      provenance colour of its own so the filed path reads apart from the GIS
      centreline; the row states its coverage (525 of 43,824 wells, 1.2%, confidential
      wells excluded at source), a trace is clickable and selectable like any well
      geometry, and its hover names station count and deepest measured depth — never
      a length

<a id="v0.24"></a>
## v0.24 — 2026-08-21

- [New] web/PERF.md records what the frontend costs, measured on the build it describes:
      entry chunk 44,192 B gzipped, the explorer route 62,817 B with the map excluded, the
      map chunk 313,823 B; budgets set from those numbers and enforced by a vitest pin that
      rebuilds rather than reading a possibly-absent dist
- [New] tests/e2e/perf.mjs drives SB-05 §8.5's frame harness over the explorer surfaces at
      ND-scale density; seven interactions, five runs each, 5,346 frames, two dropped and
      none over 100 ms
- [Fix] map: closing a well card that was opened from a deep link, or after a basemap
      change, raised an uncaught TypeError inside MapLibre's render loop and stopped it;
      the selection is now tracked as what was written to the map rather than as what the
      reader picked, and a deep-linked well is highlighted once the style's sources arrive

<a id="v0.23"></a>
## v0.23 — 2026-08-21

- [New] Map ↔ explorer crossings (SB-08 §2.6): a well card to its rows, a production chart
      to its series, a map layer to the collection behind it, the `as_of` chip to the
      vintages, and an explorer row with geometry back to the map. Every one is built by
      `stateFor`, the same router a join chip uses, so a crossing and a hop cannot drift
- [New] Both of §2.6's invariants are asserted separately: `as_of` survives every crossing,
      and each is exactly one `pushState` followed by the synthetic popstate the mode
      switch already dispatches, so one back press returns the reader to what they left
- [New] M6, applied where a link is made rather than where one is read: a crossing off a
      surface that resolved a vintage pins that vintage, so a shared link reproduces the
      numbers the sharer saw; a vintage the reader pinned themselves always wins
- [New] A crossing knows whether its own URL names a vintage, read back off the state it
      serialises rather than taken on trust, and one that names none is written as a
      statement instead of a link: no `href` to copy, no navigation, and a line saying the
      view has not resolved one yet. The map keeps the vintage its last answer resolved
      across a failing or in-flight one, so the refusal appears only where nothing has ever
      resolved — and a reader who pinned their own is never affected
- [New] `x-glasswell-dataset` destinations are declared in `bridge.ts` and checked against
      the committed OpenAPI snapshot — four of the five crossings are built on the map,
      which never fetches the document, so the declaration is proven rather than trusted
- [New] The layer registry says which served collection carries each layer, and a layer no
      collection carries states that instead of offering a link that would 404
- [New] The 820 card list and the 390 refusal (§2.5): one card per row with the column name
      beside each value, the filter bar as a sheet, and at 390 a grid that says it needs a
      wider window while the API guide renders in full — a CSS posture over the DOM the
      grid already built, so a row keeps its click, its panel and its `aria-expanded`
- [New] `work-output/pa-w1-walkthrough.md` and `pa-w1-drive.mjs`: SB-08 §5.3's walkthrough
      in the form A-6's `steps[]` will carry, driven end to end in a browser with each step
      asserted and framed. Per §9 it is a test a human runs, not a gate — the seeded-instance
      e2e job it would need is Track O's and does not exist
- [Change] C8's D1 is ruled: the grid's identifier cells carry no hop, because a chip is an
           anchor and the row's own click yields to one; the record panel keeps them. The
           geometry cell is the exception and carries the crossing, having no value to
           compete with — a coordinate is never printed
- [Fix] The explorer's stacked layout below 1024 sized the rail's row by its content while
      capping the element, so the row claimed 674 px, painted 202, and left the centre
      column zero; the row is capped instead and the rail scrolls inside it
- [Fix] `whatsBehindThisLayer` drops the viewport rather than sending a box past the four
      degrees a side `list_wells` rejects, and says the view is too wide to narrow by
- [Fix] The layer row's crossing let `display` outrank `[hidden]`, painting an arrow on
      every tile-only row above the line saying it has nowhere to cross to
- [Fix] The 820 card list labelled each value with `content: attr(data-name)`, which paints
      a name and carries it nowhere: the label was neither selectable nor exposed to
      assistive technology, and at that width the column header it would otherwise come
      from is not rendered. The label is a real element now

<a id="v0.22"></a>
## v0.22 — 2026-08-21

- [New] `?explain=true` on the figure-bearing GETs (`/v1/wells/{api10}`,
      `/v1/wells/{api10}/production`, `/v1/wells/status-summary`): the response gains
      `_explain`, one SB-07 §9.3 chain per handle it carries, keyed by handle and resolved to
      `explain_depth` levels (3 by default, 8 at most, refused over the cap); the flag adds the
      block and moves nothing else, and a response carrying more handles than one `/v1/explain`
      call accepts says how many it left out (DR-63)
- [New] `GET /v1/explain?format=dot` renders the same resolution as a Graphviz digraph —
      derivations, manifests and the conformance rules they cited as nodes, every edge labelled
      with the role the input played — served as `text/vnd.graphviz` (DR-64)
- [Change] the OpenAPI differ carries a `const` fact kind: a single-valued `Literal` renders as
         `const` rather than `enum`, so swapping one pinned value for another classified as no
         change at all; the same blind spot the `pattern` kind closed, one keyword over

<a id="v0.21"></a>
## v0.21 — 2026-08-21

- [Fix] deploy.sh waits for the api socket to answer /healthz after restart before verify.sh
      runs; the v0.20 deploy read six 000s from a socket uvicorn had not re-bound yet
- [New] ND directional-survey traces (M1-5): source `nd_gis_directionals` registered
      against OGD_Directionals.zip (3.4 MB, 52,579 stations) with the publisher's own
      disclaimer quoted verbatim; staging.nd_gis_directionals,
      canonical.well_survey_stations at station grain, and a `survey_trace` geometry in
      canonical.well_spatial keyed by API-10 the way laterals are
- [New] marts.nd_survey_traces_tile and the `nd_survey_traces` tile layer, publishing
      station_count, deepest measured depth and TVD, wellbore segment and a
      geometry_provenance column that tells a surveyed path from a GIS bore line;
      simplified like the laterals, not thinned — 586 traces statewide is not overplot
- [New] six R8 rule rows for the survey source: API-14 to API-10 on ND's own published
      rationale, the well_sub vocabulary, the ascending-measured-depth assembly with its
      tie-break, per-field physical bounds that withhold the value and keep the position,
      a two-station floor, and the unstated azimuth north reference recorded as a gap
- [New] a station whose measurement leaves its physical bound is handled the way its rule
      row says: the loader reads `field_action`, so `null_field` withholds the value and
      keeps the surveyed position while `drop_row` rejects the station, and a value the
      loader cannot honour is refused rather than quietly defaulted
- [Change] canonical.well_spatial.geom_type admits `survey_trace`; quarantine reason
           vocabulary admits `insufficient_stations`
- [Change] every survey reject records the `field_action` and `disposition` it was filed
           under, so the ledger tells six withheld values from six lost rows without
           joining back to the rule registry
- [Fix] ND GIS layer selection is declared rather than incidental: OGD_Directionals.zip
      ships two shapefiles and the loader now names the stem it reads
- [Fix] the two fold tests that read the live CHANGELOG derive their versions from its
      head instead of hardcoding v0.20; they went red the moment v0.20 shipped

<a id="v0.20"></a>
## v0.20 — 2026-08-21

- [New] GET /v1/wells/status-summary: per-status well counts for a WGS84 box, from
      canonical rather than from drawn features, so the map legend stops shrinking as the
      viewport grows (status classes are zoom-gated and the tile tier thins points, so a
      queryRenderedFeatures count fell exactly when the viewed area rose); every count is a
      figure with its own derivation handle, wells with no reported status are their own
      bucket and are never folded into a class, counts split per basin naming the vocabulary
      rule that mapped them (cr_nd_status_vocab_1, cr_tx_status_vocab_1), geometry with no
      well row at the requested vintage is disclosed as a warning rather than dropped, and
      the box is uncapped — measured at 399,280 seeded well points: 19 ms for a screen,
      237 ms for the whole of North Dakota, 1.4 s for the whole world
- [New] /v1/wells/status-summary discloses an explain-link truncation instead of an ellipsis:
      where a box produces more counts than /v1/explain accepts handles in one call,
      explain_link_truncated states exactly how many links.explain left out, and every count
      still resolves through its own handle
- [New] The rail says which build it is: `build <short sha>` under `as_of` in the top-right
      read column, injected at build time by a vite define (`dev` when there is no git to
      ask, a trailing `+` when the tree was dirty), full stamp and build date in the title
- [New] The ⌾ lesson is coached once rather than reported forever: a popover under Help that
      goes on the first lineage click, on Escape, on dismissal or on the next click
      elsewhere, and never returns; Help documents the glyph permanently
- [Change] The read column holds only the vintage and the build stamp; the status readout and
         the key chip moved to the rail's free space, so search and help start 172 px
         further right at 1600 and no control moves when a source degrades or a key fails
- [Change] Below 520 px the read column leaves the rail instead of overlapping the controls,
         and the help panel carries the vintage and the build stamp at every width
- [Fix] The 390 px rail no longer overflows its viewport: it asked for 472 px of content, and
      the browser paid by drawing help on top of search and clipping the vintage's last digit
- [Fix] NM promotion derivations record the window the run actually applied. A run
      widened with `--window-start` stamped the rule's 2015-01 default on every month,
      so a derivation for production month 1973-07 claimed a 2015-01 promotion window
      and falsified `cr_nm_wcproduction_window_1`'s served rationale verbatim
- [Fix] `lineage.vintages` counts the vintage-day rather than the last run on it.
      Canonical accumulates across same-day runs while `open_vintage` upserts on
      (source_id, vintage_date), so a DIR-12 widening performed on the day of the first
      promotion recorded 271 rows appended against the 300 that had landed
- [Fix] A refused promotion records the vintage for what the months before it committed.
      Months commit one at a time, so a run that exits 2 on a later month can leave an
      earlier month's rows appended; `rows_appended` no longer understates canonical at
      that vintage
- [Fix] The promotion's suppressed-unchanged count is measured against the canonical
      head instead of derived as kept-minus-promoted, which cancelled `promoted` out of
      SB-01 §5.1's reconciliation identity and left a promoted/suppressed mis-split
      unfalsifiable by construction
- [Fix] A filing withheld as `key_collision` or `duplicate_row` carries the cells its
      rule declares it decided on — `ogrid_cde`, `amend_ind`, `prod_amt`,
      `prodn_day_num` — so the deferred operator-effectivity resolution reads the
      quarantine ledger rather than re-staging after SB-01 §3.2's 30-day truncation
- [Fix] `cr_nm_wcproduction_collision_1` names the base each measurement was taken on:
      the 12,351 pairs with both rows producing are 12,351 of the 19,465 that disagree
      on the amount, not of the 22,591 that disagree on the amount or the day count
- [Fix] `RowCountMismatch` is exercised at both raise sites, so the staging and
      promotion reconciliation guards are shown to fire rather than asserted to exist
- [New] `canonical.well_completions` carries OGRID, pool, POD, spacing unit and property
      for every New Mexico completion: 763,473 effective-dated observations over 147,975
      completions and 121,940 wells, promoted from `wchistory` under the crosswalk
      `podwc` states, append-only and never updated
- [New] `cr_nm_wcproduction_lease_equivalent_1` records D3's Validator B grouping key as a
      rule row rather than a note. SB-01 8.6 groups NM synthetic leases on spatial
      contiguity and NM OCD's FTP ships no coordinates, so POD, spacing unit and property
      — legal areal units, which is what a TX lease actually is — stand in. The substitute
      is closer on the legal-analogue axis and strictly worse on transferability: it
      removes the resampling knob, so the rule specifies post-hoc group-selection
      reweighting and requires the residual mismatch to be published rather than claimed
      away
- [New] The wells-per-group distribution every candidate key produces, measured on the
      promoted rows: POD 141,479 groups over 83,814 completions, mean 1.445, 89.5%
      singletons; spacing unit 49,994 groups over 81,100, mean 1.622; property 52,406
      groups over all 147,975, mean 2.824. Property is the only key with full coverage and
      every key's median group holds one well, which is the ceiling on what reweighting
      can reach
- [New] The evidence for the POD fan-out is served at the granularity the join uses:
      80,663 (completion, effective date) groups in `podwc` name two to seven distinct
      PODs on one date, and the fan-out is 763,473 rows. `podwc` timestamps every row
      and the join truncates to the date, so the rule row carries the timestamp-grained
      variants beside them — 71,435 groups and 762,522 rows — rather than leaving the
      difference unstated
- [New] `cr_nm_wchistory_wellbore_policy_1` records SB-01 4.3's multi-wellbore share as
      vacuous rather than as 0%. No in-scope NM artifact carries a column past the
      api_st/api_cnty/api_well triple, so NM cannot express a sidetrack; `well_nbr_idn` is
      the operator's well number, 4,854 values over 121,940 wells, not a wellbore suffix
- [New] OGRID loads `lineage.operator_aliases` as an exact key at confidence 1.000 —
      31,696 rows, no fuzzy pass, no normalised-name fallback — and an unmatched code is
      quarantined as `alias_unresolved` with its payload rather than joined to the nearest
      name
- [New] `spc_unit_idn` '0' is the regulator's absent marker on 119,662 of 426,529 records
      and lands null; a completion that reaches none of POD, spacing unit or property is
      quarantined as `orphan_fk`, counted, never dropped
- [Change] Migration 029 gives `canonical.well_completions` a second grain. An
         effective-dated dimension observation has no production month, so
         `production_month` is nullable, the two grains are two partial unique indexes and
         a CHECK requires one of them; ND's completion-month rows and their conflict
         behaviour are untouched
- [Fix] The ND well card still index-scans with canonical 122 times larger: the served
      query filters `api10` inside the vintage window, measured at 0.9 ms against
      17,597,960 rows on VM 111. `canonical.production_monthly_latest` cannot — `api10` is
      not in its PARTITION BY — and re-ranks the whole table for one well, 2.7 s before NM
      and 73-156 s after. It is not the serving path; the finding is recorded rather than
      silently carried
- [New] The explorer's API guide pane (SB-08 §4): REQUEST, OPERATION and RESPONSE, each
      collapsible with its state in `api=`; the request block renders curl, httpie and
      fetch from the one object `requestFor` returns, so the URL a reader copies is the
      URL the grid issued — asserted at the client seam, not at fetch
- [New] Parameter semantics from A-8: WHAT from the OpenAPI description, WHY from the
      bound glossary term's expanded definition, SO from `x-glasswell-semantics`, SEE from
      the term's related terms; a parameter A-8 has not reached renders WHAT only with the
      unbound column's muted `?` and is counted in a coverage line
- [New] RESPONSE labels `data`, `meta` and `links` in place, names the `_lineage`,
      `_units` and `_basis` sidecars where the response carries them, and states an exact
      byte count on both sides of a truncation; status, timing and cache class come from
      the response itself, and the pane says so where `x-glasswell-cache` is unimplemented
- [New] Cursor pages are copyable individually, and the walk-all-pages snippet follows
      `links.next` rather than assembling a cursor
- [New] guardrails.test.ts arm 4: no domain-prose literal over 120 characters under
      `explore/`, with the vocabulary derived from the glossary terms the served document
      binds rather than from a list in the test
- [Change] The key placeholder, the curl builder and the breadcrumb's command list moved
           to `explore/api/request.ts`; `detail/chips.ts` re-exports them so the
           breadcrumb and the pane cannot drift apart
- [Fix] The stacked explorer layout at 1024-1365 gave the pane's row `auto`, so a pane
      with content took the window and left the grid a zero-height row; the row is capped
      with `fit-content(40%)` instead, because a percentage max-height cannot resolve
      against a row the item is sizing
- [Fix] Map legend: the per-class well counts are read from GET /v1/wells/status-summary for
      the viewport's box instead of counting map.queryRenderedFeatures(), so they no longer
      fall as the viewed area grows; measured over a seeded North Dakota population, the same
      box asked at two zooms returns one set of counts and no class count drops between z11
      and z5
- [New] Map legend: every count carries the derivation handle the summary served it with, so
      a class row opens the lineage drawer on the count itself rather than borrowing a drawn
      feature's geometry build; the conformance rules that classed the answer are named per
      response and link to /v1/conformance
- [New] Map legend: while a viewport's counts are in flight the rows show a wait rather than
      the previous viewport's numbers, and a summary that fails or times out shows an em dash
      on every class with the failure stated in the transient channel — never a stale or
      partial count; a late answer is matched to its viewport by request order and by the
      response's own bbox echo, so an answer for a viewport the reader has left cannot paint
- [New] Map legend: a "showing X of Y in view" line states the canvas census against the
      classes still drawn, so zoom culling and tile thinning cannot be read as the counts
      disagreeing with the dots (MAP-ROADMAP M1-1, partial half)
- [Change] The two lateral rows are one `Laterals` toggle over both style layers, off by
         default and gated at zoom 8 on the registry row and on each layer, so neither
         lateral source is fetched below it — the z7 tile measures 2,037,023 B and the tile
         tier already thins the layer to one feature per half CSS pixel at and below z7,
         which makes anything drawn there a sample of itself rather than the row's claim
- [Change] One toggle does not cost the reader the two regulators: the row carries a
         provenance line per source (ND DMR GIS · 23,228 lines, TX RRC arcs · 69,897 lines)
         naming the mart each is served from, says "bore geometry, not a directional survey
         trace" once instead of once per state, and the legend's geometry note names both.
         The panel's filter reads the sources, so "tx" still finds the row
- [Change] A row declares a list of sources and a swatch a list of colours. The laterals
         mark is green-to-grey because both layers paint from `statusColourExpression()` at
         draw time and no lateral status mix is measured in this build — a single colour
         would be a frequency claim nothing here supports, which is what the ND green and
         the TX grey each were
- [Change] `laterals` and `tx-laterals` resolve to no row rather than to the combined one.
         They named a layer that drew one state at every zoom, so a stored bit for them is
         not a preference about this one; `{on,known}` is the whole migration, and a
         returning reader gets the new default once and keeps their own answer after
- [Fix] `tx-laterals` carried no click-router priority, so a Texas lateral was unselectable
      while a North Dakota one was not — under one row that is the toggle contradicting
      itself
- [New] `make release` turns a two-digit odometer one notch and tags it: `0.20`, `0.21`, …
      `0.99`, then `1.0`, `1.01`, … `1.99`, `2.0`. There is no minor and no patch level, so
      the target takes no argument — a fix and a redesign are both one notch, because the
      changelog and not the number is where a reader finds out which it was. `MAJOR=1` jumps
      a major for a `/v2` contract event (blueprint §3.6.1) and is the only exception
- [New] `VERSION` carries the owner literal and pyproject carries the PEP 440 equivalent,
      because a release segment with a leading zero is not canonical and packaging collapses
      `1.01` to `1.1` whether or not the file says so. The mapping is injective and
      order-preserving, so the two spellings can never name different releases; the tag, the
      `## v<version>` heading, its `<a id="v...">` anchor and the header stamp are one string.
      `tests/unit/test_release_tooling.py` walks 0.99→1.0→1.01, holds `1.01` apart from
      `1.10`, and holds the pattern's four copies — Python, the page, the stamp, the vite
      define — to the same verdict on the same eighteen strings
- [New] The release refuses, naming every reason at once: a dirty tree, a topic branch, a
      `HEAD` the remote has not seen, an existing tag, nothing pending in `changelog.d`, or a
      fold the page would not render. It then folds the pending fragments and every dated
      section still under `## Unreleased` into one version section, and puts those same
      entries in the commit body and in an annotated tag. `DRY=1` prints all of it — preflight
      verdict included — and writes nothing; `make release-check` prints the same verdict and
      exits non-zero, which is what lets `make ship` stop before it builds
- [New] Nothing can tag a changelog that will not render. Every line of every fragment goes
      through the page's own parser and renderer, and the whole candidate `CHANGELOG.md` goes
      through them again, before `VERSION`, the file, the commit or the tag is touched — and
      CI runs the same check on every pull request, so a bad fragment fails at merge rather
      than at release. `make ship` orders it check → build → release → rebuild → deploy, so a
      build failure cannot strand a fresh tag and a deploy cannot carry a bundle older than
      the release it is named for
- [New] `/changelog/`: the changelog rendered to a static page in the app's own shell, with
      the palette, type ramp and font faces lifted out of `web/src/style.css` at render time
      rather than copied, and the theme read from the same `glasswell.theme` key the rail
      writes. `npm run build` renders it through a vite plugin, so CI's web job and the deploy
      runbook's frontend rebuild both produce it; behind a Make target both would have shipped
      a header stamp pointing at a 404
- [New] The page's parser is the house grammar and nothing else — four tags, indented
      continuations, anchored version headings, dated subsections, paragraphs — and it
      **refuses** a bullet in another flavour, a table, a fence, an unknown tag or an anchor
      that names a different version, naming the file and the line. One implementation, three
      callers: the fragment check, the release gate and the page itself. A changelog with a
      mistake in it stops the release instead of rendering the mistake as prose
- [Change] The rail's build stamp is a link: `v0.20+3b83fcb` pointing at
         `/changelog/#v0.20`, same-origin, still one writer, still inside the fixed read
         column. The `build` eyebrow goes when a version is present — the value names itself
         and the column is 132 px at 1024 — and stays on an unreleased build, which links to
         the page without a fragment because `#v0.0-dev` is an anchor that does not exist
- [New] `make deploy` scripts the runbook rather than describing it: `git archive HEAD` over
      ssh, `tests/` tarred separately because `.gitattributes` export-ignores it and
      `smoke.sh` reads its snapshot on the host, `web/dist` to the web root, dependencies
      only when `requirements.lock` moved, then `install.sh`, `glasswell-api` and `martin`
      restarted, `verify.sh` and `smoke.sh`. It refuses a dirty tree, an untagged `HEAD`
      unless `GW_DEPLOY_ALLOW_UNTAGGED=1`, and a `web/dist` older than `VERSION` or
      `CHANGELOG.md` — a stale bundle ships the previous release's page under this one's tag
- [New] `verify.sh` asserts the changelog page is on the host and answers 200. There is no
      SPA fallback (DR-57), so `/changelog/` resolves only because it is a real directory
      behind the existing `StaticFiles(html=True)` mount — no API and no Caddy change
- [Fix] The fold moves what was pending and rewrites nothing: `difflib` reports it as a pure
      insertion, and the moved region is asserted byte-identical and contiguous — 1,388 lines
      at the same sha256. The previous version's anchor stays with its own heading rather than
      being dragged into the new section, which a twice-folded document now proves
- [Fix] `changelog-assemble.py` accepts `[Remove]`, which `CHANGELOG.md` has used five times
      and the fragment check would have rejected on the first line of a fragment that used it
- [Fix] `release.py` refuses a `--set` outside the grammar and a `VERSION` file left at the
      pre-scheme `0.1.0` in prose rather than with a traceback, and names a modified file by
      its whole name — git's porcelain opens every line with two status columns, and stripping
      them off by eye turned `Makefile` into `akefile`
- [New] changelog.d/ per-branch changelog fragments with scripts/changelog-assemble.py and
      `make changelog TITLE=...`: tracks stop editing CHANGELOG.md (60 of the prior 200
      commits touched it) and the integrator folds fragments under a dated heading at the
      merge train; `--check` fails while fragments pend so a release cannot strand them
- [New] tests/e2e/lib.mjs: the browser-gate machinery every DIR-11 pass re-derived in
      work-output — chromium discovery, instrumented page journal, the 1600/1366/1024/820/390
      breakpoint ladder, WCAG contrast sampling, frame probe — committed and import-safe;
      smoke.mjs now shares its chromium discovery instead of carrying a copy
- [New] tests/support/serve_branch.py and `make serve-branch`: ephemeral PostGIS +
      migrations + contract-tier seeds + uvicorn for any branch (GW_ROOT points at a
      worktree, GW_SEED extends the seeds), replacing the per-track serve scripts;
      verified live — health 200, keyed wells payload, fail-closed 403, labeled teardown
- [New] `pattern` is a fact kind in `tests/contract/openapi_diff.py`, emitted per parameter
      and per schema property and through `anyOf` branches, so a relaxed identifier grammar
      is reported as the old constraint leaving rather than passing the freeze gate with no
      fact at all (UDM-SPEC §5.3 ground one, closed as a class)
- [New] Contract test pinning `API10_PATTERN` to `^\d{10}$`, that every served `{api10}`
      path declares that grammar rather than one of its own, and that a 16-character UWI is
      refused by the United States path instead of answered (UDM-SPEC §5.3, risk R-2)
- [New] Client test pinning the wells dataset's `row_id` to `["/api10"]`, with the
      counterfactual that makes the reason travel: at `["/well_id"]` every derived api10 hop
      in the explorer dies at once (UDM-SPEC §6.4, risk R-3)
- [New] Integration measurement of API-10 permanence: no well answers to two api10s and no
      api10 answers to two wells across vintages, reported with the offending api10 and the
      vintages it was seen at, and with the rows the check cannot speak for counted rather
      than hidden — §4.3(d) is an observation about ingested vintages, not a property PPDM
      certifies
- [Change] The search type guard reads the general key `(authority, native_id)` and its
           other surfaced names, so a well with no API-10 is no longer dropped silently; a
           result's `api10` is null rather than carrying a non-API-10, and the label falls
           back to the identifier the well does answer to instead of rendering `undefined`
- [Change] The explorer grid classifies `well_id`, `native_id`, `authority` and `uwi` as
           identifier columns, so the general key renders as identity rather than as prose
- [Fix] A row whose `api10` was an empty string passed the search type guard and rendered a
      blank option in the dropdown; where a second identifier kept such a row alive the empty
      string was emitted as the result's `api10`, which is neither a well nor the `null` the
      selection bus reads as deselect

### 2026-08-21 — explorer P-A + NM D1 conformance

(tracks append entries under this heading; consolidated at integration)

- [New] `make test-anvil` runs a `dbtier-preflight` target first: 24 timed `docker version`
      round-trips, refusing the suite if any fails or if more than 10% exceed 250 ms. A healthy
      window measures 59-88 ms, so a daemon that answers while its path drops packets no longer
      reaches the fixtures. An unreachable daemon costs 10 s rather than six minutes
- [New] `tests/conftest.py:pytest_exception_interact` stops a run the first time a libpq
      network error arrives from a remote daemon. The stall lands in a session-scoped fixture,
      whose exception pytest replays for every test that requests it: one stall against anvil
      measured 1063 errors and 545 passes in 6m40s. Local daemons and
      `GLASSWELL_SKIP_DBTIER_PREFLIGHT=1` are unaffected, so a real failure still reports
- [New] `tests/support/dbtier_preflight.py` holds the path verdict, the libpq-error
      classifier and the operator message; `tests/unit/test_dbtier_preflight.py` covers them,
      including that the budget is a fraction not a count and that an empty sample set fails
      rather than passes. Measurements: `work-output/anvil-dbtier-status.md`
- [New] Fourteen promotion rule rows, each naming one `source_id` because `rule_id` is a
      primary key and `load_rules` reads one source per call.
      `cr_nm_wcproduction_api10_1` pads every API segment to its own width — 2, 3 and 5 —
      because concatenating them unpadded and padding the result builds `0030520178` where
      the well is `3000520178`. A segment wider than its pad is refused rather than
      truncated: the one six-character `api_well_idn` in 48,104,334 records would otherwise
      emit an eleven-character API-10, while SQL's `lpad` truncates it onto a real well
      carrying 487 rows of its own
- [New] `cr_nm_wcproduction_entity_key_1` keys the spine at well completion × pool, the
      grain the source reports at. 48.1M rows hold 106,717 well × pool entities against
      89,136 wells, so an API-10 key collapses 17,581 of them; the source carries no
      completion suffix, which supersedes SB-01 §6.3's API-14 example
- [New] `cr_nm_wcproduction_county_parity_1` prohibits parity filtering rather than
      enumerating even-coded counties. Cibola (30-006) and Los Alamos (30-028) are LIKELY
      and not VERIFIED, and a prohibition is correct under either truth: `wellhistory`
      carries one even county code on 23 wells, so a parity predicate would look right
      against the production spine and delete Cibola the month one of them produced
- [New] `lineage.nm_stream_map` carries all four `prd_knd_cde` codes, including the `C` no
      first promotion can see — condensate is 3,398 rows and every one of them falls in
      1986-1993, so a vocabulary measured on the window would quarantine them the day it
      widened. The map is keyed on the trimmed code, which is the whole of B5
- [New] The policies the promotion reads are rows as well: units by stream with the gas
      conditions folded in as a note, the liquids policy NM's own condensate stream forces,
      the null-semantics vocabulary migration 009's CHECK admits, `amend_ind`'s ten values
      staged and promoted to nothing, the C-115 status code staged with no canonical
      mapping because the OCD publishes no codebook for it, restatement as an append, and
      NM flaring as a Property-grain fact that is not derivable at the spine's grain
- [New] `cr_nm_ogrid_operator_1` resolves the operator on OGRID at confidence 1.0 — an
      exact key rather than a name match, because a fuzzy operator match is an unlabelled
      estimate in the identity layer (SB-01 §5.3)
- [New] `x-glasswell-dataset` (SB-08 A-1) on the five collections whose `data` is already the
      array — wells, quarantine, conformance rules, derivations and glossary. The explorer's
      catalogue is generated from the served document rather than from a list in the client, so
      a dataset that is not an operation cannot appear and an operation that stops existing takes
      its dataset with it. Each declaration names its row identity, its facets, its detail
      operation and an explicit five-to-seven-pointer `columns.default`; those defaults are the
      binding ratchet's denominator, so they are a reviewable list rather than an emergent
      property of the schema-order fallback
- [New] The A-1 lint in `tests/contract/test_dataset_extension.py`, run against the served
      document and then against a mutant per rule: ids unique and never one of the four reserved
      shell routes, group one of four, every `row_id`, `columns.default`, `columns.hidden` and
      `columns.sort` pointer resolving in the operation's own response schema, every facet a real
      query parameter, every hidden column carrying its reason, and `detail_operation` /
      `summary_operation` naming operations that exist. The pivot grammar — `series_pointer`,
      `row_projection{axis,columns,suffixes}`, `anchors[]` — is checked against the production
      schemas it will be declared on, including the two rules that complete it: projection
      pointers are relative to `series_pointer`, and the axis is exempt from suffix expansion
- [New] The R6 walker asserts every browsable dataset is an operation it already exercises, so a
      generated catalogue cannot outrun the naked-number gate
- [New] `x-glasswell-dataset` on the two production operations, declared as pivots: `series_pointer`
      names the object of aligned arrays, `row_projection.axis` is the month axis every column
      aligns to, and `suffixes` expand each value column onto its report vintage and null
      semantics. Projection pointers are relative to the series, so one grammar reads `/oil_bbl` as
      `/series/oil_bbl` per well and `/pools/*/series/oil_bbl` per pool, and `anchors[]` carries the
      scalars beside the array onto every projected row so a production row states its own
      granularity. These two are the only P-A datasets that carry real figures
- [New] The remaining four declarations — Sources & freshness reading `/v1/health`'s `sources[]`
      and Problems reading the service index's `error_codes[]` through `collection_pointer`, plus
      manifests and vintages. Eleven operations now declare themselves browsable, each with an
      explicit five-to-seven-pointer `columns.default` and its own rail position
- [New] Four more lint arms, for the shapes only a served operation shows: a non-empty
      `collection_pointer` resolves to an array, a projection axis is an array because its length
      is the row count, a `series_pointer` with no `row_projection` is a half-declared pivot, and
      every required path parameter is named in `anchors[]` — `/v1/wells/{api10}/production` cannot
      be browsed until the reader supplies the well, and the rail says so instead of letting the UI
      discover a 404
- [New] `scripts/regen-snapshot.py` and `make snapshot`: the one in-tree path that rewrites the
      OpenAPI snapshot, with a `--check` arm that reports drift and writes nothing. A contract test
      runs the script and holds its output to the bytes the byte-equality gate demands, so a
      scratch renderer cannot half-repair a generated artifact
- [New] A second top-level surface at `?view=explore`: a mode switch in the header, three tabs
      (Datasets, plus Query and Learn stating the phase that lands them), a dataset catalogue
      generated from `/openapi.json`'s `x-glasswell-dataset` members, and a rail grouped
      wells / kitchen / vocabulary / service and ordered on `order` alone. The document is the
      catalogue: a dataset that stops being declared stops being listed, and a new endpoint
      appears the day its operation declares itself — with no UI release
- [New] The rail renders the honest-gap register beside what exists: twenty-one class B
      datasets, each naming the SB-04 §4 operation that would carry it and the phase where SB-08
      states one, plus the single class C entry (production across wells) naming amendment A-3
      and its status. No entry renders a link, a control or a count, and a test asserts every
      class B path is absent from the served document — the day one resolves, the entry has to
      move into the generated rail
- [New] `explore/router.ts` is the `?view=` grammar as a pure codec: `f.<param>` filters read by
      prefix and repeatable, `as_of` and `cursor` hoisted into the query rather than declared as
      facets, path anchors substituted into the path and the ones with no value named rather
      than issued as a request that 404s. The mode switch is a `pushState`, `as_of` survives the
      crossing in both directions, and a selected well crosses as `ds=wells&f.q=<api10>`
- [New] `explore/layout.css` declares named z-slots aliasing the global ladder —
      `--gw-z-explore-pane` onto `--gw-z-panel`, `--gw-z-explore-rail-pop` onto
      `--gw-z-rail-pop` — plus one local
      stacking context for the grid's sticky header. No second ladder, no numeric literal outside
      a declared `isolation: isolate` container, and the test fails if the global rungs are
      renumbered underneath the explorer
- [New] `explore/guardrails.test.ts` scans the explorer's own source in the web job that already
      exists: no `fetch(` outside the one declared exemption in `shell.ts`, no `XMLHttpRequest`,
      no absolute URL, and every operation named as a literal either served by the committed
      document or listed in the gap register as one that is not
- [New] `x-glasswell-not-a-figure` (SB-08 A-2) on all thirty-three properties
      `non_figure_allowlist.yml` exempts, carrying the exempter's reason verbatim. The register
      was a CI-only file; it is now a served surface, so the explorer can render a number with no
      derivation handle and answer "why?" in the words that granted the exemption. `api10` and
      the other identifiers are in it — they are numeric text the walker exempts and the schema
      calls strings, and they are the first exempt numbers a reader meets
- [New] `tests/contract/test_not_a_figure.py` checks the equivalence in both directions against
      the served document: a property the allowlist covers and the document does not annotate
      fails, an annotation no entry covers fails, and a reason changed in one file only fails.
      The matcher is imported from the R6 walker rather than reimplemented, so the two cannot
      drift; the population is the one R6 actually exempts, which is why `Derivation.status`
      — matched by `/status` but never a number — stays out of the register instead of
      publishing a sentence about HTTP status codes on a field that has none
- [Change] `WellDetail` redeclares `api10` and `county_code_at_permit`, and `QuarantineDetail`
         redeclares `occurrence_count`. The record and the collection item are exempted by
         different allowlist entries, and an inherited `Field` can only publish one reason
- [New] `/v1/vintages` and `/v1/vintages/{id}` carry the SB-07 §9.1b `_lineage` sidecar keyed
      on the promoting derivation (SB-08 A-4), so a vintage's `rows_examined`, `rows_appended`
      and per-reason restatement counts resolve at `/v1/explain` to that promotion and the
      manifests it read. The keys are branches of the record, not leaves — the client resolves
      by longest prefix, so a count added under `restatement_summary` tomorrow is covered by
      the entry written today. Absent, not empty, where no derivation promoted the vintage: an
      empty object contributes no prefix and would leave the numbers under it naked
- [Change] Six allowlist entries retired with it — `/rows_examined`, `/rows_appended`, their
         `/*/` twins and both `restatement_summary` globs (37 entries, was 43) —
         and `Vintage.rows_examined` and `.rows_appended` give up the A-2 extension they were
         granted three commits ago; the register is 31 properties, was 33. The sidecar and the
         prune are one commit because they must be: with the sidecar in place those patterns
         cover served figures and the allowlist's minimality gate fails on any that does.
         `/published_vintages/*/rows_examined` and its twin stay — the service index builds
         that array inline and no sidecar reaches it
- [Change] m-8 measured the R6 walker vacuous on the vintages operations: figure=0, every
         numeric leaf allowlisted. It now finds four figures there and goes red if the sidecar
         is removed, which is what makes the explorer's vintages grid a glass box rather than
         a wall of exempt numbers. `tests/contract/test_vintage_lineage.py` holds both
         directions of the coupling; the A-2 register stops demanding an exemption from every
         declared-numeric property, because a number that carries a handle is not exempt
- [New] The result grid: a windowed renderer over the page the server already capped, with the
      seven column kinds SB-08 §3.2 names. A pivot's value columns are figures by declaration and
      carry the handle their dotted `_lineage` sidecar supplies; an identifier is monospace and
      excluded from the glossary scan; an enum binds to its column's term; geometry states that
      it renders on the map rather than printing coordinates into a cell; and `null` renders its
      own `null_semantics` — `reported_zero`, `no_report`, `withheld` and `multi_pool_pending`
      each with their own mark, word and explanation — while a field the response omitted renders
      `—` and says so. No new runtime dependency: `web/package.json` is unchanged and the exit
      criterion asserts it
- [New] `<gw-count>`, the exempted number wearing its exemption: the value plus a superscript ⓔ
      whose popover quotes `x-glasswell-not-a-figure` verbatim. Where the document does not serve
      a reason yet the element renders the counted-unbound treatment and says the exemption exists
      in the allowlist and is not served — it never invents the exempter's words, and a count with
      neither a reason nor that marker throws in test mode exactly as a handle-less figure does
- [New] Column headers bind through `meta.labels` first and the schema's `x-glasswell-glossary`
      second, and where neither exists the header renders the counted-unbound treatment: a muted
      `?`, no dotted underline, no hover affordance. The per-dataset percentage renders above the
      grid, so the vocabulary debt is a product surface rather than a spreadsheet — nine of
      sixty-six default columns are bound today and the grid says so on every dataset
- [New] `explore/grid/rows.ts` turns an envelope into rows: `collection_pointer` for the two
      projections whose array sits beside `data`, `row_projection` for the two pivots, one row per
      axis entry with each suffix companion attached to its own value column, anchors repeated
      onto every row, and composite row ids read across the series and element namespaces.
      `responsePointerFor()` composes the one pointer `meta.labels` is looked up with, so the
      client and the coverage floor cannot disagree about what a column is called
- [New] The facet bar is generated from the operation's own parameters, unwrapping FastAPI's
      `anyOf: [real, null]` and refusing two non-null survivors rather than guessing: enums become
      chip groups over their own vocabulary, integers become steppers stating the server's cap,
      months validate against the pattern the server declares, and `as_of` is lifted into its own
      global strip. What a collection cannot be narrowed by is stated rather than hidden
- [New] Pagination renders as the lesson it is: the opaque cursor, a decode affordance, and each
      of the four keys annotated — including the filter fingerprint that makes a mid-walk edit a
      422 instead of a wrong answer. No page number anywhere, `links.next` followed rather than
      assembled, and an operation with no cursor parameter gets the stated fallback instead of a
      disabled cursor UI
- [Fix] The row-count line asks a summary operation for a total only when that operation declares
      every filter the grid applied. `get_quarantine_summary` takes `source_id` and `state` and
      not `stage`; FastAPI ignores an undeclared query parameter, so forwarding the grid's filters
      answered over a broader population and the line read "29 rows matched · showing 1–10" for a
      filter that matched ten. A total over a different population is a naked number wearing a
      comma
- [Fix] A report vintage shared by every value in a response is stated once above the grid
      instead of chipped onto every cell. Eighteen identical chips pushed a declared column off
      the surface at 1600 px; the chip now appears per row only when a second vintage does, which
      is the case where it means something
- [Fix] A withheld month renders its label in place of the volume rather than beside it.
      `classify_null_semantics` labels a month withheld or unreported only when the volume is
      missing, and `canonical.volume` is NOT NULL — so the ingest stores the absence as zero and
      the label is the only thing separating it from a filed zero. Rendering both put
      `0.000 bbl` beside `withheld`, which is the collapse the vocabulary exists to prevent,
      running backwards. A reported zero keeps its number, because the operator filed it
- [Fix] Grid tracks are sized per column kind: prose is the one kind that may shrink, because it
      ellipsizes without becoming a different value, and everything else holds `max-content`. A
      date cut to `2019-05-2` at the panel's edge reads as a complete date, and the grid already
      teaches `…` on prose cells. Column names ellipsize the same way and carry the full name in
      a title, and where columns still do not fit the grid says how many are off the right edge
      instead of cropping one silently
- [Fix] A figure cell is two tracks — the number and the marks beside it — so the one row
      carrying a state chip no longer pushes its value 63 px off the column's right edge, which
      is the alignment a numeric column exists to provide. Figure headers right-align onto that
      same edge: left-aligned, `water_bbl` sat three times closer to the gas column's data than
      to its own
- [Fix] The three marks a reader meets are three treatments: a served exemption is a solid amber
      ring, an unserved one is the same ring dashed, and an unbound column header keeps its muted
      pill. They were two identical `?` glyphs in one token, and the exemption mark — the only
      interactive thing in the row — was the quietest ink on it
- [Fix] The exemption mark is a ringed ASCII glyph rather than `ⓔ` (U+24D4), which none of the
      three self-hosted faces carries and which `style.css` pins GW Symbols away from, so it fell
      to the reader's system font or to tofu. A guardrail now reads the declared unicode-ranges
      off `style.css` and fails on any character the explorer renders from outside them
- [Fix] An exemption reason opens as a popover on the app's own `.gw-popover` chrome instead of
      as a block inside the cell. In flow, in a right-aligned count, it widened its own track:
      the clicked row's count moved 240 px, the last column landed 148.6 px past the panel, and
      the sentence naming off-edge columns is measured once at mount, so it could not answer for
      a state that arrives on a click. Out of the row entirely, nothing a click does can change
      the table's box, which is what makes that single measurement sound
- [Fix] The glyph guardrail reads both quote forms and template literals, over every `.ts` and
      `.css` file under `web/src` rather than one directory of it — `'ⓔ'` passed it green, and it
      covered neither of the two out-of-range characters that were already live in the product.
      `⤒` (U+2912) in the legend and `＋` (U+FF0B) on the map pills become `↑` and `+`: rendered
      under the app's own font stack, both drew at exactly the width they draw at with the brand
      faces removed, so no shipped face was supplying them
- [Change] Whole volumes drop an all-zero fraction: `1,000.000 bbl` beside a comma thousands
           separator invites a 1000x misread, and the served string stays on the element. Nothing
           is rounded — a fraction with any non-zero digit is untouched
- [Change] A column the schema binds to a glossary term and types as a bare string renders as
           vocabulary, so `granularity` carries its definition on the value and not only on the
           header — §3.2 names it among the vocabulary columns and no parameter is called that
- [Remove] The anchor prompt's duplicate sentence in the dataset header, and the coverage line
           above an empty result. One named the anchor twice 110 px apart; the other counted
           headers that were not on screen
- [New] `x-glasswell-semantics` (SB-08 A-8) on nine operations, 47 parameters: what each one
      does to *this* request, in a sentence written per operation. `as_of` on `/v1/wells`
      resolves a spine snapshot while `as_of` on a well's production selects the vintage of
      every point in the series, and the two say so separately — a shared glossary row could
      not carry either, which is the modelling reason the extension exists. The inner binding
      is named `x-glasswell-glossary`, so the R9 referential check picks these up by
      construction: a term id that does not exist turns `test_every_schema_binding_resolves`
      red with no edit to that test
- [New] The A-8 lint: every annotated key is a real parameter of the operation it sits on,
      every entry binds a term or states a consequence, every annotated parameter carries the
      description the pane reads WHAT from, and the pre-rev-3 spelling `glossary` is refused
      rather than silently uncollected. `so` is prose and stays reviewed, not machine-checked
- [New] Eleven glossary terms — pool, production month, source, pipeline stage, rule kind,
      quarantine state, well name, well status, operator of record, county at permit and spud
      date — each written for a reader who knows software and not this domain, and each
      answering the question the column raises: why a county code is a permit fact, why an
      operator name counts filings rather than companies, why a production month with two
      values has no wrong one
- [New] O-6's first authoring tranche binds 36 of 66 declared default columns — 55 %, against
      SB-08 §3.2's 40 % floor for this phase — with `production`, `production_pools` and
      `wells` bound end to end. `test_default_column_binding_meets_the_phase_floor` derives
      both terms at run time, composes its lookup pointer with the rule the grid composes its
      own with, prints the per-dataset table, and carries a vacuity guard so a future edit
      that deletes `columns.default` cannot report 100 % over six columns
- [Change] The pooled production response labels each pool at the index it is served at —
         `/pools/0/series/oil_bbl`, `/pools/1/…` — rather than at a `/pools/*/…` key. The
         client resolves labels by exact pointer match with no glob and no prefix walk, so the
         wildcard form bound nothing; the loop is bounded by the pools a well filed in
- [Fix] `SourceHealth.retrieval_vintage` and `.declared_vintage` declare `format: date`. They
      were bare strings, so the explorer classified two dates as prose where every other date
      on the surface is typed
- [Fix] `/v1/glossary`'s served-term count and `QuarantineRow.state`'s label are both derived
      rather than written down: the count reads the seed, and the label follows the schema
      binding instead of pointing at the general quarantine term
- [New] Row detail: expanding a row calls the dataset's `detail_operation` and renders the fuller
      record it exists for — `get_quarantine_row` adds `row_payload` and the first and last-seen
      manifests the collection never carries. Where none is declared the panel renders the row's
      own fields and says which operation declined to have a detail form, rather than showing a
      shorter record and calling it the record
- [New] The panel is the grid's column kinds read vertically: the same figure, count, identifier,
      enum, prose, timestamp and geometry treatments, the same placeholder honesty on a withheld
      month, and the columns the grid hides listed with the reason they were hidden. Every field
      carries its JSON Pointer, off by default and toggleable — the key `meta.labels`, `_lineage`
      and the naked-number walker all speak
- [New] Join by navigation: every id in a record is a chip, and the hop table is derived rather
      than maintained. An id whose leaf is another dataset's whole `row_id` lands on that row; an
      id the target declares as a query parameter lands on that collection narrowed to it; both
      carry `as_of` and push history. `first_seen_manifest_id` resolves as a manifest id, which is
      what makes §3.3's diagram real without a mapping table
- [New] An id no served operation reads renders inert and says so, which surfaces a missing
      endpoint instead of hiding it behind a client-side join. A hop whose target still needs a
      path parameter nobody can supply is not offered at all
- [New] "How did I get here": the last three hops with the operation each one issued, copyable as
      a numbered list of curl commands whose URLs are the requests that were actually made, with
      `$GLASSWELL_KEY` where the key goes. Three is S9's own budget for a trace, and the panel
      says the older steps are not recorded
- [New] `row=` addresses the open row, so a record is a link somebody else can open. Expanding
      costs one detail request and no re-read of the page in view; the back button returns the
      grid with its cursor and its filters intact, which `explore/detail/back.test.ts` drives end
      to end through the shell
- [Fix] A figure inside the detail is a flex line, not two of the grid table's tracks. The cell's
      `grid-template-columns: subgrid` resolves to `none` outside the table, and `6,000 bbl`
      rendered one character per line — caught in the capture pack, not by a test
- [Fix] The detail panel takes the width the reader can see rather than the width of the longest
      row: it sticks to the scrollport's left edge and caps at the grid host's inline size. At
      1366 it was 884 px against a 762 px panel, so a record that fits needed a sideways scroll to
      be read
- [New] New Mexico promotes into `canonical.production_monthly` at `well_completion_pool`
      granularity under the widened S-E key. A well producing from two pools is two observed
      rows rather than a key collision, which is why the key was widened before P7a
- [Change] Promotion is set-based: one `(report_vintage, production_month)` batch at a
         time, appended by a server-side anti-join against that month's canonical head.
         Nothing larger than one month — 147,714 rows at the widest — is ever in Python,
         where the ND-shaped design would have needed roughly 19 GB of objects on a 15 GB
         machine at 48.1M records. The anti-join is verified against that design on the
         fixture rather than trusted
- [New] `cr_nm_wcproduction_window_1` records DIR-12's 2015-01 window as a promotion
      parameter rather than a property of the artifact: staging holds all 635 months, the
      effective window is stamped on every promotion derivation, and widening it is the
      same run again
- [New] `cr_nm_wcproduction_collision_1` rules on the two rows the artifact files for
      25,029 in-window well-completion-months, almost always under two OGRIDs. Summing them
      is refuted by the bytes — 5,059 pairs already report more producing days between them
      than the month has, and 5,564 report the identical amount twice — and choosing between
      them is refuted the same way, so a disagreeing pair promotes nothing and both filings
      are quarantined as `key_collision`, while an agreeing pair promotes once and the
      second is a `duplicate_row`
- [New] `cr_nm_wcproduction_days_1`: 244,025 rows file a day count longer than the month
      they file it for, 41,593 of them inside the window, and 131,531 file 99. The day count
      is withheld and the volume beside it still promotes
- [New] `cr_nm_wcproduction_volume_range_1` refuses a negative volume as
      `impossible_volume`. Three rows in 48,104,334 report one, all in 1993 and all outside
      the window — which is why the rule is seeded now rather than on the day the window
      widens onto them
- [New] The restatement stress case: changed bytes on two days give two vintages and an
      as-of read still returns yesterday's answer; a `mod_dte` bump with unchanged volumes
      appends nothing, because `value_hash` covers the measurement while `mod_dte` and
      `amend_ind` are change signals; and a second promotion inside one vintage is a no-op
      when it agrees and a refusal when it does not, which is the arm DIR-2's four do not
      cover
- [Fix] `tests/fixtures/nm_ocd/SOURCE.md`'s `api_well_idn` width distribution summed 45,097
      over the record count. Re-measured off the staged partition, it sums to 48,104,334
- [Change] `/v1/health` reports a registered source that has never been fetched as
         `pending` and names it in `pending_sources`, rather than calling it degraded.
         Registration says the pipeline knows about a source, not that a pull has happened;
         nine NM sources registered ahead of their promotion deploy would otherwise hold the
         endpoint permanently degraded and drown the signal it exists to carry

### 2026-08-21 — increment-3 merge train

- [Fix] The `collateral` job's link check allows this product's own `gw:` scheme beside
      `http`, `https` and `mailto`. `blueprints/SB-05-map-ui.md` shows the form a live data
      link takes, and the check read the example as a missing local file — red on `main`
      since the document landed, and reported by two branches that each correctly declined
      to edit another lane's file
- [Fix] `test_nm_fetch_vintage.harness_dsn` takes the session password from the fixture
      rather than a `glasswell:glasswell` literal. D1 was cut before DIR-14 randomised it,
      so the two only met at the merge and an authentication failure read as an FTP defect
- [Fix] The Caddy basemap block's restated CSP carries the satellite imagery origin its
      API-side original gained in the same increment

### 2026-08-21 — the z<=7 overplot gate

- [New] The four well and lateral tile functions keep one feature per half CSS pixel at
      z<=7, ranked by `md5(api10)`. Below z8 the map draws more features than it has
      pixels for and the surplus reads as alpha overplot: on the ND measurement half the
      features carry 15% of the ink at z7 and 0.5% of it at z4, and the projected saving
      is z0-z7 session bytes 5.68 MB -> ~2.0 MB. The rank is deterministic and carries no
      tilt — `spud_year desc` and `lateral_length_ft desc` were measured and rejected
      because they visibly shift the status colour mix, which is a biased sample of
      something the reader reads as information (DIR-11 gate, conditions C1-C4)
- [Change] `TileLayer` carries the gate per layer. Spacing units publish no `api10` and so
         have no rank; a layer marked thinned without one is refused at SQL generation
         rather than installed. The gate is a rank inside the cell rather than a
         `distinct on` over it, because 547 of Texas's 355,463 wells and 144 of North
         Dakota's 43,817 sit at a coordinate another well already occupies: a set-collapse
         drops those at every zoom, and only inside the band is what was approved

### 2026-08-21 — Texas on the map: RRC GIS wells and wellbore identity

- [New] `glasswell.ingest.tx_gis` loads the RRC county well archives — surface points,
      bottom-hole points and well arcs, three shapefiles inside one `well###.zip`, each with
      its own `.prj`. Staging holds them in the datum the archive declares (EPSG:4267) and
      the transform to 4326 is a promotion step under `cr_tx_nad27_1`, which pins a PROJ
      `hgridshift` pipeline over `us_noaa_conus.tif`. The grid is fetched as its own
      manifested artifact and its hash is checked against the rule, so a host without it
      fails rather than falling back to the three-parameter transform PROJ would otherwise
      choose — a median 3.40 m error where the pinned pipeline leaves 0.0074 m
- [New] `glasswell.ingest.tx_wellbore` loads the Wellbore Query export: 59 comma-separated
      fields, no header row, so the layout is `cr_tx_ewa_layout_1` carrying the RRC manual's
      own field numbers and two assertions proved on every record before anything is
      promoted. It writes TX identity into `canonical.wells` — operator, well name, status,
      total depth, completion date — and the well-to-lease keys into
      `canonical.well_lease_links`
- [New] `canonical.well_lease_links` captures `(oil_gas_code, district_no, lease_no)` under
      `cr_tx_lease_key_1` with `link_role = validator_a`. A bare lease number is not a key:
      33,868 of 348,293 in the 2026-08 export appear under more than one (code, district)
      pair. The links are recorded beside the canonical crosswalk the PDQ path will bring,
      never merged into it — their disagreement is the allocation error bound (SB-01 §2.9)
- [New] `mft_guid_resolve` is implemented: `glasswell.ingest.tx_mft` resolves a GoAnywhere
      public link to its listing, hashes it, and downloads through the portal's own form
      postback. The listing paginates at 250 rows while the well folder holds 255, so a
      first-page read silently loses four counties including Yoakum; the resolver pages once
      and refuses a listing shorter than the row count the portal declares
- [New] TX tile layers `tx_wells` and `tx_laterals` follow the landed view-model and
      function-source pattern exactly — privilege-scoped `marts.tile_tx_*` views, one
      `marts.<layer>(z, x, y, query)` function each, martin grants in the migration,
      `auto_publish` still false — and the map registers both, on by default, so panning to
      the Permian shows wells without a toggle in between
- [New] `service` joins the canonical status vocabulary. Eleven of the RRC's twenty-three
      well types describe injection, disposal, storage or observation rather than
      production, and 24,710 rows in scope are injection alone; painting those as active
      would be a claim about production the source does not make
- [New] A TX well card shows identity and geometry with their handles — total depth is a
      figure with a derivation, not a bare number — and carries no production section at
      all. `/v1/wells/{api10}` and `/v1/wells/{api10}/production` both warn
      `production_pending_allocation` and link the rule: TX reports at the lease (DIR-3), so
      "no production has been reported" would be false about a well whose lease reports
      every month
- [Change] The compute-CRS rule a length resolves is the one the basin names.
         `lineage.crs_registry` gains `length_rule_source`, the Permian row pins UTM 13N for
         area work with `cr_tx_compute_crs_1` measuring geodesically, and a TX length now
         cites a rule about TX geometry rather than ND's
- [Change] `lineage.quarantine_rows` admits `out_of_scope`: a county file whose features
         carry another county's API is not a parse failure, an unknown vocabulary or an
         orphan, and every existing code would have asserted something that did not happen
- [Fix] The TX identity pass keys API-10 over every record and the lease key only on the
      link path. Keying both together quarantined a well for a lease number it does not need
      and lost whole counties — every one of Bee county's records has no lease number yet

### 2026-08-21 — D1 phase 2: 48 GB of XML streamed into staging without holding it

- [New] Migration 028: eight verbatim staging tables for the NM sibling sources, a Parquet
      partition registry for the production spine, the NM pool, status and stream
      registries, and an index on `(source_id, production_month)` so promotion's batch
      predicate has something to sit on once canonical grows 122x. The reason vocabulary
      is untouched — migration 021 already admits `key_incomplete`, and the two codes
      SB-01 handback H5 asks for belong to the track that owns H5
- [New] `ingest/xml_stream.py`: BOM-aware UTF-16 decoding, a fully-qualified match against
      the `SqlRowSet1` namespace, and root pruning into 65,536-row batches. A bare-tag
      match against this document returns zero records in silence and `elem.clear()`
      without pruning holds all 48.1M siblings, so both are pinned in a rule and asserted
      in a test
- [New] `staging/duck.py` makes DuckDB — locked since P0 and imported nowhere — both the
      Parquet writer and the reader. Batches cross into it through the Arrow C stream
      capsule polars already exposes, because `pyarrow` is not in the lockfile and is not
      being added; `COPY ... (FORMAT PARQUET)` after `SET threads=1` is the expressible
      form of SB-01 §3.6's write profile, and the same rows written twice are byte-identical
- [New] `ingest.nm_ocd --stage-only` streams each artifact out of its zip member — nothing
      is extracted, so NM contributes nothing to the scratch budget — and reconciles every
      parsed row as staged or quarantined on the derivation itself (SB-01 §3.5). A batch
      that loses a declared column is quarantined as `schema_mismatch`; a column nobody
      declared, or a member that stops being XML, halts the load rather than staging a
      partial artifact as if it were whole
- [New] Twenty parse-stage rule rows: a record-tag, namespace, encoding and declared-header
      rule per source, plus the CHAR widths each one pads to. `prd_knd_cde` is CHAR(2) and
      arrives as `'O '`, so an exact-match vocabulary would have quarantined every row of
      the spine as `stream_not_promoted` while reporting success — the trim is a mapping
      decision and gets a rule row rather than a `.strip()` in the parser. Which columns
      pad is measured across every record of all nine artifacts, not assumed: 26 columns
      in six sources, each to one fixed width, while leading spaces are data

### 2026-08-21 — Basemap coverage and the 40 ms proxy stall

- [Fix] Basemap coverage: the serving extract is `conus` (z0–13, 4.22 GB) rather than the
      `nd-tx` box, which ended at the Rockies and at Memphis and rendered blank ground with
      no error at z3–z7. `scripts/basemap-regions/conus.geojson` is a superset of every
      basin region, asserted in `tests/unit/test_basemap_regions.py`, so a swap cannot lose
      coverage; the ND tiles are byte-identical
- [Fix] `/basemap/*` is served by Caddy's `file_server` instead of proxied to uvicorn:
      `uvicorn --workers N` binds a socket with `proto=0`, so asyncio never sets
      `TCP_NODELAY` and Nagle holds every response body under the loopback MSS until the
      peer's 40 ms delayed ACK. LAN medians through https: 4 KB range 48.7 → 5.9 ms,
      16 KB 49.0 → 6.4 ms, 16 KB eight-way 49.6 → 7.6 ms. The uvicorn mount is unchanged,
      so reverting the Caddy block is the whole rollback
- [New] `scripts/tile-probe.py` measures the basemap and tile paths over the transport a
      browser negotiates — sequential and concurrent range reads, first fetch, and
      `If-None-Match` revalidation — and reports percentiles rather than one sample
- [Change] `basemap-build.sh` verifies the extract before it takes the archive name, records
         the archive's own `bounds` in the manifest, and writes a `MANIFEST.sha256` that
         `sha256sum -c` passes in the deployed directory with no arguments (SB-06 §rules
         1-2). A coverage claim is now readable without opening the archive
- [Change] `infra/basemap/README.md` records the region-is-coverage rule, the measured size
         ladder for `conus`, the symlink swap, and the Nagle diagnosis with the `tcpdump`
         that convicts it; `infra/caddy/README.md` records why the basemap block is the one
         place the edge states the response policy

### 2026-08-21 — the Caddy→uvicorn hop moves to a unix socket

- [Fix] Every proxied response smaller than the loopback MSS paid ~40 ms of Nagle/delayed-ACK
      before its body left the origin: `uvicorn --workers 2` builds its listener as
      `socket.socket(family=family)`, leaving `proto` at `0`, so
      `asyncio.base_events._set_nodelay` never sets `TCP_NODELAY` and the separate header and
      body writes stall. Caddy now dials `unix//run/glasswell/api.sock` and uvicorn binds it
      with `--uds`; AF_UNIX has no Nagle, so the defect cannot occur rather than being tuned
      around. Measured over the real https path, medians of 30: `/v1/health` 64.5 → 21.0 ms,
      a well card 84.1 → 39.0 ms, `/v1/wells?limit=25` 67.0 → 21.6 ms, a z11 tile 50.8 → 8.5 ms,
      a z13 tile 50.2 → 8.2 ms, the app shell 49.7 → 7.6 ms, `/healthz` 48.3 → 6.6 ms — every
      one a ~42-45 ms drop. The 304 path (8.6 → 7.9) and the basemap (5.8 → 4.6, served by
      Caddy) never paid the tax and did not move, which is the same evidence from the other
      side. Root cause and `tcpdump` in `work-output/tileperf-r2-status.md` §1
- [Change] The API has no TCP listener at all, and `--forwarded-allow-ips` moves from
         `127.0.0.1` to `*`: a unix peer has no address, so uvicorn leaves `scope["client"]`
         None and a numeric allow-list would stop trusting `X-Forwarded-Proto` and silently
         strip `upgrade-insecure-requests` from every CSP. The socket has one reachable peer,
         so `*` grants nothing the directory mode has not already decided. Caddy still binds
         `192.168.2.111:8000` for the courtesy redirect — that block is Caddy's and is
         unaffected
- [New] `infra/tmpfiles.d/glasswell.conf` creates `/run/glasswell` as `0750 glasswell caddy`,
      which is the whole access control because uvicorn chmods the socket `0666` and exposes
      no knob for it. Deliberately not a `RuntimeDirectory=`: systemd re-applies
      exec-directory ownership on every exec invocation, so a `chgrp` from `ExecStartPre`
      exits 0 and is then reverted before `ExecStart` — which cost a 502 on first deploy.
      `ExecStartPre=rm -f` replaces the stale-socket cleanup `RuntimeDirectory=` used to give
      for free, since uvicorn's `bind()` returns `EADDRINUSE` and exits; `install.sh` places
      the file, runs `systemd-tmpfiles --create` and creates the `caddy` group unconditionally
- [Change] `verify.sh` reaches the API through `--unix-socket` and its `exposure` block now
         asserts the socket answers, that its directory is `glasswell:caddy 0750`, and that
         nothing is bound to `127.0.0.1:8000` — the inverse of the assertion it replaced
- [New] `tests/unit/test_api_socket_contract.py` holds `glasswell-api.service`, the Caddyfile
      and `verify.sh` to one socket path and to the `*` allow-list, since each file is
      individually valid when they disagree and the symptom is a 502

### 2026-08-21 — DIR-14: the suite runs on the CI host, not the workstation

- [Change] The integration harness supports a remote docker daemon. A container's bridge IP
         is routable only from the daemon's own host, so `tests/conftest.py:daemon_address`
         decides once: a local daemon keeps the bridge address, a remote one publishes the
         database port and is addressed by the daemon's own hostname. Containers a test
         starts keep using the bridge address either way — `database_address_for_containers`
         is that address, and the martin test now takes its DSN from it rather than from the
         client's connection parameters
- [Change] The martin test copies its config in with `docker cp` instead of bind-mounting
         `tmp_path`, which a remote daemon cannot see, and reaches the server on a published
         port when the daemon is remote
- [Change] The session database's password is per-session rather than the fixed pair, since
         a remote daemon means a LAN-reachable port; `postgres_password` hands it to the two
         marts CLI tests, which reconnect from a `ConnectionInfo.dsn` that never carries one
- [Change] The session DSN carries keepalives and `tcp_user_timeout=30000`. A LAN loss burst
         backed one connection off to a 107-second RTO and hung a 25-minute run; the same
         fault now fails the test that hit it. They fire on unacknowledged data, so a slow
         query is unaffected
- [Change] An explicit `DOCKER_HOST` is now the only candidate the probe tries — a
         `make test-anvil` that silently fell back to the workstation would report a full
         suite against a host it never ran on
- [New] `make test-anvil` runs the full suite on the lab CI host, which is where full suites
      belong; `make test-local` is the same suite on this machine's daemon, for iteration
- [New] `make check-workstation` (`scripts/workstation-hygiene.sh`) fails on glasswell state
      that has no business on a workstation: installed units, cron entries, routable
      listeners, dev servers left running, unswept test volumes, regulator downloads outside
      the raw zone, and basemap extracts. Read-only — it reclaims nothing itself
- [New] The harness asserts which branch it took: one test that the session container
      publishes a port exactly when the daemon is remote, one that the client DSN and the
      container DSN agree about locality, and unit coverage of `daemon_address` across
      socket, loopback and remote endpoints

### 2026-08-20 — D1 phase 1: New Mexico's production spine, pulled and stamped

- [New] `lineage/ftp.py` and an `ftp_anon` transport inside `fetch_raw`: anonymous FTP to
      the pinned host, MDTM and SIZE read before the transfer and recorded in
      `acquisition_params`, the bytes hashed as they stream, and a short transfer refused
      rather than sealed. A host that does not answer halts with `raw.fetch_failed
      reason=host_unresolved` instead of guessing — the EMNRD page publishes the address
      as an image, so a re-pin is a config change and an audit event, never a scraper
- [New] Nine NM OCD sources with the honest licence note: UNVERIFIED, no published grant,
      and absence of a restriction is not a grant
- [New] Twenty-seven parse-stage rule rows — an undated-vintage, an FTP-layout and a
      host-pin rule per source, because `load_rules` reads one `source_id` per call and a
      derivation may not cite another source's rule. The FTP refreshes nightly with
      undated per-table filenames, contradicting its own published documentation, so the
      retrieval vintage is glasswell's own stamp and the `source_key` is the constant
      filename the supersession chain is built on
- [New] `ingest.nm_ocd --fetch-only`: one login, the tables in order, five seconds apart.
      A reset data channel — which is what 164.64.106.6 did on the third transfer — is
      retried twice on a fresh login, each failure recorded; a host that will not answer
      is never retried
- [New] Fixtures cut from one polite pull cached to `/data/raw`, preserving UTF-16LE with
      its BOM, the `SqlRowSet1` namespace and the inline schema. The production fixture
      straddles DIR-12's 2015-01 window because the member opens in 1973, and
      `tests/unit/test_nm_fixtures.py` asserts every trap it exists to carry
- [Change] `fetch_raw` reads `upstream_mtime`, the etag and the media type from whichever
         transport ran rather than from HTTP headers, and hashes the sealed files in
         chunks — the NM artifact is 968 MB and `read_bytes()` held all of it
- [Change] `seed_conformance_nd` counts its own jurisdiction's rules rather than the whole
         registry, which is what made a second state's seed non-idempotent

The `wcproduction` member measures **48,310,560,330 bytes across 48,104,334 records**,
streamed once in 24m51s: 17,645,580 rows and 80,624 well-completion × pool entities fall
inside the 2015-01 window. Three findings change what phases 2-4 must handle — a fourth
`prd_knd_cde` (`'C '`, condensate, 1986-1993 only), one row whose `api_well_idn` is six
digits and cannot compose an API-10, and an `amend_ind` that is a ten-value vocabulary
rather than a flag. `tests/fixtures/nm_ocd/SOURCE.md` carries the measurements.

### 2026-08-20 — increment-3 closeout

- [Fix] A well whose status is present but not in `cr_nd_status_vocab_1` is drawn as the
      absence class instead of not being drawn at all. The filter matched the literal
      `unmapped` id while the count routed any unrecognised code to it through
      `statusClass()`, so an unknown code fell out of the canvas, the legend count and the key
      at once — the failure mode the class exists to prevent

- [Fix] The satellite basemap's declared graticule fallback executes. `BasemapDef.fallback`
      had no consumer at all — `resolveStyle`'s non-vector branch set no failure path — so a
      reader whose imagery could not be fetched got an empty canvas, no banner and no
      graticule. The client now asks the imagery origin for one tile before committing to it,
      and degrades locally when the answer does not come (gate-inc3 R3.1)
- [Fix] The failure banner names the source that failed. The raster style reused the vector
      source id, so a USGS outage reported itself as `Tiles for protomaps did not load`; the
      imagery style now carries its own source and `sourceLabel()` turns a MapLibre
      `sourceId` into the locator a reader can act on — a host, or the archive path (R3.2)
- [Fix] The imagery attribution goes down with the imagery. A credit over a canvas with no
      imagery on it is a false statement about what was drawn (R3.3)
- [Remove] The hosted OpenFreeMap fallback, which `connect-src 'self'` had always refused;
      every basemap now degrades to the graticule, locally, through the one declared-fallback
      path both the vector and the imagery branches run

- [Change] The CSP names one external origin, `https://basemap.nationalmap.gov`, in
         `connect-src` and `img-src` and in no directive that loads code. USGS National Map
         imagery is public domain and keyless and has no self-hosted equivalent, so the
         satellite basemap could not draw under `connect-src 'self'` — 122 refusals and an
         empty canvas. Named, never a wildcard; requests happen only when a reader selects
         satellite, and dark, light and none stay zero-external under test (DIR-1 ruling)
- [Change] SB-05 §1.5 carries the amended policy and the reason, so the blueprint and the
         emitted header do not disagree

- [Remove] `statusMinZoomExpression()` is gone. The per-class zoom floor has one
      implementation — `visibleStatusesAt()` inside `statusFilter()`, measured holding at z4
      and z6 — and the second expression of the same table had no consumer at all
      (gate-inc3 4.1)
- [Fix] The status gate is applied to every layer the vocabulary paints, derived from the
      built layers rather than from a hand-written pair of ids. The pair was complete for
      North Dakota alone; a second basin's layers were ungated at style-build time and drew
      every class at every zoom until the reader happened to zoom, which is the disagreement
      between legend, count and canvas the gate measured on the Permian frames

- [Change] The unmapped row filters like every other class: its checkbox is live, All/None
         act on it, and `statusFilter()` withdraws it when the reader switches it off.
         It stays on by default and the zoom never withdraws it — a defect must not hide —
         but on the Permian slice it is the largest class on the canvas, and unfilterable
         ink is ink the reader cannot account for (gate-inc3 4.2)
- [Change] The legend builds the absence row up front and lists it only once the map has
         drawn one, so the switch exists before the class does; the collapsed pill counts
         what it lists (`Well status · 9/10`), and `glasswell.statuses` carries `unmapped`
         in its known vocabulary so a reader's refusal of it survives a reload

### 2026-08-20 — VF-6: legend select/deselect all

- [New] The well legend's header carries an All/None control, so clearing or restoring
      the nine status classes is one click rather than nine. It owns `checked` and
      nothing else: `disabled` and the out-of-scale mark stay the zoom's to set, so
      "All" cannot promote a class the zoom has withdrawn, and "None" clears one anyway
      so zooming in does not resurrect what the reader dismissed. It reports through
      the same `activeStatuses()` path a row toggle uses, and is hidden while the key is
      collapsed to its pill (VF-6)
- [New] The legend's status filter now survives a reload, under the same `{on,known}` shape
      the layer set has always used (`glasswell.statuses`), so a class added to
      `cr_nd_status_vocab_1` later arrives visible rather than hidden by a stored set that
      predates it. It did not persist before — VF-6 names a persistence contract the legend
      was not party to, and this is that half (VF-6)
- [New] The collapsed legend pill reads `Well status · 3/9` whenever classes are filtered
      out. A filter that survives a reload must not be invisible on the canvas that reload
      produces
- [Change] `persist.ts` takes the storage key as an argument — `readCapabilitySet`,
         `writeCapabilitySet`, `restoreCapabilitySet` — and keeps one debounce timer per
         key, so a status write cannot cancel a layer write still in flight

### 2026-08-20 — DIR-13: TLS on the LAN endpoint

- [New] Caddy terminates `https://glasswell.lab.rpx.sh` on VM 111 and reverse-proxies
      uvicorn on `127.0.0.1:8000`. The certificate is a Let's Encrypt host certificate
      obtained over the Cloudflare DNS-01 challenge — the only challenge that can be
      solved for a name resolving to RFC1918 — and `infra/caddy/` carries the Caddyfile,
      the unit and the argument for a download.caddyserver.com custom build over the
      distro package and over xcaddy (DIR-13)
- [Change] uvicorn binds `127.0.0.1:8000` rather than `0.0.0.0:8000` and runs with
         `--proxy-headers`, so the origin sees the request as https and its CSP carries
         `upgrade-insecure-requests`; `ufw` opens 80 and 443 to `192.168.2.0/24`, plus
         443/udp because Caddy advertises HTTP/3 in `alt-svc`, and the 8000 rule is gone.
         martin is untouched
- [New] `install.sh --with-caddy` places the Caddyfile and `caddy.service` and refuses to
      proceed on a binary without the cloudflare DNS module, a missing token file or one
      wider than `root:root 0600`; it validates the config before enabling the unit, and
      re-owns the access log the validation creates as root
- [New] `verify.sh` grows a `tls` block — issuer, subject, days remaining (a failure at 20,
      ten days after Caddy should have renewed, which is DIR-13's renewal alarm), the `:80`
      redirect, exactly one copy of each security header through the edge, one
      content-encoding on the bundle and on a tile, and a loopback-only admin API.
      `caddy.service` carries the `OnFailure=glasswell-alert@` hook the other units use
- [New] Caddy's access log filters both shapes the owner key can take: the
      `X-Glasswell-Key` header, and the `?key=` parameter the API refuses with a 422 but
      which an edge writes down verbatim — the way a key reached a log here once before.
      `verify.sh` sends both through the edge before reading the log back, so the check
      cannot pass for want of keyed traffic
- [Change] `scripts/smoke.sh` and `tests/e2e/smoke.mjs` read `$GLASSWELL_BASE_URL` and
         default to `https://glasswell.lab.rpx.sh`; `GW_BASE` survives as the retired
         alias so an old invocation targets what it names instead of the default
- [Change] SMOKE.md, `infra/README.md` and the e2e README are re-pointed at the https URL
         with no port, and the two stale suite counts (nineteen API assertions, twelve
         browser ones) are the twenty and thirteen the suites actually run

### 2026-08-20 — wave 1 merge train: the data-train batch fix

- [Fix] The anonymous read break-glass can no longer mint a credential. With
      `GLASSWELL_ALLOW_ANON=1` a caller presenting nothing resolved to owner *scope*,
      which satisfied the mutation guard, so the flag could leave durable owner keys
      behind that keep working after it is turned off. `check_scope` now refuses
      `kind = anonymous` for the mutation scopes; the read break-glass is unchanged
      (gate-a2-qa m-7)
- [Fix] Four published examples that could not resolve on a deployment now say so
      where a reader meets them: a vintage id is composed from a source and a
      knowledge date rather than content-addressed, a manifest's bytes carry the
      content-address note its sibling record already had, and the two key
      operations name a key the contract fixture seeds instead of a fabricated
      ULID (gate-a2-qa M-3)
- [Fix] The auth matrix covers `GET /v1/wells/{api10}/production/pools`. The
      endpoint arrived with one track and the matrix with another, and the
      coverage check that exists for exactly that caught it on the merge commit
- [Change] `e3-length-buckets.sh` computes the snapped bucket cuts in SQL and prints
         them in its verdict, instead of carrying the quartiles measured once as
         literals. `run-all.sh` can re-decide `LENGTH_BUCKETS_FT` after the E-0
         back-load without an agent editing the script (gate-bgate M-1)
- [Fix] `g13-formation-pools.sh` emits the two `VERDICT|` lines `run-all.sh` greps
      for — the `FORMATION_GROUP_MIN_COUNT` measurement at the threshold and the
      registry precondition — both read out of the measurement. The grep is
      `|| true`, so their absence was silent (gate-bgate m-4)
- [Fix] The glossary is alphabetical again: four adjacent pairs were transposed
      (`Effective date`/`EUR`, `Structural residual`/`Tile layer allowlist`,
      `Viewport`/`Vintage`, `Withheld`/`Working interest`). It is the seed set for
      `glossary_terms`, so its order is data (gate-bgate m-6)
- [Fix] The martin binary the tile-publication test starts is pinned to `1.14.0`,
      the version VM 111 runs; `latest` resolves there today and would move the
      test's subject silently (gate-o m-6)
- [Change] The OpenAPI snapshot is regenerated over the three data tracks at once —
         28 paths, the union of the freeze's 27 and the pool breakdown. A2's own
         differ classifies the delta as thirteen changes, all additive
- [Change] `infra/martin/config.yaml` publishes the three tile *functions* rather than the
         three views they read. Adopting it as table sources would have turned auto-publish
         off at the cost of the tile work landed hours earlier: a table source has no `z` to
         key a simplify tolerance on and cannot carry the materialised CTE. Measured on the
         deployed instance, table sources cost +21% bytes at z7, +35% at z9 and +42% at z11
         on `nd_laterals`. The privilege boundary is untouched — a `language sql` function
         runs with the caller's rights, so the `martin` role still reaches exactly the three
         `marts.tile_*` views, which is also why those views had to become what the functions
         read (DR-05, N-2)
- [Change] The deploy runbook reinstalls the tile functions when `marts/tiles.py` moves, and
         clears `.claude`/`.rdf` with the other working files. martin resolves the function
         signatures at startup, so a stale body is now a stale tile source rather than an
         unused one
- [Fix] `smoke.sh`'s per-point lineage assertion skips the `*_aggregation` columns.
      They are disclosure labels rather than figures and carry no handle, so the
      check demanded a handle that should not exist and read FAIL against a correct
      response — the same shape as the auth-matrix gap, one track's check meeting
      another track's new field
- [Change] SMOKE.md is re-read against the deployed instance after this train: the
         martin catalogue, the unsimplified-tile and the deploy-root-hygiene gaps are
         closed, the basemap is no longer described as absent, and a new entry states
         that the S-E re-promotion is armed on a timer rather than run, with the counts
         either side of it


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

### 2026-08-20 — wave 1: ops and the regression net

- [New] `scripts/smoke.sh`: twenty read-only assertions over a deployed instance —
      both refusals, the key refused in a query string, the card's unit and derivation
      handle, per-point production lineage, the chain that ends at a 64-hex sha256 and a
      `dmr.nd.gov` url, every conformance rule's rationale and evidence url, a tile
      derived from the well's own surface point, staging refused through the proxy, and
      every committed OpenAPI path present on the instance
- [New] `tests/e2e/`: thirteen browser assertions and `make test-e2e` — the app boots and
      draws, a deep link resolves to the well it names, a handle reaches a checksum and a
      regulator url on screen, a hostile query string puts the page outside neither the
      tile allowlist nor this origin, and a visitor with no key is refused honestly. Its
      own npm project, so `playwright-core` never enters the web bundle's lockfile
- [New] `tests/integration/test_tile_wire_types.py` audits every column of every served
      relation, enumerated from the catalog rather than from the declarations — property
      types, geometry type and srid against `geometry_columns`, the attributes read back
      out of the protobuf, and the tile role's own column grants
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
      migration 017 widened the column, and `lateral_length_ft_exact` riding an
      auto-published tile as a 19-digit string across 8,611 features
- [Fix] `create on schema marts` existed only because it was typed on the deployed host
      during P7; it is held by a migration now, with the spacing-unit view granted to the
      API role that migration 009's blanket grant could not reach
- [Fix] The pmtiles install hint and the basemap runbook told every operator to write the
      same `/tmp` path; both use `mktemp -d` now
- [Fix] DR-05: `infra/martin/config.yaml` had never been adopted because its DSN names no
      user and `martin.service` runs `User=martin`, for which no PostgreSQL role existed.
      Migration 026 creates it, publishes each layer through a `marts.tile_*` view holding
      exactly the columns that layer serves, and grants the role select on those three views
      and nothing else — so `staging`, `canonical` and the `numeric`
      `lateral_length_ft_exact` are unreachable by privilege rather than by declaration.
      `install.sh --with-martin-config` places the file and a `martin.service` drop-in.
      Adopted, martin publishes three sources where auto-publish published eleven, three of
      them `staging` relations
- [New] `tests/integration/test_martin_publishes.py` starts the martin binary as the role the
      unit runs as and reads its catalogue. Config and grant were previously verified apart:
      a column-level grant expresses the same intent and cannot work, because PostGIS's
      `geometry_columns` filters on `has_table_privilege`, and martin would have exited into
      a `Restart=on-failure` crash loop with every tile down
- [Change] The martin config declares `pool_size` under `postgres:`, where 1.14.0 reads it;
         at the top level it was silently ignored. The same run settles the
         view-under-`tables:` question — martin resolves the spacing-unit view as
         `source.kind="view"` without complaint
- [Change] SMOKE.md re-read against the instance that ran migrations 014-019: the hero
         lateral is 15,065.44 ft, there are 17 conformance rules, the quarantine ledger is
         292,972 rows with `unknown_vocab` and `out_of_range_date` at zero, and "292,394
         rejected rows" is corrected — 98.7 % of the ledger is deliberate non-promotion
         and true source-row rejection is 0.79 %

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
