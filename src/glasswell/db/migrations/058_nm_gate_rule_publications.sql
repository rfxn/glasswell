-- Migration 049 makes repository publication evidence a precondition for every conformance
-- rule insert, so the rows this phase seeds register theirs first.
-- Publication evidence is a placeholder until the merge train repoints it. The tag below reads
-- UNRELEASED and the commit is forty zeros — the repository's agreed placeholder literals — and
-- `make release-check` refuses while they stand. `published_vintage` is NOT placeholdered — it
-- has no placeholder form — but migration 049's column comment defines knowledge time as the
-- first-tag date, so it is coupled to the release too: **repoint checklist — confirm this date
-- is the day the train actually ships.** lineage.conformance_rule_publications is append-only,
-- so a date that slips past midnight is permanently wrong.
--
-- Only the ids this migration's own seeder inserts are registered here: the publication catalog
-- is asserted to cover the shipped registry exactly, so a registration for a rule no seeder
-- ships yet is a failure rather than a harmless forward declaration.

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-08-30', 'v0.69',
       '70d3248c562f2bc03ed9d9d290ae2db73634ab91'
  from unnest(array[
       'cr_nm_wellhistory_api10_1', 'cr_nm_wellhistory_effective_1',
       'cr_nm_wellhistory_status_vocab_1', 'cr_nm_wellhistory_well_type_1',
       'cr_nm_wellhistory_datum_1', 'cr_nm_wellhistory_coordinate_1',
       'cr_nm_wellhistory_geometry_provenance_1', 'cr_nm_wellhistory_geometry_scope_1',
       'cr_nm_wellhistory_basin_scope_1', 'cr_nm_wellhistory_header_precedence_1',
       'cr_nm_wcproduction_pool_rollup_1'
  ]::text[]) as rule_id
on conflict (rule_id) do nothing;
