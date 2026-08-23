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
