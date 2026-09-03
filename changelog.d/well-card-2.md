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
