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
