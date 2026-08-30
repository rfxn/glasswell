-- The pinned tcv1.0 control becomes a served surface. Three api.respond output datasets admit
-- the request-computed handles the type-curve and modeling-publication routes mint; without a
-- registered profile the figure still serves but /v1/explain answers 422, which is a naked
-- number wearing a handle.
--
-- Migration 049 made publication evidence a precondition for every conformance rule, so the
-- five cr_tc_* serving decisions register theirs before the seeder inserts them.
--
-- The evidence below is a PLACEHOLDER and the integrator repoints it at the merge train. A
-- branch cannot know which tag it will ship in — merge order decides that, and this horizon
-- has reordered twice — so guessing a number writes a false claim about when glasswell could
-- know these rules. `lineage.conformance_rule_publications` is append-only and this migration
-- is sha256-pinned once applied, so the repoint must happen BEFORE the production migrate;
-- afterwards the only remedy is a restore.
--
-- Repoint all THREE fields on the insert below, not two:
--   evidence_tag       the UNRELEASED literal -> the tag this actually ships in
--   evidence_commit    the 40-zero literal    -> the `main` head it was written against
--   published_vintage  the date               -> the DATE THAT TAG IS CUT
-- The third is easy to miss and is not independent of the other two: 049's own column comment
-- defines published_vintage as "first repository-tag publication of this immutable rule
-- version", so it is the release date, not the authoring date. It is right today only because
-- the train is expected to ship today; a train that slips past midnight publishes a
-- permanently wrong knowledge date, and append-only means permanently.
--
-- `scripts/release.py::placeholder_evidence_blockers` refuses to cut a release while either
-- quoted literal is still here, so the tag and the commit cannot ship by omission. It reads
-- the quoted SQL literals and not these words, so this comment is prose and not evidence.
-- The date has no such guard: it is a real date either way, and only a reader can tell whether
-- it is the right one.

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
select rule_id, date '2026-08-30', 'v0.68',
       '36687869788419669e665864762017fc17bc3eb7'
  from unnest(array[
       'cr_tc_normalization_1', 'cr_tc_peer_ladder_1', 'cr_tc_publication_scope_1',
       'cr_tc_quantile_convention_1', 'cr_tc_unavailable_vocab_1'
  ]::text[]) rule_id
on conflict (rule_id) do nothing;
