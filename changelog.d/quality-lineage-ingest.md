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
