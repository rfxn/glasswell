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
