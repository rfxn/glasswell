-- Populate the first named feature version for already-migrated databases. Fresh databases
-- receive the identical row from glasswell.seed.features; both paths are idempotent.

insert into features.feature_specs
    (feature_id, family, dtype, unit, knowable_at_rule, publication_lag_days_p50,
     transform_id, params, source_refs, missing_policy, member_of, introduced_in_fv)
values
    ('geology.formation_group', 'geology', 'categorical', 'category', 'completion_date', 0,
     'lookup_formation_alias',
     '{"alias_table":"lineage.formation_aliases","min_confidence":"0.800",'
     '"reported_pool_field":"pool_reported","source_id":"nd_mpr_xlsx"}'::jsonb,
     array['canonical.well_completions.pool_reported', 'lineage.formation_aliases'],
     'native_nan',
     array['design_adjusted', 'full', 'no_depletion', 'rock_location_only'],
     'fv1.0')
on conflict (feature_id, introduced_in_fv) do nothing;
