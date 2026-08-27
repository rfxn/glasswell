- [New] A third URL-backed Status surface joins live API and PostgreSQL signals to
      bounded infrastructure checks, scheduled work, exact-grain dataset inventory,
      platform identity, and registered-artifact age for every source
- [New] `GET /v1/status` reads a sanitized atomic snapshot produced by a mandatory
      hardened 15-minute systemd timer; deployment refreshes it before verification
- [Change] Source freshness is named as registered-artifact age rather than last-checked
         time, with unchanged fetches, source cadence, remote-copy evidence, and restore
         execution kept visible as observability limits instead of inferred success
- [Fix] Stale or invalid snapshots cannot preserve green infrastructure or job states,
      and the three-surface header keeps accessible touch targets at phone width
- [Fix] Migration 044 grants only migration-ledger reads to the API runtime role so the
      unprivileged scheduled collector can report the applied schema version
- [Fix] Stale sources and degraded checks now fail closed, jurisdiction-specific cards cannot
      mask older constituent data, and each inventory run uses one coherent read-only snapshot
