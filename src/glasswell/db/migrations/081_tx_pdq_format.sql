-- The PDQ member layout stops existing only in code. cr_tx_pdq_format_1 named the members and
-- the refuse policy and carried no column list, so the header the parse was judged against was
-- a transcription from the manual that had never been measured -- and it was three columns
-- short of OG_WELL_COMPLETION_DATA_TABLE.dsv. cr_tx_pdq_format_2 restates it with every read
-- member's measured header and the subset the parse consumes; R8 wants the mapping decision as
-- a row, and this migration is the publication evidence that admits it.
--
-- 049's trigger refuses a conformance rule whose publication is not registered, so this lands
-- before the seeder that carries the row itself (glasswell.seed.conformance_tx). The rule row
-- is not mirrored here: 080 set that shape for this track and a second writer of an immutable
-- row is a second thing to repoint.
--
-- cr_tx_pdq_format_1 is not touched. It stays resolvable for every as_of before this train,
-- which is what makes the refusal it produced on 2026-09-04 still readable against the rule
-- that produced it.
--
-- REPOINT CHECKLIST (integrator, at the merge train):
--   1. evidence_tag UNRELEASED -> the tag that first carries this row. It appears ONCE, at the
--      insert below.
--   2. evidence_commit forty zeros -> the first commit on main that contains it, which is the
--      merge commit and not the head this branch was written against.
--   3. published_vintage 2026-09-04 -> the date the tag is cut, and never a date the deploy
--      host has not reached. load_rules filters on published_vintage <= today, so a vintage
--      ahead of the host leaves cr_tx_pdq_format_1 as the rule in force -- and _1 publishes no
--      member layout, so the Texas stage refuses naming it rather than parsing against a
--      layout nobody registered. That refusal is correct and is not the one this train is for.

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-09-05', 'v0.81',
       'a1d1392a8f1621bccd1d37fd77245447a50cc3d6'
  from unnest(array[
       'cr_tx_pdq_format_2'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;
