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
