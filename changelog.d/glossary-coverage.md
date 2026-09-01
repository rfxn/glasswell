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
- [Fix] map: every drawn layer row resolves its own build handle off the tile that drew
      it; `land-grid`, `spacing-units`, `survey-traces`, the Montana rows, `basins` and
      `plays` all showed an unresolved ⌾, and each wells row was given the first handle
      on the whole canvas rather than its own state's
- [Fix] status: a state pill's wording survives the highlighter. The pill is inline-flex,
      so splitting "Current snapshot" around a term dropped the space between the halves
- [Fix] glossary: a term is no longer underlined inside a dotted identifier such as
      `marts.nm_wells_tile`; one ending a sentence is untouched
- [Fix] ARCHITECTURE.md: the wellbore-quarantine revisit trigger reads per basin, 2% in
      North Dakota and 5% in the Permian, and the detection clause names what each
      regulator publishes rather than the W-2 count that measures completions, not bores
