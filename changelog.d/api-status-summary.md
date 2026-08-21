- [New] GET /v1/wells/status-summary: per-status well counts for a WGS84 box, from
      canonical rather than from drawn features, so the map legend stops shrinking as the
      viewport grows (status classes are zoom-gated and the tile tier thins points, so a
      queryRenderedFeatures count fell exactly when the viewed area rose); every count is a
      figure with its own derivation handle, wells with no reported status are their own
      bucket and are never folded into a class, counts split per basin naming the vocabulary
      rule that mapped them (cr_nd_status_vocab_1, cr_tx_status_vocab_1), geometry with no
      well row at the requested vintage is disclosed as a warning rather than dropped, and
      the box is uncapped — measured at 399,280 seeded well points: 19 ms for a screen,
      237 ms for the whole of North Dakota, 1.4 s for the whole world
