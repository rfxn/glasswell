- [Fix] `/v1/jurisdictions` serves the wells whose regulator filed no status as their own
      class, `unmapped`, instead of summing them into the jurisdiction total and dropping
      them from the rows served beside it: Texas served 359,421 against class rows summing
      291,235, so 68,186 wells were inside the total and inside no class
- [Fix] map: the legend keeps a status class the served census carries no measurement for,
      with its label, its count and its filter switch, and hides only a class measured at
      zero everywhere; over Texas the absence class was populated and hidden, so 56,423
      wells in view at 1600 were painted in a colour the key did not name and could not be
      switched off. The hide is the render's rather than a one-shot pass, and a class the
      census does not carry is marked unmeasured rather than read as a measured zero
- [Fix] map: the `Wells` family rows state the well count `/v1/jurisdictions` served, with
      the handle that resolves it, in place of the compiled literals three of the four rows
      carried — Texas 355,463, New Mexico 141,778 and Montana 42,026 against a registry
      serving 359,421, 142,000 and 40,626 — and state no number at all until one arrives
- [Change] The count writer measures every class the registered status vocabularies name, for
           every registered jurisdiction, so a class no well carries is a measured zero rather
           than an absent row; the vocabulary is read off the `vocab_map` rules themselves, and
           the legend hides a class measured at zero everywhere while listing an unmeasured one
- [New] `python -m glasswell.marts.counts --dsn ...` appends a jurisdiction well-count
      measurement, the command the add-a-state runbook has named since step 11 and the
      module never carried; `--codes ND,TX` narrows it and refuses a code no registration
      carries by name. It takes no `--measured-on`: the ledger's date is the day the
      measurement was taken
