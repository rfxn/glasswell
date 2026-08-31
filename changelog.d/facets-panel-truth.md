- [Fix] The "Wells by …" caption names the direction the list was ranked in. Asked for
      `sort=count&order=asc` the endpoint serves the values with the fewest wells while the
      caption read "with the most wells", beneath a button reading "lowest first" — a served
      sentence that was false about the rows next to it. A complete list now says which way it
      is ranked too, rather than only by what
- [Fix] A facet bucket's `/v1/wells` link percent-encodes the value it carries, the same
      `urlencode` the cursor links already use. Written verbatim, `DIAMONDBACK E&P LLC` ended
      the value at the ampersand and minted a stray parameter, so the published link narrowed
      to a different population than the count beside it, and the spaces made it a URL no
      agent or auditor could issue at all
- [Fix] The "Wells by …" panel renders the warnings the envelope serves, through the same
      `warningPanels` the well card and the neighbour list use. `search_scopes_the_ranking`,
      `list_truncated` and `absence_unregistered` were all served and all dropped, so under a
      search the panel's arithmetic stopped closing on screen with nothing saying why
- [Change] The absence bucket's `detail` says the search did not narrow it, names the search
           and the state, and is composed beside the count so the sentence and the figure
           cannot drift apart. Under a `q` every other figure in the response moves and this
           one stays whole-state, and the total that would have been its denominator is no
           longer on the surface
- [Fix] Clicking a facet bucket narrows the grid by every filter the server's link carries,
      the state included. The panel ignored `bucket.links` and rebuilt the filter from the
      dimension alone, so Texas county 003 narrowed to Texas and North Dakota county 003
      together — the crossing `state` was added to `/v1/wells` to stop. The link is now the
      one source of truth for what a bucket narrows to, and a bucket the collection cannot
      reproduce still renders as a plain label
- [Change] `/v1/wells` declares `well_type` a facet. The collection has always applied the
           filter, and a well-type bucket set it, but a filter the dataset does not declare
           renders no chip and cannot be cleared on its own
- [Fix] The "Wells by …" search keeps focus and the caret across the re-render its own
      keystroke causes. Every debounced commit rebuilt the explorer and destroyed the focused
      input, so any pause longer than 250 ms dropped the reader out of the box mid-word
- [Change] A search commits with `replaceState` rather than `pushState`, on the convention the
           viewport already follows — a seven-character search cost seven back presses.
           Changing the dimension, the state, the ranking or its direction still pushes
