<!-- See CONTRIBUTING.md for the rules review actually enforces. -->

## What & why

<!-- What does this change, and what problem does it solve? -->

## Changes

- [New] / [Change] / [Fix] / [Remove] …

## Checklist

- [ ] Scope is covered by `blueprint.md`; if it changes §2.5, §3.0, §4 or rules R1–R8,
      the commit body carries a written rationale
- [ ] Any new cross-source mapping is a `conformance_rules` row, not code (R8)
- [ ] Every figure this change serves carries a derivation handle, and `?explain=true`
      resolves it
- [ ] Layer boundaries respected — parsers write staging only, marts read canonical only
- [ ] Failed rows go to quarantine with a reason code; nothing is silently dropped
- [ ] Nothing in the raw zone was edited in place
- [ ] Inventory output states its spacing assumption and support distribution (4D)
- [ ] Behaviour changes have a regression scenario
- [ ] One branch-owned `changelog.d/*.md` fragment added; `CHANGELOG.md` remains integrator-only
