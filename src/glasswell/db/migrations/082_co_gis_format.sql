-- Which member of each ECMC GIS archive a layer is read from was a code constant and nothing
-- else, and for two of the three archives it was wrong: ingest/co_ecmc_gis.py looked for a stem
-- ending in `directionalbottomholelocations` while ECMC ships
-- `Directional_Bottomhole_Locations`, and the separators defeated the match. The staging refused
-- on 2026-09-04 at 20:06:30Z after the wells layer had already been staged and recorded.
--
-- R8 makes that a row rather than a constant: cr_co_wells_shp_member_1,
-- cr_co_directional_bh_member_1 and cr_co_directional_lines_member_1 carry the member each
-- archive actually ships, and this migration is the publication evidence 049's trigger requires
-- before the seeder may insert them. The rule bodies live in glasswell.seed.conformance_co.
--
-- No rule is superseded: nothing described the archive layout before, so these three are
-- founding rows rather than restatements.
--
-- REPOINT CHECKLIST (integrator, at the merge train):
--   1. evidence_tag UNRELEASED -> the tag that first carries these three rule ids. It appears
--      ONCE, at the insert below.
--   2. evidence_commit forty zeros -> the first commit on main that contains them, which is the
--      merge commit and not the head this branch was written against.
--   3. published_vintage 2026-09-04 -> the date the tag is cut, and never a date the deploy host
--      has not reached: load_rules filters on published_vintage <= today, so a vintage ahead of
--      the host leaves the three rows unresolvable while the loader that cites them runs.

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-09-04', 'UNRELEASED',
       '0000000000000000000000000000000000000000'
  from unnest(array[
       'cr_co_wells_shp_member_1',
       'cr_co_directional_bh_member_1',
       'cr_co_directional_lines_member_1'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;
