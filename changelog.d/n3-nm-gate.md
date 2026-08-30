- [New] `scripts/ops/nm_reregister_manifests.py` re-registers a sealed raw-zone artifact
      from its sidecar into an index that does not carry it yet; no socket is opened and
      the operation is idempotent on the sha256 within a slot
- [New] `--dry-run` validates every sidecar, resolves each against the live index and
      reports the manifest ids it would create on a read-only connection, so committing
      nothing is enforced by the server rather than by the code path
- [Fix] the manifest re-registration tool existed only at `/data/scratch/d1-p4/reregister.py`
      on the app VM, inside a disposable tree, while the status file that directs an
      operator to it named a `work-output/experiments` path that does not exist; it now
      names its target database on every run, reports registered against already-present
      per sidecar, and exits 1 on a slot conflict instead of tracebacking
- [Fix] `status/collector.py` aggregated `canonical.production_monthly` with no state filter
      and served the result under a hardcoded North Dakota jurisdiction, so the first New
      Mexico promotion would have published 24.8M rows and ~93,958 wells under the wrong
      state within fifteen minutes, on a timer, over rows with no well header
- [Change] the inventory splits into `canonical.production_monthly/nd` and `/nm`, matching
         the state-qualified convention every sibling dataset in the file already follows,
         including the `well_completions/nm` entry that already serves zero
- [Change] the status contract test seeds two states rather than one — the defect was
         invisible to a single-state fixture — and asserts the two datasets partition the
         table, so a third population would fail rather than vanish from a served figure
