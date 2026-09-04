-- The source-health query the planner, the collector and the API all read (status/
-- source_health.py) now asks whether a fetched artifact was ever loaded into staging. A refused
-- parse is recorded as a `staging.load_failed` event against its manifest, so the query reads
-- lineage.audit_events -- and glasswell_scheduler could not, so the first cadence tick after
-- that change raised InsufficientPrivilege and returned no due set at all.
--
-- 076's own comment sets the rule this follows: the grant list is derived from the queries the
-- planner runs, and tests/integration/test_job_schedule_registry.py extracts the relations out
-- of those query strings rather than keeping a list by hand. This is that test doing its job.
--
-- Read only, and only this one relation. The audit stream is append-only and its failure
-- details are sanitized before they are written (lineage/fetch_attempts.py), so a scheduler
-- that can read it learns nothing it cannot already learn from lineage.fetch_attempts, which
-- it has read since 076.

grant select on lineage.audit_events to glasswell_scheduler;
