- [New] The weekly restore drill refuses before it creates a scratch database it has no room
      for: the scratch cluster's filesystem must hold `pg_database_size(glasswell)` plus
      10 GiB, and a drill that refuses says `insufficient_free_space` on the same receipt the
      status page reads, with its scratch database still removed
- [Change] The `System storage` check follows PGDATA rather than `/` and carries an absolute
           floor beside the 10 % ratio, both configured on the status unit: on the disk this
           runs on, a tenth of the filesystem is less than the room the next state load needs,
           so the one check that gates a deploy stayed green on a disk already too small
- [Change] `wal_compression = lz4` joins the PostgreSQL tuning drop-in, against 43 million
           full-page images written in fifteen days; it reloads rather than restarting, and
           `infra/README.md` now says how a changed drop-in reaches the host, because a deploy
           neither applies one nor reverts one
