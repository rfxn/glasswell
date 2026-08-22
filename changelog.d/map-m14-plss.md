- [New] the ND PLSS land grid as real, queryable vector features (M1-4): townships and
      sections from the BLM national CadNSDI NAD83 service land in canonical.land_units
      with full lineage, publish as two tile layers (land_townships z8+, land_sections
      z10+), and draw as two off-by-default map rows with geometry and labels split;
      the publisher choice, the NAD83 transform and the ND scope are conformance rows,
      with the measured 25/16/242-feature cross-publisher grid divergence as evidence
- [New] arcgis_rest_paginate, the sanctioned REST harvest (SB-01 §1.2.1, v0.6 §4E.7):
      an ordered page walk with before-and-after count assertion, one checksummed
      newline-delimited artifact, one manifest; a partial walk fails loudly with
      page_walk_incomplete and writes nothing, a 499/403/429 halts the service path
      as host_token_gated, and hosts are allowlisted by amendment, not by code
- [Change] the spacing-unit labels row stops disclaiming a grid that now exists: its
         subtitle points at the PLSS land grid row instead of apologising for not being it
