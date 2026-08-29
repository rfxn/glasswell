- [Fix] verify.sh: an empty tile roster and an unparseable martin catalogue are each
      their own named failure rather than compared to each other; both sides came from
      a command whose stderr is suppressed, so a venv that cannot import the marts and
      a martin that answered nothing read as ok while the per-layer loop ran zero times
- [Change] verify.sh: the deploy-hygiene sweep reads compgen output line by line rather
         than word-splitting it, so a stray path containing a space stays one path
- [Fix] app.env.example pins the lockfile fingerprint requirements.lock actually has;
      the shipped value was fifteen releases stale, and install.sh copies it verbatim to
      /etc/glasswell/app.env, so a fresh host stamped every lineage node with a false
      environment and P3 publication refused outright on lockfile_stamp_mismatch
- [Fix] workstation-hygiene.sh: the orphan-volume probe suppresses stderr like every
      sibling docker call in the file, so a daemon warning is no longer counted as a
      volume; the container age is converted from docker's prose and compared against
      CONTAINER_MAX_HOURS, anchored on the age field, rather than against a baked-in
      regex that ignored the threshold and matched a container merely named "days"
- [Fix] scripts/experiments/lib.sh: gw_psql resolves the DSN and reads the status back
      before calling psql; gw_die's exit fired inside `$(gw_dsn)`, terminating only the
      substitution, so an experiment could print a VERDICT computed from whatever PG*
      pointed at
- [New] the lockfile fingerprint app.env.example pins is asserted against
      requirements.lock, so a dependency bump cannot leave every lineage node on a
      fresh host carrying a false environment stamp
- [New] the fingerprint test also binds the pin to the env var and the lockfile path the
      publication gate reads, and to install.sh seeding the example unchanged, so a
      rename cannot leave the digest assertion green and inert
- [Change] every 2>/dev/null in workstation-hygiene.sh carries its justification on its
         own line; it was the repo's sole outlier on that rule
- [New] deploy.sh step 7d polls martin's /catalog, the endpoint verify.sh reads, before
      the gate runs; martin loads its whole source catalogue from PostgreSQL at startup
      and answers /health before it is populated, so the per-layer assertions could fail
      a deploy that was fine
- [Change] both deploy.sh readiness loops count arithmetically instead of word-splitting
         `$(seq 1 30)`
