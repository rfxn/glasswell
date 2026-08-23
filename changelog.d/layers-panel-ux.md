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
