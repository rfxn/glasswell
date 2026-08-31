- [Fix] 068: grant UPDATE on the New Mexico partition registry to glasswell_pipeline.
      nm_ocd registers a partition with `insert ... on conflict do update`, which Postgres
      checks for UPDATE, and migration 028 granted it only select and insert alongside its
      eight append-only siblings; the first least-privileged staging run refused after 33
      minutes with eight tables staged and the ninth denied
- [New] test_staging_upsert_grants.py: a staging table the ingest path upserts must be
      granted UPDATE by some migration, resolved through the module constant so an
      f-string target is not silently skipped
