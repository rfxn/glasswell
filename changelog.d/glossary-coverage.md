- [New] map, status: the map key, the layers panel and the Status page underline the
      glossary's words and answer a hover with the definition — the three densest pages
      of vocabulary in the product, and the only surfaces `gw-term` had never been wired
      into. Controls carry `data-no-glossary`, because a term inside a button swallows
      the click that was the control's and hover already teaches
- [New] glossary: nineteen seed rows the product surfaced but could not define — Basemap,
      Cadence, Declared vintage, Disposal well, Geometry provenance, Lateral, Lineage,
      Play, Producing class, Retrieval vintage, Schema head, Section (PLSS), Station
      survey, Status snapshot, Timer, Township, Viewport, Vocabulary rule and Well type
      — each citing the blueprint section, conformance rule or mart that decides it;
      "Producing" and "section" are reachable by click and never auto-scanned
- [New] glossary: a coverage gate that renders all three surfaces against the committed
      seed and fails on a term a surface names but cannot define, plus its API-side half,
      which resolves every `gt_*` id the frontend binds by hand
- [New] glossary: a parity gate over the table's two writers. The seeder upserts, so for a
      term the seed carries its text is what survives the next run and a migration writing
      the same term is either identical to it or silently dead; the gate reads every
      glossary write in the migrations, reddens on a disagreement, and reddens again on a
      write shape it cannot decode
- [Fix] map: every drawn layer row resolves its own build handle off the tile that drew
      it; `land-grid`, `spacing-units`, `survey-traces`, the Montana rows, `basins` and
      `plays` all showed an unresolved ⌾, and each wells row was given the first handle
      on the whole canvas rather than its own state's
- [Fix] status: a state pill's wording survives the highlighter. The pill is inline-flex,
      so splitting "Current snapshot" around a term dropped the space between the halves
- [Fix] glossary: a term is no longer underlined inside a dotted identifier such as
      `marts.nm_wells_tile`; one ending a sentence is untouched
- [Change] the glossary seeder upserts on the term id, so a corrected definition, an
           extended alias list, new evidence or a changed `highlightable` reaches the
           reader on the next seed run; it inserted with `on conflict do nothing` and left
           the correction sitting in the file. `effective_from` is not re-dated
- [Change] the em-dash leaves the copy the app speaks: twenty-one prose dashes in card,
           explore and map string literals become a colon, a sentence break or the house
           middot as each reads best, and two legend notes are reworded rather than
           repunctuated; no hyphen stands in for a dash. The seven that remain are the
           absent-value glyph, a data mark rather than punctuation
- [Fix] ARCHITECTURE.md: the wellbore-quarantine revisit trigger reads per basin, 2% in
      North Dakota and 5% in the Permian, and the detection clause names what each
      regulator publishes rather than the W-2 count that measures completions, not bores
