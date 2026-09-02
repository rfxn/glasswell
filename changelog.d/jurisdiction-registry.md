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
- [Change] `/v1/wells`, `/v1/wells/{api10}`, `/v1/wells/status-summary`, `/v1/wells/facets`
           and both production routes read the jurisdiction registry instead of the nine
           per-state maps they carried between them. `STATUS_VOCABULARY_RULES`,
           `PROVENANCE_RULES`, `DEFAULT_PROVENANCE_RULE`, `LENGTH_SCOPE_RULES` and
           `NEIGHBOR_STATE_CODES` in `wells.py`, `LIQUIDS_RULES`, `LIQUIDS_BASIS` and
           `ROLLUP_RULES` in `production.py`, and `STATE_NAMES` and `ABSENCE_RULES` in
           `facets.py` are deleted; the three modules now carry no two-digit state literal at
           all except the one `/v1/wells/facets` needs in its own request example. A fifth
           jurisdiction is a row in `lineage.jurisdictions`, not an edit to three routers
- [Change] Texas no longer cites `cr_nd_geometry_provenance_1`. It inherited a rule about
           *North Dakota* geometry through a module-level default; it registers no
           geometry-provenance decision, so the surface serves none and says so. Authoring a
           real Texas rule is separate R8 work
- [New] `absence:operator` is a registered decision at (jurisdiction, dimension) grain, so the
      second dimension whose absence gets a rule is a row rather than another key in a
      tuple-keyed map; an unregistered dimension still counts its bucket and claims nothing
      further about it
- [New] `GET /v1/jurisdictions` serves the registry: for each jurisdiction the regulator and
      the address it publishes at, the identity scheme and prefix its wells are keyed by, every
      conformance rule registered for it with which one serves, the liquids basis, the tile
      layer and colour it is drawn with, what is built for it, and the wells last measured in
      it. `as_of` is the registry's own knowledge cut, so a correction published after it is
      not served under it and a cut before the first registration is refused rather than
      answered with an empty page. Not `/v1/states`: `state` is already a lifecycle value and
      a frozen query parameter meaning the API prefix, and a province is not a state
- [New] Every well count on that route is a figure with a handle that resolves through
      `?explain=true` to the government file the wells were promoted from, and a jurisdiction
      with no measurement yet serves no count at all rather than a zero — "not measured" and
      "no wells" are different facts. `Jurisdiction`, `Regulator` and `Identity scheme` are
      glossary terms, and the identity prefix is the one number on the route exempted from
      carrying a handle, because it is an identifier's prefix and says so in both places
- [Change] The Status page's jurisdiction arms are generated from the registry. Sixteen
           literals decided the wells arms and ten more the completions arms, and the
           completions query still carried the `left(api10, 2) = '<literal>'` filtered
           aggregate migration 069 took out of the production arm; all of it is one grouped
           read and one comprehension now. A fifth registration yields a fifth wells dataset
           and a fifth completions dataset with no edit, and an arm whose table holds nothing
           reports `unavailable` rather than a zero — "not loaded" and "none" are different
           facts, which is the guarantee the omitted Montana completions arm used to make by
           being absent
- [New] `marts/counts.py` appends the jurisdiction well-count ledger `/v1/jurisdictions`
      serves: one measurement per registered jurisdiction, by canonical status and in total,
      under the derivation that produced it. The total is the sum of the classes it is served
      beside rather than a second `count(*)`, and the class is read from the same resolver the
      map draws with, so the ledger cannot disagree with the canvas about a well
- [Change] `land_metrics.py`'s two grid-prefix tuples and `neighbors.py`'s `STATE_CODES` read
           the registry at import. The two land-grid names stay separately named and separately
           sourced — each reads its own column — because collapsing them would silence the
           anomaly alarm one of them exists to raise
- [Change] map: the `Wells` family, its four jurisdiction rows and the status vocabulary rules
           the legend prints take their names, swatch colours, tile layers and rule ids from
           `jurisdictions.generated.ts`, rendered from the registry seed by
           `make jurisdictions`. The rows stay literal — `tests/e2e/chrome-fold.mjs` parses the
           file as text — and only the values inside them are imported
- [Remove] map: `MEASURED_WELL_COUNTS`, `MEASURED_TX_WELL_COUNTS`, `MEASURED_NM_WELL_COUNTS`,
           `MEASURED_MT_WELL_COUNTS` and `measuredWellCount`. Four count tables read by hand
           against the deployed database and compiled into the bundle with no date on them; a
           legend built from those claimed whatever somebody last measured. The census comes
           from `/v1/jurisdictions` now, fetched off the entry path, and a class is hidden only
           on an explicit measured zero — an unknown or degraded census hides nothing
- [New] `tests/unit/test_add_a_state.py` refuses a two-digit API prefix or a jurisdiction's
      name anywhere the serving path reads: `marts/`, `api/routers/`, `status/`, `lineage/`,
      every migration written after the registry, and `web/src` with comments stripped. The
      rule is positive and keyword-free, which is the point — an earlier form gated on a
      trigger word and seventeen of the nineteen literals it existed to catch sat in dict
      bodies with no such word on the line. Six exemptions, each with its reason in the file
      and each proved load-bearing by a test that removes it and expects the scan to speak
- [New] `docs/runbook-add-a-state.md`: eleven steps from registering the source to running the
      count writer, each naming the refusal that stops it being done out of order — and naming
      the one step, the ingest timer, that still has no gate behind it
- [New] `lineage.jurisdictions.explorer_default` decides which jurisdiction the Explorer opens
      on. It was a code choice — first a literal `"33"`, then whichever registration sorted
      first, which is Montana and an accident of alphabetisation. Exactly one registration
      carries the flag and its rationale says why: the only jurisdiction serving well-grain
      production history end to end. A partial unique index holds it to one per registration
      instant and a standing gate holds it to exactly one across the resolved set, because two
      registrations a day apart both resolve and no index can see that
- [Change] Which jurisdictions resolve their well status at read time, and under which rule,
           is read off `lineage.jurisdiction_rules` rather than pinned in a dict. New Mexico
           was `{"30": "cr_nm_wellhistory_status_vocab_2"}` in `status_resolution.py`, a module
           at the package root that no scan looked at; the add-a-state gate now scans there
           too. `canonical.status_resolution` stays one canonical-layer view the tile mart and
           every serving path read, and takes its API prefix from the registration instead of a
           literal — a fifth state with read-time resolution still brings its own codebook, but
           whether it resolves that way is a row
