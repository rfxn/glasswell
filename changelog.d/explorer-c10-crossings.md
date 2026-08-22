- [New] Map ↔ explorer crossings (SB-08 §2.6): a well card to its rows, a production chart
      to its series, a map layer to the collection behind it, the `as_of` chip to the
      vintages, and an explorer row with geometry back to the map. Every one is built by
      `stateFor`, the same router a join chip uses, so a crossing and a hop cannot drift
- [New] Both of §2.6's invariants are asserted separately: `as_of` survives every crossing,
      and each is exactly one `pushState` followed by the synthetic popstate the mode
      switch already dispatches, so one back press returns the reader to what they left
- [New] M6, applied where a link is made rather than where one is read: a crossing off a
      surface that resolved a vintage pins that vintage, so a shared link reproduces the
      numbers the sharer saw; a vintage the reader pinned themselves always wins
- [New] `x-glasswell-dataset` destinations are declared in `bridge.ts` and checked against
      the committed OpenAPI snapshot — four of the five crossings are built on the map,
      which never fetches the document, so the declaration is proven rather than trusted
- [New] The layer registry says which served collection carries each layer, and a layer no
      collection carries states that instead of offering a link that would 404
- [New] The 820 card list and the 390 refusal (§2.5): one card per row with the column name
      beside each value, the filter bar as a sheet, and at 390 a grid that says it needs a
      wider window while the API guide renders in full — a CSS posture over the DOM the
      grid already built, so a row keeps its click, its panel and its `aria-expanded`
- [New] `work-output/pa-w1-walkthrough.md` and `pa-w1-drive.mjs`: SB-08 §5.3's walkthrough
      in the form A-6's `steps[]` will carry, driven end to end in a browser with each step
      asserted and framed. Per §9 it is a test a human runs, not a gate — the seeded-instance
      e2e job it would need is Track O's and does not exist
- [Change] C8's D1 is ruled: the grid's identifier cells carry no hop, because a chip is an
           anchor and the row's own click yields to one; the record panel keeps them. The
           geometry cell is the exception and carries the crossing, having no value to
           compete with — a coordinate is never printed
- [Fix] The explorer's stacked layout below 1024 sized the rail's row by its content while
      capping the element, so the row claimed 674 px, painted 202, and left the centre
      column zero; the row is capped instead and the rail scrolls inside it
- [Fix] `whatsBehindThisLayer` drops the viewport rather than sending a box past the four
      degrees a side `list_wells` rejects, and says the view is too wide to narrow by
- [Fix] The layer row's crossing let `display` outrank `[hidden]`, painting an arrow on
      every tile-only row above the line saying it has nowhere to cross to
