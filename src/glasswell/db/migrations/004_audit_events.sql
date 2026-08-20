-- Append-only audit stream (SB-07 §5.1). Enforced twice: role grants, then a trigger.

create function lineage.reject_mutation() returns trigger
language plpgsql
as $$
begin
    raise exception 'append_only_violation: % is not permitted on %', tg_op, tg_table_name
        using errcode = 'restrict_violation';
end
$$;

create table lineage.audit_events (
    event_id       text not null,
    occurred_at    timestamptz not null,
    actor          text not null,
    event_type     text not null,
    subject_type   text not null,
    subject_id     text not null,
    correlation_id text,
    payload        jsonb not null default '{}'::jsonb,
    primary key (event_id, occurred_at)
) partition by range (occurred_at);

-- SB-06 creates monthly partitions a month ahead; the default catches anything it missed.
create table lineage.audit_events_default partition of lineage.audit_events default;

create index audit_events_subject_idx on lineage.audit_events (subject_type, subject_id);
create index audit_events_type_idx on lineage.audit_events (event_type, occurred_at);
create index audit_events_correlation_idx on lineage.audit_events (correlation_id);

create trigger audit_events_append_only
    before update or delete on lineage.audit_events
    for each row execute function lineage.reject_mutation();

grant select, insert on lineage.audit_events to glasswell_pipeline, glasswell_api;
revoke update, delete on lineage.audit_events from glasswell_pipeline, glasswell_api;
