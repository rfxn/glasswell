# Changelog

All notable changes to glasswell. Newest first.

Blueprint versions and code versions are tracked separately: `blueprint.md` carries
its own version in its header, and its history is summarised in §3.1.

## Unreleased

### 2026-08-21 — explorer P-A + NM D1 conformance

(tracks append entries under this heading; consolidated at integration)

- [New] Fourteen promotion rule rows, each naming one `source_id` because `rule_id` is a
      primary key and `load_rules` reads one source per call.
      `cr_nm_wcproduction_api10_1` pads every API segment to its own width — 2, 3 and 5 —
      because concatenating them unpadded and padding the result builds `0030520178` where
      the well is `3000520178`. A segment wider than its pad is refused rather than
      truncated: the one six-character `api_well_idn` in 48,104,334 records would otherwise
      emit an eleven-character API-10, while SQL's `lpad` truncates it onto a real well
      carrying 487 rows of its own
- [New] `cr_nm_wcproduction_entity_key_1` keys the spine at well completion × pool, the
      grain the source reports at. 48.1M rows hold 106,717 well × pool entities against
      89,136 wells, so an API-10 key collapses 17,581 of them; the source carries no
      completion suffix, which supersedes SB-01 §6.3's API-14 example
- [New] `cr_nm_wcproduction_county_parity_1` prohibits parity filtering rather than
      enumerating even-coded counties. Cibola (30-006) and Los Alamos (30-028) are LIKELY
      and not VERIFIED, and a prohibition is correct under either truth: `wellhistory`
      carries one even county code on 23 wells, so a parity predicate would look right
      against the production spine and delete Cibola the month one of them produced
- [New] `lineage.nm_stream_map` carries all four `prd_knd_cde` codes, including the `C` no
      first promotion can see — condensate is 3,398 rows and every one of them falls in
      1986-1993, so a vocabulary measured on the window would quarantine them the day it
      widened. The map is keyed on the trimmed code, which is the whole of B5
- [New] The policies the promotion reads are rows as well: units by stream with the gas
      conditions folded in as a note, the liquids policy NM's own condensate stream forces,
      the null-semantics vocabulary migration 009's CHECK admits, `amend_ind`'s ten values
      staged and promoted to nothing, the C-115 status code staged with no canonical
      mapping because the OCD publishes no codebook for it, restatement as an append, and
      NM flaring as a Property-grain fact that is not derivable at the spine's grain
- [New] `cr_nm_ogrid_operator_1` resolves the operator on OGRID at confidence 1.0 — an
      exact key rather than a name match, because a fuzzy operator match is an unlabelled
      estimate in the identity layer (SB-01 §5.3)
- [New] `x-glasswell-dataset` (SB-08 A-1) on the five collections whose `data` is already the
      array — wells, quarantine, conformance rules, derivations and glossary. The explorer's
      catalogue is generated from the served document rather than from a list in the client, so
      a dataset that is not an operation cannot appear and an operation that stops existing takes
      its dataset with it. Each declaration names its row identity, its facets, its detail
      operation and an explicit five-to-seven-pointer `columns.default`; those defaults are the
      binding ratchet's denominator, so they are a reviewable list rather than an emergent
      property of the schema-order fallback
- [New] The A-1 lint in `tests/contract/test_dataset_extension.py`, run against the served
      document and then against a mutant per rule: ids unique and never one of the four reserved
      shell routes, group one of four, every `row_id`, `columns.default`, `columns.hidden` and
      `columns.sort` pointer resolving in the operation's own response schema, every facet a real
      query parameter, every hidden column carrying its reason, and `detail_operation` /
      `summary_operation` naming operations that exist. The pivot grammar — `series_pointer`,
      `row_projection{axis,columns,suffixes}`, `anchors[]` — is checked against the production
      schemas it will be declared on, including the two rules that complete it: projection
      pointers are relative to `series_pointer`, and the axis is exempt from suffix expansion
- [New] The R6 walker asserts every browsable dataset is an operation it already exercises, so a
      generated catalogue cannot outrun the naked-number gate
- [New] A second top-level surface at `?view=explore`: a mode switch in the header, three tabs
      (Datasets, plus Query and Learn stating the phase that lands them), a dataset catalogue
      generated from `/openapi.json`'s `x-glasswell-dataset` members, and a rail grouped
      wells / kitchen / vocabulary / service and ordered on `order` alone. The document is the
      catalogue: a dataset that stops being declared stops being listed, and a new endpoint
      appears the day its operation declares itself — with no UI release
- [New] The rail renders the honest-gap register beside what exists: twenty-one class B
      datasets, each naming the SB-04 §4 operation that would carry it and the phase where SB-08
      states one, plus the single class C entry (production across wells) naming amendment A-3
      and its status. No entry renders a link, a control or a count, and a test asserts every
      class B path is absent from the served document — the day one resolves, the entry has to
      move into the generated rail
- [New] `explore/router.ts` is the `?view=` grammar as a pure codec: `f.<param>` filters read by
      prefix and repeatable, `as_of` and `cursor` hoisted into the query rather than declared as
      facets, path anchors substituted into the path and the ones with no value named rather
      than issued as a request that 404s. The mode switch is a `pushState`, `as_of` survives the
      crossing in both directions, and a selected well crosses as `ds=wells&f.q=<api10>`
- [New] `explore/layout.css` declares named z-slots aliasing the global ladder —
      `--gw-z-explore-pane` onto `--gw-z-panel`, `--gw-z-explore-rail-pop` onto
      `--gw-z-rail-pop` — plus one local
      stacking context for the grid's sticky header. No second ladder, no numeric literal outside
      a declared `isolation: isolate` container, and the test fails if the global rungs are
      renumbered underneath the explorer
- [New] `explore/guardrails.test.ts` scans the explorer's own source in the web job that already
      exists: no `fetch(` outside the one declared exemption in `shell.ts`, no `XMLHttpRequest`,
      no absolute URL, and every operation named as a literal either served by the committed
      document or listed in the gap register as one that is not

### 2026-08-21 — increment-3 merge train

- [Fix] The `collateral` job's link check allows this product's own `gw:` scheme beside
      `http`, `https` and `mailto`. `blueprints/SB-05-map-ui.md` shows the form a live data
      link takes, and the check read the example as a missing local file — red on `main`
      since the document landed, and reported by two branches that each correctly declined
      to edit another lane's file
- [Fix] `test_nm_fetch_vintage.harness_dsn` takes the session password from the fixture
      rather than a `glasswell:glasswell` literal. D1 was cut before DIR-14 randomised it,
      so the two only met at the merge and an authentication failure read as an FTP defect
- [Fix] The Caddy basemap block's restated CSP carries the satellite imagery origin its
      API-side original gained in the same increment

### 2026-08-21 — the z<=7 overplot gate

- [New] The four well and lateral tile functions keep one feature per half CSS pixel at
      z<=7, ranked by `md5(api10)`. Below z8 the map draws more features than it has
      pixels for and the surplus reads as alpha overplot: on the ND measurement half the
      features carry 15% of the ink at z7 and 0.5% of it at z4, and the projected saving
      is z0-z7 session bytes 5.68 MB -> ~2.0 MB. The rank is deterministic and carries no
      tilt — `spud_year desc` and `lateral_length_ft desc` were measured and rejected
      because they visibly shift the status colour mix, which is a biased sample of
      something the reader reads as information (DIR-11 gate, conditions C1-C4)
- [Change] `TileLayer` carries the gate per layer. Spacing units publish no `api10` and so
         have no rank; a layer marked thinned without one is refused at SQL generation
         rather than installed. The gate is a rank inside the cell rather than a
         `distinct on` over it, because 547 of Texas's 355,463 wells and 144 of North
         Dakota's 43,817 sit at a coordinate another well already occupies: a set-collapse
         drops those at every zoom, and only inside the band is what was approved

### 2026-08-21 — Texas on the map: RRC GIS wells and wellbore identity

- [New] `glasswell.ingest.tx_gis` loads the RRC county well archives — surface points,
      bottom-hole points and well arcs, three shapefiles inside one `well###.zip`, each with
      its own `.prj`. Staging holds them in the datum the archive declares (EPSG:4267) and
      the transform to 4326 is a promotion step under `cr_tx_nad27_1`, which pins a PROJ
      `hgridshift` pipeline over `us_noaa_conus.tif`. The grid is fetched as its own
      manifested artifact and its hash is checked against the rule, so a host without it
      fails rather than falling back to the three-parameter transform PROJ would otherwise
      choose — a median 3.40 m error where the pinned pipeline leaves 0.0074 m
- [New] `glasswell.ingest.tx_wellbore` loads the Wellbore Query export: 59 comma-separated
      fields, no header row, so the layout is `cr_tx_ewa_layout_1` carrying the RRC manual's
      own field numbers and two assertions proved on every record before anything is
      promoted. It writes TX identity into `canonical.wells` — operator, well name, status,
      total depth, completion date — and the well-to-lease keys into
      `canonical.well_lease_links`
- [New] `canonical.well_lease_links` captures `(oil_gas_code, district_no, lease_no)` under
      `cr_tx_lease_key_1` with `link_role = validator_a`. A bare lease number is not a key:
      33,868 of 348,293 in the 2026-08 export appear under more than one (code, district)
      pair. The links are recorded beside the canonical crosswalk the PDQ path will bring,
      never merged into it — their disagreement is the allocation error bound (SB-01 §2.9)
- [New] `mft_guid_resolve` is implemented: `glasswell.ingest.tx_mft` resolves a GoAnywhere
      public link to its listing, hashes it, and downloads through the portal's own form
      postback. The listing paginates at 250 rows while the well folder holds 255, so a
      first-page read silently loses four counties including Yoakum; the resolver pages once
      and refuses a listing shorter than the row count the portal declares
- [New] TX tile layers `tx_wells` and `tx_laterals` follow the landed view-model and
      function-source pattern exactly — privilege-scoped `marts.tile_tx_*` views, one
      `marts.<layer>(z, x, y, query)` function each, martin grants in the migration,
      `auto_publish` still false — and the map registers both, on by default, so panning to
      the Permian shows wells without a toggle in between
- [New] `service` joins the canonical status vocabulary. Eleven of the RRC's twenty-three
      well types describe injection, disposal, storage or observation rather than
      production, and 24,710 rows in scope are injection alone; painting those as active
      would be a claim about production the source does not make
- [New] A TX well card shows identity and geometry with their handles — total depth is a
      figure with a derivation, not a bare number — and carries no production section at
      all. `/v1/wells/{api10}` and `/v1/wells/{api10}/production` both warn
      `production_pending_allocation` and link the rule: TX reports at the lease (DIR-3), so
      "no production has been reported" would be false about a well whose lease reports
      every month
- [Change] The compute-CRS rule a length resolves is the one the basin names.
         `lineage.crs_registry` gains `length_rule_source`, the Permian row pins UTM 13N for
         area work with `cr_tx_compute_crs_1` measuring geodesically, and a TX length now
         cites a rule about TX geometry rather than ND's
- [Change] `lineage.quarantine_rows` admits `out_of_scope`: a county file whose features
         carry another county's API is not a parse failure, an unknown vocabulary or an
         orphan, and every existing code would have asserted something that did not happen
- [Fix] The TX identity pass keys API-10 over every record and the lease key only on the
      link path. Keying both together quarantined a well for a lease number it does not need
      and lost whole counties — every one of Bee county's records has no lease number yet

### 2026-08-21 — D1 phase 2: 48 GB of XML streamed into staging without holding it

- [New] Migration 028: eight verbatim staging tables for the NM sibling sources, a Parquet
      partition registry for the production spine, the NM pool, status and stream
      registries, and an index on `(source_id, production_month)` so promotion's batch
      predicate has something to sit on once canonical grows 122x. The reason vocabulary
      is untouched — migration 021 already admits `key_incomplete`, and the two codes
      SB-01 handback H5 asks for belong to the track that owns H5
- [New] `ingest/xml_stream.py`: BOM-aware UTF-16 decoding, a fully-qualified match against
      the `SqlRowSet1` namespace, and root pruning into 65,536-row batches. A bare-tag
      match against this document returns zero records in silence and `elem.clear()`
      without pruning holds all 48.1M siblings, so both are pinned in a rule and asserted
      in a test
- [New] `staging/duck.py` makes DuckDB — locked since P0 and imported nowhere — both the
      Parquet writer and the reader. Batches cross into it through the Arrow C stream
      capsule polars already exposes, because `pyarrow` is not in the lockfile and is not
      being added; `COPY ... (FORMAT PARQUET)` after `SET threads=1` is the expressible
      form of SB-01 §3.6's write profile, and the same rows written twice are byte-identical
- [New] `ingest.nm_ocd --stage-only` streams each artifact out of its zip member — nothing
      is extracted, so NM contributes nothing to the scratch budget — and reconciles every
      parsed row as staged or quarantined on the derivation itself (SB-01 §3.5). A batch
      that loses a declared column is quarantined as `schema_mismatch`; a column nobody
      declared, or a member that stops being XML, halts the load rather than staging a
      partial artifact as if it were whole
- [New] Twenty parse-stage rule rows: a record-tag, namespace, encoding and declared-header
      rule per source, plus the CHAR widths each one pads to. `prd_knd_cde` is CHAR(2) and
      arrives as `'O '`, so an exact-match vocabulary would have quarantined every row of
      the spine as `stream_not_promoted` while reporting success — the trim is a mapping
      decision and gets a rule row rather than a `.strip()` in the parser. Which columns
      pad is measured across every record of all nine artifacts, not assumed: 26 columns
      in six sources, each to one fixed width, while leading spaces are data

### 2026-08-21 — Basemap coverage and the 40 ms proxy stall

- [Fix] Basemap coverage: the serving extract is `conus` (z0–13, 4.22 GB) rather than the
      `nd-tx` box, which ended at the Rockies and at Memphis and rendered blank ground with
      no error at z3–z7. `scripts/basemap-regions/conus.geojson` is a superset of every
      basin region, asserted in `tests/unit/test_basemap_regions.py`, so a swap cannot lose
      coverage; the ND tiles are byte-identical
- [Fix] `/basemap/*` is served by Caddy's `file_server` instead of proxied to uvicorn:
      `uvicorn --workers N` binds a socket with `proto=0`, so asyncio never sets
      `TCP_NODELAY` and Nagle holds every response body under the loopback MSS until the
      peer's 40 ms delayed ACK. LAN medians through https: 4 KB range 48.7 → 5.9 ms,
      16 KB 49.0 → 6.4 ms, 16 KB eight-way 49.6 → 7.6 ms. The uvicorn mount is unchanged,
      so reverting the Caddy block is the whole rollback
- [New] `scripts/tile-probe.py` measures the basemap and tile paths over the transport a
      browser negotiates — sequential and concurrent range reads, first fetch, and
      `If-None-Match` revalidation — and reports percentiles rather than one sample
- [Change] `basemap-build.sh` verifies the extract before it takes the archive name, records
         the archive's own `bounds` in the manifest, and writes a `MANIFEST.sha256` that
         `sha256sum -c` passes in the deployed directory with no arguments (SB-06 §rules
         1-2). A coverage claim is now readable without opening the archive
- [Change] `infra/basemap/README.md` records the region-is-coverage rule, the measured size
         ladder for `conus`, the symlink swap, and the Nagle diagnosis with the `tcpdump`
         that convicts it; `infra/caddy/README.md` records why the basemap block is the one
         place the edge states the response policy

### 2026-08-21 — the Caddy→uvicorn hop moves to a unix socket

- [Fix] Every proxied response smaller than the loopback MSS paid ~40 ms of Nagle/delayed-ACK
      before its body left the origin: `uvicorn --workers 2` builds its listener as
      `socket.socket(family=family)`, leaving `proto` at `0`, so
      `asyncio.base_events._set_nodelay` never sets `TCP_NODELAY` and the separate header and
      body writes stall. Caddy now dials `unix//run/glasswell/api.sock` and uvicorn binds it
      with `--uds`; AF_UNIX has no Nagle, so the defect cannot occur rather than being tuned
      around. Measured over the real https path, medians of 30: `/v1/health` 64.5 → 21.0 ms,
      a well card 84.1 → 39.0 ms, `/v1/wells?limit=25` 67.0 → 21.6 ms, a z11 tile 50.8 → 8.5 ms,
      a z13 tile 50.2 → 8.2 ms, the app shell 49.7 → 7.6 ms, `/healthz` 48.3 → 6.6 ms — every
      one a ~42-45 ms drop. The 304 path (8.6 → 7.9) and the basemap (5.8 → 4.6, served by
      Caddy) never paid the tax and did not move, which is the same evidence from the other
      side. Root cause and `tcpdump` in `work-output/tileperf-r2-status.md` §1
- [Change] The API has no TCP listener at all, and `--forwarded-allow-ips` moves from
         `127.0.0.1` to `*`: a unix peer has no address, so uvicorn leaves `scope["client"]`
         None and a numeric allow-list would stop trusting `X-Forwarded-Proto` and silently
         strip `upgrade-insecure-requests` from every CSP. The socket has one reachable peer,
         so `*` grants nothing the directory mode has not already decided. Caddy still binds
         `192.168.2.111:8000` for the courtesy redirect — that block is Caddy's and is
         unaffected
- [New] `infra/tmpfiles.d/glasswell.conf` creates `/run/glasswell` as `0750 glasswell caddy`,
      which is the whole access control because uvicorn chmods the socket `0666` and exposes
      no knob for it. Deliberately not a `RuntimeDirectory=`: systemd re-applies
      exec-directory ownership on every exec invocation, so a `chgrp` from `ExecStartPre`
      exits 0 and is then reverted before `ExecStart` — which cost a 502 on first deploy.
      `ExecStartPre=rm -f` replaces the stale-socket cleanup `RuntimeDirectory=` used to give
      for free, since uvicorn's `bind()` returns `EADDRINUSE` and exits; `install.sh` places
      the file, runs `systemd-tmpfiles --create` and creates the `caddy` group unconditionally
- [Change] `verify.sh` reaches the API through `--unix-socket` and its `exposure` block now
         asserts the socket answers, that its directory is `glasswell:caddy 0750`, and that
         nothing is bound to `127.0.0.1:8000` — the inverse of the assertion it replaced
- [New] `tests/unit/test_api_socket_contract.py` holds `glasswell-api.service`, the Caddyfile
      and `verify.sh` to one socket path and to the `*` allow-list, since each file is
      individually valid when they disagree and the symptom is a 502

### 2026-08-21 — DIR-14: the suite runs on the CI host, not the workstation

- [Change] The integration harness supports a remote docker daemon. A container's bridge IP
         is routable only from the daemon's own host, so `tests/conftest.py:daemon_address`
         decides once: a local daemon keeps the bridge address, a remote one publishes the
         database port and is addressed by the daemon's own hostname. Containers a test
         starts keep using the bridge address either way — `database_address_for_containers`
         is that address, and the martin test now takes its DSN from it rather than from the
         client's connection parameters
- [Change] The martin test copies its config in with `docker cp` instead of bind-mounting
         `tmp_path`, which a remote daemon cannot see, and reaches the server on a published
         port when the daemon is remote
- [Change] The session database's password is per-session rather than the fixed pair, since
         a remote daemon means a LAN-reachable port; `postgres_password` hands it to the two
         marts CLI tests, which reconnect from a `ConnectionInfo.dsn` that never carries one
- [Change] The session DSN carries keepalives and `tcp_user_timeout=30000`. A LAN loss burst
         backed one connection off to a 107-second RTO and hung a 25-minute run; the same
         fault now fails the test that hit it. They fire on unacknowledged data, so a slow
         query is unaffected
- [Change] An explicit `DOCKER_HOST` is now the only candidate the probe tries — a
         `make test-anvil` that silently fell back to the workstation would report a full
         suite against a host it never ran on
- [New] `make test-anvil` runs the full suite on the lab CI host, which is where full suites
      belong; `make test-local` is the same suite on this machine's daemon, for iteration
- [New] `make check-workstation` (`scripts/workstation-hygiene.sh`) fails on glasswell state
      that has no business on a workstation: installed units, cron entries, routable
      listeners, dev servers left running, unswept test volumes, regulator downloads outside
      the raw zone, and basemap extracts. Read-only — it reclaims nothing itself
- [New] The harness asserts which branch it took: one test that the session container
      publishes a port exactly when the daemon is remote, one that the client DSN and the
      container DSN agree about locality, and unit coverage of `daemon_address` across
      socket, loopback and remote endpoints

### 2026-08-20 — D1 phase 1: New Mexico's production spine, pulled and stamped

- [New] `lineage/ftp.py` and an `ftp_anon` transport inside `fetch_raw`: anonymous FTP to
      the pinned host, MDTM and SIZE read before the transfer and recorded in
      `acquisition_params`, the bytes hashed as they stream, and a short transfer refused
      rather than sealed. A host that does not answer halts with `raw.fetch_failed
      reason=host_unresolved` instead of guessing — the EMNRD page publishes the address
      as an image, so a re-pin is a config change and an audit event, never a scraper
- [New] Nine NM OCD sources with the honest licence note: UNVERIFIED, no published grant,
      and absence of a restriction is not a grant
- [New] Twenty-seven parse-stage rule rows — an undated-vintage, an FTP-layout and a
      host-pin rule per source, because `load_rules` reads one `source_id` per call and a
      derivation may not cite another source's rule. The FTP refreshes nightly with
      undated per-table filenames, contradicting its own published documentation, so the
      retrieval vintage is glasswell's own stamp and the `source_key` is the constant
      filename the supersession chain is built on
- [New] `ingest.nm_ocd --fetch-only`: one login, the tables in order, five seconds apart.
      A reset data channel — which is what 164.64.106.6 did on the third transfer — is
      retried twice on a fresh login, each failure recorded; a host that will not answer
      is never retried
- [New] Fixtures cut from one polite pull cached to `/data/raw`, preserving UTF-16LE with
      its BOM, the `SqlRowSet1` namespace and the inline schema. The production fixture
      straddles DIR-12's 2015-01 window because the member opens in 1973, and
      `tests/unit/test_nm_fixtures.py` asserts every trap it exists to carry
- [Change] `fetch_raw` reads `upstream_mtime`, the etag and the media type from whichever
         transport ran rather than from HTTP headers, and hashes the sealed files in
         chunks — the NM artifact is 968 MB and `read_bytes()` held all of it
- [Change] `seed_conformance_nd` counts its own jurisdiction's rules rather than the whole
         registry, which is what made a second state's seed non-idempotent

The `wcproduction` member measures **48,310,560,330 bytes across 48,104,334 records**,
streamed once in 24m51s: 17,645,580 rows and 80,624 well-completion × pool entities fall
inside the 2015-01 window. Three findings change what phases 2-4 must handle — a fourth
`prd_knd_cde` (`'C '`, condensate, 1986-1993 only), one row whose `api_well_idn` is six
digits and cannot compose an API-10, and an `amend_ind` that is a ten-value vocabulary
rather than a flag. `tests/fixtures/nm_ocd/SOURCE.md` carries the measurements.

### 2026-08-20 — increment-3 closeout

- [Fix] A well whose status is present but not in `cr_nd_status_vocab_1` is drawn as the
      absence class instead of not being drawn at all. The filter matched the literal
      `unmapped` id while the count routed any unrecognised code to it through
      `statusClass()`, so an unknown code fell out of the canvas, the legend count and the key
      at once — the failure mode the class exists to prevent

- [Fix] The satellite basemap's declared graticule fallback executes. `BasemapDef.fallback`
      had no consumer at all — `resolveStyle`'s non-vector branch set no failure path — so a
      reader whose imagery could not be fetched got an empty canvas, no banner and no
      graticule. The client now asks the imagery origin for one tile before committing to it,
      and degrades locally when the answer does not come (gate-inc3 R3.1)
- [Fix] The failure banner names the source that failed. The raster style reused the vector
      source id, so a USGS outage reported itself as `Tiles for protomaps did not load`; the
      imagery style now carries its own source and `sourceLabel()` turns a MapLibre
      `sourceId` into the locator a reader can act on — a host, or the archive path (R3.2)
- [Fix] The imagery attribution goes down with the imagery. A credit over a canvas with no
      imagery on it is a false statement about what was drawn (R3.3)
- [Remove] The hosted OpenFreeMap fallback, which `connect-src 'self'` had always refused;
      every basemap now degrades to the graticule, locally, through the one declared-fallback
      path both the vector and the imagery branches run

- [Change] The CSP names one external origin, `https://basemap.nationalmap.gov`, in
         `connect-src` and `img-src` and in no directive that loads code. USGS National Map
         imagery is public domain and keyless and has no self-hosted equivalent, so the
         satellite basemap could not draw under `connect-src 'self'` — 122 refusals and an
         empty canvas. Named, never a wildcard; requests happen only when a reader selects
         satellite, and dark, light and none stay zero-external under test (DIR-1 ruling)
- [Change] SB-05 §1.5 carries the amended policy and the reason, so the blueprint and the
         emitted header do not disagree

- [Remove] `statusMinZoomExpression()` is gone. The per-class zoom floor has one
      implementation — `visibleStatusesAt()` inside `statusFilter()`, measured holding at z4
      and z6 — and the second expression of the same table had no consumer at all
      (gate-inc3 4.1)
- [Fix] The status gate is applied to every layer the vocabulary paints, derived from the
      built layers rather than from a hand-written pair of ids. The pair was complete for
      North Dakota alone; a second basin's layers were ungated at style-build time and drew
      every class at every zoom until the reader happened to zoom, which is the disagreement
      between legend, count and canvas the gate measured on the Permian frames

- [Change] The unmapped row filters like every other class: its checkbox is live, All/None
         act on it, and `statusFilter()` withdraws it when the reader switches it off.
         It stays on by default and the zoom never withdraws it — a defect must not hide —
         but on the Permian slice it is the largest class on the canvas, and unfilterable
         ink is ink the reader cannot account for (gate-inc3 4.2)
- [Change] The legend builds the absence row up front and lists it only once the map has
         drawn one, so the switch exists before the class does; the collapsed pill counts
         what it lists (`Well status · 9/10`), and `glasswell.statuses` carries `unmapped`
         in its known vocabulary so a reader's refusal of it survives a reload

### 2026-08-20 — VF-6: legend select/deselect all

- [New] The well legend's header carries an All/None control, so clearing or restoring
      the nine status classes is one click rather than nine. It owns `checked` and
      nothing else: `disabled` and the out-of-scale mark stay the zoom's to set, so
      "All" cannot promote a class the zoom has withdrawn, and "None" clears one anyway
      so zooming in does not resurrect what the reader dismissed. It reports through
      the same `activeStatuses()` path a row toggle uses, and is hidden while the key is
      collapsed to its pill (VF-6)
- [New] The legend's status filter now survives a reload, under the same `{on,known}` shape
      the layer set has always used (`glasswell.statuses`), so a class added to
      `cr_nd_status_vocab_1` later arrives visible rather than hidden by a stored set that
      predates it. It did not persist before — VF-6 names a persistence contract the legend
      was not party to, and this is that half (VF-6)
- [New] The collapsed legend pill reads `Well status · 3/9` whenever classes are filtered
      out. A filter that survives a reload must not be invisible on the canvas that reload
      produces
- [Change] `persist.ts` takes the storage key as an argument — `readCapabilitySet`,
         `writeCapabilitySet`, `restoreCapabilitySet` — and keeps one debounce timer per
         key, so a status write cannot cancel a layer write still in flight

### 2026-08-20 — DIR-13: TLS on the LAN endpoint

- [New] Caddy terminates `https://glasswell.lab.rpx.sh` on VM 111 and reverse-proxies
      uvicorn on `127.0.0.1:8000`. The certificate is a Let's Encrypt host certificate
      obtained over the Cloudflare DNS-01 challenge — the only challenge that can be
      solved for a name resolving to RFC1918 — and `infra/caddy/` carries the Caddyfile,
      the unit and the argument for a download.caddyserver.com custom build over the
      distro package and over xcaddy (DIR-13)
- [Change] uvicorn binds `127.0.0.1:8000` rather than `0.0.0.0:8000` and runs with
         `--proxy-headers`, so the origin sees the request as https and its CSP carries
         `upgrade-insecure-requests`; `ufw` opens 80 and 443 to `192.168.2.0/24`, plus
         443/udp because Caddy advertises HTTP/3 in `alt-svc`, and the 8000 rule is gone.
         martin is untouched
- [New] `install.sh --with-caddy` places the Caddyfile and `caddy.service` and refuses to
      proceed on a binary without the cloudflare DNS module, a missing token file or one
      wider than `root:root 0600`; it validates the config before enabling the unit, and
      re-owns the access log the validation creates as root
- [New] `verify.sh` grows a `tls` block — issuer, subject, days remaining (a failure at 20,
      ten days after Caddy should have renewed, which is DIR-13's renewal alarm), the `:80`
      redirect, exactly one copy of each security header through the edge, one
      content-encoding on the bundle and on a tile, and a loopback-only admin API.
      `caddy.service` carries the `OnFailure=glasswell-alert@` hook the other units use
- [New] Caddy's access log filters both shapes the owner key can take: the
      `X-Glasswell-Key` header, and the `?key=` parameter the API refuses with a 422 but
      which an edge writes down verbatim — the way a key reached a log here once before.
      `verify.sh` sends both through the edge before reading the log back, so the check
      cannot pass for want of keyed traffic
- [Change] `scripts/smoke.sh` and `tests/e2e/smoke.mjs` read `$GLASSWELL_BASE_URL` and
         default to `https://glasswell.lab.rpx.sh`; `GW_BASE` survives as the retired
         alias so an old invocation targets what it names instead of the default
- [Change] SMOKE.md, `infra/README.md` and the e2e README are re-pointed at the https URL
         with no port, and the two stale suite counts (nineteen API assertions, twelve
         browser ones) are the twenty and thirteen the suites actually run

### 2026-08-20 — wave 1 merge train: the data-train batch fix

- [Fix] The anonymous read break-glass can no longer mint a credential. With
      `GLASSWELL_ALLOW_ANON=1` a caller presenting nothing resolved to owner *scope*,
      which satisfied the mutation guard, so the flag could leave durable owner keys
      behind that keep working after it is turned off. `check_scope` now refuses
      `kind = anonymous` for the mutation scopes; the read break-glass is unchanged
      (gate-a2-qa m-7)
- [Fix] Four published examples that could not resolve on a deployment now say so
      where a reader meets them: a vintage id is composed from a source and a
      knowledge date rather than content-addressed, a manifest's bytes carry the
      content-address note its sibling record already had, and the two key
      operations name a key the contract fixture seeds instead of a fabricated
      ULID (gate-a2-qa M-3)
- [Fix] The auth matrix covers `GET /v1/wells/{api10}/production/pools`. The
      endpoint arrived with one track and the matrix with another, and the
      coverage check that exists for exactly that caught it on the merge commit
- [Change] `e3-length-buckets.sh` computes the snapped bucket cuts in SQL and prints
         them in its verdict, instead of carrying the quartiles measured once as
         literals. `run-all.sh` can re-decide `LENGTH_BUCKETS_FT` after the E-0
         back-load without an agent editing the script (gate-bgate M-1)
- [Fix] `g13-formation-pools.sh` emits the two `VERDICT|` lines `run-all.sh` greps
      for — the `FORMATION_GROUP_MIN_COUNT` measurement at the threshold and the
      registry precondition — both read out of the measurement. The grep is
      `|| true`, so their absence was silent (gate-bgate m-4)
- [Fix] The glossary is alphabetical again: four adjacent pairs were transposed
      (`Effective date`/`EUR`, `Structural residual`/`Tile layer allowlist`,
      `Viewport`/`Vintage`, `Withheld`/`Working interest`). It is the seed set for
      `glossary_terms`, so its order is data (gate-bgate m-6)
- [Fix] The martin binary the tile-publication test starts is pinned to `1.14.0`,
      the version VM 111 runs; `latest` resolves there today and would move the
      test's subject silently (gate-o m-6)
- [Change] The OpenAPI snapshot is regenerated over the three data tracks at once —
         28 paths, the union of the freeze's 27 and the pool breakdown. A2's own
         differ classifies the delta as thirteen changes, all additive
- [Change] `infra/martin/config.yaml` publishes the three tile *functions* rather than the
         three views they read. Adopting it as table sources would have turned auto-publish
         off at the cost of the tile work landed hours earlier: a table source has no `z` to
         key a simplify tolerance on and cannot carry the materialised CTE. Measured on the
         deployed instance, table sources cost +21% bytes at z7, +35% at z9 and +42% at z11
         on `nd_laterals`. The privilege boundary is untouched — a `language sql` function
         runs with the caller's rights, so the `martin` role still reaches exactly the three
         `marts.tile_*` views, which is also why those views had to become what the functions
         read (DR-05, N-2)
- [Change] The deploy runbook reinstalls the tile functions when `marts/tiles.py` moves, and
         clears `.claude`/`.rdf` with the other working files. martin resolves the function
         signatures at startup, so a stale body is now a stale tile source rather than an
         unused one
- [Fix] `smoke.sh`'s per-point lineage assertion skips the `*_aggregation` columns.
      They are disclosure labels rather than figures and carry no handle, so the
      check demanded a handle that should not exist and read FAIL against a correct
      response — the same shape as the auth-matrix gap, one track's check meeting
      another track's new field
- [Change] SMOKE.md is re-read against the deployed instance after this train: the
         martin catalogue, the unsimplified-tile and the deploy-root-hygiene gaps are
         closed, the basemap is no longer described as absent, and a new entry states
         that the S-E re-promotion is armed on a timer rather than run, with the counts
         either side of it


### 2026-08-20 — wave 1: the S-E production key

- [New] The S-E production key: `canonical.production_monthly` is keyed by
      `(entity_type, entity_key, production_month, stream, source_id, report_vintage)`
      with `reporting_level` alongside and `api10` kept denormalised, so a Texas lease
      row and the two pool filings one API-10 makes in a month both have somewhere to
      live (reconciliation §S-E, DR-04)
- [New] `canonical.well_completions`, the `well_completion_pool` entity the §3.4.3 enum
      named and no table defined; New Mexico reports at exactly this grain, so the gap
      blocked P7a rather than P7b (SB-01 E5)
- [New] `cr_nd_pool_rollup_1`, the legislated sum that replaces D1's interim withdrawal:
      a well that filed in two pools promotes one row per pool plus a well row carrying
      their exact sum, disclosed as `aggregation = sum_over_pools`, with days taken as
      the maximum over pools and never their sum; 78 wells and 139,644 bbl that were
      served as zeroes are served as what the regulator filed
- [New] `cr_nd_entity_key_1` and the `key_composite` executor that runs it — the last
      rule kind with no implementation apart from `code_ref`; it also unblocks NM's
      well-completion key and TX's `(OIL_GAS_CODE, DISTRICT_NO, LEASE_NO)` lease key,
      neither of which may be built by a literal in a parser (R8, DR-40)
- [New] `glasswell.ingest.repromote`, which re-promotes every staged month under the new
      key from staging rather than from the workbook, appends a vintage instead of
      rewriting one, is idempotent, and closes the `key_collision` ledger rows whose
      collision no longer exists
- [New] `GET /v1/wells/{api10}/production/pools`, the per-pool breakdown behind a summed
      well series, and `links.pools` / `links.aggregation_rule` on the well series that
      point at it and at the rule
- [New] `condensate` enters the canonical stream vocabulary and `key_incomplete` the
      quarantine reason vocabulary, both for the states that need them (C7, SB-01 §2.10)
- [Change] A well series whose months were summed across pools says so per point in
         `*_aggregation`, carries `reporting_level = well_completion_pool`, and resolves
         to an aggregation derivation taken over the pool rows — never a serve-time sum,
         which would be a figure with no derivation to cite (DIR-3, R6)
- [Change] The `production_monthly_latest` window partitions on the entity key and needs
         no tiebreak at all: the primary key holds every column the window partitions and
         orders on, so a report-vintage tie inside a partition is unrepresentable, and
         believing otherwise is what made a same-vintage re-promotion look safe (SB-01 H2)
- [Change] A canonical row's composed granularity token is checked against its
         `reporting_level` by the database, and `lease_allocated` is refused outright
         because allocation is a derived artifact and never a canonical observation
         (S-B, DIR-3)
- [Change] A promotion's `output_sha256` covers what it computed rather than the
         change-only subset it appended, so re-running one over the same bytes no longer
         trips the determinism detector with a hash that depended on prior state
- [Fix] `tests/support/seed.py` stamps the unit its stream declares instead of `bbl` on
      every row, takes `days_produced`, `null_semantics` and `value_hash`, and can seed
      any entity level; a fixture that made every gas row read `bbl` is a fixture that
      made the unit column untestable (DR-46)
- [Fix] A re-promotion at a vintage that already answers is refused rather than swallowed.
      `report_vintage` is the wall-clock day, so running the correction on the day the fleet
      was last promoted put every well aggregate on the primary key of the row it corrects;
      `on conflict do nothing` discarded them all while the collision ledger closed anyway,
      restoring the zero-producer defect with its only disclosure deleted. A repeat run that
      computes what is already recorded is still a no-op, as the derivation store's
      reconcile() is (SB-07 §1.3)
- [Fix] A well row that becomes a disclosed sum is appended even when its value did not move.
      The change key is `value_hash` plus `reporting_level` and `aggregation`; `value_hash`
      itself keeps migration 008's definition, so an unaffected well still appends nothing,
      but a well whose sibling pool contributed no volume no longer keeps an undisclosed head
      row and serves a cross-pool sum as a single-pool observation
- [Fix] A released ledger row carries `released_at_vintage`, and the withdrawal and
      withholding queries read it as of the vintage being asked for. An as-of replay of a
      date before the release disclosed nothing and answered with an affirmative regulator
      zero; it now answers what that date answered (DIR-2)
- [Fix] Collisions are superseded only for the well-months whose aggregate actually landed,
      and `RepromotionReport.rows_appended` counts rows that landed rather than rows that
      were computed
- [Fix] A no-op re-run no longer overwrites the vintage ledger row with zeroes, and two
      staged manifests for one workbook are refused up front rather than resolved by
      insertion order half-way through a run
- [Change] `entity_type` and `reporting_level` are checked against each other, so a lease row
         can no longer assert it was observed at the well. Latent today — every row is
         consistent — and load-bearing when the lease and pool writers arrive at P7a/P7b

### 2026-08-20 — wave 1: the /v1 freeze, keys and security headers

- [New] `/v1/keys` issues, lists, revokes and rotates API keys at owner, agent or
      guest scope: the cleartext is returned once and never stored, only its sha256
      reaches the table, issuance and revocation append `key.issued` / `key.revoked`
      to the audit stream, and an unknown key, a revoked key and an empty key table
      all answer identically so no caller can use the refusal as an oracle
      (SB-06 §8.3, DR-67)
- [New] Security response headers on every surface: a Content-Security-Policy that
      admits the MapLibre worker's blob URL and same-origin PMTiles range fetches and
      nothing else, plus `X-Content-Type-Options`, `X-Frame-Options: DENY`,
      `Referrer-Policy: no-referrer` and `X-Robots-Tag`; the policy was verified in a
      headless browser against the real bundle, and re-verified by removing `blob:`
      and watching the map die (SB-05 §1.5, N-6)
- [New] `/v1/vintages` and `/v1/vintages/{vintage_id}` serve the promotion records
      `as_of` resolves against, and `/v1/derivations` serves the collection the
      service index had been linking to since it was written (S-K, DR-65)
- [New] `/v1/manifests/{manifest_id}/bytes` serves the archived copy of a fetched
      artifact to the owner, or to any key when the source's terms mark it
      redistributable; a `storage_uri` that resolves outside the raw zone serves
      nothing (SB-07 §9.6)
- [New] The OpenAPI document states its own freeze terms in `info`, and a differ
      classifies any change against the committed snapshot as additive or breaking —
      a removed path, a withdrawn response guarantee or a newly required request
      field is reported as the `/v2` event §3.6.1 says it is
- [New] The auth matrix is a committed test: every served operation against
      anonymous, invalid, revoked, guest, agent and owner, with a coverage check that
      fails when an endpoint arrives without an entry
- [Remove] `/v1/explain?ref=` is refused with `parameter_removed` instead of being
      accepted and ignored, and `storage_uri` is absent from every manifest response
      below owner scope. Both are removals, so both had to happen before the S1
      freeze published the surface (S-A, S-K, DR-02, DR-33)
- [Change] `problem.type` is origin-relative, so it resolves on the LAN name, the
         tunnel name and localhost alike; the previous absolute host answered on
         only one of the three and was a dead link from the other two (N-9)

### 2026-08-20 — wave 1: ops and the regression net

- [New] `scripts/smoke.sh`: twenty read-only assertions over a deployed instance —
      both refusals, the key refused in a query string, the card's unit and derivation
      handle, per-point production lineage, the chain that ends at a 64-hex sha256 and a
      `dmr.nd.gov` url, every conformance rule's rationale and evidence url, a tile
      derived from the well's own surface point, staging refused through the proxy, and
      every committed OpenAPI path present on the instance
- [New] `tests/e2e/`: thirteen browser assertions and `make test-e2e` — the app boots and
      draws, a deep link resolves to the well it names, a handle reaches a checksum and a
      regulator url on screen, a hostile query string puts the page outside neither the
      tile allowlist nor this origin, and a visitor with no key is refused honestly. Its
      own npm project, so `playwright-core` never enters the web bundle's lockfile
- [New] `tests/integration/test_tile_wire_types.py` audits every column of every served
      relation, enumerated from the catalog rather than from the declarations — property
      types, geometry type and srid against `geometry_columns`, the attributes read back
      out of the protobuf, and the tile role's own column grants
- [New] `make prune-test-volumes`, run by `make test`, and a labelled named volume the
      PostGIS fixture removes itself; `tests/integration/test_harness_hygiene.py` asserts
      every mount the harness attaches carries the sweep label
- [New] CI gained a shell job (`bash -n` and `shellcheck` over every tracked `.sh`) and a
      named step asserting martin's configured source list equals the tile allowlist
- [New] `install.sh` creates `/data/staging` and `/data/scratch`, SB-07 §2.3's zones under
      the volume that exists; `verify.sh` asserts all three roots, asserts the deploy root
      carries no git-excluded working file, and checks all three published layers rather
      than two
- [Fix] `ds_size_acres` was published as `numeric`, so `ST_AsMVT` put the acreage on the
      wire as the string `"640"` and a MapLibre expression compared it lexicographically —
      the defect migration 015 fixed for `lateral_length_ft`, one layer over. The same
      audit found the martin declaration still calling `nd_laterals` a `LINESTRING` after
      migration 017 widened the column, and `lateral_length_ft_exact` riding an
      auto-published tile as a 19-digit string across 8,611 features
- [Fix] `create on schema marts` existed only because it was typed on the deployed host
      during P7; it is held by a migration now, with the spacing-unit view granted to the
      API role that migration 009's blanket grant could not reach
- [Fix] The pmtiles install hint and the basemap runbook told every operator to write the
      same `/tmp` path; both use `mktemp -d` now
- [Fix] DR-05: `infra/martin/config.yaml` had never been adopted because its DSN names no
      user and `martin.service` runs `User=martin`, for which no PostgreSQL role existed.
      Migration 026 creates it, publishes each layer through a `marts.tile_*` view holding
      exactly the columns that layer serves, and grants the role select on those three views
      and nothing else — so `staging`, `canonical` and the `numeric`
      `lateral_length_ft_exact` are unreachable by privilege rather than by declaration.
      `install.sh --with-martin-config` places the file and a `martin.service` drop-in.
      Adopted, martin publishes three sources where auto-publish published eleven, three of
      them `staging` relations
- [New] `tests/integration/test_martin_publishes.py` starts the martin binary as the role the
      unit runs as and reads its catalogue. Config and grant were previously verified apart:
      a column-level grant expresses the same intent and cannot work, because PostGIS's
      `geometry_columns` filters on `has_table_privilege`, and martin would have exited into
      a `Restart=on-failure` crash loop with every tile down
- [Change] The martin config declares `pool_size` under `postgres:`, where 1.14.0 reads it;
         at the top level it was silently ignored. The same run settles the
         view-under-`tables:` question — martin resolves the spacing-unit view as
         `source.kind="view"` without complaint
- [Change] SMOKE.md re-read against the instance that ran migrations 014-019: the hero
         lateral is 15,065.44 ft, there are 17 conformance rules, the quarantine ledger is
         292,972 rows with `unknown_vocab` and `out_of_range_date` at zero, and "292,394
         rejected rows" is corrected — 98.7 % of the ledger is deliberate non-promotion
         and true source-row rejection is 0.79 %

### 2026-08-20 — wave 1 merge train: the pre-train batch fix

- [Fix] The read slot stops shearing the bottom rule off the key chip and the
      degraded pill (gate-v M-1). The slot budgets a 20 px line, a 4 px gap and a
      16 px signal line; the layout came to 21 + 4 + 18, so 1.5 px fell off each end
      at 1600 and 1024 and the amber pill read as an open bracket. Two mechanisms,
      neither of them the `line-height` the finding named — that was already 16 px:
      the as_of row baseline-aligned a 10.56 px eyebrow inside a 12 px mono strut,
      and the pill's 1 px border added to an auto-height inline-block. The row is
      centred and the pill's rule is an inset ring; measured 20 + 4 + 16 = 40 px with
      zero overflow at 1600, 1024 and 390
- [Fix] The theme control ships `hidden` and the wiring unhides it when
      `VITE_GW_THEME_TOGGLE` is on (gate-v m-3). The module script is deferred, so
      the flag-off build painted an inert control for the pre-hydration window and
      then removed it

### 2026-08-20 — wave 1 fix round: the rail holds still

- [Fix] The rail's find and act groups no longer move when state changes. The read
      slot was `max-width`-capped inside a right-packed row, so every word the
      status gained shoved search and the buttons sideways — 117 px at 1600 between
      idle and a degraded source, 100 px on a rejected key, which landed on the
      first thing a new reader does. The slot is a fixed column per breakpoint now
      and the key chip moved into it, so the two groups have one position in every
      state; measured spread across all four states at 1600, 1024 and 390, both
      themes, is 0.00 px
- [Change] The theme toggle is behind `VITE_GW_THEME_TOGGLE`, off by default, until
         the map can follow the theme: `map.css` hardcodes a dark overlay surface
         while taking `color: var(--paper)`, so light rendered the legend and the
         tile-failure toast black-on-black, and the basemap has no light variant
         wired at all. The theme, its tests and `applyTheme` all stay; only the way
         in is closed, and dark is forced past a preference stored before the flag
- [Fix] The wordmark accent takes the text-safe cyan rather than the swatch cyan: at
      390 the wordmark is 18.4 px, under WCAG's large-text threshold, where the
      swatch measured 3.25:1 on light against a 4.5 floor. Now 4.82:1
- [Fix] The phone rail says "tap ⌾ for source" instead of truncating "Click any ⌾ to
      see where a number came from." to a stub that spent width to say nothing; the
      long form stays as the tooltip. The brief vocabulary lives in `chrome/status.ts`
      beside the slot it has to fit

### 2026-08-20 — wave 1: visual chrome and brand

- [New] The brand faces are self-hosted and same-origin: Inter 4.1 and JetBrains
      Mono 2.304, subset to latin as variable WOFF2 (73 KB / 20 KB) under
      `web/public/fonts/`, plus a 1 KB two-codepoint face carrying `U+233E ⌾` and
      `U+2715 ✕`, which Inter does not have. Both upstreams are SIL OFL 1.1 with no
      Reserved Font Name and both licences ship beside the files. No font CDN: a
      `gstatic` request would publish a page view past Access to an origin the
      reader never agreed to
- [New] `web/public/fonts/README.md` records the substitution the faces represent
      and parks it for owner sign-off: BRAND.md §Typography specifies `system-ui`
      and `ui-monospace` and forbids font loading, VF-4 asks the app for a loaded
      brand face, and the two are reconciled by scope — collateral keeps the
      generic stacks, the served app pins Inter and JetBrains Mono. BRAND.md is
      not edited; until sign-off it remains the contract and the README is the
      recorded divergence
- [New] A light theme built from BRAND.md's light column, with a control in the
      rail's action group; the choice persists per reader. Dark stays the default
      because the default basemap is dark. Every text colour that is also a data
      colour gained a text-safe cousin, so a sentence clears AA where the swatch
      beside it does not have to
- [New] Type tokens — `--gw-font-display`, `--gw-font-body`, `--gw-font-mono`, a
      size and weight scale, `--gw-radius-*`, a spacing scale and a seven-rung
      z-index ladder — all in `:root` and consumed everywhere; `map.css` takes the
      same tokens and declares no face of its own
- [Change] The header is a designed rail rather than an image and a control row:
         the wordmark is live text at 24 px with `well` in the accent, the lockup
         SVG that was being drawn at 32 px tall is gone, the strap is a brand
         element with a perforation-tick rule, and the right cluster is three
         labelled groups — find, act, read — on one 40 px band, hairline-separated
         (VF-1, VF-2, VF-3)
- [Change] The brand face flows through panel titles, drawer headers, the glossary
         popover, the well card's API-10, chart axis labels and the null-semantics
         key; identifiers, hashes and figures are set in the mono face with tabular
         figures, and `cv05`/`cv08` disambiguate `l`, `I` and `1` in operator names
         (VF-4)
- [Change] The production plot reads the theme's palette instead of a hard-coded
         dark grid, and repaints when the theme changes — a canvas inherits no CSS
- [Change] The chart's title moved into the card's frame, outside the element the
         plot replaces, so the placeholder and the error state keep it; it was also
         being rendered twice
- [Fix] The search results panel was anchored to the field and hung 79 px off the
      left edge of a 390 px viewport, clipping every operator name; at that width
      it now belongs to the viewport
- [Fix] Glossary terms are announced as buttons and activate on Enter and Space,
      but pointed with `cursor: help`; they now point like the control they are
- [Fix] One `:focus-visible` rule for the whole app, and a quieter dashed ring for
      the `tabindex="-1"` headings that are focus landing spots rather than controls
- [Remove] The `.gw-legend` rules, dead since the legend moved to `map.css` under
      `.gw-lg*`. `.gw-swatch` stays — the chart legend still uses it

### 2026-08-20 — wave 1: map legibility and the client's half of the tile contract

- [Fix] Every text-bearing layer and context line is coloured for the basemap under
      it rather than for the dark one it was drawn against: the spacing-unit label
      measured 2.04:1 on light and 1.58:1 on imagery (VF-5). 34 styled layers across
      the four variants and 127 measured cells, each against its WCAG floor, with
      the one sub-floor reading disclosed as a harness artifact — satellite z9, a
      cell where the label's own `minzoom: 11` means it cannot draw
- [New] The active basemap variant is published as `data-basemap` on the root and on
      the map container, so the styling pass and the stylesheet key on the same fact
      rather than each deciding it
- [New] `?legend=0` closes the legend for a screenshot or a shared link
- [Fix] A source id from `?wells=`, `?laterals=` or `?spacing=` is matched against
      `/^[a-z][a-z0-9_]{0,63}$/` before it becomes a tile path, an MVT
      `source-layer` and a `promoteId` key, and falls back on anything else; 24
      hostile values are pinned, including the traversal Track O reproduced (N-5)
- [Change] Each vector source declares the lowest zoom any of its own layers draws
         at, so the spacing source stops fetching the z0-z7 tiles nothing could
         render — the 568 KB z7 one included. The rest of the z7 cliff needs the
         PLSS-township substitute and is an owner decision, not a client one
- [New] The tile request is held to the cache contract the server now offers: the
      url is byte-identical on a repeat fetch, no `cache` or `credentials` flag is
      set, no explicit `Accept-Encoding` is sent, and the tile stays same-origin so
      the key does not turn every tile into a preflight. `maxzoom: 14` is pinned to
      `TILE_MAX_ZOOM` with the coupling named, so the two move together or not at all
- [Change] Map identifiers take `--gw-font-mono` rather than a literal stack, so the
         hover card and the layer readouts are set in the same face as identifiers
         everywhere else

### 2026-08-20 — tile serving: the zoom cost, measured and cut

- [New] The laterals function source thins its geometry in proportion to the zoom it
      is building for, four MVT units of tile extent, so the discarded detail stays
      a quarter of a rendered pixel: 12.8% fewer bytes at z7, 20.6% at z9, 28.2% at
      z11. Points and the spacing-unit polygons are left alone, where the same
      change measured as a cost with no return (SB-05 §2.4.1 pins a fixed metre
      ladder and marks it for tuning against measured tile bytes; this is the tuned
      form)
- [New] `/basemap/*` is served `public, max-age=86400` — the archive is immutable
      for the life of a vintage — with `manifest.json` held at `no-cache`, since it
      is how the client notices a swap
- [Fix] Every tile evaluated `ST_AsMVTGeom` twice per row — once for the null test,
      once for the aggregate — because the planner flattened the subquery. The
      function sources materialise it, which is 5–40% off every layer at every zoom
      measured on the live ND slice, most of it where the tiles are largest
- [Fix] The tile proxy asked martin to gzip every tile, because that is what the
      default `Accept-Encoding` of any HTTP client says. martin obliges: 140 ms of
      tile-server CPU on the hottest tile in the access log, to save 48 KB over
      zstd's 19 ms — after which the proxy decoded the result and shipped the 2 MB
      form anyway. It now asks for `zstd` when the caller can take it and
      `identity` otherwise, and passes the body through in whatever encoding martin
      chose rather than decoding it
- [Fix] Tiles carried no cache class at all, so a browser re-fetched every one:
      5,903 tile requests over 1,050 distinct tiles in 24 hours, one z7 tile 109
      times. Responses now carry martin's strong `ETag`, `Cache-Control: private,
      no-cache` and `Vary: Accept-Encoding`, and `If-None-Match` is forwarded, so a
      repeat costs martin's 0.7 ms `304` and no body; an empty `204` tile is
      cacheable on the same terms

### 2026-08-20 — Wave 1: the pre-P3 gate

- [Change] The blueprint is **v0.6-rc2**: the twenty amendments of the pre-P3 gate
         are applied, nine of them change-controlled with their rationale in the
         commit that landed them, plus G-13. Section 11 stays open — amendment 35
         is owner-gated and G-13 added a row to the table rather than removing one
- [Change] Eight constants stopped being assumptions and became measurements against
         the live ND data: `PAD_RADIUS_M` and `PAD_WINDOW_DAYS` ratified at 150 m /
         180 days with `pad_group_max_share` at 0.0008 against a 0.02 guard;
         `TC_MIN_N` at 20 with 89.3% of subjects on rung 1 and 2.5% with no control;
         the lateral-length buckets **moved** to {<8000, 8000-10000, 10000-10500,
         >10500} ft because the old cuts held 6.2% and 58.5% of wells in two of
         four; and `FORMATION_GROUP_MIN_COUNT` at 100, where nine ND groups cover
         97.15% of wells
- [New] `formation_group` becomes conformed data (G-13): a LOOKUP rule per reported
      pool, a canonical column on `canonical.well_completions`, and a feature
      registry row. The peer group, the Mondrian calibration taxonomy and the analog
      space all keyed on a column that existed in no table in the database
- [New] G-12 is answered with evidence rather than deferred: a 206 KB ranged read of
      the 321 MB ND survey archive found 5,470,017 stations carrying MD, inclination,
      azimuth and TVD, so ND keeps `landing_tvd_ft` and `structural_residual_ft`, with
      units and datum shipped as conformance rules rather than assumptions
- [New] A `modelled` figure gets a wire token. R5's composition table is complete over
      all four granularity values, 3.6.2 defines the forecast figure and a closed list
      of qualifier blocks, and the registry, calibrator and forecast DDL are reconciled
      against the tables that actually ship
- [New] P3 states its entry gate — the ND MPR back-load — instead of discovering it.
      Six production months are loaded and a cum12 label needs twelve after a rolling
      origin, so every origin measures zero test wells today
- [New] `scripts/experiments/` ships seven runnable, read-only experiments, each
      carrying its decision rule and printing a verdict, so the four provisional
      constants refresh mechanically when the back-load lands

### 2026-08-20 — fix cycle: data truth, guardrails, panels and map

- [New] The well card discloses what the map cannot show and the ingest held back:
      `below_tile_resolution` for laterals no zoom can render, and
      `geometry_not_promoted` for a well whose only horizontal trace is a
      sidetrack (audit A3-F5, A3-F3)
- [New] CI runs the code: a `python` job (ruff, then the full pytest suite against
      a PostGIS container the suite starts itself) and a `web` job (vitest,
      `tsc --noEmit`, production build), alongside the collateral job that was the
      only one before; `GLASSWELL_REQUIRE_DOCKER` turns a missing daemon into a
      failure, so a suite that skipped two of its three tiers can no longer report
      green
- [New] The raw zone verifies itself: `MANIFEST.sha256` is written beside the
      payload and `manifest.json` before a vintage directory is sealed, so
      `sha256sum -c` passes inside a restored directory with no arguments and no
      database (SB-06 §3.3 rule 2)
- [New] The naked-number allowlist has a minimality gate: every served figure is
      re-walked against every exemption, so a broad pattern such as `/**` fails
      the walker instead of silencing it
- [New] The naked-number walker reaches past the published examples: every handle
      a response carries is resolved to its derivation record and checked there too
- [New] `install.sh` places `glasswell-backup.{service,timer}` and the two backup
      scripts, adopted byte-for-byte from the host that was already running them;
      `--enable-backup` arms the timer, which stays disabled by default like the
      ingest timer
- [New] `verify.sh` checks the shipped Postgres tuning against the running server,
      driven by the drop-in itself so the check cannot drift from the file it
      verifies
- [New] Well search in the header over the `q` filter the API has always answered:
      250 ms debounce, one request in flight, `/` focuses it, rows read name ·
      API-10 · operator · status, and a pick opens the card and flies the map to
      the well. There was previously no text input anywhere in the application
- [New] In-app key recovery: a rejected or missing owner key raises a prompt with
      a key field and a "clear stored key" button, and every 403 routes to it. A
      wrong stored key used to fail every request with devtools as the only way
      back
- [New] Header rebuilt as a control surface: brand lockup, uppercase micro-strap,
      right-hand control cluster and a width-capped meta slot, with four status
      channels that never overwrite one another — resolved vintage, persistent
      status, transient toast and key state
- [New] Centralized focus management: one MutationObserver drives focus-in,
      focus-restore and `inert` for every panel, and Escape closes the topmost
      layer — drawer, then card, then the key prompt
- [New] The stylesheet's first media queries: below 900 px the card and drawer
      become full-width bottom sheets and the controls take a 44 px tap target;
      below 620 px the lockup becomes the square mark
- [New] The bundle is gzipped on the wire (1,153,996 to 322,718 bytes) and hashed
      assets carry `Cache-Control: public, max-age=31536000, immutable`, with
      `no-cache` on the shell that names them
- [New] Self-hosted basemap: a Protomaps PMTiles extract served from this origin
      at `/basemap` with a manifest carrying its vintage, region, maxzoom and
      sha256; `scripts/basemap-build.sh` builds it (ND measures 48 MB at z0–13,
      ND+TX 336 MB) and `infra/basemap/README.md` is the deployer runbook
- [New] Basemap switcher with four keyless options — brand-tuned dark, a grayscale
      light variant, USGS imagery and the graticule — reachable by `?base=`,
      remembered through a guarded lookup, with a collapsed attribution pill and a
      banner naming any source whose tiles fail and what was substituted
- [New] Layer registry drives the panel, the pills, the legend, the reset and the
      persisted `{on, known}` set from one table; wells, laterals and spacing units
      are registered, and EIA play outlines and USGS assessment units are
      registered as stubs stating that no ingest recipe exists yet
- [New] Layer panel with per-layer opacity, a search filter, provenance badges, the
      epistemic subtitle in the row, the geometry `derivation_id` read back out of
      the tile, and out-of-scale rows disabled with the zoom that brings them back
- [New] Legend rows are filter controls with live counts taken from what is
      rendered, collapsed to a title pill by default, patched in place, showing an
      em dash rather than a zero for a count the viewport cannot supply
- [New] Active-layer pill strip, scale bar, rotation disabled, and a hover card
      that identifies a well from the tile's own fields without a request
- [New] The assembled style is validated against the official style spec in a test.
      MapLibre drops a layer that fails validation and reports it on the `error`
      event, which an `error` listener then swallows — an invalid paint expression
      reads as "the well layers do not appear" over a clean console, which is how
      it shipped during this phase
- [Fix] A production point cites the derivation that promoted its own month.
      `sorted(derivations)[-1]` put one handle on a whole column, and ND publishes
      one workbook a month, so 327,924 of 394,278 served numbers explained to a
      regulator file that does not contain them; `_lineage` now keys a handle per
      point once a column's months disagree (audit D3)
- [Fix] The tile ships `lateral_length_ft` as a double rounded to the cent instead
      of a twenty-digit protobuf string a MapLibre expression compared
      lexicographically; the exact conversion stays in `lateral_length_ft_exact`
      (audit A3-F4)
- [Fix] A month NDIC pools as CONFIDENTIAL is quarantined as
      `confidential_withheld` instead of `out_of_range_date`, and rides the series
      axis with a null value and `withheld` semantics rather than vanishing:
      1,055 well-months, relabelled from their own payload (audit D2 / A5-F7)
- [Fix] The horizontals segment vocabulary is a rule and a reference table, not a
      literal in the loader; its 24,872 held-back rows carry
      `segment_not_promoted` and the rule that decided them instead of
      `unknown_vocab`, which claimed the ingest could not read a segment it had
      parsed itself (audit A5-F6)
- [Fix] Multi-part centrelines are stored as published rather than filed as
      `parse_error` with a NULL geometry; six real laterals were dropped by a
      staging column that declared LineString (audit A5-F8)
- [Fix] A month whose API-10 filed in more than one pool is withdrawn as
      `multi_pool_pending` with the ledger's own numbers in `meta.warnings`,
      instead of serving one pool's row as `well_observed` and `reported_zero`:
      78 wells, 454 well-months, 139,644 bbl (audit D1, interim guard)
- [Fix] `applied_rows` counts the rows a rule touched. `cr_nd_land_unit_1` was
      recorded as applied to 22,223 production rows by an executor that only
      checks three column names (audit D4)
- [Fix] `run.as_of` and the manifest `fetch_vintage` no longer diverge across UTC
      midnight: the vintage is read once when the lineage session opens, and a
      fetch stamps the day its run opened rather than the day its bytes happened
      to land
- [Fix] The pre-built `links.explain` percent-encodes the handle: a cell handle
      carries `#`, so the unencoded link sent the selector and `depth=full` as a
      URL fragment the server never received
- [Fix] The contract fixture seeds a derivation with numeric params, which the R6
      walker had never seen; `params={}` on every fixture derivation is why
      `/params/compute_epsg` shipped unexamined, and `/params/**` is now an
      exemption with a written reason
- [Fix] The published well example is a well that carries figures on a deployed
      instance, and the four content-addressed examples state in their OpenAPI
      description that they are the fixture's ids and where to obtain a live one
- [Fix] SMOKE.md gap 16 said 24,875 `unknown_vocab` rows where §5 and the database
      say 24,872
- [Fix] Panels are capped flex columns with a fixed head and a scrolling body, and
      the card is positioned off the drawer's actual state: it sat at `right:
      480px` whether or not the drawer was open, clipped below 940 px, and was
      entirely off-screen at 390 px, so tapping a lateral on a phone appeared to
      do nothing
- [Fix] Chart y axes carry their unit and the series on them, month ticks read
      `Oct 2025`, volumes carry thousands separators and are rounded to whole
      units; a withheld or unreported month is a gap in the line rather than the
      number the wire carried for it, and the state strip gained its key
- [Fix] Error panels link to `/v1/errors/{code}` on this deployment:
      `problem.type` is absolute at `glasswell.rpx.sh`, which does not resolve,
      and it was both the href and the link text
- [Fix] Repeated warnings collapse to one panel with a count, and the lineage
      drawer's acquisition link opens in a new tab instead of navigating the app
      away to download a 3 MB XLSX
- [Fix] Well status symbology matches the data: the nine classes of
      `cr_nd_status_vocab_1`, each labelled, `producing` (which matched no well)
      removed, dry, expired and temporarily_abandoned added — 12,339 of 43,817
      wells that rendered as an unlabelled grey — a struck-through modifier for the
      terminal classes per the ND DMR legend, an unmapped class in quarantine
      amber, and glass cyan reserved for selection
- [Fix] Wells render from zoom 4 rather than zoom 9, so the basin is visible at the
      app's own default viewport; culling is per status rather than a blanket
      minzoom, so active wells and drilling show statewide and the terminal classes
      arrive at zoom 9
- [Fix] Clicks hit-test a ±6 px box through one priority-sorted dispatcher instead
      of one exact-pixel handler per layer: measured on the same 195-point grid,
      6.2 per cent of clicks selected a well before and 42.6 per cent after, wells
      outrank laterals, and the pointer cursor and hover card follow the same query
- [Fix] Lateral width interpolates over `lateral_length_ft` coerced to a number:
      martin serves a Postgres `numeric` as an MVT string, so the ramp silently
      held its base value
- [Fix] The chart reads a handle per point, so a column whose months span promote
      derivations explains each point to its own month's workbook instead of
      reading `null`; the recorded web fixtures carry the percent-encoded explain
      links the API now emits
- [Fix] The pipeline role may clear a staging table, so `--restage` runs on the
      deployed database: migration 009 granted select and insert only, and the
      restage path added with migration 017 failed with `permission denied` on the
      VM while passing in a test tier whose connection owns every table
- [Change] Lateral length is measured geodesically on the WGS84 ellipsoid under
         `cr_nd_compute_crs_2`, which supersedes the UTM 14N rule rather than
         editing it. 97.6 % of ND laterals lie outside zone 14N, which overstated
         the fleet by 144,378.78 ft (+0.0709 %); the new method agrees with an
         independent pyproj geodesic to 8e-8 ft over a 100-lateral sample spanning
         the state (audit A3-F1)
- [Change] `[Change]` continuation lines indent nine spaces to the tag width, and
         the markdown variant of the rule is recorded rather than left to be
         re-derived
- [Change] infra/README.md carries a deploy runbook, including the two one-time
         steps that are still outstanding: applying the Postgres tuning, and
         dropping the `3000/tcp` LAN rule that sits in front of a loopback-only
         martin
- [Change] `web/src/bus.ts` is the seam between the map module and the rest of
         the app: selection requests in, committed selection and camera moves out
- [Change] Selection is `promoteId` plus `feature-state` rather than a duplicate
         `*-selected` filter layer per source, and data layers are inserted beneath
         the basemap's labels so town and county names stay readable over dense
         wells
- [Change] One selection bus: `map-bus.ts` is gone and the map subscribes to
         `bus.ts` itself, so the header search and the map cannot hold different
         ideas of what is selected, and a search that asks for zoom 12 gets it
         rather than the map's hardcoded floor
- [Change] The web fixtures are re-recorded from the migrated instance: the card's
         lateral length reads 15,065.44 ft where the projected rule said 15,073.98,
         the oil column carries a handle per month, and `compute_crs` reports the
         CRS the length is defined on beside the new `length_method`
### 2026-08-20 — North Dakota spine and map slice

- [New] Lineage and reproducibility spine: content-addressed raw zone with sealed
      payloads and a colocated manifest per artifact, derivation capture with a
      pinned environment, knowledge-time vintages, append-only audit stream, and
      `resolve_chain` walking any served figure to its terminal manifest
- [New] Conformance registry and quarantine ledger: every cross-source mapping is a
      registered rule with a rationale and an evidence URL, and every rejected row
      is kept with a reason code instead of being dropped
- [New] ND monthly production ingest from the free NDIC MPR path: six months
      (2025-10 through 2026-03), append-only restatements with as-of reads,
      per-stream null semantics, and key collisions quarantined rather than
      swallowed by `on conflict do nothing`
- [New] ND DMR GIS ingest: horizontal laterals, well points and spacing units into
      PostGIS, with the source datum recorded per file and the transform registered
- [New] API subset over the canonical model: wells, production, explain, manifests,
      conformance, quarantine, glossary, health and a martin tile proxy, all in one
      envelope with in-band figures, `_lineage` sidecars, RFC 9457 problems and
      cursor pagination
- [New] Serving marts and vector tiles: lateral centrelines and surface points
      published through martin under the ids the map requests
- [New] Map UI: MapLibre basin view with status-coloured laterals and no basemap,
      well card, monthly production chart, lineage drawer that reaches a SHA-256 in
      one `/v1/explain` call, and glossary hover over highlighted terms
- [New] Single-VM deployment: systemd units for the API, ingest timer and failure
      alerts, an idempotent installer, and a 27-check `verify.sh`
- [New] SMOKE.md: the first-pass walkthrough from URL to SHA-256, with the known
      gaps and the morning queue stated plainly
- [Fix] `fetch_raw` reads the run's clock instead of the wall clock, so an injected
      clock moves the manifest fetch vintage and a restatement lands on the vintage
      the run declares (B2)
- [Fix] Map style no longer declares `glyphs` as undefined: MapLibre validated the
      present-but-empty property, refused the style, and left a blank canvas with
      no layers and no tile requests
- [Fix] Tile URL templates keep MapLibre's `{z}/{x}/{y}` placeholders literal
      instead of percent-encoding them, which made every tile request 422
- [Fix] Production chart reserves room for six-figure axis labels instead of
      clipping them
- [Fix] The owner key rides in the URL fragment, never the query string: a query
      string is written to uvicorn's access log verbatim and reached journald in
      cleartext, so the API now refuses a `key` query parameter on every path and
      redacts the pattern from the access logger; the live key was rotated and the
      journal vacuumed
- [Fix] The tile proxy serves the published mart layers only; martin runs with
      `auto_publish` on, so its catalogue is every relation with a geometry column
      and the proxy's allowlist is what holds "staging never serves"
- [Fix] One length conversion in `glasswell.units`, imported by the API, the tile
      marts and the GIS load: the served figure and the tile mart disagreed at
      6731.12 against 6731.13 ft because one path rounded per lateral before
      summing and the two constants were reciprocals sharing a name; rounding is
      round-final at the serving edge and the mart stores the conversion unrounded
- [Fix] Quarantine reason vocabulary admits `stream_not_promoted` and
      `unknown_status`, and the rows whose `rule_id` proves the reason are
      relabelled: 98.7 % of the ledger read `unknown_vocab` for a deliberate
      not-promoted decision, recorded as a `quarantine.relabelled` audit event
- [Fix] All three ingest paths resolve the environment through one helper, so the
      GIS load and the mart refresh carry the lockfile hash the unit exports
      instead of stamping an unpinned `env_cli`
- [Fix] `granularity` is one vocabulary at the store and at the wire: the CHECK
      admitted a value the only sanctioned serializer refused, which would have
      been an unhandled 500 on the first lease-level row
- [Fix] The production build ships no source map; `StaticFiles` was serving 2.7 MB
      of readable proprietary TypeScript
- [Change] Frontend test fixtures are recorded from the deployed API rather than
         derived from the router source, so a response-shape drift fails a test
         instead of the first click
- [Change] README describes a repository that runs rather than one that is
         pre-build, and points at SMOKE.md

### 2026-08-19 — repository bootstrap

- [New] blueprint.md (v0.5) committed as the product and engineering contract
- [New] README.md, ARCHITECTURE.md and ROADMAP.md derived from the blueprint
- [New] Brand system: logo mark, horizontal lockups, dark and light banners, share
      card, and the palette and usage rules in BRAND.md
- [New] Architecture collateral: layer diagram, glass-box lineage chain,
      forecast-to-dollars pipeline with its control group, and the phase roadmap —
      all hand-authored SVG
- [New] Repository hygiene: proprietary license, .gitattributes export-ignore
      rules, .gitignore, contributing guide, security policy, code of conduct,
      GitHub issue and pull-request templates, and a collateral CI check
- [Change] Licensing and attribution: proprietary, all rights reserved, attributed
         directly to Ryan MacDonald. glasswell does not carry the GNU GPL v2 and the
         R-fx Networks org attribution that the rest of the rfxn workspace uses
- [New] llms.txt orientation file for agent consumers

At the close of that day there was no application code and P0 had not started — see
[ROADMAP.md](ROADMAP.md). The entries above this section are what changed since.
