- [Change] DR-87: nm_ocd's inline `_record_vintage` delegates to the shared
         `ingest.base.record_vintage_day`, deleting the duplicated accumulate/dedup/
         union/no-op-guard logic; a characterization test pins the exact same-day
         ledger rows byte-for-byte across the swap
- [Fix] DR-88: TX promotion guards consult manifest and staging identity instead of
      canonical row ownership, so a revised manifest whose rows all conflict is
      detected — its refused rows are quarantined as key_collision — rather than
      silently reported as promoted; tx_gis/tx_wellbore reports and the vintage
      ledger now carry rows actually appended, and a reload of already-processed
      bytes short-circuits as unchanged instead of re-promoting forever
