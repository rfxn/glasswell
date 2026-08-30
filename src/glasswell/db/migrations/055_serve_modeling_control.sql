-- The pinned tcv1.0 control becomes a served surface. Three api.respond output datasets admit
-- the request-computed handles the type-curve and modeling-publication routes mint; without a
-- registered profile the figure still serves but /v1/explain answers 422, which is a naked
-- number wearing a handle.
--
-- Migration 049 made publication evidence a precondition for every conformance rule, so the
-- five cr_tc_* serving decisions register theirs before the seeder inserts them. v0.65 is the
-- first tag to contain these rule ids; the commit is the `main` head they were written
-- against, because the commit that introduces a rule cannot cite its own hash.

insert into lineage.selector_output_registry
    (operation, output_dataset, selector_profile, rationale)
values
    ('api.respond', 'api.type_curve', 'response_output',
     'The request derivation records the quantile and support arrays it returned for one'
     ' control subject at one split.'),
    ('api.respond', 'api.type_curve_index', 'response_output',
     'The request derivation records the per-page peer-support arrays it returned for one'
     ' facet set of the control population.'),
    ('api.respond', 'api.modeling_publication', 'response_output',
     'The request derivation records the acceptance and support figures it returned from the'
     ' accepted publication receipt and its control coverage document.');

insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select rule_id, date '2026-08-30', 'v0.65',
       'c8cffbc344e1ea36e454e43f3c0a4d7696aa1c0a'
  from unnest(array[
       'cr_tc_normalization_1', 'cr_tc_peer_ladder_1', 'cr_tc_publication_scope_1',
       'cr_tc_quantile_convention_1', 'cr_tc_unavailable_vocab_1'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;
