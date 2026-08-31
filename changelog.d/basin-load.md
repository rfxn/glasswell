- [New] glasswell-eia-boundaries and glasswell-basin-boundaries console scripts, so both
      halves of the EIA boundary load are operator-reachable; the layer shipped in v0.69 with
      its tables, tile functions and martin sources installed and served nothing because
      neither loader had an entry point
- [New] docs/runbook-basin-load.md: the two production commands, the user each runs as, the
      exact expected counts against pinned manifest ids, success-versus-partial triage, and
      the undo
- [Change] test_fetch_attempt_entrypoints: eia_boundaries.py joins the network-fetch commands
           required to open the independent attempt ledger; it always did, and nothing
           checked it
