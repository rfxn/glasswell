- [Fix] New Mexico's production_grain decision named the rule it was superseded by on every
      host that migrated before it seeded: migration 087 repoints the registration to
      cr_nm_wcproduction_pool_rollup_2 as a new published instant, guarded on the successor
      being resident and on the restatement instant still naming the founding rule, and
      records the supersession 085 could not
- [Fix] seed_jurisdictions publishes the same correction where migration 087 could not,
      which is the host that migrates both files before it seeds: it appends New Mexico's
      registration at the correction instant with production_grain naming the successor,
      guarded on the successor's residency and on the resolved registration still naming
      the founding rule, and records the supersession on the audit trail
