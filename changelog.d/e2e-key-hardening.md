- [Change] e2e: the owner key travels header-only — lib.mjs is the single auth path,
         reading GLASSWELL_KEY_FILE or GLASSWELL_OWNER_KEY and injecting X-Glasswell-Key
         on every same-origin request; smoke.mjs and perf.mjs drop the #key= fragment
- [New] e2e: centralized key redaction and leak guards in lib.mjs — it refuses to run
      with the key in process.argv or a navigation url; lib.test.mjs proves redaction
      and both refusals under node --test
