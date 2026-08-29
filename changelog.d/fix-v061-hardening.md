- [Fix] The knowledge clock is read in UTC everywhere rather than from the host, so a machine
      west of UTC no longer spends its evening unable to see rules PostgreSQL published today;
      every registry lookup returned empty in that window and callers quarantined rows they
      should have resolved, recording the run as normal
- [Fix] The map legend's producing counts are wired to the response that carries them; the
      section was built, tested and never called, so it could not render at all
- [Fix] `rate_limited` is served as a code this slice emits, which it does — `/v1` and
      `/v1/errors/{code}` published `emitted_by_this_slice: false` for a code the wells router
      raises
- [Fix] assets/lineage.svg names the served `/v1/explain`, `/v1/conformance` and
      `/v1/quarantine`, replacing a `/quality` namespace that has never existed, and puts the
      unbuilt `/scorecard`, `/recipes` and `/audit` on the designed line under their blueprint
      names
- [Change] Architecture records the lineage-retention timer and the spacing-units tile view,
         security policy stops describing the project as pre-build 42 tags in, and status,
         roadmap and llms.txt carry the deployed v0.61 at schema head 52 with re-measured
         suite sizes
