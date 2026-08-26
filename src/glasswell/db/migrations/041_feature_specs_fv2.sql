-- Preserve fv1.0 exactly and append corrected initial-pool semantics as fv2.0.

insert into features.feature_specs
    (feature_id, family, dtype, unit, knowable_at_rule, publication_lag_days_p50,
     transform_id, params, source_refs, missing_policy, member_of, introduced_in_fv)
values
    ('geology.formation_group', 'geology', 'categorical', 'category', 'completion_date', 82,
     'lookup_initial_formation_alias',
     $json${
       "alias_table":"lineage.formation_aliases",
       "conflict_policy":"null_with_coverage",
       "min_confidence":"0.800",
       "publication_lag_measurement":{
         "availability_proxy":"first_formation_source_month_plus_45_days",
         "cohort":"completion_on_or_after_2015-05-01_and_nonnegative_lag",
         "measured_at":"2026-08-26",
         "n":9031,
         "negative_lag_exclusions":292,
         "p25_days":53,
         "p50_days":82,
         "p75_days":177,
         "p95_days":224
       },
       "reported_pool_field":"pool_reported",
       "source_history_floor":"2015-05-01",
       "source_id":"nd_mpr_xlsx",
       "source_publication_lag_days":45
     }$json$::jsonb,
     array['canonical.well_completions.pool_reported', 'lineage.formation_aliases'],
     'native_nan',
     array['design_adjusted', 'full', 'no_depletion', 'rock_location_only'],
     'fv2.0')
on conflict (feature_id, introduced_in_fv) do nothing;
