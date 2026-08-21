- [Fix] NM promotion derivations record the window the run actually applied. A run
      widened with `--window-start` stamped the rule's 2015-01 default on every month,
      so a derivation for production month 1973-07 claimed a 2015-01 promotion window
      and falsified `cr_nm_wcproduction_window_1`'s served rationale verbatim
- [Fix] `lineage.vintages` counts the vintage-day rather than the last run on it.
      Canonical accumulates across same-day runs while `open_vintage` upserts on
      (source_id, vintage_date), so a DIR-12 widening performed on the day of the first
      promotion recorded 271 rows appended against the 300 that had landed
- [Fix] A refused promotion records the vintage for what the months before it committed.
      Months commit one at a time, so a run that exits 2 on a later month can leave an
      earlier month's rows appended; `rows_appended` no longer understates canonical at
      that vintage
- [Fix] The promotion's suppressed-unchanged count is measured against the canonical
      head instead of derived as kept-minus-promoted, which cancelled `promoted` out of
      SB-01 §5.1's reconciliation identity and left a promoted/suppressed mis-split
      unfalsifiable by construction
- [Fix] A filing withheld as `key_collision` or `duplicate_row` carries the cells its
      rule declares it decided on — `ogrid_cde`, `amend_ind`, `prod_amt`,
      `prodn_day_num` — so the deferred operator-effectivity resolution reads the
      quarantine ledger rather than re-staging after SB-01 §3.2's 30-day truncation
- [Fix] `cr_nm_wcproduction_collision_1` names the base each measurement was taken on:
      the 12,351 pairs with both rows producing are 12,351 of the 19,465 that disagree
      on the amount, not of the 22,591 that disagree on the amount or the day count
- [Fix] `RowCountMismatch` is exercised at both raise sites, so the staging and
      promotion reconciliation guards are shown to fire rather than asserted to exist
