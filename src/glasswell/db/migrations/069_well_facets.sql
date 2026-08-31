-- "Wells by ..." serves counted buckets over the well spine, so it asks the one question the
-- spine had no index for: dedup an effective-dated state partition in api10 order, then group
-- by a dimension. Measured on the deployed database at 487,681 resident rows, the top-15 TX
-- operator facet read 269,438 shared buffers in 459 ms -- a full pass of wells_pkey with the
-- state filter applied per row. The covering index below answers the same query index-only
-- with 0 heap fetches, 4,395 buffers and 285 ms; the INCLUDE list is exactly the five served
-- dimensions, so no facet has to visit the heap. 48 MB against a 101 MB table.
--
-- The leading (state_code, api10) is not interchangeable with wells_state_effective_idx from
-- 059: that one leads (state_code, effective_from desc) for the tile marts' `where state_code`
-- scan, and cannot supply the `order by api10` the dedup needs without a sort.

-- `derivation_id` is in the INCLUDE list and is not optional: every bucket count is a figure
-- and carries the derivation its wells were promoted under, so the aggregate selects it. Left
-- out, the planner still uses this index but as a plain Index Scan with a heap visit per row --
-- measured at 182,523 buffers against 4,401 for the index-only plan, on the same query.
create index if not exists wells_facet_dimensions_idx
    on canonical.wells (state_code, api10, effective_from desc, created_at desc)
    include (operator_name_reported, county_code_at_permit, status_canonical,
             well_type_reported, completion_date, derivation_id);

comment on index canonical.wells_facet_dimensions_idx is
    'Index-only support for /v1/wells/facets: dedup per state in api10 order, group by dimension.';

-- Every bucket count, the remainder, the absence bucket and the total are request-computed
-- figures, so they mint api.respond handles. Without a registered profile the figures still
-- serve and /v1/explain answers 422 -- a naked number wearing a handle.
insert into lineage.selector_output_registry
    (operation, output_dataset, selector_profile, rationale)
values
    ('api.respond', 'api.well_facets', 'response_output',
     'The request derivation records every bucket count, the truncation remainder, the named'
     ' absence bucket and the scoped total returned for one dimension of one state.');

-- cr_tx_operator_absence_1 states what a missing TX operator name means. Montana already
-- registers the equivalent (cr_mt_operator_absence_1); Texas carried the same absence with no
-- row to cite, which is the R8 failure the facet surface would have published 70,039 times.
-- The rule body is seeded from glasswell.seed.conformance_tx; 049 made publication evidence a
-- precondition for the insert, so it is registered here first.
--
-- The evidence below is a PLACEHOLDER and the integrator repoints it at the merge train. A
-- branch cannot know which tag it will ship in. Repoint all THREE fields, not two:
--   evidence_tag       the UNRELEASED literal -> the tag this actually ships in
--   evidence_commit    the 40-zero literal    -> the first commit on main containing the rule
--   published_vintage  the date               -> the DATE THAT TAG IS CUT
-- `scripts/release.py::placeholder_evidence_blockers` refuses to cut a release while either
-- quoted literal is still here; the date has no such guard and only a reader can check it.
insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
values ('cr_tx_operator_absence_1', date '2026-08-30', 'UNRELEASED',
        '0000000000000000000000000000000000000000')
    on conflict (rule_id) do nothing;
