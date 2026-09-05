- [Fix] Caddy redacts the credential-shaped headers the API refuses as well as the one
      it accepts: Authorization, Proxy-Authorization and X-Api-Key join X-Glasswell-Key,
      Cookie and X-Glasswell-CSRF in both listeners' access-log filters. The log line is
      written before the refusal, so a key guessed into a header the API never reads was
      logged in full — which is how one reached tunnel.log and forced a rotation
- [Change] verify.sh asserts snapshot freshness and check health separately, and the
           health failure names the check and job ids it failed on; as one assertion it
           reported an unavailable check as "marked the freshly collected snapshot stale",
           which was a false statement about the host on every train that ships an
           empty-mart disclosure as a check
- [Change] The Texas load runbook states which verify assertion is expected red before the
           load and green after it, and the exactly three check ids it may name; "verify
           green, then the load" was circular for a train whose reds are the disclosures
           the load clears
- [New] A shipped em dash in any literal under web/src is red, gated on the corpus the
      tofu sweep already reads; the class was swept by grep twice and reopened both times
- [Change] The five em-dash literals still on the wire are reworded: a refusal pointer
           joins its detail with a colon, and the absent-value mark reads `--` on the
           vintage slot, the figure tree, the grid's absent cell and the map hover card
- [Fix] PERF.md §3's budget table quoted a map-chunk measurement three trains stale, so
      the headroom it stated as +5.2% was really +1.3%; all three rows are re-measured at
      a stated head by a stated method, and a budget quoting a figure more than 3% from
      what the build measures is now red
- [Fix] The layer panel's provenance row renders the lineage mark through the module that
      owns it rather than spelling the codepoint a second time
