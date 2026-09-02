- [Change] STATUS.md's Deployed table is re-measured read-only against VM 111 and the
      tree on 2026-09-02 · code version `v0.75+2189262`, schema head `072`, `main` at
      `2189262` level with `origin/main` and 56 version tags, agreeing at last with the
      release line above it; CI is green at `2189262` (PR #47) and `infra/verify.sh` and
      `scripts/smoke.sh` read 197 passed / 0 failed and 31 passed / 0 failed at the v0.75
      deploy rather than 194/194 and 26/26 at v0.72; the P3 entry gate carries the date
      its neighbours carry
- [New] STATUS.md gains a seventh open item: cumulative production is North Dakota only,
      `marts/cumulatives.py:64` pinning `STATE_API_PREFIXES = ("33",)` so 43,817 of
      585,864 wells carry a cumulative, routed to H2 (v0.77)
- [Fix] llms.txt records New Mexico as resident with its header, API-10 and production
      counts and Montana as resident on both production grains with tiles and well paths,
      and its deployment paragraph is re-derived against v0.75 at `2189262`, schema head
      072, 197 host checks and 31 smoke checks, in place of a v0.60 paragraph pinning
      schema 52 that named Montana nowhere
- [Change] ROADMAP.md stops contradicting itself on Colorado: the state-expansion section
         records that Colorado and Wyoming open the Rockies rather than extending the
         Williston, the deferral covers additional basins beyond the Rockies sequence
         named under Horizon H2, and H2 is re-themed so v0.77 is state #5 as a
         registration, v0.79 is status truth for N states and v0.80 carries an em-dash
         lint, a media arm below 520 px and DOM-count budgets; H3 sequences the
         `/v1/wells` spine rewrite ahead of P3 modeling; open question 14 is closed by
         `cr_nd_vintage_cohort_1`
- [New] blueprint.md carries four states and the registry: the `[as-built]` four-state
      paragraph and §3.0.1a are promoted verbatim from `blueprint-v0.6-draft.md` into the
      committed contract, the status line reads four states deployed and serving, and
      §2.3's deferral brings the Rockies sequence · Colorado, Utah and Wyoming · into
      scope under the registry with each state's reachability evidence and named risk
- [Change] blueprint-v0.6-draft.md is cut to v0.6-rc6 with the §0 row for the four-state,
         registry and session-login wave; §3.4.1 gains `lineage.jurisdiction_codes`,
         `jurisdictions`, `jurisdiction_rules` and `jurisdiction_well_counts` from
         migration `073_jurisdictions.sql` under their two clocks; §3.6.12 gains
         `GET /v1/jurisdictions`, the `/v1/users` administration set and `GET` and
         `DELETE /v1/sessions`; and C26 is amended to the four-table scheduler v0.77
         builds, retiring the single `jobs` table that exists in no migration
- [New] blueprints/SB-04-api-agent-gateway.md §3.6 lists the six registry and account
      routes with their auth class, keyed for jurisdictions and owner-only for every user
      and session operation
- [Fix] ARCHITECTURE.md's wellbore-policy citation resolves to `blueprint.md` §3.0.5 and
      §3.0.1a rather than to the draft, with the per-basin revisit trigger attributed to
      `blueprint-v0.6-draft.md` as a `[D]` item pending the §11 review
- [Fix] .gitattributes names SB-01..08, since SB-08 exists and specs against the draft
