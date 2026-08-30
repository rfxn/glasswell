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
-- Migration 049 makes publication evidence a precondition for the insert. v0.68 is the first
-- tag to contain the id; the commit is the `main` head the branch was written against.
insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
values ('cr_land_agg_membership_2', date '2026-08-30', 'v0.68',
        'c8cffbc344e1ea36e454e43f3c0a4d7696aa1c0a')
on conflict (rule_id) do nothing;
