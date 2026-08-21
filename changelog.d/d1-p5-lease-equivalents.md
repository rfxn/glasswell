- [New] `canonical.well_completions` carries OGRID, pool, POD, spacing unit and property
      for every New Mexico completion: 763,473 effective-dated observations over 147,975
      completions and 121,940 wells, promoted from `wchistory` under the crosswalk
      `podwc` states, append-only and never updated
- [New] `cr_nm_wcproduction_lease_equivalent_1` records D3's Validator B grouping key as a
      rule row rather than a note. SB-01 8.6 groups NM synthetic leases on spatial
      contiguity and NM OCD's FTP ships no coordinates, so POD, spacing unit and property
      — legal areal units, which is what a TX lease actually is — stand in. The substitute
      is closer on the legal-analogue axis and strictly worse on transferability: it
      removes the resampling knob, so the rule specifies post-hoc group-selection
      reweighting and requires the residual mismatch to be published rather than claimed
      away
- [New] The wells-per-group distribution every candidate key produces, measured on the
      promoted rows: POD 141,479 groups over 83,814 completions, mean 1.445, 89.5%
      singletons; spacing unit 49,994 groups over 81,100, mean 1.622; property 52,406
      groups over all 147,975, mean 2.824. Property is the only key with full coverage and
      every key's median group holds one well, which is the ceiling on what reweighting
      can reach
- [New] `cr_nm_wchistory_wellbore_policy_1` records SB-01 4.3's multi-wellbore share as
      vacuous rather than as 0%. No in-scope NM artifact carries a column past the
      api_st/api_cnty/api_well triple, so NM cannot express a sidetrack; `well_nbr_idn` is
      the operator's well number, 4,854 values over 121,940 wells, not a wellbore suffix
- [New] OGRID loads `lineage.operator_aliases` as an exact key at confidence 1.000 —
      31,696 rows, no fuzzy pass, no normalised-name fallback — and an unmatched code is
      quarantined as `alias_unresolved` with its payload rather than joined to the nearest
      name
- [New] `spc_unit_idn` '0' is the regulator's absent marker on 119,662 of 426,529 records
      and lands null; a completion that reaches none of POD, spacing unit or property is
      quarantined as `orphan_fk`, counted, never dropped
- [Change] Migration 029 gives `canonical.well_completions` a second grain. An
         effective-dated dimension observation has no production month, so
         `production_month` is nullable, the two grains are two partial unique indexes and
         a CHECK requires one of them; ND's completion-month rows and their conflict
         behaviour are untouched
- [Fix] The ND well card still index-scans with canonical 122 times larger: the served
      query filters `api10` inside the vintage window, measured at 0.9 ms against
      17,597,960 rows on VM 111. `canonical.production_monthly_latest` cannot — `api10` is
      not in its PARTITION BY — and re-ranks the whole table for one well, 2.7 s before NM
      and 73-156 s after. It is not the serving path; the finding is recorded rather than
      silently carried
