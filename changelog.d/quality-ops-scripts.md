- [Fix] verify.sh: an empty tile roster and an unparseable martin catalogue are each
      their own named failure rather than compared to each other; both sides came from
      a command whose stderr is suppressed, so a venv that cannot import the marts and
      a martin that answered nothing read as ok while the per-layer loop ran zero times
- [Change] verify.sh: the deploy-hygiene sweep reads compgen output line by line rather
         than word-splitting it, so a stray path containing a space stays one path
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
- [Change] every 2>/dev/null in workstation-hygiene.sh carries its justification on its
         own line; it was the repo's sole outlier on that rule
