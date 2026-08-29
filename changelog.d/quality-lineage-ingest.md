- [New] TX wellbore: a depth or completion date the parser cannot read is quarantined
      per field as `unreliable_numeric` or `out_of_range_date`, carrying `filed_as`,
      `field_action` and the row's ordinal, so a filing the reader failed on is no
      longer indistinguishable from one the regulator never made
- [Change] `WellboreLoad.quarantined` counts the two new reason codes rather than
         reporting zeroes for a class the loader never produced
- [Fix] a blank TX measure stays an absence and is not quarantined, and the well still
      promotes with the field null rather than being dropped
- [Fix] the service index publishes its promotion row counts with the derivation handle
      `/v1/vintages` already gives them, retiring two allowlist exemptions written
      around the gap rather than around a ruling
- [Fix] `register_manifest` refuses the same bytes under a second (source_id,
      source_key) instead of returning the incumbent's manifest, so a slot can no
      longer inherit another slot's provenance and resolve `/explain` to the wrong
      government file; `ManifestConflict` is raised rather than dead
- [Fix] an ArcGIS layer matching no features is refused as `EmptyWalk` rather than
      sealed as a zero-byte artifact whose hash every empty harvest shares
- [Change] raw-zone staging is scoped by source slot, not by content hash alone, and
         the reuse-or-place block is one helper shared by the HTTP and ArcGIS
         registrars, refusing before the payload is moved into place
- [Fix] the ND re-promotion and the NM production promotion record the derivation that
      promoted them on their vintage-day ledger row, and a run carrying none no longer
      overwrites the one the ledger already holds
- [Fix] a vintage row no derivation promoted withholds `rows_examined`, `rows_appended`
      and `restatement_summary` as null on `/v1` and `/v1/vintages` rather than serving
      counts no handle can explain; a promoted row is unaffected
