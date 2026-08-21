- [New] changelog.d/ per-branch changelog fragments with scripts/changelog-assemble.py and
      `make changelog TITLE=...`: tracks stop editing CHANGELOG.md (60 of the prior 200
      commits touched it) and the integrator folds fragments under a dated heading at the
      merge train; `--check` fails while fragments pend so a release cannot strand them
- [New] tests/e2e/lib.mjs: the browser-gate machinery every DIR-11 pass re-derived in
      work-output — chromium discovery, instrumented page journal, the 1600/1366/1024/820/390
      breakpoint ladder, WCAG contrast sampling, frame probe — committed and import-safe;
      smoke.mjs now shares its chromium discovery instead of carrying a copy
- [New] tests/support/serve_branch.py and `make serve-branch`: ephemeral PostGIS +
      migrations + contract-tier seeds + uvicorn for any branch (GW_ROOT points at a
      worktree, GW_SEED extends the seeds), replacing the per-track serve scripts;
      verified live — health 200, keyed wells payload, fail-closed 403, labeled teardown
