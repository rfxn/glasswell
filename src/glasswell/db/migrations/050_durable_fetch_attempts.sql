-- Independently committed source-poll evidence and its single cadence registry.

create table lineage.source_poll_policies (
    source_id                  text primary key,
    cadence                    text not null check (
                                   length(cadence) between 1 and 80),
    expected_poll_interval     interval,
    attempt_timeout            interval not null default interval '6 hours',
    check (expected_poll_interval is null or expected_poll_interval > interval '0 seconds'),
    check (attempt_timeout > interval '0 seconds')
);

comment on table lineage.source_poll_policies is
    'The sole runtime registry for source-specific poll cadence and interrupted-attempt bounds.';
comment on column lineage.source_poll_policies.expected_poll_interval is
    'Null only for event-driven sources whose next poll cannot be predicted from elapsed time.';

insert into lineage.source_poll_policies
    (source_id, cadence, expected_poll_interval, attempt_timeout)
values
    ('blm_plss_sections', 'Every 35 days', interval '35 days', interval '6 hours'),
    ('blm_plss_townships', 'Every 35 days', interval '35 days', interval '6 hours'),
    ('fracfocus_csv', 'Owner-triggered; no recurring timer', null, interval '6 hours'),
    ('nd_gis_directionals', 'Every 35 days', interval '35 days', interval '6 hours'),
    ('nd_gis_horizontals_line', 'Every 35 days', interval '35 days', interval '6 hours'),
    ('nd_gis_spacing_units', 'Every 35 days', interval '35 days', interval '6 hours'),
    ('nd_gis_wells', 'Every 35 days', interval '35 days', interval '6 hours'),
    ('nd_mpr_xlsx', 'Every 35 days', interval '35 days', interval '6 hours'),
    ('nm_c115b_upstream', 'Every 35 days', interval '35 days', interval '6 hours'),
    ('nm_ocd_ogrid', 'Owner-triggered; no recurring timer', null, interval '6 hours'),
    ('nm_ocd_pod', 'Owner-triggered; no recurring timer', null, interval '6 hours'),
    ('nm_ocd_podwc', 'Owner-triggered; no recurring timer', null, interval '6 hours'),
    ('nm_ocd_pool', 'Owner-triggered; no recurring timer', null, interval '6 hours'),
    ('nm_ocd_property', 'Owner-triggered; no recurring timer', null, interval '6 hours'),
    ('nm_ocd_spacingunit', 'Owner-triggered; no recurring timer', null, interval '6 hours'),
    ('nm_ocd_wchistory', 'Owner-triggered; no recurring timer', null, interval '6 hours'),
    ('nm_ocd_wcproduction', 'Owner-triggered; no recurring timer', null, interval '6 hours'),
    ('nm_ocd_wellhistory', 'Owner-triggered; no recurring timer', null, interval '6 hours'),
    ('proj_grid_nad27', 'When the dependency pin changes', null, interval '1 hour'),
    ('tx_gis_wells_county', 'Owner-triggered; no recurring timer', null, interval '6 hours'),
    ('tx_pdq_dsv', 'Owner-triggered; no recurring timer', null, interval '12 hours'),
    ('tx_wellbore_ewa_csv', 'Owner-triggered; no recurring timer', null, interval '12 hours');

create table lineage.fetch_attempts (
    attempt_id       text primary key check (attempt_id ~ '^fat_[0-9A-Z]{26}$'),
    source_id        text not null references lineage.sources (source_id) on delete restrict,
    source_key       text not null check (length(source_key) between 1 and 512),
    attempted_at     timestamptz not null,
    completed_at     timestamptz,
    outcome          text check (outcome in ('new', 'unchanged', 'failed')),
    manifest_id      text references lineage.manifests (manifest_id) on delete restrict,
    failure_code     text check (failure_code ~ '^[a-z][a-z0-9_]{0,63}$'),
    failure_detail   text check (length(failure_detail) between 1 and 256),
    correlation_id   text check (correlation_id is null or length(correlation_id) <= 128),
    check (completed_at is null or completed_at >= attempted_at),
    check (
        (outcome is null and completed_at is null and manifest_id is null
            and failure_code is null and failure_detail is null)
        or
        (outcome in ('new', 'unchanged') and completed_at is not null
            and manifest_id is not null and failure_code is null and failure_detail is null)
        or
        (outcome = 'failed' and completed_at is not null and manifest_id is null
            and failure_code is not null and failure_detail is not null)
    )
);

comment on table lineage.fetch_attempts is
    'Append-once source polls. A null outcome is durable attempted evidence that may still be'
    ' active or may have been interrupted; Status applies the registered attempt timeout.';
comment on column lineage.fetch_attempts.outcome is
    'new only after the new manifest is committed and independently visible; unchanged only'
    ' after the referenced existing manifest is independently visible.';

create index fetch_attempts_current_idx
    on lineage.fetch_attempts (source_id, attempted_at desc, attempt_id desc)
    include (completed_at, outcome, manifest_id, failure_code, failure_detail);
create index fetch_attempts_key_current_idx
    on lineage.fetch_attempts (source_id, source_key, attempted_at desc, attempt_id desc)
    include (completed_at, outcome, manifest_id, failure_code, failure_detail);
create index fetch_attempts_open_idx
    on lineage.fetch_attempts (attempted_at, attempt_id)
    where outcome is null;

create function lineage.guard_fetch_attempt_completion() returns trigger
language plpgsql as $$
begin
    if old.outcome is not null then
        raise exception 'completed fetch attempt % is immutable', old.attempt_id;
    end if;
    if new.outcome is null then
        raise exception 'fetch attempt % update must complete the attempt', old.attempt_id;
    end if;
    if row(new.attempt_id, new.source_id, new.source_key, new.attempted_at, new.correlation_id)
       is distinct from
       row(old.attempt_id, old.source_id, old.source_key, old.attempted_at, old.correlation_id)
    then
        raise exception 'fetch attempt % identity is immutable', old.attempt_id;
    end if;
    return new;
end
$$;

create trigger fetch_attempt_completion_guard
before update on lineage.fetch_attempts
for each row execute function lineage.guard_fetch_attempt_completion();

create trigger fetch_attempt_delete_guard
before delete on lineage.fetch_attempts
for each row execute function lineage.reject_mutation();

grant select, insert, update on lineage.fetch_attempts to glasswell_pipeline;
grant select on lineage.fetch_attempts, lineage.source_poll_policies to glasswell_api;
grant select on lineage.source_poll_policies to glasswell_pipeline;
