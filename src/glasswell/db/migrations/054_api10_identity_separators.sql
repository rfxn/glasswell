-- Migration 049 made publication evidence a precondition for every conformance rule, so the
-- three superseding API-10 identity rows register theirs before the seeder inserts them. v0.62
-- is the first tag to contain these rule ids; the commit is the `main` head they were written
-- against, because the commit that introduces a rule cannot cite its own hash.
insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-08-29', 'v0.62',
       '307d65d25dc85785c0d87ac9097ef59085ec819a'
  from unnest(array[
       'cr_ff_api_identity_2', 'cr_nd_api_identity_2', 'cr_nd_survey_api_identity_2'
  ]) as rule_id
    on conflict (rule_id) do nothing;
