- [Fix] API-10 normalisation is one registry-driven decision instead of three loaders
      disagreeing: FracFocus hardcoded the digit count, the slice, the state code and the
      state name that `cr_ff_api_identity` already seeded, so `/conformance` described a
      rule row that governed nothing
- [Fix] A dashed identity no longer keys under FracFocus and the ND MPR while
      quarantining under ND GIS surveys; no identity rule row said whether a published
      API literal may carry punctuation, so `33-053-03901-00-00` was an identity under
      one rule and `key_incomplete` under another. The survey and MPR keys meet at one
      checkable predicate — `/v1/wells/status-summary` reads `canonical.well_spatial`
      with no `geom_type` filter and classes it against `canonical.production_monthly`
      on `api10` — where the separator decided whether the well appeared from this
      source at all, not how its key was spelled
- [New] `cr_ff_api_identity_2`, `cr_nd_api_identity_2` and `cr_nd_survey_api_identity_2`
      supersede their ancestors and declare the separator set explicitly, evidenced from
      the FracFocus data dictionary's own `xx-xxx-xxxxx-00-00` template; they correct on
      knowledge time and keep the ancestor's valid time, so a replay at an older report
      vintage reads the corrected row rather than the one that never said; migration 054
      registers their publication
- [Change] Only the two declared separators are removed before an API-14 is read, where
         the FracFocus and ND MPR loaders previously deleted every non-digit character;
         `API 33053039010000` and `33053039010000 (amended)` keyed onto a real well and
         now quarantine under their declared reason code
- [Change] `glasswell.identity` reads the identity spec off the rule row and refuses a row
         that leaves it unstated, so an undeclared identity decision fails at the registry
         rather than being invented per loader
