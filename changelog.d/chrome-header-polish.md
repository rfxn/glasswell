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
