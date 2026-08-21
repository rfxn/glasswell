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
