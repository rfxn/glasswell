- [New] The PDQ member layout is a conformance row: cr_tx_pdq_format_2 restates
      cr_tx_pdq_format_1 with the measured header of every member the Texas load
      reads and the subset each parse consumes, published by 081_tx_pdq_format.sql
- [Fix] The completion member is read at its measured 16 columns; the 13 the
      parser carried were transcribed from the manual and never measured, and the
      stage refused on the width
- [Change] A member's header is judged by name and position against the rule and
         refuses naming the columns and the rule id, so a renamed or reordered
         column is as loud as an added one; all five members read are judged,
         where three were read against no layout at all
- [Fix] A completed fetch is recorded when its bytes are placed rather than at the
      end of the run, so a refused parse leaves a manifest and the re-run reuses
      the slot instead of placing a second copy of the archive
- [Fix] An undeclared raw zone refuses with RawRootUnset; the default was the
      relative data/raw, which resolved against the caller's working directory
- [Fix] The two-clock gate for the Texas card reads the grain rule's own published
      vintage instead of a date the v0.80 repoint had already moved
