# SMOKE.md — the first-pass walkthrough

Fifteen minutes at a keyboard, in order. Everything below was executed against the
running instance on 2026-08-20; the screenshots named in each step are on the build
host under `work-output/smoke-shots/` (untracked, not in git).

Every figure here was re-read from the deployed instance after migrations 014-019 and the
re-derivation on 2026-08-20, so this is a dated walkthrough rather than the current-state
ledger. `scripts/smoke.sh` is the machine-checkable twin; [`STATUS.md`](STATUS.md) records
what has landed since.

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
- **No allocation, and no lease-level Texas production.** Texas wells and wellbore
  identity are on the map with no production behind them. New Mexico has both: a well
  header with a surface point, and production filed per completion pool. Nothing rolls
  a New Mexico pool series up to the well, so its well-level series is absent rather
  than zero and the card says so (`cr_nm_wcproduction_pool_rollup_1`). The allocation
  work that would make Texas comparable is not built.
- **No tunnel and no Access.** HTTPS is up on the LAN name (DIR-13); reaching it from
  outside the LAN is not — see §2.

Also absent by design: GOR and water cut (derived surfaces, never served as
targets), daily production, ownership, and the agent gateway.

## 2. How to reach it

```
https://glasswell.lab.rpx.sh/
```

**Log in with a username and password.** The app shows a login panel on first load; there is
no key to paste and no `#key=` link any more. Sessions are server-side records: logging out
kills the cookie's row, so a copy taken beforehand is dead. The cookie is `__Host-` prefixed,
`HttpOnly`, `Secure` and `SameSite=Lax`, and it is the only credential a browser holds.

Accounts are created by the owner. There is no self-registration, no password-reset email and
no "forgot password" link — recovery is `glasswell-owner-reset` over ssh (§6). The first
account is created once, on the host:

```bash
ssh root@glasswell.lab.rpx.sh
# runuser, because the DSN uses peer auth: as root the connection arrives as the role
# `root`, which does not exist, and it fails before the password prompt.
runuser -u glasswell -- /opt/glasswell/venv/bin/glasswell-owner-bootstrap \
    --dsn 'postgresql:///glasswell?host=/var/run/postgresql' --username <you>
# the password is read from stdin: type it, then Ctrl-D. It is never echoed, never in argv,
# and never in the environment.
```

**HTTPS, no port, no certificate warning.** Caddy terminates TLS with a Let's Encrypt
host certificate obtained over the DNS-01 challenge — the name resolves to `192.168.2.111`,
which no ACME server can reach, and DNS-01 does not care. It reverse-proxies uvicorn over
`/run/glasswell/api.sock`; the API has no TCP port at all, and `http://` on `:80` and the old
`:8000` both redirect.
The firewall is unchanged in spirit: `443` and `80` from `192.168.2.0/24` and nothing else.

**The API key is still the machine path.** A session is for a browser; a key is for `curl`
and for the deploy gate. Keys are unchanged, and `?key=` is still refused with a `422` — as
are `?password=` and `?token=`, because a query string reaches the access log verbatim. For
the API steps in §5, put the key in a curl config file so it never reaches your shell history
or the process table:

```bash
CFG=$(mktemp); chmod 600 "$CFG"
ssh root@glasswell.lab.rpx.sh 'sed -n "s/^GLASSWELL_OWNER_KEY=/header = \"X-Glasswell-Key: /p" /etc/glasswell/app.env | sed "s/$/\"/"' > "$CFG"
curl -sS -K "$CFG" https://glasswell.lab.rpx.sh/v1/health
# rm -f "$CFG" when you are done
```

One thing the static owner key no longer does: it is **refused on the public listener**. It
has no expiry, no rotation path and no revocation row, so after this release it is a LAN and
deploy-gate credential only. Issued `api_keys` rows carry an expiry and a revocation row and
still work from anywhere.

## 3. The map and one well — about eight minutes

**Step 1 — open the app and log in.** Expect the Williston basin: several thousand well
points on a dark canvas with a one-degree graticule, coloured by well status, a
status legend bottom-left, and a header line reading
`Glossary loaded: 50 highlightable surface forms.`
Laterals are a layer now, not the default: open **Layers** and switch **Laterals**
on. The row stays dark and says "Visible at zoom 8 and above" until Step 2.
*There is no basemap.* No roads, no terrain, no satellite — the geometry and the
graticule are the whole reference, by design. It is not broken.
Screenshot: `01-map-initial.png`.

**Step 2 — zoom in.** Scroll to about z12 anywhere in the green mass. Laterals
appear at z8 and thicken from there; **well points appear from z9** as circles at
the surface location. Pan
east past roughly −100.5° and the canvas empties — that is the edge of the data,
not a failure.

**Step 3 — click a lateral.** The well card opens on the right. If you would rather
land on a known-good one, use the deep link:

```
https://glasswell.lab.rpx.sh/?map=12.00/47.71074/-102.74821&well=3305310451
```

Expect **Mandaree 50-2008H**, API-10 `3305310451`, operator `EOG RESOURCES, INC.`,
status `active`, land unit `149N-94W-20`, spud `2025-01-05`, one lateral,
`lateral length 15,065.44 ft` — the geodesic figure migration 014 introduced, 8.54 ft
shorter than the planar one this file quoted before the re-derivation. Note the URL: viewport and selection are in the
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
- **Not logged in:** open the app in a private window. The login panel renders and every
  data route answers `403`. It refuses honestly instead of looking empty.
- **A wrong password, and a username that does not exist:** both answer the *same*
  `403 unauthenticated` with no `detail`, and take the same time to do it. That is
  deliberate — a difference either way tells a stranger which accounts exist.
- **A credential in the query string:** `?key=`, `?password=` or `?token=` → `422
  validation_failed` pointing at `/query/<name>`, on every path including `/`. A query
  string is written to the access log verbatim, so the API will not take a credential
  there at all.
- **A stale cookie after logging out elsewhere:** `403`. Sessions are server-side rows,
  not self-describing tokens, so revocation is immediate rather than eventual.
- **A bad handle:** `?explain=drv_doesnotexist` → the drawer opens and reads
  `Lineage could not be resolved (lineage_unresolved) · last resolved nothing ·
  stopped because unknown_id`. A broken chain renders as a broken chain.
  Screenshot: `10-bad-handle.png`.
- **A path that is not `/`:** `https://glasswell.lab.rpx.sh/wells/3305310451`
  **404s** — there is no SPA fallback tonight. Deep links use the query form
  (`?map=…&well=…&explain=…`).
- **A huge page:** `/v1/wells?limit=5000` → `422 validation_failed` pointing at
  `/query/limit` with `Input should be less than or equal to 1000`. The bound is
  stated, not silently applied.

## 5. The kitchen — about four minutes, from a terminal

The API is the same surface the UI uses. With `$CFG` from §2:

```bash
B=https://glasswell.lab.rpx.sh
curl -sS -K "$CFG" "$B/v1/conformance" | python3 -m json.tool | head -40
curl -sS -K "$CFG" "$B/v1/quarantine/summary" | python3 -m json.tool
curl -sS -K "$CFG" "$B/v1/health" | python3 -m json.tool
curl -sS "$B/openapi.json" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["paths"]), "paths")'
```

- **`/v1/conformance`** — 17 rules, every one carrying a rationale and an evidence
  URL. If two sources were reconciled anywhere in the pipeline, the rule that did it
  is in this list. A mapping that exists only in code is the defect this endpoint
  exists to make visible.
- **`/v1/quarantine/summary`** — **292,972 rows in the ledger**, grouped:
  `stream_not_promoted` 263,786 · `segment_not_promoted` 25,449 · `key_collision` 1,401 ·
  `confidential_withheld` 1,055 · `multi_wellbore_policy` 695 · `schema_mismatch` 583 ·
  `parse_error` 2 · `duplicate_row` 1. A zero here would mean the checks were not running.
  Each row is kept with its payload and its reason code — nothing is silently dropped.
  **"Rejected" is the wrong word for almost all of it and this file used to use it.**
  98.7 % of the ledger is two deliberate non-promotions of rows that were read correctly:
  `stream_not_promoted` (`GasSold`/`Flared`, dispositions of gas that did promote) and
  `segment_not_promoted` (vertical and sidetrack traces that are not a producing
  centreline). True source-row rejection is **1,057 of 132,950 MPR rows — 0.79 %**, not the
  ~43 % the old framing implied (fp-audit A5-F13, off by ~54×).
  `stream_not_promoted` is the dominant fact and it is a **decision, not a failure**:
  `GasSold` and `Flared` are dispositions of produced gas, enumerated in
  `lineage.nd_stream_map` with `promoted = false`, so conflict C7's claim is measured
  rather than asserted. Migration 007's reason vocabulary had no such code and every
  one of these rows read `unknown_vocab` until migration 011 admitted it and relabelled
  them — bounded by `rule_id = cr_nd_stream_vocab_1`, which is what proves the reason,
  and recorded as a `quarantine.relabelled` audit event. The GIS layer's `_VERT`/`_STK`
  segments were the last `unknown_vocab` rows; migration 016 gave them a vocabulary of
  their own and there are now **zero** (gap 16, closed).
  Note `multi_wellbore_policy` at 3.1 %, above the 2 % ND revisit trigger: that is a
  real signal to act on, not noise.
- **`/v1/health`** — every registered source with its manifest count (six for the monthly
  production file, one per GIS layer). A source that has been fetched reads `current`; one
  that is registered and not yet fetched reads `pending` and is named in `pending_sources`,
  which is where the NM sources sit until the promotion deploy. `degraded_sources` must be
  empty: that list is for data that has gone stale, and a source on it is a served lie.

### The control is pinned, and the pin is what is served

```bash
PUB=$(curl -sS -K "$CFG" "$B/v1/modeling/publications" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"][0]["publication_id"])')
curl -sS -K "$CFG" "$B/v1/modeling/publications/$PUB" | python3 -m json.tool | head -60
SUBJECT=$(curl -sS -K "$CFG" "$B/v1/type-curves?limit=1" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["series"]["api10"][0])')
curl -sS -K "$CFG" "$B/v1/wells/$SUBJECT/type-curve?explain=true&explain_depth=8" \
  | python3 -c 'import json,sys; c=json.load(sys.stdin)["_explain"]; v=next(iter(c.values())); print({"truncated": v["truncated"], "depth": v["depth"], "terminals": len(v["terminals"])})'
```

- **`/v1/modeling/publications`** — the accepted P3 receipt, its three semantic versions,
  its split set, and the peer-ladder support distribution read from the artifact's own
  coverage document. No filesystem path is served; `artifact_sha256` addresses the same
  bytes without disclosing where they live.
- **The chain must read `truncated: false` and `depth: 7`.** `MAX_DEPTH` is 8, so 7 is the
  last passing value: one more hop in a future `typecurve.build` turns every served
  type-curve handle truncated at once. **CI cannot see this** — the contract fixture
  registers a single manifest input, so its chain is two levels deep by construction and
  the same assertion holds there whatever the real build gains. Record the number here at
  each deploy.
- **Time both explain paths.** Budget: p95 under 2 s at `explain_depth=8` (twelve handles
  over a chain roughly nine hundred derivations wide) and under 300 ms at the default
  depth 3. Over budget is a register item, not a new norm.
- **The negative check.** With `GLASSWELL_MODEL_ROOT` unset the type-curve routes must
  answer **409 `unregistered_artifact`** — not 200, and not 500. `DEFAULT_MODEL_ROOT` is
  relative, so an unset variable makes every absolute locator fail containment. That is
  the fail-closed behaviour, and it is why the variable is in `app.env.example`.
- **A `control_unavailable` subject must answer 200**, not 404, with `outcome` reading
  `control_unavailable`, its reasons named, and the figure slots present and null.
  `curl "$B/v1/type-curves?fallback_level=control_unavailable&limit=1"` finds one.
- **Re-publication is a restatement event.** A second accepted publication is announced by
  a `publication_superseded` warning on every affected response; the prior publication stays
  served under its own id and is reachable with `?publication=`. Nothing is edited.

## 6. Known gaps, stated plainly

- **Global concurrency is not capped.** §3.6.8 asks for 32 concurrent requests and 5
  concurrent write jobs. The limiter is a fixed-window counter, which counts requests per
  window and not simultaneous in-flight work, so those two are recorded as unmet rather
  than asserted by a test that measures nothing. The four per-principal buckets — 120/min
  interactive, 60 service, 600 tiles, 30 anonymous — are applied.
- **`/basemap/*` is deliberately anonymous.** It is public OpenStreetMap-derived bytes
  containing no glasswell layer, served directly by Caddy with `sendfile`. Routing it back
  through uvicorn to authenticate costs the ~40 ms Nagle penalty the Caddyfile documents.
  A test asserts the archive's layer set contains no glasswell mart layer, so the carve-out
  cannot silently widen.
- **Account recovery is ssh, not email.** `runuser -u glasswell -- glasswell-owner-reset --username <name>` on the
  host, password on stdin. It clears the lockout, re-enables a disabled account and revokes
  every session it holds. There is no reset link and no security questions, which is what
  keeps "not multi-user" true.
- **`GLASSWELL_ALLOW_ANON=1` resolves a caller to the viewer role** — read-only, never
  owner scope. It is a development and kiosk break-glass, and with `GLASSWELL_PUBLIC=1` the
  API refuses to start rather than serving the internet anonymously. This deployment does
  not set it.

1. **~~No TLS~~ — closed; no tunnel, no Access.** HTTPS on `glasswell.lab.rpx.sh` with a
   Let's Encrypt host certificate, renewed by Caddy over DNS-01, and `verify.sh` fails
   when under 20 days remain (DIR-13). What is still open is reachability: one static
   owner key, LAN only, no tunnel and no Access in front of it.
2. **Role separation is collapsed.** The `glasswell` login is a member of both the
   pipeline and the API group roles, so the API's connection is structurally capable
   of writing canonical rows. Real separation needs two login identities. Do not
   claim write-separation until it is split.
3. **~~martin auto-publishes `staging` and `canonical`~~ — closed.** The config is
   adopted: `127.0.0.1:3000/catalog` now lists exactly `nd_laterals`, `nd_wells` and
   `nd_spacing_units`, where it listed eleven sources with three `staging` relations
   among them. "Staging never serves" is held by three controls rather than one — the
   `/v1/tiles` proxy allowlist, `auto_publish: false`, and the PG role `martin`, which
   holds select on three `marts.tile_*` views and cannot read the `staging` schema at
   all. The published sources are the tile *functions*, which read those same views.
4. **~~One `marts` grant is hand-applied~~ — closed.** `create on schema marts` is held
   by a migration now (DR-21), so a database built from migrations alone survives its
   first `refresh_for`. The deployed host already had the privilege; the migration is what
   makes the next one reproducible.
5. **Six months of production only** (2025-10 → 2026-03), one knowledge vintage per
   source. The full back-load is a loop of real fetches against a public regulator.
6. **No GOR, no water cut, no forecasts, no economics** — out of scope by design.
7. **~~Tiles are unsimplified~~ — closed.** The laterals layer is thinned at four MVT
   units of the tile being built, so the discarded detail stays a quarter of a rendered
   pixel at any zoom. The z7 tile is 1,777,155 bytes uncompressed and 582,220 on the
   wire, against ~2 MB and no compression before; a repeat fetch is a `304` and no body.
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
14. **~~No repeatable end-to-end smoke script in the repo~~ — closed.**
    `scripts/smoke.sh` runs twenty-five read-only API assertions against a deployed
    instance — including the per-well cumulative's coverage identity, the vintage
    cohorts' served key rule and the promoted completion design — and `tests/e2e/`
    runs thirteen more through a real browser
    (`make test-e2e`). Together with `infra/verify.sh` they are the regression net this
    walkthrough used to be.
15. **~~The VM's `/opt/glasswell/src` copy carries working files~~ — closed.**
    `PLAN.md`, `CLAUDE.md`, `.rdf/`, `work-output/` and the eight `docs/product-*.md`
    deep-dives (IP carve-out material) were rsync-era residue and are removed; the deploy
    is `git archive HEAD | ssh tar -x` and cannot recreate them. `verify.sh` asserts it.
16. **~~The GIS `_VERT`/`_STK` segments quarantine as `unknown_vocab`~~ — closed.**
    Migration 016 gave them `cr_nd_segment_vocab_1` and the reason code
    `segment_not_promoted`; `unknown_vocab` is 0 and 25,449 rows now say what they are.
    The relabel was not a guess after all: every row carried the segment its own parser
    had read (fp-audit A5-F6).
17. **Not a gap, so it does not surprise you:** `204` on a tile means
    healthy-but-empty, and the `series_spans_derivations` warning is correct.
18. **The S-E re-promotion is armed, not yet run.** The correction that gives 78
    multi-pool wells their filed volumes back appends a new knowledge vintage, and the
    runner refuses to open one that already answers — `report_vintage` is a calendar day
    and 2026-08-20 is taken. `glasswell-repromote.timer` runs it once at
    **00:30 UTC on 2026-08-21**, logging to `/var/log/glasswell/repromote-2026-08-21.log`,
    which also records the reconciliation counts. Until it does, well `3305302532` serves
    `null` with a `multi_pool_pending` warning, `canonical.production_monthly` holds
    394,278 rows and the collision ledger holds 1,401 open rows. Afterwards: 398,403 rows,
    0 open collisions, and 17,247 bbl of oil over six months on that well.

Three defects were found by driving the real UI tonight and fixed before this file
was written: the map style declared `glyphs` as undefined and MapLibre therefore
refused the whole style (blank canvas, no layers, no tile requests); the tile URL
template was percent-encoded so every tile returned 422; and the chart clipped its
six-figure axis labels. Each has a regression test.

## 7. Follow-up queue recorded with the walkthrough

This was the queue on 2026-08-20. Closed items stay visible as history; current priorities
live in [`STATUS.md`](STATUS.md).

1. **Cloudflare Tunnel + Access.** Needs your dashboard. ~~A real certificate~~ is done
   (DIR-13): Caddy fronts the LAN name with a Let's Encrypt certificate and uvicorn is
   loopback-only. The tunnel points at the same origin and is the only thing standing
   between this and being reachable from outside the LAN.
2. **Split the login roles** to restore pipeline/API write separation (gap 2).
   ~~Adopt `infra/martin/config.yaml`~~ (gap 3) — done; the catalogue is the allowlist.
   Never run both publishing mechanisms at once: the config publishes the functions, so
   a `tables:` block naming the views they read would collide on the same ids.
3. ~~**Fold the hand-applied `marts` grant into a migration**~~ (gap 4) — done.
4. ~~**Full production back-load** beyond six months~~ — done: all 125 back-load
   workbooks landed, producing 131 distinct canonical months from 2015-05-01.
5. ~~**`scripts/smoke.sh`**~~ (gap 14) — done, with a browser tier beside it.
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

### The New Mexico cadences, proposed rather than scheduled

Two recurring-run questions the New Mexico gate raises and does not answer, both with the
numbers now measured:

- **A recurring OCD FTP promotion.** Not implemented and not recommended without a decision.
  All nine `nm_ocd_*` sources are registered `'Owner-triggered; no recurring timer'`, and the
  FTP pull is a once-ever event by contract. The measured cost of a full re-run is **89 minutes
  of wall clock and 9.9 GB of table growth** for the production spine, plus ~35–40 minutes of
  staging; `glasswell-ingest.service` bounds a run at `TimeoutStartSec=3600`, so a recurring
  promotion does not fit inside it and would need its own unit.
- **The OCD public wells layer (`nm_ocd_wells_gis`).** Upstream describes it as updated daily,
  and the walk is ~141,916 features at 6,000 per page — about 24 pages at the standard 0.25 s
  spacing, so a few minutes. It is registered owner-triggered like its FTP siblings until a
  cadence is chosen. **Recommended: weekly**, which is well inside the layer's own refresh rate
  and cheap enough to be unremarkable; daily buys freshness the frozen FTP archive beside it
  cannot match anyway.

The ingest unit's own bounds were re-checked against these numbers rather than assumed. What it
gained is one mart refresh — `glasswell.marts.nm_wells`, a rebuild of a point projection — so
`TimeoutStartSec=3600` and `MemoryMax=6G` are unchanged. The measured pressure on that unit is
not the new mart: it is the `canonical.production_monthly_latest` scan the land-metrics refresh
runs, which the gates measure on the host as G7-3.
