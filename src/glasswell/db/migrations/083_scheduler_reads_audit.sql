-- The source-health query the planner, the collector and the API all read (status/
-- source_health.py) now asks whether a fetched artifact was ever loaded into staging. A stage
-- that fails is recorded as a `staging.load_failed` event against its manifest, so the query
-- reads lineage.audit_events -- and glasswell_scheduler could not, so the first cadence tick
-- after that change raised InsufficientPrivilege and returned no due set at all.
--
-- 076's own comment sets the rule this follows: the grant list is derived from the queries the
-- planner runs, and tests/integration/test_job_schedule_registry.py extracts the relations out
-- of those query strings rather than keeping a list by hand. This is that test doing its job.
--
-- The grant is on a view and not on the table, because lineage.audit_events also carries the
-- account and session trail -- `username`, `client_ip`, `role`, `sessions_revoked` from
-- api/routers/session.py and api/accounts.py -- and the scheduler is the least-privileged role
-- in the system. The view exposes one column of one event type, which is the whole of what the
-- query asks; naming it in source_health._SOURCES is what keeps the grants-derived test honest
-- by construction, since the extraction reads the relations the query names.

create view lineage.staging_load_failures as
select e.subject_id as manifest_id
  from lineage.audit_events e
 where e.event_type = 'staging.load_failed'
   and e.subject_type = 'manifest';

comment on view lineage.staging_load_failures is
    'Manifests a stage refused or failed to load, for status.source_health. Deliberately no'
    ' payload column: the audit stream it reads also carries the account and session trail.';

grant select on lineage.staging_load_failures
    to glasswell_scheduler, glasswell_api, glasswell_pipeline;

-- 003_manifests.sql declared the column with an FK and no comment, and nothing ever set it.
-- Three modules now depend on what its absence means, so the schema says it rather than the
-- prose around it.
comment on column lineage.manifests.staging_load_ref is
    'The derivation that read this artifact into staging; null means fetched and never parsed'
    ' (status.source_health).';
