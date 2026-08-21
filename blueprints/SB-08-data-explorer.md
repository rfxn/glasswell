# SB-08 — Data Explorer & API Guide

**Sub-blueprint against `blueprint-v0.6-draft.md` (v0.6-rc2). Status: rev 2, post-challenge.**
Owner: Ryan MacDonald. Component: a new UI surface under **C13/C14**, consuming **C12**
(SB-04) and **C25** (glossary), reusing SB-05's component system verbatim.

## Revision log

**rev 2 (2026-08-20)** — applies `work-output/sb08-challenge.md`: GO-WITH-FIXES, 4 blockers,
10 majors, 10 minors. **Nothing is refuted.** Every blocker and major is adopted; all ten
minors are applied. The reviewer's evidence note holds in both directions — SB-08 rev 1's
claims about *shipped code* survived spot-verification, and every failure was a claim about
another document's state or about machinery that is specified but unbuilt. That is the
lesson of this revision and it is recorded here rather than absorbed: **a `[V]` tag on a
file I read is worth what it says; a citation of another sub-blueprint's specification is
not evidence that the thing exists.** rev 2 adds an evidence class for exactly that.

| Finding | Resolution | Lands in |
|---|---|---|
| **B1** every `/explore/*` route 404s (`StaticFiles(html=True)` has no SPA fallback; probed) | Adopt `?view=` routing for P-A — it lands entirely in the seam commit with zero cross-track dependency. Path routes become a URL migration behind new amendment **A-7**, owned, sized and registered. Refutation attempted and failed: the fallback is not one line (§7.1 A-7) | §2.1, §7.1 A-7 |
| **B2** P-A ships zero figure cells | Adopt the controller's ruling: `get_well_production` + `get_well_production_pools` move into P-A and **A-4 is pulled forward**. W1 becomes deliverable at P-A. **A-3** stays P-B's gate for the cross-well grid and the rail carries it as a stated Class C gap | §2.4, §8.1 |
| **B3** WHY and SO are unsourceable — 0/78 parameters carry any `x-glasswell-*` extension (re-measured) | Adopt new amendment **A-8** `x-glasswell-semantics` on operations. SO is kept, not dropped: it is per-operation while the term is shared, so the reviewer is right that this was a modelling error rather than a missing column | §4.3, §7.1 A-8 |
| **B4** ~110 column bindings needed, 19 exist; the allowlist file, `labels.ts` and the extractor do not exist | Adopt option (b): **counted-unbound treatment** with a per-dataset coverage percentage and a phase ratchet, **plus** a funded authoring line — obligation **O-6**, sized, owned, with the measured baseline (201 properties across the explorer's schemas, 19 bound) | §3.2, §6.1, §7.1 O-6 |
| **M1** SB-05 §3.10's table system does not exist; no `@tanstack/*` installed | Own it, and add **no runtime dependency**: a ~250-line windowed grid in `explore/grid/`. The response is already server-paginated, so the case for a headless table library is weak here. SB-05 §3.10 is raised as an erratum | §3.2, §7.3 |
| **M2** `extra: Record<string, string>` collapses repeated params; `map=` always emitted | Seam commit makes `extra` multi-valued and `map=` conditional. Stated as what it is: **a new mechanism in a frozen file**, in the seam's scope, with its own tests | §8.4 |
| **M3** merge-order rationale false | Re-derived with fresher evidence than the reviewer had — **the train landed mid-authoring**. Seam lands immediately; phases resequenced | §8.4 |
| **M4** `x-glasswell-dataset` cannot express 3/11 datasets and carries no column config | Extend **A-1**: `row_id[]`, `collection_pointer`, `columns{}`. CI-checks every pointer resolves | §2.3, §7.1 A-1 |
| **M5** runner's rate-limit premise false; permit admits non-JSON operations; no response metadata | All three fixed: debounce is named as the only control **and as advisory**; JSON media type joins the permit with a fifth refusal test; `client.ts` response metadata joins the seam scope explicitly | §4.4, §4.5, §8.4 |
| **M6** "failing walkthrough = failing build" false — no e2e job in CI, e2e runs against the live instance | P-C requires a **seeded-instance e2e job (Track O)** and every walkthrough step pins an `as_of` vintage | §5.3, §8.3, §9 |
| **M7** SB-05 §13 cut in-app tours; §5.3 reinstated without argument | Argued in §0.4 against the cut item's actual text | §0.4 |
| **M8** A-3 says `granularity`; rc2 ratified `granularity_filter` | Renamed; SB-04 §4.2 needs the same fix and it is raised as an erratum | §7.1 A-3, §7.3 |
| **M9** sizing counts UI only | Session band on **every** §7.1 row; critical-path total published; P-A re-baselined against SB-05 §9's own optimism factor | §7.1, §8 |
| **M10** ESLint does not exist in the repo | Replaced with a vitest/node source scan. No new toolchain | §2.3, §9 |
| **m1–m10** | All applied. m5 (`anyOf` unwrap) and m7 (dynamic import) treated as load-bearing and given tests | §3.1, §2.6, §3.5, §3.6, §6.1, §7.1, §8.4 |

**rev 3 (2026-08-21)** — surgical. `work-output/plan-explorer-pa-challenge.md` ratified the
P-A plan's three entry-gated spec deltas against rev 2; they land here rather than inside an
implementation commit, because a spec resolved in the code it governs is not a spec.

| Delta | Resolution | Lands in |
|---|---|---|
| **G-1** premise holds; rev 2's `row_id[]` cannot address the production endpoints (parallel aligned arrays, and `/pool_id` does not resolve — the property is `well_completion_pool` **[V]**) | A-1 gains `series_pointer`, `row_projection{axis,columns,suffixes}` and `anchors[]`, **plus the two rules the challenge required to make it complete**: pointers inside `row_projection` are relative to `series_pointer`, and the axis column is exempt from suffix expansion | §2.3, §2.4 |
| **G-2** holds; free | A-8's inner member is **named `x-glasswell-glossary`**, so the existing recursive R9 collector picks it up with no collector change. Rev 2's "free R9 coverage" becomes true by construction | §4.3 |
| **G-3** premise holds; **rev 2's resolution was arithmetically unsatisfiable** — three ordered slots needed below `--gw-z-drawer: 12`, one integer available above `--gw-z-panel: 10` **[V]** | Re-ruled: **named slots aliasing the global ladder plus declared local stacking contexts**, not a private explorer ladder. Pane and rail take `--gw-z-panel`; popovers take `--gw-z-rail-pop`; the sticky grid header takes a local context. The test asserts no new global rung | §2.5 |

Folded in the same pass: **O-6's denominator is ~87–90** — the plan initially carried 55,
which undercounted the seven datasets falling back to their full schema, and was corrected
to §7.1's figure; and **all eleven P-A datasets now declare explicit 5–7-column defaults**,
because A-1's column config is the denominator of §3.2's binding ratchet and is therefore a
phase gate rather than presentation.

**rev 1 (2026-08-20)** — initial draft.

**Evidence classes, added at rev 2.** rev 1 used one tag for two very different claims.
Rev 2 splits them, and every claim about another document's *specification* now says whether
the thing it specifies exists:

| Tag | Meaning |
|---|---|
| **[V]** | Verified — read from a file in this repo at the cited path and line |
| **[S]** | **Specified but unbuilt** — a sibling sub-blueprint requires it; no implementation was found. Treated as a dependency with an owner and a size, never as a given |

This document specifies a second top-level surface alongside the map: a **data explorer**
whose every view is paired with a **contextual API guide**. It is Mandate B's *understand*
half, built as a product rather than as documentation.

**The pressure test is Mandate B's second sentence** (`v0.6 §1.1`): *the system itself must
teach.* `work-output/ux-deep-dive.md` §3 scores the two halves of that mandate separately —
**trace 7/10, understand 3/10** — and names the cause: *"the receipt is world-class. The
reading of the receipt is not."* Every decision below is answerable to the understand half.

**Citation convention.** `v0.6 §N` = `blueprint-v0.6-draft.md` section N · `SB-0n §N` =
sibling sub-blueprint · `DIR-n` = `work-output/direction-log.md`. **Section anchors, not line
anchors:** SB-04 and SB-05 cite the blueprint as `bp:N`, and those line numbers no longer
resolve against v0.6-rc2 (spot-checked 2026-08-20 — `bp:99` lands on a heading, `bp:262` on
R3 **[V]**). SB-08 cites sections so its citations survive the next amendment set; the
mismatch in the siblings is raised as a housekeeping item in §11. Evidence tags inherited
from SB-05/SB-06, plus **[S]** added at rev 2:

| Tag | Meaning |
|---|---|
| **[V]** | Verified — read from a file in this repo at the cited path and line |
| **[S]** | Specified but unbuilt — a sibling requires it; no implementation found. A dependency with an owner and a size, never a given |
| **[I]** | Inferred — conclusion from verified facts, reasoning stated inline |
| **[A]** | Assumed — unmeasured estimate; must be measured before it is relied on |

Every **[A]** touching a size or a budget becomes a measurement task in §8. Every **[S]**
gets a row in §7.1 with an owner and a session band, or it is not depended on.

**The `[S]` inventory, measured 2026-08-20.** Everything SB-08 depends on that a sibling
specifies and no code provides: `@tanstack/table-core` + `@tanstack/virtual-core`
(SB-05 §3.10 — `web/package.json` runtime deps are `@protomaps/basemaps`, `maplibre-gl`,
`pmtiles`, `uplot`, and nothing else **[V]**); ESLint and the three project lint rules
(SB-05 §1.1, §5.7 — no config file, no dependency, no `lint` script **[V]**); `label()`,
`ui/labels.json` and the Vite extractor (SB-05 §5.7 **[V]**);
`ui/glossary-allowlist.yml` (SB-05 §5.7 **[V]**); `ui/figure-manifest.json` and the
`stranger` CI job (SB-04 §7.4 **[V]**); `GET /v1/notebook` (SB-04 §4.12 **[V]**); a
rate limiter (`errors.py:137` declares `rate_limited` with `emitted=False` **[V]**); a
seeded-instance e2e CI job (`.github/workflows/` has `python`, `web`, `shell`,
`collateral` **[V]**). Rev 1 cited five of these as though they were infrastructure.

---

## 0. Scope, obligations, and the boundary

### 0.1 What SB-08 owns

| Owns | Does not own |
|---|---|
| The `/explore` surface: routes, layout, tab model, dataset catalogue rendering | Any endpoint's implementation or response shape (SB-04, SB-07) |
| The result grid, facet bar, row detail, cursor surface, inline visualisation | The data those surfaces render (SB-01, SB-02, SB-03) |
| The API guide pane: request rendering, parameter annotation, envelope anatomy, problem curriculum, the in-page runner and its ruling | The OpenAPI document's content (SB-04 §7), the error registry (SB-04 §2.4) |
| The educational layer: dataset intros, concept pages, walkthroughs — **as consumed data** | The prose rows themselves and the notebook endpoints (SB-01 rows, SB-04 §4.12) |
| `web/src/explore/**` in full, plus `<gw-count>` | `<gw-figure>`, `<gw-term>`, the drawer, the chart module, the map — all read-only imports from SB-05's tree |
| The explorer's additions to the R6 walker, and the exemption-binding CI check | The walker itself (`glasswell.lineage.ci`, SB-07 §10) |
| Contract deltas raised against SB-04 (§7) | Ratifying them — that is SB-00's, and SB-04 owns the surface |

### 0.2 Requirements this SB satisfies

| Requirement | Source | Satisfied in |
|---|---|---|
| **Mandate B** — the system must teach; vocabulary obligation | `v0.6 §1.1` | §1, §5, §6 |
| **S1** a stranger with the OpenAPI doc and a guest key reproduces every number | `v0.6 §2.4 S1` | §4.2, §4.5, §3.6 |
| **S5** the agent answers via public tools, every figure traceable | `v0.6 §2.4 S5` | §4.3 — the pane and the agent read one document |
| **S9** any UI number → raw manifest in ≤3 interactions and one `/explain` | `v0.6 §2.4 S9` | §3.2, §5.3 W1 (the budget is not spent again) |
| **S11** conformance registry served; every cross-source number cites its rules | `v0.6 §2.4 S11` | §2.4 dataset `conformance`, §5.3 W3 |
| **S13** every surfaced term resolves through `/v1/glossary` | `v0.6 §2.4 S13` | §3.2, §6.1 |
| **S14** as-of reproducibility | `v0.6 §2.4 S14` | §3.1, §5.3 W2 |
| **R5** estimates are labelled | `v0.6 §3.3 R5` | §3.2, §6.1 |
| **R6** derivation coverage, mechanically checked | `v0.6 §3.3 R6` | §6.1, §6.2, §6.3 |
| **R8** conformance as data | `v0.6 §3.3 R8` | §2.4, §5.2 C-c |
| **R9** glossary coverage | `v0.6 §3.3 R9` | §3.2, §6.1 |
| **U9** discover the entire API and answer without human help | `v0.6 §6 U9` | §4 |
| **U10, U12, U21, U22** auditor and learner stories | `v0.6 §6 U10`, `v0.6 §6 U12`, `v0.6 §6 U21`, `v0.6 §6 U22` | §2.4, §5 |
| **E15** learning instrument — findings memos with live data links | `v0.6 §5 E15` | §5.1 (the same store, extended) |
| **E18** glossary-as-data, never hand-tagged | `v0.6 §5 E18` | §3.2 — the authoritative path used at scale |
| **DIR-1** survives a Novi PM and a DS reviewer | direction log | throughout; §10 |
| **DIR-2** bitemporality taught in place | direction log | §4.3, §5.2 C-b, §5.3 W2 |
| **DIR-8** glossary is data; one popover; auto-highlighted | direction log | §3.2, §5.4 |
| **DIR-10** TDD; tests with or before implementation | direction log | §9 |
| **DIR-11** visual QA gate, reviewer-judged, ≥3 breakpoints | direction log | §8, per phase |

### 0.3 Contracts consumed verbatim — SB-08 invents nothing

1. **SB-04 §4** — the endpoint catalog. The explorer calls operations that exist in the
   served `/openapi.json` and nothing else. Where the explorer needs something the surface
   lacks, that is a **spec finding routed as an additive SB-04 amendment (§7)**, never a
   client-side workaround, never a second data path.
2. **SB-04 §2.2** — the envelope. `data` / `meta` / `links`, figure objects with `d`,
   `_lineage` / `_units` / `_basis` sidecars. The explorer parses it through the existing
   seam (`web/src/api/envelope.ts:89` `derivationFor`, `:54` `labelFor`, `:103` `sidecarFor`)
   **[V]** and adds no parser.
3. **SB-04 §2.3** — cursor pagination. The explorer *displays* the cursor; it never
   synthesises one, and it never invents a page number (SB-05 §3.10 forbids it).
4. **SB-04 §2.4** — the frozen error registry. The problem curriculum (§4.6) is a rendering
   of that registry, not a second list.
5. **SB-05 §3.1** — `<gw-figure>` is the only component that renders a number.
   `web/src/card/gw-figure.ts:10` **[V]**.
6. **SB-05 §5** — one term index, one scanner, one popover.
   `web/src/glossary/index.ts:28,59,85` and `store.ts:28,41,52` **[V]**.
7. **SB-05 §4** — the lineage drawer is the only chain renderer.
   `web/src/lineage/drawer.ts:42` **[V]**.
8. **SB-07 §9.1** — figure/sidecar carriage is the only handle mechanism.
9. **SB-07 §10** — one walker. SB-08 extends its *coverage*, and writes no second walker.

### 0.4 What this is not — the cut item is not being reinstated

SB-07 §14 item 5 cut *"any lineage UI beyond the drawer"* and left the question open:
*"a lineage explorer is SB-05's call, later, if ever"* **[V]**. SB-05 §13 then cut *"a
lineage explorer beyond the drawer"* as gold-plating **[V]**. SB-08 is the call being made,
and it is made **against** reinstating that item:

- **SB-08 is a dataset explorer, not a lineage explorer.** It browses served collections.
  It renders no graph, no node-link canvas, no derivation-tree navigator.
- **Every lineage interaction in the explorer opens the existing drawer** on a handle. The
  drawer's S9 budget (SB-05 §4.2: one activation, one `/explain`) is unchanged and unspent
  by anything the explorer adds.
- `derivations`, `manifests` and `vintages` appear as **datasets** — flat, filterable,
  paginated collections, exactly like `wells` — because they are collections the API serves
  (`GET /v1/derivations`, `GET /v1/manifests`, `GET /v1/vintages` are live today **[V]**,
  `tests/contract/openapi_snapshot.json`). Browsing a collection is not exploring a graph.

If a reviewer reads §3 as the cut item returning, §3.3's join-by-navigation is the line: the
explorer walks **ids between collections**, which is what a REST client does, and never
walks **edges inside a chain**, which is what the drawer does.

**The second cut item, argued rather than ignored (M7).** SB-05 §13 also cut *"in-app
onboarding tour (the glossary and the notebook are the teaching surfaces)"* **[V]**. §5.3's
walkthroughs are not that item, and the difference is mechanical rather than rhetorical:

| The cut onboarding tour | §5.3 walkthroughs |
|---|---|
| Chrome authored in the client, over the product | Notebook rows — *"the glossary and the notebook are the teaching surfaces"* is the cut item's own stated alternative, and this is that alternative |
| Describes the UI; drifts silently when the UI moves | **Drives** the UI, and every step carries an assertion that runs in the e2e tier — a drifted step is a red build (§5.3, §8.3) |
| Onboards once, then is dead weight | Answers a standing question (*why did my number change*), reachable by deep link at any step, quotable in an issue |
| No failure mode | Vintage-pinned, `requires`-gated, and unavailable rather than degraded when its data is absent |

The honest form of the concession: if the assertions were dropped, §5.3 **would** be the cut
item and should be cut with it. The assertion harness is therefore not a testing detail — it
is the entire justification, which is why §8.3 makes the seeded-instance e2e job a P-C
dependency with an owner instead of assuming CI already runs one (M6).

---

## 1. The problem, stated as a measurement

`ux-deep-dive.md` §3 **[V]**, against a running deployment:

> **Trace half: 7/10** … **Understand half: 3/10.** *"A visitor who reaches the drawer sees
> `canonical.promote produced canonical.production_monthly … conformance rules
> cr_nd_days_range_1, cr_nd_stream_vocab_1`. Every noun in that sentence is a system-internal
> term. The rule chips that would explain the sentence are dead ids."*

Three facts follow, and they are the whole design brief:

1. **The product has one entry point and it is a map.** A map answers *where*. It does not
   answer *what is in here*, *what does this column mean*, or *how would I get this myself* —
   which are the first three questions a technical newcomer asks. `ux-deep-dive` §2.2 scores
   findability **1/10** **[V]**.
2. **The teaching layer is client-side by construction.** `v0.6 §3.6.9` forbids
   server-authored prose in `/explain` **[V]**, so the only server-side pedagogy is the
   glossary — and `ux-deep-dive` §3 records it firing on 8 terms **[V]**.
3. **The API is the best-documented thing in the product and no human ever sees it.**
   `/openapi.json` carries 29 request examples and 19 glossary bindings today **[V]**
   (measured against `tests/contract/openapi_snapshot.json`); `/docs` is a generic Swagger
   page. The richest teaching asset in the system is addressed only at machines.

**The thesis of SB-08:** the API *is* the curriculum. A technical person who does not know
the domain does know HTTP, JSON and query parameters. Teach the domain **through** the
interface they already read — build the filter UI so that it constructs real API calls,
show them the call, annotate the parameters semantically, show them the response with its
envelope labelled, and let them run it. The vernacular arrives attached to something they
can execute, which is the only form of domain teaching this persona trusts.

The owner is this persona and says so. DIR-1 applies unchanged: a Novi PM must find the
domain framing correct, and a DS reviewer must find the data semantics honest — the same
surface has to satisfy both, and the way it does is by never asserting anything it cannot
resolve to a rule, a manifest or a glossary row.

---

## 2. Information architecture

### 2.1 Where it lives

The product gains a **mode switch** in the header, not a nav menu.

**B1 — path routes do not work today, and rev 1 assumed they did.** The app is served by
`app.mount("/", StaticFiles(directory=web_root, html=True))`
(`src/glasswell/api/__init__.py:191` **[V]**). `html=True` serves `index.html` for a
*directory* request; it does not rewrite an unmatched path, so `/explore/wells` returns a
`404` from Starlette **[V]**, and the reviewer confirmed it by probing the live instance.
Caddy is not in front of it on VM 111 today (DIR-13 stages it), and no client router exists.

**Refutation attempted and withdrawn.** The controller offered path routes if the fallback
is genuinely one line in `api/__init__.py` **and** registered to Track A2. It is not one
line: `StaticFiles(html=True)` raises `HTTPException(404)` from inside the ASGI app, so the
fix is either a `StaticFiles` subclass overriding `get_response`, or a catch-all route
mounted **before** `/` that must exclude `/v1/*`, `/openapi.json`, `/docs*`, `/healthz`,
`/basemap/*` and the tile path by prefix. It also lands on the security-header middleware's
404 path, which `api/__init__.py:155` calls out by name **[V]**. That is a real change with
a real test surface in another track's file. So:

**Ruling: P-A ships `?view=` routing, entirely inside the seam commit.** Zero cross-track
dependency, no unregistered work, and the URL grammar stays flat and readable — which is the
property SB-05 §6.1 was actually after (*"filters, flat and readable"* **[V]**).

| Parameter | Meaning |
|---|---|
| `view=map\|explore` | The mode switch. Default `map`, so every existing URL is unchanged |
| `tab=datasets\|query\|learn` | Explorer tab. Default `datasets` |
| `ds=<dataset_id>` | The dataset in view |
| `row=<row_id>` | The expanded row |
| `as_of` | Unchanged; propagates to every request from this view (`v0.6 §3.6.6`) |
| `f.<param>=` | A filter, named for **the API parameter it becomes** — `f.reason_code=key_incomplete` is `?reason_code=key_incomplete` on the wire. The URL and the curl are the same statement. **Repeatable** (`f.stream=oil&f.stream=gas`), which the current state module cannot express — see §8.4 M2 |
| `cursor=` | The cursor currently being displayed, so a page of a walk is shareable |
| `api=req\|op\|res\|prob` | Which section of the API pane is expanded |
| `pane=open\|closed` | Pane state; **in the URL** because it changes what a shared link teaches |
| `slug=` | Concept page or walkthrough, when `tab=learn` |

**Path routes are registered, not abandoned.** Amendment **A-7** (§7.1) adds the SPA
fallback with Track A2 as owner and Track O's Caddyfile as the deployed equivalent. When it
lands, `/explore/{ds}/{row}` becomes the canonical form and the `?view=` grammar stays as a
permanent alias — a redirect, not a removal, because by then people will have shared links.
`/glossary/{term_id}` likewise resolves to `?view=explore&ds=glossary&row={term_id}` today
and becomes a path when A-7 ships.

`explain=<handle>` is unchanged and opens the same drawer over the explorer that it opens
over the map. **Not in the URL:** grid column widths, scroll position, highlight-all
(localStorage, per SB-05 §6.1).

**Mode switch is not a page load.** Both surfaces are the same SPA; switching preserves
`as_of` and, where meaningful, selection. Losing the reader's as-of when they change mode
would make the two surfaces disagree about a number, which is the one thing this product
cannot do.

### 2.2 Three tabs and one persistent pane

The owner's ask names an API guide that is *contextual, not a separate silo*. The mechanism
that guarantees it: **the pane has no route of its own.** It is not a tab. It renders
whatever the centre column is currently showing, and it re-renders on every state change —
filter, cursor step, row expansion, as-of change. There is no way to reach the API guide
except by looking at data, which is the point.

| Tab | Contains | Route |
|---|---|---|
| **Datasets** | The catalogue rail plus the queryable surface for the selected dataset. The default and the centre of gravity | `?view=explore&ds={id}` |
| **Query** | The workspace: compose across parameters, walk the cursor deliberately, stage an export, keep a session history of what you ran | `?view=explore&tab=query` |
| **Learn** | Walkthroughs and concept pages, each of which **drives the Datasets tab** rather than describing it | `?view=explore&tab=learn` |

**Rejected: a fourth "API" tab.** It would be the silo the ask forbids, and it would be a
second implementation of the pane. The pane's operation index — "show me every operation,
not just this one" — is reachable by expanding the pane's OPERATION section to its list
view, which is the same component with the current operation deselected.

**Rejected: a Glossary tab.** The glossary is a dataset (`GET /v1/glossary` is a paginated
collection like any other **[V]**), so it lives in the catalogue's Vocabulary group and
inherits the grid, the facets, the API pane and the deep links for free. Building a bespoke
glossary browser beside a generic dataset browser would be two implementations of one thing.
`/glossary/{term_id}` keeps working and redirects.

### 2.3 The dataset catalogue is generated, never hardcoded

**This is the load-bearing architectural decision of SB-08.**

The catalogue is built at runtime from `GET /openapi.json` plus a new operation-level
extension, `x-glasswell-dataset` (§7, amendment **A-1**). A dataset is an *operation* that
declares itself browsable:

```yaml
# on the operation object for GET /v1/quarantine
x-glasswell-dataset:
  id: quarantine                    # reserved ids rejected by lint: map, query, learn, api
  title: Quarantine
  group: kitchen                    # wells | kitchen | vocabulary | service
  collection_pointer: ""            # JSON Pointer to the array inside `data`; "" = data is
                                    #   the array. `/error_codes` for the Problems dataset,
                                    #   `/sources` for Sources & freshness
  row_id: [/quarantine_id]          # ordered pointers; composite where identity is composite
  detail_operation: get_quarantine_row
  facets: [reason_code, state, stage, source_id]
  summary_operation: get_quarantine_summary   # optional
  columns:
    default: [/quarantine_id, /reason_code, /state, /stage, /occurrence_count]
    hidden:  [/row_fingerprint, /notes]       # each needs a `hidden_reason`
    sort:    /last_seen_at                    # informational: the API declares the order
  intro: nb_dataset_quarantine      # notebook slug; §5.1
  order: 20
```

**G-1 (ratified against the P-A plan's challenge) — the production endpoints are parallel
arrays, and `row_id[]` alone cannot address them.** `ProductionSeries` is not a list of row
objects: it is `pm` plus, per stream, four aligned arrays — `oil_bbl`, and
`oil_bbl_report_vintage`, `oil_bbl_null_semantics`, `oil_bbl_aggregation` **[V]**. There is
no row to point at. A-1 therefore gains a **pivot**:

```yaml
# on the operation object for GET /v1/wells/{api10}/production
x-glasswell-dataset:
  id: production
  series_pointer: /series          # the object holding the aligned arrays
  row_projection:
    axis: /pm                      # the index every other array aligns to; one row per entry
    columns: [/oil_bbl, /gas_mcf, /water_bbl]
    suffixes: [_report_vintage, _null_semantics, _aggregation]
  anchors: [/api10, /granularity, /reporting_level]   # scalars repeated onto every row
  row_id: [/pm]
```

Two rules the challenge required, because the resolution is incomplete without them:

- **Namespace: every pointer inside `row_projection` — `axis`, `columns`, and the `row_id`
  pointers it produces — is relative to `series_pointer`, not to `data`.** `/oil_bbl` means
  `/series/oil_bbl` on the per-well operation and `/pools/3/series/oil_bbl` on the pooled
  one, and the same extension therefore describes both without repeating the prefix. This is
  also what makes the label lookup land: the router emits `meta.labels` keyed at
  `/series/oil_bbl` **[V]** (`routers/production.py:180-182`), so the header binding resolves
  by composing `series_pointer` with the column pointer rather than by exact-matching a
  root-relative key that was never emitted.
- **The axis column is exempt from suffix expansion.** `pm` has no
  `pm_report_vintage`; expanding suffixes over it produces three pointers that resolve to
  nothing and a grid with three permanently empty columns. `axis` is projected once, as the
  row key; only `columns[]` take `suffixes[]`.

`anchors[]` covers the third shape rev 2's `collection_pointer` could not: scalars that sit
*beside* the array and belong on every projected row (`api10`, `granularity`,
`reporting_level` **[V]**). Without it a production row cannot state its own granularity,
which R5 requires of every figure the grid renders.

**M4 — rev 1's shape could not express three of eleven datasets, and the reviewer counted
them correctly.** `row_id[]` handles composite identity (production is `(api10, pm, stream)`
**[V]**); `collection_pointer` handles the two projections where the browsable array is not
`data` itself — Problems reads `/v1`'s `error_codes[]` and Sources reads `/v1/health`'s
`sources` **[V]**; `columns{}` carries the configuration rev 1 left implicit, which is the
half that would otherwise have been hardcoded in the client and quietly falsified the
section title. A dataset whose extension omits `columns.default` renders every property in
schema order — a stated, testable fallback rather than a per-dataset special case.

**Rev 3: that fallback is a fallback, not a plan. All eleven P-A datasets declare an
explicit `columns.default` of five to seven pointers.** The P-A plan's challenge showed why
this stopped being cosmetic: §3.2's binding ratchet is a percentage, so its **denominator is
whatever `columns.default` declares**, and seven of the eleven datasets falling back to
their full schema silently inflated it — which is how the plan arrived at 55 where the
measured figure is ~87–90 (O-6). Explicit defaults make the ratchet's denominator a
reviewable list rather than an emergent property of a fallback, and the floor test derives
its denominator from the declared defaults instead of hardcoding a count. **A-1's column
config is therefore load-bearing for a phase gate, not presentation.**

Consequences, each of them a DIR-1 answer:

- **The explorer cannot drift from the API.** A dataset that is not an operation cannot
  appear. An operation that stops existing takes its dataset with it. The snapshot gate
  (SB-04 §7.2) already guards the document, so it now guards the explorer too.
- **New endpoints arrive with zero explorer work.** When P3 lands `GET /v1/models` and P5
  lands `GET /v1/operators`, they appear in the rail the day the extension is added to the
  operation — which is the same commit that adds the operation. No UI release.
- **Column semantics come from the same document.** Column headers bind to glossary terms
  via the existing `x-glasswell-glossary` property extension (20 occurrences document-wide,
  **19 of them inside the sixteen schemas this surface renders** — re-measured at `debf6cc`
  **[V]**); units come from `x-glasswell-unit`, which SB-04 §7.1 already requires and which
  is **unimplemented — 0 occurrences** **[V]** (§7, obligation **O-1**).
- **The explorer's filter set is the operation's parameter set.** No mapping table exists to
  drift.

A hard rule with a mechanism: **every network call in `web/src/explore/**` goes through
`web/src/api/client.ts:83` `getEnvelope` and names an `operationId` present in the served
document.**

**M10 — the enforcement is a vitest source scan, not a lint rule.** Rev 1 specified an
ESLint rule. **ESLint does not exist in this repo**: no `eslint.config.*`, no `.eslintrc*`,
no `eslint` dependency, and `web/package.json` has no `lint` script — its scripts are
`dev`, `build`, `preview`, `test`, `typecheck` **[V]**. SB-05 §1.1 specifies ESLint plus
three project rules; that is **[S]**, and standing up a linter to enforce SB-08's invariant
would make SB-08 the funder of SB-05's toolchain. Instead, `explore/guardrails.test.ts`
reads its own source tree with `node:fs` — the pattern `web/src/build.test.ts` already uses
**[V]** — and asserts:

1. No `fetch(` and no `XMLHttpRequest` anywhere under `web/src/explore/`.
2. Every `operationId` string literal under `explore/` resolves in
   `tests/contract/openapi_snapshot.json`.
3. No absolute `http(s)://` URL under `explore/` outside a comment or a doc example.
4. No domain-prose string literal above 120 characters outside the notebook renderer (§8.3).

Same guarantee, zero new toolchain, and it runs in the `web` CI job that already exists
**[V]**. If SB-05 later lands ESLint, these move to lint rules and the tests are deleted in
that commit.

### 2.4 The dataset set, by phase and honesty class

Three classes, and the rail renders all three so a reader learns the shape of the system
including its incompleteness:

**Class A — live today** (verified against `tests/contract/openapi_snapshot.json`, 28 paths
**[V]**):

| Group | Dataset | Operation | Row identity | Facets | Figures? |
|---|---|---|---|---|---|
| Wells & production | **Wells** | `list_wells` | `[/api10]` | status, operator, county, bbox, q | none — identifiers and strings |
| Wells & production | **Production** (per well) | `get_well_production` | `row_projection` over `/series`, anchor `pm` | stream, from, to | **yes — `_lineage` sidecars over `oil_bbl`/`gas_mcf`/`water_bbl`** |
| Wells & production | **Production by pool** | `get_well_production_pools` | `row_projection` per `/pools/*`, anchor `pm`, row_id `[/well_completion_pool, /pm]` | stream | **yes** |
| The kitchen | **Quarantine** | `list_quarantine` | `[/quarantine_id]` | reason_code, rule_id, state, stage, source_id | counts only |
| The kitchen | **Conformance rules** | `list_conformance_rules` | `[/rule_id]` | source_id, kind, family, stage, field, effective_at | none |
| The kitchen | **Manifests** | `list_manifests` | `[/manifest_id]` | source_id, source_key, vintage_from/to, head_only | counts only (`bytes`) |
| The kitchen | **Derivations** | `list_derivations` | `[/derivation_id]` | operation, status | counts only |
| The kitchen | **Vintages** | `list_vintages` | `[/vintage_id]` | source_id · **no `cursor`** (§3.6) | counts only → **a handle after A-4** |
| Vocabulary | **Glossary** | `list_glossary_terms` | `[/term_id]` | q, domain_tag | none |
| Service | **Sources & freshness** | `get_health` | `[/source_id]`, `collection_pointer: /sources` | — | counts only |
| Service | **Problems** | `get_service_index`, `collection_pointer: /error_codes` | `[/code]` | status class | none |

**B2 — rev 1 put the only figure-bearing datasets in P-B, and the reviewer audited every
Class-A row schema to prove it: one figure object across the entire class, on `get_well`'s
detail.** A first phase of a *no-naked-numbers* surface that renders no number carrying a
handle is not a demonstration of the thesis; it is a metadata browser that happens to be
well-built. The controller's ruling is adopted in full (§8.1): **`get_well_production` and
`get_well_production_pools` move into P-A**, which is where the real figures, the
`_lineage` sidecars, the `null_semantics` vocabulary and W1's traceable barrel all live —
and **A-4 is pulled forward** so the vintages dataset carries a handle in the same phase.
The cross-well grid stays gated on **A-3**, and the rail carries it as a stated Class C gap
rather than as an absence.

**Class B — specified in SB-04 §4, not yet built.** Rendered in the rail, greyed, each
carrying the phase that lands it and the operation it will be: Completions
(`v0.6 §3.6.12` **row 7** — rev 1 cited row 6, which is production; m3),
Forecasts, Models, Benchmarks, Analogs, Operators, League, Permits, Activity/DUC, Land
units, Formations, Spacing units, CRS, Scorecard, Ledger, Audit, Recipes, Jobs, Exports,
Notebook, Inventory. **This is not a placeholder for a placeholder's sake** — it is the
honest-gap register made navigable, which is what E16 asks for (`v0.6 §5 E16`) and what
`ux-deep-dive` §2.9 says the product currently fails to do.

**Class C — needs a contract delta.** Exactly one dataset in the owner's list falls here:
**Production across wells.** Today production is reachable only per well
(`/v1/wells/{api10}/production` **[V]**), so a cross-well production grid does not exist.
§7 amendment **A-3** proposes it.

**It no longer gates the feature, and that is the point of the B2 reshuffle.** P-A ships
per-well production, so the figure grid, the sidecar lesson and W1 are all deliverable
without A-3. What A-3 buys is the *population* question — *show me every well in McKenzie
County in 2024-03* — which is the query a Novi PM asks in the first minute and which the
rail states as an open gap in the meantime, naming the amendment and its status. Rev 1 made
A-3 the critical path; rev 2 makes it the second phase's gate, which is what the ruling
asked for and what the evidence supports.

"Geology layers" from the owner's list are Class B/C: `landunits`, `spacingunits` and
`formations` are SB-04 §4.7 rows not yet built; formation tops are a P2+ data question
(DIR-9's NDIC Premium decision). They enter the rail as Class B and light up when built.

### 2.5 Layout

**≥1600 px — three columns.**

```
┌ glasswell ──────────────────────── [ Map │ Explore ] ─── as_of 2026-08-01 ▾ ─ key ok ─┐
├────────────────┬──────────────────────────────────────────┬──────────────────────────┤
│ DATASETS       │  Datasets   Query   Learn                │  API                 [—] │
│                │                                          │                          │
│ WELLS & PROD   │  QUARANTINE                              │  ▾ REQUEST               │
│  Wells         │  Rows the pipeline refused, kept with a  │   [curl] httpie  fetch   │
│  Production    │  reason. Nothing is dropped silently.    │   curl -s \              │
│  Prod by pool  │  ▸ what am I looking at?                 │    -H "X-Glasswell-Key:  │
│                │                                          │        $GLASSWELL_KEY" \ │
│ THE KITCHEN    │  reason_code ▾ state ▾ stage ▾ source ▾   │    'https://glasswell.  │
│  Quarantine ●  │  ────────────────────────────────────    │     lab.rpx.sh/v1/quara  │
│  Conformance   │  1,284 rows · 12 shown · this page only  │     ntine?reason_code=k  │
│  Manifests     │  ▂▇▇▃▁▁ reason_code  [distribution ▾]    │     ey_incomplete&limit  │
│  Derivations   │                                          │     =100'                │
│  Vintages      │  ┌─────────┬──────────────┬───────┬────┐ │           [copy] [run ▶] │
│                │  │quarantin│ reason_code ⓘ│state ⓘ│occ…│ │                          │
│ VOCABULARY     │  │_id      │              │       │ ⓔ  │ │  ▾ OPERATION             │
│  Glossary      │  ├─────────┼──────────────┼───────┼────┤ │   list_quarantine        │
│                │  │qr_01c…  │ key_incomple…│ open  │ 3  │ │   GET /v1/quarantine     │
│ SERVICE        │  │qr_01d…  │ stream_vocab…│ open  │ 1  │ │   ── parameters ──       │
│  Sources       │  │qr_01e…  │ key_incomple…│ super…│ 7  │ │   reason_code · string    │
│  Problems      │  └─────────┴──────────────┴───────┴────┘ │    Why the row was       │
│                │  ▸ next 100  ·  cursor eyJrIjoi… [decode]│    refused. A closed     │
│ NOT YET BUILT  │                                          │    vocabulary, not free  │
│  Completions   │                                          │    text — every value is │
│  Forecasts P3  │                                          │    a rule outcome. ⓖ     │
│  Operators P5  │                                          │                          │
│  Scorecard P6  │                                          │  ▸ RESPONSE 200 · 41 ms  │
│  …             │                                          │  ▸ PROBLEMS 403 422 404  │
└────────────────┴──────────────────────────────────────────┴──────────────────────────┘
   240 px                        flex                                  420 px
```

**1366–1599 px.** Rail collapses to a 56 px icon strip with the group initial and a hover
label; pane narrows to 380; the grid keeps a 640 px floor. If the floor cannot be met the
pane collapses to its edge tab and the grid takes the space — the data is the subject.

**1024–1365 px.** The pane **stacks below** the grid with a sticky section header rather
than narrowing further. A request block rendered at 320 px wraps a curl command into
unreadable confetti, and the request block is the pane's highest-value content **[I]**. The
grid keeps full width; the pane is one scroll away and its state is still in the URL.

**820 px.** Grid becomes a card list (one card per row, columns as `<dt>/<dd>` pairs, the
figure treatment unchanged). Facets become a filter sheet. Pane stacked.

**390 px.** The grid is honestly unusable and says so: *"the result grid needs a wider
window — the API guide below works everywhere."* The pane renders in full. This inversion is
deliberate: on a phone the API guide is the whole product, and pretending a 12-column grid
fits is the sort of thing DIR-11 exists to catch. SB-05 §13 already cut phone-specific
layouts; this is the honest degradation, not a new layout.

**Panel stacking.** The lineage drawer opens **over** the API pane at ≥1600 (drawer 480,
pane hidden behind it, restored on close), and as a full overlay below that.
`ux-deep-dive` P2-10 records the map's current control/panel collisions **[V]**; the
explorer declares **named slots that alias the global ladder, plus local stacking contexts
where the ordering is internal** — not a private ladder of its own. **G-3: a private ladder
is arithmetically unsatisfiable here.** `style.css:84-90` fixes the global rungs at
`--gw-z-map-chrome: 5`, `--gw-z-panel: 10`, `--gw-z-drawer: 12`, `--gw-z-rail-pop: 30`,
`--gw-z-modal: 40`, `--gw-z-popover: 50`, `--gw-z-toast: 60` **[V]**, and the explorer needs
three ordered layers below the drawer while exactly one integer (11) sits between `panel` and
`drawer`. The re-ruling, per the plan challenge's B3:

| Explorer layer | Resolution |
|---|---|
| API pane, rail, grid | **`--gw-z-panel`.** They are siblings in one grid container; DOM order decides paint order and no rung is needed |
| Sticky grid header | **A local stacking context** — `position: sticky` plus `z-index: 1` scoped to the grid, which cannot escape its parent and therefore cannot collide with the drawer |
| Facet and column-picker popovers | **`--gw-z-rail-pop`**, the rung the chrome already uses for exactly this |
| Lineage drawer | Unchanged at `--gw-z-drawer`, above the pane, which is the §2.5 requirement |

The test asserts **no new global rung and no numeric literal outside a declared local
context** in `explore/layout.css` — a stronger and satisfiable property than rev 2's
"assert the order".

### 2.6 Map ↔ explorer, both directions

| From | Affordance | Lands on |
|---|---|---|
| Map well card header | **"Rows for this well"** | `?view=explore&ds=wells&f.q={api10}` with the row expanded, `as_of` preserved |
| Map well card, production chart header | **"Open this series"** | `?view=explore&ds=production&f.api10={api10}` (Class A per-well today; the cross-well grid after A-3) |
| Map legend layer ⓘ | **"What's behind this layer"** | The dataset that feeds the layer, filtered to the current bbox where the operation accepts `bbox` (`list_wells` does **[V]**) |
| Map status rail, `as_of` chip | **"Vintages"** | `?view=explore&ds=vintages` |
| Explorer row with geometry | **"Show on map"** | `/?well={api10}&map=z/lat/lon`, reusing `bus.ts:51 selectWell` and `:67 flyTo` **[V]** when the mode switch is in-document |
| Explorer wells grid, multi-select | **"Show N on map"** | Deferred — needs `POST /v1/wellsets` (SB-04 §4.8, Class B). Stated, not faked |
| Any figure, either surface | The `⌾` handle | The same drawer, the same one `/explain` call |

Two invariants: **`as_of` always survives the crossing**, and **the crossing is a
`pushState`**, so the back button returns the reader to where they were looking.

**m7 — "does not boot MapLibre" was half-true, and the half that was false is the expensive
half.** `main.ts:18` statically imports `createMap` from `./map/map.ts` **[V]**, so the
MapLibre bundle is fetched and parsed on every load regardless of surface — the shipped main
chunk is **1,224,213 bytes** uncompressed **[V]** (`web/dist/assets/index-*.js`). Not
constructing a map instance saves the GL context and the tile requests; it does not save the
download or the parse. The fix belongs in the seam commit (§8.4): **`createMap` becomes a
dynamic `import()` behind the `view=map` branch**, which also gives the explorer a genuine
code-split boundary and is the precondition for §8.1's shell budget being meaningful. A
guardrail test asserts `map/map.ts` is not in the entry chunk's static import graph.

---

## 3. The explorer core

### 3.1 The filter model is the API's parameter set — that *is* the pedagogy

Every control in the facet bar is generated from one OpenAPI parameter and is typed by its
schema.

**m5 — unwrap `anyOf` first, or every control silently degrades to a text box.** FastAPI
serialises an optional parameter as `anyOf: [{…real schema…}, {"type": "null"}]`, not as a
nullable scalar: `as_of` is `[{format: date, type: string}, {type: null}]`, `state` is
`[{enum: [open, released, accepted_loss, superseded], type: string}, {type: null}]`, and
`limit` — being non-optional — is a bare `{type: integer, maximum: 200}` **[V]** (measured
across the snapshot). A naive `schema.type` read therefore finds `undefined` on almost every
filter and falls through to the default control. **The generator resolves a parameter schema
by discarding `{"type": "null"}` members of `anyOf`/`oneOf` and requiring exactly one
survivor**, and it *fails loudly* on two survivors rather than guessing — a union parameter
is a design question, not a rendering one. `explore/facets/schema.test.ts` fixes this against
five real parameter schemas lifted from the committed snapshot, so a FastAPI upgrade that
changes the serialisation breaks the test rather than the UI.

| Parameter schema (after unwrap) | Control | Notes |
|---|---|---|
| `enum` | Chip group, multi where the parameter is repeatable | The enum is the vocabulary; the chips *are* the closed list |
| `string` free-text | Text input with the parameter's description as placeholder help | |
| `date` / `YYYY-MM` pattern | Date or month input, validated client-side against the same `pattern` the server declares **[V]** (`from`/`to` carry `^\d{4}-\d{2}$`) | An invalid month never becomes a request; the reader sees the constraint, not a 422 |
| `integer` with `maximum` | Stepper showing the cap inline: *"1–200; the server's cap, not ours"* | The spine caps at 200, wells at 1000 **[V]** — the difference is a teachable fact, not a bug |
| `boolean` | Toggle | |
| `bbox` | "Use the map's current view" button plus the raw value, editable | The 4° cap is stated |
| `as_of` | Hoisted out of the facet bar into the header — it is global, not per-dataset | |

Four rules:

1. **A filter with no API parameter behind it does not exist.** No client-side filtering
   that the API cannot express. If a reader can narrow it in the UI, they can narrow it in
   `curl`, and the pane proves it in the same frame. This is the anti-story *"no UI figure
   without an endpoint that reproduces it"* (`v0.6 §6.1`) generalised from figures to queries.
2. **Changing a filter updates the URL, the request block and the grid in one commit.** The
   three are never out of step, because they are one render off one state object.
3. **Unsupported combinations are shown, not hidden.** `list_vintages` accepts only
   `source_id` and `limit` — **and no `cursor` at all** **[V]** — so the facet bar shows
   exactly those two and a line naming what this collection cannot be filtered by, and the
   pagination block renders its uncursored form (§3.6). An absence a reader can act on (file
   it, or understand why) beats an absence they cannot see.
4. **`as_of` changes are announced.** Changing as-of re-runs the query and renders a diff
   line: *"3 rows changed value at this as-of"* where the dataset supports it. This is DIR-2
   made visible at the point it bites (§5.2 C-b).

### 3.2 The result grid and column semantics

**M1 — SB-05 §3.10's table system does not exist, and rev 1 built on it as though it did.**
`web/package.json` runtime dependencies are `@protomaps/basemaps`, `maplibre-gl`, `pmtiles`
and `uplot` **[V]**; there is no `@tanstack/table-core`, no `@tanstack/virtual-core`, and no
`web/src/tables/` directory **[S]**. Two consequences the reviewer is right to force:

1. **Ownership.** `tables/` would be a shared sibling that SB-05 specifies and no track owns.
   SB-08 will not create a contested shared module as a side effect of building a view.
2. **The decision.** SB-08 adds **no runtime dependency**. The grid is ~250 lines in
   `explore/grid/`: a windowed renderer over an array that the **server has already
   paginated to ≤1000 rows** (`list_wells` caps at 1000, spine collections at 200 **[V]**).
   Sorting and filtering are server-side by §3.1's first rule, so the headless-table feature
   set is mostly inapplicable here, and SB-05 §12 already rejects a component library on
   exactly this reasoning. **Added gzip cost: 0 KB.** If a later surface genuinely needs
   client-side sort over a large in-memory set, that is the commit that installs a library
   and owns `tables/`.

SB-05 §3.10 is raised as an erratum (§7.3): it describes a shipped system that is a plan.

Column kinds, and what each guarantees:

| Column kind | Rendering | Guarantee |
|---|---|---|
| **Figure** | `<gw-figure>` with `value`, `unit`, `granularity`, `vintage`, `handle` **[V]** `card/gw-figure.ts:10` | R5 + R6. The `⌾` opens the drawer |
| **Count** | New `<gw-count>`: the number, plus a superscripted `ⓔ` whose popover states **why this number is not a figure**, quoting the exemption reason verbatim | §6.3 — this is how the exemption register becomes a product surface |
| **Identifier** | Monospace chip, navigable (§3.3), never scanned by the glossary highlighter (SB-05 §5.3 exclusion table **[V]**) | No highlighting inside `qr_01…` — closes `ux-deep-dive` P2-12 for the new surface |
| **Enum** | The value plus a `<gw-term>` binding where the enum has a glossary row | `reason_code`, `state`, `stage`, `granularity`, `null_semantics` are all vocabulary |
| **Prose** | Text, glossary-scanned, first-occurrence-per-cell (SB-05 §5.3) | Rationale and rule text are where the vernacular lives |
| **Timestamp** | Vintage-aware; the formatting rule is SB-05 §3.10's, the implementation is `explore/grid/` | |
| **Geometry** | A "show on map" affordance, never raw coordinates in a cell | Coordinates are allowlisted non-figures **[V]**; rendering them as data would teach the wrong thing |

**Column headers bind where a binding exists, and say so where it does not (B4).**
The binding comes from the **authoritative path** (SB-05 §5.1): `x-glasswell-glossary` on
the schema property, read from `/openapi.json` at catalogue build; where the operation also
populates `meta.labels`, that wins, being per-response and therefore more specific; only
where neither exists does the client-side scanner run.

**Rev 1 then asserted that every column header resolves, which is not a design — it is an
unfunded content project.** Measured: across the sixteen schemas this surface renders,
**201 properties carry 19 glossary bindings** **[V]**. The client-side residue cannot close
the gap either, because `ui/glossary-allowlist.yml`, `labels.ts` and the build-time
extractor SB-05 §5.7 specifies are all **[S]**. So the acceptance criterion changes shape:

> **Counted-unbound treatment.** Every column header is **either** bound — and renders as a
> `<gw-term>` — **or** renders in an explicit `unbound` treatment: no dotted underline, no
> hover affordance, and a muted `?` in the header's info slot whose popover reads *"this
> column has no glossary entry yet"* with a link to the coverage report. A reader is never
> misled into thinking a term was checked and found absent.

Three properties follow. The unbound state is **visible**, so the debt is a product surface
rather than a spreadsheet (the §6.3 pattern, applied to vocabulary). The coverage job
**reports a percentage per dataset** rather than failing the build, and that percentage is
also the scorecard's glossary-coverage metric (`v0.6 §3.2` C18), so one number serves both.
And the floor **ratchets by phase** — P-A ≥ 40 % of default columns, P-B ≥ 70 %, P-C 100 %
of default columns and ≥ 60 % overall — which is a schedule, not an aspiration, because
**O-6** in §7.1 funds the authoring with an owner and a session band.

The rev-1 claim that this *"closes `ux-deep-dive` P2-11 for every column of every dataset at
once"* is withdrawn. What it closes is the *mechanism* — one binding path, used everywhere,
with the gap counted. Closing the gap itself is O-6's job and takes the sessions O-6 states.

**Column visibility is honest.** Datasets are wide; the grid shows `columns.default` from
the dataset extension (§2.3) and a column picker. The picker lists **every** field the
operation returns, including the ones in `columns.hidden` — a reader must never conclude a
field does not exist because a UI chose not to show it. Every hidden column carries a
`hidden_reason` in the extension (*"long text"*, *"identical across this page"*), and the
A-1 lint fails a `hidden` entry without one.

**Empty is a statement, never a blank.** `null` renders as its `null_semantics` where the
API supplies one — `reported_zero` / `no_report` / `withheld` are three different facts
**[V]** and collapsing them is a defect (`v0.6 §3.6.12` row 6). Where the API supplies no semantics, the
cell renders `—` with a popover saying the field was absent from the response, not that the
value is zero.

### 3.3 Join by navigation, not by query language

The explorer offers no SQL, no expression builder, no GraphQL. It offers **navigable ids**,
which is what a REST surface actually is:

```
quarantine row  ──rule_id──▸  conformance rule  ──applied_by──▸  derivations
      │                              │
      └──first_seen_manifest_id──▸  manifest  ──▸  [verify] sha256 · [open ↗] source URL
                                       │
                                     vintages ──promotion_derivation_id──▸ derivation
```

Every id-typed cell is a chip. Activating it navigates to that id's dataset row, carrying
`as_of` and pushing history. The path a reader walks **is** the join, and each step is one
HTTP request they can see in the pane. Three properties fall out:

- **The join is provably real.** Each hop is an operation; if a hop has no operation, the
  chip is inert and says so — which surfaces missing endpoints instead of hiding them behind
  a client-side join.
- **It teaches the identity spine.** Walking `api10` from a well to its production to its
  quarantine rows is how a newcomer learns that API-10 is the identity spine and that digits
  11–14 are wellbore and convention, not identity (`v0.6 §9`, `v0.6 §3.0.5`) — without being told.
- **A "how did I get here" breadcrumb** records the hop chain with the operation for each
  hop, and copies as a numbered list of curl commands. That is S1's *"reproduce this view"*
  (SB-05 §6.5) applied to a path rather than to a single view.

### 3.4 Row detail

Expanding a row calls the dataset's `detail_operation` where one is declared, and renders
the full record — because a detail endpoint routinely returns more than its collection does
(`get_quarantine_row` adds `row_payload` and the first/last-seen manifests **[V]**).

The detail panel is **pointer-labelled**: every field renders with its JSON Pointer in a
muted monospace suffix, toggleable. This sounds like developer debris and is the opposite —
it is what makes `meta.labels`, `_lineage` prefixes and the naked-number walker's own
vocabulary legible to a reader who has just been shown the response in the pane. Default:
off; the Learn tab turns it on for the walkthroughs that need it.

`row_payload` and other verbatim source rows render in a JSON viewer with the offending
field highlighted (SB-05 §3.7's quarantine treatment, reused) and a standing caption: *"this
is the source row as it arrived, not a number the system stands behind"* — matching the
allowlist's own reason text **[V]**.

### 3.5 Inline visualisation, with an honest population

Two visualisations, and one rule that governs both.

**Column distribution.** Any enum, count or figure column can be summarised above the grid.
**m4 — the split is uPlot for histograms, SVG for ranked bars, and rev 1 got it backwards.**
SB-05 §3.9.1 assigns *"time-series, decline, band and distribution charts"* to uPlot and
reserves hand-rolled SVG for *"tornado, ranked bars and coverage tables"* **[V]**. A
histogram is a distribution chart: it is binned, continuous-axis, redrawn on every brush,
and uPlot is already a shipped dependency **[V]**. So: **numeric/figure columns bin into a
uPlot histogram; enum and reason-code columns render as an SVG ranked bar** in
`explore/viz/`. Both read the same `Distribution` value object, so §3.5's population rule
applies once rather than twice, and neither path edits Track V's `chart/` module.

> **The rule: no naked distributions.** A chart computed from the rows currently loaded
> carries the caption **"this page only — 100 of 1,284 rows"** and a muted treatment. A
> chart computed from a server-side summary operation carries **"whole population at as_of
> 2026-08-01"** and full treatment. The two never look alike, for the same reason an
> allocated series may not look like an observed one (`v0.6 §3.3 R5`, SB-05 §3.9.4).

This is the explorer's own contribution to the glass ethos and it generalises R5's spirit
from *estimates never pose as observations* to *samples never pose as populations*. It has a
unit test in the SB-05 §3.9.4 pattern: a pure `treatmentFor(populationKind)` that fails if
any two kinds map to identical treatments.

`GET /v1/quarantine/summary` exists today and gives the whole-population form for one
dataset **[V]**. §7 amendment **A-5** generalises it; until it lands, every other dataset's
distribution is page-scoped and says so — which is a weaker product and an intact lesson,
and is why A-5 sits below A-3 in the cut order (§8.5).

**Series preview on row selection.** Selecting a well row fetches
`get_well_production` for that `api10` and renders the existing chart via
`web/src/chart/chart.ts:26 renderChart` **[V]** — read-only import, no edit to Track V's
files. The chart frame is DOM per SB-05 §5.6, so its axis labels are hoverable terms like
everything else. `null_semantics` renders as the state strip; the strip gets the key
`ux-deep-dive` P2-4 says it needs, because in the explorer it is the first thing a newcomer
meets and 18 unexplained green squares is worse here than on the card **[V]**.

### 3.6 Pagination is a teaching moment, not a control

The single most under-taught mechanism in the API, and it is already fully implemented and
already decodable client-side.

Below every grid:

```
  1,284 rows matched · showing 1–100 · ▸ next 100
  cursor  eyJrIjoiMjAyNi0wOC0xOFQwOTozMTowMloiLCJxIjoiYTNmMj…  [decode ▾]
  ┌ decoded ───────────────────────────────────────────────────────┐
  │ { "k": "2026-08-18T09:31:02Z",   ← sort key of the last row     │
  │   "t": "qr_01contract0007",      ← tiebreak id                  │
  │   "v": "2026-08-01",             ← the as-of this walk is pinned│
  │   "q": "a3f2b81c" }              ← fingerprint of your filters  │
  │                                                                 │
  │ There is no page number, and no `offset` parameter exists. The  │
  │ cursor is not signed — SB-04 §2.3: it carries no authorisation, │
  │ it is a WHERE clause you could have written. `v` is why a       │
  │ restatement landing mid-walk cannot shift your rows. `q` is why │
  │ changing a filter mid-walk is a 422 instead of a wrong answer.  │
  │                          [break it on purpose ▸]                │
  └─────────────────────────────────────────────────────────────────┘
```

This is implementable exactly as drawn: the cursor is
`base64url(canonical_json({k,t,v,q}))` with no signature
(`src/glasswell/api/pagination.py:47` `encode_cursor`, `:57` `decode_cursor`, `:36`
`query_fingerprint` **[V]**), and SB-04 §2.3 states the non-signing as a deliberate honesty
property **[V]**. The client decodes it with `atob` + `JSON.parse` and asserts the four keys
— and a unit test asserts the decoder against a cursor minted by the fixture server, so a
cursor-format change fails the explorer's tests rather than silently rendering nonsense.
(The reviewer probed 3,000 minted cursors and found the base64url alphabet safe for `atob`;
the decoder normalises `-_` to `+/` and re-pads anyway, because the input is a server
implementation detail and one line is cheaper than the class of bug it forecloses.)

**"Break it on purpose"** replays the current cursor against a mutated filter, producing a
real `422 cursor_query_mismatch` from the real server, rendered by the problem curriculum
(§4.6). The reader learns the failure mode by causing it, on their own data. Total
`meta.next_cursor` honesty per SB-05 §3.10: **no page numbers, ever.**

**m10 — the uncursored form, stated.** Not every collection paginates: `list_vintages`
declares `source_id` and `limit` and **no `cursor` parameter at all** **[V]**. On such an
operation the block renders *"this collection is not cursor-paginated — `limit` is the whole
control, and the server caps it at 200"*, with the decode affordance absent rather than
disabled. Inventing a cursor UI for an operation that has no cursor would teach the reader a
contract the API does not offer, which is the same defect class as inventing a page number.

**Row counts are honest too.** `1,284 rows matched` requires a count the API may not serve.
Where a summary operation supplies a total, show it. Where it does not, show
`showing 1–100 · more available` and never `1–100 of ~1,284`. An invented total is a naked
number wearing a comma.

### 3.7 The Query workspace

Not a second explorer. The Query tab is the same query state, presented for **composition
and repetition** rather than browsing:

- **The full parameter form**, every parameter of the current operation, including the ones
  the facet bar hoists (`limit`, `cursor`, `as_of`) — with the OpenAPI description under
  each field and its cap or enum inline.
- **Session history:** every request the explorer made this session, with status, latency,
  row count and a re-run affordance. This is where a reader discovers that opening a well
  card is four requests, which teaches the surface's shape better than any diagram.
- **Compare as-of:** run the identical query at two as-of values side by side, with changed
  cells marked. This is S14 (`v0.6 §2.4 S14`) turned into a control, and it is the substrate of
  walkthrough W2.
- **Stage an export:** `?format=csv` where the endpoint supports it, capped at one page per
  SB-04 §10 E-20; larger sets are `POST /v1/exports`, Class B today, so the control states
  what it will do when the endpoint lands rather than silently offering less.

No saved queries in P-A/P-B: saved objects need `POST /v1/wellsets`-class endpoints and an
owner-scope story. A shareable URL is the save mechanism, and it is better because it
reproduces on a stranger's machine.

### 3.8 What the explorer never does

- **Compute a derived number.** Not a sum, not a ratio, not a percentage of a filtered set —
  except the explicitly-labelled page-scoped distributions of §3.5, which are labelled as
  *counts of rows on screen*, never as domain quantities. Every domain figure comes from the
  API with its handle, or it does not appear. GOR and water cut are derived server-side and
  the well card says so **[V]**; the explorer inherits that discipline.
- **Cache across `as_of`.** The response cache is keyed on `(url, as_of)` per SB-05 §6.3.
- **Render a figure it cannot handle-through.** Missing handle in a figure position is the
  `NAKED` badge in dev and a throw in test **[V]** (`gw-figure.ts:6,39`), unchanged.
- **Show fixture or demo data.** §6.5.

---

## 4. The API guide pane

### 4.1 Anatomy

Four sections, stacked, each independently collapsible, each bound to the current state.
Section state lives in the URL (`api=`) so a shared link teaches what the sharer meant.

| Section | Answers | Bound to |
|---|---|---|
| **REQUEST** | *How do I get exactly this myself?* | The current dataset + filters + cursor |
| **OPERATION** | *What do these parameters and fields actually mean?* | The current `operationId` |
| **RESPONSE** | *What did the server send back, and what is all that scaffolding?* | The last response |
| **PROBLEMS** | *What goes wrong, and what does it look like?* | The operation's declared problem types |

### 4.2 REQUEST — the exact call, in three dialects

```
  curl │ httpie │ fetch                                    [copy] [run ▶]

  curl -s \
    -H "X-Glasswell-Key: $GLASSWELL_KEY" \
    -H "Accept: application/json" \
    'https://glasswell.lab.rpx.sh/v1/quarantine?reason_code=key_incomplete&limit=100'
```

Rules:

- **The key is a placeholder, always.** `$GLASSWELL_KEY`, never the reader's actual key,
  even though the app holds one (`api/client.ts:56` `apiKey` **[V]**). The copy button is
  aimed at a chat window, an issue, a notebook — every one of which is a credential-leak
  path. A one-line note under the block says where to get a key and that the owner issues
  them at `POST /v1/keys` (Class A **[V]**, owner scope).
- **Absolute URL, real host.** A relative path teaches nothing about how to call the service
  from outside the browser.
- **The URL is byte-identical to the one the grid fetched**, built by the same
  `api/client.ts:75 apiUrl` **[V]**. A test asserts the rendered command's URL equals the
  URL of the request the grid actually issued — the highest-value single test in this
  document, because a request block that drifts from the request is worse than none.
- **httpie** for readability, **fetch** for the browser-native reader. All three from one
  request object; no hand-maintained templates.
- **Cursor pages are copyable individually**; a "walk all pages" snippet is offered as a
  short shell loop that follows `links.next` — teaching the follow-the-link discipline
  rather than URL assembly.

### 4.3 OPERATION — annotated semantically, not typed

The differentiator. A type says `string`. The reader needs to know what the string *means in
this domain*, and DIR-2 is the canonical example: nothing in `format: date` explains why a
row has two dates.

Each parameter and each response field renders as:

```
  report_vintage · string (date)                                   ⓖ report vintage
  ─────────────────────────────────────────────────────────────────────────────────
  WHAT   The knowledge date — when the regulator published this figure.
  WHY    A production month is not a fact with one value. North Dakota restates
         months for years; each restatement is a new vintage, appended, never an
         edit (DIR-2). A row therefore carries two dates: the month it describes
         (production_month) and the moment it was reported (report_vintage).
  SO     ?as_of=2026-06-01 answers "what did this system publish in June", which
         is not the same question as "what is true now" — and both are legitimate.
  SEE    concept: bitemporality · walkthrough: what a vintage is · glossary: vintage
```

**B3 — rev 1 specified four fields and could source one.** Two measurements settle it.
First: **0 of 78 parameters carry any `x-glasswell-*` extension** **[V]** — the 19 glossary
bindings that exist are all on *schema properties*, and a parameter is not a property, so
the binding rev 1 leaned on for WHY does not exist anywhere on the parameter surface.
Second, and more interesting because it is a modelling error rather than a gap: **no
glossary column could carry SO even if the binding existed.** SO is the operational
consequence *of this parameter on this operation* — `as_of` on `list_wells` resolves a
well-spine snapshot, `as_of` on `get_well_production` selects the vintage of every point in
a series — while a glossary term is deliberately shared across every site it appears at
(DIR-8: *"the agent and the UI read the same rows"*). Putting a per-operation sentence in a
shared row would make the glossary lie at every other site.

**Resolution: amendment A-8, `x-glasswell-semantics`, on the operation** (§7.1). Kept, not
dropped, because SO is the field this persona actually needs — WHY explains the domain, SO
explains what it does to *their* request:

```yaml
# on the operation object for GET /v1/wells/{api10}/production
x-glasswell-semantics:
  as_of:
    x-glasswell-glossary: gt_report_vintage   # WHY ← the shared term's expanded_definition
    so: >-                                    # SO  ← per-operation, authored here
      Selects the vintage of every point in the series. Two requests a month apart
      can return different volumes for the same production month, and both are correct.
  stream:
    x-glasswell-glossary: gt_stream
```

**G-2 — the inner member is named `x-glasswell-glossary`, and the name is the mechanism.**
`test_glossary_coverage.py` collects bindings by recursive key name, so an inner member
called `glossary` would be invisible to it and A-8's term references would resolve to
nothing while the check stayed green. Naming it `x-glasswell-glossary` makes the existing
collector pick these up **by construction** — no collector change, no second code path, and
§7.1's claim that A-8's referential integrity comes "for free" becomes true rather than
aspirational. It is one identifier, and it is the difference between a check that covers the
new surface and a check that silently does not.

- **WHAT / WHY / SO / SEE is the fixed shape.** WHAT is one sentence. WHY is the domain
  reason a newcomer cannot derive from the schema. SO is the operational consequence. SEE
  links a concept page, a walkthrough and a glossary term.
- **Each field has exactly one source, and none of them is the client.** WHAT ← the OpenAPI
  parameter `description` (SB-04 §7.1 requires one per parameter, and every parameter in the
  snapshot has one **[V]**). WHY ← `expanded_definition` of the term named by
  `x-glasswell-semantics[param].glossary`. SO ← `x-glasswell-semantics[param].so`. SEE ←
  the term's `related_terms` plus the concept index (§5.2). **No prose is hardcoded in the
  explorer**, which §2.3's guardrail test enforces by refusing long string literals.
- **Graceful degradation is specified, because A-8 will land incrementally.** A parameter
  with no `x-glasswell-semantics` entry renders **WHAT only**, with the same muted `?`
  treatment §3.2 gives an unbound column, and is counted by the coverage job. The pane never
  invents a WHY.
- **Semantic annotation is therefore an authoring obligation with an owner**, funded as
  **O-6** alongside the column bindings — not, as rev 1 implied, a property the glossary
  would supply for free.
- **Caps, enums and defaults render as facts with their reason**: *"limit ≤ 200 on the spine
  collections, ≤ 1000 on wells — each operation declares its own cap"* (SB-04 §2.3 **[V]**).
- **`operationId` is shown.** It is the join key to the MCP tool set (SB-04 §5.5) and to
  `x-glasswell-request-example` **[V]** — an agent-curious reader should be able to follow
  it.

### 4.4 RESPONSE — the envelope, labelled in place

The live response, pretty-printed, with the structural parts annotated as an overlay rather
than as commentary:

```
  {
    "data": [ … 100 rows … ]                    ← the resource. Collections put the
                                                   array here, never {items:[…]}
    "meta": {
      "request_id": "01JBQ7…",                  ← echoed in every problem body
      "as_of": { "requested": "latest",
                 "resolved": "2026-08-01" },    ← what "latest" actually meant
      "source_freshness": { … },                ← per-source retrieval + declared vintage
      "labels": { "/reason_code": "gt_quaran…"} ← JSON Pointer → glossary term. This is
                                                   what makes the column header hoverable
      "next_cursor": "eyJrIjoi…",               ← §3.6
      "warnings": [], "deprecations": [] },
    "links": { "self": …, "next": …,
               "explain": "/v1/explain?h=…" }   ← the S9 one-call link, pre-built
  }
```

- **Sidecars are called out where they appear.** On a production response the pane points at
  `_lineage`, `_units`, `_basis` and states the trade: *"one handle for a 300-point series,
  not 300 handles — the sidecar is rooted at the resource and covers everything below it"*
  (SB-04 §2.2 **[V]**). Then it points at a figure object and states the other half: *"a
  scalar carries its own `d`."*
- **Figure objects are highlighted and cross-linked to the cell** that rendered them, both
  ways. Clicking `/data/0/reason_code` in the pane flashes the cell; clicking the cell
  scrolls the pane. This is the single cheapest way to teach the pointer grammar.
- **Truncation is stated.** Large responses render the first N rows with an exact byte count
  and a "download this response" affordance; never an ellipsis with no number.
- **Timing and cache class** render in the header (`200 · 41 ms · public, max-age=…`).
  **M5 — this line was unbuildable as rev 1 wrote it.** `getEnvelope` returns the parsed
  envelope and discards the `Response`: no status, no headers, no timing survive the call
  (`web/src/api/client.ts:83-94` **[V]**). So the header needs a change to a **frozen** file,
  and rev 2 puts it in the seam's scope explicitly (§8.4): `getEnvelope` gains an optional
  out-parameter carrying `{status, headers, elapsed_ms}`, additively, with every existing
  call site unchanged. `x-glasswell-cache` is separately required by SB-04 §7.1 and
  unimplemented **[V]** (§7.1, **O-3**); until it lands the pane shows the response's actual
  `Cache-Control`, which is honest and strictly less useful.

### 4.5 "Run it yourself" — the ruling

**Ruling: the in-page runner ships, and it is narrowly scoped.**

Permitted:

- **GET only.**
- **Only operations present in the served `/openapi.json`**, resolved by `operationId`.
- **Only operations that return `application/json`.** **M5 — rev 1's permit admitted two
  operations that would break the runner**: `get_tile` returns MVT bytes and
  `get_manifest_bytes` streams a raw artifact **[V]**, and `getEnvelope` calls
  `response.json()` unconditionally (`client.ts:93` **[V]**), so both would throw a parse
  error the reader would read as a server fault. The permit now tests the operation's
  declared response media type; the two binary operations render copy-only with a line
  saying why, which is a better lesson than a hidden exclusion.
- **Only parameters that validate against that operation's schema**, checked client-side
  before dispatch.
- **Same-origin only**, through `api/client.ts:83 getEnvelope` **[V]**, with the key applied
  by `authHeaders()` **[V]** — the same code path the grid uses. There is no second fetch.

Forbidden, and copy-only in the pane:

- **Every mutation POST and DELETE.** `POST /v1/keys`, `DELETE /v1/keys/{id}`,
  `POST /v1/keys/{id}/rotate` are Class A today **[V]** and are exactly the operations a
  one-click runner must never fire. They render with their curl, their annotations and their
  problems, and no run button.
- **Compute POSTs** (`/v1/typecurves`, `/v1/valuations`, `/v1/sensitivities`,
  `/v1/exports` — SB-04 §3.3, guest-allowed) stay copy-only in P-A/P-B. They are re-examined
  at P-C when they exist; the argument for allowing them is strong (pure, content-addressed,
  guest-scoped) and the argument for waiting is stronger: none of them are built, so the
  decision has no evidence yet.

Reasoning, in DIR-1 terms:

1. **The runner adds no capability the app does not already have.** The grid issues these
   GETs with this key already; a runner that replays them is a re-render, not a new
   privilege. An **arbitrary-URL** runner would be a different product — a page-scoped
   credential pointable anywhere the key's scope reaches, from a surface that has just
   encouraged the reader to experiment.
2. **The key never leaves the browser's own request.** Not rendered, not copied, not put in
   a URL — `api/client.ts:56` already moves a key out of the fragment for this reason **[V]**.
3. **There is no rate limiter, and rev 1 said there was.** SB-04 §2.9 specifies one; the
   shipped registry declares `rate_limited` with **`emitted=False`** (`api/errors.py:137`
   **[V]**), which is the code's own statement that nothing can emit it. **The debounce is
   therefore the only control, it is client-side, and it is advisory** — a reader with
   `curl` and the copied command bypasses it entirely, which is fine, because that reader is
   an authenticated principal doing what the API is for. What the debounce actually protects
   is the reader from their own repeat-key, on one VM with 32-way concurrency
   (`v0.6 §3.6.8`). When a limiter lands, `429` joins the problem curriculum and this line is
   deleted rather than quietly becoming true.

A **"run as a stranger would"** toggle is specified and deferred to P-C: it re-issues the
request with the reader's *guest* key where one is configured, proving S1's claim on the
reader's own screen. It is deferred because the fifth Access class it depends on is DR-07,
still open **[V]** (`NEXT-CYCLE.md:149`).

### 4.6 PROBLEMS — the error registry as curriculum

The API's frozen error registry is 26 codes (SB-04 §2.4) of which the shipped slice can emit
a subset, and `/v1` already serves the whole registry with an `emitted_by_this_slice` flag
per code **[V]** (`api/routers/index.py`). That flag is a gift: it lets the pane teach the
full contract while being honest about what this deployment can actually produce.

Per operation, the pane lists every problem type it can emit, and for each:

- The **type URI**, resolvable at `GET /v1/errors/{code}` **[V]** — and the pane says so,
  because a resolvable error type is a rare and teachable property.
- **What causes it**, from the registry description.
- **A reproduction, where it is safe to reproduce**: `422 cursor_query_mismatch` via §3.6's
  "break it on purpose"; `422 validation_failed` via an over-cap `limit`;
  `404 lineage_unresolved` via a malformed handle — which additionally teaches that the
  auditor never gets a bare 404, since the body names `last_resolved` and `stop_reason`
  **[V]**.
- **The problem body rendered as a labelled object**, the same treatment §4.4 gives the
  envelope. `errors[]` with `pointer` is where a reader learns that field-level failures are
  addressed by JSON Pointer, which is the same grammar as `meta.labels` and `_lineage`. Three
  mechanisms, one grammar, taught once.

`403 unauthenticated` gets a specific note: the body carries **no `detail`** by design
(SB-04 §2.4), and the pane states the reason — no oracle for a probing client — rather than
letting a reader conclude the API is unhelpful.

### 4.7 What the pane never does

- **Author domain prose of its own.** Same rule as the drawer (SB-05 §4.3): UI-authored
  explanation is a second implementation that drifts. Everything in WHY/SO comes from the
  glossary or the notebook.
- **Show an operation that is not in the served document.** No "coming soon" endpoints in
  the pane; Class B lives in the rail (§2.4), which is a different claim — *this dataset is
  not built* is honest, *here is an endpoint* would not be.
- **Fabricate an example.** Examples come from `x-glasswell-request-example` **[V]**, and
  where an id in an example is a content address that differs per deployment, the example's
  own note says so **[V]** (`api/examples.py:19-30` — the note exists because
  `gate-a2-qa` M-3 found four unresolvable published examples).
- **Hide the request when it fails.** A failed request keeps its REQUEST block; the reader
  needs the command that failed more than the one that worked.

---

## 5. The educational layer

### 5.1 Prose as data — the model, and why not strings

DIR-8 settled this for terms: *"glossary is data, not markup"* **[V]**. SB-08 extends the
same ruling to longer-form prose, using the store the blueprint already has: the notebook
(`GET /v1/notebook`, `GET /v1/notebook/{slug}`, C21, SB-04 §4.12 **[V]** — specified, not yet
built; §7 **O-2**).

The notebook gains a `kind` discriminator (§7 amendment **A-6**):

| `kind` | Purpose | Rendered where |
|---|---|---|
| `memo` | Today's findings memos with live data links (E15, unchanged) | `?view=explore&tab=learn`, tag-filtered |
| `dataset_intro` | *"What am I looking at"* — 120–250 words per dataset | Collapsed header of the dataset surface |
| `concept` | The concepts thread (§5.2) | `?view=explore&tab=learn&slug={slug}`, linked from where it bites |
| `walkthrough` | A scripted sequence with `steps[]` (§5.3) | Driven over the live UI |

Why data and not strings, in one line each: a prose fix ships without a UI build; the agent
and the UI read identical text (the S13 property, extended); the glossary highlighter runs
over the markdown token stream so terms in intros are hoverable with no hand-tagging (SB-05
§3.8 **[V]**); live data links (`gw:` token rule, SB-05 §3.8) mean an intro that quotes a
number quotes a *current* number with a handle; and CI can assert every dataset has an intro
the same way it asserts every term has a row.

**Dataset intro contract.** Each must: name what a row *is*, in one sentence; state which
regulator artifact it derives from, by source id; state one thing it is **not** (the
misconception a newcomer arrives with); and link at least one concept page and one
conformance rule or manifest. Four sentences and two links. Example, quarantine:

> A row here is a source row the pipeline refused, kept with the reason it was refused.
> These come from `nd_mpr_xlsx` — the North Dakota monthly production report — and are held
> at the stage that rejected them, with the conformance rule that did the rejecting.
> **This is not an error log.** A quarantined row is data the system declined to promote
> rather than data it lost; nothing is dropped silently, and the count is a published
> quality metric, not an embarrassment. See: *conformance*, and rule `cr_nd_stream_vocab_1`.

### 5.2 The concepts thread

Six concept pages, each linked from every place its confusion bites. Not a glossary entry —
a glossary entry defines a word, a concept page explains a mechanism a newcomer must hold to
read the data at all.

| # | Concept | Bites at | Teaches |
|---|---|---|---|
| **C-a** | **Identity: API-10, API-12, API-14** | Every `api10` column; the search box; the wells grid | Why a well has several numbers, which one is the spine, what normalisation does. Project vocabulary rule: API-10 is the spine; API-14 normalises to it |
| **C-b** | **Bitemporality: month vs vintage** | `report_vintage`, `as_of`, the vintages dataset, the as-of compare | DIR-2 in full: two time axes, restatements as appends, why `as_of=latest` resolves to a date. F11's instrument |
| **C-c** | **Conformance: mapping as data** | Every `rule_id` chip; the conformance dataset; the drawer's rule chips | R8: LOOKUP / PARAMETERIZED / DOCUMENTED, why a mapping in code fails review, what `applied_by` proves |
| **C-d** | **Granularity: observed, allocated, modelled, assumed** | Every `granularity` and `reporting_level` cell; every figure chip | R5's composition table: why a Texas well-level volume is an estimate and a North Dakota one is not; why lease vs well granularity exists at all |
| **C-e** | **Provenance: manifest → derivation → figure** | Every `⌾`; every manifest and derivation row | What a handle is, what a selector is, what a terminal node is, why the drawer stops at amber |
| **C-f** | **Absence: reported zero, no report, withheld** | Every null cell; the state strip; `null_semantics` | The most-missed distinction in the data, and the one that silently corrupts every naive sum |

Each page: ≤ 600 words, at least one **worked example expressed as two API calls whose
outputs differ**, and a "where this bites" list generated from `bites_at[]` rather than
maintained by hand. The worked-example requirement is the persona fit: this reader believes
a diff, not a paragraph.

### 5.3 The walkthroughs

Five guided sequences that **drive the real UI against real data**. A walkthrough is a
notebook row of `kind: walkthrough` whose `steps[]` each carry prose, a route, and an
assertion:

```yaml
slug: trace-a-barrel
title: Trace a barrel from the screen to the regulator's file
audience: newcomer
requires: [dataset:production, dataset:manifests]
as_of: "2026-08-01"                 # pinned: every step runs at this vintage (M6)
steps:
  - prose: "Start with one well's production. Every row here is a month."
    route: "?view=explore&ds=production&f.api10=3305310451&as_of=2026-08-01"
    assert: { rows_gte: 12 }
  - prose: "That number is a figure object: it carries its own derivation handle. Open it."
    action: open_figure
    pointer: /series/oil_bbl/0
    assert: { drawer_open: true, explain_calls: 1 }
  - prose: "One call resolved the whole chain. The amber node at the bottom is a file."
    assert: { terminal_type: manifest, has_sha256: true }
  - prose: "That is the checksum of the North Dakota workbook. Here is where it came from."
    assert: { manifest_has_acquisition_url: true }
```

| # | Walkthrough | Answers | Data it needs |
|---|---|---|---|
| **W1** | **Trace a barrel from the screen to the regulator's file** | Mandate B's own sentence (`v0.6 §1.1`); S9 rendered as a lesson | Live today |
| **W2** | **What a vintage is, and why your number changed** | DIR-2, S14, F11 — same query at two as-ofs, diffed | Needs ≥2 vintages of one month; ND has them **[V]** |
| **W3** | **Why "oil" is a policy, not a fact** | U21, R8, S11 — the liquids rule, its rationale, its evidence URL, the derivations that applied it | Live today for ND. **The two-state version needs the Permian; the walkthrough says so and does not fake it** (§6.5) |
| **W4** | **Where the rejected rows go** | *"The kitchen is the product"* (`v0.6 §2.5.2`); U12 | Live today |
| **W5** | **Build a query and read the cursor** | The API lesson: facet → URL → curl → walk → decode → break it on purpose | Live today |

Rules that make these survive their own product:

- **A walkthrough drives the product; it does not simulate it.** No screenshots, no canned
  responses, no shadow DOM. Step N leaves the reader on a real view with real state, and
  they can abandon at any step and keep what they were looking at.
- **Every `assert` is an end-to-end test — and M6 is right that the CI to run it does not
  exist.** Rev 1 wrote *"a failing walkthrough is a failing build"* as though it were true
  today. It is not: `.github/workflows/` defines `python`, `web`, `shell` and `collateral`
  and **no e2e job at all** **[V]**, and the e2e tier that does exist runs against the
  **live deployed instance** (`make test-e2e`, project CLAUDE.md **[V]**) — which is a smoke
  test of a deployment, not a gate on a commit. Two corrections, both in §8.3's dependencies:
  **(a)** P-C requires a **seeded-instance e2e job**, owned by Track O (`tests/e2e/**` and
  `.github/workflows/**` are Track O's block **[V]**), running the same ephemeral-container
  fixture the integration tier uses; **(b)** until that job exists, a walkthrough assertion
  is a test that a human runs, and §8.3 says so instead of claiming a gate.
- **Every step pins its `as_of` vintage.** A walkthrough asserting `rows_gte: 12` against
  `latest` breaks when the ND E-0 back-load lands a new vintage — the drift the reviewer
  names. Each step carries an explicit `as_of` and, where it asserts a value, the
  `report_vintage` it was written against; the seeded fixture pins both. W2 is the exception
  that proves it: it *needs* two vintages, so it names both explicitly rather than reading
  whichever two happen to be newest.
- **A walkthrough whose `requires` are unmet renders as unavailable**, naming the phase or
  the dataset that unlocks it. Never a degraded version on partial data.
- **Deep-linkable at every step**, so a step is quotable in an issue.

### 5.4 The vernacular ladder

Four mechanisms, in the order a newcomer meets them:

1. **Term-level.** `<gw-term>` everywhere, via the authoritative path at scale (§3.2). Hover
   short, click expanded + related + where-used. Unchanged from SB-05 §5.
2. **Column-level.** The `ⓘ` on a column header opens the same popover pre-expanded, plus
   the OPERATION section scrolled to that field. Vocabulary and mechanism in one action.
3. **Dataset-level.** The intro (§5.1), collapsed by default after first visit
   (localStorage; it is not a number, so it is not in the URL).
4. **Concept-level.** The `SEE` line and the `bites_at[]` links (§5.2).

Two authoring constraints that make the ladder work for the *technical* uninitiated
specifically:

- **Define before use, within the block.** Any intro or concept page using a domain noun
  before that noun's glossary row exists is an authoring defect. **m1 — rev 1 said the R9
  job catches this and it does not.** `test_glossary_coverage.py` checks *referential
  integrity* — that every `x-glasswell-glossary` value and every `meta.labels` value
  resolves to a real row **[V]**. Description-scanning is SB-04 §6.3 item 3 and is **[S]**.
  So today this rule is enforced by review; it becomes mechanical when that check is
  implemented and extended to notebook body text, which §7.1 carries as part of **O-2**.
- **No industry analogies.** Explain with the system's own data and the reader's own
  request. The audience reads a diff faster than a metaphor, and a metaphor is a claim
  nobody can trace — which is the one thing this product does not ship.

---

## 6. Glass-ethos enforcement in the new surface

### 6.1 Every figure handles through — and what the explorer adds to the walker

The R6 walker exists and is real: `tests/contract/test_naked_numbers.py` walks every numeric
leaf of `data`, accepts a figure or a `_lineage` sidecar, and resolves every handle to a
terminal manifest **[V]**. The explorer must not create a surface outside it. Three additions:

1. **The explorer's operation set is walker-covered by construction.** Because every dataset
   is an operation in the served document (§2.3) and the walker exercises every operation in
   the served document **[V]** (`exercised()`, line 127), the explorer cannot render a
   response the walker has not walked. This is a property of the generated-catalogue
   decision, not an extra check — but it is asserted anyway: a test that the set of
   `x-glasswell-dataset` operations is a subset of the walker's exercised set.
2. **A UI-side figure-coverage test.** For each dataset, render a page against the fixture
   and assert every numeric-typed cell is either a `<gw-figure>` with a non-empty `handle`
   or a `<gw-count>` bound to an exemption (§6.3). This catches the failure the server-side
   walker structurally cannot: a number the API served correctly that the UI rendered as
   plain text. `ux-deep-dive` §3 found exactly that on the well card — *"two card values are
   bare numbers rendered outside `<gw-figure>` entirely"* **[V]**.
3. **A label-coverage *report* per dataset (B4).** For each dataset, count column headers
   bound via `x-glasswell-glossary` or `meta.labels`, and emit the percentage. It **fails**
   below the phase floor (§3.2's ratchet: 40 / 70 / 100 on default columns) and otherwise
   **reports**. Rev 1 made it a pass/fail on total coverage, which with 19 bindings across
   201 properties **[V]** would have been red on the first commit — a gate nobody can go
   green on is a gate that gets disabled.
   *`ui/glossary-allowlist.yml` is **[S]*** — SB-05 §5.7 specifies it and no file exists —
   so the unbound treatment (§3.2), not an exemption file, is what carries the residue until
   SB-05's extractor lands.

**m1 — and the R9 check does less than rev 1 said.** `tests/contract/test_glossary_coverage.py`
asserts **referential integrity**: that `x-glasswell-glossary` values and `meta.labels`
values resolve to real `glossary_terms` rows **[V]**. It does **not** scan field descriptions
for domain terms — that is SB-04 §6.3's item 3, and it is **[S]**. So rev 1's claim that a
domain term used in prose before its row exists "fails the R9 coverage job" (§5.4) is false
today; the honest form, now written in §5.4, is that it fails **when SB-04 §6.3 item 3 is
implemented**, and until then it is an authoring convention enforced by review.

### 6.2 m-8 and m-9 — addressed, not inherited

`wave1-gate-findings.md` records two walker gaps **[V]**:

> **m-8:** the R6 walker is vacuous on `/v1/derivations`, `/v1/vintages` and
> `/v1/vintages/{id}` — figure=0, every numeric leaf allowlisted. Not a regression … but
> `/v1/vintages` carries `promotion_derivation_id`, so a `_lineage` sidecar would make the
> gate real.
> **m-9:** the walker is GET-only (`exercised()` reads `item.get("get")`), so POST/DELETE are
> outside R6. … S-K's compute POSTs will return figures and land outside the gate silently.

**The explorer makes m-8 worse before it makes it better, and that must be said plainly.**
Today those three vacuous operations are machine-facing. The explorer promotes them to
browsable datasets with rendered numeric columns (`rows_examined`, `rows_appended`,
`occurrence_count`, `bytes`, `duration_ms`, `output_rows` — all allowlisted **[V]**). A
reader will see numbers in a glass-box product, on a surface whose whole claim is that
numbers carry their provenance, and every one of them will be exempt. Doing nothing is not
available.

Three responses, all in scope for SB-08:

- **A-4 (§7.1), pulled into P-A:** `/v1/vintages` records carry a `_lineage` sidecar keyed on
  `promotion_derivation_id`. This is m-8's own recommendation, it converts a vacuous gate into
  a real one, and rev 2 moves it into the phase where the vintages dataset first ships rather
  than the phase after — because shipping a browsable vintages grid whose every number is
  exempt, and *then* fixing it, is the sequencing that made B2 a blocker.
- **§6.3:** every remaining exempt number renders as `<gw-count>` carrying its exemption
  reason. The exemption stops being invisible.
- **m-9 is stated as an inherited dependency, not solved here.** The explorer runs GETs only
  (§4.5), so it adds no uncovered figure surface. But its API pane *documents* POSTs, and
  when compute POSTs land (S-K, P4) the pane will show figures from operations the walker
  does not exercise. **SB-08 requires m-9 fixed before the explorer's pane documents any POST
  that returns a figure**, and records the dependency here so the sequencing is not
  rediscovered at that phase.

### 6.3 The exemption register becomes a served surface

`tests/contract/non_figure_allowlist.yml` is an excellent document — 40-odd entries, each
with a written reason, guarded by a minimality test that re-walks every served figure and
fails if any pattern would have covered one **[V]**. It is also invisible to every reader of
the product.

**Proposal (§7 amendment A-2):** each exempted numeric property carries
`x-glasswell-not-a-figure: "<reason>"` in the OpenAPI document, with **the same reason string
as the allowlist entry**, and a CI check asserting the two sets are identical — same
pointers, same reasons. Then:

- `<gw-count>` renders the number with an `ⓔ` whose popover is that reason, verbatim.
- The `Problems`-style surface gains a sibling: `?view=explore&tab=learn&slug=what-is-not-a-figure`, a
  concept page generated from the register, listing every exempt class with its reason.
- A reader who asks *"why does this number have no handle when everything else does"* gets
  the project's actual answer, written by the person who made the exemption.

This is *"the kitchen is the product"* (`v0.6 §2.5.2`) applied to the gate itself, and it makes a
broad exemption expensive in the way a hostile reviewer would want: it would have to be
defended in the UI, in the reader's own words.

### 6.4 The kitchen datasets are first-class, not a dev flag

Quarantine, conformance, manifests, derivations and vintages share the rail's second group
and get the same grid, the same facets, the same API pane, and the same visual weight as
wells. SB-05 §3.7 already insists these are *"real views, not JSON dumps behind a dev flag"*
**[V]**; the explorer is where that stops requiring five bespoke views. The auditor persona
(`v0.6 §2.2`) gets a home: five collections, one interaction model, every row navigable to the
rule and the file behind it.

Two specifics carried over: quarantine's summary bar renders share by reason against the
per-basin trigger as a **stated exceedance, never a red alarm** (BRAND.md: nothing uses red
for severity **[V]**); manifest rows and detail are **amber**, the terminal-node colour
(BRAND.md **[V]**), so the reader learns amber means "you have reached the bottom" in the
explorer and in the drawer identically.

### 6.5 No synthetic data, ever

- **Empty is explained.** A dataset with no rows at this as-of renders the reason — source
  not ingested, filter too narrow, as-of precedes the earliest vintage (which is
  `422 as_of_out_of_range`, a real problem type **[V]**) — and never a sample row, never a
  greyed skeleton implying content.
- **Class B datasets show nothing.** They name the phase and the operation, and stop.
- **The walkthroughs run on live data or declare themselves unavailable** (§5.3). W3's
  two-state form is the standing example: it is genuinely unavailable until the Permian is
  ingested, and saying so is a better lesson than a fabricated Texas row.
- **Fixtures never leak into a build a reader can reach.** The explorer's tests use the
  contract fixture; the deployed bundle contains no row data. Asserted by a build test in the
  SB-05 §1.4 pattern.

### 6.6 New anti-stories

Added to `v0.6 §6.1`'s list, in its voice:

- **No dataset without an operation.** If the explorer can list it, an endpoint served it.
- **No filter the API cannot express.** A narrowing the reader cannot reproduce in `curl` is
  a UI feature, which is to say a lie about the contract.
- **No distribution without its population.** A chart over a page says so; a chart over a
  population says which as-of.
- **No page numbers.** The API paginates by cursor; a UI that invents pages is lying about a
  contract it does not control.
- **No exempt number without its exemption on screen.**
- **No annotation prose in the client.** WHAT/WHY/SO comes from glossary and notebook rows,
  or it does not render.

---

## 7. Contract deltas against SB-04

SB-04 §2.1's freeze permits additive change: new endpoints, new optional parameters, new
response fields, new document extensions. **Nothing below removes, renames, narrows or
changes a default.** Each is routed to SB-04 for ratification (SB-04 §13's pattern), not
implemented as a client workaround.

### 7.1 Register — 8 additive amendments, 6 obligations already owed

**M9 — rev 1 sized the UI and nothing else, which is the third instance of this failure
class in this project.** Every row below now carries a session band, and §8's critical-path
total adds them up. Bands are **agent-sessions**; `S` ≤ 1, `M` 2–3, `L` 4–6.

| # | Kind | Delta | Why the explorer needs it | R6 / R5 / R9 obligations | Owner | Sessions |
|---|---|---|---|---|---|---|
| **A-1** | Additive · OpenAPI extension | `x-glasswell-dataset` on browsable GET operations: `{id, title, group, collection_pointer, row_id[], detail_operation, facets[], summary_operation?, columns{default,hidden,sort}, intro, order}` — the M4-extended shape of §2.3 | §2.3 — the catalogue is generated. Without it the explorer hardcodes a dataset list that drifts from the API on the first new endpoint | None — metadata about operations, carrying no figure. Snapshot-gated by SB-04 §7.2 (byte equality, so `x-` extensions are covered — reviewer-verified). Lint: every pointer resolves in the response schema, every facet is a real parameter, `hidden` entries carry a `hidden_reason`, and the ids `map`/`query`/`learn`/`api` are reserved (m6) | Track A2 | **M** — 11 datasets × extension + lint + snapshot regen |
| **A-2** | Additive · OpenAPI extension + CI | `x-glasswell-not-a-figure: "<reason>"` on every numeric property the allowlist exempts, plus a check that the extension set and `non_figure_allowlist.yml` are identical in pointers **and** reasons | §6.3 — the explorer renders exempt numbers and must state why each is exempt, in the exempter's words | Strengthens R6: the exemption register becomes served, and a broad exemption must be defended in the UI. The existing minimality test is unchanged and still binding | Track A2 | **M** — 43 allowlist entries **[V]** mapped onto properties, plus the equality check |
| **A-3** | Additive · new operation | `GET /v1/production` — cross-well monthly production. Params: `api10` (repeatable), `basin`, `operator`, `county`, `land_unit_id`, `formation`, `from`/`to` (`YYYY-MM`), `stream` (repeatable), **`granularity_filter`** (M8 — rc2 §3.6.12 row 6 ratified this name; rev 1 wrote `granularity`), `as_of`, `limit`/`cursor`. Row form: one row per `(api10, pm, stream)` | §2.4 Class C — the population query. **No longer gates the feature** after the B2 reshuffle; it gates the cross-well grid at P-B | **The heaviest obligations in the register.** Every value is a figure object or covered by a per-row `_lineage` sidecar (R6); `granularity` + `reporting_level` + `method` per R5's composition table; `null_semantics` never collapsed; declared total order, cap, `result_cap_exceeded`; a published example so the walker exercises it; `meta.labels` populated | **Track A1b/D0** (owns `routers/production.py`, `marts/**`) | **L** — see the three notes below |
| **A-4** | Additive · response field | `_lineage` sidecar on `/v1/vintages` and `/v1/vintages/{id}` records, keyed on `promotion_derivation_id` | §6.2 — closes m-8's named gap. **Pulled into P-A** so the vintages dataset carries a handle in the phase it first ships | Converts a vacuous R6 gate into a real one on three operations. m-8's own recommendation | Track A2 | **S** |
| **A-5** | Additive · new operations | Generalise the summary pattern: `GET /v1/wells/summary`, `/v1/manifests/summary`, `/v1/derivations/summary`, `/v1/conformance/summary`, each `?group_by=<enum>` returning `{total, as_of, filter_echo, groups:[{key, count, share}]}` — the shape `/v1/quarantine/summary` already serves **[V]** | §3.5 — whole-population distributions. Without it every distribution is page-scoped and captioned as such | Counts and shares are bookkeeping and match existing allowlist patterns `/groups/*/count`, `/groups/*/share`, `/total` **[V]**. **New obligation: a mandatory `population` block** — total, resolved as-of, filter echo — because a share with no denominator is a naked number by another route | Track A2 | **M** — 4 operations on one pattern |
| **A-6** | Additive · response field | Notebook rows gain `kind ∈ {memo, dataset_intro, concept, walkthrough}`, `bites_at[]`, and `steps[]` for walkthroughs | §5.1 — prose is data, not hardcoded strings; walkthrough scripts are data so their assertions are testable | R9 extends to notebook body text when SB-04 §6.3 item 3 exists (m1). R6/R7 apply to notebook rows via SB-04 §4.12 | Track A2 | **S** — *on top of* O-2, which builds the subsystem |
| **A-7** *(new at rev 2)* | Additive · route | **SPA fallback.** Unmatched non-API paths return `index.html`: either a `StaticFiles` subclass overriding `get_response` on 404, or a catch-all mounted before `/` that excludes `/v1/*`, `/openapi.json`, `/docs*`, `/healthz`, `/basemap/*` by prefix. Track O's Caddyfile is the deployed equivalent once DIR-13 puts Caddy in front | **B1** — `app.mount("/", StaticFiles(html=True))` (`api/__init__.py:191` **[V]**) 404s every `/explore/*` path, probe-confirmed. P-A routes around it with `?view=` (§2.1); A-7 is what makes path routes possible **later**, and it is registered rather than assumed | Interacts with the security-header middleware's 404 path (`api/__init__.py:155` **[V]**) — the header stack must still apply. Needs a contract test per excluded prefix, and `/explore/x` must not shadow a future `/v1` addition | Track A2 (route) + Track O (Caddyfile) | **S–M** — the exclusion list and its tests are the work, not the fallback |
| **A-8** *(new at rev 2)* | Additive · OpenAPI extension | `x-glasswell-semantics` on operations: `{<param>: {glossary: <term_id>, so: <sentence>}}` | **B3** — 0/78 parameters carry any `x-glasswell-*` extension **[V]**, and SO is per-operation while a glossary term is shared, so no glossary column can carry it (§4.3) | Every `glossary` value resolves to a `glossary_terms` row (the existing R9 referential check extends to it for free); `so` is prose and is reviewed, not machine-checked. Rendering degrades to WHAT-only where absent, counted by the coverage report | Track A2 (extension + lint) · authoring in **O-6** | **S** extension + lint; the sentences are O-6 |

**Obligations already owed by SB-04/SB-05, not new asks.** Each is **[S]** — specified by a
sibling, no implementation found:

| # | Obligation | Evidence it is unmet | Where the explorer needs it | Degradation if unmet | Owner | Sessions |
|---|---|---|---|---|---|---|
| **O-1** | `x-glasswell-unit` on every numeric property (SB-04 §7.1) | **0 occurrences** in the served snapshot **[V]** | §3.2 figure columns; §4.3 annotation | Units come from the figure object at runtime only; unit-less numeric columns cannot be pre-classified before data arrives | Track A2 | **S–M** |
| **O-2** | `GET /v1/notebook`, `GET /v1/notebook/{slug}` built (SB-04 §4.12, C21) | Absent from the 28 served paths **[V]** | §5 in full | **P-C cannot ship.** The educational layer is prose-as-data or it is hardcoded strings, and hardcoded strings are what DIR-8 ruled against | Track A2 + SB-01 (table) | **M–L** — a table, two endpoints, markdown storage, the `gw:` link validator, R6/R7 on rows. M9 is right that rev 1 hid a subsystem inside a checkbox |
| **O-3** | `x-glasswell-cache`, `x-glasswell-component` (SB-04 §7.1) | 0 occurrences **[V]** | §4.4 response header | Pane shows the raw `Cache-Control`; component attribution dropped | Track A2 | **S** |
| **O-4** | `meta.labels` populated on every operation | **m2 — rev 1's evidence was stale.** `routers/wells.py:36-42` now passes `WELL_LABELS`, so `get_well` returns **5** pointers against `WellDetail`'s **25** properties **[V]**. The gap is smaller and real | §3.2 authoritative label path | Falls back to `x-glasswell-glossary`, then to the client scanner — the residue path used as the default | Track A2 | **S** per operation; rolls up into O-6 |
| **O-5** | Walker covers non-GET operations (m-9) | `exercised()` reads `item.get("get")` **[V]** | §6.2 | The pane must not document a figure-returning POST until fixed; a sequencing constraint on P4, not on SB-08 | Track A2 | **S** |
| **O-6** *(rev 2; denominator confirmed at rev 3)* | **The authoring line — B4's funded half.** Glossary rows plus bindings plus `so` sentences for the surface: `x-glasswell-glossary` on the explorer's default columns, `x-glasswell-semantics` on the facet parameters, and the `glossary_terms` rows both resolve to | Measured: **201 properties across the 16 explorer schemas, 19 bound** **[V]**; **0/78 parameters** annotated **[V]**; §11's rev-1 budget named 12 UI terms, which was an order of magnitude short | §3.2 headers, §4.3 annotations, §5.4's ladder | Without it the ratchet floors in §3.2 cannot be met and the surface ships mostly-unbound — visibly, per the counted-unbound treatment, which is the point of choosing option (b) | SB-01 (rows) + Track A2 (bindings) | **M–L** — **~87–90** default-column bindings and ~40 facet `so` sentences, at ~40 per session for authoring that must be domain-correct. Split one session per phase to match the ratchet. **The P-A plan's challenge independently derived this denominator and confirms §7.1's ~90** — the plan had initially carried 55, which undercounted the seven datasets that fall back to their full schema, and was corrected to this number |

**A-3's three notes, required before ratification (controller ruling).**

1. **Size: L, and it is the largest single item in this document.** New mart read path, a
   `(api10, pm, stream)` total order with its cursor, R5's composition on every row, the
   `null_semantics` and `aggregation` columns, a cap plus `result_cap_exceeded`, a published
   example, and the walker's coverage of it.
2. **Ownership and collision.** It lands in `routers/production.py` and `marts/**` — Track
   A1b/D0's block **[V]** (`CADENCE.md` §2.2), *not* SB-08's. At challenge time the reviewer
   flagged a live collision with `tx-gis-wells`; **re-measured at rev 2, that branch has
   merged and been deleted — `main` is at `debf6cc` and no feature branch remains** **[V]**.
   The collision is therefore historical, but the ownership is not: SB-08 does not edit
   these files, and A-3 is dispatched as A1b/D0 work with SB-08 as the consumer.
3. **It inverts the sidecar economy, and that is a design question, not a detail.** The
   per-well form pays one handle per series (`v0.6 §3.6.2`); a row-per-`(api10, pm, stream)`
   grid at `limit=100` would carry ~100–300 handles per page. §11 item 2 carries this as an
   open item with SB-08's recommendation (rows, with a per-row `_lineage` sidecar keyed on
   the series) and an explicit **[A]** on the payload cost, to be measured, not assumed.

### 7.2 What SB-08 deliberately does not ask for

Each of these was designed and dropped; listing them is the discipline:

- **A dataset-metadata endpoint** (`GET /v1/datasets`). Rejected: the OpenAPI document is
  already the schema-describe surface, it is already snapshot-gated, and the agent already
  reads it. A second metadata surface is a second thing to drift.
- **A `GET /v1/errors` collection.** Rejected: `/v1` already serves the full registry with
  `emitted_by_this_slice` per code **[V]**, and each code resolves at `/v1/errors/{code}`.
  Nothing is missing.
- **A `?fields=` projection parameter.** SB-04 §12 item 5 already cut it, and it would break
  the walker's schema assertions. The column picker is client-side over the full response.
- **A search endpoint across datasets.** SB-04 §12 item 2 cut it; per-resource `q` covers the
  need and the explorer's rail is the navigation.
- **Server-side saved queries.** A URL is the save, and it reproduces on a stranger's
  machine, which a saved object does not.
- **Server-rendered prose in `/explain`.** `v0.6 §3.6.9` forbids it and SB-08 does not
  relitigate it — the pane's annotations come from the glossary and the notebook, both of
  which the agent reads too.
- **A second walker for the UI.** §6.1's UI tests assert rendering, not lineage; lineage has
  one walker (SB-07 §10).
### 7.3 Errata raised against the siblings

Found while writing to freeze level. Each is a sibling's claim that this document tried to
build on and could not:

| # | Where | Defect | Proposed resolution |
|---|---|---|---|
| **X-1** | SB-05 §3.10 | Describes "one headless table (`@tanstack/table-core`) + one virtualizer" as the table system every view uses. **Neither package is installed and no `web/src/tables/` exists** **[V]** | Either install and own it in a named phase, or restate §3.10 as a *contract* (column kinds, cursor rendering) that any implementation satisfies. SB-08 takes the second reading and implements it in `explore/grid/` with no dependency (§3.2 M1) |
| **X-2** | SB-04 §4.2 | The production row's granularity parameter is spelled `granularity`; v0.6-rc2 §3.6.12 row 6 ratified **`granularity_filter`**, with the rationale that filtering on granularity is legitimate while *selecting* it is not **[V]** | SB-04 adopts `granularity_filter`. A-3 already uses it (M8) |
| **X-3** | SB-04 §7.1 | Four required OpenAPI extensions have **0 occurrences** each: `x-glasswell-unit`, `x-glasswell-granularity`, `x-glasswell-cache`, `x-glasswell-component` **[V]**. §7.1 states them as enforced by lint rules that do not exist | Either implement the lint and backfill (O-1, O-3), or mark them as a P-phase obligation with a date. A requirement nothing checks is a requirement nothing has |
| **X-4** | SB-05 §5.7 | `label()`, the Vite extractor, `ui/labels.json` and `ui/glossary-allowlist.yml` are the mechanism R9's UI half rests on. **None exist** **[V]**, and SB-04 §7.4's `stranger` CI job consumes `ui/figure-manifest.json`, which also does not exist | Schedule as SB-05 work. SB-08 does not build another project's toolchain; it uses the counted-unbound treatment (§3.2) until they land |
| **X-5** | `tests/contract/openapi_diff.py` | m9 — the additive/breaking classifier SB-04 §2.1 relies on exists as a module and **is not wired into any check that fails a build**; additivity is human judgment today | Wire it into the contract tier. SB-08's amendments are all additive and would be its first real exercise |

---

## 8. Phasing

Three phases, dispatch-shaped. Sizes are **agent-sessions** with the `S/M/L` band
`CADENCE.md` §2.5 uses; the blueprint's unit is weekends (`v0.6 §7.2`) and one weekend
≈ 2–3 sessions **[A]**.

**M9 — the re-baseline, and where rev 1's optimism came from.** SB-05 §9 re-estimated its own
P2 from the blueprint's **3 weekends to 4–5** on inspection **[V]**, an optimism factor of
≈ 1.5×, and the row it corrected (*"the glossary system alone … is a weekend, and the S2
tuning loop is another"*) is the same shape as rev 1's P-A: a phase that counts the visible
component and not the enabling machinery. Rev 2 applies that factor to the UI bands and adds
the API-track rows that rev 1 omitted entirely.

**Critical path, published.** The API-track amendments are on a different track and can run
concurrently with UI work, but a phase cannot exit ahead of its blocking amendments:

| Phase | UI sessions | Blocking API-track sessions | Phase total (sequential) |
|---|---|---|---|
| **Seam** (§8.4) | 1 | — | **1** |
| **P-A** | 5 | A-1 (M, 3) · A-2 (M, 2) · A-4 (S, 1) — 6 | **11** |
| **P-B** | 5 | A-3 (L, 5) · A-5 (M, 2) — 7 | **12** |
| **P-C** | 4 | O-2 (M–L, 5) · A-6 (S, 1) · A-8 ext (S, 1) · Track O e2e job (S–M, 2) — 9 | **13** |
| **O-6 authoring** | — | 4, one per phase plus a closing pass | **4, parallel** |
| | | | **≈ 36 sessions ≈ 12–15 weekends** |

Rev 1's implied total was 15–21 sessions and counted no API work. **The honest number is
about double**, and the largest single contributor is A-3 plus the notebook subsystem —
neither of which is explorer code. If that total is unacceptable, §8.5's cut line is where
the conversation happens, not inside a phase.

### 8.1 P-A — shell, catalogue, figure grid, pane (read-only)

**Contents.** The seam (§8.4); the `?view=explore` shell and three-tab frame; the generated
catalogue from `x-glasswell-dataset`; the rail with all three honesty classes; the grid with
its six column kinds and the counted-unbound header treatment; `<gw-count>`; row detail;
join-by-navigation chips; the API pane's REQUEST / OPERATION / RESPONSE sections, read-only
(no runner); map ↔ explorer deep links both directions.

**Datasets in P-A — eleven, and three of them carry figures (B2).** `wells`, **`production`
(per well)**, **`production_pools`**, `quarantine`, `conformance`, `manifests`,
`derivations`, `vintages`, `glossary`, `sources`, `problems`. The two production datasets
are the reason this phase demonstrates the thesis rather than describing it: real figure
objects, real `_lineage` sidecars, real `null_semantics`, and **W1 deliverable at P-A**
rather than deferred to P-C.

**Depends on:** A-1 (blocking), A-2 (blocking for `<gw-count>`), **A-4 (pulled forward)**,
O-1 (degrades §3.2/§4.3), O-6 pass 1 (the 40 % ratchet floor).

**Acceptance.**
1. Every P-A dataset renders, filters, paginates and deep-links; a shared URL reconstructs
   dataset, filters, cursor page, pane section, tab and `as_of` exactly — including a
   **repeated** filter (`f.stream=oil&f.stream=gas`), which is M2's regression.
2. The rendered curl in REQUEST is **byte-identical in URL** to the request the grid issued —
   asserted by test, not by eye.
3. **≥ 40 % of default column headers are glossary-bound**, and every unbound header renders
   the explicit unbound treatment. The coverage report prints per-dataset percentages.
4. Every numeric cell is a `<gw-figure>` with a handle or a `<gw-count>` with an exemption
   reason; **at least one dataset renders real figures with real handles** (the B2 gate).
5. `x-glasswell-dataset` operations ⊆ walker-exercised operations.
6. `explore/guardrails.test.ts` green: no `fetch(` under `explore/`, every `operationId`
   resolves in the snapshot, no long domain-prose literals, and `map/map.ts` absent from the
   entry chunk's static graph (m7).
7. Map→explorer and explorer→map preserve `as_of` and push history.
8. **Shell budget measured and recorded** in `web/PERF.md`: the explorer route's JS, gzipped,
   excluding the dynamically-imported map chunk. **The budget is set from the measurement,
   not before it** — M1 is right that an unenforced number is not a budget, and the current
   main chunk is 1,224,213 bytes **[V]**, so the split has to be measured to mean anything.

**DIR-11 evidence.** Reviewing agent, not the implementer. **1600 / 1366 / 1024** × both
themes × real ND data. Required frames: catalogue landing; wells grid; **the production grid
showing figure chips and the state strip**; quarantine grid with facets applied; a row detail
expanded; the pane at each of its three layout modes; the drawer open over the pane at 1600;
a header showing bound and unbound columns side by side; the 390 fallback. Judged against
BRAND.md — amber for manifest surfaces, no red for severity, and legibility of the monospace
request block at actual rendered size.

**Size: 5 UI sessions** (rev 1 said 3–4; re-baselined per M9 for the grid built without a
table library, the two production datasets, and the counted-unbound treatment).

### 8.2 P-B — query workspace, visualisation, runner, walker coverage

**Contents.** The Query tab (full parameter form, session history, as-of compare, export
staging); the cursor surface with decode, the uncursored form, and "break it on purpose";
column distributions with the population rule and its treatment test; series preview on row
selection; the API pane's PROBLEMS section; the in-page runner under §4.5's ruling; the
explorer's walker additions and the A-2 binding check; `?format=csv` where supported; **the
cross-well `production` dataset when A-3 lands.**

**Depends on:** A-3 (the cross-well grid only — everything else in P-B is independent of it),
A-5 (degrades to page-scoped distributions), O-6 pass 2 (70 % floor).

**Acceptance.**
1. The cursor decoder round-trips a server-minted cursor; "break it on purpose" produces a
   real `422 cursor_query_mismatch`; `vintages` renders the uncursored form (m10).
2. Every distribution carries its population statement; `treatmentFor(populationKind)` fails
   if two kinds render alike.
3. **The runner refuses five things**, one test each: a non-GET operation; an operation
   absent from the document; a parameter failing schema validation; a cross-origin URL; and
   **an operation whose declared response media type is not JSON** (M5 — `get_tile`,
   `get_manifest_bytes`).
4. The runner's request is the same code path as the grid's — asserted by spying on
   `getEnvelope`, not by inspection.
5. Every problem type an operation declares is listed; at least three are reproducible from
   the UI and render their labelled body. **`rate_limited` is not one of them** and the pane
   says why (`emitted=False` **[V]**).
6. The A-2 binding check fails when a reason string is changed in one file only.
7. ≥ 70 % default-column binding.

**DIR-11 evidence.** **1600 / 1366 / 1024 / 820** × both themes. Required frames: the decoded
cursor block; the uncursored form; a page-scoped distribution beside a population one (the
treatment difference must be visible in a still); the runner before/after; a rendered `422`;
a rendered `403` with no detail; the Query tab's as-of compare with changed cells marked.

**Size: 5 UI sessions.**

### 8.3 P-C — the educational layer

**Contents.** Notebook consumption (dataset intros, concept pages); the six concept pages
authored; the five walkthroughs with their `steps[]` and the assertion harness; the
`what-is-not-a-figure` generated page; the vernacular-ladder wiring; full a11y pass; the
"run as a stranger would" toggle **if** DR-07 has landed, else recorded as deferred.

**Depends on:** **O-2 (`/v1/notebook` built — blocking, and a subsystem, not a checkbox)**,
A-6, A-8's extension, O-6 pass 3, and **a seeded-instance e2e CI job owned by Track O**
(M6 — no e2e job exists in `.github/workflows/` **[V]**, and `make test-e2e` targets the
live deployment, which is a deployment smoke test rather than a commit gate).

**Acceptance.**
1. Every P-A dataset has an intro meeting §5.1's four-part contract; CI asserts presence.
2. All five walkthroughs run green **in the new seeded-instance job**; a deliberately broken
   step turns the suite red (mutation-checked). **If that job does not exist, P-C does not
   exit** — the assertion harness is §0.4's entire justification for not being the cut tour.
3. Every walkthrough step pins an explicit `as_of`; none reads `latest`.
4. W3 renders its ND form and states the Permian gap explicitly; no fabricated second state.
5. 100 % of default column headers bound; ≥ 60 % overall; the coverage percentage is
   published on the scorecard.
6. axe clean on all three tabs; keyboard path through grid → row → chip → drawer → back.
7. Zero hardcoded domain prose in `explore/` — the §2.3 guardrail test, not a lint rule.

**DIR-11 evidence.** **1600 / 1366 / 1024 / 820 / 390** × both themes, plus a **walkthrough
frame set**: every step of W1 and W5 captured in sequence, judged for whether a newcomer
could follow it without prior knowledge. This is the pass that most needs a reviewer who is
not the implementer, because the implementer cannot un-know the domain.

**Size: 4 UI sessions**, of which roughly one is prose authoring rather than code.

### 8.4 File ownership, and the seam — re-derived at rev 2

**SB-08 owns, exclusively and newly:**

```
web/src/explore/**            catalogue, grid, facets, detail, pane, viz, learn
web/src/explore/gw-count.ts   the exemption-bearing number element
web/src/explore/layout.css    the explorer's own z-index ladder and grid layout
web/src/explore/guardrails.test.ts   the M10 source scan
tests/e2e/explore/**          walkthrough assertions (job owned by Track O)
tests/contract/test_dataset_extension.py   A-1/A-2/A-8 checks
```

**SB-08 reads and never edits:** `web/src/card/gw-figure.ts`, `web/src/chart/**`,
`web/src/glossary/**`, `web/src/lineage/drawer.ts`, `web/src/style.css`, `web/src/map/**`,
`web/src/map.css`.

**M3 — rev 1's merge-order rationale was false, and rev 2's re-derivation is stronger than
the reviewer's.** Rev 1 claimed the seam had to wait because `main.ts` and `index.html` were
"exactly the files those branches touch". The reviewer diffed all six in-flight branches and
found **none of them touched either file**, that `index.html` is **Track V-owned** rather
than frozen (`CADENCE.md` §2.2 **[V]**), that the real contested surface was `map.ts` /
`map.css`, and that **`bus.ts` is frozen and rev 1 omitted it** from its own list. All four
corrections stand. Re-measured during this revision, the picture has moved further:

> **`main` is at `debf6cc` and `git for-each-ref refs/heads/` returns `main` alone** **[V]**
> — the increment-3 closeout, the vf6 legend work, the NM spine and the TX slice all landed
> mid-authoring (`c0f157f` and its parents **[V]**), and every feature branch has been
> deleted. **There is no conflict surface at all.**

**Resequencing outcome: the seam lands immediately, as commit zero of P-A.** No train to
wait for, no cross-track handshake, and DIR-13's TLS work is unaffected because it touches
no web file.

**The seam commit, stated in full — five files, and two of them gain new mechanisms.**
Rev 1 said "four files, one commit" and enumerated three (m8):

| File | Ownership | Change |
|---|---|---|
| `web/src/app/state.ts` | **FROZEN** | Add `view`, `tab`, `ds`, `row`, `slug`. **M2: `extra` becomes `Record<string, string[]>`** so repeated filters survive — today `parseState` writes `extra[key] = value` and `serializeState` calls `params.set`, so `f.stream=oil&f.stream=gas` collapses to `gas` **[V]**, probe-confirmed. **Also: `map=` becomes conditional**, since `serializeState` emits a viewport on every URL and an explorer link has no map |
| `web/src/main.ts` | **FROZEN** | One dispatch on `view`; `createMap` becomes a **dynamic `import()`** (m7) |
| `web/index.html` | **Track V** (not frozen — rev 1 had this wrong) | `<div id="gw-explore" hidden>` |
| `web/src/api/client.ts` | **FROZEN** | **M5: `getEnvelope` gains an optional out-parameter** carrying `{status, headers, elapsed_ms}`, additively, so §4.4's response header is buildable |
| `web/src/bus.ts` | **FROZEN** | Read-only — but named here because rev 1 omitted it from the frozen list and the explorer's "show on map" uses `selectWell`/`flyTo` **[V]** |

Two of these are **new mechanisms in frozen files**, not passthroughs, and rev 2 says so
rather than filing them as plumbing: multi-valued URL state, and response metadata on the
API client. Each ships with its own tests in the seam commit, announced to the controller
per `CADENCE.md` §2.3. **From that commit forward SB-08 touches no frozen file.**

**API-side deltas are not SB-08's files.** A-1/A-2/A-4/A-5/A-6/A-7/A-8 are Track A2's block;
A-3 is Track A1b/D0's; the e2e job is Track O's **[V]**. SB-08 is the consumer and does not
edit them — which is why §7.1 gives every one an owner and a session band.

### 8.5 The cut line

Under compression, in cut order — first cut first:

0. **A-3 and the cross-well grid** — cut first at rev 2, which is the whole point of the B2
   reshuffle. It is the single largest item in §7.1 (**L**, another track's files), and after
   P-A ships per-well production the surface still demonstrates every claim it makes. The
   rail carries it as a stated Class C gap. Rev 1 had this on the critical path.
1. **A-5 and whole-population distributions.** Page-scoped distributions with honest captions
   survive; the lesson is intact and slightly weaker.
2. **The Query tab's as-of compare.** W2 teaches the same thing with two browser tabs.
3. **W3 and W5.** W1, W2 and W4 cover trace, vintage and kitchen — the three Mandate-B
   claims.
4. **Series preview on row selection.** The well card already renders series; the explorer
   can link to it.
5. **The in-page runner.** Copy-to-clipboard plus a terminal is the fallback, and it is what
   S1's stranger does anyway.
6. **The Query tab entirely**, folding session history into the pane.

**Never cut, in any compression** — these are the surface's reason to exist:
the REQUEST block; the counted-unbound column treatment (the *mechanism*, whatever the
coverage percentage is); the cursor surface; `<gw-count>` with its exemption reason; the
walker additions (§6.1); **the per-well production dataset**, without which no figure carries
a handle anywhere in the surface; dataset intros; W1.

**And one thing that must be cut together or not at all:** the walkthroughs and their
assertion harness. §0.4's argument that §5.3 is not SB-05 §13's rejected onboarding tour
rests entirely on the assertions. Shipping the sequences without the harness — as a schedule
squeeze would tempt — converts them into the cut item, so the cut order pairs them: W3 and W5
go before the harness does, and if the harness goes, all five go with it.

---

## 9. Test strategy (DIR-10)

Written with or before the implementation, per phase.

| Tier | Harness | What it must cover |
|---|---|---|
| **Unit (vitest)** | happy-dom | Catalogue construction from an OpenAPI fixture (including a malformed `x-glasswell-dataset` → dataset omitted, not crashed); facet-control selection per parameter schema; URL ↔ state round-trip for `f.*`, `cursor`, `api`, `pane`, `as_of`; cursor decode against a server-minted fixture cursor; `treatmentFor(populationKind)` distinctness; column-kind classification; `<gw-count>` renders its reason; the z-index ladder ordering |
| **Component (vitest)** | happy-dom + MSW | Grid renders every column kind from a real envelope fixture; row detail from a detail-operation fixture; the pane's four sections from one response; empty and problem states |
| **Contract (pytest)** | TestClient | `x-glasswell-dataset` well-formedness: `row_id` resolves in the response schema, `facets[]` are declared parameters, `detail_operation`/`summary_operation` exist; `x-glasswell-not-a-figure` set == `non_figure_allowlist.yml` set (pointers **and** reasons); dataset operations ⊆ walker-exercised operations |
| **E2E (Playwright)** | **seeded ephemeral instance — a job that does not exist yet (M6)** | Each walkthrough's vintage-pinned `steps[]` assertions; the request-block URL equals the issued request URL; **runner refusals (five cases, including the non-JSON media type)**; "break it on purpose" produces a real 422; map↔explorer `as_of` preservation; keyboard path |
| **Guardrail (vitest + `node:fs`)** | no browser | **M10, replacing rev 1's ESLint rules** — ESLint is absent from this repo **[V]**. Scans `web/src/explore/` for `fetch(`, unresolvable `operationId` literals, absolute URLs, and long domain-prose literals; asserts `map/map.ts` is outside the entry chunk's static graph (m7). Same pattern as the existing `web/src/build.test.ts` **[V]** |
| **Visual (DIR-11)** | headless capture, reviewer-judged | §8's per-phase frame lists |

**The e2e tier's honest status.** `.github/workflows/` runs `python`, `web`, `shell` and
`collateral` — **no e2e job** **[V]** — and `make test-e2e` targets the deployed instance,
which makes it a deployment smoke test rather than a commit gate. The seeded-instance job is
a **P-C dependency owned by Track O** (§8.3), sized in §8's critical path. Until it exists,
every "fails the build" claim in this document that depends on the browser is written as
what it is: a test a human runs.

Three tests that exist because a hostile reviewer would ask for them specifically:

- **Mutation check on the walkthrough harness.** Break one `assert` deliberately; the suite
  must go red. `wave1-gate-findings.md` shows repeatedly that a passing test for behaviour
  that does not exist is the recurring defect class here — `basemap.test.ts:94-99` asserting
  a `fallback` field with zero non-test consumers **[V]** is the exemplar.
- **A drift test on the catalogue.** Add a dataset extension for an operation that does not
  exist; the build must fail rather than the rail rendering a dead entry.
- **A schema-shape test on the facet generator (m5).** Five real parameter schemas lifted
  from the committed snapshot — an `anyOf` optional enum, an `anyOf` optional date, an
  `anyOf` optional string, a bare required integer with `maximum`, and a repeatable array —
  each asserting the control kind chosen. A FastAPI upgrade that changes optional
  serialisation then breaks a test instead of silently degrading every filter to a text box.

---

## 10. Rejected alternatives

- **A separate documentation site (Docusaurus / mkdocs / Redoc).** Drifts from the served
  document by construction, and cannot show the reader's own `as_of`, key or row.
- **Embedding Swagger UI as the API guide.** `/docs` already exists **[V]**
  (`api/__init__.py:95`) and is operation-centric with no data context; it renders no
  `<gw-term>` or `<gw-figure>`, and it teaches types where the problem is semantics (§4.3).
- **A notebook-style REPL (Jupyter / Observable / in-page console).** Arbitrary code needs
  `unsafe-eval` against a deliberately tight CSP (SB-05 §1.5), and it teaches a notebook
  rather than the API — which the reader already has, via curl and the document (S1).
- **A GraphiQL-style explorer.** SB-04 §11 rejected GraphQL (one flexible endpoint defeats
  R6's per-operation obligations); a GraphiQL clone over REST invents that query language in
  the client anyway.
- **A SQL console over a read replica.** The fastest available way to serve a naked number,
  bypassing every conformance rule, granularity flag and vintage resolution.
- **A fourth "API" tab.** The silo the ask forbids, and a second implementation of the pane.
- **A bespoke glossary browser beside the dataset browser.** Two implementations of one thing
  (§2.2).
- **Client-side joins across datasets.** Produces numbers no endpoint served — `v0.6 §6.1`
  inverted. Join-by-navigation keeps every hop a request (§3.3).
- **Annotations auto-generated from Pydantic docstrings alone.** Types are not semantics;
  `report_vintage` needs a sentence about restatements, and it belongs in the glossary where
  the agent reads it too.

---

## 11. Open items handed back

| # | Item | Owner | Why it is not decided here |
|---|---|---|---|
| 1 | **Ratify A-1 … A-8** (eight, after rev 2 adds A-7 and A-8) | **SB-04**, then SB-00 | Additive to a frozen surface; SB-04 owns the catalog and the extension vocabulary. A-3 carries its three pre-ratification notes in §7.1 |
| 2 | **A-3's shape** — row-per-`(api10, pm, stream)` vs the column-oriented sidecar form `/wells/{api10}/production` already uses **[V]** | SB-04 + SB-01 | A grid wants rows; the sidecar economy wants columns. **SB-08 recommends rows with a per-row `_lineage` sidecar keyed on the series**, but a 100-row page then carries ~100–300 handles against the current 3, and that payload cost is unmeasured **[A]**. It is a design decision, not a preference |
| 3 | **O-2 is a subsystem, and it is unscheduled** | SB-00 / phase owner | **P-C cannot ship without it** and rev 1 hid it inside a checkbox (M9). A table, two endpoints, markdown storage, the `gw:` live-link validator and R6/R7 on rows is **M–L**, not a line item. The alternative — hardcoded intro strings — is rejected in §5.1, so this is a scheduling decision with a real number attached |
| 4 | **A seeded-instance e2e CI job** | **Track O** | M6. §0.4's justification for the walkthroughs, §8.3's exit criterion and §9's "failing build" claims all rest on it, and it does not exist **[V]**. It is the single dependency most likely to be assumed rather than scheduled — which is exactly what rev 1 did |
| 5 | **m-9 (walker POST coverage)** before any figure-returning POST is documented in the pane | SB-04 / Track A2 | §6.2; a sequencing constraint on P4, recorded so it is not rediscovered |
| 6 | **DR-07 (fifth Access class)** gates the "run as a stranger" toggle | SB-06 / owner | `NEXT-CYCLE.md:149` **[V]**; deferred in §4.5 rather than half-built |
| 7 | **Whether a rate limiter is built at all** | SB-06 / Track A2 | SB-04 §2.9 specifies one; `errors.py:137` declares `rate_limited` with `emitted=False` **[V]**. §4.5 no longer claims one exists. Either build it or amend SB-04 — a specified control that nothing enforces is worse than a stated absence |
| 8 | **Every `[A]` becomes a measurement:** A-3's payload at 1,000 rows; grid render cost at 1,000 rows × 12 columns against SB-05 §5.4's ≤ 2 ms/batch scanning budget; the explorer route's gzipped shell after the map is dynamically imported (§8.1 acceptance 8); catalogue-build cost from a full document; the weekend↔session conversion | P-A/P-B | An estimate that never becomes a measurement is a guess wearing a costume (SB-05's phrasing, adopted). Rev 1 asserted a 60 KB shell budget it had not measured; rev 2 measures first |
| 9 | **O-6's authoring is content work and needs a person, not a phase** | SB-01 (rows) + owner | ~90 default-column bindings and ~40 facet `so` sentences, measured against 201 properties / 19 bindings / 0 of 78 parameters **[V]**. It must be domain-correct or it fails DIR-1 in the most visible possible place — a glossary that is wrong is worse than a column that is unbound |
| 10 | **Whether the explorer becomes the default landing surface** rather than the map | Owner | `ux-deep-dive` §2.2 scores findability 1/10 on a map-only entry **[V]**, and a catalogue answers *what is in here* better than a map does. Cheap to try now that `view=map` is the default and one character changes it — but it is a positioning call, to be made with P-A in front of you |
| 11 | **`bp:N` line anchors in SB-01…SB-07 no longer resolve** against v0.6-rc2 — housekeeping, not a defect in any decision | SB-00 | Spot-checked at authoring (§ citation convention). Either re-anchor the siblings to sections at the next consolidation, or freeze a line-numbered copy for citations to point at. SB-08 uses sections and is unaffected |
| 12 | **The `[S]` class should propagate to the other sub-blueprints** | SB-00 | Rev 2's own lesson (§ revision log): SB-08 rev 1 cited five pieces of unbuilt sibling machinery as though they were infrastructure, and the reviewer caught every one. SB-01…SB-07 cite each other the same way. A one-pass sweep marking specified-but-unbuilt dependencies would find the same class elsewhere — and §7.3's five errata are the sample that suggests it |

---

*SB-08 specs against `blueprint-v0.6-draft.md` v0.6-rc2, `blueprints/SB-04-api-agent-gateway.md`
and `blueprints/SB-05-map-ui.md`, and no earlier version. Every delta against SB-04 is in §7;
every obligation SB-04 already owes and has not met is in §7.1's second table. There is no
silent divergence, and there is no endpoint invented in the client.*
