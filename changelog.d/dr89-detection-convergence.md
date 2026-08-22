- [Fix] DR-89: nd_gis and blm_plss promotion guards consult manifest and staging
      identity instead of canonical row ownership — the class DR-88 closed for TX —
      so a revised extract whose rows all conflict is detected: its refused rows are
      quarantined as key_collision at stage join, reports and the vintage ledger
      carry rows actually appended from insert rowcounts across all four ND layers
      and both land grains, and a reload of already-processed bytes short-circuits
      as unchanged instead of re-promoting forever
