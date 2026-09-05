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
      read ` (HTTP 500)` on the deployment's own transport
- [Fix] the capture band's row names fit at every width, the vintage control uses the
      text-safe cyan, and the widening control no longer abuts the sentence it follows
