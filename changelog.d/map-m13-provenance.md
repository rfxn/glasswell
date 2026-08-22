- [New] coordinate-source provenance as a served, styleable field (M1-3, ND half):
      every ND tile layer now carries geometry_provenance verbatim — surface, lateral
      or survey_trace — so the laterals row's "not a directional survey trace" caveat
      has a machine-readable backing; hover states the class unasked; the legend names
      the vocabulary and why TX serves none (licence-gated, RF-1)
- [New] cr_nd_geometry_provenance_1: which ND filing each geometry family's coordinates
      come from, as a conformance row served at /v1/conformance and cited by the mart
      refresh derivation; seeded for fresh and deployed databases alike (migration 033)
- [Fix] Texas well dots are pickable: tx-wells and tx-wells-struck join the click
      router's priority map at the ND wells' rank — 355,463 points previously returned
      no hit at all
- [Fix] the panel's ND counts read from one served snapshot (43,817 wells at the v0.30
      refresh) instead of mixing a FeatureServer vintage denominator with the served
      point count; percentages are computed, never hand-written
- [Change] a status class the summary serves at zero is dropped with its handle before
         the legend, so none-in-view has exactly one render — the em dash
