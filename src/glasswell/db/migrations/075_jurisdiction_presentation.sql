-- The web Wells rows become registration data. Seven facts each row in web/src/map/registry.ts
-- carried as an object literal -- its layer id, its style layers, its draw order, whether it is
-- on at first paint, which measured snapshot it cites, the subtitle the census fills, and the
-- legend note a jurisdiction may need -- move onto lineage.jurisdictions, so a fifth state is a
-- registration rather than four hand edits in a file no gate can read.
--
-- The append-only trigger forbids an UPDATE, so the backfill is four appended restatements at
-- the same effective_from and a strictly later published_at, each re-appending the rule rows it
-- declares. There is deliberately no `on conflict do nothing` on the restatement insert: an
-- unrepointed clock would otherwise collide with the founding key, be absorbed in silence, and
-- leave all seven columns null while the migration reported success.
--
-- This train also registers the decisions the mart engine and the neighbour mart read: which
-- basin governs a jurisdiction's compute CRS, which source computes its lateral length, and
-- whether the neighbour mart's measured domain reaches it. `length_scope` gains no new row --
-- the serving path reads that decision's existence as "withheld", so registering one for North
-- Dakota would delete its lateral length from the well card.
--
-- REPOINT CHECKLIST (integrator, at the merge train):
--   1. evidence_tag UNRELEASED -> the tag that first carries these rows. It appears ONCE, at
--      the conformance_rule_publications insert; the registration insert reads it back from
--      that row, so a half-repoint is not expressible in this file.
--   2. evidence_commit forty zeros -> the first commit on main that contains them, which is
--      the merge commit and not the head this branch was written against.
--   3. published_vintage 2026-09-02 -> the date the tag is cut. It is the conformance rules'
--      own clock and is read against the host's today, so it must never be a date the deploy
--      host has not reached: a rule published in the future resolves nowhere and
--      /v1/conformance/<id> serves 404 for it.
--   4. The restatement's published_at 2026-09-04 -> the same date, and it MUST be strictly
--      later than every founding published_at (2026-09-02); if both trains are cut on one day,
--      the restatement carries the following day. It must also not be the founding date plus
--      one day: two standing gates plant a rival registration on that instant and the partial
--      unique indexes would refuse them. Unlike the vintage above it may sit ahead of today --
--      load_jurisdictions reads max(published_at) as its knowledge cut, not the host clock.
--   5. seed/jurisdictions.py RESTATED_ON / RESTATED_EVIDENCE_TAG / RESTATED_EVIDENCE_COMMIT ->
--      the same three values, in the same commit. The seed is the second writer.

alter table lineage.jurisdictions
    add column if not exists wells_layer_id          text,
    add column if not exists wells_style_layer_ids   text[],
    add column if not exists wells_draw_order        integer,
    add column if not exists wells_default_on        boolean,
    add column if not exists wells_snapshot_key      text,
    add column if not exists wells_subtitle_template text,
    add column if not exists legend_note             text;

comment on column lineage.jurisdictions.wells_layer_id is
    'The client layer id for this jurisdiction''s wells row. North Dakota''s is the irregular'
    ' "wells" rather than "nd-wells": it predates the per-jurisdiction spelling and is frozen'
    ' by every saved permalink, so the registry carries the irregularity rather than a rule.';

comment on column lineage.jurisdictions.wells_style_layer_ids is
    'The style layers the row toggles, in draw order. Two today: the points and the struck'
    ' overlay. An array rather than a derivation, because a fifth may need three.';

comment on column lineage.jurisdictions.wells_draw_order is
    'A real per-row integer, not a rank over the family: disposal-wells sits at 41, between'
    ' North Dakota at 40 and Texas at 42.';

comment on column lineage.jurisdictions.wells_snapshot_key is
    'Which measured coverage snapshot the row cites, by key. Null where none is published.'
    ' A key rather than a value: the number and the refresh it was read from live in one'
    ' place in the client, and a registration must not be able to restate them.';

comment on column lineage.jurisdictions.wells_subtitle_template is
    'The subtitle with {count} where the measured well count goes. The count is fetched from'
    ' /v1/jurisdictions at render time with the date it was measured on, never generated in.';

comment on column lineage.jurisdictions.legend_note is
    'A per-jurisdiction line the legend renders, so no jurisdiction name enters legend.ts.';

do $$
begin
    if not exists (select 1 from pg_constraint
                    where conrelid = 'lineage.jurisdictions'::regclass
                      and conname = 'jurisdictions_wells_style_layers_together') then
        alter table lineage.jurisdictions
            add constraint jurisdictions_wells_style_layers_together
            check ((wells_layer_id is null) = (wells_style_layer_ids is null));
    end if;
    if not exists (select 1 from pg_constraint
                    where conrelid = 'lineage.jurisdictions'::regclass
                      and conname = 'jurisdictions_wells_draw_order_positive') then
        alter table lineage.jurisdictions
            add constraint jurisdictions_wells_draw_order_positive
            check (wells_draw_order is null or wells_draw_order > 0);
    end if;
    -- No naked numbers, and nowhere to put one either: a template with no slot for the
    -- measured count is a subtitle that can only ever carry a baked constant.
    if not exists (select 1 from pg_constraint
                    where conrelid = 'lineage.jurisdictions'::regclass
                      and conname = 'jurisdictions_wells_subtitle_has_a_count') then
        alter table lineage.jurisdictions
            add constraint jurisdictions_wells_subtitle_has_a_count
            check (wells_subtitle_template is null
                   or wells_subtitle_template like '%{count}%');
    end if;
end
$$;

create unique index if not exists jurisdictions_wells_draw_order_key
    on lineage.jurisdictions (wells_draw_order, effective_from, published_at)
    where wells_draw_order is not null;

-- The evidence pair, written once. 049's trigger refuses a conformance rule whose publication
-- is not registered, so this lands before the seeders that carry the rules themselves.
insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-09-02', 'UNRELEASED',
       '0000000000000000000000000000000000000000'
  from unnest(array[
       'cr_nd_basin_scope_1', 'cr_tx_basin_scope_1',
       'cr_nd_length_source_1', 'cr_tx_length_source_1',
       'cr_nd_neighbors_scope_1', 'cr_mt_neighbors_scope_1',
       'cr_mt_paths_length_scope_2'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;

-- Every value but the seven new ones is carried over from the row being restated rather than
-- restated by hand, so the restatement cannot drift from what it restates. The evidence pair is
-- read back from the publication row above: one literal in this file, and a repoint that moves
-- the registration without the rules is not expressible.
insert into lineage.jurisdictions (
    jurisdiction_code, effective_from, published_at, evidence_tag, evidence_commit,
    name, regulator_name, regulator_url, identity_scheme, identity_is_unique,
    identity_prefix, identity_pattern, source_ids, liquids_basis, wells_tile_layer_id,
    map_colour, neighbors_available, explorer_default, land_grid_state, land_grid_scope,
    status_dataset_detail, rationale, wells_layer_id, wells_style_layer_ids, wells_draw_order,
    wells_default_on, wells_snapshot_key, wells_subtitle_template, legend_note)
select founding.jurisdiction_code, founding.effective_from, date '2026-09-04',
       evidence.evidence_tag, evidence.evidence_commit,
       founding.name, founding.regulator_name, founding.regulator_url,
       founding.identity_scheme, founding.identity_is_unique, founding.identity_prefix,
       founding.identity_pattern, founding.source_ids, founding.liquids_basis,
       founding.wells_tile_layer_id, founding.map_colour, founding.neighbors_available,
       founding.explorer_default, founding.land_grid_state, founding.land_grid_scope,
       founding.status_dataset_detail, founding.rationale,
       presentation.wells_layer_id, presentation.wells_style_layer_ids,
       presentation.wells_draw_order, presentation.wells_default_on,
       presentation.wells_snapshot_key, presentation.wells_subtitle_template,
       presentation.legend_note
  from lineage.jurisdictions_as_of(date '2026-09-02', date '2026-09-02') founding
  join (values
    ('ND', 'wells', array['wells', 'wells-struck']::text[], 40, true,
     'nd_wells_refresh'::text,
     'ND DMR GIS surface locations · {count} points · culled by status below zoom 9'::text,
     null::text),
    ('TX', 'tx-wells', array['tx-wells', 'tx-wells-struck']::text[], 42, true,
     null::text,
     'TX RRC GIS surface locations, 55 Permian-district counties · {count} points'::text,
     null::text),
    ('NM', 'nm-wells', array['nm-wells', 'nm-wells-struck']::text[], 43, true,
     null::text,
     'NM OCD well-header surface locations · {count} points, ten of the fourteen OCD status'
     ' codes mapped and four documented without an equivalent'
     ' (cr_nm_wellhistory_status_vocab_2)'::text,
     null::text),
    ('MT', 'mt-wells', array['mt-wells', 'mt-wells-struck']::text[], 44, true,
     null::text,
     'MBOGC surface locations · {count} points, 13 of the 19 filed status values mapped and'
     ' the other 6 quarantined rather than defaulted (cr_mt_gis_status_vocab_1) · no basin'
     ' tag: Bakken is 4.6% of Montana (cr_mt_basin_scope_1) · completion year, never a'
     ' spud'::text,
     null::text)
  ) as presentation(jurisdiction_code, wells_layer_id, wells_style_layer_ids, wells_draw_order,
                    wells_default_on, wells_snapshot_key, wells_subtitle_template, legend_note)
    on presentation.jurisdiction_code = founding.jurisdiction_code
 cross join (select evidence_tag, evidence_commit
               from lineage.conformance_rule_publications
              where rule_id = 'cr_nd_basin_scope_1') evidence;

-- Guarded on residency exactly as 073's insert is: migrations run before the seed, so on a
-- fresh database lineage.conformance_rules is empty and seed/jurisdictions.py supplies these.
-- On a database that is already seeded -- the deployed one -- this is what lands them.
insert into lineage.jurisdiction_rules
    (jurisdiction_code, effective_from, published_at, decision, rule_id, serving, note)
select r.jurisdiction_code, date '2026-09-02', date '2026-09-04',
       r.decision, r.rule_id, r.serving, r.note
  from (values
    ('ND', 'status_vocabulary', 'cr_nd_status_vocab_1', true, null::text),
    ('ND', 'geometry_provenance', 'cr_nd_geometry_provenance_1', true, null::text),
    ('ND', 'liquids', 'cr_nd_liquids_policy_1', true, null::text),
    ('ND', 'production_grain', 'cr_nd_pool_rollup_1', true, null::text),
    ('ND', 'inventory_jurisdiction', 'cr_nd_inventory_jurisdiction_1', true, null::text),
    ('ND', 'identity', 'cr_nd_api_identity_1', true, null::text),
    ('ND', 'basin_scope', 'cr_nd_basin_scope_1', true, null::text),
    ('ND', 'length_source', 'cr_nd_length_source_1', true, null::text),
    ('ND', 'neighbors_scope', 'cr_nd_neighbors_scope_1', true, null::text),
    ('TX', 'status_vocabulary', 'cr_tx_status_vocab_1', true, null::text),
    ('TX', 'identity', 'cr_tx_api10_build_1', true, null::text),
    ('TX', 'absence:operator', 'cr_tx_operator_absence_1', true, null::text),
    ('TX', 'basin_scope', 'cr_tx_basin_scope_1', true, null::text),
    ('TX', 'length_source', 'cr_tx_length_source_1', true, null::text),
    ('NM', 'status_vocabulary', 'cr_nm_wellhistory_status_vocab_2', true, null::text),
    ('NM', 'geometry_provenance', 'cr_nm_wellhistory_geometry_provenance_1', true, null::text),
    ('NM', 'liquids', 'cr_nm_wcproduction_liquids_1', true, null::text),
    ('NM', 'production_grain', 'cr_nm_wcproduction_pool_rollup_1', true, null::text),
    ('NM', 'inventory_jurisdiction', 'cr_nm_wcproduction_inventory_jurisdiction_1', true,
     null::text),
    ('NM', 'identity', 'cr_nm_wchistory_api10_1', true, null::text),
    ('NM', 'basin_scope', 'cr_nm_wellhistory_basin_scope_1', true, null::text),
    ('MT', 'status_vocabulary', 'cr_mt_gis_status_vocab_1', true, null::text),
    ('MT', 'geometry_provenance', 'cr_mt_paths_geometry_class_1', true, null::text),
    ('MT', 'liquids', 'cr_mt_liquids_policy_1', true, null::text),
    ('MT', 'inventory_jurisdiction', 'cr_mt_inventory_jurisdiction_1', true, null::text),
    ('MT', 'inventory_jurisdiction', 'cr_mt_pru_inventory_jurisdiction_1', false,
     'PRU lease grain'),
    ('MT', 'length_scope', 'cr_mt_paths_length_scope_2', true, null::text),
    ('MT', 'absence:operator', 'cr_mt_operator_absence_1', true, null::text),
    ('MT', 'basin_scope', 'cr_mt_basin_scope_1', true, null::text),
    ('MT', 'neighbors_scope', 'cr_mt_neighbors_scope_1', true, null::text)
  ) as r(jurisdiction_code, decision, rule_id, serving, note)
 where exists (select 1 from lineage.conformance_rules c where c.rule_id = r.rule_id)
on conflict do nothing;

-- The supersession, recorded the way 071 records one: the rule is appended, never edited, and
-- what changed between the two is on the audit trail rather than only in the rationale.
insert into lineage.audit_events (event_id, occurred_at, actor, event_type, subject_type,
                                  subject_id, payload)
select 'evt_migration_cr_mt_paths_length_scope_2', now(), 'system:migration',
       'conformance.rule_superseded', 'rule', 'cr_mt_paths_length_scope_2',
       jsonb_build_object('supersedes', 'cr_mt_paths_length_scope_1',
                          'from_spec', 'length_rule_source_if_defaulted:'
                                       ' nd_gis_horizontals_line',
                          'to_spec', 'no default; an unregistered length source is a served'
                                     ' refusal with its own reason code',
                          'migration', 'jurisdiction_presentation')
 where exists (select 1 from lineage.conformance_rules
                where rule_id = 'cr_mt_paths_length_scope_2')
   and not exists (select 1 from lineage.audit_events
                    where event_id = 'evt_migration_cr_mt_paths_length_scope_2');
