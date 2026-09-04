- [New] The weekly restore drill refuses before it creates a scratch database it has no room
      for: the scratch cluster's filesystem must hold `pg_database_size(glasswell)` plus
      10 GiB, the scratch database is still removed on the way out, and the receipt the status
      page reads distinguishes a measured shortfall from a probe that could not measure
- [Change] The storage check that gates a deploy follows PGDATA rather than `/`, is named
           `PostgreSQL storage` for what it now measures, and refuses below an absolute floor
           as well as below the 10 % ratio, both configured on the status unit: a tenth of this
           filesystem is less than the room the next state load needs, so the check stayed
           green on a disk already too small
- [Change] `wal_compression = lz4` joins the PostgreSQL tuning drop-in, against 43 million
           full-page images written in fifteen days; it reloads rather than restarting, and
           `infra/README.md` now says how a changed drop-in reaches the host, because a deploy
           neither applies one nor reverts one
