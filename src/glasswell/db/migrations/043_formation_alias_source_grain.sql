-- The alias registry is source-scoped in conformance and serving, but migration 005 keyed it
-- only by (formation_raw, effective_from). That prevents two sources from preserving distinct
-- mappings learned on the same effective date. Keep the legacy unscoped namespace unique on
-- its own and make source_id part of the scoped grain; append-only history remains unchanged.

alter table lineage.formation_aliases drop constraint formation_aliases_pkey;

create unique index formation_aliases_scoped_uq
    on lineage.formation_aliases (formation_raw, source_id, effective_from)
    where source_id is not null;

create unique index formation_aliases_unscoped_uq
    on lineage.formation_aliases (formation_raw, effective_from)
    where source_id is null;

comment on index lineage.formation_aliases_scoped_uq is
    'One effective alias decision per source namespace and reported formation label.';

comment on index lineage.formation_aliases_unscoped_uq is
    'Legacy fallback aliases form one explicit unscoped namespace.';
