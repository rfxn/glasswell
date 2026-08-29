- [Change] The Postgres tuning drop-in is resized for VM 111 as it runs — 8 vCPU, 16 GiB
         resident, PGDATA on the ssd-pool — rather than for the 8 GiB balloon floor.
         Allocations still assume the floor is reachable, because the balloon reclaims page
         cache and never the shared-memory segment; planner hints do not, because they
         allocate nothing. `shared_buffers` 2GB to 4GB, `effective_cache_size` 6GB to 12GB
- [New] Thirteen settings the drop-in never carried, for a database that has grown 18x and
      has a 17.6M-row promotion queued: WAL sizing (`wal_buffers`, `min_wal_size`,
      `max_wal_size`, `checkpoint_timeout`) against a bulk promotion that writes ~12 GB of
      relation data through a 1GB checkpoint trigger; parallelism capped at four workers
      plus the leader, which is C26's five-of-eight-vCPU batch cap; and autovacuum reach
      for tables whose `reject_mutation` trigger makes insert-driven freezing, not bloat,
      the risk
- [Change] `work_mem` 32MB to 64MB, bounded by martin's `pool_size` of 10 and the
         cluster-wide parallel-worker cap rather than by `max_connections`, and
         `autovacuum_work_mem` pinned at 256MB so raising `maintenance_work_mem` to 1GB
         cuts the autovacuum burst from 1.5 GB to 0.75 GB instead of tripling it
- [Change] `max_connections` 60 to 80: there is no connection pool, so one map pan's
         tile-proxy requests take 12-24 of the 57 usable and martin's pool takes 10
- [Fix] `infra/README.md` said the tuning was shipped but not applied. It was applied on
      2026-08-20 at 15:25:57 and an independent gate read `shared_buffers` back off the
      running server the same afternoon; the claim outlived the fact by eight days. The
      section now separates what was measured from what nobody has confirmed, and no
      longer asserts a state without evidence
- [Fix] `verify.sh`'s tuning block counted nothing, so a drop-in reformatted to `key=value`
      matched no line and produced output indistinguishable from a pass (F28). It now
      asserts that at least one setting was checked, and its parser tolerates an inline
      comment and a digit in a setting name
- [New] A measurement runbook in `infra/README.md`: the SQL for database and relation
      sizes, cache hit ratio, connection high-water, checkpoint counters and autovacuum
      reach, the apply sequence including the 4 GiB swapfile SB-06 2.3 asked for and
      provisioning never created, and which four values to re-check once real numbers
      come back
