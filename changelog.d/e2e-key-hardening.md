- [Change] e2e: the owner key travels header-only — lib.mjs is the single auth path,
         reading GLASSWELL_KEY_FILE or GLASSWELL_OWNER_KEY and injecting X-Glasswell-Key
         on every same-origin request; smoke.mjs and perf.mjs drop the #key= fragment
- [New] e2e: centralized key redaction (case-insensitive) and leak guards in lib.mjs —
      it refuses to run with the key in process.argv or a navigation url, and journals
      any same-origin request that redirects off-origin; lib.test.mjs proves redaction,
      both refusals and the redirect detector under node --test
- [Change] make test-e2e and CI run the browserless e2e guard suite first
         (node --test tests/e2e), so the key-hygiene boundary is enforced even where
         the browser tier skips
