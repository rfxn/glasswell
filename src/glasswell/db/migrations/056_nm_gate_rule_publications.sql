-- Migration 049 made repository publication evidence a precondition for every conformance rule
-- insert, so the rows the New Mexico gate seeds register theirs first. v0.68 is the first tag to
-- contain these ids; the commit is the `main` head the branch was written against, because the
-- commit that introduces a rule cannot cite its own hash.
--
-- Only the ids this migration's own seeder inserts are registered here: the publication catalog
-- is asserted to cover the shipped registry exactly, so a registration for a rule no seeder
-- ships yet is a failure rather than a harmless forward declaration.

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-08-30', 'v0.68',
       'c8cffbc344e1ea36e454e43f3c0a4d7696aa1c0a'
  from unnest(array[
       'cr_nm_wellhistory_api10_1', 'cr_nm_wellhistory_effective_1',
       'cr_nm_wellhistory_status_vocab_1', 'cr_nm_wellhistory_well_type_1',
       'cr_nm_wellhistory_datum_1', 'cr_nm_wellhistory_coordinate_1',
       'cr_nm_wellhistory_geometry_provenance_1', 'cr_nm_wellhistory_geometry_scope_1',
       'cr_nm_wellhistory_basin_scope_1', 'cr_nm_wellhistory_header_precedence_1',
       'cr_nm_wcproduction_pool_rollup_1'
  ]::text[]) as rule_id
on conflict (rule_id) do nothing;
