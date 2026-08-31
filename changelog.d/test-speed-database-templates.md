- [Change] The contract tier seeds its fixture once into a template database every test
           clones, rather than seeding it per test. `seed_all`, the eight wells, their
           geometry and production, the neighbour mart, the quarantine rows and the pinned
           control publication cost 0.32 s per test and land the same rows every time; the
           assertions pinning the documented example ids run in the builder, once, and still
           fail the tier when an example goes stale. Contract setup falls from 695.7 s to
           262.6 s across 1,367 tests, and the full suite from 27:40 to 18:45 on one host
- [Change] The ephemeral PostGIS container runs with fsync, synchronous_commit and
           full_page_writes off at wal_level=minimal, and `create database` clones with
           `strategy file_copy`. A server destroyed at the end of the session has nothing to
           recover, and file_copy is the faster strategy only once the checkpoints it forces
           are free: 67 ms of create-plus-drop per test against 118 ms measured on the
           defaults, over the 2,749 databases a full run builds
- [Change] The control artifact the contract tier publishes is written once per session and
           copied per test rather than rebuilt through duckdb for each one. Every path it
           records is relative, so a copy under another root is byte-identical and
           EXAMPLE_PUBLICATION_ID does not move
