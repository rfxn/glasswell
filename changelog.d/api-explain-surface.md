- [New] `?explain=true` on the figure-bearing GETs (`/v1/wells/{api10}`,
      `/v1/wells/{api10}/production`, `/v1/wells/status-summary`): the response gains
      `_explain`, one SB-07 §9.3 chain per handle it carries, keyed by handle and resolved to
      `explain_depth` levels (3 by default, 8 at most, refused over the cap); the flag adds the
      block and moves nothing else, and a response carrying more handles than one `/v1/explain`
      call accepts says how many it left out (DR-63)
- [New] `GET /v1/explain?format=dot` renders the same resolution as a Graphviz digraph —
      derivations, manifests and the conformance rules they cited as nodes, every edge labelled
      with the role the input played — served as `text/vnd.graphviz` (DR-64)
- [Change] the OpenAPI differ carries a `const` fact kind: a single-valued `Literal` renders as
         `const` rather than `enum`, so swapping one pinned value for another classified as no
         change at all; the same blind spot the `pattern` kind closed, one keyword over
