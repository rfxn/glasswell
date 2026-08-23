- [Fix] Well card: the shell's height cap now reaches through the card's own wrapper, so the
      body scrolls instead of running off the viewport — 286 px of chart, null-semantics key
      and derivation warning were unreachable at 1024x768, 281 px at 390 and 86 px at 1366
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
- [Change] Map chrome takes its layer from the z-index ladder token rather than a literal
           value the ladder's own comment forbids
