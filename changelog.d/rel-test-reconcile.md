- [Fix] the deploy refusal tests catch up to the v0.31 contract: the fixture tree
      carries numbered migrations so the tree-shape refusal no longer masks the
      cases, a stub host answers the schema_migrations head query so gap, no-gap
      and garbage answers are posed for real, and the retired "migrations skipped"
      silence is replaced by asserting the refusal that names both heads; new
      coverage for --skip-migrations issuing zero head queries and for the two
      migration flags together exiting 2
