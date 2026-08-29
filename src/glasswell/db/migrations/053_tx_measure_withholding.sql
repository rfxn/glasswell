-- The TX withholding policy — which measured fields are withheld, what withholding does to the
-- row, and the reason code each field is filed under — lived only in tx_wellbore.py, so a
-- mapping decision existed in code with no row to cite and no rationale to read (R8). The rule
-- body is seeded from glasswell.seed.conformance_tx; migration 049 made publication evidence a
-- precondition for the insert, so it is registered here first. v0.62 is the first tag to contain
-- the rule id; the commit is the `main` head the branch was written against, because the commit
-- that introduces a rule cannot cite its own hash.
insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
values ('cr_tx_ewa_measures_1', date '2026-08-29', 'v0.62',
        '307d65d25dc85785c0d87ac9097ef59085ec819a')
    on conflict (rule_id) do nothing;
