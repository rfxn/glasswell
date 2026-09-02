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

`source_ids` is **complete, not curated**: every source registered to this jurisdiction, or the
parity gate reddens. `identity_pattern` is derived from the prefix — do not spell it out.

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

### 6. Write the mart, with `STATE_CODE = "<PREFIX>"` at the module head

One literal per mart module is the honest declaration of which regulator's data it promotes,
and it is the only two-digit literal `marts/` is allowed.

> **Refuses if the prefix is unregistered:** `tests/unit/test_add_a_state.py` — the exemption
> matches `STATE_CODE = "<p>"` only for a `<p>` the registry carries.

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
make jurisdictions        # rewrites web/src/map/jurisdictions.generated.ts
```

The map's `Wells` family row, its swatch colour, the layer panel's abbreviation tag and the
status vocabulary rules the legend prints all come from that file. Nothing in `web/src` names a
jurisdiction, and the gate above holds it that way.

> **Refuses if skipped:** `tests/unit/test_regen_jurisdictions.py` fails while the committed
> file is stale.

### 10. Schedule the ingest

Add an `ExecStart=` line to `infra/systemd/glasswell-ingest.service`.

> **Refuses if skipped: nothing, today.** This is the one step with no gate behind it, and the
> gap is known — cadence-driven scheduling is the work that closes it. Until then, check the
> service file by eye.

### 11. Run the mart, then the count writer

```bash
sudo -u glasswell $VENV/bin/python -m glasswell.marts.<code>_wells --dsn "$DSN"
sudo -u glasswell $VENV/bin/python -m glasswell.marts.counts --dsn "$DSN"
```

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
