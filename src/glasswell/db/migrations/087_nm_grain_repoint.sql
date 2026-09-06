-- New Mexico's production_grain decision resolves to the rule it was superseded by, on every host
-- that migrated before it seeded. scripts/deploy.sh runs step 6 (migrate) ahead of step 6b
-- (seed_all), so 085's guarded CASE read a registry in which cr_nm_wcproduction_pool_rollup_2 was
-- not yet resident -- the successor is seeded in Python, from glasswell.seed.conformance_nm_wells --
-- while the founding rule, seeded by every release before this one, was. It therefore appended the
-- founding rule at the 2026-09-06 restatement instant, and the seed that landed the successor a
-- step later could not move it: lineage.jurisdiction_rules is append-only, and the row the seed
-- offers collides with the resident one on jurisdiction_rules_serving_key, so `on conflict do
-- nothing` reads as success. On a fresh database neither rule is resident when 085 applies, both
-- of its production_grain inserts land nothing and the seed writes the decision unopposed, which
-- is why the suite was green against a live registry that named the wrong rule.
--
-- Measured on VM 111 after the v0.83 deploy: marts.well_pool_rollup built for no jurisdiction and
-- 0 rows, because the mart is registry-driven and cr_nm_wcproduction_pool_rollup_1's own spec says
-- glasswell performs no rollup. Had it built, the served sum would have cited a rule that says
-- there is no sum.
--
-- The correction is a new published instant and not an edit to the old one. 073's
-- jurisdiction_rules_append_only trigger refuses UPDATE and DELETE outright, and what 2026-09-06
-- published was served -- a registry that rewrites what it served is the failure two clocks exist
-- to prevent. So New Mexico is restated at 2026-09-07 carrying every rule row its own registration
-- declares, with production_grain naming the successor and a note saying why the instant exists.
--
-- Guarded on both sides, so this file is a no-op wherever 085 already chose the successor: every
-- fresh database, and every host that seeded before it migrated. It publishes no conformance rule
-- and so carries no evidence placeholder and no repoint checklist -- the correction restates a
-- decision v0.83 published, and carries v0.83's evidence pair forward by reading it off the row it
-- restates. glasswell.seed.jurisdictions is the second writer of the same correction, for the host
-- where the successor is not resident at this migration either, and spells the same instant, rule
-- and note.

insert into lineage.jurisdictions (
    jurisdiction_code, effective_from, published_at, evidence_tag, evidence_commit,
    name, regulator_name, regulator_url, identity_scheme, identity_is_unique,
    identity_prefix, identity_pattern, source_ids, liquids_basis, wells_tile_layer_id,
    map_colour, neighbors_available, explorer_default, land_grid_state, land_grid_scope,
    status_dataset_detail, rationale, wells_layer_id, wells_style_layer_ids, wells_draw_order,
    wells_default_on, wells_snapshot_key, wells_subtitle_template, legend_note)
select prior.jurisdiction_code, prior.effective_from, date '2026-09-07',
       prior.evidence_tag, prior.evidence_commit,
       prior.name, prior.regulator_name, prior.regulator_url,
       prior.identity_scheme, prior.identity_is_unique, prior.identity_prefix,
       prior.identity_pattern, prior.source_ids, prior.liquids_basis,
       prior.wells_tile_layer_id, prior.map_colour, prior.neighbors_available,
       prior.explorer_default, prior.land_grid_state, prior.land_grid_scope,
       prior.status_dataset_detail, prior.rationale, prior.wells_layer_id,
       prior.wells_style_layer_ids, prior.wells_draw_order, prior.wells_default_on,
       prior.wells_snapshot_key, prior.wells_subtitle_template, prior.legend_note
  from lineage.jurisdictions_as_of(
           (select max(published_at) from lineage.jurisdictions), current_date) prior
 where prior.jurisdiction_code = 'NM'
   and exists (select 1 from lineage.conformance_rules c
                where c.rule_id = 'cr_nm_wcproduction_pool_rollup_2')
   and exists (select 1 from lineage.jurisdiction_rules r
                where r.jurisdiction_code = prior.jurisdiction_code
                  and r.effective_from = prior.effective_from
                  and r.published_at = prior.published_at
                  and r.decision = 'production_grain'
                  and r.serving
                  and r.rule_id = 'cr_nm_wcproduction_pool_rollup_1')
on conflict do nothing;

-- Every rule row the corrected registration declares, read back from the instant it corrects
-- rather than respelled, with the one decision that moved repointed. The join is the guard: where
-- the registration above landed nothing, this lands nothing.
insert into lineage.jurisdiction_rules
    (jurisdiction_code, effective_from, published_at, decision, rule_id, serving, note)
select prior.jurisdiction_code, prior.effective_from, corrected.published_at, prior.decision,
       case when prior.decision = 'production_grain'
            then 'cr_nm_wcproduction_pool_rollup_2' else prior.rule_id end,
       prior.serving,
       case when prior.decision = 'production_grain'
            then 'repointed to the successor the restatement instant could not name: the'
                 ' successor was not resident when the migration that restated it ran'
            else prior.note end
  from lineage.jurisdiction_rules prior
  join lineage.jurisdictions corrected
    on corrected.jurisdiction_code = prior.jurisdiction_code
   and corrected.effective_from = prior.effective_from
   and corrected.published_at = date '2026-09-07'
 where prior.jurisdiction_code = 'NM'
   and prior.published_at = (select max(p.published_at) from lineage.jurisdiction_rules p
                              where p.jurisdiction_code = prior.jurisdiction_code
                                and p.published_at < date '2026-09-07')
on conflict do nothing;

-- The supersession 085 could not record, in the shape it records one: guarded on the successor
-- being resident and on the event not already being on the trail, so the fact is recorded once
-- whichever migration reaches it first.
insert into lineage.audit_events (event_id, occurred_at, actor, event_type, subject_type,
                                  subject_id, payload)
select 'evt_migration_cr_nm_wcproduction_pool_rollup_2', now(), 'system:migration',
       'conformance.rule_superseded', 'rule', 'cr_nm_wcproduction_pool_rollup_2',
       jsonb_build_object('supersedes', 'cr_nm_wcproduction_pool_rollup_1',
                          'from_spec', 'no served rollup; the regulator files at completion-pool'
                                       ' grain and glasswell performs none',
                          'to_spec', 'served_rollup: sum_over_pools, served_from:'
                                     ' marts.well_pool_rollup, promotes_to_canonical: false',
                          'migration', 'nm_grain_repoint')
 where exists (select 1 from lineage.conformance_rules
                where rule_id = 'cr_nm_wcproduction_pool_rollup_2')
   and not exists (select 1 from lineage.audit_events
                    where event_id = 'evt_migration_cr_nm_wcproduction_pool_rollup_2');

-- The knowledge cut the resolver reads is max(published_at) over the registry, and the correction
-- above moves it. 085 ends the same way and for the same reason.
select lineage.refresh_status_resolution();
