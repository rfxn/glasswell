- [Fix] explain links: the envelope is now the only author of links.explain — a
      router-supplied link naming handles is refused, /v1/derivations/{id} and the
      vintages pair advertise their handles through the envelope's own selection, and
      router-written _lineage sidecars feed the same list `_explain` inlines, closing
      gate-apix ADV-1's two-carrier divergence before ?explain=true reached those paths
- [Fix] status-summary truncation warning now counts distinct handles the way the
      link selection counts them, so a repeated handle can no longer claim a truncation
      the link does not have
- [Fix] explain chains order root-first with the terminal manifests closing the node
      list: a root whose manifest was its first-ord input served the manifest mid-chain
      ahead of deeper derivations, so the drawer's bottom node was a derivation under a
      header counting terminal manifests (DR-83); pinned by a contract test on a chain
      that reproduces the live input ordering
- [Fix] the contract fixture's vintage now states the restatement its own seed performs,
      so the R6 walker serves a restatement count and the restatement-exemption gate
      guards data it actually meets (DR-82)
- [New] ?explain=true[&explain_depth=N] extends to every remaining figure-bearing GET:
      /v1/derivations/{id}, /v1/vintages, /v1/vintages/{id} and
      /v1/wells/{api10}/production/pools, each with annotated parameters, contract
      coverage and auth-matrix rows; the OpenAPI delta is 16 changes, all additive
