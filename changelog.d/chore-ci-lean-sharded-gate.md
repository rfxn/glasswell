- [Change] CI: the Python job is four `pytest -n 4` shards over the contract and integration
         tiers plus a docker-free lint-and-unit job, gated by a diff classifier and a
         tree-identity skip that does not re-run a merge commit whose tree a green parent
         already carried; `CI complete` is the one always-running required check, and PR refs
         cancel their own superseded runs
- [New] `.github/workflows/nightly.yml`: the whole suite once a day, unsharded, in one process
      and in collection order — the control for the order dependence and lost-shard classes a
      split run cannot see — plus the shard-parity comparison against its own collection
- [New] `make test` selects the tests a diff can reach (`scripts/test-scope.py`: import graph,
      `test_<stem>.py` naming, and a whole-suite fallback for conftest, fixtures, migrations,
      the lockfile and the workflows) and prints what it excluded; `make test-full` is the whole
      suite, `make test-scope` prints the selection alone, `make durations` refreshes the file
      that balances the CI shards
- [New] docs/ci-gate.md: what each job refuses, when the tree-identity skip may fire, how the
      shards are kept honest, and what every red symptom means
- [Change] 104 items that reach no database fixture move from the contract and integration tiers
         to `tests/unit/`, eight are deleted with the surviving cover named for each, and the
         `?explain=true` pools surface is merged into `test_explain_inline.py` as a parametrised
         row; with the guards this work added, collected 5,736 -> 5,775
- [Fix] tests/unit/test_access_log_redaction.py: the 13 assertions that hold the access-log
      filter to *under*-redacting nothing served -- the five live query strings, the eight served
      parameter names one by one, and `new_password=` / `owner_key=` / `x_csrf_token=` -- were
      overwritten rather than extended when the key-hygiene tests moved in; restored beside the
      seven arrivals, both directions covered again (B-1)
