- [New] One tile-mart engine: `marts/wells.py` refreshes any registered jurisdiction from a
      `MartProfile` row and its registration, and `glasswell-tiles --jurisdiction <CODE>` is
      its entry point; the four per-state modules stay as shims because two applied
      migrations name them by module path and the deployed timer executes a third. Every ND,
      TX, NM and MT derivation id and tile digest is byte-identical before and after, proved
      by `scripts/mart-address-diff.sh` running both checkouts against one database
- [New] Seven presentation columns on `lineage.jurisdictions` and a `wells-roster.json` the
      generator emits beside the client module, so the map's Wells rows, their style layers,
      their draw order and their subtitles are registrations rather than object literals
- [New] `basin_scope`, `length_source` and `neighbors_scope` as `jurisdiction_rules`
      decisions, with `cr_nd_basin_scope_1`, `cr_tx_basin_scope_1`, `cr_nd_length_source_1`,
      `cr_tx_length_source_1`, `cr_nd_neighbors_scope_1` and `cr_mt_neighbors_scope_1`
- [Fix] `/v1/wells/{api10}/completions` served a `lateral_length_ft` for Montana wells with a
      FracFocus disclosure, computed under `cr_nd_compute_crs` because the endpoint called the
      length resolver unconditionally and the Montana mart stores its paths as laterals; the
      figure is now null with `cr_mt_paths_length_scope_2` cited, which is what that rule's
      contract note has always claimed. Any served intensity for such a well changes with it
- [Fix] A jurisdiction with no registered basin was served a length method and a compute CRS
      resolved from North Dakota's rule on both `/v1/wells/{api10}` and `/completions`; an
      unregistered length rule is a 200 with a null and a `length_scope_unregistered` reason
- [Fix] The glossary client read one page of 200 terms and declared itself loaded, so a
      vocabulary past that cap would have rendered "Definition loading…" for the life of the
      page; it follows `meta.next_cursor` to a ten-page cap without throwing
- [Fix] A jurisdiction registered as carrying laterals outside the neighbour mart's measured
      domain aborted the whole monthly refresh naming another state's well; it is excluded
      with a reason the well card and `/v1/jurisdictions` both report
- [Change] `cr_mt_paths_length_scope_2` supersedes `_1`, dropping the sentence that described
           the North Dakota length default this release removes; `_1` stays served and
           historical
- [Change] Every bore line is declared under every wellhead dot rather than interleaved per
           jurisdiction, so a lateral stroke no longer bisects the dot it belongs to in the
           Permian; the disposal ring keeps its place over the dots and moves under North
           Dakota's plugged strike. Pinned by an order assertion, which nothing had
- [Change] The add-a-state gate gains two narrow regex arms and a registered-code arm, and
           carries exactly eight named exemptions; `selector_registry.py`, `status.ts`,
           `style.ts` and `click-router.ts` derive from the registry rather than naming
           jurisdictions
