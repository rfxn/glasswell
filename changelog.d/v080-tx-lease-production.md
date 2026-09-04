- [New] Texas is resident with production, and it arrives at the grain the regulator files
      at: the RRC's PDQ lease cycles are staged, crosswalked to API-10 through the wellbore
      EWA export and promoted a calendar year at a time as rows the lease owns, with
      `rows_read`, `rows_built`, `rows_appended`, `rows_excluded_out_of_scope` and
      `rows_quarantined` reported per year, and a later filing appended as a restatement
      rather than applied over the first one
- [New] Every well-level Texas figure is an allocated share and says so: `cr_tx_allocation_v0_1`
      splits each lease-month among the wells eligible in that month, conserves the lease
      total exactly, and each share is served, charted and labelled as allocated beside the
      number of wells it was divided among and a handle that resolves to the lease row the
      split was taken from
- [New] `/v1/validators/allocation` publishes the three residual ledgers an allocation owes
      about itself -- conservation, crosswalk coverage and the error band -- each with its
      outcome, the rule it was measured under and its reasons, and `not_available` with a
      reason rather than a figure wherever the ledger holds another jurisdiction's rows
- [New] The allocation's error band is measured where both grains are published: Montana files
      lease and well volumes for the same months, so the same split is scored there under
      `cr_alloc_v0_error_bounds_1` and the band stays `not_measured` on any jurisdiction the
      study has not been run on rather than borrowing Montana's
- [New] Between deploy and the end of the manual load, a Texas well card says production is
      pending allocation and names both the registered grain decision and the rule that will
      close it, rather than drawing an empty chart over a lease that has filed every month
- [New] `docs/runbook-tx-load.md`: the PDQ fetch, the year-at-a-time load, the mart refreshes,
      and what each step's counts must say before the next one is run
- [Change] A Texas cumulative carries the allocated share beside the total and a coverage
           block saying how many of its months are allocated, under which model run, and how
           many were observed; a jurisdiction whose mart the last refresh skipped is told that,
           rather than told it is outside the mart's scope
- [Change] `?as_of=` is refused on the allocated series, with the rule that says why: the
           allocation is one snapshot per key, so a figure served under an earlier knowledge
           cut would be this run's arithmetic wearing an older date
- [Change] Texas's three scheduled jobs -- the PDQ ingest, the allocation mart and the
           back-test -- observe: each tick records what it would have run and starts nothing
- [Change] Texas is corrected by appending a registration rather than by editing the one that
           was wrong: the founding row saying Texas publishes no well-level production still
           answers under its own knowledge cut, and the successor carries the grain decision
           and the cumulative scope that admit an allocated figure
