-- The land grid's membership universe is every well with a surface point, in any state, and it
-- always was: 355,463 Texas surface points are in it today, all of them unassigned, and
-- cr_land_agg_membership_1 legislates exactly that in its own words. New Mexico's 141,778
-- points join them at the header promotion.
--
-- The scope is now stated beside the served figure as a third counter rather than applied to it
-- as a filter. Filtering the universe to the grid's own states would have collapsed a served
-- unassigned count from about 355,463 to about zero while describing a scope that has not
-- changed, and _1's contract_note already says a different membership is a superseding row
-- rather than a code change. cr_land_agg_membership_2 is that row; the membership it carries is
-- identical.
--
-- Migration 049 makes repository publication evidence a precondition for every conformance
-- rule insert, so the rows this phase seeds register theirs first.
-- Publication evidence is a placeholder until the merge train repoints it. The tag below reads
-- UNRELEASED and the commit is forty zeros — the repository's agreed placeholder literals — and
-- `make release-check` refuses while they stand. `published_vintage` is NOT placeholdered — it
-- has no placeholder form — but migration 049's column comment defines knowledge time as the
-- first-tag date, so it is coupled to the release too: **repoint checklist — confirm this date
-- is the day the train actually ships.** lineage.conformance_rule_publications is append-only,
-- so a date that slips past midnight is permanently wrong.
insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
values ('cr_land_agg_membership_2', date '2026-08-30', 'UNRELEASED',
        '0000000000000000000000000000000000000000')
on conflict (rule_id) do nothing;
