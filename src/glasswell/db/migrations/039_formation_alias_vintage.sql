-- `effective_from` is valid time: it says when an alias mapping applies. C2 also needs the
-- independent date glasswell learned the mapping, or a late correction backdated to an old
-- effective date can enter a historical feature matrix.

alter table lineage.formation_aliases add column created_vintage date;

comment on column lineage.formation_aliases.created_vintage is
    'Knowledge time: the vintage at which glasswell learned this mapping. A feature build'
    ' refuses an applicable alias whose knowledge vintage is absent.';
