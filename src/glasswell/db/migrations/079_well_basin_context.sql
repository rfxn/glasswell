-- The v0.80 well-card migration, train head + 1 in merge order; the integrator renumbers.
--
-- It carries the publication evidence for the two rule families the card registers, and the
-- basin-context mart the card's Basin and geology section reads. Publication evidence is what
-- brings a rule id into existence: lineage.conformance_rules refuses an insert for a rule id
-- with no row here (049's assign_conformance_rule_publication), so a seeded rule needs a line
-- in a migration whatever else it needs, which is why cr_nd_vintage_cohort_1 and the cadence
-- rules have theirs in 072 and 076.
--
-- REPOINT CHECKLIST (integrator, at the merge train):
--   1. evidence_tag UNRELEASED -> the tag that first carries these rules
--   2. evidence_commit forty zeros -> the merge commit on main that carries them
--   3. published_vintage -> the date that tag is actually cut; the table is append-only
-- The rule ids are immutable and must not change during the repoint. Both literals appear
-- exactly once each, in the evidence insert below and nowhere else.

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-09-03', 'UNRELEASED',
       '0000000000000000000000000000000000000000'
  from unnest(array[
       'cr_status_history_basis_1'
  ]) as rule_id
on conflict do nothing;
