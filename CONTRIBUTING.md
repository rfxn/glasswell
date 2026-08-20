# Contributing

glasswell is a single-operator build, so this document is less "how to open a pull
request" and more "what review rejects". The rules below are the ones that are
expensive to retrofit, which is why they are enforced from the first commit rather
than adopted later.

## Change control

[`blueprint.md`](blueprint.md) is the contract. Anything not in scope there is out
until the blueprint changes.

Edits to any of the following require a **written rationale in the commit body**:

- Section 4 — protocols
- Section 2.5 — design philosophy
- Section 3.0 — the canonical model thesis
- Rules R1–R8

Everything else is fair game and does not need ceremony.

## The rules review actually enforces

**A mapping that exists only in code fails review (R8).** If a commit conforms two
sources to one field, there is a `conformance_rules` row with a rationale and an
effective date, and the derivations reference it. No exceptions for "obvious" or
"temporary" mappings — those are the ones that rot.

**No naked numbers.** A new endpoint, chart, tile, or export that serves a figure
without a derivation handle does not merge. CI checks this; do not argue with it.

**Layer boundaries are absolute.** Parsers write staging. Marts read canonical. A
mart that reads a `stg_` table is a build error, not a shortcut. Staging never
serves.

**Rejects are quarantined, never dropped.** A row that fails validation goes to
quarantine with a reason code. Silently discarding rows makes the quality scorecard
a lie.

**Nothing in the raw zone is ever edited.** Restatements are new files with new
vintages and new hashes, appended. If a fix requires mutating raw, the fix is wrong.

**Inventory numbers carry their assumptions (4D).** No slot without geometric
admissibility and a support score; no rollup without the spacing assumption and the
support distribution stated. This is the feature most prone to confident nonsense.

**Every behaviour change gets a regression scenario.** Especially in the promotion
step, where a conformance bug is invisible until someone audits a number months
later.

## Working in the repo

```bash
git clone https://github.com/rfxn/glasswell.git
```

The repository is currently blueprint and collateral only — no application code has
been written. When P0 lands, this section gains the toolchain, the test command,
and the lint gate.

Commit style: a short descriptive subject, with body lines tagged `[New]`,
`[Change]`, `[Fix]`, or `[Remove]`. Stage files explicitly by name. No AI-assistant
attribution lines.

Diagrams in `assets/` are hand-authored SVG and are edited as source, not exported
from a design tool. Validate with `xmllint --noout assets/*.svg` and re-render the
PNG derivatives per [BRAND.md](BRAND.md) when a mark changes.

## Reporting problems

- **A wrong number** — open an issue with the `/explain` output for it. That is the
  entire point of the lineage chain: a bug report should be able to name the
  derivation, the rules applied, and the manifest.
- **A missing conformance rule** — open an issue naming the two sources that
  disagree and the field.
- **A security issue** — do not open a public issue. See [SECURITY.md](SECURITY.md).

## License

By contributing you agree that your contributions are licensed under the GNU GPL
v2, consistent with the rest of the project.
