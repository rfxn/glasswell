-- ECMC files an empty string where it files no value, and ingest/co_ecmc_gis.py staged it
-- verbatim: `str(value).strip()` for every attribute of all three GIS archives. Colorado is the
-- only jurisdiction in the registry that produces the empty string, and an empty string is not
-- a smaller absence -- it is a different answer. 1,172 of the 124,392 promoted Colorado headers
-- carry it as their well type, and /v1/wells/status-summary refused every viewport holding one
-- of them with 422 selector_ambiguous, because the selector grammar admits no empty value.
--
-- R8 makes "blank is absent" a row rather than a call to nullif: cr_co_wells_shp_blank_is_absent_1,
-- cr_co_directional_bh_blank_is_absent_1 and cr_co_directional_lines_blank_is_absent_1 carry the
-- decision per layer, and this migration is the publication evidence 049's trigger requires
-- before the seeder may insert them. The rule bodies live in glasswell.seed.conformance_co.
--
-- No rule is superseded. cr_co_wells_well_type_1 says Well_Class is served exactly as ECMC
-- filed it and that stands: these rows say what "filed nothing" is, which is a question it
-- never answered.
--
-- The 124,392 rows already promoted are read under the rule, not restated. canonical.wells is
-- keyed (api10, effective_from) and Colorado's effective_from is ECMC's own Stat_Date
-- (cr_co_wells_effective_1), so a corrected row carries the key of the row it corrects and the
-- append is refused; an effective date the regulator never filed is the invention
-- ingest/co_wells.py already refuses for status_canonical. glasswell.absence:absent_if_blank is
-- where the read applies it, once, so the tile mart, the well card and the status summary
-- cannot answer differently on the same screen.
--
-- RENUMBERED at the v0.83 train: this file was 084_co_blank_is_absent.sql on fix/co-blank-well-type
-- (cut from main 80fb09d, whose last migration was 083); it is 086 behind 085_status_vocabulary.sql,
-- because db/migrate.py:63-66 refuses both a gap and a duplicate. Nothing about the number is owed.
--
-- REPOINT CHECKLIST (integrator, at the merge train):
--   1. evidence_tag UNRELEASED -> the tag that first carries these three rule ids. It appears
--      ONCE, at the insert below.
--   2. evidence_commit forty zeros -> the first commit on main that contains them, which is the
--      merge commit and not the head this branch was written against.
--   3. published_vintage 2026-09-05 -> the date the tag is cut, and never a date the deploy host
--      has not reached: load_rules filters on published_vintage <= today, so a vintage ahead of
--      the host leaves the three rows unresolvable while the staging that cites them runs.

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-09-06', 'v0.83',
       'ac9cccd4541112bad96ec5a420b890b9a9cbde0d'
  from unnest(array[
       'cr_co_wells_shp_blank_is_absent_1',
       'cr_co_directional_bh_blank_is_absent_1',
       'cr_co_directional_lines_blank_is_absent_1'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;

-- The decision, as a row. R8 is not "a rule exists" but "a rule the derivations it shaped
-- reference", and this rule shapes served figures: api/routers/wells.py reads every
-- source-reported text column of the spine under it, and /v1/wells/status-summary groups by a
-- well type it has applied. Registered per jurisdiction so the citation is Colorado's alone --
-- a rule about ECMC's blanks on a Texas box is the mistake wells.py:1663-1670 already records
-- in the other direction.
--
-- The instant is Colorado's existing registration (2026-09-02), not this train's date: the
-- composite foreign key binds a rule row to the registration it belongs to, and this appends a
-- decision to that registration rather than restating it. It must NOT be repointed with the
-- rule publication above.
--
-- Guarded on residency exactly as 077's rule insert is: migrations run before the seed, so on a
-- fresh database the conformance rule is not there yet and seed/jurisdictions.py supplies both.
-- On a database that is already seeded, this is what lands it.
insert into lineage.jurisdiction_rules
    (jurisdiction_code, effective_from, published_at, decision, rule_id, serving, note)
select 'CO', date '2026-09-02', date '2026-09-02',
       'blank_is_absent', 'cr_co_wells_shp_blank_is_absent_1', true, null::text
 where exists (select 1 from lineage.conformance_rules
                where rule_id = 'cr_co_wells_shp_blank_is_absent_1')
on conflict do nothing;
