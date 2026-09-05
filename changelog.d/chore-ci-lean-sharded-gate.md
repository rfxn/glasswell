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
- [Change] 24 tests that reach no database fixture move from the contract and integration tiers
         to `tests/unit/`, and `test_tiles.py`'s tile-allowlist assertion is deleted for the
         identical one in `tests/unit/test_martin_config.py`
