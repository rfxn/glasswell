- [Fix] Map legend: the per-class well counts are read from GET /v1/wells/status-summary for
      the viewport's box instead of counting map.queryRenderedFeatures(), so they no longer
      fall as the viewed area grows; measured over a seeded North Dakota population, the same
      box asked at two zooms returns one set of counts and no class count drops between z11
      and z5
- [New] Map legend: every count carries the derivation handle the summary served it with, so
      a class row opens the lineage drawer on the count itself rather than borrowing a drawn
      feature's geometry build; the conformance rules that classed the answer are named per
      response and link to /v1/conformance
- [New] Map legend: while a viewport's counts are in flight the rows show a wait rather than
      the previous viewport's numbers, and a summary that fails or times out shows an em dash
      on every class with the failure stated in the transient channel — never a stale or
      partial count; a late answer is matched to its viewport by request order and by the
      response's own bbox echo, so an answer for a viewport the reader has left cannot paint
- [New] Map legend: a "showing X of Y in view" line states the canvas census against the
      classes still drawn, so zoom culling and tile thinning cannot be read as the counts
      disagreeing with the dots (MAP-ROADMAP M1-1, partial half)
