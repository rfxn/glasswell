- [New] `lineage.jurisdictions`, `lineage.jurisdiction_rules` and
      `lineage.jurisdiction_well_counts` (migration `072_jurisdictions.sql`) record which
      regulators glasswell serves, on whose authority and under which conformance rules — R8's
      "a mapping that exists only in code fails review" applied to the four API-10 prefixes the
      serving path has been keyed on since migration 009. Registrations are append-only under
      two clocks, so superseding a decision is a later `effective_from` and correcting what was
      published about it is a later `published_at` at the same one;
      `lineage.jurisdictions_as_of(knowledge_as_of, valid_as_of)` resolves the pair. There is no
      current-state view: `as_of` is a knowledge-time cut, which a static view cannot honour
- [New] North Dakota, Texas, New Mexico and Montana register with their regulator, identity
      prefix and pattern, complete source list, liquids basis, wells tile layer, map colour and
      capability flags, and with one row per mapping decision — Montana carrying both its
      well-grain and its PRU lease-grain inventory rules, exactly one of them serving. The rows
      ship in the migration and in `glasswell.seed.jurisdictions`, which `seed_all` runs on
      every deploy, and `tests/contract/test_jurisdiction_parity.py` holds the two copies to
      each other and refuses a prefix that resolves to two jurisdictions, a registration missing
      the rule rows it declares, or a `source_ids` array that has stopped being complete
- [New] `load_jurisdictions` reads the registry at a knowledge and a valid instant and refuses
      an empty one with `JurisdictionRegistryError` instead of returning an empty map — R8's
      rule that a missing row is a refusal, never an assumed default
- [Change] `scripts/release.py` scans `src/glasswell/seed/jurisdictions.py` beside the
           migrations for placeholder publication evidence, in both quote styles, so a repoint
           that edits the migration and forgets its mirror is refused at `make release-check`
           rather than landing a permanent false claim about when the rows were published
