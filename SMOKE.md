# SMOKE.md — the first-pass walkthrough

Fifteen minutes at a keyboard, in order. Everything below was executed against the
running instance on 2026-08-20; the screenshots named in each step are on the build
host under `work-output/smoke-shots/` (untracked, not in git).

---

## 1. What this is, and what it is not

One basin, end to end, on one VM. North Dakota: NDIC monthly production and DMR GIS
geometry pulled into a content-addressed raw zone, conformed through a registry of
named rules, served by an API, drawn on a map — and traceable. A production number
on the chart resolves in **one** `/v1/explain` call to a SHA-256 and the
`dmr.nd.gov` URL the bytes came from. That path is the product; the map is how you
find a number to test it with.

Four things are **not** here, so do not go looking for them:

- **No forecasts.** No decline curves, no EUR, no type curve, no ML.
- **No dollars.** No economics, no NPV, no scenarios, no inventory.
- **No Permian, no Texas, no New Mexico.** North Dakota only.
- **No tunnel and no HTTPS.** LAN-only plain HTTP tonight — see §2.

Also absent by design: GOR and water cut (derived surfaces, never served as
targets), daily production, ownership, and the agent gateway.

## 2. How to reach it

```
http://glasswell.lab.rpx.sh:8000/#key=<GLASSWELL_OWNER_KEY>
```

The key rides in the **fragment**, after the `#`. A fragment is never sent to the server,
so it cannot reach uvicorn's access log or journald. `?key=` is refused with a `422` —
the query form was live long enough to write the old key into the journal, so that key was
rotated and the journal vacuumed.

Plain **HTTP on port 8000**, firewalled to `192.168.2.0/24`. There is no
certificate, no certificate warning, no HTTPS, no tunnel and no Access tonight —
that is a deliberate trade, and it is first in the morning queue (§7).

The key is 64 hex characters, generated on the VM and written only to
`/etc/glasswell/app.env` (`root:root`, mode 0600). It is in no log and no file in
this repository. Read it on the VM:

```bash
ssh root@glasswell.lab.rpx.sh 'sed -n "s/^GLASSWELL_OWNER_KEY=//p" /etc/glasswell/app.env'
```

Paste it into the `#key=` link once. The app stores it in `localStorage`, strips it
from the fragment, and plain `http://glasswell.lab.rpx.sh:8000/` works in that browser
from then on.

For the API steps in §5, put the key in a curl config file so it never reaches your
shell history or the process table:

```bash
CFG=$(mktemp); chmod 600 "$CFG"
ssh root@glasswell.lab.rpx.sh 'sed -n "s/^GLASSWELL_OWNER_KEY=/header = \"X-Glasswell-Key: /p" /etc/glasswell/app.env | sed "s/$/\"/"' > "$CFG"
curl -sS -K "$CFG" http://glasswell.lab.rpx.sh:8000/v1/health
# rm -f "$CFG" when you are done
```

## 3. The map and one well — about eight minutes

**Step 1 — open the keyed link.** Expect the Williston basin: several thousand
lateral centrelines on a dark canvas with a one-degree graticule, coloured by well
status, a status legend bottom-left, and a header line reading
`Glossary loaded: 50 highlightable surface forms.`
*There is no basemap.* No roads, no terrain, no satellite — the geometry and the
graticule are the whole reference, by design. It is not broken.
Screenshot: `01-map-initial.png`.

**Step 2 — zoom in.** Scroll to about z12 anywhere in the green mass. Laterals
thicken; **well points appear from z9** as circles at the surface location. Pan
east past roughly −100.5° and the canvas empties — that is the edge of the data,
not a failure.

**Step 3 — click a lateral.** The well card opens on the right. If you would rather
land on a known-good one, use the deep link:

```
http://glasswell.lab.rpx.sh:8000/?map=12.00/47.71074/-102.74821&well=3305310451
```

Expect **Mandaree 50-2008H**, API-10 `3305310451`, operator `EOG RESOURCES, INC.`,
status `active`, land unit `149N-94W-20`, spud `2025-01-05`, one lateral,
`lateral length 15,073.98 ft`. Note the URL: viewport and selection are in the
query string, so any state you reach is a link you can send.
Screenshots: `02-map-well-selected.png`, `03b-well-card-closeup.png`.

Other known-good wells: `3305310497`, `3305310490`, `3305310007`, `3305310453`.

**Step 4 — read the card's numbers.** Every figure carries a unit and a small
`⌾` handle beside it. That is the no-naked-numbers rule enforced in the browser: a
figure without a unit and a derivation handle throws in the test build rather than
rendering. `As of 2026-08-20 (requested latest)` is the report vintage you are
looking at.

**Step 5 — the production chart.** Three streams, six months (2025-10 → 2026-03),
oil and water on the left axis in bbl, gas on the right in mcf. Below the plot is
the **state strip**: one mark per month per stream, each one a button, so a gap in
the line is never ambiguous — reported, reported-zero, withheld and no-report are
four distinct marks, not one hole.
Screenshot: `08-production-chart.png`.

Under the chart you will see three warnings reading
`series_spans_derivations: 6 derivations contributed to this column`. That is
**correct and honest**: six monthly promotions each wrote part of that column, and
the envelope says so rather than pretending one job produced it.

**Step 6 — the whole point. Click the `⌾` beside `Oil (bbl)`.** The lineage drawer
opens on the far right. Expect, without scrolling or expanding anything:

- `depth 2 · 3 nodes · 1 terminal manifest · vintage 2026-08-20`
- a `canonical.promote` node naming the rules that shaped the number
  (`cr_nd_days_range_1`, `cr_nd_stream_vocab_1`, `cr_nd_units_1`,
  `cr_nd_volume_range_1`)
- a **MANIFEST** node with
  `source https://www.dmr.nd.gov/oilgas/mpr/2025_10.xlsx`,
  `fetched 2026-08-20T08:07:51+00:00`, and
  `sha256 a5cbbe40fe0e49b116e279079996c4ecfda6757450c6f43b14fff66bc160b7b5`
  (64 characters) · 3,247,051 bytes
- a `stage.parse` node showing the same manifest entering staging

That is the thesis: a number on a chart, two clicks, a checksum and a government
URL. One `/v1/explain` call, no expanding.
Screenshots: `07-explain-production-number.png`, `07b-explain-drawer-closeup.png`.

**Step 7 — do it from a different figure.** Click the `⌾` beside
`lateral length`. Same drawer, different chain: it terminates at
`OGD_Horizontals_Line.zip` from `gis.dmr.nd.gov`, 15,572,888 bytes, with its own
SHA-256. Two different numbers on one card, two different files.
Screenshot: `04b-lineage-drawer-closeup.png`.

**Step 8 — hover a highlighted term.** Terms with a dotted underline
(`API-10`, `Land unit`, `Compute CRS`, `Oil (bbl)`, …) pop a definition after a
moment. `expand` opens the long form. The highlighter runs over labels the API
itself names, so the vocabulary comes from the served glossary, not from the
frontend guessing.
Screenshot: `05-glossary-popover.png`.

## 4. What you should be able to break — about three minutes

- **A well that does not exist:** `?well=9999999999` → the card renders
  `Not found (not_found) · no well 9999999999 at this vintage`, not an empty panel.
  Screenshot: `09-well-not-found.png`.
- **No key at all:** open the app in a private window without `#key=`. The header
  says `The API needs the owner key: open this page once with #key=…` and the card
  shows `API key required (key_required)`. It refuses honestly instead of looking
  empty. Screenshot: `06-no-key-403.png`.
- **The key in the query string:** `?key=<GLASSWELL_OWNER_KEY>` → `422
  validation_failed` pointing at `/query/key`, on every path including `/`. A query
  string is written to the access log verbatim, so the API will not take a credential
  there at all.
- **A bad handle:** `?explain=drv_doesnotexist` → the drawer opens and reads
  `Lineage could not be resolved (lineage_unresolved) · last resolved nothing ·
  stopped because unknown_id`. A broken chain renders as a broken chain.
  Screenshot: `10-bad-handle.png`.
- **A path that is not `/`:** `http://glasswell.lab.rpx.sh:8000/wells/3305310451`
  **404s** — there is no SPA fallback tonight. Deep links use the query form
  (`?map=…&well=…&explain=…`).
- **A huge page:** `/v1/wells?limit=5000` → `422 validation_failed` pointing at
  `/query/limit` with `Input should be less than or equal to 1000`. The bound is
  stated, not silently applied.

## 5. The kitchen — about four minutes, from a terminal

The API is the same surface the UI uses. With `$CFG` from §2:

```bash
B=http://glasswell.lab.rpx.sh:8000
curl -sS -K "$CFG" "$B/v1/conformance" | python3 -m json.tool | head -40
curl -sS -K "$CFG" "$B/v1/quarantine/summary" | python3 -m json.tool
curl -sS -K "$CFG" "$B/v1/health" | python3 -m json.tool
curl -sS "$B/openapi.json" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["paths"]), "paths")'
```

- **`/v1/conformance`** — 14 rules, every one carrying a rationale and an evidence
  URL. If two sources were reconciled anywhere in the pipeline, the rule that did it
  is in this list. A mapping that exists only in code is the defect this endpoint
  exists to make visible.
- **`/v1/quarantine/summary`** — **292,394 rejected rows**, grouped:
  `stream_not_promoted` 263,786 · `unknown_vocab` 24,872 · `key_collision` 1,401 ·
  `out_of_range_date` 1,055 · `multi_wellbore_policy` 694 · `parse_error` 585 ·
  `duplicate_row` 1. A zero here would mean the checks were not running. Each row is
  kept with its payload and its reason code — nothing is silently dropped.
  `stream_not_promoted` is the dominant fact and it is a **decision, not a failure**:
  `GasSold` and `Flared` are dispositions of produced gas, enumerated in
  `lineage.nd_stream_map` with `promoted = false`, so conflict C7's claim is measured
  rather than asserted. Migration 007's reason vocabulary had no such code and every
  one of these rows read `unknown_vocab` until migration 011 admitted it and relabelled
  them — bounded by `rule_id = cr_nd_stream_vocab_1`, which is what proves the reason,
  and recorded as a `quarantine.relabelled` audit event. The remaining `unknown_vocab`
  are the GIS layer's `_VERT`/`_STK` segments, which carry no rule id (see gap 16).
  Note `multi_wellbore_policy` at 3.1 %, above the 2 % ND revisit trigger: that is a
  real signal to act on, not noise.
- **`/v1/health`** — four sources, all `current`, with the manifest count per source
  (six for the monthly production file, one per GIS layer).

## 6. Known gaps, stated plainly

1. **No TLS, no tunnel, no Access.** Plain HTTP, one static owner key, LAN only.
2. **Role separation is collapsed.** The `glasswell` login is a member of both the
   pipeline and the API group roles, so the API's connection is structurally capable
   of writing canonical rows. Real separation needs two login identities. Do not
   claim write-separation until it is split.
3. **martin auto-publishes `staging` and `canonical`**, so its catalogue on
   `127.0.0.1:3000` still lists relations that are not published layers. The
   `/v1/tiles` proxy now refuses everything outside `nd_laterals`, `nd_wells` and
   `nd_spacing_units` with a `404`, so "staging never serves" is a control on the one
   path a caller can reach. Making martin's own source list equal that allowlist
   (S-C) needs `infra/martin/config.yaml` adopted — morning-queue item 2.
4. **One `marts` grant is hand-applied**, not in a migration — exactly the drift
   migrations exist to prevent. Fold it into a migration before the next rebuild.
5. **Six months of production only** (2025-10 → 2026-03), one knowledge vintage per
   source. The full back-load is a loop of real fetches against a public regulator.
6. **No GOR, no water cut, no forecasts, no economics** — out of scope by design.
7. **Tiles are unsimplified.** The z7 laterals tile is ~2 MB. Fine on a LAN, wrong
   for anything with latency; zoom-dependent simplification is unbuilt.
8. **No connection pool** — one PostgreSQL connection per request.
9. **`marts.nd_well_card` is empty by design**; the card reads canonical directly.
10. **Glossary hover coverage is partial.** 44 terms / 50 surface forms are served
    and roughly a dozen highlight on a typical card; some terms are deliberately
    non-highlightable (`Wellbore`) so common words do not light up everywhere.
11. **Two small envelope honesty gaps:** `basin` is `null` on the well record, and
    `meta.source_freshness` is empty on `/v1/wells/{api10}` while populated on the
    production endpoint.
12. **~~GIS and marts derivations are stamped `env_cli`~~ — closed.** All three ingest
    paths call `glasswell.ingest.base.resolve_environment`, so every derivation from
    here on carries the lockfile hash the unit exports. The ten historical `env_cli`
    derivations keep their unpinned environment row: that is what the run recorded,
    and rewriting it would be falsification. Re-run the pipeline to repin them.
13. **The frontend is one 1.14 MB chunk.** No code splitting. The source map is no
    longer built or deployed (the project is proprietary and `StaticFiles` served it).
14. **No repeatable end-to-end smoke script in the repo.** Tonight's gate was a
    browser drive plus the 27 checks in `infra/verify.sh` on the VM; a committed
    `scripts/smoke.sh` covering the sixteen API assertions is unwritten.
15. **The VM's `/opt/glasswell/src` copy carries working files** (`PLAN.md`,
    `CLAUDE.md`) that are excluded from git. Harmless on a LAN box, worth tidying.
16. **The GIS `_VERT`/`_STK` segments still quarantine as `unknown_vocab`** — 24,875
    rows. They are not unknown either: a vertical hole is not a centreline, and the
    promotion measures them deliberately. Unlike the stream case there is no rule id
    on those rows, so nothing in the ledger proves the truer reason and the relabel
    would have been a guess. It needs a conformance rule, not a migration.
17. **Not a gap, so it does not surprise you:** no basemap (deliberate), `204` on a
    tile means healthy-but-empty, and the `series_spans_derivations` warning is
    correct.

Three defects were found by driving the real UI tonight and fixed before this file
was written: the map style declared `glyphs` as undefined and MapLibre therefore
refused the whole style (blank canvas, no layers, no tile requests); the tile URL
template was percent-encoded so every tile returned 422; and the chart clipped its
six-figure axis labels. Each has a regression test.

## 7. Morning queue, in priority order

1. **Cloudflare Tunnel + Access + a real certificate.** Needs your dashboard. This
   retires gap 1 and is the only thing standing between this and being reachable
   from outside the LAN.
2. **Split the login roles** to restore pipeline/API write separation (gap 2), and
   adopt `infra/martin/config.yaml` with `auto_publish: false` so martin's own
   source list equals the proxy allowlist (gap 3, S-C hardening condition 2) —
   never run both publishing mechanisms at once.
3. **Fold the hand-applied `marts` grant into a migration** (gap 4).
4. **Full production back-load** beyond six months, then re-check the quarantine
   shares.
5. **`scripts/smoke.sh`** (gap 14) so this walkthrough has a machine-checkable twin.
6. **IP carve-out review** — the top risk item, and the gate on anything public.

## 8. Three decisions waiting for you

None of them block the walkthrough above; all three were parked overnight rather
than being decided on your behalf.

1. **`work-output/reconciliation.md` §5 — the OWNER list**, five items each with a
   recommendation: whether basin transfer (E14) survives the cut order, the NDIC
   Premium $500/yr question, putting a date on the IP carve-out review, confirming
   `192.168.2.111` sits outside the router's DHCP pool, and the stale
   `freedom-zfs-snap` cron.
2. **`blueprint-v0.6-draft.md` §11 — the `[D]` table.** v0.4 is unrecoverable, so
   v0.6 restates the contract in one document; every item re-derived from the
   system's own logic rather than from a surviving anchor is tagged `[D]` and listed
   in §11 for one review pass. Nothing else in the draft needs your eye.
3. **`work-output/direction-log.md` — parked items**, plus the infra facts of
   record: the NDIC Premium question again from the data side, and the router/DHCP
   confirmation for `.111`.
