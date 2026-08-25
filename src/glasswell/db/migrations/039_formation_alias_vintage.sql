-- `effective_from` is valid time: it says when an alias mapping applies. C2 also needs the
-- independent date glasswell learned the mapping, or a late correction backdated to an old
-- effective date can enter a historical feature matrix.

alter table lineage.formation_aliases add column created_vintage date;

comment on column lineage.formation_aliases.created_vintage is
    'Knowledge time: the vintage at which glasswell learned this mapping. A feature build'
    ' refuses an applicable alias whose knowledge vintage is absent.';

create trigger formation_aliases_append_only
    before update or delete on lineage.formation_aliases
    for each row execute function lineage.reject_mutation();

revoke update, delete on lineage.formation_aliases from glasswell_pipeline, glasswell_api;
