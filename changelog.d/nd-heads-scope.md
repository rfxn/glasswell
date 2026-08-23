- [Fix] DR-17: ND promotion no longer reads canonical.production_monthly whole. The head
      map behind change-only append, and the same-vintage map behind the divergence
      refusal, were both keyed by every row the table holds and both were rebuilt for
      each of the 125 back-load workbooks; each is now scoped to the entity-months being
      promoted, which is exactly the set the lookups ask about. Measured at 397,041
      resident heads: 394.3 MB against 102.4 MB, and flat rather than linear as further
      months land
- [New] tests/integration/test_nd_heads_scope.py pins the scope: the map holds only the
      month being promoted, does not grow as further months land, answers what a read of
      the whole table answered, and refuses a lookup it never covered rather than
      reporting that head as absent — which would append a restatement as a first
      observation
- [New] the UTC-midnight straddle is pinned at both tiers: months whose sessions open
      either side of midnight keep a lineage.vintages row per knowledge day, each
      carrying only the months that landed under it, and the driver summary reads both
      rows back rather than filing the walk under the day it started
