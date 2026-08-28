-- Selector-bearing handles are executable claims about one served output. Register every
-- admitted claim shape, and give request-computed aggregates their own derivation operation.

alter table lineage.derivations drop constraint derivations_operation_check;
alter table lineage.derivations add constraint derivations_operation_check check (operation in (
    'raw.fetch', 'stage.parse', 'canonical.promote', 'features.build', 'model.train',
    'model.calibrate', 'forecast.batch', 'forecast.scenario', 'econ.value',
    'econ.sensitivity', 'alloc.apply', 'typecurve.build', 'analog.index', 'analog.query',
    'mart.refresh', 'tiles.build', 'ledger.grade', 'inventory.run', 'api.respond'));

create table lineage.selector_output_registry (
    operation        text not null,
    output_dataset   text not null,
    selector_profile text not null,
    rationale        text not null,
    primary key (operation, output_dataset, selector_profile)
);

comment on table lineage.selector_output_registry is
    'Fail-closed registry of selector grammars that may address a derivation output.';

create table lineage.response_selector_outputs (
    derivation_id  text not null references lineage.derivations (derivation_id) on delete restrict,
    selector       text not null,
    evidence       jsonb not null,
    primary key (derivation_id, selector)
);

comment on table lineage.response_selector_outputs is
    'Exact response figures persisted outside derivation identity so output changes collide.';

create or replace function lineage.guard_response_selector_output_mutation()
returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE'
       and current_setting('glasswell.retention_sweep', true) = 'on' then
        return old;
    end if;
    raise exception 'append_only_violation on lineage.response_selector_outputs'
        using errcode = 'restrict_violation';
end
$$;

create trigger response_selector_outputs_append_only
    before update or delete on lineage.response_selector_outputs
    for each row execute function lineage.guard_response_selector_output_mutation();

insert into lineage.selector_output_registry
    (operation, output_dataset, selector_profile, rationale)
values
    ('canonical.promote', 'canonical.production_monthly', 'production_series',
     'Well and completion-pool production series and points persisted by the promotion.'),
    ('canonical.promote', 'canonical.production_monthly', 'completion_pool',
     'ND MPR promotion also persists the completion-pool observation addressed by the handle.'),
    ('alloc.apply', 'canonical.production_monthly', 'production_series',
     'Allocated production is validated at the persisted canonical production grain.'),
    ('canonical.promote', 'canonical.well_completions', 'completion_pool',
     'Completion-dimension promotions persist the addressed completion observation.'),
    ('canonical.promote', 'canonical.well_completion_anchors', 'completion_anchor',
     'FracFocus promotion persists the addressed completion anchor.'),
    ('canonical.promote', 'canonical.wells', 'well',
     'Well promotion persists the addressed reported well value.'),
    ('mart.refresh', 'marts.nd_neighbors', 'nd_neighbor',
     'The neighbour mart persists subject, edge and bounded coverage evidence.'),
    ('api.respond', 'api.well_detail', 'response_output',
     'The request derivation records the measured lateral aggregate it returned.'),
    ('api.respond', 'api.well_status_summary', 'response_output',
     'The request derivation records every aggregate count returned for the viewport.');

grant select on lineage.selector_output_registry to glasswell_pipeline, glasswell_api;
grant select on lineage.response_selector_outputs to glasswell_pipeline, glasswell_api;
grant insert on lineage.response_selector_outputs to glasswell_api;
grant insert on lineage.environments to glasswell_api;
grant insert on lineage.derivation_rules to glasswell_api;
revoke update, delete on lineage.selector_output_registry, lineage.environments
    from glasswell_api;

create or replace function lineage.sweep_ephemeral_derivations(
    cutoff timestamptz default now() - interval '90 days'
) returns bigint
language plpgsql
security definer
set search_path = pg_catalog, lineage
as $$
declare
    candidate_id text;
    deleted_count bigint;
    deleted_this bigint;
begin
    deleted_count := 0;
    for candidate_id in
        select d.derivation_id
          from lineage.derivations d
         where d.ttl_class = 'ephemeral'
           and d.status = 'ok'
           and d.created_at < cutoff
           and not exists (
               select 1
                 from lineage.derivation_inputs i
                where i.kind = 'derivation'
                  and i.ref_id = d.derivation_id
           )
         order by d.derivation_id
         limit 50000
    loop
        begin
            perform set_config('glasswell.retention_sweep', 'on', true);
            delete from lineage.response_selector_outputs where derivation_id = candidate_id;
            delete from lineage.derivation_rules where derivation_id = candidate_id;
            delete from lineage.derivation_inputs where derivation_id = candidate_id;
            delete from lineage.derivations where derivation_id = candidate_id;
            get diagnostics deleted_this = row_count;
            deleted_count := deleted_count + deleted_this;
        exception
            when foreign_key_violation then
                -- A served artifact or future table still owns this derivation. The block is
                -- a subtransaction, so its selector/rule/input evidence is restored as well.
                null;
        end;
    end loop;
    return deleted_count;
end
$$;

comment on function lineage.sweep_ephemeral_derivations(timestamptz) is
    'Delete successful unreferenced ephemeral derivations older than the supplied cutoff.';

revoke all on function lineage.sweep_ephemeral_derivations(timestamptz) from public;
revoke all on function lineage.sweep_ephemeral_derivations(timestamptz) from glasswell_api;
grant execute on function lineage.sweep_ephemeral_derivations(timestamptz)
    to glasswell_pipeline;
