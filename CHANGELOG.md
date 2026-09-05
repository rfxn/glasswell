# Changelog

All notable changes to glasswell. Newest first.

Blueprint versions and code versions are tracked separately: `blueprint.md` carries
its own version in its header, and its history is summarised in §3.1.

## Unreleased

<a id="v0.82"></a>
## v0.82 — 2026-09-05

- [Fix] Caddy redacts the credential-shaped headers the API refuses as well as the one
      it accepts: Authorization, Proxy-Authorization and X-Api-Key join X-Glasswell-Key,
      Cookie and X-Glasswell-CSRF in both listeners' access-log filters. The log line is
      written before the refusal, so a key guessed into a header the API never reads was
      logged in full — which is how one reached tunnel.log and forced a rotation
- [Change] verify.sh asserts snapshot freshness and check health separately, and the
           health failure names the check and job ids it failed on; as one assertion it
           reported an unavailable check as "marked the freshly collected snapshot stale",
           which was a false statement about the host on every train that ships an
           empty-mart disclosure as a check
- [Change] The Texas load runbook states which verify assertion is expected red before the
           load and green after it, and the exactly three check ids it may name; "verify
           green, then the load" was circular for a train whose reds are the disclosures
           the load clears
- [New] A shipped em dash in any literal under web/src is red, gated on the corpus the
      tofu sweep already reads; the class was swept by grep twice and reopened both times
- [Change] The five em-dash literals still on the wire are reworded: a refusal pointer
           joins its detail with a colon, and the absent-value mark reads `--` on the
           vintage slot, the figure tree, the grid's absent cell and the map hover card
- [Fix] PERF.md §3's budget table quoted a map-chunk measurement three trains stale, so
      the headroom it stated as +5.2% was really +1.3%; all three rows are re-measured at
      a stated head by a stated method, and a budget quoting a figure more than 3% from
      what the build measures is now red
- [Fix] The layer panel's provenance row renders the lineage mark through the module that
      owns it rather than spelling the codepoint a second time
- [New] a fourth bundle budget, the entry stylesheet at 7,420 B gzip: the budget
      test resolved only `.js` out of `dist/index.html`, so a 30 kB stylesheet
      addition passed every gate in the file; set at the 6,507 B measured plus the
      900 B the rail is allowed to spend, and ratcheted at the end of the release
- [Change] the lineage drawer is fetched on the first handle a reader opens rather
         than riding the entry chunk for every first paint; the entry falls 13,947 to
         13,026 B gzip (`gw-chain` 3 occurrences to 0) and an Explore reader's
         landing download falls 74,838 to 73,925 B
- [Change] the well card is an in-page right rail rather than a panel over the map:
         `#gw-main` is a grid whose columns are the map and the card, `#gw-map` leaves
         `position: absolute`, the card keeps `min(38vw, 540px)` exactly, and the map
         column measures 1,059 px at 1600 with the card open, 578 with the lineage
         drawer in its own column, 846 at 1366 and 634 at 1024 with the drawer stacked
         in the rail, against 560 + 8 + 12 and 135 + 78 + 12 in three strips before
- [New] the rail collapses to a 40 px strip carrying the well's name and an expand
      control, and the teaching hint steps aside by the strip rather than by a rail
      that is no longer there
- [New] a Locate control in the rail's head centres the map on the open well whenever
      the well has a surface point, because a rail lets a reader pan a still-open card
      off screen
- [New] below 900 px the sheet has three snap points, 160 px, 46dvh and 78dvh, driven
      by a grab bar that is a named three-value slider rather than a boolean
      disclosure, so every stop is reachable from the keyboard; the top stop is the
      single stop that shipped before it
- [Fix] `flyTo` reserves no right padding: it held back half the canvas for a card
      that no longer overlaps it, landing the well in the left third of its column
- [New] the card is ten named sections in one fixed order, three expanded and the
      rest collapsed and lazy, each an accessible disclosure with a stable id, an
      ARIA accordion keyboard, and a request queue that holds the fan-out to two in
      flight and never asks twice for a section it has
- [New] `?section=` opens, scrolls to and focuses a section by name; the card
      validates it against the list its own response made knowable, so an unknown id
      renders the default set, says so once and is dropped from the URL, and an id
      this jurisdiction has no section for names the section and links the rule
- [Fix] back and forward stop tearing the card down: `showWell` returns early when
      the mounted well has not changed, so a section-only history entry re-renders
      nothing, re-requests nothing and keeps the reader's disclosures and focus
- [Change] every request the card makes is built in one place and forwards the whole
         known bag (`as_of`, `from`, `to`, `normalization`, grain) where the card
         forwarded `as_of` alone; `section` is app state and reaches no request
- [New] `cr_status_history_basis_1` records, per jurisdiction, whether a well header's
      `effective_from` is the regulator's own valid time or the vintage of the extract
      glasswell pulled; it registers as the `status_history` decision for New Mexico
      and Colorado and is the only thing that emits `links.history`
- [New] `GET /v1/wells/{api10}/history` serves every effective-dated header a well
      carries, newest first and capped at ten with the remainder counted, over the
      filed code and never over the canonical class; the class column is headed
      "class as glasswell maps this code today", carries the mapping rule per row and
      says it is not historical
- [New] the well record carries the jurisdiction, the regulator and the regulator's
      portal, plus the jurisdiction's `geometry_provenance` rule, which is null for
      Texas and stated as a registry gap rather than filled with North Dakota's
- [Fix] a well whose class resolves nowhere shows the code its regulator filed and
      the regulator's name instead of no status at all; 68,186 Texas wells on the
      deployed instance serve a null class today and rendered a blank
- [New] `marts.well_basin_context`: which published basin polygon a well's surface point falls
      in, the plays that stack there, the ingest scope label kept beside them with their
      agreement marked, the boundary vintage and which geometry answered — one row per well in
      `canonical.wells_latest`, so a well with no geometry is `no_geometry` and a well inside no
      polygon is `outside_published_boundaries` rather than a null
- [New] five `basin_context` rules, one per jurisdiction, registering the polygon answer as a
      mapping decision with its measurement: ND 43,424 of 43,817 inside a published basin, NM
      137,505 of 142,000, TX 344,611 of 359,421 with 10,896 of them in a basin that is not the
      filed `permian`, and MT 13,062 of 40,626 with 27,564 outside every published boundary
- [Change] the card's Basin and geology section reads the served block instead of printing
         `canonical.wells.basin` as bare text: the polygon with its rule, the plays as chips,
         the filed label marked as the ingest slice it is, the boundary vintage, and the
         geometry that answered
- [Fix] every line the Basin section serves carries the derivation handle of the mart run that
      wrote it, and `/v1/explain` resolves it: the mart already recorded the run and the well
      record dropped it, so the section showed a rule link and no chain
- [Fix] the status-history clock is a rule per jurisdiction rather than one shared row: a
      Colorado card's `links.history_rule` served New Mexico's source and OCD evidence for a
      decision about Colorado's clock
- [Fix] the cap's served reason said a New Mexico well carries up to 15,590 effective-dated
      headers; 15,590 is the population's distinct filed dates and the fullest single well
      carries 15, with 248 wells over the cap of ten
- [Fix] `cap.total` counts the headers the well carries whether or not a history is served for
      its jurisdiction, where it answered 0 for a well with two
- [New] the deploy refreshes `marts.well_basin_context`, verify asserts it holds a row per
      well, and the scheduler registry carries the job with its dependency edges
- [Fix] the card prints the well type once, as its own regulator filed it, where the Drilling
      band still carried the bare code five rows below its replacement
- [Fix] back and forward to another well keep the section that history entry recorded; the
      section is dropped when a reader chooses a well, which is a different act
- [Fix] the section queue holds its bound when a second well mounts while the first is still
      loading, where a settling load took the counter negative and admitted a third request
- [Fix] an in-card section link's href carries the well, so a middle click or a copied link
      lands on the section rather than on the map with no card open
- [Fix] the coach mark steps aside by the drawer's own column at 1600 and rides above the
      sheet below 900, where it sat on the drawer's heading and on the phone's chart
- [Fix] the bottom sheet settles on a cancelled pointer as well as a lifted one, where a
      system gesture left it at an arbitrary height with its snap transition off
- [New] the rail names the well it carries, the lineage drawer offers the way back to it, and
      the Lineage index counts again when another section draws
- [New] the production chart is a control surface: the legend toggles a stream off
      plot, band and readout together and refuses to hide the last one, a log scale
      names what it cannot place, and a drag across the band brushes a window that
      rides `from`/`to` into the URL and is answered by the server on reload
- [New] a running total over the months on screen, computed on the served decimal
      strings rather than through a float, carrying no derivation handle at all and
      saying so: it counts each stream's own reported, reported-zero and no-report
      months and points at the ⌾ beside every point it summed
- [New] `?normalization=per_lateral_ft` divides a well's monthly volumes by its own
      lateral length as a served arm rather than in the browser, so the unit reads
      `bbl/kft`, the basis names the divisor, the method and the liquids policy
      together, and one chain resolves the production and the geometry it divided by
- [New] the lateral floor the divisor refuses below is read from the
      `cr_ff_fluid_intensity` family at request time and cited beside the length rule,
      where it was a constant in the serving module
- [New] the capture band: one row per stream whose window holds a month read at an
      earlier capture, a key that says in words what the two marks mean, and one
      control that re-reads the series at the earliest capture the window holds
- [New] the chart as a data table, fetched on the press and by no reader who lands on
      Explore, with one row per month and the unit, the null-semantics class and the
      point's own derivation handle in every cell
- [New] `links.type_curve` and a `type_curve_scope` block on every well record, so the
      Peer control section renders on a served link rather than on a client guess, and
      states the relation verbatim, the quantile convention, the ladder rung, the peer
      count per month, the pad-group exclusion and the knowledge cutoff
- [New] a Production by pool section, drawn with the monthly chart's own table rekeyed
      per pool and expanded by default where the jurisdiction files below the well, so
      a New Mexico card shows the record instead of an empty chart
- [New] CSV and JSON export of the window on screen, one row per month per stream, each
      carrying its unit, its class, its report vintage and its derivation handle, headed
      by the basis of every stream and the URL that reproduces the view
- [New] twelve glossary terms for the card's second generation: bottom hole, basin
      boundary, producing month, normalised volume, running total, status history, peer
      control, held-out subject, held out, log scale, derivation chain and scope label
- [New] a vocabulary gate over the shipped string literals that fails on the reserves
      and resource *nouns* rather than on the verb, holds `EUR` to an uppercase token
      beside a volume unit, and asserts the quantile-convention negation is still served
- [Change] the entry stylesheet budget ratchets 7,420 to 7,400 B gzip, which is the
         7,367 B this group measured plus 33: the card's second generation added three
         sections and the stylesheet fell, because the drawer's chrome moved onto the
         drawer's own sheet
- [Fix] a normalised series over a well whose months were promoted separately answered
      500: the divided points are evidence rows on the response derivation now, so the
      column carries one handle, every point's month names its own evidence, and the
      registrar is never handed a series that carries point handles
- [Fix] a month one promotion filed twice is addressed by the report vintage it was read
      at, where the point's ⌾ answered `selector_ambiguous` on a served figure; a
      restatement is a second row and never an edit, so the month alone never named it
- [Fix] no ⌾ is drawn on a month the response served no figure for: a withheld or
      unreported month resolved to nothing, and on a column with per-point handles it
      borrowed the first month's and opened another month's chain
- [Fix] `Per 1,000 ft`, `Read at …` and `Widen to the whole record` re-land the card
      instead of writing the URL and waiting for a reload; a brush still redraws what
      the card already holds, because those months need no request
- [Fix] a log axis prints no label on the minor ticks uPlot leaves unlabelled, where it
      printed the literal `null` eight times down both sides of a served chart
- [Fix] the table's stylesheet ships with the table rather than with the chart: on a
      pool-grain well the chart never loads, so both pool tables overflowed the card
      with no way to scroll to the columns past its edge. The peer, pools and export
      rules moved off the chart's sheet for the same reason
- [Fix] the data table's pinned month column marks the edge it covers, on a separated
      border model that travels with the cell: a shadow was painted on no cell of a
      collapsed-border table and a border was painted where the cell used to be, so a
      half-covered `10100.000 mcf` read `000 mcf` for three rounds with nothing to say
      so; a headless-Chromium gate now reads the pixels at max scroll in both themes
- [Fix] a month that is both withheld at pool grain and filed twice is served no
      `_lineage` handle: the two sets come from different tables and are not disjoint,
      and the response offered a resolvable chain for a figure it had not served
- [Fix] a press of `Per 1,000 ft`, `Read at …` or `Widen to the whole record` re-lands
      the card without taking the reader's place: the card stays on screen instead of
      flashing back to a loading placeholder, and the disclosures they opened, their
      scroll position and their focus stay where they were
- [Fix] a second window of a normalised or allocated series answered 500: the response
      derivation's partition named the well, the basis and the vintage but not the window
      or the stream set, so every window of one well shared a derivation id and the
      lineage store's determinism guard refused the second for the life of the store;
      two presses on the card reached it
- [Fix] the card's error banner invents no problem type where the API named none: a
      typeless failure read `Internal Server Error (about:blank)` and linked
      `/v1/errors/about:blank`, a page that does not exist, instead of naming the status
      and the request that failed; and it says a request failed and names the status
      over HTTP/2, which carries no reason phrase for it to print, where the heading
      read ` (HTTP 500)` on the deployment's own transport; a problem body that serves
      those fields empty, null or as the wrong type is filled the same way rather than
      rendering the empty heading back or deciding which failure the card is looking at
- [Fix] a re-land the server refuses costs the reader the section that asked and not the
      card: a press of `Read at …` at a vintage that resolves nowhere answered 404 and
      replaced every section, every disclosure and the window bar with the banner, where
      the refusal now stands in the production section, the card stays up and the panel
      carries no dismiss that would close it; a lost session still takes the whole card,
      because a card of the previous reading standing under one reads live
- [Fix] the capture band spans exactly the plot it captions, measured after the axes are
      placed rather than before: the band took the gutter of the layout that existed one
      tick earlier, so on a card where nothing mounts after the chart it ran 76 px wider
      than the drawing area at 1600, its cells a month off their ticks and the focused
      month's outline clipped at the card's edge, and it was only ever right where a
      later resize happened to arrive
- [Fix] the report-vintages disclosure a reader opened stays open across the chart's own
      redraws: a stream toggle, the log axis, a span press, a drag, clearing it and the
      table view each rebuilt the chart with the disclosure closed, and the summary those
      controls rewrite is the one they were closing
- [Fix] the capture band's row names fit at every width, the vintage control uses the
      text-safe cyan, and the widening control no longer abuts the sentence it follows

<a id="v0.81"></a>
## v0.81 — 2026-09-05

- [New] The weekly restore drill refuses before it creates a scratch database it has no room
      for: the scratch cluster's filesystem must hold `pg_database_size(glasswell)` plus
      10 GiB, the scratch database is still removed on the way out, and the receipt the status
      page reads distinguishes a measured shortfall from a probe that could not measure
- [Change] The storage check that gates a deploy follows PGDATA rather than `/`, is named
           `PostgreSQL storage` for what it now measures, and refuses below an absolute floor
           as well as below the 10 % ratio, both configured on the status unit: a tenth of this
           filesystem is less than the room the next state load needs, so the check stayed
           green on a disk already too small
- [Change] `wal_compression = lz4` joins the PostgreSQL tuning drop-in, against 43 million
           full-page images written in fifteen days; it reloads rather than restarting, and
           `infra/README.md` now says how a changed drop-in reaches the host, because a deploy
           neither applies one nor reverts one
- [New] The PDQ member layout is a conformance row: cr_tx_pdq_format_2 restates
      cr_tx_pdq_format_1 with the measured header of every member the Texas load
      reads and the subset each parse consumes, published by 081_tx_pdq_format.sql
- [Fix] The completion member is read at its measured 16 columns; the 13 the
      parser carried were transcribed from the manual and never measured, and the
      stage refused on the width
- [Change] A member's header is judged by name and position against the rule and
         refuses naming the columns and the rule id, so a renamed or reordered
         column is as loud as an added one; all five members read are judged,
         where three were read against no layout at all
- [Fix] A completed fetch is recorded when its bytes are placed rather than at the
      end of the run, so a refused parse leaves a manifest and the re-run reuses
      the slot instead of placing a second copy of the archive
- [Fix] An undeclared raw zone refuses with RawRootUnset; the default was the
      relative data/raw, which resolved against the caller's working directory
- [Fix] The two-clock gate for the Texas card reads the grain rule's own published
      vintage instead of a date the v0.80 repoint had already moved
- [Fix] The Colorado GIS staging reads the member ECMC actually ships:
      Directional_Bottomhole_Locations and Directional_Lines were selected by a
      suffix that ignored their separators, so --layer all refused after staging
      the wells layer; member selection now compares case and separators on
      neither side, and the three member names are conformance rows
- [Fix] A source whose artifact was fetched and never parsed is served as stale
      rather than current: a refused stage records the refusal against its
      manifest and leaves staging_load_ref unset, so a fetch that landed and a
      parse that refused are two answers and not one
- [Fix] Any way a Texas stage can end short of loading the archive is recorded
      against the manifest, not only a refused header: a memory kill, a database
      error or the per-year headroom refusal now leave the same staging.load_failed
      event and the same stale source the header refusal does
- [Change] The scheduler reads staging refusals through lineage.staging_load_failures
         rather than lineage.audit_events, so the least-privileged role gains one
         column of one event type instead of the account and session trail the same
         table carries

<a id="v0.80"></a>
## v0.80 — 2026-09-04

- [Change] Colorado's six job schedules observe: the rows `077_colorado.sql` registered
           launching are superseded at 2026-09-03 by rows that record what a tick would run
           and start nothing, each under its own `cr_job_cadence_<job>_2` rule stating why and
           which preconditions it is waiting on; the founding rows stand as what was decided
           on 2026-09-02
- [Change] `launch_mode = 'launch'` is the scheduler launch-flip track's own act rather than a
           choice a jurisdiction makes at registration; the add-a-state and scheduler runbooks
           say so, and a seed guard reddens on any row that resolves to it
- [Fix] `infra/verify.sh` compares the scheduler role's flags against `false|true`, which is
      what `rolsuper || '|' || rolcanlogin` returns; it asserted psql's bare-column `f|t`
      rendering, so the check could never have passed against any role
- [Fix] The Status page's `What drives this` no longer opens on the sentence already in the
      Cadence cell beside it, which it repeated on 31 of 38 job rows
- [Fix] A command-line flag inside a cadence note is held on one line, so `--promote-design` is
      no longer shown to a reader broken after its first hyphen
- [Fix] A `Next due` the observation instant has already passed reads "Was due" rather than
      stating a future-tense fact about a past one
- [Fix] The positioning line beside the wordmark completes at the 820 rung signed out, where it
      was cut to `— NO NAKED NUM` with no ellipsis to mark it
- [Fix] An out-of-scale legend row recedes without taking its served count and derivation
      handle below the contrast floor, and the browser tier's contrast audit measures every
      match and reports the worst rather than the first it finds
- [Change] Four routers read each borrowed name from the module that defines it rather than
           through another router relaying it
- [New] Texas is resident with production, and it arrives at the grain the regulator files
      at: the RRC's PDQ lease cycles are staged, crosswalked to API-10 through the wellbore
      EWA export and promoted a calendar year at a time as rows the lease owns, with
      `rows_read`, `rows_built`, `rows_appended`, `rows_excluded_out_of_scope` and
      `rows_quarantined` reported per year, and a later filing appended as a restatement
      rather than applied over the first one
- [New] Every well-level Texas figure is an allocated share and says so: `cr_tx_allocation_v0_1`
      splits each lease-month among the wells eligible in that month, conserves the lease
      total exactly, and each share is served, charted and labelled as allocated beside the
      number of wells it was divided among and a handle that resolves to the lease row the
      split was taken from
- [New] `/v1/validators/allocation` publishes the three residual ledgers an allocation owes
      about itself -- conservation, crosswalk coverage and the error band -- each with its
      outcome, the rule it was measured under and its reasons, and `not_available` with a
      reason rather than a figure wherever the ledger holds another jurisdiction's rows
- [New] The allocation's error band is measured where both grains are published: Montana files
      lease and well volumes for the same months, so the same split is scored there under
      `cr_alloc_v0_error_bounds_1` and the band stays `not_measured` on any jurisdiction the
      study has not been run on rather than borrowing Montana's
- [New] Between deploy and the end of the manual load, a Texas well card says production is
      pending allocation and names both the registered grain decision and the rule that will
      close it, rather than drawing an empty chart over a lease that has filed every month
- [New] `docs/runbook-tx-load.md`: the PDQ fetch, the year-at-a-time load, the mart refreshes,
      and what each step's counts must say before the next one is run
- [Change] A Texas cumulative carries the allocated share beside the total and a coverage
           block saying how many of its months are allocated, under which model run, and how
           many were observed; a jurisdiction whose mart the last refresh skipped is told that,
           rather than told it is outside the mart's scope
- [Change] `?as_of=` is refused on the allocated series, with the rule that says why: the
           allocation is one snapshot per key, so a figure served under an earlier knowledge
           cut would be this run's arithmetic wearing an older date
- [Change] Texas's three scheduled jobs -- the PDQ ingest, the allocation mart and the
           back-test -- observe: each tick records what it would have run and starts nothing
- [Change] Texas is corrected by appending a registration rather than by editing the one that
           was wrong: the founding row saying Texas publishes no well-level production still
           answers under its own knowledge cut, and the successor carries the grain decision
           and the cumulative scope that admit an allocated figure

<a id="v0.79"></a>
## v0.79 — 2026-09-03

- [Fix] install.sh writes the pg_ident include as a bare filename; an HBA or ident include
      takes no quotes, and PostgreSQL read the quoted postgresql.conf form as a name with
      quotes in it, so the usermap loaded empty and every peer login but postgres was
      refused on a host that had taken the map; a re-run now corrects a host that received
      the quoted line, and the unit test asserts the name resolves rather than pinning the
      string install.sh happens to write

<a id="v0.78"></a>
## v0.78 — 2026-09-03

- [New] The schedule is data: `lineage.{refusal_codes, scheduled_jobs, job_sources,
      job_schedules, job_dependencies, job_runs}`, append-only and on two clocks, with a
      `cr_job_cadence_*` conformance rule and published evidence behind every cadence
- [New] `glasswell-scheduler` on an hourly timer, running as root and dropping per transient
      unit to a CHECK-constrained uid; it resolves the registry, computes what is due from the
      freshness rule `/v1/health` reads, orders by dependency, reconciles on `ActiveState`,
      holds a per-job advisory lock and defers what will not fit the tick budget
- [New] v0.78 ships observing: every seeded row records what it would have run and launches
      nothing, while the guard that survives the flip is the narrower one that no `launch` row
      may name an entry point an installed timer already drives
- [New] `/v1/schedules` and `/v1/schedules/{job_id}`, `as_of`-aware over both clocks, serving
      each job's sources, dependencies, cadence rule, recent runs and refusal vocabulary
- [New] `marts.counts` gets a `main` and a registered daily cadence, so the jurisdiction
      well-count ledger has a writer to turn on; like every row this release seeds it observes,
      so the ledger still advances only when someone runs it
- [Change] `/v1/status` generates its job rows from the registry instead of six literal
           blocks, and carries each job's kind, jurisdiction, cadence, next due, duration,
           last outcome, the reason a failed run recorded, and refusal class with its
           severity
- [Change] The Status page splits scheduled work into data jobs grouped by jurisdiction behind
           a disclosure and platform jobs below them, opening any group that holds a fault
- [Change] `--dsn` is optional on `glasswell.marts.counts` with the `GLASSWELL_DSN` /
           `DATABASE_URL` fallback the API and collector already use
- [Change] `deploy.sh` installs the tree's Caddyfile and reloads caddy when it differs, which
           `install.sh` only ever did under `--with-caddy`
- [Fix] The two EIA boundary sources had no poll policy at all, so freshness served them
      `cadence: null` and `pending` forever; the guard that should have caught it was blind
      twice over, missing two seed registries and unable to see a one-row insert
- [Fix] Three sources carried a null poll interval that made their jobs permanently not due
- [Fix] The jurisdiction repoint guard asserted its literals were present only while the tag
      was still UNRELEASED, so the correct repoint turned it red
- [New] Colorado is resident, and it arrived as a registration rather than as a project: one
      `lineage.jurisdictions` row with prefix `05`, thirteen `jurisdiction_rules` decisions
      and twenty-two conformance rules with published ECMC evidence, and no edit to
      `api/routers/wells.py`, `facets.py`, the legend census constants or the status collector
- [New] `cr_co_wells_status_vocab_1` maps the thirteen published ECMC Well Status codes:
      eleven to a canonical class and `SO` and `UN` to `documented_unmapped`, resolved at read
      time from `lineage.co_facility_status_map` through the registry-driven resolver, which
      the rule's own spec hands the table and the two columns to read. The shapefile's in-band
      legend is the stale one, and the rule says which of the three published legends governs
- [New] `cr_co_wells_location_qualifier_1` and `canonical.well_spatial.location_qualifier`:
      how good a coordinate is, on the row that holds the coordinate and on a separate axis
      from `geometry_provenance`. 44.67% of Colorado's served points are permit locations
      rather than surveys, 27,976 of them on wells that carry a spud date
- [New] Colorado production at completion grain with North Dakota's dual write beside it: one
      row per completion plus one `sum_over_pools` well row per month and stream, so
      `/v1/wells/{api10}/production` renders and a reader can tell a two-completion month from
      a one-completion one. Liquid means oil plus condensate, because ECMC files one liquid
      stream and no condensate column exists
- [New] `marts.co_wells_tile` and the `co_wells` layer, from a `MartProfile` row in the
      parameterised engine. There is no `marts/co_wells.py`: Colorado is the first state added
      without a module of its own
- [New] Colorado's six jobs are `scheduled_jobs` rows seeded `launch_mode = 'launch'`, so the
      scheduler runs the first load in dependency order. It installs no systemd unit, which is
      what makes launching admissible: nothing an installed timer drives shares an entry point
- [Change] The cumulative mart's population is a `cumulatives_scope` registry dimension rather
           than a tuple in `marts/cumulatives.py`; North Dakota and Colorado each carry a row
           naming the rule that decides whether they write a well-grain row at all. The mart's
           derivation address moves from `states 33` to `states 05,33`, because a total over a
           different population is a different figure; North Dakota's own totals are unchanged
- [Change] The scheduler's launch gate asserts the invariant it was standing in for rather
           than the posture: no launching row carries a legacy unit or shares an entry point
           with an installed timer, and something must launch for the gate to pass at all
- [Change] The legend note's per-registration sentences are scoped to the jurisdictions the
           view was classed by, and sit above the symbology clauses rather than after them, so
           a basin's decoding rule is neither stated over a viewport that draws none of it nor
           left below the note's own fold
- [Fix] `test_no_other_states_letters_are_resolved_through_the_new_mexico_map` asserted the
      read-time resolver answered for one jurisdiction, which a second read-time jurisdiction
      would have reddened without any defect; it now asserts each codebook reaches only its own
      registered prefix
- [New] `/v1/wells/facets` counts across a set of jurisdictions: repeat `state`,
      comma-separate the codes, or send `all` for every registered jurisdiction the
      spine carries wells for, resolved from the registry at request time
- [New] `/v1/wells/facets` serves `jurisdictions`: the set the counts were taken
      over, each one's wells, and whether it carries the dimension, reports none of
      it under a registered rule, or reports none with nothing registered (R8)
- [New] the Wells-by panel offers `All jurisdictions` and takes several at once on
      Explore and on the map sheet; `wb.state` carries `all` or a comma list, and a
      jurisdiction that reports nothing at all is named under the ranking with its
      wells and the rule that took them out of the "not reported" bucket
- [Change] `/v1/wells` accepts the same `state` set grammar, so a facet bucket link
         narrows the collection to exactly the jurisdictions the bucket was counted
         over; a single code behaves as it did, and the page cursor is fingerprinted
         over the normalised set so two spellings of one scope are one traversal
- [Change] the facet scope is deduped per (state_code, api10), the order
         `wells_facet_dimensions_idx` answers index-only over a set: measured on the
         deployed 585,864 wells at 12,780 buffers and 592 ms against 279,288 and
         1,031 ms for the api10-only partition (web/PERF.md §7)
- [Fix] a jurisdiction contributing no well to the scope is served as
      `no_wells_in_scope` rather than `absent_by_rule`: under an `as_of` before its
      promotion the emptiness is the knowledge cut's, and blaming a conformance rule
      for it is a claim with no row behind it
- [Fix] a status map whose reported-code column repeats is refused at the registration
      that introduces it, naming the rule and the table; left to the refresh it aborted
      every later append to the registry from inside a statement trigger, naming a
      primary key instead of its cause
- [New] `/v1/status` carries a `status_resolver` check and `infra/verify.sh` asserts
      that every jurisdiction registered for read-time status resolution has resolver
      rows; a registered mapping table that has not landed is skipped with a notice
      instead of silently drawing that jurisdiction's spine unmapped
- [Change] `canonical.status_resolution` is registry-driven: it resolves every
         jurisdiction whose status-vocabulary rule says `resolved_at: read_time`,
         reading the mapping table and its key and value columns out of that rule's own
         spec, so a later jurisdiction registers rows rather than redefining the view
- [Change] `wells_facet_dimensions_idx` carries `status_reported`, and
         `canonical.status_resolution` is backed by a relation keyed on (state, reported
         code) rather than a view; the status facet over a set of states goes from an index
         scan with a heap visit per row to an index-only scan with a keyed resolver lookup,
         measured at 809,191 rows as 32,598 buffers and 1,285 ms against 12,484 and 818 ms.
         The index is rebuilt in place, so deploying this train holds a brief exclusive lock
         on the well spine at migrate time; the migration bounds it at five seconds and
         RELEASING.md says not to deploy inside the backup window
- [New] One tile-mart engine: `marts/wells.py` refreshes any registered jurisdiction from a
      `MartProfile` row and its registration, and `glasswell-tiles --jurisdiction <CODE>` is
      its entry point; the four per-state modules stay as shims because two applied
      migrations name them by module path and the deployed timer executes a third. Every ND,
      TX, NM and MT derivation id and tile digest is byte-identical before and after, proved
      by `scripts/mart-address-diff.sh` running both checkouts against one database
- [New] Seven presentation columns on `lineage.jurisdictions` and a `wells-roster.json` the
      generator emits beside the client module, so the map's Wells rows, their style layers,
      their draw order and their subtitles are registrations rather than object literals
- [New] `basin_scope`, `length_source` and `neighbors_scope` as `jurisdiction_rules`
      decisions, with `cr_nd_basin_scope_1`, `cr_tx_basin_scope_1`, `cr_nd_length_source_1`,
      `cr_tx_length_source_1`, `cr_nd_neighbors_scope_1` and `cr_mt_neighbors_scope_1`
- [Fix] `/v1/wells/{api10}/completions` served a `lateral_length_ft` for Montana wells with a
      FracFocus disclosure, computed under `cr_nd_compute_crs` because the endpoint called the
      length resolver unconditionally and the Montana mart stores its paths as laterals; the
      figure is now null with `cr_mt_paths_length_scope_2` cited, which is what that rule's
      contract note has always claimed. Any served intensity for such a well changes with it
- [Fix] A jurisdiction with no registered basin was served a length method and a compute CRS
      resolved from North Dakota's rule on both `/v1/wells/{api10}` and `/completions`; an
      unregistered length rule is a 200 with a null and a `length_scope_unregistered` reason
- [Fix] The glossary client read one page of 200 terms and declared itself loaded, so a
      vocabulary past that cap would have rendered "Definition loading…" for the life of the
      page; it pages to the end of what the server serves, treating an absent `next_cursor` as
      the last page, and refuses a cursor that offers another page and returns nothing new,
      naming the count it had read
- [Fix] A jurisdiction registered as carrying laterals outside the neighbour mart's measured
      domain aborted the whole monthly refresh naming another state's well; it is excluded
      with a reason the well card and `/v1/jurisdictions` both report
- [Change] `cr_mt_paths_length_scope_2` supersedes `_1`, dropping the sentence that described
           the North Dakota length default this release removes; `_1` stays served and
           historical
- [Change] Every bore line is declared under every wellhead dot rather than interleaved per
           jurisdiction, so a lateral stroke no longer bisects the dot it belongs to in the
           Permian; the disposal ring keeps its place over the dots and moves under North
           Dakota's plugged strike. Pinned by an order assertion, which nothing had
- [Change] The add-a-state gate gains two narrow regex arms and a registered-code arm, and
           carries exactly eight named exemptions; `selector_registry.py`, `status.ts`,
           `style.ts` and `click-router.ts` derive from the registry rather than naming
           jurisdictions
- [Fix] The scheduler's double-run guard reported a DSN psycopg could not parse as a
      double-run hazard rather than as a check that never ran, because it caught
      `psycopg.OperationalError` where a malformed connection string raises
      `psycopg.ProgrammingError`
- [Fix] A Colorado production row the promotion quarantined recorded every staged SQL null in
      `lineage.quarantine_rows.row_payload` as the four characters `None`, so a blank the
      regulator filed could not be told from a column filed with that text
- [Change] The `cursor_query_mismatch` refusal says what to do when the filter a reader did not
           change is `?state=all` and a jurisdiction registered mid-traversal

<a id="v0.77"></a>
## v0.77 — 2026-09-02

- [Fix] `/v1/jurisdictions` serves the wells whose regulator filed no status as their own
      class, `unmapped`, instead of summing them into the jurisdiction total and dropping
      them from the rows served beside it: Texas served 359,421 against class rows summing
      291,235, so 68,186 wells were inside the total and inside no class
- [Fix] map: the legend keeps a status class the served census carries no measurement for,
      with its label, its count and its filter switch, and hides only a class measured at
      zero everywhere; over Texas the absence class was populated and hidden, so 56,423
      wells in view at 1600 were painted in a colour the key did not name and could not be
      switched off. The hide is the render's rather than a one-shot pass, and a class the
      census does not carry is marked unmeasured rather than read as a measured zero
- [Fix] map: the `Wells` family rows state the well count `/v1/jurisdictions` served, with
      the handle that resolves it, in place of the compiled literals three of the four rows
      carried — Texas 355,463, New Mexico 141,778 and Montana 42,026 against a registry
      serving 359,421, 142,000 and 40,626 — and state no number at all until one arrives
- [Change] The count writer measures every class the registered status vocabularies name, for
           every registered jurisdiction, so a class no well carries is a measured zero rather
           than an absent row; the vocabulary is read off the `vocab_map` rules themselves, and
           the legend hides a class measured at zero everywhere while listing an unmeasured one
- [New] `python -m glasswell.marts.counts --dsn ...` appends a jurisdiction well-count
      measurement, the command the add-a-state runbook has named since step 11 and the
      module never carried; `--codes ND,TX` narrows it and refuses a code no registration
      carries by name. It takes no `--measured-on`: the ledger's date is the day the
      measurement was taken
- [Fix] chrome: the Sign-out, Help and theme controls carry their own accessible name, so the
      compact rail's `display: none` on their label span below 901 px no longer leaves them
      unnamed — at 820 and 390 the Sign-out button had no text in the accessibility tree and
      its runtime title, "Signed in as <account>", would have been announced as its name

<a id="v0.76"></a>
## v0.76 — 2026-09-02

- [New] `GET /v1/sessions` lists every session the deployment holds a row for, owner-only and
      newest first, with the account, the role, the state against both windows, a coarse client
      label and an `address_class` of `lan`, `remote` or `unknown`. The address itself is not
      served: no ruling permits a client address in a body, so the row carries the class the
      screen actually reads and nothing more
- [New] `DELETE /v1/sessions/{session_id}` ends a session server-side. The owner may revoke any
      session; anyone else may revoke the one they are calling with, decided before any read so
      the route is not an existence oracle. Revoking twice answers the same record and writes
      one `session.ended`, because the event follows the rowcount rather than the request
- [New] `PATCH /v1/users/{user_id}` gains `state`, whose only accepted value is `active`.
      Disabling stays on `DELETE /v1/users/{user_id}`, which carries the owner floor and revokes
      the account's sessions; re-enabling an account that is already active is refused with
      `not_disabled` rather than answered silently, because the list that said otherwise is
      stale. The enable clears `disabled_at` and `disabled_by` together
- [New] `POST /v1/users` and `POST /v1/users/{user_id}/password` mint a password when the caller
      supplies none and return it once, on a `CreatedUser` model those two operations alone
      serve, with a `password_shown_once` warning. `UserModel` declares no password and a
      contract test keeps it that way — `/v1` is frozen additive, so a field published on the
      list schema is published for good
- [New] Migration `074_session_user_agent_family.sql` adds `lineage.sessions.user_agent_family`,
      written at login from the user-agent header, and a `(created_at desc, session_id desc)`
      index the newest-first list orders on. The stored fingerprint is one-way, so the label
      cannot be recovered at read time; rows created before the column are served as `unknown`
- [New] The users list carries `sessions_live`, counted against the injected clock rather than
      SQL `now()`, with its exemption reason stated in `non_figure_allowlist.yml` and beside the
      property in the served document
- [New] `session`, `role`, `owner` and `viewer` are seeded as glossary terms, all four
      `highlightable: false`: the highlighter compiles one app-wide regex over every served
      term, and four common words would gain underlines on every screen from a seed edit
- [Change] `new_password` joins the refused query parameters and is deleted by both Caddy log
           blocks, and the access-log filter now matches a credential-shaped parameter *inside*
           an identifier — `\b` before a bare `password` never fired on `new_password=`, because
           `_` is a word character. `monkey=` is redacted as collateral, which is the safe
           direction: a redacted log value is recoverable from the request, a leaked credential
           is not
- [Change] The two owner routes that hash a password charge a distinct `admin_write` rate bucket
           as their first statement, before the Argon2id call, rather than riding the 120/min
           interactive bucket a session already holds
- [Fix] The last-owner refusal names the field the caller sent: the pointer is a parameter of
      the guard, so the `DELETE` path — which has no body — no longer points at `/role`, a field
      that request never carried
- [New] Accounts is a section of the Status surface for an owner and for nobody else, at
      `?view=status#accounts`: the users list with role, creation, last sign-in and live
      sessions; add a user; reset a password; disable and re-enable; and the session list with
      a revoke. It is a section rather than a fourth header mode because the mode switch spends
      373 of the 390 px a phone has and a fourth button needs 46 more than exist
- [New] A minted password is rendered once, from the response that minted it, beside the
      server's own `password_shown_once` warning and behind a `data-gw-secret` hook a
      screenshot harness substitutes before it captures. It is never put in a URL, never sent
      back, and leaves the document entirely when the panel is dismissed
- [New] Disabling, resetting and revoking each open an inline `role="alertdialog"` naming what
      ends, and send nothing until the reader confirms; re-enabling asks nothing, because
      nothing ends. Every refusal renders the server's own `detail`, with the fields it named
      only when it named some
- [Change] `client.ts` gains `listUsers`, `createUser`, `updateUser`, `enableUser`,
           `disableUser`, `resetPassword`, `listSessions` and `revokeSession` over a private
           `mutateEnvelope`, which returns the whole envelope so a write can carry a warning;
           `mutate` is now that function unwrapped, so the one-shot CSRF re-challenge stays in
           one place. `main.ts` passes the role it already resolved into the Status surface
           rather than letting a second probe answer the same question
- [New] `tests/e2e/accounts.mjs` runs the DIR-11 ladder at 1600, 1024 and 390 against a
      branch-local instance and, in the same pass, the round trip the section exists for: an
      owner creates a viewer, that viewer signs in, and the surface tells them nothing about
      anyone else. No shot is taken while the panel holds a live value — the minted password is
      registered as a secret before it is read and substituted before capture — and the gate
      disables every account it created and replaces the seeded owner's password with one the
      server minted and nobody read
- [New] `registerSecret()` in the e2e library: a credential a gate reads out of the page is
      redacted from the journal and refused in a target url and in argv, exactly as the owner
      key is. `tests/support/serve_seed_accounts.py` is the throwaway owner the gate signs in as
- [Fix] `serve_branch.py` mints a `GLASSWELL_CSRF_KEY` per run. Without one every CSRF mint
      raised and the login screen answered 500, so a branch instance could serve every
      key-authenticated surface and none of the session ones
- [Change] The Accounts tables keep one line per row and their action buttons on one line, so a
           timestamp no longer doubles every row's height at 1024 and the two controls no longer
           stack; both tables scroll horizontally below their width, as the tables beside them
           on this page already do
- [Change] STATUS.md's Deployed table is re-measured read-only against VM 111 and the
      tree on 2026-09-02 · code version `v0.75+2189262`, schema head `072`, `main` at
      `2189262` level with `origin/main` and 56 version tags, agreeing at last with the
      release line above it; CI is green at `2189262` (PR #47) and `infra/verify.sh` and
      `scripts/smoke.sh` read 197 passed / 0 failed and 31 passed / 0 failed at the v0.75
      deploy rather than 194/194 and 26/26 at v0.72; the P3 entry gate carries the date
      its neighbours carry
- [New] STATUS.md gains a seventh open item: cumulative production is North Dakota only,
      `marts/cumulatives.py:64` pinning `STATE_API_PREFIXES = ("33",)` so 43,817 of
      585,864 wells carry a cumulative, routed to H2 (v0.77)
- [Fix] llms.txt records New Mexico as resident with its header, API-10 and production
      counts and Montana as resident on both production grains with tiles and well paths,
      and its deployment paragraph is re-derived against v0.75 at `2189262`, schema head
      072, 197 host checks and 31 smoke checks, in place of a v0.60 paragraph pinning
      schema 52 that named Montana nowhere
- [Change] ROADMAP.md stops contradicting itself on Colorado: the state-expansion section
         records that Colorado and Wyoming open the Rockies rather than extending the
         Williston, the deferral covers additional basins beyond the Rockies sequence
         named under Horizon H2, and H2 is re-themed so v0.77 is state #5 as a
         registration, v0.79 is status truth for N states and v0.80 carries an em-dash
         lint, a media arm below 520 px and DOM-count budgets; H3 sequences the
         `/v1/wells` spine rewrite ahead of P3 modeling; open question 14 is closed by
         `cr_nd_vintage_cohort_1`
- [New] blueprint.md carries four states and the registry: the `[as-built]` four-state
      paragraph and §3.0.1a are promoted verbatim from `blueprint-v0.6-draft.md` into the
      committed contract, the status line reads four states deployed and serving, and
      §2.3's deferral brings the Rockies sequence · Colorado, Utah and Wyoming · into
      scope under the registry with each state's reachability evidence and named risk
- [Change] blueprint-v0.6-draft.md is cut to v0.6-rc6 with the §0 row for the four-state,
         registry and session-login wave; §3.4.1 gains `lineage.jurisdiction_codes`,
         `jurisdictions`, `jurisdiction_rules` and `jurisdiction_well_counts` from
         migration `073_jurisdictions.sql` under their two clocks; §3.6.12 gains
         `GET /v1/jurisdictions`, the `/v1/users` administration set and `GET` and
         `DELETE /v1/sessions`; and C26 is amended to the four-table scheduler v0.77
         builds, retiring the single `jobs` table that exists in no migration
- [New] blueprints/SB-04-api-agent-gateway.md §3.6 lists the six registry and account
      routes with their auth class, keyed for jurisdictions and owner-only for every user
      and session operation
- [Fix] ARCHITECTURE.md's wellbore-policy citation resolves to `blueprint.md` §3.0.5 and
      §3.0.1a rather than to the draft, with the per-basin revisit trigger attributed to
      `blueprint-v0.6-draft.md` as a `[D]` item pending the §11 review
- [Fix] .gitattributes names SB-01..08, since SB-08 exists and specs against the draft
- [New] `lineage.jurisdictions`, `lineage.jurisdiction_rules` and
      `lineage.jurisdiction_well_counts` (migration `072_jurisdictions.sql`) record which
      regulators glasswell serves, on whose authority and under which conformance rules — R8's
      "a mapping that exists only in code fails review" applied to the four API-10 prefixes the
      serving path has been keyed on since migration 009. Registrations are append-only under
      two clocks, so superseding a decision is a later `effective_from` and correcting what was
      published about it is a later `published_at` at the same one;
      `lineage.jurisdictions_as_of(knowledge_as_of, valid_as_of)` resolves the pair. There is no
      current-state view: `as_of` is a knowledge-time cut, which a static view cannot honour
- [New] North Dakota, Texas, New Mexico and Montana register with their regulator, identity
      prefix and pattern, complete source list, liquids basis, wells tile layer, map colour and
      capability flags, and with one row per mapping decision — Montana carrying both its
      well-grain and its PRU lease-grain inventory rules, exactly one of them serving. The rows
      ship in the migration and in `glasswell.seed.jurisdictions`, which `seed_all` runs on
      every deploy, and `tests/contract/test_jurisdiction_parity.py` holds the two copies to
      each other and refuses a prefix that resolves to two jurisdictions, a registration missing
      the rule rows it declares, or a `source_ids` array that has stopped being complete
- [New] `load_jurisdictions` reads the registry at a knowledge and a valid instant and refuses
      an empty one with `JurisdictionRegistryError` instead of returning an empty map — R8's
      rule that a missing row is a refusal, never an assumed default
- [Change] `scripts/release.py` scans `src/glasswell/seed/jurisdictions.py` beside the
           migrations for placeholder publication evidence, in both quote styles, so a repoint
           that edits the migration and forgets its mirror is refused at `make release-check`
           rather than landing a permanent false claim about when the rows were published
- [Change] `/v1/wells`, `/v1/wells/{api10}`, `/v1/wells/status-summary`, `/v1/wells/facets`
           and both production routes read the jurisdiction registry instead of the nine
           per-state maps they carried between them. `STATUS_VOCABULARY_RULES`,
           `PROVENANCE_RULES`, `DEFAULT_PROVENANCE_RULE`, `LENGTH_SCOPE_RULES` and
           `NEIGHBOR_STATE_CODES` in `wells.py`, `LIQUIDS_RULES`, `LIQUIDS_BASIS` and
           `ROLLUP_RULES` in `production.py`, and `STATE_NAMES` and `ABSENCE_RULES` in
           `facets.py` are deleted; the three modules now carry no two-digit state literal at
           all except the one `/v1/wells/facets` needs in its own request example. A fifth
           jurisdiction is a row in `lineage.jurisdictions`, not an edit to three routers
- [Change] Texas no longer cites `cr_nd_geometry_provenance_1`. It inherited a rule about
           *North Dakota* geometry through a module-level default; it registers no
           geometry-provenance decision, so the surface serves none and says so. Authoring a
           real Texas rule is separate R8 work
- [New] `absence:operator` is a registered decision at (jurisdiction, dimension) grain, so the
      second dimension whose absence gets a rule is a row rather than another key in a
      tuple-keyed map; an unregistered dimension still counts its bucket and claims nothing
      further about it
- [New] `GET /v1/jurisdictions` serves the registry: for each jurisdiction the regulator and
      the address it publishes at, the identity scheme and prefix its wells are keyed by, every
      conformance rule registered for it with which one serves, the liquids basis, the tile
      layer and colour it is drawn with, what is built for it, and the wells last measured in
      it. `as_of` is the registry's own knowledge cut, so a correction published after it is
      not served under it and a cut before the first registration is refused rather than
      answered with an empty page. Not `/v1/states`: `state` is already a lifecycle value and
      a frozen query parameter meaning the API prefix, and a province is not a state
- [New] Every well count on that route is a figure with a handle that resolves through
      `?explain=true` to the government file the wells were promoted from, and a jurisdiction
      with no measurement yet serves no count at all rather than a zero — "not measured" and
      "no wells" are different facts. `Jurisdiction`, `Regulator` and `Identity scheme` are
      glossary terms, and the identity prefix is the one number on the route exempted from
      carrying a handle, because it is an identifier's prefix and says so in both places
- [Change] The Status page's jurisdiction arms are generated from the registry. Sixteen
           literals decided the wells arms and ten more the completions arms, and the
           completions query still carried the `left(api10, 2) = '<literal>'` filtered
           aggregate migration 069 took out of the production arm; all of it is one grouped
           read and one comprehension now. A fifth registration yields a fifth wells dataset
           and a fifth completions dataset with no edit, and an arm whose table holds nothing
           reports `unavailable` rather than a zero — "not loaded" and "none" are different
           facts, which is the guarantee the omitted Montana completions arm used to make by
           being absent
- [New] `marts/counts.py` appends the jurisdiction well-count ledger `/v1/jurisdictions`
      serves: one measurement per registered jurisdiction, by canonical status and in total,
      under the derivation that produced it. The total is the sum of the classes it is served
      beside rather than a second `count(*)`, and the class is read from the same resolver the
      map draws with, so the ledger cannot disagree with the canvas about a well
- [Change] `land_metrics.py`'s two grid-prefix tuples and `neighbors.py`'s `STATE_CODES` read
           the registry at import. The two land-grid names stay separately named and separately
           sourced — each reads its own column — because collapsing them would silence the
           anomaly alarm one of them exists to raise
- [Change] map: the `Wells` family, its four jurisdiction rows and the status vocabulary rules
           the legend prints take their names, swatch colours, tile layers and rule ids from
           `jurisdictions.generated.ts`, rendered from the registry seed by
           `make jurisdictions`. The rows stay literal — `tests/e2e/chrome-fold.mjs` parses the
           file as text — and only the values inside them are imported
- [Remove] map: `MEASURED_WELL_COUNTS`, `MEASURED_TX_WELL_COUNTS`, `MEASURED_NM_WELL_COUNTS`,
           `MEASURED_MT_WELL_COUNTS` and `measuredWellCount`. Four count tables read by hand
           against the deployed database and compiled into the bundle with no date on them; a
           legend built from those claimed whatever somebody last measured. The census comes
           from `/v1/jurisdictions` now, fetched off the entry path, and a class is hidden only
           on an explicit measured zero — an unknown or degraded census hides nothing
- [New] `tests/unit/test_add_a_state.py` refuses a two-digit API prefix or a jurisdiction's
      name anywhere the serving path reads: `marts/`, `api/routers/`, `status/`, `lineage/`,
      every migration written after the registry, and `web/src` with comments stripped. The
      rule is positive and keyword-free, which is the point — an earlier form gated on a
      trigger word and seventeen of the nineteen literals it existed to catch sat in dict
      bodies with no such word on the line. Six exemptions, each with its reason in the file
      and each proved load-bearing by a test that removes it and expects the scan to speak
- [New] `docs/runbook-add-a-state.md`: eleven steps from registering the source to running the
      count writer, each naming the refusal that stops it being done out of order — and naming
      the one step, the ingest timer, that still has no gate behind it
- [New] `lineage.jurisdictions.explorer_default` decides which jurisdiction the Explorer opens
      on. It was a code choice — first a literal `"33"`, then whichever registration sorted
      first, which is Montana and an accident of alphabetisation. Exactly one registration
      carries the flag and its rationale says why: the only jurisdiction serving well-grain
      production history end to end. A partial unique index holds it to one per registration
      instant and a standing gate holds it to exactly one across the resolved set, because two
      registrations a day apart both resolve and no index can see that
- [Change] Which jurisdictions resolve their well status at read time, and under which rule,
           is read off `lineage.jurisdiction_rules` rather than pinned in a dict. New Mexico
           was `{"30": "cr_nm_wellhistory_status_vocab_2"}` in `status_resolution.py`, a module
           at the package root that no scan looked at; the add-a-state gate now scans there
           too. `canonical.status_resolution` stays one canonical-layer view the tile mart and
           every serving path read, and takes its API prefix from the registration instead of a
           literal — a fifth state with read-time resolution still brings its own codebook, but
           whether it resolves that way is a row

<a id="v0.75"></a>
## v0.75 — 2026-09-01

- [New] map, status: the map key, the layers panel and the Status page underline the
      glossary's words and answer a hover with the definition — the three densest pages
      of vocabulary in the product, and the only surfaces `gw-term` had never been wired
      into. Controls carry `data-no-glossary`, because a term inside a button swallows
      the click that was the control's and hover already teaches
- [New] glossary: nineteen seed rows the product surfaced but could not define — Basemap,
      Cadence, Declared vintage, Disposal well, Geometry provenance, Lateral, Lineage,
      Play, Producing class, Retrieval vintage, Schema head, Section (PLSS), Station
      survey, Status snapshot, Timer, Township, Viewport, Vocabulary rule and Well type
      — each citing the blueprint section, conformance rule or mart that decides it;
      "Producing" and "section" are reachable by click and never auto-scanned
- [New] glossary: a coverage gate that renders all three surfaces against the committed
      seed and fails on a term a surface names but cannot define, plus its API-side half,
      which resolves every `gt_*` id the frontend binds by hand
- [New] glossary: a parity gate over the table's two writers. The seeder upserts, so for a
      term the seed carries its text is what survives the next run and a migration writing
      the same term is either identical to it or silently dead; the gate reads every
      glossary write in the migrations, reddens on a disagreement, and reddens again on a
      write shape it cannot decode
- [Fix] map: every drawn layer row resolves its own build handle off the tile that drew
      it; `land-grid`, `spacing-units`, `survey-traces`, the Montana rows, `basins` and
      `plays` all showed an unresolved ⌾, and each wells row was given the first handle
      on the whole canvas rather than its own state's
- [Fix] status: a state pill's wording survives the highlighter. The pill is inline-flex,
      so splitting "Current snapshot" around a term dropped the space between the halves
- [Fix] glossary: a term is no longer underlined inside a dotted identifier such as
      `marts.nm_wells_tile`; one ending a sentence is untouched
- [Change] the glossary seeder upserts on the term id, so a corrected definition, an
           extended alias list, new evidence or a changed `highlightable` reaches the
           reader on the next seed run; it inserted with `on conflict do nothing` and left
           the correction sitting in the file. `effective_from` is not re-dated
- [Change] the em-dash leaves the copy the app speaks: twenty-one prose dashes in card,
           explore and map string literals become a colon, a sentence break or the house
           middot as each reads best, and two legend notes are reworded rather than
           repunctuated; no hyphen stands in for a dash. The seven that remain are the
           absent-value glyph, a data mark rather than punctuation
- [Fix] ARCHITECTURE.md: the wellbore-quarantine revisit trigger reads per basin, 2% in
      North Dakota and 5% in the Permian, and the detection clause names what each
      regulator publishes rather than the W-2 count that measures completions, not bores
- [New] GET /v1/wells/{api10}/cumulatives: per-well cumulative oil, gas and water,
      each a figure carrying its unit, its liquids basis and the mart snapshot
      vintage it was built at, beside four month counts per stream that reconcile
      to the span; reported, reported_zero, no_report and withheld stay four
      distinct served facts and only the first two enter a total
- [New] a well that has never filed anything is served with a null cumulative and
      coverage_outcome never_reported rather than a zero or a 404, and a well
      outside the mart's states is refused by name rather than served an empty
      total that would read as no production
- [New] a cumulative_behind_series warning naming both vintages and the month
      count wherever canonical already holds filings the snapshot has not
      absorbed, so a reader summing the live series is not left to find the gap by
      arithmetic
- [New] GET /v1/wells/vintage-cohorts: wells, the wells whose record admits a month
      into those totals, and cumulative volumes per cohort, all three keyed by
      cr_nd_vintage_cohort_1 - which rules the support measure as well as the
      cohort key, so neither is decided in a query - on the spud year with
      its measured rationale and its rejected alternative served at
      /v1/conformance; the no-spud-date cohort is its own, never folded into a
      year, and the Montana truncation is stated inside data rather than only in a
      warning a copied payload would lose
- [New] Protocol 4D on the cohort rollup: spacing_assumption is stated as
      inapplicable with its reason, and support_distribution uses cohort-scale
      bands because the PLSS section scale puts 73 of the 94 measured ND cohorts
      in one class
- [New] canonical.well_completion_design promotes the FracFocus base water volume
      under cr_ff_base_water_units_1 and cr_ff_design_promote_1: a blank promotes
      as no_report rather than as a zero, and a non-numeric literal, a duplicate
      disclosure or a volume above the measured 50,000,000 gal bound is
      quarantined with a reason rather than dropped
- [New] fluid intensity per lateral foot on /v1/wells/{api10}/completions under
      cr_ff_fluid_intensity_1, which declares a 1,000 ft divisor floor and a 5,000
      gal/ft ceiling; no ND well has a zero summed lateral, so a divide-by-zero
      guard would fire on nothing while the measured 0.24 ft minimum would serve
      26 M gal/ft as a handled figure. An absent numerator is reported as the
      source classified it, so a withheld volume yields a withheld intensity and
      never an undisclosed one
- [New] marts.well_cumulatives and marts.well_withholding carry no state regex and
      an explicit state_code, so a second jurisdiction widens a Python constant
      rather than altering shipped DDL
- [New] glasswell-fracfocus --promote-design promotes completion design from
      staging already resident on the host with no fetch, and states its outcome
      rather than failing where the 440 MB archive has never been pulled
- [New] deploy.sh populates the cumulative marts and backfills completion design
      before verify.sh and smoke.sh run, and verify.sh asserts both marts are
      non-empty; the design check reports pending rather than failing on a host
      with no staged ND disclosures
- [Change] design_availability reads promoted. It is a statement about the
         release, not about the well: per-well absence is design null with
         design_null_semantics, which is the right grain for a per-well fact
- [Change] the per-well cumulative has one definition. marts.cumulatives owns it
         and land_metrics reads it rather than its own copy; the predicate names
         what the total admits instead of relying on a NOT NULL column's fill
         value staying zero. per_well_cumulative_cte takes the membership CTE to
         bound its scan, so the land grid keeps the restriction that stops it
         reading 24.8M rows it discards
- [Fix] the well card rejected any design_availability other than not_promoted and
      replaced the whole completion panel with 'unavailable', so promoting the
      design server-side would have removed the panel from every card
- [Change] a saved handle from a cumulative, cohort or intensity figure resolves
         through an api.respond derivation, which lineage.sweep_ephemeral_derivations
         deletes once unreferenced and older than 90 days; the same inherited
         behaviour as the existing well-detail and status-summary figures
- [Change] the N2 migration lands as 072_n2_enrich_views.sql. The track branched
         at v0.64 and main's head migration is 070; discover_migrations refuses a
         duplicate version as well as a gap
- [Change] the completion-design and fluid-intensity sections are re-expressed
         inside the well flyout's section grammar rather than the panel they were
         written against: short empty states, a scope line of dense facts, and no
         prose paragraph where the flyout carries none
- [New] the well flyout carries a cumulative row under monthly production: oil, gas
      and water as three figures, each with its own derivation handle, over a scope
      line stating the window, the months admitted and the mart snapshot; a stream
      with no admitted month reads withheld or no report and never a zero, and a
      well that never filed reads as such rather than as three zeroes
- [New] /v1/wells/{api10} links to cumulatives only where the mart holds a total, so
      a client reads the link rather than testing the API prefix itself and a
      jurisdiction outside the mart is never rendered as a well that produced nothing
- [Fix] the cumulative mart's served population is its own constant rather than a
      view of the withholding registry; registering a quarantine source for a state
      the mart does not cover no longer widens states_served, the well card's
      cumulatives link or the mart refresh
- [Fix] cr_nd_vintage_cohort_1's cohort_key_field is held to the column the executor
      actually reads, so a rule repointed at another column refuses at load rather
      than publishing a statement the served cohorts do not follow
- [Fix] /v1/wells/vintage-cohorts refuses with service_degraded naming the empty mart
      instead of serving snapshot_vintage null against a schema that requires a date;
      an empty cohort list would have read as North Dakota having none
- [Fix] verify.sh reports the withholding mart as not yet refreshed before any
      mart.refresh has run, and as empty-with-nothing-to-hold where no open
      confidential_withheld row exists, refusing only when a refresh has run and rows
      were there to hold; every branch still reports a check
- [Fix] the cumulative refresh refuses an api10 that is not ten digits rather than
      silently skipping its months, since the ordered merge compares in Python what
      Postgres ordered
- [Fix] smoke.sh asks for the New Mexico status vocabulary rule the host serves
      (cr_nm_wellhistory_status_vocab_2); v0.74 refused its own smoke on the superseded id

<a id="v0.74"></a>
## v0.74 — 2026-09-01

- [Change] The tunnel connector runs `protocol: http2` instead of the QUIC default, and
           `infra/install.sh` places `/etc/sysctl.d/99-cloudflared-udp.conf` raising
           `net.core.rmem_max`/`wmem_max` to 7.5 MB — cloudflared asks quic-go for 7 MiB and
           logged `failed to sufficiently increase receive buffer size` against the 208 kiB
           default at every start. On an uplink that drops out for tens of seconds at a
           time, QUIC's idle timeout tore the tunnel down 1,919 times in six hours and the
           edge answered 530; TCP rides the same outages without re-registering. Remove the
           `protocol` line once the link is stable
- [Change] STATUS.md is rewritten under 120 lines against read-only measurements of the
           deployed database and host taken 2026-09-01, with the three figures it carries
           forward saying so on the line; ROADMAP.md's P2, P6 and P7 rows and its N1-N3
           markers are corrected to the releases that shipped and it gains a Horizon section
           carrying the H1-H3 table the open items now point at; README.md records New
           Mexico as resident, with its status class resolved at read time
- [Change] blueprint-v0.6-draft.md scopes four resident states including Montana, registers
           jurisdiction as a layer boundary whose promotion, inventory and serving paths read
           a registry rather than an API-10 prefix, resolves well status once in a
           canonical-layer view over that registry which every serving path reads rather than
           per surface, serves a documented-but-unmappable code as a distinct class, and
           carries one version string; SB-04 3.1 is amended to the session login that shipped
           and its endpoint catalog gains /v1/states and /v1/wells/facets
- [Fix] app/router: the Map → Explore crossing narrows the wells collection by
      `api10`, the parameter that names the row, instead of by `q`, which
      `/v1/wells` accepts as a `well_name` substring and answers with nothing
      for every API-10 a reader had selected
- [New] map: Basins and Plays rows in the Geology framework group, drawn from
      `marts.basin_boundaries_tile` — the EIA lower-48 boundaries this build has
      ingested, served and allowlisted since migration 063 — with a `geology`
      line role and per-variant token so the frame is recoloured for the
      substrate under it and never reads as an administrative boundary
- [Remove] map: the `play-outline` and `geology-au` stub rows and the
           `pendingSource` vocabulary behind them; the first promised work that
           had already shipped, the second promises work nothing serves
- [Change] main: one latched session probe, awaited immediately before the map
           and explorer mounts, so a signed-out first paint no longer spends a
           403 on every tile source and the status summary behind the login
           modal; `/basemap/*` stays anonymous and the expiry suppression in
           `map.ts` is unchanged
- [New] map: a `minZoom` of 3 and a `maxBounds` holding the contiguous
      forty-eight, mainland Alaska, Canada and Mexico, so a pinch or a drag can
      no longer leave the reader over an empty world with every tile source
      still fetching
- [New] web: `test:changed` and `test:watch` scripts for the narrow loop, with
      `test` left as the full suite CI runs
- [New] `cr_nm_wellhistory_status_vocab_2` supersedes `_1` and maps the OCD well-header
      status letters to the canonical vocabulary from the regulator's own data dictionary
      (sheet "consolidated code list", sha256 `b95c45d3…`), corroborated per well against
      OCD's live `Wells_Public` layer. Ten of fourteen codes reach a canonical class; `I`,
      `J`, `Q` and `Z` — reclamation-fund and zone-plugged — carry the new registered class
      `documented_unmapped`, because forcing them into `plugged` would strike 507 wells
      through on a claim the regulator never made and collapsing them into the absence class
      would erase that it said anything. The dictionary transposes `I` and `J` against both
      live services; the services win, per well
- [New] `lineage.nm_wellhistory_status_map` and `canonical.status_resolution` (migration
      `071_nm_status_resolution.sql`) resolve the class at read time. `marts.tile_nm_wells`,
      `/v1/wells`, `/v1/wells/{api10}`, `/v1/wells/status-summary` and `/v1/wells/facets`
      all read the one view, so the map and the well card cannot answer differently about
      the same well. `canonical.wells.status_canonical` stays null for New Mexico: the table
      is append-only and a backfill would have to invent a valid time the OCD never filed
- [New] `nm-wells-struck` draws the strike over plugged New Mexico wells, which had no
      struck style layer because no New Mexico well could previously carry a terminal class
- [Change] New Mexico's 141,778 mapped wells stop painting as one unmapped swatch: 54,325
           active, 50,935 plugged, 18,161 permitted, 17,056 expired, 779 temporarily
           abandoned, 507 documented-without-an-equivalent and 15 dry. The legend census
           counts them, the map key lists them and the flyout carries the class beside the
           filed letter. `unmapped_action` is `passthrough` and not the `quarantine` North
           Dakota and Montana use, because the header table is the identity spine production
           joins to and quarantining would drop 2,211 records from it
- [New] `/v1/wells` and `/v1/wells/{api10}` serve `status_vocabulary_rule` beside the class,
      and the record links it at `/v1/conformance/{rule_id}`. New Mexico is the first state
      whose served class is decided by a rule its own row derivation does not cite — the
      promotion still cites the superseded `_1` — so without this a reader resolving the
      handle behind an NM `active` reached the rule that refuses the mapping
- [Fix] The `status` filter description and the `gt_well_status` glossary term said an
      unmapped code is always quarantined, which stopped being true when
      `cr_nm_wellhistory_status_vocab_2` registered the repository's first `passthrough`.
      Both now name the two actions and which jurisdiction chooses which, and the glossary
      enumerates `service` and `documented_unmapped`

<a id="v0.73"></a>
## v0.73 — 2026-09-01

- [Fix] `README.md` claimed 34 operations in the frozen snapshot, 33 under `/v1`; the
      snapshot holds 49 across 44 paths, 48 under `/v1`. The listing gains
      `/v1/wells/facets`, the glossary and quarantine members, the derivations, manifests
      and vintages collections, and a line naming the session, user and key write paths
- [Fix] `README.md` described the deployment as a North Dakota production slice with a
      North Dakota/Texas map. It is four states at four depths: North Dakota end to end,
      Montana with both production grains promoted, Texas geometry-only, and New Mexico's
      spine behind a closed gate
- [Fix] `README.md` carried a v0.60 paragraph stating schema head 52, 111 host checks and
      20 smoke checks, and a P3 block of coverage percentages, row counts and a
      publication id. Volatile figures now live in `STATUS.md` and the P3 docs, which the
      README defers to rather than restating
- [Change] `README.md` marks the Texas and New Mexico source rows for what is ingested
           against what is designed, lists the five console scripts it omitted
           (`glasswell-nm-wells`, `-nm-tiles`, `-basin-boundaries`, `-eia-boundaries`,
           `-owner-reset`), and points each multi-step load at its runbook
- [Fix] `assets/architecture.svg` named no Montana source or staging table though the
      state is promoted and on the map; the source band gains `MT BOGC — well · lease
      production` and the staging band re-pitches to six for `mt_bogc_* · mt_gis_*`
- [Fix] `assets/architecture.svg` named `TX RRC — PDQ lease production` in the source
      band, which is not a registered source and has no ingest module; the box now reads
      `TX RRC — GIS wells · wellbore export`, which is what Texas actually contributes
- [Fix] `README.md` described `glasswell-owner-bootstrap` as creating "the owner key"
      rotated by `glasswell-owner-reset`. Neither is a key: bootstrap creates the first
      owner *account* with a password read from stdin only, and reset is the break-glass
      path that sets a password and clears a lockout
- [Change] Well card: production leads. Identity, then the monthly series, then the fact
      bands, then completions, neighbours and notes — the chart began 975 px into a 2,180 px
      card behind two sections that are empty for most wells, and now begins at 222 px; the
      operator moved from a band of its own into the identity header
- [New] Well card draws five fields the API has always served and it never showed: API-14
      beside the API-10, the NDIC file number, the reported well type, the surface-hole
      coordinate, and the length method as a qualifier on the lateral length
- [Change] Scope statements read as chrome rather than paragraphs across the map key, the
           well card, the Wells-By panel, the grid and the facet bar: a `·`-joined summary
           line with the wording it replaces kept behind a disclosure or on the row's title,
           never dropped; new `web/src/chrome/notes.ts` is the one implementation
- [Change] API warnings render as one collapsed `<details>` per code with the count in the
           summary, the server's own detail and pointers inside, and a title derived from
           the code so a new code needs no client edit — the card printed the raw
           `code: detail (pointer)` line, 199 characters of it above the panel saying the
           same thing
- [Fix] The well card's neighbour slot states the refusal the endpoint named rather than
      "unavailable for this well or requested historical view": a 422 carrying
      `completion_anchor_required` and the parameter that would unblock it was caught and
      replaced with wording vaguer than the server's
- [Fix] The first-run lineage hint no longer covers the well name — it hangs out of the
      header into the canvas at the corner the card opens at, and at 1600 the heading was
      unreadable behind it
- [Fix] The month axis no longer shows one month as two: uPlot splits a time scale on its
      own increments, so a seven-month series across a full-width card drew "Sep 2025 Sep
      2025 Oct 2025 Oct 2025"; a repeated label is dropped, the tick under it is not
- [Change] Layer rows are one line at every breakpoint: the jurisdiction comes out of the
           noun into a scope chip against the provenance badge, so "Survey traces (North
           Dakota)" no longer wraps and makes its row 10 px taller than the one above it
- [Change] The well card loads on the first well opened rather than with the app. It was the
           largest module on the entry path since C0, so every reader — including one who
           lands on the explorer and never clicks a dot — downloaded it: the entry chunk
           falls 21,340 to 12,750 B gzipped and its budget is re-tightened to 14,000
- [Fix] Shared note chrome inside the map key and the map sheets takes panel-local greys
      rather than the theme's, which the light theme resolves to dark-on-dark; the light
      theme remains flagged off for the reasons `chrome/theme.ts` records
- [New] The map key's collapsed pill carries the count it is a key to — the population's own
      figure while nothing is filtered off, the sum of the classes left on when something is,
      and nothing at all while the counts are pending; "how many wells am I looking at" was
      the first question a map of dots raises and the only one answered by opening something
- [Change] The well flyout's column is capped at 540 px rather than a flat 460 at every
           desktop width, so the stream legend stops wrapping and the plot gets the room a
           wide display already had; 38vw still holds it under a third of the canvas, and the
           width is one token the first-run hint steps aside by
- [Fix] A warning code the server repeats with different wording keeps every wording:
      `series_spans_derivations` counts derivations per column, so one well can carry a
      different figure against oil than against gas, and rendering only the first dropped a
      served number while still listing every pointer under it
- [Fix] Opening a well guards against the card chunk landing after the reader has closed it
      or picked another, and reports a chunk that will not load instead of leaving an
      unhandled rejection and a rail that never fills

<a id="v0.72"></a>
## v0.72 — 2026-09-01

- [Fix] The auth matrix status-probes the six routes it used to skip. `POST /v1/session`,
      `POST /v1/session/password` and the four `/v1/users` mutations sat in the table for
      coverage and outside the status assertions, which is 54 of the suite's 55 skips and one
      hole: what an anonymous, invalid-key, revoked-key or expired-session caller receives
      from a user-administration route was asserted nowhere, and the four `/v1/users` rows had
      been that way since the commit that added them. All 54 answer 403, or 200 for the owner
- [New] A matrix row carries an optional request body, and the login row carries a CSRF token
      bound to a pre-session nonce, so a POST, PATCH or DELETE case can be dispatched at all.
      `NOT_STATUS_PROBED` is gone rather than shorter
- [New] test_an_anonymous_caller_is_refused_before_their_body_is_read holds the five gated
      body-taking routes to answering 403 and not 422. A validation body names the schema it
      was validated against, and an uncredentialled caller's payload is never examined; the
      test goes red when a route's gate moves out of the dependency tree into the handler
- [Change] The matrix's principals speak https, including the key classes. A `__Host-` cookie
           requires Secure, so over http the transport drops it and a key-class caller could
           never hold the pre-session CSRF cookie the login row needs
- [Change] Each POST row states its own body instead of every POST being handed the key-issue
           one. `POST /v1/keys/{key_id}/rotate` takes no body and was being sent one, and a
           body shared by rows that do not share a schema hides which row needs what
- [New] map key: wells by reported well type and by geometry provenance, two
      dimensions /v1/wells/status-summary already served and the client discarded;
      every row is a served figure with its own derivation handle, the provenance
      block states that its classes overlap and do not sum, and each block is a
      disclosure under the key's scroll body rather than inside it, so neither it
      nor the cross-reference to the other scope has to be scrolled to be found
- [New] map: a Wells by sheet beside the layer panel, counting every current well
      in one state rather than the map view and saying so on screen; each panel
      carries a one-line cross-reference to the other scope
- [New] map: pressing a bucket narrows the canvas to that value across every well
      and bore layer, including the five whose filter slot is not the status
      gate's; the applied bucket rides the URL as wb.pick, and back and forward
      move the pill, the pressed row and the canvas filter with it
- [New] map: an applied-bucket pill carrying the panel's own figure and handle,
      never a count of the canvas; it names the layers a press does not reach,
      states that the tiles keep one well per half pixel below zoom 8, and paints
      on --panel so the filter it announces is readable in either theme
- [Change] the Wells-By panel takes its applied filters, its press rule and its
         scope line from its host, so the map and the explorer render one
         component rather than two; it drops its rank and bar columns on its own
         column width rather than the window's, and states on screen rather than
         in a tooltip alone where the surface cannot be narrowed by a dimension;
         the explore surface is unchanged
- [Change] the wells dataset declares geometry_provenance as a facet, so a
         crossing onto that filter renders a chip the reader can clear
- [Change] the layer panel and the Wells by sheet share one frame declaration,
         .gw-sheet; opening either shuts the other, Escape closes whichever is
         open and hands focus back to the control that opened it, and at 768 and
         under the drawer clears the map's own control column
- [Fix] map key: the ⌾ on a producing or dimension row is a control rather than
      the key's expand target, so asking where a count came from no longer
      collapses the key and throws away the scroll position that reached it
- [Fix] map key: the rule between the key's groups is a defined token that
      follows the panel's substrate, not an undefined one falling back to a white
      that measured 1.00:1 against a light basemap's white panel
- [Fix] map key: the key is capped at the map's own height less its insets and
      lays its blocks out as a column, so opening both dimension blocks on a
      phone no longer grows it off the top of the map and under the app header —
      where a tap aimed at the title that collapses it landed on the surface
      switch and navigated the reader off the map
- [Fix] tests: the R6 naked-numbers gate classifies a figure by the value of its `d` rather than
      by the key's presence, and a handle position carrying a null or non-string value is now
      reported as an offender instead of being skipped. Serving `d: null` on every figure in
      the API left all eleven checks green, with the non-emptiness guard held up by the
      `_lineage` sidecars
- [Fix] tests: the login bound's ordering assertion counts Argon2id verifies on
      `accounts.verify_password` rather than reading the status code. Authenticate-then-limit
      and limit-then-authenticate both answer 429, so the status assertion was satisfied by a
      route that ran a full 64 MiB verify for every unauthenticated attempt and refused
      afterwards — the amplification the bound exists to stop
- [Fix] tests: the constant-time guards read the parsed module. `hmac.compare_digest` must appear
      as a call node rather than anywhere in the source text, and each `==` operand is followed
      back through the renames that bound it, so `_a, _b = presented, owner_key` no longer hides
      a variable-time comparison of the owner API key from the name allowlist
- [Fix] tests: the layer-boundary guards fold every string a module builds — concatenations and
      f-string parts alike — before searching it, so a schema name written in pieces is judged
      on the value it executes as. Applied to the feature matrix, the whole marts package, the
      Montana and New Mexico marts and the New Mexico wells GIS walk
- [Fix] tests: the producing-summary omission check is driven from the collection and asserts set
      equality, so a class the summary drops is visited rather than never iterated, and the box
      is seeded a second class so an omission has something to omit
- [Fix] tests: the `/v1/keys` at-rest scan reads every column rather than `sha256, label`, and
      names the column a cleartext key reached; the claim was "sha256 is the only representation
      at rest" while two of ten columns were looked at
- [Fix] tests: non-emptiness guards on the glossary label, conformance rationale, quarantine
      metric, stored session hash and status-bucket assertions, each of which an empty
      collection made vacuously true
- [Fix] tests: the selector registry fixtures pin `output_sha256` as a literal rather than
      computing it with the same function the implementation compares against, and a mismatched
      evidence hash is asserted to be refused
- [Fix] web: the overlay restore test asserts focus lands on the body when the restore target has
      left the document, rather than asserting a different element is still attached. `.focus()`
      on a detached element is a silent no-op, so dropping the `isConnected` guard stranded
      focus inside the panel that had just closed with all nine tests green
- [Change] The contract tier seeds its fixture once into a template database every test
           clones, rather than seeding it per test. `seed_all`, the eight wells, their
           geometry and production, the neighbour mart, the quarantine rows and the pinned
           control publication cost 0.32 s per test and land the same rows every time; the
           assertions pinning the documented example ids run in the builder, once, and still
           fail the tier when an example goes stale. Contract setup falls from 695.7 s to
           262.6 s across 1,367 tests, and the full suite from 27:40 to 18:45 on one host
- [Change] The ephemeral PostGIS container runs with fsync, synchronous_commit and
           full_page_writes off at wal_level=minimal, and `create database` clones with
           `strategy file_copy`. A server destroyed at the end of the session has nothing to
           recover, and file_copy is the faster strategy only once the checkpoints it forces
           are free: 67 ms of create-plus-drop per test against 118 ms measured on the
           defaults, over the 2,749 databases a full run builds
- [Change] The control artifact the contract tier publishes is written once per session and
           copied per test rather than rebuilt through duckdb for each one. Every path it
           records is relative, so a copy under another root is byte-identical and
           EXAMPLE_PUBLICATION_ID does not move

<a id="v0.71"></a>
## v0.71 — 2026-08-31

- [Fix] The "Wells by …" search box carries what the reader has typed across the rebuild its own
      commit causes, not their caret alone. The rebuilt box is filled from the URL, which lags
      the keyboard by a 250 ms debounce plus a round trip, so a reader typing slower than that —
      anyone recalling an operator name — lost every letter after the second and lost the box
      with them: measured on a branch instance at 300 ms a character, `energy` arrived as `en`
      with `document.activeElement` back on `BODY`, and the rest of the word went nowhere. Fast
      typing never saw it, because every keystroke landed inside one debounce window and only
      one commit ever fired. The word the reader is mid-way through now survives the rebuild,
      the caret sits where they left it, and no other control on the panel — dimension, state,
      sort, cut or a bucket press — pulls them back into the box it rebuilt
- [Fix] The "Wells by …" caption names the direction the list was ranked in. Asked for
      `sort=count&order=asc` the endpoint serves the values with the fewest wells while the
      caption read "with the most wells", beneath a button reading "lowest first" — a served
      sentence that was false about the rows next to it. A complete list now says which way it
      is ranked too, rather than only by what
- [Fix] A facet bucket's `/v1/wells` link percent-encodes the value it carries, the same
      `urlencode` the cursor links already use. Written verbatim, `DIAMONDBACK E&P LLC` ended
      the value at the ampersand and minted a stray parameter, so the published link narrowed
      to a different population than the count beside it, and the spaces made it a URL no
      agent or auditor could issue at all
- [Fix] The "Wells by …" panel renders the warnings the envelope serves, through the same
      `warningPanels` the well card and the neighbour list use. `search_scopes_the_ranking`,
      `list_truncated` and `absence_unregistered` were all served and all dropped, so under a
      search the panel's arithmetic stopped closing on screen with nothing saying why
- [Change] The absence bucket's `detail` says the search did not narrow it, names the search
           and the state, and is composed beside the count so the sentence and the figure
           cannot drift apart. Under a `q` every other figure in the response moves and this
           one stays whole-state, and the total that would have been its denominator is no
           longer on the surface
- [Fix] Clicking a facet bucket narrows the grid by every filter the server's link carries,
      the state included. The panel ignored `bucket.links` and rebuilt the filter from the
      dimension alone, so Texas county 003 narrowed to Texas and North Dakota county 003
      together — the crossing `state` was added to `/v1/wells` to stop. The link is now the
      one source of truth for what a bucket narrows to, and a bucket the collection cannot
      reproduce still renders as a plain label
- [Change] `/v1/wells` declares `well_type` a facet. The collection has always applied the
           filter, and a well-type bucket set it, but a filter the dataset does not declare
           renders no chip and cannot be cleared on its own
- [Fix] The "Wells by …" search keeps focus and the caret across the re-render its own
      keystroke causes. Every debounced commit rebuilt the explorer and destroyed the focused
      input, so any pause longer than 250 ms dropped the reader out of the box mid-word
- [Change] A search commits with `replaceState` rather than `pushState`, on the convention the
           viewport already follows — a seven-character search cost seven back presses.
           Changing the dimension, the state, the ranking or its direction still pushes
- [New] The "Wells by …" panel offers the cut as a control — 10, 15, 20, 25 or 50 — writing
      `wb.top`. The API has always accepted `top` and the owner asked for "top 15 or 20", but
      reaching 20 meant hand-editing the URL. A cut the URL names and the list does not offer
      is shown rather than silently replaced by the default
- [New] A bucket whose filter the grid beside it already carries is drawn and announced as
      pressed, the same `aria-pressed` convention the enum chips in the facet row use. The
      state term counts: the same county code in another state is not the applied filter
- [New] The counted list is an `aria-live="polite"` region and the wait before it carries
      `role="status"`, so the list changing under a control that keeps focus is announced
      rather than replaced in silence
- [Fix] A "Wells by …" picker shows the value the request actually used. Selectedness set
      before an option is inserted does not survive the select's reset, so a picker could name
      one dimension, state or ranking while the list beside it answered another
- [Fix] The applied bucket in "Wells by …" carries its state on a cyan ring and keeps its label
      at the contrast it had unselected — the facet chip convention it claimed to mirror and
      did not. The 12% tint alone measured 1.24:1 dark and 1.10:1 light against the page where
      WCAG 1.4.11 asks 3:1, and in light theme selecting a bucket dropped its own label from
      17.11:1 to 3.91:1, making the selected row the least legible one in the list. Measured
      after: ring 10.9:1 dark and 4.32:1 light, label 13.01:1 and 15.52:1, and the value column
      does not move
- [Fix] Clicking the pressed bucket clears the filter it applied instead of re-applying it. The
      `aria-pressed` a bucket carries is a toggle contract the handler did not honour, and at
      520 and below the grid's clear-filters line is `display: none` — so selecting a bucket on
      a phone was a one-way door out of the unfiltered list. The un-press removes every term
      the press added, the crossing `state` included
- [Change] Below 520 the explorer scrolls as one document rather than three capped scrollports.
           A 38% band was enough while the middle row held a hidden table's refusal; with a
           counted list in it the total sat 327 px below a 253 px fold and the band edge drew a
           warning sliced mid-line with the API guide painted through the rest. Nothing in the
           panel is clipped now at 390 or 520, and the rail keeps a cap of its own
- [Fix] The "Wells by …" direction button and the caption speak one vocabulary for one
      parameter: under `sort=value` both say `A to Z` / `Z to A`. The button read "lowest
      first" 40 px under a caption reading "ranked by value, ascending" — count words on an
      alphabetical ranking, and two names for the same `order`
- [Fix] "All 1 operator value matching …" — the searched arm of the facet caption pluralises on
      what it counted. Only the unsearched arm did, so a search matching a single value said
      "values" on screen at every width
- [Change] A warning pointing at `/absence` renders inside the absence block it explains, and
           `absence_unregistered` says what that block does not already say. It rendered 39 px
           below the block with the total wedged between them, restating the block's own
           paragraph, `(R8)` included
- [Fix] `make serve-branch` refuses a `web/dist` older than `web/src` and names the build that
      would fix it, the check `scripts/deploy.sh` already makes before shipping. The target
      mounted whatever was last compiled, so a browser gate pointed at the instance judged code
      that was never under review; `GW_WEB_STALE=ok` serves it anyway for runs that put their
      own dev server in front of this API
- [New] `GET /v1/wells/facets` counts wells by a dimension for one state — operator, county,
      status, well type or completion year — ranked, searchable and sortable, with every
      bucket count, the truncation remainder, the named absence bucket and the scoped total
      served as figures carrying derivation handles that `?explain=true` resolves
- [New] The explorer's wells dataset carries a "Wells by …" panel above the grid: the leading
      values with counts and proportion bars, a caption stating what the list is a cut of, and
      a bucket click that narrows the grid beside it to exactly that bucket
- [New] Truncation is counted rather than implied: `remainder` states how many values fall
      below the cut and how many wells they hold, `distinct_values` states how many the state
      holds in total, and with no search in force `buckets` + `remainder` + `absence` sum to
      `wells`; under a search the absence bucket stays outside it, so `buckets` + `remainder`
      sum to `matched_wells` and the served description says which reconciliation applies
- [New] Wells whose dimension has no value are their own named bucket, outside the ranking and
      outside the search — on the current Texas load 70,039 wells report no operator, more
      than any real operator holds, so ranking it would have put a non-operator at the top and
      dropping it would have broken the sum
- [New] `cr_tx_operator_absence_1` registers what a missing Texas operator means: not reported,
      never withheld and never imputed, measured at 39,390 wells whose EWA wellbore record
      carries an empty operator field and 30,649 that reach canonical from a county GIS layer
      with no EWA record at all; Montana's `cr_mt_operator_absence_1` already stated the same
      for its source and is cited beside it
- [New] `/v1/wells` accepts `state`, an exact API state-code filter, so a facet bucket's link
      narrows to the state the bucket was counted in
- [New] Migration 070 adds `wells_facet_dimensions_idx`, a covering index over
      `canonical.wells` that answers the facet aggregate index-only with no heap fetches;
      measured on the deployed database the top-15 Texas operator facet falls from 269,438
      shared buffers and 459 ms to 5,717 buffers and 354 ms
- [Change] Scope is one state and is required. Operator names arrive per source and
           `lineage.operator_aliases` carries no row for any state served, so summing a company
           across a state border would be an aliasing decision no conformance rule has made
- [Change] A state the spine holds no wells for is refused with the loaded states named, rather
           than answered with an empty list — New Mexico's promotion is gated, and "no wells
           loaded" is a different fact from "no operators found". The refusal carries the state
           list as an RFC 9457 extension member so the picker survives it
- [Change] Search runs over every value in the state before the ranking, not over the served
           page: with 9,369 Texas operators a page-scoped search would answer "no such
           operator" for the 9,354 it never loaded
- [Change] Explorer route bundle budget re-measured 71,500 → 75,000 B gzipped for the panel,
           which is on the route rather than split behind a dynamic import because it renders
           on the dataset the explorer opens on
- [Fix] An empty string in a facet dimension is treated as an absent value rather than a bucket
      with no name, which would have ranked among the real values and minted a handle whose
      selector the grammar cannot address
- [Fix] The login ordering test no longer walks the address bucket to its limit through the
      route. Twenty-one requests at the 250 ms login floor is a multi-second loop against a
      limiter window that is a truncated UTC minute, so a run that crossed a boundary met a
      reset counter and the last request answered 403 rather than 429; seven of the last
      twenty CI runs on main failed that way and v0.69 was tagged red. It now seeds the
      bucket and asserts the same 403-then-429 pair in two requests
- [Fix] test_the_index_is_rate_limited asserts both edges of the type-curve index ceiling
      against the shipped constant rather than walking thirty-one requests to it, which
      carried the same window race with no margin
- [New] await_rate_window, rate_window_remaining and spend_rate_window hold the limiter's
      current window open for the request under test, measured on the database clock the
      limiter reads rather than the runner's; fill_bucket waits through a boundary that is
      about to fall, and test_a_seeded_bucket_outlives_the_request_it_was_seeded_for goes
      red if that wait is removed
- [Fix] The legend's rendered-wells census left New Mexico out: with New Mexico the
      only well row switched on, the showing-N-of-M-in-view line vanished, and beside
      another state the count silently excluded every New Mexico well on the canvas
- [Fix] nm_wells: declare the staged header frame's dtypes instead of letting polars infer
      them per batch. The staging table is 39 text columns and one integer, but a column null
      across the inference window is typed Null, so the first state code below it refused the
      whole frame and failed the promotion that opens the New Mexico gate
- [Fix] 068: grant UPDATE on the New Mexico partition registry to glasswell_pipeline.
      nm_ocd registers a partition with `insert ... on conflict do update`, which Postgres
      checks for UPDATE, and migration 028 granted it only select and insert alongside its
      eight append-only siblings; the first least-privileged staging run refused after 33
      minutes with eight tables staged and the ninth denied
- [New] test_staging_upsert_grants.py: a staging table the ingest path upserts must be
      granted UPDATE by some migration, resolved through the module constant so an
      f-string target is not silently skipped
- [Change] status collector: canonical.production_monthly is inventoried by one bounded query
           per registered source instead of one multi-arm filtered aggregate over the whole
           table; 60,571 ms to 3,474 ms with the whole-table sort (1.88 GB spilled to temp
           files) removed rather than made cheaper, measured on a synthetic 29,580,309-row
           local fixture against 2 GB of shared_buffers, so the ratio and the plan shape are
           what carry and the absolute times are not the deployed host's
- [New] migration 069: production_monthly (source_id, entity_key) and
      (source_id, created_at desc) indexes, so the per-source arms run index-only with no heap
      fetch; on the same synthetic fixture max(created_at) was the column that forced the heap,
      costing 25,934 ms for one source against 596 ms without it. Both builds are `if not
      exists`, so an operator can build them CONCURRENTLY before the migrate rather than hold a
      write lock on the table for the length of a build inside its transaction
- [New] cr_nd_inventory_jurisdiction_1, cr_nm_wcproduction_inventory_jurisdiction_1,
      cr_mt_inventory_jurisdiction_1 and cr_mt_pru_inventory_jurisdiction_1 register that each
      source's production rows are inventoried under the jurisdiction its lineage.sources row
      carries, not under an API-10 prefix (R8); a new state registers a source and a rule and
      is inventoried without editing the collector
- [Change] production inventory counts distinct entity_key rather than distinct api10, so the
           Montana PRU lease grain is counted on the identity it carries; an API-10 prefix
           predicate reached none of its 4,808,814 rows
- [Change] New Mexico's production entity metric is identified and labelled as completion-pool
           entities rather than wells, because that is the grain the source files and glasswell
           rolls none of it up to the well
- [New] Layer panel: the Well spine group nests its four state well rows under one `Wells`
      parent switch, tri-state on `aria-pressed` (all on, all off, `mixed`), with the members
      shut on first paint and each reading by its state alone
- [Change] Layer labels state the state the same way on every row — `Wells (North Dakota)`,
           `Wells (Texas)`, `Survey traces (North Dakota)`, `Well paths (Montana)` and the
           six others — spelling the name out as the status page and the glossary already do
- [Fix] The North Dakota wells row was labelled `Wells`, unqualified, while Texas, New Mexico
      and Montana carried a state; first-ingested was reading to a reader as a distinction
- [Fix] Layer search finds a state by name: `texas` and `new mexico` matched no row, and
      `montana` matched only where a subtitle happened to spell it
- [Fix] Layer switch and opacity slider announce the standalone layer name under the nesting,
      so a screen reader hears `Show Wells (Texas)` rather than `Show Texas`

<a id="v0.70"></a>
## v0.70 — 2026-08-30

- [New] glasswell-eia-boundaries and glasswell-basin-boundaries console scripts, so both
      halves of the EIA boundary load are operator-reachable; the layer shipped in v0.69 with
      its tables, tile functions and martin sources installed and served nothing because
      neither loader had an entry point
- [New] docs/runbook-basin-load.md: the two production commands, the user each runs as, the
      exact expected counts against pinned manifest ids, success-versus-partial triage, and
      the undo
- [Change] test_fetch_attempt_entrypoints: eia_boundaries.py joins the network-fetch commands
           required to open the independent attempt ledger; it always did, and nothing
           checked it
- [New] Montana reaches the API and the map: marts.mt_wells_tile and marts.mt_paths_tile
      rebuilt by glasswell.marts.mt_wells, mt_wells and mt_paths published as tile layers
      and martin function sources, and a Wells (MT) and Well paths (MT) row in the layer
      registry drawn from the same status expressions as North Dakota and Texas
- [New] every served Montana path carries geometry_class map_stick and its vertex_count as
      tile properties, so cr_mt_paths_geometry_class_1's requirement that the distinction
      be stated wherever the geometry is served holds for a client that reads no docs
- [New] cr_mt_paths_length_scope_1: no lateral length is served for a Montana well, and the
      response carries the rule in the figure's place with a length_not_served warning and
      a links.length_rule handle
- [New] glasswell-mt-bogc and glasswell-mt-gis console scripts, the Montana mart refresh on
      the ingest timer, and docs/runbook-mt-load.md — the production load with its expected
      counts, tolerances, success-versus-partial cut and its undo
- [New] /status reports current Montana wells and published Montana map layers, each stating
      the rule behind what it counts
- [Fix] mt_gis: rejected rows reach lineage.quarantine_rows instead of only a counter — on
      the 2026-08-18 Wells.zip that is 1,400 wells whose MBOGC status cr_mt_gis_status_vocab_1
      does not promote, plus one unparseable API-10, recoverable with their payloads rather
      than reconstructable by subtracting two printed totals
- [Fix] the well card served a Montana lateral length of 6,120.87 ft under North Dakota's
      cr_nd_compute_crs rule: lengths.length_rule_source answers nd_gis_horizontals_line for
      any well with no basin, and cr_mt_basin_scope_1 leaves every Montana well untagged
- [Change] the frozen WellDetail schema documents what it now serves: length_method reads
           not_served where a rule withholds the length, compute_crs and lateral_length_ft are
           null there, and links.length_rule names the rule; descriptions only, no structural
           change, snapshot regenerated with scripts/regen-snapshot.py
- [Change] /status inventories Montana production on both grains MBOGC files, bucketed by
           source rather than by API-10 prefix: the lease grain carries a lease entity_key and
           no api10, so a prefix filter reaches none of it and would report 72% of the state
           under a label saying Montana
- [Change] PROVENANCE_RULES maps state 25 to cr_mt_paths_geometry_class_1 rather than
           falling through to North Dakota's cr_nd_geometry_provenance_1, which would have
           cited a survey-derived classing rule for a cartographic centreline
- [New] `glasswell-nm-wells` and `glasswell-nm-tiles` console scripts for the New Mexico
      Tier 2 pair — the header and surface-geometry promotion, and the tile mart refresh.
      Both modules already had a `main()` and neither had an operator entry point, so the
      runbook commands were module invocations; `scripts/deploy.sh` reinstalls the project
      editable on every deploy, so the table and the host move together
- [New] `docs/runbook-nm-tier2.md`: the four production steps that open the New Mexico gate,
      scoped as Tier 2 and explicitly not the production-history load. Every expected figure
      carries its provenance — sealed 2026-08-20 measurement, estimate by analogy, or record
      it — so no fixture count is mistaken for a forecast
- [New] `tests/integration/test_nm_tier2_end_to_end.py` runs the operator's chain on one
      database — stage, promote, refresh, serve — and decodes a fixed zoom-9 southeastern New
      Mexico tile off the wire; the promotion and the mart each had their own suite and
      nothing measured the seam between them
- [New] the gate assertion is red then green on the same API-10: the first promotion is
      rolled back so the 404 and the 200 are the same key on the same database, which is the
      only ordering that proves the header row is what changed the answer
- [New] `tests/unit/test_console_scripts.py` pins the New Mexico pair to the launcher
      contract and fails if `nm_ocd` or `nm_dims` ever acquires a script of its own: an entry
      point is a form of encouragement, and the production-history load needs a runbook and a
      named authorisation instead of a shorter spelling
- [New] `canonical.wells.operator_name_reported` is decided at promotion time and is not one
      of the attributes the divergence check compares, so a re-run once
      `lineage.operator_aliases` exists appends nothing and leaves every name null — measured,
      then pinned by a test pair covering both orderings. The runbook makes it an abort
      condition with an owner decision rather than a default
- [Change] `infra/README.md` gains an operator entry-point table, and records why the Tier 1
         production-history load keeps its `python -m` spelling: an entry point is a form of
         encouragement, and that load needs a runbook and a named authorisation instead
- [Change] `infra/martin/README.md` lists `nm_wells` with its refresh command, states that
         New Mexico publishes a point layer and no lateral, and stops claiming a layer count
         the roster outgrew
- [Change] `README.md`'s project-docs table gains both New Mexico runbooks; the Tier 1 one
         has never been listed there and the pair only reads correctly together
- [New] Status serves a Deployment block: code version, schema head, edge host,
      database storage, and the posture the serving process is actually enforcing
      (public origin, anonymous reads, tile upstream, frontend bundle, local
      basemap, CSP), read from the API process rather than the snapshot because
      only it knows what it refuses
- [New] Status groups components into an Architecture section by tier — serving
      plane, data plane, edge, host — and names the systemd unit or mount each one
      was observed through, so a reader can act on the row
- [New] The collector observes the Cloudflare tunnel (`cloudflared.service`), the
      status-snapshot timer that writes this page, and the Cloudflare range
      refresh; three components the deployment ran with no telemetry at all
- [New] Scheduled work reports each job's timer unit and whether it is armed,
      separately from whether its last run succeeded
- [New] Dataset inventory counts `lineage.conformance_rules` — registered rules,
      rules in force today, rule families, sources covered — so R8's mapping
      registry has a magnitude on the page
- [New] Open quarantine is inventoried per reason code as well as in total; the
      per-reason metrics partition the open population
- [New] Monthly production carries a distinct-month count per state alongside its
      span, because two endpoints cannot show a hole between them
- [New] Status discloses that staging is not inventoried, rather than leaving its
      absence to inference
- [Change] Dataset inventory becomes a Data footprint table grouped by storage
           layer (canonical, marts, lineage), with scope, grain, magnitudes, the
           span covered and latest knowledge on one scannable row; each dataset's
           served caveat and count time move into a per-row disclosure
- [Change] Method statements that qualified a section rather than reported its
           state — what a check proves, how counts are grained, what a run time
           means, how freshness is decided — move from standing paragraphs into
           collapsed disclosures beside each heading; visible standing prose on the
           surface drops from 276 words to 77, all of it served content
- [Change] Precision is marked once per footprint row when every metric shares it
           and per metric when they differ, replacing a badge on all 43 counts
- [Change] Component cards state their observation time only when it differs from
           the snapshot's, instead of repeating one timestamp on every card
- [Change] The committed OpenAPI snapshot regains the served document: `deployment`,
           `checks[].tier`, `checks[].probe`, `jobs[].unit`, `jobs[].timer_armed` and
           `platform.edge_host` are all additive
- [Change] `tests/e2e/status-surface.mjs` grows from 88 to 124 assertions, adding
           deployment facts, tier grouping and probe identity, layer grouping and
           laid-out magnitude height, a derivation handle on every rendered count,
           and that each demoted caveat starts collapsed behind a visible control
           and becomes visible when opened; visibility is measured with
           `checkVisibility()`, since a closed `<details>` keeps a laid-out box that
           makes both `getBoundingClientRect()` and `offsetParent` report it visible
- [Fix] deploy.sh: install every configured layer's tile function after seeding and before
      the martin restart. martin refuses to boot on an unresolvable source, so three New
      Mexico and boundary layers whose marts had never been refreshed stopped it starting
      and took nd_wells and tx_wells down with them
- [Fix] deploy.sh: hand the marts tile functions to the pipeline role after installing them
      as superuser; a function first created by the deploy was owned by postgres and made
      the next mart refresh fail with "must be owner of function nd_survey_traces"

<a id="v0.69"></a>
## v0.69 — 2026-08-30

- [New] tiles: basins and plays are served tile layers over marts.basin_boundaries_tile —
      32 EIA sedimentary basin outlines and 16 individual play boundaries for the lower 48,
      each with a label anchor point owned by exactly one tile, so the map has a geological
      frame of reference instead of an undifferentiated field of well points
- [New] ingest: eia_boundaries loads both EIA archives as plain HTTPS zips through the
      existing strict-.prj shapefile reader — one manifest per archive, twelve boundary
      shapefiles selected out of the play bundle by a declared stem marker so the elevation
      and isopach contours beside them are never read
- [New] canonical: basin_boundaries holds one published boundary per row under a minted key
      — EIA publishes no feature id — discriminated by boundary_kind, append-only, with the
      publisher's own Basin string kept verbatim beside the resolved link
- [New] seed: eight code_ref and datum conformance rules record the boundary decisions —
      whose interpretation is drawn, that a basin and a play are different objects, how a
      play links to its basin, that overlap is served rather than arbitrated, how an invalid
      published ring is repaired, whose area is served, how a well is judged inside a
      boundary, and that both archives ship WGS 84
- [New] conformance: cr_eia_basin_link_1 links a play to its basin by case-folded exact name
      and to nothing otherwise; four of sixteen plays do not resolve and the rule records why
      each near match is refused, because a join right twelve times and quietly wrong twice
      is worse than one that reports four unresolved links
- [New] conformance: cr_eia_geometry_repair_1 repairs the two invalid published rings —
      Bakken and Three Forks, both ring self-intersections, both Williston — by ST_MakeValid
      with polygonal extraction, records each as an invalid_geometry reject and then releases
      it under the rule with the promotion derivation, so the repair is a ledger fact rather
      than a silent edit; a repair that yields no polygon is refused outright
- [New] conformance: cr_eia_well_membership_1 defines basin membership as surface-hole
      intersection with the served boundary, states that membership is a set and that a well
      inside none is unassigned, and records that canonical.wells.basin is a declared
      per-source constant and not this geometric claim
- [New] quarantine: invalid_geometry joins the reject vocabulary
- [Change] tiles: TILE_LAYERS composes BASIN_LAYERS, so the proxy allowlist, the martin
         config assertion and the wire-type audit cover the two new layers on the day they
         are declared
- [New] map: the layer list is grouped by what a layer is of rather than by the mart that
      publishes it. Well spine, land and legal framework, derived surfaces and geology
      framework each head a collapsible band; a band opens when the reader is already
      drawing something inside it and carries a count of its live switches when shut, so
      nothing on the canvas is hidden without a mark. The panel now fits above the fold at
      every breakpoint, 635px of list at 390 wide becoming 419px
- [New] map: a layer that is switched on, in scale, and painting nothing at this extent
      says so on its own row instead of looking drawn. Read off the canvas at map idle, so
      a layer whose tiles are still streaming is never reported absent; the wording states
      the canvas and never the ground, because a failed source queries empty too
- [New] card: the well header carries the status as the same glyph the map painted it
      with, and names the code the regulator filed beside the canonical class, so the
      mapping is readable rather than hidden. Loaded on a dynamic edge, which is what keeps
      the map status vocabulary off the entry chunk and off the explorer route
- [Change] card: the well facts read as four bands, operator, location, drilling and
           completion, and record, instead of one flat list where a compute CRS carried the
           same weight as the operator; a band whose every field is absent is dropped
           rather than left heading an empty list
- [Fix] card: an absent value is no longer typographically identical to a measured one.
      DR-H24 recorded that absence and measurement shared colour, weight, family and font
      style, and that this becomes a real problem when a panel is skimmed rather than read;
      absence now takes one muted italic form and still names which kind of absence it is
- [Fix] card: the neighbour rows printed the raw null-semantics token, so "alias
      unavailable" stood in the Formation cell looking exactly like a formation name beside
      "bakken". Both the absent value and the mapping state are spelled out now, each from
      its own endpoint's vocabulary, which are rendered in one form and never asserted to
      mean the same thing
- [Change] tests/e2e/chrome-fold.mjs: the fold arithmetic divides by rendered rows and
           asserts every group header is reachable, plus every operable layer having a row
           at all. A row inside a shut group has a zero rect, which would have made both
           the fold count and the mean row height pass while measuring nothing
- [New] seed: conformance_mt.py registers 45 Montana rules across four MBOGC sources — the
      API-14 to API-10 slice on state code 25, the end-of-month report convention, the -999
      Lease_Unit sentinel, the pre-applied oil-plus-condensate liquids basis, the formation
      rollup, the lease grain's reporting level, the fifteen disposition columns that stage
      but never promote, the cp1252 DBF encoding, the twinned-layer selection, and the
      map-stick-not-survey class on well paths; every row carries a rationale, an evidence
      URL and a figure measured by full streaming pass rather than sampled
- [New] seed: four MBOGC sources registered with an UNVERIFIED licence note — the listing
      root answers 403, so bulk paths are pinned constants and no filename is ever derived
      from an index
- [New] db: the Montana registry migration adds the poll cadences, lineage.mt_stream_map and
      lineage.mt_status_map with their promoted views, and the first-publication evidence
      migration 049 requires before any cr_mt_ rule may be seeded
- [Fix] ingest: ZippedShapefile takes an optional encoding. The MBOGC DBF declares Windows-1252
      at language-driver byte 0x59 and pyshp's strict UTF-8 default raised partway through
      iteration on a well named Blasé; the default is unchanged, so ND, TX and NM read exactly
      as before
- [Fix] tests: the source-poll cadence guard scans every migration for its insert rather than
      opening 050 by name — migrations are immutable, so a source registered later can only be
      given a policy in a later file, and the guard was blind to precisely that case; its
      statement terminator now tolerates a semicolon inside a cadence string
- [New] ingest: mt_bogc.py stages and promotes both MBOGC grains from one archive and one
      manifest — the well grain at well and well_completion_pool over ST_FMTN_CD with a
      sum_over_pools rollup whose days take the maximum, and the lease grain at
      lease_reported. Staging streams from the zip member and promotion reads one production
      month at a time, so a 573 MB file is never extracted and never held in memory
- [New] ingest: mt_gis.py loads the surface points and well paths, selecting the geographic
      layer of each twinned archive by stem and keying a lateral on WellSub within its API-10;
      the promotion derivation records is_directional_survey false, so a consumer reading
      provenance learns the map-stick class from the ledger rather than from prose
- [New] ingest: promote.py carries the source-parameterised bitemporal append — change-only
      heads, scoped head reads and same-vintage divergence refusal — so a second state does
      not restate them as literals bound to one source id
- [New] db: the Montana staging migration adds the four staging tables, text-faithful including
      the -999 sentinel and the fifteen unpromoted disposition columns
- [New] seed: the registry migration seeds all nineteen published MBOGC status values with their measured counts;
      six are deliberately unpromoted and quarantine as unknown_status rather than being forced
      onto a canonical state the source does not claim
- [Fix] marts: the neighbour mart spans North Dakota and Montana. ND wells within 26,400 ft of
      the state line had their neighbour sets truncated at the border because
      nd_neighbor_subjects and both sides of nd_neighbor_edges were constrained to
      '^33[0-9]{8}$' — a correctness gap ROADMAP already named, not a coverage gap
- [Fix] marts: the pair-local UTM zone is computed from the shortest-line midpoint rather than
      chosen from a hardcoded pair split at -102. The old expression had no unsupported branch,
      so a pair outside 13N/14N was silently measured in one of them, passed the CHECK and was
      stored under a handle asserting a pair-local CRS. Over the ND rectangle the formula
      reproduces the old rule with zero mismatches, so ND distances are unchanged
- [Fix] marts: SUPPORTED_LONGITUDE_MIN moves from -104.15 to -116.10. The old floor sat 7,531 m
      west of the ND/MT line while the padded discovery radius is 8,208 m, so it was already
      too tight for ND-only correctness before Montana existed
- [New] db: the neighbours multi-state migration relaxes the subject and edge API-10 checks to
      '^(25|33)[0-9]{8}$' and admits UTM 11N-14N, the zones the widened domain can produce
- [Change] api: the neighbours HAL link and the explain-handle validators accept Montana
      subjects, and STATUS_VOCABULARY_RULES gains 25 so an MT row does not emit
      status_vocabulary_unregistered
- [Change] tests: the candidate-pad proof imports the zone rule instead of reimplementing it,
      and its measured bound is re-derived over the widened domain rather than relaxed — max
      ratio 1.013136 against the same < 1.014 claim, with no false negatives. The domain-refusal
      test is re-anchored from -105.50 to -118.00, never deleted: it is the only proof the
      guard fires
- [New] `scripts/ops/nm_reregister_manifests.py` re-registers a sealed raw-zone artifact
      from its sidecar into an index that does not carry it yet; no socket is opened and
      the operation is idempotent on the sha256 within a slot
- [New] `--dry-run` validates every sidecar, resolves each against the live index and
      reports the manifest ids it would create on a read-only connection, so committing
      nothing is enforced by the server rather than by the code path
- [Fix] the manifest re-registration tool existed only at `/data/scratch/d1-p4/reregister.py`
      on the app VM, inside a disposable tree, while the status file that directs an
      operator to it named a `work-output/experiments` path that does not exist; it now
      names its target database on every run, reports registered against already-present
      per sidecar, and exits 1 on a slot conflict instead of tracebacking
- [Fix] `status/collector.py` aggregated `canonical.production_monthly` with no state filter
      and served the result under a hardcoded North Dakota jurisdiction, so the first New
      Mexico promotion would have published 24.8M rows and ~93,958 wells under the wrong
      state within fifteen minutes, on a timer, over rows with no well header
- [Change] the inventory splits into `canonical.production_monthly/nd` and `/nm`, matching
         the state-qualified convention every sibling dataset in the file already follows,
         including the `well_completions/nm` entry that already serves zero
- [Change] the status contract test seeds two states rather than one — the defect was
         invisible to a single-state fixture — and asserts the two datasets partition the
         table, so a third population would fail rather than vanish from a served figure
- [New] `docs/runbook-nm-promotion.md`: the four New Mexico production steps with their
      preconditions, abort conditions, expected counts, verification gates and the rollback
      each step actually has — which for three of the four is none, stated in terms designed
      to stop an operator improvising a delete
- [New] `tests/integration/test_nm_promotion_gates.py` pins the index the deployed G7-2 gate
      names: `production_monthly_api10_idx` exists, leads on `api10`, and both the served
      query and the `_latest` view resolve to it once a sequential scan stops being free
- [Change] `057_state_parameterised_neighbors.sql`: `nd_neighbor_subjects.api10` and both
         `nd_neighbor_edges` endpoints accept any ten-digit API-10 rather than only `^33`,
         while a new constraint keeps an edge intra-state because the pair-local UTM zone
         selection is undefined across an arbitrary state pair
- [Change] `marts/neighbors.py`: `STATE_CODE` becomes the `STATE_CODES` tuple the refresh
         binds through `= any(...)`, so a second state is a data change rather than an edit;
         New Mexico is deliberately not in it, because neither NM source ships a lateral
- [New] `seed/conformance_nm_wells.py`: ten conformance rows covering New Mexico's header
      identity, effective dating, status and well-type domains, the NAD83 datum transform, the
      coordinate policy, geometry provenance and scope, the pool grain and the cross-source
      header precedence; `058_nm_gate_rule_publications.sql` registers their publication
      evidence, which migration 049 makes a precondition for the insert
- [New] `cr_nm_wellhistory_coordinate_1` records the measurement behind the policy: 318,720 of
      321,510 records carry a usable coordinate pair, 897 carry a zero ordinate and 1,893 a nil
      one, giving 141,778 of 142,000 wells a point — three counted populations that sum to the
      record count rather than two counted and one subtracted
- [New] `cr_nm_wellhistory_status_vocab_1` records the fifteen-value status domain and asserts
      no canonical status: the OCD publishes no codebook, so a New Mexico well carries its
      letter in `status_reported` and null in `status_canonical`, and the served unmapped count
      has a rule behind it
- [New] `cr_nm_wellhistory_geometry_scope_1` states that no in-scope New Mexico source ships a
      lateral or a bottomhole, so the 43,409 horizontal and 3,265 directional wells the header
      table names must never be read as carrying a path
- [New] `cr_nm_wcproduction_pool_rollup_1` gives New Mexico's pool grain a New Mexico rule to
      cite instead of North Dakota's, and says the opposite of what North Dakota's says: all
      17,597,960 promoted rows are `well_completion_pool` with a null aggregation and there is
      no well-level row among them, so a New Mexico well's well-level series is absent rather
      than zero
- [New] `059_nm_well_headers.sql`: `coordinate_sentinel` and `coordinate_absent` join the
      quarantine reason vocabulary, so a zero ordinate and a nil one are quarantined under
      distinct codes rather than dropped or collapsed, and `wells_state_effective_idx` supports
      the per-state newest-effective-row scan the tile marts run
- [Change] `canonical.wells` and `canonical.well_spatial` need no widening for API prefix 30 —
         neither carries a state constraint and `geom_type` already admits `surface` — and a
         test now guards that against a future state check
- [New] `ingest/nm_wells.py` promotes `staging.stg_nm_ocd_wellhistory__records` into
      `canonical.wells` and `canonical.well_spatial`, keyed by the registry's own per-segment
      API-10 composition rule and carrying no state-code literal. This is the row that opens the
      serving gate: the spine is rooted on `canonical.wells`, so every New Mexico figure becomes
      servable here and nowhere earlier
- [New] the OCD FTP header table ships latitude, longitude and NAD83 datum — 318,720 usable
      pairs of 321,510 records and 141,778 of 142,000 wells — so New Mexico geometry needs no
      new source; the earlier "no coordinates" finding was scoped to `wcproduction`
- [New] the coordinate policy is a pair rule, not a latitude rule: either ordinate nil
      quarantines as `coordinate_absent` and either ordinate zero as `coordinate_sentinel`, nil
      taking precedence. Four records carry a good latitude with a zero longitude, and a
      latitude-only check would have given them a valid point in the Gulf of Guinea in an
      append-only table
- [New] `tests/fixtures/nm_ocd/nm_wellhistory_headers.xml`, cut from the sealed artifact by
      truncation and selected rather than taken from the head, so all six coordinate
      populations are present — three of them hold fewer than five records in 321,510
- [Change] neither refusal suppresses the well header, and two reconciliations close on counted
         populations rather than on subtraction: records equal headers plus unkeyed plus
         undated, and headers equal points plus coordinate refusals
- [New] `marts/land_metrics.py` counts unassigned wells a third way — those outside the states
      the PLSS grid covers at all — so the scope New Mexico's 141,778 surface points fall
      outside is stated explicitly rather than inferred from a total
- [Change] `060_land_grid_state_scope.sql` and `seed/conformance_land.py` supersede
         `cr_land_agg_membership_1` with `_2`, carrying the third counter and the measured
         populations; the membership itself is unchanged, which is why this is a superseding
         row rather than the code change its own contract_note forbids
- [Fix] the membership universe is not filtered by state: 355,463 Texas surface points are in
      it today and a scope filter would have collapsed a served figure to zero while a fixture
      with one state in it reported no change
- [Change] the production CTE is restricted to the wells membership actually joins, which is
         output-identical — asserted by running both shapes side by side — and removes a full
         scan of a view that spans 24.8M rows after the New Mexico promotion
- [New] `marts/nm_wells.py`: a point-only New Mexico tile mart on the same shape as the ND and
      TX marts — reads canonical only, rebuilds rather than appends, one content-addressed
      derivation per refresh — and `061_nm_marts.sql` creates `marts.nm_wells_tile` with its
      grants and registers the GIS layer's poll cadence
- [New] the tile carries `status_reported` beside `status_canonical`, because every New Mexico
      `status_canonical` is null by `cr_nm_wellhistory_status_vocab_1` and the reported letter
      is what a legend has to work with
- [Change] there is no `nm_laterals` layer and a test guards against one, asserted against the
         tile proxy's own allowlist rather than the mart module's constant: no in-scope New
         Mexico source ships a lateral, and a layer would imply a footprint nobody filed
- [Fix] `api/routers/production.py`: the pool-rollup link was pinned to `cr_nd_pool_rollup_1`
      and served on the pool endpoint unconditionally, so every New Mexico pool series would
      have cited a North Dakota rule; the link now resolves per jurisdiction and cites
      `cr_nm_wcproduction_pool_rollup_1`, which says New Mexico rolls nothing up
- [Fix] `api/routers/production.py`: `ND_LIQUIDS_BASIS` was served as the mandatory `_basis`
      sidecar on every liquids figure regardless of state, so every New Mexico oil figure would
      have carried North Dakota's liquids policy; the basis is resolved per figure and New
      Mexico's is `oil`, because `cr_nm_wcproduction_liquids_1` measured 3,398 condensate
      filings and ruled that condensate is its own stream
- [New] a New Mexico well whose production is filed at pool grain now says so on its
      well-level series instead of rendering an empty chart: all 17,597,960 promoted rows are
      `well_completion_pool` and nothing rolls up, so the series is absent rather than zero
- [Fix] `api/routers/wells.py`: `STATUS_VOCABULARY_RULES` had no prefix-30 entry, so a New
      Mexico well served a null `status_vocabulary_rule` and a spurious warning; geometry
      provenance likewise resolved to the North Dakota rule for every state, and five served
      field descriptions enumerated North Dakota and Texas in prose where they now name the
      per-jurisdiction mapping
- [Change] `status/collector.py` reports New Mexico in the `canonical.wells_latest` inventory
         and publishes `marts.published_map_layers/nm`, so the status surface stops enumerating
         two states out of three
- [New] `web/src/map`: the `nm_wells` point layer, its registry provenance entry citing
      `marts.nm_wells_tile`, and its status-count block — which is empty, and says why: every
      New Mexico `status_canonical` is null under `cr_nm_wellhistory_status_vocab_1`, so the
      whole state draws in the unmapped class rather than a guessed one
- [Change] no `nm_laterals` layer is added and no struck sibling: no in-scope New Mexico source
         ships a lateral, and the strike marks a status class New Mexico can never carry
- [Change] the default Williston centring is left alone; re-centring for a second basin is an
         owner decision and is routed to the register rather than taken here
- [New] the `nm_wells` mart joins the ingest unit's refresh sequence, and the unit description
      stops claiming it is ND-only; that unit runs monthly on day 5, not nightly
- [New] a smoke check asserts the New Mexico spine — a well header with a geometry provenance
      and a New Mexico status vocabulary rule — rather than a row count, and skips cleanly
      where the gate is not open
- [Change] no timer is added for `nm_ocd`, `nm_dims` or `nm_wells`: those sources are
         registered owner-triggered and the FTP pull is a once-ever event; the measured cost of
         a recurring promotion — 89 minutes and 9.9 GB, which does not fit the ingest unit's
         `TimeoutStartSec` — is recorded in `SMOKE.md` for the decision, along with a weekly
         recommendation for the daily-refreshed GIS layer
- [New] `ingest/nm_wells_gis.py`: one ordered walk of the OCD Wells_Public FeatureServer layer,
      ordered by the unique `id` rather than `OBJECTID`, into one checksummed artifact, one
      manifest and one staging load; the host is already allowlisted so no blueprint amendment
      is required, and `062_nm_wells_gis.sql` creates the staging table and registers the rule
      publications
- [New] `cr_nm_wells_gis_parity_1` records the agreement between two independently produced New
      Mexico well populations — 141,916 GIS features against 142,000 FTP header API-10s, a
      0.06% difference — as a prohibition rather than a tolerance band: the per-well distance
      distribution is not measured, so no rule can yet say which source wins where they differ
- [Change] the module stops at staging on purpose: the parity measurement decides how it
         promotes, and promoting first would make the rule a rationalisation rather than a
         finding. `cr_nm_wellhistory_header_precedence_1` accordingly still names the FTP
         archive as sole authority, and no superseding row is seeded ahead of the evidence
- [Fix] `STATUS.md` conflated the production database with the deployed host, so it reported
      New Mexico as unpopulated while 79 conformance rules, 10 sources and 71,447 staging rows
      were resident and a full 17.6M-row spine sat in a scratch database on the same machine
- [Fix] `STATUS.md` overstated `tx_pdq_dsv`: it has a poll-cadence row on a table with no
      foreign key to `lineage.sources`, and a test fixture — not a seeded source registration,
      not conformance rules and not an ingest module
- [Change] `ROADMAP.md` N3 says surface geometry rather than lateral geometry, and New Mexico
         lateral geometry is tagged `data-unreachable`: neither the OCD FTP header table nor
         the OCD public wells layer ships a lateral or a bottomhole, measured in both, with
         43,409 horizontal wells named and no path filed for any of them
- [Change] `ARCHITECTURE.md` names the New Mexico tile mart and the two staging termini that
         are termini by design rather than by omission
- [Change] the promotion runbook asserts the Wave-1 `glasswell-repromote` units are **absent**
         rather than masking them: T6 removed them from VM 111 on 2026-08-30 and `verify.sh`
         now asserts host against tree, so masking a unit that does not exist is not the check
         the condition wants. The armed-timer framing is corrected with the measurement that
         settles it — `Persistent=` catch-up needs a calendar occurrence after the base time,
         and `systemd-analyze calendar '2026-08-21 00:30:00 UTC'` returns `Next elapse: never`
- [Change] the dump precondition says what it does not give: `verify.sh` gates its schema-head
         comparison on a drill completing after `max(applied_at)`, and the drill is weekly, so
         between this deploy and the next Sunday the newest restore proof covers the previous
         schema
- [Fix] `cr_nm_wellhistory_effective_1` legislated a translation of the `9999-12-31` sentinel
      into a null `effective_to`, and `canonical.wells` has no `effective_to` column and the
      promoter never read `rec_termn_dte`; the row now states what the code does, the promoter
      reads the field name and the reason code from the spec, and the ranking question the old
      text hid is measured — 142,000 open headers against 142,000 wells and zero wells whose
      newest row is retired
- [New] `cr_nm_wellhistory_basin_scope_1` records that New Mexico headers carry no basin and
      why: its wells sit in the Permian and the San Juan and this build delineates neither, so
      a default would be a claim about geography wrong for every San Juan well
- [Fix] `marts/producing.py` filtered `entity_type = 'well'` and served every New Mexico well
      `producing: unknown` under a field description offering three causes, none of which
      applied; the states with no well-level series now resolve from the registry for either
      recorded reason, and the well card discloses which with the rule that decided it
- [Change] the New Mexico smoke check keys its branch on `/v1/status` rather than on the
         endpoint under test, so a regression that drops New Mexico from the spine fails
         instead of converting the assertion into a skip
- [Change] `scripts/ops/nm_reregister_manifests.py` gains `--expect-database`, turning an
         operator rule into a refusal; `test_martin_publishes` suffixes its container name, so
         two worktrees sharing a Docker daemon stop manufacturing false reds
- [Change] the three migrations that write `lineage.conformance_rule_publications` carry the
         repository's placeholder evidence rather than a hardcoded release tag, so the release
         guard refuses until the merge train repoints them; the table is append-only, and a tag
         that ships from another track would be a permanently false claim about publication
- [Change] `producing.py`'s `lease_reported_states` alias is removed rather than kept: the
         function now returns both reasons a state has no well-level series, and a name that
         describes one of them is the same defect as a rule that describes a transformation the
         code does not perform
- [Fix] both manifest re-registration invocations in the promotion runbook pass
      `--expect-database glasswell`, so the refusal guarding the one-letter gap between
      `glasswell` and `glasswell_d1` fires on the documented path instead of leaving an
      operator with the transcript check the flag was added to replace
- [Fix] Makefile: `make lint` and `make fmt` borrow the main checkout's interpreter when the
      current tree has none, so they work in a git worktree; every dispatched track hit the
      failure and reached for a system ruff instead. The test targets deliberately do not
      borrow it, because that venv installs glasswell editable against its own src
- [Fix] test_d1_entry_gate.py: skip the wave-1 status-artifact gate in a linked worktree.
      Its guard keyed on work-output/ existing, so any dispatched track writing a status
      file there turned a self-disabling gate red with a message naming the wrong cause

<a id="v0.68"></a>
## v0.68 — 2026-08-30

- [Fix] cloudflared: the connector unit declared `Type=notify`, but `tunnel run` serves
      without ever sending sd_notify READY, so systemd held it in `activating`, timed the
      start out and restarted a working tunnel — 49 restarts against four registered QUIC
      connections; now `Type=exec`
- [Fix] install.sh: make `/etc/cloudflared` group-traversable, since 0640 root:cloudflared
      files are unreadable through a 0700 root:root parent and the connector reports the
      file rather than the directory that refused it
- [Fix] api: POST /v1/session/password charges the login bucket before it verifies the
      current password; the session router is included without enforce_rate_limit, so a
      held session cookie bought unlimited current-password guesses against an account it
      could not otherwise take over
- [Fix] verify.sh: resolve the public hostname at a public resolver and carry the address
      on the four edge probes; lab DNS is split-horizon and NXDOMAINs the record, so every
      probe answered 000 and the deploy gate read an unreachable name as a broken edge
- [New] verify.sh: assert the installed Caddyfile equals the tree, the front-door
      equivalent of the connector drift check; deploy never installs it, so the two
      diverged silently for ten days with only an inert stale origin to show for it
- [Fix] install.sh, deploy.sh: enable and start glasswell-cf-ranges.timer, which shipped
      installed but armed by nothing, so the weekly Cloudflare range refresh its own file
      header advertises had never run on any host
- [New] verify.sh: assert the range-refresh timer is enabled and active; the freshness
      check beside it cannot fail on a deploy, because install.sh rewrites the file
      minutes before verify reads its mtime
- [New] api: GET /v1/wells/{api10}/type-curve serves the pinned tcv1.0 control for one
      held-out test subject — P10/P50/P90 monthly and cumulative curves month-indexed to
      the split's horizon, both normalisation arms, the resolved peer-ladder rung, the
      per-month peer support and the cum12/cum24 band; every array carries a handle that
      resolves to the pinned artifact and its split set at the default explain depth
- [New] api: control_unavailable is a served outcome on a required field — a 200 naming
      its reasons with the figure slots present and null, whose handles resolve to the
      rung that terminated rather than to a value that does not exist
- [New] api: GET /v1/type-curves browses the control population at its horizon with the
      ladder rung, the control_unavailable reasons and the per-subject peer support,
      cursor-paginated and rate-limited; the two support columns are page-level series,
      so a page mints two evidence rows rather than two hundred
- [New] api: GET /v1/modeling/publications and its detail serve the accepted P3
      publication receipt — the three semantic versions, the three pinned derivations,
      the split set and every split hash, the acceptance gates with their thresholds, and
      the peer-ladder support distribution; a second publication is announced as a
      restatement with the prior one linked and still addressable
- [New] modeling: served.py resolves the control through four independent agreements — an
      accepted publication receipt, a registered typecurve.build derivation,
      receipt/locator/digest agreement, and a containment-checked non-symlink path whose
      sha256 matches output_sha256 — and re-stats the file after the read
- [New] seed: five code_ref conformance rules record the type-curve serving decisions —
      which publication is servable, the closed peer ladder, what typecurve_per_kft
      rescales to, that quantiles are statistical-ascending and not the reserves reading,
      and that control_unavailable is a stated value
- [New] seed: glossary terms for quantile convention, peer ladder and split set
- [New] infra: GLASSWELL_MODEL_ROOT pins the registered artifact tree the API may read;
      unset refuses every type-curve route rather than reading an unregistered path
- [Fix] api: the served control is resolved through the receipt keys the P3 builder writes,
      artifact_sha256.typecurve_control and .typecurve_coverage, not the artifact_uri
      vocabulary; the two key spaces are now named once in p3_publication and imported by
      every consumer, and the contract fixture derives its receipt from them
- [Fix] api: an empty facet value on the type-curve index is an unset filter rather than a
      second response identity; it minted one derivation for two pages, and a derivation
      row is immutable, so one request poisoned the default page permanently
- [Fix] api: the type-curve index pages by the subject instance rather than by the api10,
      so a subject held out at more than one origin keeps its rows at a page boundary
- [Fix] web: a label column declared as a series projection rendered as a figure with no
      handle; the type-curve grid carried twenty-eight naked-number badges and now carries
      none, and the control_unavailable reasons are a default column
- [Fix] web: a composite row identity is addressable by a detail operation whose single
      path parameter names one of its pointers, so the type-curve detail pane opens
      instead of reporting that the row supplies no value for it
- [Fix] web: a nested block whose leaves are figures renders as figures rather than as a
      pre block of its JSON, so the publication receipt's acceptance gates and support
      distribution are explain affordances rather than printed handles
- [Fix] api: a forged cursor whose tiebreak is not an ISO-8601 date is a malformed cursor
      rather than a 500; cursors are unsigned, so the tiebreak is caller-controlled text and
      this is the only site in the codebase that parses one
- [Change] api: register_response_figures walks and rebinds Series alongside Figure,
         recording the whole array and its unit as selector evidence; a series without a
         selector, or one carrying point handles, is refused rather than silently skipped
- [Change] api: unregistered_artifact drops emitted=false in the phase that first raises
         it, and the served description states the control is a backward-looking peer
         aggregate over a held-out arm rather than a forecast
- [Change] docs: STATUS, ROADMAP, ARCHITECTURE, README and SMOKE record N1 as served, the
         chain-depth headroom the contract tier cannot measure, and a re-publication of
         the P3 context as a restatement event
- [Fix] map: a tile or count refused for want of a session is a normal state, not a
      failure; 401/403 raises no banner, no toast and no console error, and signing in
      re-requests every data source and re-asks the counts, so the false "Tiles for
      nd_wells did not load" and "Well counts unavailable" no longer outlive the sign-in
      that answers them
- [Fix] sign-in now updates the header and session state from the session the login panel
      returns; the boot probe had already latched, so a signed-in reader was still shown
      as signed out
- [Change] login copy greets the reader and says what is behind the door, instead of
           describing what the deployment refuses; refusal messages still enumerate no
           accounts
- [Change] em dashes are out of user-facing copy: page title, share-card metadata, panel
           and banner text, empty and error states now read with a colon, comma or full
           stop; the absent-value mark and console diagnostics keep theirs
- [Change] report vintage moves off the default reading surface into a closed disclosure
           on the chart, and the "mixed report vintages" warning chip is gone; the fact is
           routine provenance, the derivation handle beside it is untouched, and the
           disclosure is re-read over the drawn window so it cannot claim a vintage the
           span dropped
- [Fix] an element carrying the hidden attribute is no longer painted: the UA's own
      [hidden] rule is UA-origin and loses to any author display, which left five
      .gw-hover-meta elements reserving an empty 8px band under every hover card. One
      author-origin reset replaces the 25 per-rule overrides that had accumulated and
      still missed them
- [Fix] the hover card's derivation handle no longer takes Tab: a focusable control
      inside an aria-hidden subtree is a control a keyboard reader reaches and hears
      nothing about. It keeps its click, and the same derivation still reaches the
      keyboard through the Layers panel
- [New] tests/e2e/hidden-display.mjs: asserts in a real browser that every element
      carrying hidden computes to display:none, read off the rendered document rather
      than a class list; happy-dom cannot see this defect class
- [Remove] the unpainted vintage attribute on gw-figure and the unread vintage field on
           the chart's readout row, with the uniformVintage plumbing behind them; the
           explorer grid now names several vintages on the one strap line it already used
           for a single one, instead of chipping every cell

<a id="v0.67"></a>
## v0.67 — 2026-08-30

- [Fix] verify.sh asserted that a caddy tunnel listener exists rather than that any listener
      on 8080 is loopback-bound, so a host with nothing on 8080 failed the deploy gate with
      a message claiming a binding it did not have; the negative stays unconditional
- [Fix] the documented glasswell-owner-bootstrap and glasswell-owner-reset commands run as
      root, where peer authentication resolves the role `root` and the connection fails
      before the password prompt; both now carry runuser -u glasswell

<a id="v0.66"></a>
## v0.66 — 2026-08-30

- [Change] blueprint: Cloudflare Access is not enabled on this account, so ingress is
           Cloudflare Tunnel only and authorization is the application's own session
           login; SB-06 §5 and SB-04 §3.1 amended, the ruled Access design retained as
           the design to reinstate
- [New] argon2-cffi pinned; Argon2id at t=3, m=64MiB, p=2, sized against the two-worker
      uvicorn RAM budget, with a floor assertion so the parameters cannot be lowered
- [New] the accounts migration adds lineage.users, lineage.sessions and
      lineage.login_attempts, with owner-created accounts only, session tokens stored as
      sha256 alone, and a CHECK that refuses any password hash that is not Argon2id
- [New] login throttling: per-account and per-IP backoff on a doubling curve capped at
      900s, a 15-minute time-boxed lockout, and a known-good-IP bypass so a flood from
      an unfamiliar address cannot lock the owner out of their own network
- [Fix] the client address is resolved from a Caddy-set edge marker, never from
      X-Forwarded-For; uvicorn runs with --forwarded-allow-ips '*', under which the
      leftmost X-Forwarded-For entry is attacker-controlled
- [New] infra/cloudflare: the edge range list, a weekly refresh unit that refuses to
      publish a shrunken list, and a misconfiguration detector that never grants trust
- [New] CSRF tokens bound to the session hash and HMAC-signed, so a token minted for one
      session cannot be replayed into another and a caller with no session cannot mint
      one; a missing signing key is a startup abort, never a disabled check
- [New] session login with two roles (owner, viewer) over lineage.users: __Host- cookie,
      server-side session records, rotation on login, sliding idle expiry under a
      never-extended absolute cap, and server-side logout invalidation
- [Fix] /docs and /openapi.json were served anonymously; both now require a principal,
      and the auth-matrix coverage test walks the router rather than the OpenAPI
      document so a reachable-but-undeclared route cannot recur
- [Change] the static owner key is refused on the tunnel listener, demoting it to a
           LAN and deploy-gate credential; issued api_keys rows are unaffected
- [Change] GLASSWELL_ALLOW_ANON resolves to the viewer role rather than owner scope, and
           the API refuses to start when it is set together with GLASSWELL_PUBLIC=1
- [New] owner-only account administration at /v1/users: create, list, change role, soft
      disable and reset a password, each an audit event; the last enabled owner cannot
      be disabled or demoted, guarded by a row lock rather than a handler-side count
- [New] the four ruled rate-limit buckets applied on the /v1 router set: 120/min
      interactive, 60 service, 600 tiles and 30 per resolved address for anonymous, with
      one uniform 429 and a Retry-After rounded to 30s so the bucket that fired is not
      named; global concurrency stays unmet and is recorded as such
- [New] HSTS over https only, at a year with includeSubDomains and no preload
- [Change] credential redaction widened to password, token, session and csrf query
           parameters and to any gws_ session token anywhere in a log record; the
           tunnel listener gains its own Caddy log block, since a site inherits none
- [New] retention sweeps expired sessions after their absolute cap plus seven days and
      login attempts after ninety, keyed on the cap so a live session is unreachable
- [New] infra: the cloudflared ingress publishes one hostname to the Caddy tunnel
      listener and answers 404 for everything else, so the tile server is not reachable
      through the edge; install.sh gains --with-cloudflared and mints GLASSWELL_CSRF_KEY
- [New] glasswell-owner-bootstrap creates the first owner account and
      glasswell-owner-reset is the lockout break-glass; both read the password from stdin
      only, never argv or the environment, and the installer calls neither, so no
      default credential ships
- [Change] the web app replaces the API-key panel with a session login: the form carries
           no action attribute and submits by fetch, because the app's own CSP ships
           form-action 'none'; a stale key in localStorage is cleared on first render
- [Fix] og:image and twitter:image are made absolute at build time from
      GLASSWELL_PUBLIC_ORIGIN, since Open Graph consumers do not reliably resolve a
      relative URL; unset leaves them relative, so the LAN deployment degrades sanely
- [Fix] the static owner key gets its own 600/min ceiling rather than the 60/min service
      bucket: deploy.sh runs verify.sh and smoke.sh back to back, 64 requests, so the
      deploy gate would otherwise throttle itself
- [Fix] the Caddy tunnel listener binds 127.0.0.1 instead of matching on a caller-supplied
      Host header, so it is not open on every interface and can actually match the
      connector; the adapted configuration is now asserted with caddy adapt
- [Fix] HSTS and upgrade-insecure-requests now reach the public path: the tunnel hop is
      plaintext loopback, so X-Forwarded-Proto is forced to https inside the proxy
- [Fix] /docs and /openapi.json are registered before the SPA mount, which shadowed them
      into a 404 in any deployment that serves a frontend
- [Change] /v1/keys* and the agent scope are marked deprecated with a stated removal
           target of the next major version
- [Fix] the two open session routes are bounded per resolved address, and a login already
      refused by the limiter is padded rather than run through a 64MiB Argon2id verify
- [New] the login bound is proved by test: the limiter runs before the CSRF check and
      before any password hashing, and deleting either call turns seven tests red
- [Fix] GET /v1/session is open and always answers 200: asking who you are is not a
      privileged question and "nobody" is a valid answer, so an uncredentialled caller
      gets kind: anonymous rather than a refusal on every first page load
- [Fix] the sign-out control carried the hidden attribute but a class rule set display,
      so it rendered for signed-out readers on every surface and overflowed the 320px
      rail; the session probe no longer fires on Status, which needs no identity

<a id="v0.65"></a>
## v0.65 — 2026-08-30

- [New] verify.sh reads the restore-drill receipt instead of only its timer: the receipt's
      schema head must equal the live head, and the receipt must be recent, so a drill that
      passed against a stale dump and a receipt that stopped updating both fail. The head
      comparison waits for a drill that postdates the newest migration, because the drill is
      weekly and a migration deploy would otherwise red the verifier until Sunday
- [New] Offsite push receipt at /var/lib/glasswell-backup/offsite.json — generation, dump
      identity, per-stream files and bytes from rsync --stats — plus an offsite_copy status
      job and verify.sh assertions over it; recorded from the sending side only, because the
      forge grant is rrsync -wo and this host cannot read the far side back
- [New] Replacement-host recovery drill, runbook, receipt shape, recovery_drill status job
      and stub-based unit tests; globals then dump then raw zone. It refuses the production
      database by case-folded comparison and a plain-identifier allowlist, and refuses the
      production host itself when the live database is present or the API is serving, with
      the probe failing closed. It has never been executed end to end and every surface
      says so
- [New] verify.sh asserts systemd units in the reverse direction: every glasswell-* unit on
      the host must be declared in infra/systemd, which the tree-walking loop could never see
- [New] glasswell-durable-write.py, the shared atomic receipt writer with the target-safety
      checks the restore drill established
- [New] The verify.sh receipt helpers are executed under bash against real files by
      tests/unit/test_verify_helpers.py, not only grepped for
- [Fix] The recovery drill's identifier allowlist and case-folding pin LC_ALL=C: under
      en_US.UTF-8 glibc collation [a-z] also matches fullwidth forms such as U+FF47, so the
      guard no longer depends on the ambient locale of the host it runs on
- [Change] remote_backup_copy disclosure moves from not_instrumented to limited and states
         the write-only read-back limit; a replacement_host_recovery disclosure states that
         the recovery path is mechanised and unexercised
- [Change] infra/README.md gains a durability-proofs section recording what each receipt does
         not prove, the removal procedure for the undeclared glasswell-repromote units, and
         the new coupling that a receipt it cannot publish fails the nightly backup
- [Fix] The restore-drill job measures its dump's staleness at drill time rather than against
      now, so a healthy weekly drill no longer degrades every Tuesday and refuses every deploy
      until Sunday; a drill that genuinely restored an old dump still degrades

<a id="v0.64"></a>
## v0.64 — 2026-08-30

- [Change] app chrome no longer hardcodes a coverage footprint: the page title is
         `glasswell — subsurface well intelligence`, the map's aria-label names laterals
         and surface locations, and the help panel and the OpenAPI `info.description`
         point at `/v1/status` dataset scope instead of restating a two-state string
- [Change] collateral de-scoped to match: the README hero badge reads coverage
         multi-basin and its opening paragraph drops the two-regime ceiling, `llms.txt`
         opens on reporting regimes rather than a basin list, and the og-card subtitle
         carries the capability line
- [New] `og:` and `twitter:` meta tags wired to the existing share card, so a link
      unfurl renders `og-card.png` at 1200x630 instead of falling back to the title
- [New] regression assertions pin the page title, the share-card tags, and the absence
      of any place name in the document head or the map's label

<a id="v0.63"></a>
## v0.63 — 2026-08-29

- [Change] roadmap: P7 reads built and gated rather than started and unpromoted — NM's
         three ingest paths, the C-115B staging terminus and the missing
         `canonical.wells`/`well_spatial` spine are named, so the gate is a decision
         about a product surface rather than a missing module
- [New] roadmap: a Next work section carrying the three owner-approved priorities with
      exit criteria in the phase-table idiom — serve the 5,211-line modeling layer under
      the derivation-handle contract, enrich the served views from data already held,
      and state expansion as the NM gate then Montana; each sits inside an existing
      phase and renumbers none
- [New] roadmap: Montana placed after the NM gate and before TX allocation v0, with its
      reasons — it extends the trained Williston rather than opening a basin, repairs
      the `^33` neighbour truncation that leaves ND wells at the state line with
      incomplete offsets, is the only candidate publishing both production grains from
      one regulator, and inherits the BLM PLSS grid on a scope change
- [New] roadmap: Oklahoma production tagged `data-unreachable` — no bulk file exists,
      the Tax Commission serves lease-grain history per record through a web lookup and
      a mailed form, and header-only coverage would ship wells that could never carry a
      production number
- [Change] roadmap: open question 11 stops reading as Texas-specific — PA, WV and OH are
         metes-and-bounds too, so `blm_plss.py`, `land_units`, `land_metrics` and the
         Protocol 4D township-inventory story do not port to Appalachia at all
- [New] roadmap: two open questions — the vintage cohort key as a conformance row rather
      than a query-level choice, and whether a six-month horizon justifies re-pinning
      `mdv1.4` and its accepted publication
- [New] roadmap: two known risks — state assumptions hardened into DDL where the mart
      module already parameterises them, and built-but-unserved work accumulating
      against the serving contracts it will have to meet
- [Fix] STATUS.md asserted two deployed versions at once: the header read
      `v0.61+e07db3d` at schema head 52 while the verification state read
      `v0.60+be8e234`; both now read the deployed `v0.62+204bebb` at schema head 54
- [Fix] STATUS.md carried 111 host checks in the P6 row and the verification state;
      the deployed instance passes 127, having read 109 / 18 immediately after the
      deploy with every failure in the Postgres tuning block
- [Fix] STATUS.md read "lease production, well allocation, and its validators are not
      built" for Texas, which buried `canonical.well_lease_links`; the row now states
      that the EWA load populates the Validator A well-to-lease crosswalk and that
      lease production is a registered source with no ingest module
- [Fix] STATUS.md listed land/spacing units among P2's remaining work, conflating no
      JSON endpoint with not built; both ship as tiles and the row now names the five
      published layers and marks `/v1/spacingunits` unserved
- [Change] STATUS.md separates "computed but not served" from "not built" on the
         serving surface: `src/glasswell/modeling/` is 5,211 lines under pinned
         `tcv1.0` / `fv2.0` / `mdv1.4` identities that no router imports
- [Change] STATUS.md records the v0.62 deployment: schema 53 and 54 registering
         publication evidence for `cr_tx_ewa_measures_1` and the three superseding
         API-10 identity rules, the ND neighbour mart at 7,958,550 edge rows over
         22,263 subjects, and CI green on the exact release SHA
- [Change] STATUS.md records the Postgres drop-in applied for the first time — 22
         settings live, `shared_buffers` 2GB→4GB — the 4 GiB swapfile SB-06 §2.3 asked
         for, and that the guest reports 12,179 MB rather than the 16 GiB the drop-in
         was sized against
- [Change] STATUS.md states that the New Mexico OCD staging schema exists and is
         unpopulated, and that the benchmark artifact contract is built with no caller
         outside its own unit test
- [Fix] The two-clock migration test compared a `published_vintage` PostgreSQL stamps from
      its own `current_date` against the host's `date.today()`, so it reddened on any
      workstation west of UTC for the hours between UTC midnight and local midnight. It
      reads `utc_today()`, the helper added for exactly this, whose docstring already
      described the defect
- [Fix] The well card's "Rows for this well" returns the well. The card built its link
      from the API-10 and put it in `f.q`, a filter that matches well names only, so the
      crossing landed on an empty grid for every well ever built and no test noticed —
      the one that checked the link asserted it emitted `f.q`, which is the defect
      written down as an expectation
- [New] `GET /v1/wells?api10=` resolves the identity spine: matched whole, one well or
      none, never as a prefix or a fragment. It also takes the fourteen-digit literal,
      matched against the API-14 canonical records for the well rather than trimmed to
      ten at the route — which digits of an API-14 make the API-10 is an identity rule's
      declaration, so a completion this deployment never recorded answers with an empty
      page instead of with a guess
- [Change] The row hop into the wells collection narrows by `api10` rather than by `q`,
         and the map search box sends a pasted API-14 to that filter instead of to the
         name search the path cannot take; `q` stays what its served semantics say it is
- [New] `tests/contract/test_crossing_targets.py` reads the crossing table the browser
      ships and issues it against the API, so a filter that cannot match the identity it
      is handed fails in the suite rather than on a reader's screen; the explorer's own
      check that a crossing names a parameter the operation takes is what a name search
      handed an API-10 satisfied

<a id="v0.62"></a>
## v0.62 — 2026-08-29

- [Fix] API-10 normalisation is one registry-driven decision instead of three loaders
      disagreeing: FracFocus hardcoded the digit count, the slice, the state code and the
      state name that `cr_ff_api_identity` already seeded, so `/conformance` described a
      rule row that governed nothing
- [Fix] A dashed identity no longer keys under FracFocus and the ND MPR while
      quarantining under ND GIS surveys; no identity rule row said whether a published
      API literal may carry punctuation, so `33-053-03901-00-00` was an identity under
      one rule and `key_incomplete` under another. The survey and MPR keys meet at one
      checkable predicate — `/v1/wells/status-summary` reads `canonical.well_spatial`
      with no `geom_type` filter and classes it against `canonical.production_monthly`
      on `api10` — where the separator decided whether the well appeared from this
      source at all, not how its key was spelled
- [New] `cr_ff_api_identity_2`, `cr_nd_api_identity_2` and `cr_nd_survey_api_identity_2`
      supersede their ancestors and declare the separator set explicitly, evidenced from
      the FracFocus data dictionary's own `xx-xxx-xxxxx-00-00` template; they correct on
      knowledge time and keep the ancestor's valid time, so a replay at an older report
      vintage reads the corrected row rather than the one that never said; migration 054
      registers their publication
- [Change] Only the two declared separators are removed before an API-14 is read, where
         the FracFocus and ND MPR loaders previously deleted every non-digit character;
         `API 33053039010000` and `33053039010000 (amended)` keyed onto a real well and
         now quarantine under their declared reason code
- [Change] `glasswell.identity` reads the identity spec off the rule row and refuses a row
         that leaves it unstated, so an undeclared identity decision fails at the registry
         rather than being invented per loader
- [Fix] restore drill: a scratch-cleanup failure no longer overwrites the cause that came
      first, so result.json still names the unrestorable dump while scratch_removed carries
      the cleanup miss
- [Fix] backup retention: a generation now expires as a unit on its dump's mtime, manifest
      first, so a generation straddling the cutoff can no longer strand a manifest without
      its archive and abort the next restore drill with manifest_dump_missing
- [Fix] backup retention: a prune that cannot delete now fails the run after the offsite
      push instead of logging a WARN and exiting 0, so OnFailure fires before the disk fills
- [Fix] verify.sh: the retention-sweep and status-collector result assertions now check run
      evidence; systemctl show -p Result answers success for a unit that is absent or has
      never run
- [Fix] The knowledge clock is read in UTC everywhere rather than from the host, so a machine
      west of UTC no longer spends its evening unable to see rules PostgreSQL published today;
      every registry lookup returned empty in that window and callers quarantined rows they
      should have resolved, recording the run as normal
- [Fix] The map legend's producing counts are wired to the response that carries them; the
      section was built, tested and never called, so it could not render at all
- [Fix] `rate_limited` is served as a code this slice emits, which it does — `/v1` and
      `/v1/errors/{code}` published `emitted_by_this_slice: false` for a code the wells router
      raises
- [Fix] assets/lineage.svg names the served `/v1/explain`, `/v1/conformance` and
      `/v1/quarantine`, replacing a `/quality` namespace that has never existed, and puts the
      unbuilt `/scorecard`, `/recipes` and `/audit` on the designed line under their blueprint
      names
- [Change] Architecture records the lineage-retention timer and the spacing-units tile view,
         security policy stops describing the project as pre-build 42 tags in, and status,
         roadmap and llms.txt carry the deployed v0.61 at schema head 52 with re-measured
         suite sizes
- [Change] The Postgres tuning drop-in is resized for VM 111 as it runs — 8 vCPU, 16 GiB
         resident, PGDATA on the ssd-pool — rather than for the 8 GiB balloon floor.
         Allocations still assume the floor is reachable, because the balloon reclaims page
         cache and never the shared-memory segment; planner hints do not, because they
         allocate nothing. `shared_buffers` 2GB to 4GB, `effective_cache_size` 6GB to 12GB
- [New] Thirteen settings the drop-in never carried, for a database that has grown 18x and
      has a 17.6M-row promotion queued: WAL sizing (`wal_buffers`, `min_wal_size`,
      `max_wal_size`, `checkpoint_timeout`) against a bulk promotion that writes ~12 GB of
      relation data through a 1GB checkpoint trigger; parallelism capped at four workers
      plus the leader, which is C26's five-of-eight-vCPU batch cap; and autovacuum reach
      for tables whose `reject_mutation` trigger makes insert-driven freezing, not bloat,
      the risk
- [Change] `work_mem` 32MB to 64MB, bounded by martin's `pool_size` of 10 and the
         cluster-wide parallel-worker cap rather than by `max_connections`, and
         `autovacuum_work_mem` pinned at 256MB so raising `maintenance_work_mem` to 1GB
         cuts the autovacuum burst from 1.5 GB to 0.75 GB instead of tripling it
- [Change] `max_connections` 60 to 80: there is no connection pool, so one map pan's
         tile-proxy requests take 12-24 of the 57 usable and martin's pool takes 10
- [Fix] `infra/README.md` said the tuning was shipped but not applied. It was applied on
      2026-08-20 at 15:25:57 and an independent gate read `shared_buffers` back off the
      running server the same afternoon; the claim outlived the fact by eight days. The
      section now separates what was measured from what nobody has confirmed, and no
      longer asserts a state without evidence
- [Fix] `verify.sh`'s tuning block counted nothing, so a drop-in reformatted to `key=value`
      matched no line and produced output indistinguishable from a pass (F28). It now
      asserts that at least one setting was checked, and its parser tolerates an inline
      comment and a digit in a setting name
- [New] A measurement runbook in `infra/README.md`: the SQL for database and relation
      sizes, cache hit ratio, connection high-water, checkpoint counters and autovacuum
      reach, the apply sequence including the 4 GiB swapfile SB-06 2.3 asked for and
      provisioning never created, and which four values to re-check once real numbers
      come back
- [Fix] `infra/README.md` said martin publishes three function sources in four places,
      one of them a runbook command asserting `expect exactly three ids`. The roster has
      been ten since the land-grid and TX layers landed, so that check failed on a
      correct host; the martin role's grant spans migrations 026-035, not 026 alone
- [Fix] The swapfile runbook step appended to `/etc/fstab` unconditionally inside a step
      documented as rerunnable, so a second run duplicated the entry and `fallocate`
      failed on a swapfile already in use. Both halves are guarded
- [Change] The applied-state paragraph names its evidence as internal deploy and gate
         records under the git-excluded `work-output/`, rather than citing paths a
         repository checkout cannot resolve
- [New] TX wellbore: a depth or completion date the parser cannot read is quarantined
      per field as `unreliable_numeric` or `out_of_range_date`, carrying `filed_as`,
      `field_action` and the row's ordinal, so a filing the reader failed on is no
      longer indistinguishable from one the regulator never made
- [Change] `WellboreLoad.quarantined` counts the two new reason codes rather than
         reporting zeroes for a class the loader never produced
- [Fix] a blank TX measure stays an absence and is not quarantined, and the well still
      promotes with the field null rather than being dropped
- [Fix] the service index publishes its promotion row counts with the derivation handle
      `/v1/vintages` already gives them, retiring two allowlist exemptions written
      around the gap rather than around a ruling
- [Fix] `register_manifest` refuses the same bytes under a second (source_id,
      source_key) instead of returning the incumbent's manifest, so a slot can no
      longer inherit another slot's provenance and resolve `/explain` to the wrong
      government file; `ManifestConflict` is raised rather than dead
- [Fix] an ArcGIS layer matching no features is refused as `EmptyWalk` rather than
      sealed as a zero-byte artifact whose hash every empty harvest shares
- [Change] raw-zone staging is scoped by source slot, not by content hash alone, and
         the reuse-or-place block is one helper shared by the HTTP and ArcGIS
         registrars, refusing before the payload is moved into place
- [Fix] the ND re-promotion and the NM production promotion record the derivation that
      promoted them on their vintage-day ledger row, and a run carrying none no longer
      overwrites the one the ledger already holds
- [Fix] a vintage row no derivation promoted withholds `rows_examined`, `rows_appended`
      and `restatement_summary` as null on `/v1` and `/v1/vintages` rather than serving
      counts no handle can explain; a promoted row is unaffected
- [Fix] TX identity promotion refuses a layout that no longer declares a measured
      column instead of reading it as absent and nulling the field on every well
- [New] TX withholding is registered as `cr_tx_ewa_measures_1` — the withheld fields,
      their reason codes and `field_action` are read from the rule row, both quarantine
      calls and the promotion derivation cite it, and an action the loader cannot
      execute is refused
- [Fix] the ArcGIS empty-layer test names its true motivating source, the two
      `blm_plss` slots on one scoped MapServer, not `tx_gis_wells_county`, which
      fetches over `mft_guid_resolve` and never walks an ArcGIS layer
- [Fix] verify.sh: an empty tile roster and an unparseable martin catalogue are each
      their own named failure rather than compared to each other; both sides came from
      a command whose stderr is suppressed, so a venv that cannot import the marts and
      a martin that answered nothing read as ok while the per-layer loop ran zero times
- [Change] verify.sh: the deploy-hygiene sweep reads compgen output line by line rather
         than word-splitting it, so a stray path containing a space stays one path
- [Fix] app.env.example pins the lockfile fingerprint requirements.lock actually has;
      the shipped value was fifteen releases stale, and install.sh copies it verbatim to
      /etc/glasswell/app.env, so a fresh host stamped every lineage node with a false
      environment and P3 publication refused outright on lockfile_stamp_mismatch
- [Fix] workstation-hygiene.sh: the orphan-volume probe suppresses stderr like every
      sibling docker call in the file, so a daemon warning is no longer counted as a
      volume; the container age is converted from docker's prose and compared against
      CONTAINER_MAX_HOURS, anchored on the age field, rather than against a baked-in
      regex that ignored the threshold and matched a container merely named "days"
- [Fix] scripts/experiments/lib.sh: gw_psql resolves the DSN and reads the status back
      before calling psql; gw_die's exit fired inside `$(gw_dsn)`, terminating only the
      substitution, so an experiment could print a VERDICT computed from whatever PG*
      pointed at
- [New] the lockfile fingerprint app.env.example pins is asserted against
      requirements.lock, so a dependency bump cannot leave every lineage node on a
      fresh host carrying a false environment stamp
- [New] the fingerprint test also binds the pin to the env var and the lockfile path the
      publication gate reads, and to install.sh seeding the example unchanged, so a
      rename cannot leave the digest assertion green and inert
- [Change] every 2>/dev/null in workstation-hygiene.sh carries its justification on its
         own line; it was the repo's sole outlier on that rule
- [New] deploy.sh step 7d polls martin's /catalog, the endpoint verify.sh reads, before
      the gate runs; martin loads its whole source catalogue from PostgreSQL at startup
      and answers /health before it is populated, so the per-layer assertions could fail
      a deploy that was fine
- [Change] both deploy.sh readiness loops count arithmetically instead of word-splitting
         `$(seq 1 30)`
- [Change] both martin guards distinguish a failed read from a successful empty one: an
         import or parse failure and an empty TILE_LAYERS or empty tiles list are
         separate refusals, so the reason names the fault the operator has to fix
- [Fix] deploy.sh's martin wait parses /catalog and requires a non-empty tiles list; it
      matched the string "tiles", so `{"tiles":[]}` satisfied the wait it exists to
      outlast and verify.sh failed immediately after
- [Fix] The health contract was seven days from reddening on a calendar date rather than a
      code change: `tests/support/seed.py` pinned the artifact clock at 2026-08-01, and
      migration 050's 35-day cadence turns an artifact older than its interval `stale`
      when no durable attempt proves a check. The vintage stays pinned, because served
      figures assert on it; the freshness clock is now relative to the run
- [New] A ratchet asserting the seeded artifact is younger than the shortest cadence the
      migrations declare, so the same fixture cannot age out again unnoticed
- [Change] Gate G9's tree invariant — A1b's block is 020-024, versions contiguous from 1 —
         is its own test and never skips; the status-file lookup is separate and resolves
         the artifact across both of its known homes. The gate had skipped itself since
         the wave-1 archive move, in the exact environment its stated reason claimed it
         should run in, while two status files recorded it as PASS
- [Fix] Two contract ratchets could pass over a feature that no longer existed, and now
      count what they measure
- [Remove] `lateral_ordinals` in the ND GIS fixture cutter ignored the reader it was
         handed and returned the same `range(RECORD_COUNT)` its sibling call site inlines,
         under a docstring describing two records rather than three hundred
- [Fix] `STATUS.md`'s verification counts are derived from the suite rather than carried
      forward from the previous release: 2,916 Python tests with one skip and 1,290 web
      tests across 86 files, where the ledger had stated 2,817/2 and 1,274/85. The
      figures had gone stale because the release marker was edited and the numbers
      beneath it were not
- [New] `web/src/chrome/handle.ts` is the one builder for R6's ⌾ derivation affordance, owning
      `EXPLAIN_EVENT`, the button's shape and the accessible contract it carries
- [Fix] The ⌾ handle names the figure it explains before any derivation arrives; the map hover
      card and the thematic key set no `aria-label` until their tile answered, so a screen
      reader met an unnamed button, and both blanked the name again whenever the handle went
      away
- [Change] The derivation id rides `title` rather than the accessible name, so assistive tech
         is read "Lineage for these cell figures" instead of an opaque handle string; the
         handle is visible exactly when it has a derivation to resolve
- [Change] The seven hand-built copies of the affordance — layer panel, legend, hover card,
         thematic key, well card, chart and `<gw-figure>` — are routed through the shared
         builder, with the chart's callback form, the legend's `<label>` cancellation and the
         element's host dispatch kept as declared options rather than private redrafts
- [Fix] `card.ts` registers `<gw-figure>` by an explicit side-effect import; it had been
      relying on a named import for the custom element's registration
- [New] `explainHandle` refuses a label that already carries the "Lineage for" prefix — the
      test build throws and the dev build logs, as `<gw-figure>` does for a naked number — so a
      caller cannot name the button twice; every label is interpolated from data, so the rule
      has to be checked rather than remembered
- [Remove] Dead web code first reported at v0.47 and still present at v0.61: `DIALECT_TITLES`,
      `isGlossaryLoaded` and the write-only flag behind it, the unreachable hidden-column badge
      in `renderHeader` with the two `gw-col-hidden` rules it took with it, and the always-true
      conjunct in the explorer detail's `omittedFrom`
- [Remove] Three unread test fixtures — `glossaryIndexEnvelope`, `glossaryTermsEnvelope` and
      `errorTypeEnvelope`; the recorder's `DETAILS` entry for the last one goes with it, so the
      deletion is not undone the next time fixtures are recorded
- [Remove] The `absoluteTileUrl` and `baseStyle` re-exports from `map/map.ts`, which nothing
      imported, and the orphaned `.gw-explore-eyebrow` rule

<a id="v0.61"></a>
## v0.61 — 2026-08-28

- [Fix] Well card, monthly production: the ND back-load took this well's axis from
      6 months to 131 and the chart was designed against 6. One month's tap target
      measured 2 CSS px across — three rows of 131 buttons sharing 426 px — so the
      state a reader wanted could not be hit, and three streams at 131 points over
      426 px drew a scribble
- [New] The pointer now resolves to the month nearest it across the whole plot
      rectangle and the whole state band, one hit surface instead of 393, and the
      month it lands on is read out below the plot: every stream's volume, unit,
      report state, report vintage and its own derivation handle. The handle and
      the month stepper are 44 px targets, and the stepper is the keyboard path a
      canvas hover never had
- [New] A range control on the card's chart — 1 year, 2 years, 5 years, All —
      offered only where the record is longer than the span, so a well with six
      months is never asked to choose between two identical charts. Nothing is
      aggregated, binned or downsampled to fit: the window is a view over the
      served series, every drawn point is one month at its own value, and widening
      it costs no request
- [New] The card states the window it is drawing — "showing 60 of 131 months on
      record", both ranges, and that the rest is one click away. A chart showing
      part of a record while implying it shows the record is a naked number wearing
      a time series (R6)
- [Change] The default window is anchored on the last month on record rather than
         on today, so a well that stopped producing in 2015 draws its own last five
         years instead of an empty chart, and it windows by calendar span, so a
         gappy record reports the months it actually holds in that span rather than
         the span's length
- [Change] The four report states are drawn as one band per stream aligned under
         the plot rather than a row of buttons beside a label: it starts and ends
         where the plot area does, measured off the plot rather than assumed, and a
         reported zero is a bar of zero height inside its own cell, which survives
         at five pixels where a hollow outline did not
- [New] "Open this series" lands on the plot as well as the rows: the explorer
      redraws the series at the panel's width, 760 px against the card's 426, from
      the response the grid already fetched, with the same month readout and the
      same handles. Its window is the stream, from and to facets, which ride the
      URL, so the plot grows no second control a shared link would not carry
- [New] A collection whose operation declares a sort order can be reversed on the
      explorer, offered only where the server has no next page to give — a
      descending page one whose next link walks the ascending order would be a claim
      the collection does not make. The direction rides the URL, and is absent from
      it while it is the server's own
- [Fix] The series' own warnings, including the series_spans_derivations line
      naming the derivations behind a column, moved out of the element the chart
      replaces; a span change or a theme repaint used to take R8's disclosure down
      with the plot it had been appended to
- [Fix] Each chart repaint left its predecessor's resize observer and theme
      listener alive, so a surface redrawn N times observed and rebuilt N times.
      One live chart per host now, and the old one is torn down before the new one
      is built
- [Change] The card loads the chart on demand rather than from the entry chunk, so
         uPlot no longer ships to every reader whether or not a card is opened; the
         entry chunk falls from 46,330 to 21,340 B gzipped
- [Change] The bundle budgets are re-measured against that split: the entry falls
         to 22,500 B and the explorer route rises to 71,500 B, both at the ~5%
         headroom the convention in `web/PERF.md` states
- [Fix] A `row=` deep link on a descending page opened whichever row sat at the mirrored
      position rather than the one linked: the reversed array was matched against the
      index each row was built at
- [Change] Reconcile status, roadmap and machine-readable collateral with deployed
         `v0.60+be8e234` at schema head 51 and its exact release CI, 111 host checks and 20 API
         smoke checks, while retaining the pending schema-51 restore proof as an explicit gap
- [New] Producing classes on the well spine: `/v1/wells?producing=` scopes the collection to
      producing, not_producing or unknown, every well carries its class, and the class is
      defined by cr_producing_window_1, cr_producing_streams_1 and cr_producing_evidence_1
      rather than by a predicate in a query (R8); a class outside the three is refused
- [New] `/v1/wells/status-summary` counts the box by producing class, each count a figure with
      a derivation handle, beside `producing_window` stating the window, the qualifying
      streams and the oil+condensate liquids basis the counts are on
- [New] Producing read-out in the map legend: per-class counts with their own lineage handles,
      the window and basis stated beneath, and each class linking to the wells it counted
- [New] Migration 052 indexes canonical.production_monthly on production_month for well-level
      rows, which the window anchor reads once per request; it was a 288 ms sequential scan at
      7.2M rows
- [Change] The producing window is anchored on the newest filed production month, never on the
         wall clock: the monthly report runs about five months behind, so a clock-anchored
         window would class every well not-producing
- [Change] A well that filed nothing in the window answers unknown, not not_producing, as does
         one whose months the regulator withheld and one in a jurisdiction that reports at the
         lease; only a filed zero or a hydrocarbon-free filing is not_producing

<a id="v0.60"></a>
## v0.60 — 2026-08-28

- [Fix] The architecture document, contributing rules and architecture diagram name the
      served `/v1/quarantine` path and the real `staging.` table families, replacing a
      `/quality` namespace and a `stg_` naming convention the schema never used
- [Change] The architecture document separates resident marts and data-model tables from
         contracted ones, and names the systemd timers the deployed host actually runs
- [Change] Status and roadmap record the deployed recurring restore drill's own verified
         pass, and the resident reverse-FK index and completed neighbour replay, in place
         of the deployment gaps those items had been carrying
- [Change] The README API block covers every served operation family, and the project docs
         table links the two P3 evidence documents that only prose had referenced
- [New] Publish accepted P3 receipt `p3pub_8b434525d8c621762e31b06ca660bfcd` with
      unchanged `fv2.0`, `mdv1.4`, `tcv1.0` and split hashes, two byte-identical builds,
      independent receipt rehashing and 1.0798% control unavailability against the 5% ceiling
- [New] Validate every current selector-bearing API figure against a fail-closed persisted-output
      registry, with dedicated response derivations for computed well and viewport aggregates
- [New] Give conformance rules and lookup rows immutable publication evidence independent of
      valid time, and expose both clocks without hiding known historical rule versions by default
- [New] Persist source polls independently of ingest transactions with explicit new, unchanged,
      failed and interrupted outcomes and one source-specific cadence registry
- [New] Sweep successful unreferenced ephemeral lineage after 90 days from an always-armed,
      sandboxed nightly unit while retaining failed, permanent, recent and referenced derivations
- [Change] Show attempt outcome, next expected poll, cadence, retrieval and declared vintages,
         latest artifact identity, and bounded freshness reasons on Status and health surfaces
- [Change] Use the first published routing/rule set as the explicit baseline for source-data
         vintages that predate Glasswell, without admitting later backdated corrections
- [Fix] Prevent another source key's success from hiding a failed or interrupted key, and keep
      failure evidence bounded, redacted, database-safe and append-only
- [Fix] Keep response values outside derivation identity so a repeated request with different
      output hits the determinism gate instead of minting a second derivation
- [Fix] Keep retention progress safe around every foreign-key-owned ephemeral artifact, bind
      directly applied summary rules, and cap viewport provenance writes per principal
- [Fix] Align freshness cadence with the recurring units, treat unscheduled sources as explicitly
      owner-triggered, and refuse deployments that intentionally skip required migrations

<a id="v0.59"></a>
## v0.59 — 2026-08-28

- [Fix] Preserve the restore drill's implicit root credential so its constrained `SETUID` and
      `SETGID` capabilities can enter the PostgreSQL identity under the existing sandbox
- [Fix] Index the physical-neighbour mart's reverse subject foreign key so replacement no longer
      scans 7.96 million directed edges for each subject deletion

<a id="v0.58"></a>
## v0.58 — 2026-08-27

- [Fix] Give the restore drill a dedicated root-owned, Glasswell-readable state directory so a
      validated live restore can atomically publish durable Status evidence under its sandbox

<a id="v0.57"></a>
## v0.57 — 2026-08-27

- [New] Serve lineage-pinned current North Dakota physical neighbours in the API, well card,
      and Status inventory, with strict completion cutoffs and a non-analog warning
- [New] Add a fail-closed repaired-context publisher that verifies byte-identical P3 artifacts
      and persists an immutable deployment-identity-bound family receipt
- [Change] Bind each logical backup manifest to the dump's exported snapshot and schedule a
         freshness-checked weekly scratch-database restore with durable Status evidence
- [Fix] Validate completion and physical-neighbour lineage selectors against persisted
      derivation outputs, including strict URL-safe base64 identities

<a id="v0.56"></a>
## v0.56 — 2026-08-27

- [Fix] Status counts North Dakota wells with API state code `33`, matching canonical data,
        and now pins both ND and TX jurisdiction filters in the collector test suite

<a id="v0.55"></a>
## v0.55 — 2026-08-26

- [New] A third URL-backed Status surface joins live API and PostgreSQL signals to
      bounded infrastructure checks, scheduled work, exact-grain dataset inventory,
      platform identity, and registered-artifact age for every source
- [New] `GET /v1/status` reads a sanitized atomic snapshot produced by a mandatory
      hardened 15-minute systemd timer; deployment refreshes it before verification
- [Change] Source freshness is named as registered-artifact age rather than last-checked
         time, with unchanged fetches, source cadence, remote-copy evidence, and restore
         execution kept visible as observability limits instead of inferred success
- [Fix] Stale or invalid snapshots cannot preserve green infrastructure or job states,
      and the three-surface header keeps accessible touch targets at phone width
- [Fix] Migration 044 grants only migration-ledger reads to the API runtime role so the
      unprivileged scheduled collector can report the applied schema version
- [Fix] Stale sources and degraded checks now fail closed, jurisdiction-specific cards cannot
      mask older constituent data, and each inventory run uses one coherent read-only snapshot

<a id="v0.54"></a>
## v0.54 — 2026-08-26

- [New] `GET /v1/wells/{api10}/completions` serves FracFocus completion events separately
      from regulator completion-pool entities, source-scoped formation mappings, explicit
      null semantics, as-of guards, and derivation handles without joining unrelated keys
- [New] `GET /v1/formations` aggregates current source-scoped aliases into canonical
      formations with alias counts, basin and free-text filters, cursor pagination, and
      reviewed peer groups
- [New] Well cards show completion events and pool-to-formation context with independent
      loading, empty, and unavailable states; staging-only design measurements and formation
      tops remain explicitly unserved
- [Fix] Formation-alias uniqueness now includes the source namespace; historical well rows,
      geometry, completion context, and formation aliases honor their available knowledge,
      effective, and release dates without leaking future or unvintaged observations
- [Fix] Historical North Dakota single-pool completion observations now backfill only from
      staged pools joined to the same canonical manifest and API-10, restoring formation
      context without inferred geology or rewritten vintages
- [Change] P3 lateral readiness distinguishes 38 source-confirmed absent state laterals from
         recoverable measurements; survey traces, vertical segments, and spud dates remain
         prohibited substitutes under unchanged `tcv1.0`

<a id="v0.53"></a>
## v0.53 — 2026-08-26

- [Fix] Feature matrix `fv2.0` freezes formation at the earliest source month, publishes
      simultaneous conflicts as null, and makes the mutation-invariance test alter the
      completion source the feature actually reads
- [New] Every `fv2.0` partition carries immutable missing, conflict, anchor-timing, lag,
      and retrospective-vintage coverage whose hash is registered in the build recipe
- [Change] The formation registry records the measured 82-day median publication lag and
         keeps strict Glasswell knowledge history separate from reconstructed source time
- [New] P3 model-ready `mdv1.4` persists three-stream cum12/cum24 labels,
      producing-month curves, DB-backed shared splits, and immutable coverage and
      rejection artifacts under one registered D1 recipe
- [Change] E-6 now measures the intermittency guard at 16 months over 22,023 matured
         North Dakota wells using the canonical three-stream producing-month rule
- [Fix] Incomplete labels remain assigned without moving split knowledge cutoffs, while
      withheld/confidential and completion-after-production subjects are explicitly
      excluded instead of silently entering train, calibration, or test
- [New] P3 type-curve control `tcv1.0` runs absolute and per-1,000-foot
      empirical P10/P50/P90 curves for oil, gas, and water on the exact eight
      `mdv1.4` rolling splits under one permanent D1 recipe
- [Fix] The closed peer ladder now records monthly and cumulative peer counts,
      overlapping unavailability reasons, and explicit 60% rung-one and 5%
      control-unavailability acceptance results without widening failed cells
- [Change] P3 status now reports the resident control coverage miss separately
         from implementation completion; forecasts, models, and calibration
         remain unserved and unclaimed

<a id="v0.52"></a>
## v0.52 — 2026-08-26

- [Fix] Alias hydration now accepts legacy unscoped registry rows as fallbacks while
      preferring the rule's source namespace and rejecting mappings from other sources

<a id="v0.51"></a>
## v0.51 — 2026-08-26

- [Fix] Deploys always refresh the editable project install even when the dependency
      lock is unchanged, so new console entry points cannot be omitted from a release
- [Change] P3 status and in-app Help now report the measured resident ND readiness load:
         43,817 Williston wells, 17,563 anchored API-10s, and explicit nulls elsewhere

<a id="v0.50"></a>
## v0.50 — 2026-08-26

- [New] P3 ND readiness: FracFocus terms and every decompressed archive member are
      hashed before source-faithful disclosure staging; valid hydraulic-fracturing
      JobEndDate observations append as completion anchors with no spud fallback
- [Change] All 40 current ND MPR pool labels now carry reviewed, knowledge-vintaged
         canonical formation and benchmark-group mappings, with Three Forks distinct
         and ambiguous composites explicit as __other__
- [Fix] ND well promotion now records its Williston modeling-basin rule, preserves
      completion anchors across later GIS vintages, exposes post-v009 well columns in
      wells_latest, and registers single-pool completion entities instead of only
      multi-pool filings

<a id="v0.49"></a>
## v0.49 — 2026-08-25

- [New] P3 feature matrix foundation: the first `fv1.0` registry declaration,
      completion-anchor availability enforcement, pinned knowledge-time reads and a
      byte-reproducible content-addressed Parquet artifact with recipe and derivation
- [Fix] The matrix builder refuses empty, all-missing and conflicting partitions instead
      of publishing an artifact that overstates ND feature readiness

<a id="v0.48"></a>
## v0.48 — 2026-08-24

- [Fix] NM staging integration fixtures pin ZIP member metadata, so identical regulator
      documents keep one manifest identity instead of changing at a wall-clock boundary
- [Change] Layer panel: every row collapses to one line — label, provenance badge,
         out-of-scale mark and switch — with the subtitle, the per-source lines, the
         tiles-only statement, the crossing and the opacity slider behind a per-row
         disclosure; the 34rem cap is lifted to the space available. Measured at
         390x844: 1,806px of rows against a 505px viewport becomes 606 against 573,
         and 2 of 12 rows fully above the fold becomes 11 of 12 — every operable
         layer, both default-on layers included, at all five breakpoints
- [Change] Layer panel: a row matched by the filter opens itself, since the per-source
         strings the filter reads now sit inside the disclosure
- [Fix] Layer panel: Escape closes it, the Layers control carries aria-expanded and
      aria-controls, focus lands inside the panel on open and returns to the control
      on close instead of falling to <body>
- [Fix] Layer panel: the panel no longer covers the Layers button that opens and closes
      it — a measured 19.6 x 29px overlap that rendered the control as "ayers"
- [Fix] Layer panel: the row's derivation handle is a live explain button, as the same
      handle already is in the status legend and the thematic key
- [Fix] Layer panel: the layer switch meets the 24px target floor at 44 x 24, the
      basemap switcher no longer clips the focus ring on its end segments, and the
      bottom sheet clears env(safe-area-inset-bottom) as the card and drawer do
- [New] Layer panel: the rows whose counts come from a served snapshot carry that
      snapshot's derivation handle, so 43,817 points and 13,952 binned cells resolve
      through the explain drawer like every other figure
- [New] tests/e2e/chrome-fold.mjs: the map chrome's fold ratio, row height, panel
      occlusion, Escape and focus restore across the breakpoint ladder — geometry no
      gate in the repository measured
- [Remove] Layer registry: the LayerGroup field, declared and assigned on all twelve
         layers and read by nothing
- [New] P3 foundation: an append-only feature registry, declared availability guard,
      deterministic pad-group temporal split and content-addressed benchmark artifact
      schema now make the leakage and honest-loser contracts executable before model code
- [Fix] CI uses the official Node 24 majors of checkout, setup-python and setup-node,
      removing the retired action-runtime annotations without changing project runtimes
- [Fix] Release cuts now update and validate the README badge, status ledger, roadmap
      ledger, and machine-readable project summary atomically with VERSION and the changelog
- [Change] STATUS and ROADMAP record the fresh six-job hosted main pass after the P3
         foundation merge, including its zero-annotation result
- [Fix] Python CI's tile preflight names the current Martin publication contract
      instead of a removed test; the next hosted run passed all six jobs
- [Fix] The locked development environment includes Starlette's supported httpx2
      test transport instead of emitting its deprecated-httpx warning
- [New] STATUS.md is the tracked current-state ledger: shipped release and data
      baseline, per-phase boundary, immediate gaps and verified gate state
- [Change] README, ROADMAP, SMOKE, llms.txt, OpenAPI and in-app Help now distinguish
         the deployed ND production and ND/TX map from unbuilt modeling, economics,
         allocation, agent and inventory scope

<a id="v0.47"></a>
## v0.47 — 2026-08-23

- [New] Hybrid basemap: the archive's own road, place and water labels composited over
      satellite imagery, from the PMTiles extract already shipped — no new origin, no key
      and no CSP change, since the label data was always there and no symbol layer was ever
      constructed on the raster path
- [Change] Satellite imagery now reads from Esri World Imagery rather than USGS National
         Map, a swap and not an addition, so exactly one external origin stays named in the
         policy; measured, USGS serves nothing above z16 while the map reaches z18, so every
         z17-z18 view was a z16 tile stretched 4x
- [Change] The imagery source declares `maxzoom` 19 because that is the deepest level both
         basins in scope were measured to carry, not because the service stops there: the
         deepest level with real pixels ranges z17 to z20 by location and is not monotonic,
         so a region added later has to be re-probed rather than inheriting 19
- [Change] The map's own `maxZoom` rises from 18 to 19 to reach the level the imagery now
         serves, halving ground resolution to 0.2 m per pixel in both basins; a test holds
         it equal to the imagery ceiling, since below it a served level is unreachable and
         above it the map paints the service's grey placeholder with no error anywhere
- [Change] Every basemap option declares the substrate it is read against instead of having
         one inferred from its id; an option whose id is not a variant name used to resolve
         silently to the dark token row, which is slate labels over bright aerial
- [New] The hybrid's two substrates fail independently and are named separately: imagery
      unreachable keeps the labels and names the imagery host, an archive that cannot serve
      ranges degrades to the graticule and names the archive
- [Fix] The imagery credit is dropped together with the imagery it covers, so an attribution
      never renders over a canvas with nothing of that source drawn on it; the hybrid probes
      the origin before drawing either, and reports the loss from the resolve path, because
      a source that was never added raises no tile error for the banner to read
- [Fix] Well card: a served figure's provenance could not be reached by any user action. The card
      clipped its own tail with no scroll affordance at 1366, 1024 and 390, and the tail was the
      derivation disclosure — the `series_spans_derivations` warning naming the seven derivations
      behind the production column — along with the chart's axis and the null-semantics key. The
      shell caps and the body scrolls, but `card.ts` renders both inside an `<article>` that sized
      to its content, so the body never had a height to scroll against; the cap now reaches
      through it and every handle is reachable at every breakpoint. A handle nobody can get to is
      a naked number with a footnote
- [Fix] Escape closes one layer: an open glossary popover, help panel or search panel now
      keeps the well card and the lineage drawer beneath it standing, instead of spending one
      key on two surfaces at every breakpoint
- [Fix] Tile-failure banner: sized to its sentence rather than to half the viewport, and
      dropped clear of the ⌾ coach mark, which covered the fault line at every width but 1600;
      at phone width the banner and the pill strip stack in one column clear of the zoom column
- [Fix] Thematic key reserves the status key's column at phone width, where the two keys
      overlapped and the choropleth key covered nine status counts and their ⌾ handles
- [Fix] Glossary and exempt-count popovers share one placement helper that clamps them into
      the viewport and states the height they may use, so a long definition folds rather than
      running past the bottom edge
- [Change] Map chrome takes its layer from the z-index ladder token rather than a literal, and the
           fault banner's raw rung drops to the local value its sealed stacking context actually
           needs: 8 read as a ladder rung between the chrome's 5 and the panels' 10 while ordering
           nothing but the banner against its own chrome siblings

<a id="v0.46"></a>
## v0.46 — 2026-08-23

- [Fix] source comments in the land-grid thematics, the layer registry, the land
      metrics mart, its unit test and migration 034 carried research provenance
      from the blueprint 8.2 carve-out corpus, which is git-excluded — the
      pointers dangled as well as leaked; the properties they justified are
      restated in the project's own voice, with no behaviour change
- [Change] migration 034's comment scrub changes the file's sha256, which
         `public.schema_migrations` records; an environment that already applied
         034 needs its recorded sha updated or `glasswell-migrate` refuses the
         run, by design — no DDL changed and no re-run is required
- [New] the `collateral` CI job rejects carve-out material in tracked source,
      beside the AI-attribution check; the token list is deliberately narrow to
      stay false-positive free and carries a note on extending it
- [Fix] DR-17: ND promotion no longer reads canonical.production_monthly whole. The head
      map behind change-only append, and the same-vintage map behind the divergence
      refusal, were both keyed by every row the table holds and both were rebuilt for
      each of the 125 back-load workbooks; each is now scoped to the entity-months being
      promoted, which is exactly the set the lookups ask about. Measured at 397,041
      resident heads: 394.3 MB against 102.4 MB, and flat rather than linear as further
      months land
- [New] tests/integration/test_nd_heads_scope.py pins the scope: the map holds only the
      month being promoted, does not grow as further months land, answers what a read of
      the whole table answered, and refuses a lookup it never covered rather than
      reporting that head as absent — which would append a restatement as a first
      observation
- [New] the UTC-midnight straddle is pinned at both tiers: months whose sessions open
      either side of midnight keep a lineage.vintages row per knowledge day, each
      carrying only the months that landed under it, and the driver summary reads both
      rows back rather than filing the walk under the day it started

<a id="v0.45"></a>
## v0.45 — 2026-08-23

- [New] NM OCD C-115B natural gas waste capture (M1-9): glasswell/ingest/nm_c115b.py
      walks the well-level flaring and venting layer through arcgis_rest_paginate,
      preserves the assembly as one manifested raw artifact, and loads
      staging.nm_c115b_upstream; migration 036, staging terminus by design
- [New] glasswell-c115b.service and .timer, monthly on the 12th with Persistent=true;
      reporting_period is a rolling ~13-month window and a month that rolls out is
      unrecoverable from the endpoint, so a missed fire is caught on the next boot
- [New] five conformance rows for nm_c115b_upstream: source selection over the stale
      OCDView/Venting_Flaring demo layer, the walk order, the dashed-API-10 to API-10
      normalisation, the F/V waste vocabulary in lineage.nm_waste_type_map, and the
      NAD83 to EPSG:4326 transform
- [Fix] arcgis_rest_paginate walked every layer ordered by OBJECTID, which the C-115B
      layer assigns per query rather than storing; a resultOffset walk over it re-read
      and skipped rows while count_before, count_after and features_written all
      reconciled. Callers may now declare a stable total order; the default is
      unchanged, and a repeated identity key inside one harvest quarantines as
      duplicate_row
- [Change] infra/verify.sh asserts every glasswell-* unit in the tree is installed and
           byte-identical to it, so a unit added to infra/systemd but not to
           install.sh's placement loop fails verification instead of silently never
           running
- [Fix] DR-17: infra/load-nd-months.py no longer writes a vintage row of its own at
      the end of the walk — ingest_month's record_vintage_day already checkpoints the
      knowledge-day row after every month, so the driver's union overwrote accumulated
      counters and, on a walk that crosses UTC midnight, filed both days under the last
      one; the summary now reads the ledger back instead of reporting from memory
- [New] the back-load driver survives an unattended multi-hour run: --resume skips
      workbooks already staged for this source (asked of lineage.manifests and
      staging.nd_mpr_oil, not a state file), --log-file appends every progress record
      to a file that outlives a dropped ssh session, and --raw-root states in the log
      where the fetched bytes landed rather than inheriting a CWD-relative default
- [Fix] one unreachable or malformed workbook no longer ends the walk: the month is
      rolled back, reported with its error on the progress stream, and the remaining
      months continue, with a non-zero exit naming what failed
- [Fix] SIGTERM and SIGINT stop the back-load at a month boundary rather than mid
      transaction — the polite pause waits on an event, which a signal clears, instead
      of time.sleep, which PEP 475 restarts for the remainder of the interval

<a id="v0.44"></a>
## v0.44 — 2026-08-22

- [Fix] SMOKE.md's absence list stops claiming no Texas and no New Mexico: Texas wells
      and wellbore identity have been on the map since the TX slice, so the line now
      scopes the absence to Permian production and allocation, which really are North
      Dakota only
- [Change] ROADMAP.md is regenerated against the nine-phase P0-P8 model: v0.6 phase
         names, fully-stated contents and exit criteria, the traceability table, the
         cut order with the field-notes reader, and the re-estimated ~32-weekend
         timebox with the argument for why the earlier 17-19 figure did not survive
         inspection
- [Fix] ROADMAP.md no longer reads "pre-build. Nothing in P0 has started" 24 tagged
      releases after P0 started; status is stated per phase against that phase's exit
      criteria, including the two gates that are open by measurement rather than by
      opinion - P3 needs 120 production months and six are resident, and P7's NM rows
      are ingested but unpromoted
- [Fix] TX lease production is stated as unbuilt P7b scope. It is scheduled work under
      blueprint 7.1 P7b (OG_LEASE_CYCLE via PDQ_DSV.zip), not a licence exclusion; the
      RRC licence question in the tree scopes to one coordinate-source provenance
      field, under which 359,421 TX wells are already served. The redistribution
      exposure is now its own risk row, over the TX stack, explaining nothing about
      what is or is not built
- [Fix] The P3 back-load span and workbook count are both quoted from the contract with
      their disagreement named - that span is 125 months, not 134 - and left open
      against the contract rather than silently corrected in a derived document
- [Change] assets/roadmap.svg carries nine phases. The four-across, two-row grid could
         not absorb a ninth card legibly, so it is a three-by-three grid at 322 px per
         card with the cut-order and never-cut panels stacked full-width beneath it;
         band colours, canvas fill and the aria-label follow BRAND.md
- [Fix] README.md's roadmap image alt text and documentation-index row name P0-P8

<a id="v0.43"></a>
## v0.43 — 2026-08-22

- [New] /v1/wells serves geometry_provenance on every collection item — the distinct
      classes of the well's recorded geometry, canonical geom_type verbatim under
      cr_nd_geometry_provenance_1 — and gains the matching filter, verbatim equality
      on any of the well's geometry, wired into the cursor fingerprint and the served
      next link with both refusal directions under test (m13 residual, the R-1 pattern)
- [New] /v1/wells/status-summary classes the box two more ways: wells per
      geometry-provenance class and per reported well-type code, each a figure with
      its own handle and the classing rule linked, so registry coverage statements
      (traced wells, disposal-code counts) derive from the API instead of pinned
      constants (m13 residual / m17 R-3)
- [Change] api follow-on residuals closed in the test tier: the vintages page-link
         byte assertion now derives from the page's own promotions and is proven
         against a second seeded promotion rather than depending on the single-
         promotion fixture (RN-2), and the parser-symmetric fragment shapes
         (%23h=, #h%3D, ##h=) are documented as naming no h key to any parser,
         with their decoded neighbours proven refused (RN-1)

<a id="v0.42"></a>
## v0.42 — 2026-08-22

- [Fix] the legend's vocabulary note opens with the licence pair itself — the ND
      provenance and TX RF-1 sentences now precede the status-colours preamble, not
      just the symbology prose — so the TX sentence tail clears the note's internal
      fold on open at 390 without scrolling (visual-m24 O2); the order pin moves
      with it and the fold cap is pinned unchanged

<a id="v0.41"></a>
## v0.41 — 2026-08-22

- [Fix] DR-89: nd_gis and blm_plss promotion guards consult manifest and staging
      identity instead of canonical row ownership — the class DR-88 closed for TX —
      so a revised extract whose rows all conflict is detected: its refused rows are
      quarantined as key_collision at stage join, reports and the vintage ledger
      carry rows actually appended from insert rowcounts across all four ND layers
      and both land grains, and a reload of already-processed bytes short-circuits
      as unchanged instead of re-promoting forever

<a id="v0.40"></a>
## v0.40 — 2026-08-22

- [Fix] M2-4, VF-5 as a class: map line colours join the variant machinery the labels
      already ride — a context line declares its role (boundary, grid, graticule) where
      it is defined and the styling pass recolours whatever is marked, retiring the
      hand-kept id list; the PLSS land-grid lines key to a per-variant grid token
      (white over satellite imagery, where the one shipped constant measured ~1.1:1)
      and a class test refuses any literal-coloured line that names no role
- [Fix] the legend's vocabulary note leads with its two licence-class sentences — ND
      provenance served verbatim, the TX RF-1 exclusion — and the note deepens to
      min(28vh, 12rem), so both read on open at 390 (visual-webpolish O2)
- [Fix] the one-shot coach mark no longer covers the zoom "+" at 390: the top-right
      control cluster yields while the hint shows, the same clearance treatment the
      layer pills received (visual-webpolish O1)
- [Change] the disposal ring's stroke ladders are pinned by test — base 1.2/1.6/2.2,
         selected 2.4/3/3.8 (gate-webpolish R3) — and the three unit-label layers
         build from one shape instead of three forks

<a id="v0.39"></a>
## v0.39 — 2026-08-22

- [Change] DR-87: nm_ocd's inline `_record_vintage` delegates to the shared
         `ingest.base.record_vintage_day`, deleting the duplicated accumulate/dedup/
         union/no-op-guard logic; a characterization test pins the exact same-day
         ledger rows byte-for-byte across the swap
- [Fix] DR-88: TX promotion guards consult manifest and staging identity instead of
      canonical row ownership, so a revised manifest whose rows all conflict is
      detected — its refused rows are quarantined as key_collision — rather than
      silently reported as promoted; tx_gis/tx_wellbore reports and the vintage
      ledger now carry rows actually appended, and a reload of already-processed
      bytes short-circuits as unchanged instead of re-promoting forever

<a id="v0.38"></a>
## v0.38 — 2026-08-22

- [Fix] the hover card places edge-aware: it flips left of the cursor at the right
      edge, above it at the bottom, clamps inside the canvas and steps around the
      on-canvas thematic key when a corner clears it — every hover surface, every
      breakpoint (visual-m13, visual-m23 V-1)
- [Fix] the "Click any ⌾" coach mark no longer sits on the first layer pill at phone
      width: the pill strip yields the band until the lesson is dismissed
      (visual-m23 V-3)
- [New] the land-cell hover card carries its own ⌾ raising the standard explain event
      with the cell's refresh derivation, so a cropped screenshot of the card keeps
      its resolution path (gate-m23 cycle-1 item 8)
- [Change] the legend's vocabulary note moved out of the scroll body into its own
         always-in-frame disclosure, so the provenance sentences are discovered
         rather than scroll-gated (visual-m12/m13)
- [Change] the panel coverage snapshot names the live v0.37 refreshes — nd_wells at
         drv_gh5zhnea4trtofypofbq, land metrics at drv_u6ntpnulcqf7kfij3t5a with the
         promoted grid and cell counts — read from the deployed mart 2026-08-22
- [Change] a selected disposal ring gains stroke weight over its teal siblings at
         every zoom stop, so selection no longer rides the cyan-teal hue pair alone
         (visual-m17 judgment 3)

<a id="v0.37"></a>
## v0.37 — 2026-08-22

- [New] observed rollups on the land grid (M2-3): well counts and cumulative liquid, gas
      and water summed per PLSS section and township into marts.land_metrics_tile, served
      as two tile layers with a support-aware amber choropleth (support modulates the ink,
      unobserved cells stay unpainted, never interpolated); percentile bins are cut at
      refresh and ride the tile with their edges, population and derivation handle, and
      the on-canvas key restates exactly that frame; liquid means oil plus condensate
      (cr_nd_liquids_policy_1) and says so wherever the number appears
- [New] cr_land_agg_membership_1, the section-membership decision as a conformance row:
      a well belongs to the section holding its lateral midpoint, else its surface hole —
      chosen against measured evidence (84.9% of ND laterals cross 2+ sections; 57.33% of
      well-reported ND liquid sits on wells whose midpoint and surface sections differ);
      the newest filing wins with geom_key breaking ties, grid-edge midpoint orphans
      (163 wells, 2.07M bbl) fall back to the surface hole rather than vanishing, ND
      bottomhole is ruled out by absence, and apportionment is deferred to a superseding
      rule with its Protocol 4D obligations
- [Fix] polygon labels no longer duplicate at tile seams: the land-grid and spacing-unit
      tile functions emit one anchor point per unit in the one tile that owns it, and the
      symbol layers bind to that `_label` sublayer instead of the polygon fragments
- [Fix] the land-grid panel row quotes its counts as published by BLM, so the register no
      longer presents staged totals as what was promoted

<a id="v0.36"></a>
## v0.36 — 2026-08-22

- [New] the ND PLSS land grid as real, queryable vector features (M1-4): townships and
      sections from the BLM national CadNSDI NAD83 service land in canonical.land_units
      with full lineage, publish as two tile layers (land_townships z8+, land_sections
      z10+), and draw as two off-by-default map rows with geometry and labels split;
      the publisher choice, the NAD83 transform and the ND scope are conformance rows,
      with the measured 25/16/242-feature cross-publisher grid divergence as evidence
- [New] arcgis_rest_paginate, the sanctioned REST harvest (SB-01 §1.2.1, v0.6 §4E.7):
      an ordered page walk with before-and-after count assertion, one checksummed
      newline-delimited artifact, one manifest; a partial walk fails loudly with
      page_walk_incomplete and writes nothing, a 499/403/429 halts the service path
      as host_token_gated, and hosts are allowlisted by amendment, not by code
- [Change] the spacing-unit labels row stops disclaiming a grid that now exists: its
         subtitle points at the PLSS land grid row instead of apologising for not being it

<a id="v0.35"></a>
## v0.35 — 2026-08-22

- [Fix] the three remaining same-day vintage-ledger upsert-without-accumulation
      sites route through record_vintage_day: the NM dimension close, TX GIS county
      loads and TX wellbore exports now sum counters and union manifest ids onto the
      one (source, day) row instead of overwriting the pass that did the work; the
      no-op guard holds at all three (DR-85, class from gate-a1b claim 3)
- [Change] ingest.base record_vintage_day returns the written VintageRecord — None
         when the no-op guard leaves the row alone — so a caller can cite the
         vintage_id it wrote instead of reconstructing it
- [Fix] the deploy refusal tests catch up to the v0.31 contract: the fixture tree
      carries numbered migrations so the tree-shape refusal no longer masks the
      cases, a stub host answers the schema_migrations head query so gap, no-gap
      and garbage answers are posed for real, and the retired "migrations skipped"
      silence is replaced by asserting the refusal that names both heads; new
      coverage for --skip-migrations issuing zero head queries and for the two
      migration flags together exiting 2

<a id="v0.34"></a>
## v0.34 — 2026-08-22

- [New] coordinate-source provenance as a served, styleable field (M1-3, ND half):
      every ND tile layer now carries geometry_provenance verbatim — surface, lateral
      or survey_trace — so the laterals row's "not a directional survey trace" caveat
      has a machine-readable backing; hover states the class unasked; the legend names
      the vocabulary and why TX serves none (licence-gated, RF-1)
- [New] cr_nd_geometry_provenance_1: which ND filing each geometry family's coordinates
      come from, as a conformance row served at /v1/conformance and cited by the mart
      refresh derivation; seeded for fresh and deployed databases alike (migration 033)
- [Fix] Texas well dots are pickable: tx-wells and tx-wells-struck join the click
      router's priority map at the ND wells' rank — 355,463 points previously returned
      no hit at all
- [Fix] the panel's ND counts read from one served snapshot (43,817 wells at the v0.30
      refresh) instead of mixing a FeatureServer vintage denominator with the served
      point count; percentages are computed, never hand-written
- [Change] a status class the summary serves at zero is dropped with its handle before
         the legend, so none-in-view has exactly one render — the em dash

<a id="v0.33"></a>
## v0.33 — 2026-08-22

- [New] well_type filter on /v1/wells: matches the code exactly as the regulator
      filed it, no decode and no classing, so the disposal layer's class can scope
      the spine; composed into the cursor fingerprint, so a cursor minted under one
      well_type is refused under another instead of quietly re-scoping the page
- [Change] the status-summary handle count now rides the envelope's own walker
         instead of a router-local duplicate, and a hand-authored explain link is
         refused even when it smuggles its handle in a URL fragment

<a id="v0.32"></a>
## v0.32 — 2026-08-22

- [Change] e2e: the owner key travels header-only — lib.mjs is the single auth path,
         reading GLASSWELL_KEY_FILE or GLASSWELL_OWNER_KEY and injecting X-Glasswell-Key
         on every same-origin request; smoke.mjs and perf.mjs drop the #key= fragment
- [New] e2e: centralized key redaction (case-insensitive) and leak guards in lib.mjs —
      it refuses to run with the key in process.argv or a navigation url, and journals
      any same-origin request that redirects off-origin; lib.test.mjs proves redaction,
      both refusals and the redirect detector under node --test
- [Change] make test-e2e and CI run the browserless e2e guard suite first
         (node --test tests/e2e), so the key-hygiene boundary is enforced even where
         the browser tier skips

<a id="v0.31"></a>
## v0.31 — 2026-08-22

- [New] deploy.sh stamps the code identity for lineage on every deploy: writes
      GLASSWELL_CODE_VERSION=<tag>+<commit> and GLASSWELL_LOCKFILE_SHA256 into
      /etc/glasswell/code-version.env, sourced last by glasswell-api.service and
      glasswell-ingest.service; verify.sh asserts the stamp is present
- [New] deploy.sh refuses when the repo carries migrations ahead of the database's
      schema_migrations head; --skip-migrations states the gap in a banner and proceeds
- [New] deploy.sh seeds the registries on every deploy (seed_all as postgres over the
      socket DSN, after migrate) so new conformance rules land before the first ingest
- [Fix] deploy.sh installs the tree's martin config to /etc/martin/config.yaml on every
      deploy, closing the drift verify.sh could only detect; usage now carries the
      canonical postgres-uid mart-refresh command with the code-version env

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
