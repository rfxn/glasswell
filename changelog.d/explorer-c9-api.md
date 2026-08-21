- [New] The explorer's API guide pane (SB-08 §4): REQUEST, OPERATION and RESPONSE, each
      collapsible with its state in `api=`; the request block renders curl, httpie and
      fetch from the one object `requestFor` returns, so the URL a reader copies is the
      URL the grid issued — asserted at the client seam, not at fetch
- [New] Parameter semantics from A-8: WHAT from the OpenAPI description, WHY from the
      bound glossary term's expanded definition, SO from `x-glasswell-semantics`, SEE from
      the term's related terms; a parameter A-8 has not reached renders WHAT only with the
      unbound column's muted `?` and is counted in a coverage line
- [New] RESPONSE labels `data`, `meta` and `links` in place, names the `_lineage`,
      `_units` and `_basis` sidecars where the response carries them, and states an exact
      byte count on both sides of a truncation; status, timing and cache class come from
      the response itself, and the pane says so where `x-glasswell-cache` is unimplemented
- [New] Cursor pages are copyable individually, and the walk-all-pages snippet follows
      `links.next` rather than assembling a cursor
- [New] guardrails.test.ts arm 4: no domain-prose literal over 120 characters under
      `explore/`, with the vocabulary derived from the glossary terms the served document
      binds rather than from a list in the test
- [Change] The key placeholder, the curl builder and the breadcrumb's command list moved
           to `explore/api/request.ts`; `detail/chips.ts` re-exports them so the
           breadcrumb and the pane cannot drift apart
- [Fix] The stacked explorer layout at 1024-1365 gave the pane's row `auto`, so a pane
      with content took the window and left the grid a zero-height row; the row is capped
      with `fit-content(40%)` instead, because a percentage max-height cannot resolve
      against a row the item is sizing
