-- One granularity vocabulary at the store and at the wire (M-5). Reconciliation S-B composes
-- granularity x reporting_level into the served token: (observed, well) -> well_observed,
-- (observed, well_completion_pool) -> well_observed with an aggregation, (observed, lease) ->
-- lease_reported, (allocated, well) -> lease_allocated. Migration 008 admitted a row this
-- deployment's only sanctioned serializer would refuse, and refused one it can serve.
-- ND is well_observed throughout, so no live row changes class; TX is where this fires.

alter table canonical.production_monthly drop constraint production_monthly_granularity_check;

alter table canonical.production_monthly add constraint production_monthly_granularity_check
    check (granularity in ('well_observed', 'lease_reported', 'lease_allocated'));
