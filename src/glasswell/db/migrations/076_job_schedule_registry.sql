-- The schedule as data: which jobs exist, what drives each one, on whose decision, and what
-- every tick observed. Cadence lived in ten ExecStart lines and one runbook sentence, so a
-- registered source was not a scheduled source and nobody could tell which was which from a
-- query. R8 in the same shape 073 gave the jurisdiction registry: append-only rows, two
-- clocks, and a conformance rule behind every decision.
--
-- REPOINT CHECKLIST (integrator, at the merge train):
--   1. evidence_tag UNRELEASED -> the tag that first carries these cadence rules
--   2. evidence_commit forty zeros -> the merge commit on main that carries them
--   3. published_vintage -> the date that tag is actually cut; the table is append-only
-- The rule ids are immutable and must not change during the repoint. Both literals appear
-- exactly once each, in the evidence insert below and nowhere else: a quoted placeholder above
-- it re-arms the release guard through prose, so this header names the columns, not the values.

-- A cadence decision runs at none of the four pipeline stages, and recording it as a rule is
-- what keeps it reviewable. Drop-and-re-add is the form 048:4, 011:8, 012:8, 021:12, 030:100
-- and 034:20 use. rule_kind is NOT widened: a cadence is a code_ref, the kind the glossary
-- already calls the honest exception.
alter table lineage.conformance_rules drop constraint conformance_rules_stage_check;
alter table lineage.conformance_rules add constraint conformance_rules_stage_check
    check (stage in ('parse', 'validate', 'conform', 'join', 'schedule'));

create table if not exists lineage.refusal_codes (
    code           text primary key check (code ~ '^[a-z][a-z0-9_]{0,63}$'),
    severity_class text not null check (severity_class in ('informational', 'waiting', 'fault')),
    sentence       text not null check (btrim(sentence) <> '')
);

comment on table lineage.refusal_codes is
    'The refusal vocabulary and its three severity classes, as rows. A standing condition that'
    ' is merely informational must not redden the deploy gate, and which class a code carries'
    ' is a decision, not a hardcoded list in the collector.';

create table if not exists lineage.scheduled_jobs (
    job_id           text primary key check (job_id ~ '^[a-z][a-z0-9_]{2,63}$'),
    kind             text not null check (kind in ('ingest', 'mart', 'maintenance')),
    -- Served rather than mapped again in the client, the way lineage.jurisdictions.name is:
    -- a page that derived "North Dakota GIS ingest" from an identifier would be holding a
    -- naming decision in code that no one could review or correct without a release.
    label            text not null check (btrim(label) <> ''),
    -- One entry point per job: a job is one runnable command, which is what keeps the
    -- ceilings, the timeout, the transient unit and the run ledger one-to-one with a process.
    -- The second arm admits the two platform units that run a shell script rather than a
    -- module (refresh-ranges.sh, glasswell-backup.sh); the scheduler never launches those, and
    -- binding every launchable row to the glasswell. namespace is what the arm preserves.
    entry_point      text not null check (
                         entry_point ~ '^glasswell\.[a-z0-9_.]+$'
                         or (kind = 'maintenance' and entry_point ~ '^/[A-Za-z0-9_./-]+$')),
    argv             text[] not null default '{}',
    anchor_source_id text references lineage.sources (source_id),
    jurisdiction     text,
    -- Null only where this registry does not decide the uid: an external timer's own unit
    -- does. The CHECK below pairs it to kind exactly as anchor_source_id is paired.
    run_as           text check (run_as in ('glasswell', 'postgres')),
    rationale        text not null check (btrim(rationale) <> ''),
    check (kind = 'maintenance' or anchor_source_id is not null),
    check (kind = 'maintenance' or run_as is not null)
);

comment on table lineage.scheduled_jobs is
    'Identity and the immutable runnable facts. anchor_source_id carries the source whose'
    ' cadence rule the job is filed under -- for a mart, the anchor of its first dependency,'
    ' resolved transitively -- so the join is a row and not a lookup in code.';

create table if not exists lineage.job_sources (
    job_id    text not null references lineage.scheduled_jobs,
    source_id text not null references lineage.sources (source_id),
    primary key (job_id, source_id)
);

comment on table lineage.job_sources is
    'Five entry points cover between two and nine sources, so the job-to-source edge is a'
    ' table. An ingest interval is min(expected_poll_interval) over these rows.';

create table if not exists lineage.job_schedules (
    job_id                 text not null references lineage.scheduled_jobs,
    effective_from         date not null,
    published_at           date not null,
    rule_id                text references lineage.conformance_rules (rule_id),
    trigger                text not null check (trigger in
                               ('cadence', 'after_dependency', 'manual', 'external_timer')),
    launch_mode            text not null default 'observe'
                               check (launch_mode in ('observe', 'launch')),
    cadence_interval       interval check (cadence_interval > interval '0 seconds'),
    cadence_monthly_on_day smallint check (cadence_monthly_on_day between 1 and 28),
    cadence_note           text not null check (length(cadence_note) between 1 and 80),
    memory_max             text check (memory_max ~ '^[1-9][0-9]{0,3}[MG]$'),
    timeout_seconds        integer check (timeout_seconds between 60 and 21600),
    concurrency_group      text not null default 'default',
    enabled                boolean not null default true,
    legacy_unit            text,
    external_timer_unit    text,
    external_service_unit  text,
    primary key (job_id, effective_from, published_at),
    check (trigger = 'external_timer' or rule_id is not null),
    check ((trigger = 'external_timer')
           = (external_timer_unit is not null and external_service_unit is not null)),
    check ((trigger = 'external_timer') = (memory_max is null and timeout_seconds is null)),
    check (trigger <> 'external_timer' or launch_mode = 'observe'),
    check (cadence_interval is null or cadence_monthly_on_day is null),
    check (trigger <> 'cadence'
           or cadence_interval is not null or cadence_monthly_on_day is not null)
);

comment on table lineage.job_schedules is
    'The decision, append-only and on two clocks. A supersession is a later effective_from and'
    ' a restatement is a later published_at at the same one; neither is ever an edit. The'
    ' 21600 second ceiling equals the scheduler unit TimeoutStartSec, so no single job can'
    ' outlive its parent.';
comment on column lineage.job_schedules.launch_mode is
    'observe computes the plan and records would_run; launch runs it. v0.77 seeds observe on'
    ' every row here, and the permanent guard is that no launch row names an entry point an'
    ' installed timer already drives.';
comment on column lineage.job_schedules.legacy_unit is
    'The still-armed unit that actually runs this job while the row is observing, so a plan'
    ' row never claims the scheduler ran something it did not.';

create table if not exists lineage.job_dependencies (
    job_id            text not null references lineage.scheduled_jobs,
    depends_on_job_id text not null references lineage.scheduled_jobs,
    trigger_on        text not null default 'changed'
                          check (trigger_on in ('changed', 'completed')),
    rationale         text not null check (btrim(rationale) <> ''),
    primary key (job_id, depends_on_job_id),
    check (job_id <> depends_on_job_id)
);

create table if not exists lineage.job_runs (
    run_id            text primary key check (run_id ~ '^jrn_[0-9A-Z]{26}$'),
    job_id            text not null references lineage.scheduled_jobs on delete restrict,
    -- The DUE instant, never the tick clock: that is what makes a plan row idempotent per due
    -- window, so an hourly tick observes without flooding the ledger.
    planned_at        timestamptz not null,
    started_at        timestamptz,
    completed_at      timestamptz,
    launched_by       text not null check (launched_by in ('scheduler', 'manual')),
    outcome           text check (outcome in
                          ('would_run', 'ran', 'failed', 'interrupted', 'refused')),
    refusal_code      text references lineage.refusal_codes (code),
    failure_detail    text check (length(failure_detail) between 1 and 256),
    exit_status       integer,
    transient_unit    text,
    -- Null where systemd is older than 254: MemoryPeak does not exist there, and an absent
    -- measurement is stated rather than zeroed.
    memory_peak_bytes bigint check (memory_peak_bytes >= 0),
    derivation_id     text references lineage.derivations,
    correlation_id    text check (correlation_id is null or length(correlation_id) <= 128),
    check (completed_at is null or started_at is null or completed_at >= started_at),
    check (   (outcome is null       and completed_at is null and refusal_code is null)
           or (outcome = 'would_run' and started_at is null and completed_at is not null
               and refusal_code is null and failure_detail is null)
           or (outcome = 'ran'       and started_at is not null and completed_at is not null
               and refusal_code is null and failure_detail is null)
           or (outcome = 'failed'    and started_at is not null and completed_at is not null
               and refusal_code is null and failure_detail is not null)
           or (outcome = 'interrupted' and started_at is not null and completed_at is not null
               and refusal_code is not null)
           or (outcome = 'refused'   and started_at is null and completed_at is not null
               and refusal_code is not null))
);

comment on table lineage.job_runs is
    'Append-once run evidence in fetch_attempts shape. refused, failed and interrupted are'
    ' three different facts and collapsing them is the silence R8 forbids.';

create index if not exists job_runs_current_idx
    on lineage.job_runs (job_id, planned_at desc, run_id desc)
    include (started_at, completed_at, outcome, refusal_code);
create index if not exists job_runs_open_idx
    on lineage.job_runs (planned_at, run_id) where outcome is null;

-- One plan row per job per due window PER FACT: repeated ticks collide on the same triple and
-- the writer takes `on conflict do nothing`, so observing does not flood the ledger, while a
-- refusal and a later plan for the same instant both survive. `do update` is unavailable
-- because the completion guard refuses any update to an already-closed row. refusal_code is
-- deliberately not in the key: two different refusals at one instant collapse onto the first,
-- so the ledger keeps one row per fact class rather than one per reason, and the served row
-- names the reason a job first could not run in that window.
create unique index if not exists job_runs_plan_key
    on lineage.job_runs (job_id, planned_at, outcome)
    where outcome in ('would_run', 'refused');

drop trigger if exists refusal_codes_append_only on lineage.refusal_codes;
create trigger refusal_codes_append_only
    before update or delete on lineage.refusal_codes
    for each row execute function lineage.reject_mutation();

drop trigger if exists scheduled_jobs_append_only on lineage.scheduled_jobs;
create trigger scheduled_jobs_append_only
    before update or delete on lineage.scheduled_jobs
    for each row execute function lineage.reject_mutation();

drop trigger if exists job_sources_append_only on lineage.job_sources;
create trigger job_sources_append_only
    before update or delete on lineage.job_sources
    for each row execute function lineage.reject_mutation();

drop trigger if exists job_schedules_append_only on lineage.job_schedules;
create trigger job_schedules_append_only
    before update or delete on lineage.job_schedules
    for each row execute function lineage.reject_mutation();

drop trigger if exists job_dependencies_append_only on lineage.job_dependencies;
create trigger job_dependencies_append_only
    before update or delete on lineage.job_dependencies
    for each row execute function lineage.reject_mutation();

create or replace function lineage.guard_job_run_completion() returns trigger
language plpgsql as $$
begin
    if old.outcome is not null then
        raise exception 'completed job run % is immutable', old.run_id;
    end if;
    if new.outcome is null then
        raise exception 'job run % update must complete the run', old.run_id;
    end if;
    if row(new.run_id, new.job_id, new.planned_at, new.launched_by, new.correlation_id)
       is distinct from
       row(old.run_id, old.job_id, old.planned_at, old.launched_by, old.correlation_id)
    then
        raise exception 'job run % identity is immutable', old.run_id;
    end if;
    return new;
end
$$;

drop trigger if exists job_run_completion_guard on lineage.job_runs;
create trigger job_run_completion_guard
    before update on lineage.job_runs
    for each row execute function lineage.guard_job_run_completion();

drop trigger if exists job_run_delete_guard on lineage.job_runs;
create trigger job_run_delete_guard
    before delete on lineage.job_runs
    for each row execute function lineage.reject_mutation();

-- Two clocks, so two parameters, and no _current view for the reason 049 exists.
create or replace function lineage.job_schedules_as_of(knowledge_as_of date, valid_as_of date)
returns setof lineage.job_schedules
language sql stable parallel safe as $$
    select (ranked.schedule).*
      from (select s as schedule,
                   row_number() over (partition by s.job_id
                       order by s.effective_from desc, s.published_at desc) as rank
              from lineage.job_schedules s
             where s.published_at <= knowledge_as_of
               and s.effective_from <= valid_as_of) ranked
     where ranked.rank = 1;
$$;

comment on function lineage.job_schedules_as_of(date, date) is
    'The schedule serving at a knowledge instant for a valid instant. published_at desc is the'
    ' tie-breaker between a founding row and a restatement at the same effective_from.';

grant select on lineage.refusal_codes, lineage.scheduled_jobs, lineage.job_sources,
                lineage.job_schedules, lineage.job_dependencies, lineage.job_runs
    to glasswell_api, glasswell_pipeline;
grant insert, update on lineage.job_runs to glasswell_pipeline;
grant execute on function lineage.job_schedules_as_of(date, date)
    to glasswell_api, glasswell_pipeline;

-- The scheduler's own login identity. A root process cannot peer-authenticate as itself --
-- there is no role named root and this migration does not create one -- so install.sh maps OS
-- root onto this role through pg_ident. Its grants are the planner's reads and the ledger's
-- writes and nothing else: no canonical, no staging, no marts, and no glasswell_pipeline
-- membership, so the layer-boundary rule cannot be expressed here even by accident.
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'glasswell_scheduler') then
        create role glasswell_scheduler login;
    end if;
end
$$;

grant usage on schema lineage to glasswell_scheduler;
-- manifests and vintages are on this list because the moved source-health query reads five
-- lineage relations, not three: it selects max(vintage_date) from vintages and its two lateral
-- joins read manifests. Without them the first cadence tick raises InsufficientPrivilege and
-- returns no due set at all rather than a degraded one.
grant select on lineage.scheduled_jobs, lineage.job_sources, lineage.job_schedules,
                lineage.job_dependencies, lineage.refusal_codes, lineage.sources,
                lineage.source_poll_policies, lineage.fetch_attempts, lineage.manifests,
                lineage.vintages, lineage.conformance_rules
    to glasswell_scheduler;
grant select, insert, update on lineage.job_runs to glasswell_scheduler;
grant execute on function lineage.job_schedules_as_of(date, date) to glasswell_scheduler;

-- The three intervals a 35-day cadence was already implied for but never given, so the due
-- rule could compute nothing for them and /v1/health called them pending forever.
update lineage.source_poll_policies
   set cadence = 'Every 35 days', expected_poll_interval = interval '35 days'
 where source_id in ('tx_gis_wells_county', 'tx_wellbore_ewa_csv', 'nm_ocd_wells_gis');

-- 063 registered both EIA boundary sets and gave neither a cadence row, so /v1/health served
-- them cadence null and state pending permanently.
insert into lineage.source_poll_policies
    (source_id, cadence, expected_poll_interval, attempt_timeout)
values
    ('eia_sedimentary_basins', 'Every 35 days', interval '35 days', interval '6 hours'),
    ('eia_shale_plays', 'Every 35 days', interval '35 days', interval '6 hours')
on conflict (source_id) do nothing;

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-09-02', 'UNRELEASED',
       '0000000000000000000000000000000000000000'
  from unnest(array[
       'cr_job_cadence_ingest_nd_gis_1',
       'cr_job_cadence_ingest_nd_mpr_1',
       'cr_job_cadence_ingest_blm_plss_1',
       'cr_job_cadence_ingest_nm_c115b_1',
       'cr_job_cadence_ingest_fracfocus_1',
       'cr_job_cadence_ingest_mt_bogc_1',
       'cr_job_cadence_ingest_mt_gis_1',
       'cr_job_cadence_ingest_eia_boundaries_1',
       'cr_job_cadence_ingest_nm_ocd_stage_1',
       'cr_job_cadence_ingest_nm_ocd_promote_1',
       'cr_job_cadence_ingest_nm_dims_1',
       'cr_job_cadence_ingest_nm_wells_1',
       'cr_job_cadence_ingest_nm_wells_gis_1',
       'cr_job_cadence_ingest_tx_gis_1',
       'cr_job_cadence_ingest_tx_wellbore_1',
       'cr_job_cadence_marts_nd_wells_1',
       'cr_job_cadence_marts_nm_wells_1',
       'cr_job_cadence_marts_mt_wells_1',
       'cr_job_cadence_marts_tx_wells_1',
       'cr_job_cadence_marts_land_units_1',
       'cr_job_cadence_marts_land_metrics_1',
       'cr_job_cadence_marts_cumulatives_1',
       'cr_job_cadence_marts_neighbors_1',
       'cr_job_cadence_marts_basin_boundaries_1',
       'cr_job_cadence_marts_jurisdiction_counts_1'
  ]) as rule_id
    on conflict (rule_id) do nothing;
