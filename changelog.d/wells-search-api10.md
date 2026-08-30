- [Fix] The well card's "Rows for this well" returns the well. The card built its link
      from the API-10 and put it in `f.q`, a filter that matches well names only, so the
      crossing landed on an empty grid for every well ever built and no test noticed —
      the one that checked the link asserted it emitted `f.q`, which is the defect
      written down as an expectation
- [New] `GET /v1/wells?api10=` resolves the identity spine: matched whole, one well or
      none, never as a prefix or a fragment. It also takes the fourteen-digit literal,
      matched against the API-14 canonical records for the well rather than trimmed to
      ten at the route — which digits of an API-14 make the API-10 is an identity rule's
      declaration, so a completion this deployment never recorded answers with an empty
      page instead of with a guess
- [Change] The row hop into the wells collection narrows by `api10` rather than by `q`,
         and the map search box sends a pasted API-14 to that filter instead of to the
         name search the path cannot take; `q` stays what its served semantics say it is
- [New] `tests/contract/test_crossing_targets.py` reads the crossing table the browser
      ships and issues it against the API, so a filter that cannot match the identity it
      is handed fails in the suite rather than on a reader's screen; the explorer's own
      check that a crossing names a parameter the operation takes is what a name search
      handed an API-10 satisfied
