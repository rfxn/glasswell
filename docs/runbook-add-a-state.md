# Runbook — registering a fifth jurisdiction

Written for someone who has not read the plan behind it. Every step names the refusal that
stops it being done in the wrong order, because the order is the whole point: a registration
whose rules do not exist yet is a registry citing decisions nobody made.

**What this does.** Adds a jurisdiction to `lineage.jurisdictions` and gets it onto the map,
the Status page, the facet panel and `/v1/jurisdictions`. It does **not** cover writing the
ingest — that is a per-regulator job with its own runbook — only the registration around it.

**What this replaces.** Nineteen literals across the routers, the status collector, two marts
and the web bundle. Adding Montana in v0.69 meant editing nine files that had no business
knowing about Montana. This is the list that replaced them.

---

## Layout

| | |
|---|---|
| registry seed | `src/glasswell/seed/jurisdictions.py` |
| registry migration | `src/glasswell/db/migrations/*_jurisdictions.sql` |
| generated client module | `web/src/map/jurisdictions.generated.ts` (never hand-edited) |
| the gate | `tests/unit/test_add_a_state.py` |

Throughout, `<CODE>` is the new jurisdiction's code (`CO`), `<PREFIX>` its two-digit API state
code (`05` — an API code, not FIPS).

---

## The order, and what refuses out of order

### 1. Register the source

`seed/reference.py` `SOURCES` (or the conformance module that owns it), with
`"jurisdiction": "<CODE>"`.

> **Refuses if skipped:** `lineage.conformance_rules.source_id` is
> `not null references lineage.sources`, so step 3 cannot run.

### 2. Register publication evidence

In the jurisdiction's own migration, insert into `lineage.conformance_rule_publications` with
`evidence_tag` and `evidence_commit` placeholders and a REPOINT CHECKLIST header — copy the one
at the head of `064_mt_registry.sql`.

> **Refuses if skipped:** `lineage.assign_conformance_rule_publication()` raises
> *"no publication evidence registered for conformance rule %"*.

### 3. Seed the R8 rules

`seed/conformance_<code>.py`, including `spec.unmapped_action` on the status vocabulary rule.
Decide it deliberately: North Dakota, Texas and Montana quarantine an unmapped code out of the
spine; New Mexico passes it through unclassed. Inheriting the wrong one silently drops wells.

> **Refuses if skipped:** `conformance_rules_publication_fk`.

### 4. Register the jurisdiction

Two files, and they must agree:

- `src/glasswell/db/migrations/*_jurisdictions.sql` — a row in `lineage.jurisdiction_codes` and
  one in `lineage.jurisdictions`, plus its `lineage.jurisdiction_rules` rows.
- `src/glasswell/seed/jurisdictions.py` — the same rows in `JURISDICTION_CODES`,
  `JURISDICTIONS` and `JURISDICTION_RULES`.

`JURISDICTIONS` is the **resolved** set — one row per code, carrying the latest published
values. The founding rows a restatement supersedes live in `JURISDICTION_RESTATEMENTS`, and
both writers emit both. Two runtime consumers build tuples straight out of `JURISDICTIONS` and
feed them into derivation params, so a second row for a code moves two mart addresses.

`source_ids` is **complete, not curated**: every source registered to this jurisdiction, or the
parity gate reddens. `identity_pattern` is derived from the prefix — do not spell it out.

**A `status_vocabulary` rule that resolves at read time owes three spec keys, not one.**
`lineage.refresh_status_resolution()` is driven by rows, and it selects on `mapping_table`,
`key_col` **and** `value_col` together. `spec->>` on an absent key is SQL NULL, so a rule
carrying only `mapping_table` is filtered out of the loop one step before the
missing-table notice can fire: the jurisdiction is skipped in silence and every one of its
wells resolves unmapped. Name the table and both of its columns.

> **Refuses if skipped or wrong:** `jurisdiction_rules.rule_id` references
> `lineage.conformance_rules`, so step 3 cannot be skipped; the composite foreign key refuses a
> rule row with no registration at that `(effective_from, published_at)`; and the `coalesce`d
> CHECK refuses an `api10` registration with no prefix.
>
> **Note the change from a mid-2026 draft of this runbook.** Both writers now skip a rule row
> whose conformance rule is not yet resident — migrations run before the seed, so on a fresh
> database `lineage.conformance_rules` is empty and a hard failure there would break every
> migrate. The completeness refusal moved to gate (b) in
> `tests/contract/test_jurisdiction_parity.py`, which asserts every resolved registration
> carries the rule rows it declares. It fails in CI, not at the keyboard.

### 5. Write the ingest — staging only

> **Refuses otherwise:** the pipeline role's grants, and `tests/support/layers.py`
> `schema_reads_in`.

### 6. Add the mart profile row

There is no mart module to write. `src/glasswell/marts/wells.py` refreshes every jurisdiction's
tile marts from one engine, and what differs between them is a `MartProfile` row beside
`TILE_LAYERS`: the dataset, the layers, the projections with their ordered published columns
and their select SQL, the spine columns the CTE selects, the params keys this jurisdiction adds,
the rules its refresh cites, and the audit payload it emits.

Everything the registry can answer, the engine asks it rather than the profile. The API prefix
comes from the registration. Which basin governs the compute CRS is a `basin_scope` rule; which
source measures a lateral is a `length_source` rule; whether a lateral is served at all is
`length_scope`, whose *presence* means withheld. A jurisdiction that publishes no length column
registers neither of the last two and the engine makes no call.

Optionally add a shim module — `JURISDICTION_CODE` and a four-line `main` that delegates — if
something outside the tree needs to type `python -m glasswell.marts.<code>_wells`. The four
resident ones exist because two applied migrations name them and the deployed timer executes a
third; a new jurisdiction needs one only if an operator command is going to name it, and
`glasswell-tiles --jurisdiction <CODE>` covers the ordinary case.

> **Refuses if the profile and the registration disagree:** `tests/unit/test_mart_profiles.py`
> holds each profile's `rule_ids` and params key set to what its address already carried, and
> the engine refuses at load time if a profile publishes a length column under a registration
> whose `length_scope` rule withholds one — a refusal rather than a `KeyError` inside a refresh.
> A profile for an unregistered code raises `MartProfileError` naming the registered ones.

### 7. Add the tile layer, then name it

Add the `TileLayer` to `marts/tiles.py`, then set `wells_tile_layer_id` on the registration.
The column lists stay hand-authored: they are per-jurisdiction by data shape, and deriving them
from data would encode a schema in rows.

> **Refuses otherwise:** `tiles.py` raises *"thinned but publishes no api10 to rank by"*, and
> the unit gate asserts every non-null `wells_tile_layer_id` names a member of `TILE_LAYERS`.

### 8. Publish it

Add the layer to `infra/martin/config.yaml`.

> **Refuses in either direction:** `test_martin_publishes.py` asserts the shipped config equals
> `{l.name for l in TILE_LAYERS}`.

### 9. Regenerate the client

```bash
make jurisdictions        # rewrites jurisdictions.generated.ts and wells-roster.json
```

Two artifacts, because two readers need different things. The generated module is what the
bundle imports; `web/src/map/wells-roster.json` is the same wells rows as data, for
`tests/e2e/chrome-fold.mjs`, which is plain node ESM and cannot import a TypeScript module.

The map's `Wells` family row, its swatch colour, its style layers, its draw order, its
first-paint default, its subtitle template, the layer panel's abbreviation tag and the status
vocabulary rules the legend prints all come from those two files. So do the point layer and the
struck sibling `style.ts` draws, the rank `click-router.ts` gives them, and the facet columns
`TILE_FACET_PROPERTIES` can press on — the roster carries the tile function's published columns,
read out of `marts/tiles.py` by the generator, so a jurisdiction whose tile publishes a
different column set needs no edit in `web/src`.

Nothing in `web/src` names a jurisdiction, and the gate above holds it that way — including
jurisdiction-scoped layer ids such as `co-wells`, which carry no prefix and no state name and
which the two-digit rule alone could not see.

> **The subtitle carries `{count}`, never a number.** The count is fetched from
> `/v1/jurisdictions` at render time with the date it was measured on beside it. A registration
> with a null `wells_tile_layer_id` is refused by name rather than rendered as the string
> `"None"`.

> **Refuses if skipped:** `tests/unit/test_regen_jurisdictions.py` fails while the committed
> file is stale.

### 10. Register the job rows

**Do not add an `ExecStart=` line.** Scheduling has been rows since v0.78, and an entry point
named in a unit file joins the set an installed timer already drives — after which the
double-run guard correctly forbids that job from ever being seeded `launch`, which is the
opposite of what a new jurisdiction wants. `docs/runbook-scheduler.md` is the whole scheme;
this is the part a new state performs.

Four inserts, one job per entry point:

1. `src/glasswell/seed/conformance_schedules.py` — a `cr_job_cadence_<job_id>_1` decision per
   job, `stage='schedule'`, `rule_kind='code_ref'`, with the rationale that says why this
   cadence and not another. `source_id` is the job's anchor, which the walk resolves.
2. Your own migration's `conformance_rule_publications` insert, under its own REPOINT
   CHECKLIST — that table is append-only and the scheduler's own insert closed at its repoint.
3. **Both writers, the same four inserts.** `scheduled_jobs`, `job_sources`, `job_schedules`
   and `job_dependencies` go in **your own migration** and in
   `src/glasswell/seed/schedules.py`. The migration is the one that matters: a deploy that
   seeds nothing still has to schedule, and `seed_all` is not on the migrate path. The seed
   module is the mirror the parity gate reads. Colorado is the worked example, at
   `077_colorado.sql:424-522` and `schedules.py`'s `CO_JOBS`.

   A jurisdiction with no legacy timer **may** be seeded `launch_mode='launch'` from day one,
   provided its cadence rule's rationale says why that is safe; every jurisdiction an installed
   timer still drives is `observe`.
4. An optional DSN flag in your own mains, resolved through `glasswell.db.dsn` so they read
   `GLASSWELL_DSN` then `DATABASE_URL` like every other entry point.

> **Refuses otherwise:** `tests/contract/test_schedule_parity.py` gate 1 is a two-sided set
> equality over `lineage.job_sources`, so a source registered in step 2 with no job row
> reddens; gate 2 refuses a jurisdiction mart with no ingest edge of its own jurisdiction;
> gate 3 refuses a `cadence` row the due rule can produce no instant for; and gate 4 refuses a
> rule with no publication evidence. Gate 5 holds the two writers to one truth — it resolves
> the registry the migration wrote and compares every field against the seed module's tuple —
> so writing one of them and not the other reddens rather than shipping half a schedule.
> `infra/verify.sh` refuses a `launch` row whose entry point an installed timer already drives.

### 11. Run the mart, then the count writer

```bash
export VENV=/opt/glasswell/venv
export GLASSWELL_DSN='postgresql:///glasswell?host=/var/run/postgresql'
sudo --preserve-env=GLASSWELL_DSN -u glasswell $VENV/bin/glasswell-tiles --jurisdiction <CODE>
sudo --preserve-env=GLASSWELL_DSN -u glasswell $VENV/bin/python -m glasswell.marts.counts
```

> **Run `seed_all` first, and not only for the API.** The tile refresh reads the registry now:
> it resolves the registration, its `basin_scope` and its `length_source` before it measures
> anything, and refuses by name if they are not there. The migration's `jurisdiction_rules`
> insert is guarded on conformance-rule residency, so on a fresh database those rows land only
> after the seed has run. `scripts/deploy.sh` already orders it that way (6a migrate, 6b
> `seed_all`, then the marts); what changed is that the mart is no longer indifferent to it.

The count writer measures every registration by default. `--codes ND,TX` narrows it to some of
them, which is a partial measurement rather than a smaller claim: the jurisdictions left out
keep whatever the ledger already holds. A code no registration carries is refused by name, so a
typo cannot report success over a run that measured nothing.

There is no `--measured-on`. The ledger's date is the day the measurement was taken, and the
key is `(jurisdiction, measured_on, status)`: a second run on a day the ledger already holds
inserts the rows that day lacks and keeps the rest, with the derivation each was written by. So
the day's rows may name two runs, which is honest as long as the counted population did not
move between them — run it on a day the ledger does not already hold if it did.

> **Refuses otherwise:** `jurisdiction_well_counts.well_count` is `not null` and
> `derivation_id` references `lineage.derivations` — there is no count without a refresh that
> produced it. Until the second command runs, `/v1/jurisdictions` serves this jurisdiction with
> **no** `well_count` and no `measured_on`. That is correct: "not measured yet" and "no wells"
> are different facts, and the surface never substitutes a zero for the first.

---

## Before you push

```bash
make lint
pytest tests/unit/test_add_a_state.py tests/unit/test_regen_jurisdictions.py -q
pytest tests/unit/test_mart_profiles.py -q
pytest tests/contract/test_jurisdiction_parity.py -q
npm --prefix web run typecheck && npm --prefix web run test
node tests/e2e/chrome-fold.mjs
```

The first is the gate this runbook exists to keep green: if it is red, a literal went into a
tree that is not allowed to have one, and the fix is a row rather than an exemption.

## What is deliberately not here

- **A `US` row.** `lineage.sources.jurisdiction` is a coverage axis, not a regulator axis: the
  BLM PLSS layers are tagged `ND` because that is what they cover. Federal sources have no
  regulator to register and stay outside the registry.
- **A `loaded` column.** Whether a jurisdiction's ingest has run is a fact about the data, and
  the facet surface reads it from the spine rather than from a registration.
- **Deleting anything.** `lineage.jurisdictions` is append-only under two clocks. Superseding a
  decision is a new row at a later `effective_from`; correcting what was published about an
  unchanged decision is a new row at the same `effective_from` and a later `published_at`. A
  restatement re-appends its rule rows — a row published at T2 states what was known at T2.
