- [Fix] The health contract was seven days from reddening on a calendar date rather than a
      code change: `tests/support/seed.py` pinned the artifact clock at 2026-08-01, and
      migration 050's 35-day cadence turns an artifact older than its interval `stale`
      when no durable attempt proves a check. The vintage stays pinned, because served
      figures assert on it; the freshness clock is now relative to the run
- [New] A ratchet asserting the seeded artifact is younger than the shortest cadence the
      migrations declare, so the same fixture cannot age out again unnoticed
- [Change] Gate G9's tree invariant — A1b's block is 020-024, versions contiguous from 1 —
         is its own test and never skips; the status-file lookup is separate and resolves
         the artifact across both of its known homes. The gate had skipped itself since
         the wave-1 archive move, in the exact environment its stated reason claimed it
         should run in, while two status files recorded it as PASS
- [Fix] Two contract ratchets could pass over a feature that no longer existed, and now
      count what they measure
- [Remove] `lateral_ordinals` in the ND GIS fixture cutter ignored the reader it was
         handed and returned the same `range(RECORD_COUNT)` its sibling call site inlines,
         under a docstring describing two records rather than three hundred
