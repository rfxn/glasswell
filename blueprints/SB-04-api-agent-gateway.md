# SB-04 — API & Agent Gateway

**Sub-blueprint against `blueprint-v0.6-draft.md` (v0.6). Freeze level.**
Owner: Ryan MacDonald. Component: **C12** (API server) and **C15** (agent gateway),
with serving responsibilities for C25 (glossary) and read surfaces of C1, C4, C5,
C7, C9, C10, C11, C16–C24, C26.

This document is what SB-05 (UI), SB-02/03 (producers) and every agent build
against. It consumes SB-07 §9 (explain/lineage payloads) and SB-06 §1/§5 (identity
edge) as given contracts, and it hands back a numbered errata list (§10) rather
than diverging silently.

**The pressure test is S1** (`bp:99`): *a stranger with the OpenAPI doc and a guest
key reproduces every number in the UI.* Every decision below is answerable to that
sentence. Where a choice was made for developer convenience against S1, it was
reversed.

---

## 0. Scope, obligations, and what this freezes

### 0.1 What SB-04 owns

| Owns | Does not own |
|---|---|
| The FastAPI application, routers, dependency graph, process model | Any transform's content (SB-01/02/03) |
| Response envelope, error model, pagination, versioning, `as_of` placement | Figure-level lineage carriage and chain payloads (SB-07 §9) |
| Access JWT validation *implementation* against SB-06 §5.3 | The Access application, policies, tunnel, Caddy (SB-06) |
| App API keys: issuance, hashing, scope resolution, revocation, rotation | The `api_keys` DDL (SB-01), the on-VM secret placement (SB-06 §8) |
| Tile tokens: minting, signing, validation, martin fronting | martin itself, its Postgres source tables (SB-01/C20) |
| Rate limiting at the origin, idempotency, async job handoff shape | The job runner (C26), systemd units (SB-06) |
| OpenAPI generation, examples, snapshot gate, the S1 stranger CI job | The UI figure manifest that job consumes (SB-05, §7.4) |
| The MCP server, the curated tool set, tool↔endpoint equivalence CI | Agent prompts, client configuration |
| Glossary endpoints and the term index the highlighter consumes (DIR-8) | `glossary_terms` rows and the tooltip component (SB-01, SB-05) |

### 0.2 Requirements this SB satisfies

| Requirement | Source | Satisfied in |
|---|---|---|
| S1 stranger reproduces every UI number | `bp:99` | §2, §7.4, §8 |
| S5 agent passes the 10-question suite via public tools | `bp:103`, `bp:432-443` | §5.4, §5.6 |
| S9 any UI number → raw manifest in ≤3 interactions + one `/explain` | `bp:107` | §2.6, §4.9 |
| S13 every surfaced term resolves through `/v1/glossary` | `bp:111`, DIR-8 | §6 |
| S14 as-of reproducibility | `bp:112`, DIR-2 | §2.5 |
| R5 estimates labelled | `bp:262` | §2.2, §4.2 |
| R6 derivation coverage on every served figure | `bp:263` | §2.2, §8.3 |
| R7 reproducibility / recipes on every artifact-producing call | `bp:264` | §2.7, §4.9 |
| R9 glossary coverage | `bp:271`, DIR-8 | §6, §8.3 |
| Versioning, envelope, errors, pagination, ids, as-of, async | `bp:358-400` | §2 |
| Auth, three scopes, tile entitlement, rate limits, ownership | `bp:402-411`, D-5, D-12 | §3 |
| Curated MCP tools with a CI equivalence report | `bp:426-430`, D-4 | §5 |
| Six CI checks on the API surface | `bp:445-454` | §8 |
| Non-functional budgets are tests | `bp:570-572` | §8.6 |
| DIR-6 auth classes at the origin | DIR-6, SB-06 §5 | §3.1, §3.3 |
| DIR-8 glossary endpoints + highlighter index | DIR-8 | §6 |
| DIR-10 TDD, contract tier, fixtures from real data | DIR-10 | §8 |

### 0.3 Contracts consumed verbatim

1. **SB-07 §9.1** — figure objects and `_lineage`/`_units`/`_basis` sidecars are the
   *only* mechanism by which a served number carries its handle. SB-04 does not
   invent a second one (§10 E-01).
2. **SB-07 §9.2** — `?explain=true` never changes values; it only adds.
3. **SB-07 §9.3** — the Chain JSON is served byte-for-byte as the spine produces it.
4. **SB-07 §9.4** — the nine spine endpoints and their parameters, remounted under
   `/v1` (§4.9).
5. **SB-07 §9.5** — spine ID immutability, `(created_at, id)` cursor convention, and
   the `lineage_unresolved` problem type.
6. **SB-07 §9.6** — `/manifests/{id}` is open to every key; `/manifests/{id}/bytes`
   is owner-scoped unless `redistributable`.
7. **SB-07 §10** — the naked-number harness. SB-04 supplies the app, the fixture
   examples, and `ci/non_figure_allowlist.yml`; it reuses
   `glasswell.lineage.ci.walk_api()` and never writes a second walker.
8. **SB-06 §5.3 / §5.5** — the Access JWT validation table and the
   `request.state.principal` shape. SB-04 implements it; it does not redesign it.
9. **SB-06 §1.3** — bind `127.0.0.1:8000`, deploy at `/opt/glasswell/`, config from
   `/etc/glasswell/{app,access}.env`, rate limits keyed on `principal.id`,
   single origin therefore **no CORS is required or permitted**.
10. **SB-06 §10.4** — the rate-limit table and the loopback-IP gotcha.

---

## 1. Application architecture

### 1.1 Package layout

Mirrors the component inventory (`bp:206-252`) and slots into the repository layout
at `bp:594-595`. One router module per component family, so "which component serves
this endpoint" is answerable by file path rather than by grep.

```
src/glasswell/api/
  app.py            create_app(); ORJSONResponse default; lifespan; router mount
  settings.py       pydantic-settings over /etc/glasswell/{app,access}.env
  envelope.py       Envelope[T], meta assembly, figure()/attach_lineage() re-export
  errors.py         Problem model, handlers, the error registry (§2.4)
  pagination.py     Cursor codec, Page[T], per-endpoint caps
  asof.py           AsOf dependency; resolution against lineage.vintages
  caching.py        ETag derivation, Cache-Control classes (§2.8)
  idempotency.py    Idempotency-Key store and replay
  deps/
    principal.py    access_principal(), api_key(), require_scope(), Entitlements
    stores.py       PgDep (psycopg pool), DuckDep, PostGISDep
    lineage.py      LineageDep (SB-07 lineage_session), ExplainDep
    limits.py       rate_limit() token bucket keyed on principal.id
  routers/
    service.py      GET /v1, /v1/health, /healthz            (C12, C26)
    wells.py        wells, production, completions, neighbors (C5, C6)
    forecasting.py  forecasts, typecurves, analogs, models, benchmarks (C7, C9, C24)
    scenarios.py    scenarios                                 (C11)
    econ.py         decks, assumptions, valuations, sensitivities (C10)
    inventory.py    inventory runs and slots                  (C22, C26)
    operators.py    operators, aliases, league                (C4, C7)
    spatial.py      permits, landunits, spacingunits, formations (C6)
    saved.py        aois, digests, wellsets, rollups          (C23)
    lineage.py      explain, derivations, manifests, recipes, vintages, audit (C16)
    quality.py      quarantine, conformance, scorecard, ledger (C17, C18, C19)
    glossary.py     glossary, glossary index                  (C25)
    notebook.py     notebook memos                            (C21)
    jobs.py         jobs, exports                             (C26)
    tiles.py        tile token, tile proxy, attribute bundles (C20, C6)
    keys.py         API key lifecycle                         (C12)
  schemas/          pydantic v2 models, one module per resource family
  openapi/
    customize.py    examples, error enumeration, x-glasswell-* extensions
    snapshot.py     committed-snapshot diff + additive-only classifier
src/glasswell/agent/
  server.py         MCP server (Streamable HTTP), separate systemd unit
  tools/            one module per curated tool, one schema per tool
  equivalence.py    tool ↔ OpenAPI equivalence report (§5.5)
```

**Rule:** a router module may import from `schemas/`, `deps/`, `envelope`, and the
compute packages it serves. A router may never import another router, and no router
may construct a derivation directly — request-time compute goes through the
`LineageDep` session so SB-07 §1.1's "one mechanism" holds (`sb07:1.1`).

### 1.2 Application construction

```python
def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(
        title="glasswell", version=API_VERSION, openapi_version="3.1.0",
        default_response_class=ORJSONResponse,
        docs_url="/docs", redoc_url=None, openapi_url="/openapi.json",
        lifespan=lifespan,
    )
```

- **`default_response_class=ORJSONResponse`.** orjson is already a pinned dependency
  (`pyproject.toml`). It is not a micro-optimisation here: the attribute-bundle and
  series paths carry the S2/S3 budgets (`bp:80-81`), and orjson's `OPT_SORT_KEYS`
  gives the **stable key order** that D3 response-determinism normalisation (SB-07
  §4.2) is defined against. Response bodies are emitted with sorted keys everywhere.
- **No middleware stack beyond three**: `RequestContextMiddleware` (assigns
  `request_id`, a ULID, and binds structlog context), `PrincipalMiddleware` (calls
  the SB-06 §5.3 validator once and sets `request.state.principal`), and
  `RateLimitMiddleware`. Everything else is a dependency, because dependencies appear
  in the OpenAPI document and middleware does not — and an undocumented behaviour is
  an S1 failure.
- **No `CORSMiddleware`.** SB-06 §1.3 pins a single origin. Adding CORS would be the
  first step toward a second origin that Access does not cover. If a second origin is
  ever wanted, it is an SB-06 change first.
- **Lifespan** opens the psycopg pool (max 10 + 5 overflow, SB-06 §10.4), the DuckDB
  connection, the httpx client used for the martin proxy, and the JWKS cache. It does
  **not** fetch JWKS at startup (SB-06 §5.3 item 1).

### 1.3 Dependency injection

Five injected values, all `Annotated` aliases so a router signature reads as a
contract:

| Alias | Provides | Notes |
|---|---|---|
| `PrincipalDep` | `Principal` per SB-06 §5.5 (`kind`, `id`, `aud`, `exp`) plus SB-04's resolved `scope` and `Entitlements` | Set by middleware; the dependency reads `request.state` so the OpenAPI security scheme is still declared |
| `AsOfDep` | `AsOf(requested, resolved, source_vintages)` | §2.5 |
| `ExplainDep` | `ExplainContext(enabled, depth, collector)` | §2.6; the collector accumulates handles and the envelope resolves them in **one** batched `resolve_chain()` call |
| `StoreDep` | `Stores(pg, duck, postgis)` | Per-request; transaction scope is read-only unless the route declares otherwise |
| `LineageDep` | `LineageSession` from `glasswell.lineage.capture` | Required on every route that computes rather than reads |

The pattern is uniform: **no route body constructs its own principal, vintage, or
lineage session.** A route that does is a review failure, and §8.5's auth-matrix test
catches the principal case mechanically.

### 1.4 Pydantic v2 models are the single schema source

Every request and response is a Pydantic v2 model. There is no hand-written OpenAPI,
no `response_model=None`, and no `dict[str, Any]` on a public response — the OpenAPI
document must be complete enough for S1's stranger, and completeness is achieved by
making the validating model and the published schema the same object.

Field metadata carries the glass-box obligations directly:

```python
class Figure(BaseModel):
    value: Decimal
    unit: Unit
    granularity: Granularity | None = None
    report_vintage: date | None = None
    basis: Literal["oil+condensate", "oil", "gas", "water"] | None = None
    d: Handle
```

```python
cum12_oil: Figure = Field(
    description="Cumulative oil over the first twelve producing months.",
    json_schema_extra={"x-glasswell-glossary": "cum12",
                       "x-glasswell-unit": "bbl",
                       "x-glasswell-granularity": "observed|allocated"},
)
```

Three consequences that make CI mechanical rather than aspirational:

1. `x-glasswell-glossary` on every field is what R9's coverage check walks (§6.3).
   The binding is declared once on the model, not per response, so DIR-8's
   "auto-highlighted from the index, not hand-tagged per view" holds on the API side
   as well as the UI side.
2. `x-glasswell-unit` makes the naked-number harness's Check 5 (SB-07 §10) a schema
   read rather than a runtime guess.
3. A new field with no glossary binding and no unit **fails the build**. That is the
   only enforcement mechanism that survives a solo builder in a hurry.

**Decimal policy (SB-07 §4.4).** Volumes and money are `Decimal` in the model and
serialise as **JSON strings**, never floats. A `field_serializer` emits the declared
scale (`numeric(18,3)` for volumes; `numeric(18,2)` for money). Justification: a
float round-trip breaks D3 response comparison and re-introduces the summation-order
nondeterminism SB-07 §4.4 removed. Floats remain acceptable for model outputs,
feature values, probabilities and geometry — all D2/D3 — and those fields declare
`format: double`.

### 1.5 Process model

One uvicorn process on `127.0.0.1:8000` (SB-06 §1.3), `--workers 1`, behind Caddy.
Concurrency comes from asyncio, not from workers.

The consequence is stated rather than assumed: **any state SB-04 holds in-process is
correct only at one worker.** Rather than depend on that, the two pieces of state
that must survive a restart or a future second worker are backed by PostgreSQL:

| State | Home | Why |
|---|---|---|
| Rate-limit buckets | `api.rate_buckets`, **unlogged** table, one UPSERT per request | Correct at any worker count. Unlogged is deliberate — a restart resetting buckets is acceptable; a wrong limit is not. At ≤120 req/min the write is noise against SB-06's 60-connection budget |
| Idempotency records | `api.idempotency_keys`, logged, 24 h TTL | §2.7's replay guarantee is durable by definition |
| JWKS cache | in-process | Rebuildable in one HTTP call; SB-06 §5.3's stale-serve window covers the restart case |
| Explain chain cache | none | `/explain` is a graph read; SB-07 §1.8 budgets it at depth 5 |

CPU-bound work (scenarios, type curves, sensitivities) runs in a bounded
`ThreadPoolExecutor` sized to 4, leaving headroom under SB-06 §3.7.3's 5-of-8 vCPU
batch cap. Anything whose p95 exceeds 5 s is a job, not a thread (§2.7).

---

## 2. Cross-cutting standards

### 2.1 Versioning

Per `bp:358-360`, made operational.

- All resource paths carry `/v1`. `/openapi.json`, `/docs` and `/healthz` are
  unversioned by design — they describe the service, not a resource.
- **Additive-only within a major**: new endpoints, new optional parameters, new
  response fields, new enum values in a *response* position. Breaking: removing or
  renaming a field, narrowing a type, changing a default, making an optional
  parameter required, adding an enum value in a *request* position that the server
  rejects, or changing a status code for an existing condition.
- `openapi/snapshot.py` diffs the served document against
  `api/openapi_snapshot.json` and classifies each change. Additive changes require
  the snapshot to be regenerated in the same commit; breaking changes fail the build
  unless `API_VERSION` majors. This is the mechanisation of `bp:360`'s "the contract
  cannot drift from the implementation without failing the build".
- Deprecation: the operation gains `deprecated: true`, a `Sunset` header (RFC 8594)
  with the removal date, and a row in `meta.deprecations` on every response that
  touches it. `GET /v1` lists all live deprecations. Minimum notice: one full phase.
- **Phase-gated endpoints are absent from the served document, not stubbed.** An
  endpoint that P2 has not built does not appear in `/openapi.json` and does not
  return `501`. Justification: S1's stranger discovers the API from the document; a
  documented endpoint that cannot answer is worse than an undocumented one, and the
  naked-number harness (SB-07 §10 Check 1) would have nothing to call.
- Recipes record `api_version` alongside `code_version` (`bp:360`).

### 2.2 Response envelope

```json
{
  "data": { },
  "meta": {
    "request_id": "01JBQ7M0Z8K2V4N6X8R0T2Y4W6",
    "as_of": { "requested": "latest", "resolved": "2026-08-01" },
    "source_freshness": {
      "nd_mpr_xlsx": { "retrieval_vintage": "2026-08-18",
                       "declared_vintage": "2026-06", "state": "current" }
    },
    "labels": { "/cum12_oil": "gls_cum12", "/series/water_bbl": "gls_water_cut" },
    "next_cursor": null,
    "warnings": [],
    "deprecations": []
  },
  "links": { "self": "/v1/wells/33053012340000", "next": null,
             "explain": "/v1/explain?h=drv_7QK3M2XR4V9B&depth=full" }
}
```

Inside `data`, lineage carriage is **SB-07 §9.1 verbatim** — figure objects with `d`,
`unit`, `granularity`, `report_vintage`, `basis` for scalars; `_lineage`, `_units`,
`_basis` sidecars for dense series. SB-04 adds no parallel representation
(§10 E-01).

`meta` fields and their justification:

| Field | Always? | Purpose |
|---|---|---|
| `request_id` | yes | ULID; echoed in every problem body and every audit event; the join key for support |
| `as_of.requested` / `as_of.resolved` | on any endpoint that reads vintaged data | The *resolved* vintage is what makes S14 checkable. `requested: "latest"` with `resolved: "2026-08-01"` is a reproducible answer; `latest` alone is not |
| `source_freshness` | on any endpoint whose data derives from a fetched source | Per `bp:544`. Per-source `retrieval_vintage`, `declared_vintage`, and `state` ∈ `current \| stale \| failing` |
| `labels` | yes | JSON Pointer → `glossary_terms.term_id`. **Generated from the Pydantic field metadata (§1.4), never hand-written per response.** This is what makes R9 mechanical and what the agent reads so tool documentation and hover text cannot diverge |
| `next_cursor` | collections only | Null at the end (`bp:386`) |
| `warnings` | yes (may be empty) | Structured: `{code, detail, pointer?}`. Used for explain-budget truncation, wide allocation bounds, thin training support |
| `deprecations` | yes (may be empty) | §2.1 |

`links.explain` is present on every response containing at least one handle and is
pre-built with up to 20 handles — this is the S9 "one `/explain` call" (`bp:107`,
SB-07 §1.8) delivered as a link the UI drawer and the agent both follow without
constructing anything.

**Collections.** `data` is the array itself, not `{items: [...]}`. Pagination state
lives in `meta.next_cursor` and `links.next`. Justification: an agent that has
learned "the list is at `data`" learns it once for the whole API.

**Partial results.** Batch-shaped endpoints (`POST /v1/valuations` over a set,
`GET /v1/wellsets/{id}/rollup`) never fail whole. Each item carries
`{status: "ok"|"error", problem?: Problem}` and the envelope returns `200`. The
partial shape is part of the schema (`bp:382`), so a client discovers it rather than
inferring it from a bad day.

### 2.3 Pagination

Cursor-based on every collection (`bp:384-386`). No offset pagination anywhere.

- `limit`: default **100**. Ceiling **1000**; each endpoint declares its own cap in
  the OpenAPI parameter schema (`maximum`), and spine collections cap at **200** per
  SB-07 §9.5 (§10 E-16). Over the cap is `422 validation_failed`, never a silent clamp
  — a silent clamp is how a stranger concludes a dataset is smaller than it is.
- Every collection declares a **total order**: an explicit sort key plus the resource
  id as tiebreak. Defaults:

| Collection | Default order |
|---|---|
| `/v1/wells` | `(api10 ASC)` |
| `/v1/permits` | `(permit_date DESC, permit_id)` |
| `/v1/operators/league` | `(value DESC, operator_id)` |
| `/v1/manifests` | `(fetched_at DESC, manifest_id)` |
| `/v1/derivations` | `(created_at DESC, derivation_id)` |
| `/v1/audit` | `(occurred_at DESC, event_id)` |
| `/v1/quarantine` | `(last_seen_at DESC, quarantine_id)` |
| `/v1/conformance` | `(effective_from DESC, rule_id)` |
| `/v1/glossary` | `(term ASC, term_id)` |
| `/v1/ledger` | `(published_at DESC, entry_id)` |
| `/v1/jobs` | `(queued_at DESC, job_id)` |
| `/v1/scenarios`, `/v1/aois`, `/v1/wellsets`, `/v1/inventory/runs` | `(created_at DESC, id)` |

- **Cursor format.** `base64url(canonical_json({"k": <sort value>, "t": <tiebreak id>,
  "v": <resolved as_of>, "q": <sha256(normalised query params)[:8]>}))`, built with
  the spine's `canonical_json` so the encoding is the same one the rest of the system
  hashes with.
- The `q` fingerprint covers every parameter except `cursor` and `limit`. A cursor
  presented against different filters returns `422 cursor_query_mismatch`. This is
  not defensive decoration: without it, changing a filter mid-traversal silently
  returns a page from a different result set, which is exactly the class of quiet
  wrongness S1 is meant to catch.
- The cursor pins `as_of`, so **pagination is stable under concurrent ingest**
  (`bp:386`). A restatement landing between page 1 and page 2 does not shift rows.
- The cursor is **not signed**. Justification: it carries no authorisation and no
  secret — it is a `WHERE` clause the client could have written. Signing it would
  imply a trust property it does not have. It *is* strictly parsed: unknown keys,
  wrong types, or a `v` outside the served vintage range are `422 cursor_malformed`.

### 2.4 Error model

RFC 9457 `application/problem+json` (`bp:380-382`).

```json
{
  "type": "https://glasswell.rpx.sh/v1/errors/validation_failed",
  "title": "Request validation failed",
  "status": 422,
  "detail": "limit must be less than or equal to 200",
  "instance": "/v1/derivations",
  "request_id": "01JBQ7M0Z8K2V4N6X8R0T2Y4W6",
  "errors": [{"pointer": "/query/limit", "code": "less_than_equal",
              "detail": "Input should be less than or equal to 200"}]
}
```

`type` URIs are stable and resolvable: `GET /v1/errors/{code}` returns the
human-readable description of the code (and is itself in the OpenAPI document). Every
operation enumerates every problem type it can emit, each with an example
(`bp:382`, and SB-07 §10 Check 1 fails an operation with no example).

**Error registry** — the complete set, frozen. Adding a code is an additive API change
and requires a `/v1/errors/{code}` entry in the same commit.

| Code | Status | Emitted when |
|---|---|---|
| `unauthenticated` | 403 | No Access JWT, invalid signature, bad `aud`/`iss`, `alg` not RS256, expired |
| `forbidden` | 403 | Authenticated but out of scope for the operation |
| `key_required` | 403 | `principal.kind == "service"` with no `X-Glasswell-Key` |
| `key_revoked` | 403 | Key present, hash matches a revoked or expired row |
| `jwks_unavailable` | 503 | No usable Access signing keys and the 24 h stale window has elapsed (SB-06 §5.3 item 3) |
| `not_found` | 404 | Resource absent, **or** present but not visible to this principal (§2.10) |
| `validation_failed` | 422 | Pydantic request validation, including parameter caps |
| `cursor_malformed` | 422 | Undecodable or structurally invalid cursor |
| `cursor_query_mismatch` | 422 | Cursor's `q` fingerprint does not match the request |
| `as_of_out_of_range` | 422 | `as_of` precedes the earliest captured vintage for every contributing source |
| `selector_ambiguous` | 422 | SB-07 §1.3 — a handle selector resolves to more than one figure |
| `lineage_unresolved` | 404 | SB-07 §9.5 — carries `handle`, `last_resolved`, `stop_reason` ∈ `selector_ambiguous \| depth_exceeded \| derivation_swept \| unknown_id`. **An auditor never gets a bare 404** |
| `explain_on_dry_run` | 422 | `?explain=true` combined with `?dry_run=true` (§2.6) |
| `result_cap_exceeded` | 422 | A filter set (type curve, export, attribute bundle) selects more than the endpoint's declared cap; the body states the cap and the selected count |
| `unregistered_artifact` | 409 | D-22 — a request would serve a number from an unregistered artifact |
| `model_not_promoted` | 409 | SB-07 §7 — `resolve_model()` refused a non-promoted model without an explicit `shadow` flag |
| `idempotency_conflict` | 409 | Same `Idempotency-Key`, different request body |
| `idempotency_in_progress` | 409 | Same key, original request still running; carries `Retry-After` |
| `job_not_cancellable` | 409 | `DELETE /v1/jobs/{id}` against a terminal job |
| `tile_token_invalid` | 403 | Signature, expiry, audience or principal binding failed |
| `tile_layer_not_entitled` | 403 | Token valid, requested layer outside its layer set |
| `rate_limited` | 429 | Token bucket exhausted; carries `Retry-After` and the bucket name |
| `payload_too_large` | 413 | Above Caddy's 8 MB cap or an endpoint's own body cap |
| `unsupported_format` | 415 | `?format=` outside the endpoint's declared set |
| `upstream_tile_error` | 502 | martin returned non-2xx to the tile proxy |
| `service_degraded` | 503 | A required store is unavailable |

**The `unauthenticated` exception, stated deliberately.** SB-06 §5.3 requires "403
with no detail body" and "never fall back to anonymous". Reconciliation: the body
*is* `problem+json` — with `type`, `title`, `status`, `instance` and `request_id` —
and **no `detail` and no `errors`**. This satisfies SB-06 (no information about *why*
the token failed, so there is no oracle) and satisfies S1 (the failure is
discoverable and typed). `403` is used rather than `401` throughout: no
`WWW-Authenticate` challenge is meaningful behind Access, and a `401` would invite
clients to build a retry loop against an identity edge that has none.

**Visibility failures return `404`, not `403`** (§2.10). A guest probing for the
owner's scenario ids learns nothing.

### 2.5 `as_of` semantics

Per `bp:392-394` and DIR-2, with the resolution semantics taken from SB-07 §3.3.

- `as_of=<ISO date | ISO timestamp | vintage-id | latest>`, accepted on every read
  endpoint that touches vintaged data. Declared per operation in OpenAPI — an
  endpoint that does not read vintaged data does not accept it, rather than accepting
  and ignoring it.
- **Default is `latest`**, resolved to a concrete vintage and reported in
  `meta.as_of.resolved`. `bp:394` frames the default as "the current published
  vintage, not wall-clock now"; SB-07 §3.3 pins the mechanism as *greatest vintage ≤
  as_of, per (well, month, stream, source)*. Both hold: `latest` means the greatest
  published vintage, and every series additionally carries the `report_vintage`
  actually used per point, so a response can never silently mix vintages
  (SB-07 §9.1).
- `as_of` propagates through the whole request: the observation vintage selected, the
  model whose `training_data_vintage` is at or before it (via `resolve_model()`), the
  conformance rules effective at that time, and the chain `/explain` returns.
- `as_of` earlier than the earliest captured vintage for **every** contributing source
  is `422 as_of_out_of_range` — not an empty result. An empty result is
  indistinguishable from "nothing happened", and 4E.5 is explicit that history not
  snapshotted cannot be reconstructed. Where *some* sources have coverage and others
  do not, the response succeeds and `meta.warnings` names the uncovered sources.
- `as_of` participates in the cursor (§2.3) and in the ETag (§2.8).

### 2.6 `?explain=true` inlining

SB-07 §9.2 verbatim, with SB-04 owning placement and the cost guard.

| Method | Semantics |
|---|---|
| `GET …?explain=true[&explain_depth=N]` | Adds an envelope-level `explain` object: `{"<handle>": <Chain>}` for every handle in the response. `explain_depth` default **3**, max **8** |
| `POST …?explain=true` | **Post-hoc**: explains the artifact the request created. A POST body is the `params` of a recorded derivation, so `POST /v1/inventory/runs?explain=true` explains the run it just created (§10 E-02) |
| `POST` on pure endpoints (`/v1/sensitivities`, `/v1/valuations` — R3) | Explains each returned row's derivation; identical requests return the identical `derivation_id` by content addressing |
| `GET /v1/explain?h=…&depth=full` | The S9 one-call path; 1–20 handles (§4.9) |
| `?explain=true` **with** `?dry_run=true` | `422 explain_on_dry_run` |

Decisions:

- **`explain` is a fourth top-level envelope key**, sibling to `data`/`meta`/`links`,
  not a `_explain` key inside `data`. Reason: `data` is an array on collections and
  has nowhere to put it. SB-07 §9.2's invariant is preserved exactly — the flag is
  purely additive and **never changes a value** (§10 E-03).
- The `explain_on_dry_run` rejection is what resolves `bp:424`'s worry directly.
  `bp:424` banned `?explain=true` on POST because "explain the run you just created"
  and "explain the run you would create" are different requests. They are — and a dry
  run creates no derivation, so the ambiguity is closed by refusing the one
  combination that is ambiguous, rather than by prohibiting the whole flag and forcing
  every agent into a second round trip. POSTs continue to return derivation handles
  unconditionally, with or without the flag, exactly as `bp:424` requires.
- **Cost guard.** At most **50 distinct handles** are inlined per response. Beyond
  that the response carries a `meta.warnings` entry with code `explain_truncated`,
  the count omitted, and `links.explain` for the remainder. Justification: a
  collection of 1000 wells at depth 8 is a resource-exhaustion surface, and SB-07
  §1.8 already caps depth for the same reason.
- `?explain=true` responses are **never cached** and carry `Cache-Control: no-store`
  (§2.8), so a cached comparison is unaffected by the flag.

### 2.7 Idempotency, async, exports

Per `bp:396-400`.

**Idempotency.** Every POST accepts `Idempotency-Key` (client-generated ULID or UUID).
The record is `(key, principal_id, method, path, sha256(body), response_status,
response_body, created_at)` in `api.idempotency_keys`, TTL 24 h.

- Same key + same body hash → the original response is replayed byte-for-byte, with
  `Idempotency-Replayed: true`.
- Same key + different body hash → `409 idempotency_conflict`.
- Same key, original still in flight → `409 idempotency_in_progress` with
  `Retry-After`.
- The key is scoped to the principal. Two principals may use the same key value
  without collision.
- Absent key on a POST: allowed but discouraged; `meta.warnings` carries
  `idempotency_key_absent` on artifact-creating POSTs. Content addressing means
  "creating the same scenario twice yields one scenario" (`bp:398`) holds anyway for
  the *artifact*; the key exists so the client's retry story is also deterministic.

**Async.** Any operation whose p95 exceeds 5 s returns `202 Accepted` with a
`Location: /v1/jobs/{job_id}` header and a body of
`{"job_id", "state", "links": {"self": "/v1/jobs/{id}"}}`. Covers inventory runs,
model training, benchmark runs, re-promotion, recipe replay, and large exports.

- Job states: `queued → running → succeeded | failed | cancelled`. `progress` is a
  float 0–1 plus a free-text `stage`. `result_ref` names the created artifact;
  `error` is a `Problem`.
- `DELETE /v1/jobs/{id}` cancels a `queued` or `running` job; terminal states return
  `409 job_not_cancellable`.
- **S3's 3 s budget governs a single scenario only.** A township inventory run is a
  job (`bp:399` — this is the D-04 resolution and it is restated here because SB-05
  will otherwise wire the inventory panel to a synchronous expectation).
- Concurrency limits are C26's (`bp:528`): one training job system-wide, at most two
  batch jobs. SB-04 surfaces the refusal as `429 rate_limited` with bucket name
  `jobs.concurrent`, not as a queue that silently grows.

**Exports.** Two paths, and the boundary is declared:

- `?format=csv` on a collection returns `text/csv` for **at most one page** at the
  endpoint's `limit` cap. It is a convenience, not an export.
- `POST /v1/exports` returns a job for anything larger, with `query_ref` naming the
  operation and parameters to replay.

Every export — both paths — carries a provenance header block. For CSV it is leading
`#`-comment lines before the header row; for the async formats it is a sidecar
`manifest.json` in the export bundle. The block states: resolved `as_of`, the
derivation ids covering each column, per-column `granularity` and `unit` per R5, the
recipe id where one exists, and — for inventory exports — the mandatory 4D.3 spacing
assumption and support distribution plus the 4D.5 `not_a_reserves_estimate`
statement. **An export that strips provenance is not an export this system produces**
(`bp:400`), and §8.3 asserts the block's presence in CI rather than trusting it.

### 2.8 ETag and caching

The derivation model makes a large share of this API content-addressed for free, and
declining to use that would be leaving correctness on the table.

Four cache classes, declared per operation in OpenAPI as `x-glasswell-cache`:

| Class | Applies to | Headers |
|---|---|---|
| **immutable** | Any GET whose path ends in a content-addressed id: `/v1/forecasts/{id}`, `/v1/valuations/{id}`, `/v1/typecurves/{id}`, `/v1/decks/{id}`, `/v1/assumptions/{id}`, `/v1/models/{id}`, `/v1/derivations/{id}`, `/v1/manifests/{id}`, `/v1/recipes/{id}`, `/v1/benchmarks/{id}` | `ETag: "<id>"` (strong), `Cache-Control: private, max-age=31536000, immutable` |
| **vintage-pinned** | Any GET with an explicit `as_of` that is not `latest` | `ETag: "<sha256(resolved_as_of, canonical params, api_version)[:16]>"` (strong), `Cache-Control: private, max-age=3600` |
| **revalidate** | Everything else: `as_of=latest` reads, collections, saved objects | `ETag: W/"<sha256(response body)[:16]>"` (weak), `Cache-Control: private, no-cache` |
| **no-store** | `?explain=true`, all POST/PATCH/DELETE responses, `/v1/keys`, `/v1/manifests/{id}/bytes` | `Cache-Control: no-store` |

- `If-None-Match` is honoured on every GET and returns `304` with an empty body. For
  the **immutable** class the handler short-circuits before touching a store — a
  measurable win on the drawer path, where the UI re-fetches the same manifests
  repeatedly while a user walks a chain.
- **Everything is `private`.** Cloudflare Access sits in front, entitlement is
  per-principal, and SB-06 §5.6 step 10 explicitly warns against assuming edge
  caching. `private` means no shared cache stores a response, so no `Vary` on the
  identity headers is needed; `Vary: Accept-Encoding` only.
- Tiles are their own case (§3.4).

### 2.9 Rate limiting at the origin

SB-06 §10.4 is adopted whole, including its decisive observation: **every request
arrives from 127.0.0.1**, so IP-keyed limiting puts the entire internet in one
bucket. Keys are `principal.id` (§10 E-09 records the divergence from `bp:410`).

| Bucket | Limit | Key |
|---|---|---|
| `read.interactive` | 120 req/min | `principal.id` where `kind ∈ {owner, guest, lan}` |
| `read.service` | 60 req/min | `principal.id` where `kind == service` |
| `tiles` | 600 req/min | `principal.id`, any kind |
| `write.jobs` | 5 concurrent | `principal.id` |
| `train` | 1 system-wide | global |
| `global.concurrency` | 32 in-flight | global; `/v1/tiles/*` is **exempt** and carries its own semaphore of 64 |

Implementation: token bucket in `api.rate_buckets` (unlogged), one UPSERT per
request, refill computed from `now - last_refill`. `429` carries `Retry-After`, plus
`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` on every response
so a well-behaved agent can pace itself rather than discover the wall.

The tile exemption from `global.concurrency` is deliberate: a pan issues 20–40
requests (SB-06 §10.4) and would otherwise consume the concurrency budget that the
S3 scenario SLO depends on.

Cloudflare-side limiting on `/v1/*` and `/v1/tiles/*` is the outer layer (§10 E-15
corrects SB-06's `/api/*`).

### 2.10 Ownership and visibility

D-12 (`bp:865`), made mechanical.

- Saved objects — `scenarios`, `aois`, `well_sets`, `inventory_runs` — carry
  `owner_principal` and `visibility ∈ {private, shared-read}`.
- `owner` and `lan` see everything. `guest` and `agent` see public data plus
  `visibility = 'shared-read'` objects (`bp:407`).
- A read of an object outside the principal's visibility returns **`404 not_found`**,
  never `403`. Existence is not disclosed.
- Writes: `owner` and `lan` may write. `agent` may write only if its key carries the
  `write` capability (`bp:407` — "read-only by default, write scope grantable per
  key"). `guest` may never write; guest POST returns `403 forbidden`.
- Every mutation of a saved object increments `revision` and emits an audit event
  (`bp:390`, SB-07 §5.2).
- Ids are never reused (`bp:390`). Mutable objects are ULIDs; immutable artifacts are
  content-addressed with the spine's prefixes.

---

## 3. Authentication and authorisation

Two independent gates, composed. Neither is sufficient alone, and that is the point:
SB-06 §5.3's whole argument is that the origin validating the JWT is the difference
between defense-in-depth and a single point of failure.

**Amended 2026-09-01.** The two-gate composition holds; the identity edge changed. Gate 1
shipped as the application's own session login rather than Cloudflare Access — see §3.1.

### 3.1 Gate 1 — Cloudflare Access JWT at the origin

**Amended 2026-09-01.** Cloudflare Access is **not enabled on this account** and is not
used: `access/apps` and `access/service_tokens` both answer
`403 access.api.error.not_enabled`, and enabling it needs an irreversible team-name choice
plus a second interactive login in front of the application's own (SB-06 §5, amended
2026-08-29). **Gate 1 as shipped is the application's own session login.** Two roles,
`owner` and `viewer`, over a `lineage.users` table; opaque server-side sessions in
`lineage.sessions`; a `__Host-` cookie, `HttpOnly`, `Secure`, `SameSite`; CSRF on every
state-changing route; Argon2id at rest; login throttling with backoff and lockout; uniform
failure responses with no user enumeration. Accounts are **created by the owner only** —
no registration path, no password-reset-by-email — which is the property the Access design
was protecting, preserved without Access. The origin validates a server-side session record
on every request and rejects anything without one, which is the same property "validates
the Access JWT on every request" was buying. §3.2's `api_keys` is retained unchanged as the
non-interactive path, and the static owner key is refused on the tunnel listener, so the
credential with the weakest lifecycle is not reachable from the internet.
`request.state.principal` carries `kind ∈ {owner, viewer, service, lan}`, and **`owner`
versus `viewer` is a column on the users row, not `GLASSWELL_OWNER_EMAILS` in
`/etc/glasswell/app.env` — a table, not config**, because roles are administered at runtime
by the owner and config is not.

**Superseded, and retained for reinstatement.** Everything below in §3.1 describes Gate 1
as ruled and not built. It stands as the design to reinstate should Access ever be enabled,
exactly as SB-06 §5.1–§5.6 do, and is not a description of shipped behaviour.

SB-04 implements SB-06 §5.3's specification exactly. Restated here only where SB-04
adds an implementation obligation:

| Item | Value |
|---|---|
| Header | `Cf-Access-Jwt-Assertion` **only**; the `CF_Authorization` cookie is never consulted |
| Algorithms | Pinned `["RS256"]`; `alg: none` and every HMAC alg rejected explicitly |
| JWKS | `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`; in-process cache, TTL 3600 s, lazy refresh, **serve stale up to 24 h** on refresh failure, then `503 jwks_unavailable` — never "allow" |
| Unknown `kid` | At most one out-of-band refresh per 300 s (token bucket), so forged tokens with random `kid` cannot turn the origin into an outbound amplifier |
| `iss` / `aud` | Exact string comparison against `/etc/glasswell/access.env`; never prefix-matched |
| `exp` / `nbf` / `iat` | Enforced, leeway ≤ 60 s |
| Principal | Exactly one of `email` (human) or `common_name` (service token) must be present |
| LAN bypass | Skipped entirely when `X-Glasswell-Origin: lan` is present — a header only the LAN Caddy listener can set (SB-06 §4.5) |
| HTTP client | 5 s total timeout, TLS verification on, redirects disabled, body capped at 256 KiB |
| Failure | `403 unauthenticated` per §2.4's no-detail form. Never anonymous fallback |

`503` on "no usable keys" is distinguishable in logs from `403` on "invalid token"
(SB-06 §5.3 item 6). SB-04's structlog binding carries `auth_outcome` as a distinct
field so the first real outage is diagnosable.

Result: `request.state.principal` per SB-06 §5.5 — `{kind, id, aud, exp}` — with
`kind ∈ {owner, guest, service, lan}`. `owner` vs `guest` is decided by matching
`email` against `GLASSWELL_OWNER_EMAILS` in `/etc/glasswell/app.env`: **config, not a
table.** Owner-created accounts only; no registration path (SB-06 §5, amended 2026-08-29).

### 3.2 Gate 2 — application API keys

Header **`X-Glasswell-Key`**, never a query parameter (SB-06 §8.3; a query-param token
leaks through access logs and referrers).

**Token format.** `gwk_<key_id_b32>_<secret_b64url>` where `secret` is 32 bytes from
`secrets.token_bytes`. The `key_id` segment is a Crockford-base32 ULID.

**At rest.** Only `sha256(secret)` is stored, in `api_keys.hashed_secret`. Cleartext
is never stored and never logged. Lookup is by `key_id` (indexed), then a
constant-time comparison of the hash — so a full-table hash scan is not needed and
`key_id` is safe to carry in logs and audit events.

**Row shape** (SB-01 owns the DDL; this is the shape, merging `bp:336` with SB-06
§8.3 — §10 E-10):

| Column | Purpose |
|---|---|
| `key_id` | ULID; the loggable half of the token |
| `principal` | The identity this key is bound to: an owner/guest email, or a service-token `common_name` |
| `scope` | `owner` \| `guest` \| `agent` |
| `label` | `<consumer>-<purpose>-<year>`, e.g. `agent-mcp-2026` |
| `capabilities` | text[]; `read` always, `write` grantable per `bp:407` |
| `layer_entitlements` | text[]; the tile layers this key may mint tokens for (`bp:336`) |
| `hashed_secret` | sha256 hex, the only representation at rest |
| `issued_at`, `expires_at`, `revoked_at`, `last_used_at` | Lifecycle and a usable revocation audit |

**Binding.** For `principal.kind == "service"`, the key is **required** (SB-06 §5.5)
*and* `api_keys.principal` must equal the service token's `common_name`. A leaked API
key alone is useless without the Cloudflare service token, and a leaked service token
alone is useless without the key. For `owner`/`guest` the key is optional; when
present it may only **narrow**, never widen (§3.3).

**Fail-safe.** If no key rows exist at all, deny — never default-open (SB-06 §8.3).

**Show-once issuance.** `POST /v1/keys` returns the cleartext secret exactly once, in
the creation response, with `meta.warnings` carrying `secret_shown_once`. No other
endpoint ever returns it, and there is no recovery path. Rotation issues a successor
and auto-revokes the predecessor in one transaction (the `rfxn-infra` runbook shape
SB-06 §8.3 points at). Every issuance, rotation and revocation emits `key.issued` /
`key.revoked` audit events, which SB-07 §12 requires of SB-04. `last_used_at` is
updated at most once per minute per key to keep the write off the hot path.

### 3.3 Scope resolution

```
scope = resolve(principal.kind, key)
```

| `principal.kind` | Key present? | Resulting scope | Notes |
|---|---|---|---|
| `owner` | no | `owner` | Full read/write |
| `owner` | yes | `min(owner, key.scope)` | A narrow key on an owner session is honoured — that is how the owner tests the guest surface |
| `guest` | no | `guest` | Read-only, public + `shared-read` |
| `guest` | yes | `min(guest, key.scope)` | |
| `service` | **required** | `key.scope` ∈ {`guest`, `agent`} | The key decides, not the class — this is what makes S1's non-interactive stranger possible (§10 E-21) |
| `service` | no | — | `403 key_required` |
| `lan` | no | `owner` | Physically gated (SB-06 §4.5). Recorded as an accepted risk: LAN break-glass is full owner |

Capability check per operation: routes declare `require_scope("owner")` /
`require_capability("write")` as dependencies, so the requirement appears in the
OpenAPI security description and the §8.5 auth matrix can enumerate it from the
document rather than from a maintained list.

**Ordering.** Gate 1 runs in middleware before routing. Gate 2 runs as a dependency,
so `403 key_required` is emitted with the operation's `instance` path intact.

### 3.4 Tile tokens and the martin fronting arrangement

D-5 (`bp:409`, `bp:858`) requires that **martin is never exposed directly** and that
layer entitlement is a property of the key. SB-06 §4.5's Caddyfile as written routes
`/tiles/*` straight to martin with no token check, and SB-06 §1.3 forbids SB-04 from
defining routes under `/tiles/*`. Those two positions cannot both stand (§10 E-12).

**Resolution.** martin is removed from public routing entirely. Tiles are served by
SB-04 at `/v1/tiles/...`, and the API process is the only client of
`127.0.0.1:3000`.

**Minting.** `POST /v1/tiles/token` with body `{layers: [str], as_of: <as_of>}`.

- The requested layer set is intersected with the principal's entitlement (the key's
  `layer_entitlements`, or the class default: `owner`/`lan` → all layers, `guest` →
  the `public` layer group, `agent` → key-declared only). An empty intersection is
  `403 tile_layer_not_entitled`.
- Response: `{token, expires_at, layers, as_of}` plus `Cache-Control: no-store`.

**Signing.** Compact JWS, `HS256`, over these claims:

```
{ "aud": "glasswell-tiles", "sub": <principal.id>, "knd": <principal.kind>,
  "lyr": [<sorted layer ids>], "aof": <resolved as_of>,
  "iat": <epoch>, "exp": <iat+300>, "jti": <ulid> }
```

- Key material: 32 random bytes at `/etc/glasswell/tile-signing.key`, mode `0400`,
  owner `glasswell:glasswell` (SB-06 §8.1 placement). Two-key window with `kid` in
  the JOSE header so rotation never invalidates live sessions.
- **TTL 300 s**, exactly `bp:409`'s five minutes. A leaked tile URL expires in
  minutes.
- HS256 rather than RS256: signer and verifier are the same process, so asymmetry
  buys nothing and costs per-tile verification time against a 150 ms p95 budget
  (`bp:572`).

**Presentation.** `X-Glasswell-Tile-Token` header. **Never a path segment and never a
query parameter** — the same reasoning SB-06 §8.3 already applies to API keys, and it
applies harder here because tile URLs are the most-shared URLs in a map product.
MapLibre sets it via `transformRequest`; deck.gl via `loadOptions.fetch`.

**Serving.** `GET /v1/tiles/{layer}/{z}/{x}/{y}.pbf`:

1. Validate the token: signature, `kid`, `aud`, `exp`, and that `sub` equals the
   current request's `principal.id`. A token minted for one principal is unusable by
   another even inside the same Access session.
2. Assert `{layer} ∈ claims.lyr`, else `403 tile_layer_not_entitled`.
3. Reverse-proxy to `http://127.0.0.1:3000/{layer}/{z}/{x}/{y}` over a pooled
   `httpx.AsyncClient`, streaming the body. martin's `ETag` is passed through;
   `Content-Type: application/vnd.mapbox-vector-tile`.
4. `Cache-Control: private, max-age=86400` for geometry layers — they regenerate only
   on GIS refresh (`bp:349`) and are versioned by the `tiles.build` derivation id,
   which is also the strong `ETag`. Non-2xx from martin is `502 upstream_tile_error`.

The proxy runs outside `global.concurrency` with its own semaphore of 64, and the
tile bucket is 600 req/min (§2.9).

**Attribute bundles.** `GET /v1/tiles/attributes` returns the Arrow IPC bundle
deck.gl joins client-side (`bp:350`). Parameters are `layer`, `bbox`, `z`,
`model_id`, `as_of` — **the server derives the key set from the bbox**; the client
never sends a key list, because a viewport key set at 20k laterals would exceed any
URL length (§10 E-19). The bundle is content-addressed over
`(layer, bbox-quantised, z, model_id, resolved as_of, tiles.build id)`, so `ETag` is
strong and `Cache-Control: private, max-age=3600`. Selecting above the declared cap
(default 50,000 features) is `422 result_cap_exceeded` with the count stated — the
measurable form of OQ-14.

Every styling attribute in the bundle carries its own handle in the bundle's schema
metadata, per SB-07 §12's obligation on map-styled numbers. A bundle whose model
column has no handle is a naked number wearing a binary format.

### 3.5 Key management endpoints

`bp:408` requires that "rotation is a documented procedure, not an aspiration" and
SB-07 §12 requires SB-04 to emit `key.issued` / `key.revoked`. Neither is reachable
without endpoints, and `bp:456-502` has none (§10 E-11).

| Method / path | Scope | Notes |
|---|---|---|
| `POST /v1/keys` | `owner` | Body: `principal`, `scope`, `label`, `capabilities`, `layer_entitlements`, `expires_at`. **`201`; the cleartext secret appears here and nowhere else** |
| `GET /v1/keys` | `owner` | Collection; `hashed_secret` never serialised |
| `GET /v1/keys/{key_id}` | `owner` | |
| `POST /v1/keys/{key_id}/rotate` | `owner` | Issues a successor, auto-revokes the predecessor, one transaction, show-once secret |
| `DELETE /v1/keys/{key_id}` | `owner` | Revokes; the row is never deleted |

### 3.6 Registry and account endpoints

**Added 2026-09-02.** The jurisdiction registry and the account surface both shipped
routes this document did not carry. They split cleanly by auth class: the registry is a
read of served reference data, so it takes the same keyed path every other `/v1` GET
takes; every account and session operation is owner-only, because §3.1's whole property
is that accounts are created and revoked by the owner and by nobody else.

| Method / path | Scope | Notes |
|---|---|---|
| `GET /v1/jurisdictions` | keyed (`owner` \| `guest` \| `agent` read) | Registrations resolved under two clocks with their R8 rule set and last measured counts. `as_of` and `explain` apply; a registration published after `as_of` is not served under it |
| `GET /v1/users` | `owner` | Collection, newest first. No password material is serialised; the list answers *who exists*, not *what they know* |
| `POST /v1/users` | `owner` | The only way an account comes into existence after the first: no self-registration, no reset by email. Supply `password` or the server mints one, shown once |
| `PATCH /v1/users/{user_id}` | `owner` | Changes an account's role, or re-enables it |
| `GET /v1/sessions` | `owner` | Live sessions with their account and their standing against the idle and absolute windows. Neither the token, nor its hash, nor the client address appears |
| `DELETE /v1/sessions/{session_id}` | `owner` | Revokes one session. CSRF applies, as on every state-changing route |

---

## 4. Endpoint catalog

### 4.0 Conventions applying to every row

- All GET endpoints obey **R6** (`bp:263`): every served figure carries a derivation
  handle in the SB-07 §9.1 form.
- All artifact-producing endpoints obey **R7** (`bp:264`): a recipe is recorded and
  reachable at `/v1/recipes/{id}`.
- All endpoints whose figures are not observations obey **R5** (`bp:262`):
  `granularity`, `unit`, `report_vintage`, and — where applicable — method identity
  and uncertainty.
- Unless a row says otherwise, every GET accepts `as_of` and `explain`
  (+`explain_depth`), and every collection accepts `limit` and `cursor`.
- Every operation can emit `unauthenticated`, `forbidden`, `rate_limited`,
  `service_degraded`. Only *additional* error cases are listed per row.
- `Served by` uses the component numbers from `bp:206-252`.

### 4.1 Service and meta

| Method / path | Params | Response | Errors | Served by | Obligations |
|---|---|---|---|---|---|
| `GET /openapi.json` | — | OpenAPI 3.1 document | — | C12 | S1 anchor; byte-compared to the committed snapshot (§2.1) |
| `GET /docs` | — | Swagger UI | — | C12 | Behind Access like everything else |
| `GET /v1` | — | Service index: `api_version`, published vintages per source, live deprecations, error-code index, `links` to every resource family | — | C12 | The stranger's entry point |
| `GET /v1/health` | — | Enveloped: per-source freshness, last job state per job type, store reachability; `state ∈ ok\|degraded` — `degraded` when any scheduled job failed or any source is beyond its pull window (`bp:544`) | — | C12, C26 | — |
| `GET /healthz` | — | `{"ok": true}`, no envelope, ~0 cost | — | C12 | SB-06 §1.3's liveness probe. Unauthenticated **only** on the LAN listener (§10 E-14) |
| `GET /v1/errors/{code}` | — | Problem-type description matching the `type` URI | `not_found` | C12 | Makes every `type` URI resolvable |
| `GET /v1/states` | `code` str | Jurisdiction registry rows: API state code, name, regulator, identity scheme, source ids, the rule ids deciding status vocabulary, geometry provenance, liquids basis, production grain and unmapped action, tile layer id and colour, and a measured well count with the date it was measured | `not_found` | C12, C4 | R6, R8; **planned, v0.76.** The registry the promotion, inventory and serving paths read instead of an API-10 prefix (`bp:3.0.1a`) |

### 4.2 Wells and production

| Method / path | Params (type · default · cap) | Response | Errors | Served by | Obligations |
|---|---|---|---|---|---|
| `GET /v1/wells` | `basin` enum · — ; `operator_id` str; `formation_id` str; `county_code` str; `land_unit_id` str; `spacing_unit_id` str; `vintage_from`/`vintage_to` date; `status` enum; `bbox` `minx,miny,maxx,maxy` WGS84 · cap 4°×4°; `q` free-text on well name; `sort` enum(`api10`,`first_production_month`,`operator`) · `api10`; `limit` int · 100 · **1000** | Array of well spine records: `api10`, operator (resolved, with alias provenance and `rollup_mode`), status, spud/completion/first-production, basin, land unit, confidential flag, geometry refs | `validation_failed`, `cursor_*` | C12, C5 | R6 |
| `GET /v1/wells/{api10}` | — | Well header, resolved operator with alias provenance, geometry refs, completion summary, latest forecast ref, `links` to sub-resources | `not_found` | C12, C5, C6 | R6; p95 < 300 ms (`bp:572`) |
| `GET /v1/wells/{api10}/production` | `stream` enum(`oil`,`gas`,`water`,`condensate`) repeatable · all; `from`/`to` production month `YYYY-MM`; `granularity` enum(`observed`,`allocated`,`any`) · `any`; `derived` enum(`gor`,`water_cut`) repeatable · none; `as_of` | Monthly series per stream in the SB-07 §9.1 sidecar form, with per-point `report_vintage` and `null_semantics` ∈ `reported_zero\|no_report\|withheld`; GOR and water-cut as derived series when requested | `not_found`, `as_of_out_of_range` | C12, C5 | R5, R6; U13, U21. **`granularity=allocated` responses carry `allocation_model_id` and `error_bounds` (4F.5)**; single-well leases pass through as `observed` with a 1:1 note (4F.6) |
| `GET /v1/wells/{api10}/completions` | — | Completion events with design fields and **per-field** `null_semantics`; source attribution per field (FracFocus vs TX completion feed vs GIS-derived lateral length) | `not_found` | C12, C5 | R5, R6 |
| `GET /v1/wells/{api10}/neighbors` | `radius_ft` int · 5280 · cap 26400; `formation_id` str; `at_date` date · well's completion date; `limit` int · 50 · 200 | Spatial neighbours with **projected** distances (basin compute CRS from `crs_registry`), completion dates, and the CRS used | `not_found`, `validation_failed` | C12, C6 | R6; distinct from analogs — the response says so in its description. Distances never computed in degrees (`bp:157`) |
| `GET /v1/wells/facets` | `state` str · **required**; `by` enum(`operator`,`county`,`status`,`well_type`,`completion_year`) · **required**; `top` int · 15 · **50**; `q` case-insensitive substring of the value; `sort` enum(`count`,`value`) · `count`; `order` enum(`desc`,`asc`) · `desc` | Ranked buckets with counts and a `/v1/wells` link each; `distinct_values`; a `remainder` naming how many values fell below the cut and how many wells they hold, absent rather than zero when the list is complete; and an `absence` bucket carrying the count, the reason and the rule that decided it, never ranked and never searched | `validation_failed` | C12, C5 | R6, R8. `state` is **required as an R8 constraint, not a UX one**: operator names arrive per source and `lineage.operator_aliases` is empty, so a cross-state sum would be an unmade aliasing decision. `buckets + remainder + absence == wells` without a search, `buckets + remainder == matched_wells` under one, both asserted. Capped at 60 requests per principal per UTC minute |
| `GET /v1/wells/{api10}/forecast` | `model_id` str · resolved from `as_of`; `stream` enum · `oil`; `horizon_months` int · 24 · cap 60 | P10/P50/P90 series, `model_id`, `feature_version`, `training_support` (4A.10), calibration ref, extrapolation flag where beyond the trained horizon (4A.9) | `not_found`, `model_not_promoted`, `unregistered_artifact` | C12, C7 | R5, R6, R7 |

### 4.3 Forecasting artifacts

| Method / path | Params | Response | Errors | Served by | Obligations |
|---|---|---|---|---|---|
| `GET /v1/forecasts/{forecast_id}` | — | Forecast artifact, immutable | `not_found` | C12, C7 | R6, R7; **immutable** cache class |
| `GET /v1/analogs` | **exactly one of** `api10` \| `scenario_id`; `n` int · 10 · cap 50; `metric` enum(`euclidean`,`leaf_cooccurrence`) · `euclidean`; `index_id` str · resolved from `as_of` | Ranked analogs with feature distances, actual outcomes, and the index's `derivation_id` | `validation_failed` (both or neither id), `not_found` | C12, C7 | R6; serves **wells and scenarios** (U17). The index is always persisted (D-23) so results always carry a handle |
| `GET /v1/typecurves` | `filter_spec` (JSON, URL-encoded) or `type_curve_id`; `normalization` enum(`absolute`,`per_1000ft`) · `per_1000ft`; `band` enum(`p10_p90`,`p25_p75`) · `p10_p90`; `min_n` int · 10 | Curve, band, `n`, filter echo, content-addressed `type_curve_id` | `result_cap_exceeded` (filter selects > 20,000 wells), `validation_failed` | C12, C7 | R6, R7; p95 < 2 s at the cap (`bp:572`) |
| `POST /v1/typecurves` | Body: same fields | As above | as above | C12, C7 | R6, R7; POST exists for filter sets too long for a URL (`bp:473`) |
| `GET /v1/typecurves/{type_curve_id}` | — | The artifact | `not_found` | C12, C7 | **immutable** cache class |
| `GET /v1/models` | `basin`; `target` enum(`oil`,`gas`,`water`,`allocation`); `status` enum(`candidate`,`shadow`,`promoted`,`retired`); `limit` · 100 · 200 | Registry entries per SB-07 §7 | — | C12, C24 | R7 |
| `GET /v1/models/{model_id}` | — | Full registry record: training window, `training_data_vintage`, feature version, artifact hash, seeds, `holdout_def`, calibration coverage **by slice** (4A.8), `probe_tolerance`, `error_bounds` for allocation models | `not_found` | C12, C24 | R7; **immutable** |
| `GET /v1/benchmarks` | `basin`; `as_of` | Benchmark run index | — | C12, C9 | R6, R7; S4 |
| `GET /v1/benchmarks/{benchmark_id}` | `slice_by` enum(`operator`,`vintage`,`formation`,`area`,`lateral_bucket`) repeatable | Sliced type-curve vs ML comparison on the identical temporal holdout, with the control always present (4A.5) and the censored share reported (4A.4) | `not_found` | C12, C9 | R6, R7; S4; **immutable** |

### 4.4 Scenarios, economics, sensitivities

| Method / path | Params | Response | Errors | Served by | Obligations |
|---|---|---|---|---|---|
| `POST /v1/scenarios` | Body: `name`, `design` {`lateral_length_ft`, `proppant_lb_per_ft`, `fluid_bbl_per_ft`, `stage_count`, `landing_zone_formation_id`, `spacing_ft`}, `location` {geom \| `land_unit_id`}, `model_id?`, `deck_id?`, `assumption_id?`, `visibility` · `private`. Query: `explain`, `dry_run` | Scenario with forecast, valuation, `training_support`, analog panel | `validation_failed`, `model_not_promoted`, `idempotency_*` | C12, C11 | R3, R6, R7; **S3's 3 s p95 budget lives here** (`bp:472`) |
| `GET /v1/scenarios` · `GET /v1/scenarios/{id}` | visibility-filtered | Scenario records | `not_found` | C12, C11 | R6 |
| `PATCH /v1/scenarios/{id}` | Body: partial `design` / `location` / `name` / `visibility` | New `revision`; **new** forecast and valuation artifacts — prior artifacts are never mutated | `not_found`, `forbidden` | C12, C11 | R3, R6, R7; mutation is an audit event |
| `DELETE /v1/scenarios/{id}` | — | `204`; soft-delete with `deleted_at`, id never reused | `not_found` | C12 | Audit event |
| `GET /v1/decks` · `GET /v1/decks/{deck_id}` | `q`; `limit` · 100 · 200 | Price decks — discoverable because they are user-selectable inputs (`bp:477`). The default deck's provenance is stated, **including that a free-tier strip is unavailable and the default is a flat assumption** (4B.2, OQ-6) | `not_found` | C12, C10 | R5, R6; `{deck_id}` is **immutable** |
| `GET /v1/assumptions` · `GET /v1/assumptions/{assumption_id}` | `state` enum(`ND`,`TX`,`NM`) | Econ assumption sets with per-state severance and ad-valorem defaults; `wi` default 1.00; **`nri` default 0.75 carrying an explicit warning that it is an assumption, not knowledge** (§2.2, 4B.3) | `not_found` | C12, C10 | R5, R6 |
| `POST /v1/valuations` | Body: `forecast_id` \| `forecast_ids[]`, `deck_id`, `assumption_id`, `wi?`, `nri?`, `discount_rate?` · 0.10 | NPV **at P10, P50 and P90 together** (4B.7 — a single-point NPV is never served alone), `breakeven_price` with its method stated (4B.5), `payout_months`, monthly cash flows. Set form returns per-item `status`/`problem` | `not_found`, `validation_failed` | C12, C10 | R3, R5, R6, R7 |
| `GET /v1/valuations/{valuation_id}` | — | The artifact | `not_found` | C12, C10 | **immutable** |
| `POST /v1/sensitivities` | Body: `base_ref` (forecast_id \| valuation_id), `parameters[]` ∈ {`price`,`capex`,`opex`,`water_handling`,`cum12_error`} with `delta` magnitudes | Tornado rows ranked by absolute NPV delta; **the base case and the delta magnitudes are stated in the response** (4B.6) | `not_found`, `validation_failed` | C12, C10 | R3, R6. Pure by R3, so identical requests return the identical `derivation_id` |

### 4.5 Inventory

| Method / path | Params | Response | Errors | Served by | Obligations |
|---|---|---|---|---|---|
| `POST /v1/inventory/runs` | Body: `area_ref` (`land_unit_id`, **system `plss` only** — 4D.4), `spacing_assumption_ft`, `model_id?`, `deck_id?`, `assumption_id?`. Query: `dry_run`, `explain` | `202` + `job_id` + `Location`. With `dry_run=true`: the plan and its inputs, executing nothing | `validation_failed` (non-PLSS `area_ref`), `rate_limited` (`write.jobs`), `explain_on_dry_run` | C12, C22, C26 | R5, R6, R7; **4D.3 and 4D.5 statements mandatory on every response and export** |
| `GET /v1/inventory/runs` · `GET /v1/inventory/runs/{run_id}` | visibility-filtered | Run record: status, spacing assumption, model/deck/assumption refs, **support distribution**, rollup NPV, `not_a_reserves_estimate: true` | `not_found` | C12, C22 | 4D.3, 4D.5; R5, R6 |
| `GET /v1/inventory/runs/{run_id}/slots` | `min_training_support` float; `limit` · 100 · 1000 | Slots with geometry, land unit, forecast ref, valuation ref, `training_support`, `admissibility_flags` | `not_found` | C12, C22 | 4D.1, 4D.2; R5, R6 |
| `DELETE /v1/inventory/runs/{run_id}` | — | `204`; cancels the job if in flight | `not_found`, `job_not_cancellable` | C12, C22, C26 | Audit event |

### 4.6 Operators and activity

| Method / path | Params | Response | Errors | Served by | Obligations |
|---|---|---|---|---|---|
| `GET /v1/operators` · `GET /v1/operators/{operator_id}` | `q`; `basin`; `limit` · 100 · 500 | Canonical operator with aliases (source key, reported name, confidence, method), parent, and `operator_events` history | `not_found` | C12, C4 | R6 |
| `GET /v1/operators/league` | `basin` **required**; `vintage_from`/`vintage_to` date; `metric` enum(`residual_cum12`,`residual_cum12_design_adj`,`raw_cum12_per_kft`) · **`residual_cum12`** (DIR-5); `rollup_mode` enum(`as_reported`,`parent_rollup`) **required — neither is silently the default** (`bp:294`); `min_wells` int · 10; `stream` · `oil`; `limit` · 100 · 500 | Ranked operators with `value`, bootstrap CI (`ci_lo`/`ci_hi`), `n_wells`, the expectation model's `model_id`, and **`raw_cum12_per_kft` alongside, always** (D-17) | `validation_failed` (missing `rollup_mode`) | C12, C7, C4 | R5, R6; DIR-5, D-17 |
| `GET /v1/permits` | `basin`; `operator_id`; `from`/`to` date; `bbox`; `land_unit_id`; `status`; `limit` · 100 · 1000 | Permits with geometry and status | — | C12, C6 | R6 |
| `GET /v1/activity/duc` | `basin`; `operator_id`; `bbox`; `age_window_days` int · 365 | DUC proxy: permitted or spudded, not yet reporting production, within the stated age window. **The proxy's definition is served from the glossary and the response links to it** (U8) | — | C12, C5 | R5 (`granularity = modelled`), R6. Labelled a proxy everywhere it appears |

### 4.7 Spatial reference

| Method / path | Params | Response | Errors | Served by | Obligations |
|---|---|---|---|---|---|
| `GET /v1/landunits` · `GET /v1/landunits/{land_unit_id}` | `system` enum(`plss`,`tx_abstract`,`nm_plss`); `state`; `bbox`; `label`; `parent_land_unit_id`; `limit` · 100 · 1000 | PLSS sections and townships, TX abstracts, NM units, with `area_acres` and parent refs | `not_found` | C12, C6 | R6 |
| `GET /v1/spacingunits` | `basin`; `state`; `formation_id`; `bbox`; `limit` · 100 · 1000 | Spacing units with `order_ref` | — | C12, C6 | R6 |
| `GET /v1/formations` | `basin`; `q`; `limit` · 100 · 500 | Canonical formations with alias counts | — | C12, C4 | R6 |
| `GET /v1/crs` | `basin` | `crs_registry` rows: compute CRS per basin, storage always 4326 | — | C12, C6 | R6, R8; the CRS every projected distance in the API was computed in |

### 4.8 Saved objects

| Method / path | Params | Response | Errors | Served by | Obligations |
|---|---|---|---|---|---|
| `POST /v1/aois` · `GET /v1/aois` · `GET/PATCH/DELETE /v1/aois/{aoi_id}` | Body: `name`, `geom` (GeoJSON Polygon, ≤ 5000 vertices), `visibility` | AOI CRUD, `revision` on every mutation | `not_found`, `forbidden`, `validation_failed` | C12, C23 | R6; **symmetric CRUD** — every add-path input form works on the remove path |
| `GET /v1/aois/{aoi_id}/digests` | `period_start`/`period_end`; `limit` · 100 · 200 | Digest index | `not_found` | C12, C23 | R6 |
| `GET /v1/aois/{aoi_id}/digest` | `since` date | Current digest: new permits and new first-production wells inside the polygon, **plus the `freshness_window` per source that was actually diffed** (`bp:544`) — a digest generated against stale data says so | `not_found` | C12, C23 | R6; U16 |
| `POST /v1/wellsets` · `GET /v1/wellsets` · `GET/PATCH/DELETE /v1/wellsets/{set_id}` | Body: `name`, `api10s[]` (≤ 5000), `visibility` | Set CRUD | `not_found`, `forbidden`, `validation_failed` | C12 | R6; symmetric CRUD |
| `GET /v1/wellsets/{set_id}/rollup` | `deck_id`; `assumption_id`; `include` enum(`production`,`forecast`,`valuation`,`tornado`) repeatable · all | Rollup of production, forecast, valuation and tornado, with **granularity flags per member well** per R5 — a set mixing observed ND and allocated TX wells says so per component | `not_found` | C12, C10 | R5, R6, R7; U20 |

### 4.9 Lineage spine — SB-07 §9.4 remounted under `/v1`

Handlers are the spine's; SB-04 supplies transport, auth, envelope and pagination
only (SB-07 §9, first paragraph).

| Method / path | Params | Response | Errors | Served by | Obligations |
|---|---|---|---|---|---|
| `GET /v1/explain` | `h` handle · **repeatable 1–20 · required**; `depth` int \| `full` · 3 · **cap 8**; `format` enum(`json`,`dot`) · `json` | `{chains: [Chain]}` per SB-07 §9.3 — nodes, edges, terminals, recipe, per-node `explanation` | `lineage_unresolved`, `selector_ambiguous`, `validation_failed` | C12, C16 | S9; depth-5 p95 < 500 ms (`bp:572`) |
| `GET /v1/derivations/{derivation_id}` | `include` enum(`inputs`,`rules`,`recipe`) repeatable | Derivation record | `not_found` | C12, C16 | **immutable** |
| `GET /v1/derivations` | `operation`; `output_dataset`; `since`/`until`; `model_id`; `rule_id`; `correlation_id`; `limit` · 100 · **200** | Collection | — | C12, C16 | §10 E-04 (absent from `bp:456-502`) |
| `GET /v1/manifests` | `source_id`; `source_key`; `vintage_from`/`vintage_to`; `head_only` bool · false; `limit` · 100 · 200 | Manifest records | — | C12, C1 | R1 |
| `GET /v1/manifests/{manifest_id}` | — | Full record + `supersedes`/`superseded_by` + `decompressed_inventory` members. **Terminal node of every lineage chain** | `not_found` | C12, C1 | R1; **immutable**; open to every key (SB-07 §9.6) |
| `GET /v1/manifests/{manifest_id}/bytes` | — | Raw passthrough | `forbidden` unless `owner` **or** `manifest.redistributable` | C12, C1 | SB-07 §9.6; `no-store`. The auditor's need is verifiability — the checksum plus the exact `acquisition_url` lets them re-fetch and hash it themselves |
| `GET /v1/recipes/{recipe_id}` | — | Recipe document (SB-07 §4.1) incl. `determinism_class`, `environment`, `seeds`, `replay` CLI string | `not_found` | C12, C16 | R7; **immutable** |
| `POST /v1/recipes/{recipe_id}/replay` | — | `202` + `job_id`; on completion, the per-artifact hash comparison table and pass/fail per the determinism class | `not_found`, `rate_limited` | C12, C16, C26 | R7; U11. **Owner scope only.** §10 E-06 |
| `GET /v1/vintages` · `GET /v1/vintages/{vintage_id}` | `source_id`; `from`/`to` | Vintage records incl. `restatement_summary` | `not_found` | C12, C16 | DIR-2; §10 E-04 |
| `GET /v1/audit` | `since`/`until`; `event_type`; `subject_type`; `subject_id`; `correlation_id`; `actor`; `limit` · 100 · 200 | Append-only event stream | — | C12, C16 | R2 |

Note on `bp:493`: v0.6 describes `/v1/audit` as "hash-chained". SB-07 §14 item 1 cut
the hash chain deliberately (one writer who is also the auditor; role grants plus an
append-only trigger are the guarantee). The endpoint therefore serves
`prev_event_hash`/`event_hash` as **absent**, and the response description states the
enforcement mechanism instead of implying a chain that does not exist (§10 E-22).

### 4.10 Quality, conformance, track record

| Method / path | Params | Response | Errors | Served by | Obligations |
|---|---|---|---|---|---|
| `GET /v1/quarantine` | `source_id`; `reason_code` enum (SB-07 §8.2); `rule_id`; `state` enum(`open`,`released`,`accepted_loss`,`superseded`); `stage` enum(`parse`,`validate`,`conform`,`join`); `limit` · 100 · 200 | Rejected rows with reason, the rule that rejected them, `occurrence_count`, and lifecycle state | — | C12, C17 | "The kitchen is the product" (`bp:133`) |
| `GET /v1/quarantine/{quarantine_id}` | — | Row + `row_payload` + first/last seen manifests | `not_found` | C12, C17 | U12 |
| `GET /v1/quarantine/summary` | `basin`; `source_id`; `vintage`; `group_by` enum(`reason_code`,`stage`) | Share rows for the scorecard, **sliced by basin** (D-17's per-basin trigger) | — | C12, C17, C18 | §10 E-04 |
| `POST /v1/quarantine/{quarantine_id}/reprocess` | — | `202` + `job_id`; re-runs promotion **from the manifest**, never from `row_payload` (SB-07 §8.3) | `not_found`, `rate_limited` | C12, C17, C26 | Owner scope; audit event |
| `GET /v1/conformance` | `source_id`; `entity`; `field`; `kind` enum (SB-07 §6.1's eight); `family`; `effective_at` date; `limit` · 100 · 200 | Rule rows with `rule_text`, `rationale`, `evidence_url`, `spec` | — | C12, C4 | R8; S11 |
| `GET /v1/conformance/{rule_id}` | `include=applied_by` | Rule + reverse index of citing derivations — **the U21 path** | `not_found` | C12, C4 | R8; S11; **immutable** (rules are append-only) |
| `GET /v1/scorecard` | `as_of`; `scope` enum(`system`,`basin`,`source`); `basin`; `source_id` | Quality metrics **each with a derivation**: source coverage and freshness, quarantine share by reason and basin, wellbore-quarantine share against the per-basin trigger (3.0.5), withheld/confidential share, allocation error bounds, calibration coverage by slice, conformance-rule coverage and staleness, **DOCUMENTED/`code_ref` rule share** (R10 mitigation), glossary coverage | — | C12, C18 | S8; R6 |
| `GET /v1/ledger` | `api10`; `model_id`; `graded` bool; `from`/`to`; `limit` · 100 · 200 | Forecast track record | — | C12, C19 | S7 |
| `GET /v1/ledger/{entry_id}` | — | Entry with **both** `trained_on_vintage` and `graded_against_vintage`, and grading reported both as-of-vintage **and** against current actuals (4A.14, SB-07 §3.5) | `not_found` | C12, C19 | S7; DIR-2 |

### 4.11 Glossary — see §6

| Method / path | Params | Response | Served by |
|---|---|---|---|
| `GET /v1/glossary` | `q`; `domain_tag`; `limit` · 100 · 500 | Term collection | C12, C25 |
| `GET /v1/glossary/{term_id_or_term}` | — | Term + expanded definition + related terms + `appears_in[]` | C12, C25 |
| `GET /v1/glossary/index` | `etag`-friendly, no params | The surface-form index the UI highlighter consumes | C12, C25 |

### 4.12 Notebook, jobs, exports

| Method / path | Params | Response | Errors | Served by | Obligations |
|---|---|---|---|---|---|
| `GET /v1/notebook` | `tag`; `since`; `limit` · 50 · 200 | Findings-memo index | — | C12, C21 | Mandate B |
| `GET /v1/notebook/{slug}` | — | Memo markdown + resolved live data links (each link is an endpoint + params, validated at render so a memo cannot link to a dead figure) | `not_found` | C12, C21 | Mandate B |
| `GET /v1/jobs` | `state`; `job_type`; `since`; `limit` · 100 · 200 | Job collection | — | C12, C26 | — |
| `GET /v1/jobs/{job_id}` | — | State, progress, `stage`, `result_ref`, `error` as a `Problem`, `derivation_id` | `not_found` | C12, C26 | — |
| `DELETE /v1/jobs/{job_id}` | — | `204` | `not_found`, `job_not_cancellable` | C12, C26 | Audit event |
| `POST /v1/exports` | Body: `query_ref` {`operation_id`, `params`}, `format` enum(`csv`,`parquet`,`arrow`) | `202` + `job_id` | `validation_failed`, `result_cap_exceeded`, `rate_limited` | C12, C26 | R5, R6; provenance block mandatory (§2.7) |
| `GET /v1/exports/{export_id}` | — | Export record + download link + the provenance block | `not_found` | C12, C26 | R5, R6 |

### 4.13 Tiles — see §3.4

| Method / path | Scope | Response |
|---|---|---|
| `POST /v1/tiles/token` | any | `{token, expires_at, layers, as_of}` |
| `GET /v1/tiles/{layer}/{z}/{x}/{y}.pbf` | token-gated | MVT via the martin proxy |
| `GET /v1/tiles/attributes` | token-gated | Arrow IPC attribute bundle |
| `GET /v1/tiles/layers` | any | Layer catalog: id, geometry type, min/max zoom, `tiles.build` derivation id, entitlement group |

### 4.14 Coverage against `bp:456-502`

All 41 rows of the v0.6 endpoint inventory are present. SB-04 adds, all additive:

| Addition | Justified by |
|---|---|
| `GET /docs`, `GET /v1/errors/{code}`, `GET /healthz` | S1 discoverability; SB-06 §1.3 |
| `GET /v1/derivations` (collection), `/v1/manifests/{id}/bytes`, `/v1/vintages`, `/v1/vintages/{id}`, `/v1/quarantine/summary`, `/v1/conformance/{id}?include=applied_by` | SB-07 §9.4 (E-04) |
| `GET /v1/typecurves/{id}`, `GET /v1/valuations/{id}` (v0.6 lists POST only for valuations) | Content-addressed artifacts must be retrievable by id or R7's replay claim is unreachable |
| `GET /v1/crs` | R8 evidence for every projected distance served |
| `GET /v1/activity/duc` | U8, E8 — v0.6 names the DUC proxy in a story with no endpoint |
| `GET /v1/glossary/index` | DIR-8 highlighter (E-17) |
| `GET /v1/tiles/layers` | The tile-token minting flow needs a discoverable layer catalog |
| `POST/GET/DELETE /v1/keys`, `POST /v1/keys/{id}/rotate` | `bp:408` rotation; SB-07 §12 key events (E-11) |

---

## 5. Agent gateway (C15)

### 5.1 Curated, not generated — and why the drift risk is closed

D-4 (`bp:857`) and `bp:428`: the tool list is hand-curated for task ergonomics, not
generated from OpenAPI. The reasoning restated because it will be challenged:

- A generated tool per operation produces ~60 tools whose names are HTTP shaped
  (`get_v1_wells_api10_production`) and whose parameters are transport artifacts
  (`cursor`, `explain_depth`, `format`). An agent's tool-selection accuracy degrades
  with tool count and with parameter noise; both are avoidable here.
- Task-shaped tools compose the 2–3 calls a question actually needs. `run_scenario`
  is one tool over `POST /v1/scenarios`; a generated surface would make the agent
  build the design object, choose a deck, choose an assumption set and poll — four
  decisions where the product has one opinion.
- The counter-risk is drift: a curated list can silently stop covering the API. That
  is closed by CI, not by discipline (§5.5).

### 5.2 Transport, deployment, auth

- **Transport: MCP Streamable HTTP**, single endpoint `POST /mcp` with SSE upgrade
  for server-initiated messages. `bp:430` says "HTTP/SSE"; the separate HTTP+SSE
  transport was superseded by Streamable HTTP in the MCP specification and building
  the retired transport in 2026 is a gratuitous compatibility problem (§10 E-18). SSE
  remains the streaming mechanism *within* Streamable HTTP, so `bp:430`'s intent is
  preserved.
- Separate systemd unit `glasswell-agent.service`, same VM, bound `127.0.0.1:8010`,
  routed by Caddy at `/mcp` inside the same Access application (SB-06 §5.1 — path
  `*`, no carve-outs).
- Authenticates with an `agent`-scope service token plus its own app API key, and
  **never holds the owner key** (`bp:232`). The gateway calls the API over loopback
  and forwards its own credentials; it does not share a process or a database
  connection with the API.
- Rate limited under `read.service` (60 req/min) — "an agent should be deliberate;
  S5 is a 10-question suite, not a crawler" (SB-06 §10.4).

### 5.3 Tool schema discipline

Every tool obeys all seven, and `equivalence.py` asserts each mechanically:

1. **Declared endpoints.** Each tool declares `endpoints: [operation_id]`. CI asserts
   every one exists in the served OpenAPI document (`bp:428` (i)).
2. **Parameter subset.** Each tool's input schema is a subset of the union of its
   endpoints' parameter schemas, with identical types and identical constraints
   (`bp:428` (ii)). A tool may omit a parameter or fix it; it may never invent one or
   widen one.
3. **No transport parameters.** `cursor`, `limit`, `format`, `explain_depth` are not
   tool inputs. Pagination is handled inside the tool with a stated cap; the tool
   response says how many were omitted.
4. **Every parameter described, and every domain term in a description resolves to a
   glossary row** (R9). The description text is *generated from* the OpenAPI field
   descriptions, so tool documentation and hover text cannot diverge.
5. **Enumerated failure modes.** Each tool declares the `Problem` codes it can
   surface and returns them structurally, not as prose. `bp:741` — "every failure mode
   enumerated" — is a schema property here.
6. **Every numeric in every tool response carries its handle**, in the SB-07 §9.1
   form, unchanged from the API response. The gateway does not reshape figures; it
   passes them through. This is what makes S5's "every figure traceable" survive the
   second surface.
7. **Every tool response carries `as_of.resolved`** so an agent's answer is
   reproducible by a human against the same vintage.

### 5.4 The curated tool set — 20 tools

| # | Tool | Endpoints (operation ids) | Answers |
|---|---|---|---|
| 1 | `search_wells` | `list_wells` | Locate wells by operator, formation, county, land unit, vintage, bbox |
| 2 | `get_well` | `get_well`, `get_well_completions` | Header, operator with alias provenance, completion design |
| 3 | `get_production` | `get_well_production` | Q1 — monthly series by stream with granularity, vintage and null semantics; GOR and water cut |
| 4 | `find_neighbors` | `get_well_neighbors` | Spacing context: offsets, projected distances, completion dates |
| 5 | `find_analogs` | `list_analogs` | Q2 — nearest wells in feature space with their actual outcomes |
| 6 | `get_forecast` | `get_well_forecast`, `get_forecast` | P10/P50/P90 with training support and calibration ref |
| 7 | `build_typecurve` | `create_typecurve`, `get_typecurve` | Peer-group curve with band and n from any filter set |
| 8 | `list_reference_sets` | `list_decks`, `list_assumptions`, `list_models` | The selectable inputs: decks, assumption sets, promoted models |
| 9 | `run_scenario` | `create_scenario`, `get_scenario` | Q3 — design + location → forecast + NPV + training support + analogs |
| 10 | `value_forecast` | `create_valuation`, `get_valuation` | Q4a — NPV at P10/P50/P90, breakeven with method, payout |
| 11 | `run_sensitivity` | `create_sensitivity` | Q4b — which single input moves NPV most |
| 12 | `rank_operators` | `get_operator_league`, `get_operator` | Q5 — residual-metric league with CI, n, and expectation model |
| 13 | `run_inventory` | `create_inventory_run`, `get_inventory_run`, `list_inventory_slots`, `get_job` | Q6 — slots, rollup NPV, spacing assumption, support distribution. Polls the job internally |
| 14 | `get_benchmark` | `list_benchmarks`, `get_benchmark` | Type curve vs ML on the identical temporal holdout, sliced |
| 15 | `get_forecast_ledger` | `list_ledger`, `get_ledger_entry` | Q10 — what we forecast, what happened, graded at the forecast's own vintage and against current |
| 16 | `get_quality` | `get_scorecard`, `get_quarantine_summary`, `list_quarantine` | Q8 — quarantine share by reason and basin, coverage, calibration, withheld share |
| 17 | `explain_figure` | `explain`, `get_derivation` | Q9a — the full chain for a handle, down to terminal manifests |
| 18 | `get_provenance` | `get_manifest`, `list_manifests`, `get_recipe` | Q9b — the checksummed source record and the recipe that regenerates the artifact. Prefix-dispatched on `man_*` / `rcp_*` |
| 19 | `search_conformance` | `list_conformance`, `get_conformance_rule` | Q7 — the rules governing a cross-source difference, with rationale and evidence URL |
| 20 | `define_term` | `get_glossary_term`, `list_glossary` | Any term the agent or the user does not know; identical text to the UI tooltip (U22) |

**Deliberately uncovered endpoints** — the reviewed list `bp:428` (iii) requires,
with the reason each is out:

| Endpoint family | Why no tool |
|---|---|
| `/v1/keys/*` | Credential issuance is owner-only and must not be reachable from an agent scope |
| `/v1/aois`, `/v1/wellsets` | Saved-object CRUD is a UI workflow; the agent reads their outputs via `get_quality`/`run_inventory` equivalents but does not create durable state |
| `/v1/jobs`, `/v1/exports` | Job polling is internal to `run_inventory`; a bare job tool invites an agent to poll a queue |
| `/v1/tiles/*` | Tiles are a rendering surface with no figure semantics |
| `/v1/audit`, `/v1/vintages`, `/v1/derivations` (collection) | Bulk forensic surfaces; the agent's traceability path is handle-first via `explain_figure` |
| `/v1/permits`, `/v1/landunits`, `/v1/spacingunits`, `/v1/formations`, `/v1/crs`, `/v1/activity/duc` | Reference and activity lookups the ten questions do not exercise. **First candidates if the suite grows** |
| `/v1/notebook`, `/v1/health`, `/v1/` | Not figure-bearing |
| `/v1/recipes/{id}/replay` | Owner-only; SB-07 §4.5's CLI is the stranger's replay path |

### 5.5 Tool ↔ endpoint equivalence CI

`agent/equivalence.py`, run every build (`bp:428`, `bp:453`):

1. Every `endpoints:` entry resolves to an `operationId` in the served
   `/openapi.json`. Miss → **FAIL**.
2. Every tool input schema is a subset of its endpoints' parameter schemas, compared
   structurally (name, type, format, enum members, `minimum`/`maximum`). A widened
   constraint → **FAIL**.
3. Every `Problem` code a tool declares is declared by at least one of its endpoints.
4. The **equivalence report** — a generated `agent/EQUIVALENCE.md` listing every
   operation and its covering tools, with the uncovered set — is regenerated and
   diffed. A change to the uncovered set requires the table in §5.4 to be updated in
   the same commit. This makes "which endpoints have no tool coverage" a reviewed
   list rather than an accident (`bp:428`).

### 5.6 The 10-question suite as an executable contract test

`tests/contract/test_agent_suite.py` — one test per question from `bp:432-443`, run
against the fixture instance (SB-07 §10's fixture: ~200 ND wells, ~50 TX leases, ~30
NM wells, one trained model, one inventory run, one AOI, one well set).

Each test asserts four things, and the fourth is the one that makes S5 real:

1. **Answerable through public tools only** — the harness drives the MCP server with
   an `agent`-scope credential, never the API directly and never the owner key.
2. **Correct** — the answer matches a checked-in expected value computed from the
   fixture.
3. **Complete** — the question's every sub-clause is answered (Q3 has three: the
   quantiles, the training support, *and* the feature-space location; Q10 has three
   vintages).
4. **Traceable** — every numeric leaf in the tool output carries a handle; every
   handle resolves through `explain_figure` to terminals that are **all manifests**,
   with `truncated == false`. This is SB-07 §10 Check 3 applied to the agent surface.

Question-to-tool mapping, with the sub-clause each tool supplies:

| Q | Tools | The clause that is easy to miss |
|---|---|---|
| 1 | `get_production` → `explain_figure` → `get_provenance` | "which regulator file" — the terminal manifest's `source_key` and `sha256`, not just the source name |
| 2 | `find_analogs` | "what did they actually produce" — actual outcomes, not predicted |
| 3 | `run_scenario` | "training support **for that point in feature space**" (4A.10), with k and metric declared |
| 4 | `value_forecast`, `run_sensitivity` | "which single input moves NPV most" — the ranked tornado, and NPV10 carrying its rate (4B.1) |
| 5 | `rank_operators` | "with what confidence interval" and the expectation model's `model_id`; `rollup_mode` stated |
| 6 | `run_inventory` | "what spacing assumption and support distribution underlie it" (4D.3) — both, or the answer is incomplete |
| 7 | `search_conformance`, `define_term` | "which conformance rules govern the difference" — rule ids with `evidence_url`, not prose |
| 8 | `get_quality` | "what would change if the rule were relaxed" — the reason-code breakdown plus the released-candidate count from the quarantine release loop |
| 9 | `explain_figure`, `get_provenance` | "down to a checksummed file" **and** "the recipe that regenerates it" — two artifacts |
| 10 | `get_forecast_ledger` | "using the actuals as they stood at grading vintage, not as they stand now" — both vintages present, both grades reported (4A.14) |

The suite is a **P5 exit criterion and re-verified at P6** (`bp:794`, `bp:830`). A
failing question fails the build; it is not a report.

---

## 6. Glossary endpoints (DIR-8, E18, R9)

### 6.1 Endpoints

| Method / path | Params | Response |
|---|---|---|
| `GET /v1/glossary` | `q` (prefix + alias match); `domain_tag` repeatable; `limit` · 100 · 500 | `term_id`, `term`, `aliases[]`, `short_definition`, `domain_tags[]` |
| `GET /v1/glossary/{term_id_or_term}` | — | The above plus `expanded_definition`, `related_terms[]`, `source_refs[]`, `first_surfaced_in`, `effective_from`, and **`appears_in[]`** |
| `GET /v1/glossary/index` | — | The term index (§6.2) |

`{term_id_or_term}` accepts either the `gls_*` id or the surface form, case-folded.
DIR-8 writes `GET /glossary/{term}`; an agent that has read a `meta.labels` value has
an id, and a human typing a URL has a word. Accepting both costs one lookup branch
and removes a class of "the documented URL does not work".

**`appears_in[]`** answers DIR-8's "where the term appears in the product": a list of
`{kind: "api_field"|"ui_label"|"chart_axis"|"table_header"|"tool_param", ref}`.
API-field entries are generated from the `x-glasswell-glossary` bindings (§1.4); UI
entries come from SB-05's build-time label extraction (§9). Stored in
`glossary_term_sites`, rebuilt every CI run — so it is derived, never hand-curated.

R6 and R7 apply to the glossary like everything else (DIR-8): every term row carries
a `derivation_id` from its promotion, and `GET /v1/glossary/{term}?explain=true`
resolves it. The glossary is data served through the same glass-box rules as the rest
of the system, which is the whole point of "glossary is data, not markup".

### 6.2 The term index the highlighter consumes

`GET /v1/glossary/index` returns a compact artifact built for one job: letting the UI
highlight terms in prose, chart axes and table headers **without hand-tagging any
view** (DIR-8).

```json
{ "index_version": "gix_2026-08-20_014",
  "built_at": "2026-08-20T04:00:00Z",
  "entries": [
    {"surface": "proppant intensity", "term_id": "gls_proppant_intensity", "n_words": 2},
    {"surface": "ip90", "term_id": "gls_ip90", "n_words": 1},
    {"surface": "nri", "term_id": "gls_nri", "n_words": 1}
  ],
  "stopwords": ["oil", "gas", "well"] }
```

Decisions:

- **Surface forms are pre-lowercased and pre-expanded from `term` + `aliases[]`**, so
  the client does no morphology. Matching is longest-surface-first on word
  boundaries; `n_words` lets the client build the multi-word trie in one pass.
- **`stopwords`** removes the failure mode DIR-8 invites: a glossary containing "oil"
  and "well" would highlight every third word on the page. Stopwords are terms that
  exist in the glossary and are *excluded from auto-highlighting*; they remain
  reachable by search and by explicit link.
- **`index_version`** is content-addressed over the term rows it was built from and
  is the strong `ETag`. `Cache-Control: private, max-age=3600`. The UI fetches it once
  per session; a glossary edit changes the version and the next fetch picks it up.
- The index is served, not bundled. Bundling it into the frontend would mean a
  glossary row added in a data commit requires a UI rebuild — which is exactly the
  hand-tagging DIR-8 rejects, one layer up.

### 6.3 R9 coverage check

Runs every build (`bp:450`), reusing `glasswell.lineage.ci.walk_api()` — one walker,
two assertion sets (SB-07 §10):

1. Every `x-glasswell-glossary` value in the OpenAPI document resolves to a
   `glossary_terms` row.
2. Every value in `meta.labels` across every exercised response resolves.
3. Every domain term flagged by the index inside an OpenAPI field `description`
   resolves — this catches a description that uses "parent-child" before the term
   exists.
4. Every UI label extracted from the built frontend bundle resolves (SB-05 emits
   `ui/labels.json` at build time; §9).
5. Every MCP tool parameter description term resolves (`bp:271` names tool parameter
   descriptions explicitly).

A new surfaced term with no glossary row **fails the build** (`bp:709`). The check is
cheap and the glossary is on the never-cut list (`bp:846`), so there is no phase in
which this is skipped.

---

## 7. OpenAPI quality bar and the S1 stranger test

### 7.1 The bar, per operation

| Requirement | Enforced by |
|---|---|
| Stable `operationId`, snake_case, unique — also the tool-mapping key | Snapshot diff (§2.1) |
| `summary` (one line) and `description` (what it returns *and* what it does not) | Lint rule in `openapi/customize.py` |
| `tags` naming the serving component | Lint rule |
| **≥1 request example per operation** | SB-07 §10 Check 1 — **no example → FAIL** |
| Every parameter: `description`, explicit `type`/`format`, `default` where one exists, `maximum`/`enum` where a cap exists | Lint rule; a parameter with no description fails |
| Every response code the operation can emit, each with a schema and an example, including every `Problem` type | Lint rule cross-checked against the handler's declared raises |
| Every numeric field: `x-glasswell-unit`; every domain field: `x-glasswell-glossary`; production-derived fields: `x-glasswell-granularity` | §6.3 and SB-07 §10 Check 5 |
| `x-glasswell-cache` naming the cache class (§2.8) | Lint rule |
| `x-glasswell-component` naming the C-number | Lint rule |

Examples are not decorative. They are the *input set* for the naked-number harness,
the contract tier and the schemathesis pass — which is why "no example" is a build
failure rather than a documentation nit.

### 7.2 The snapshot gate

`api/openapi_snapshot.json` is committed. CI regenerates and byte-compares
(`bp:452`). A diff is classified additive or breaking (§2.1); additive requires the
snapshot committed in the same change, breaking requires a major bump.

### 7.3 Description discipline

Descriptions state what a stranger cannot infer: which conformance rules shaped the
number, which normalization is in force (D-2), which vintage semantics apply, and
what the number is *not*. Example, `GET /v1/wells/{api10}/production`:

> Monthly produced volumes for one well. In North Dakota and New Mexico these are
> well-level regulator reports (`granularity: observed`). In Texas, production is
> reported by lease, so well-level series are **allocated** derived artifacts
> (`granularity: allocated`) carrying `allocation_model_id` and `error_bounds`;
> where a lease maps to exactly one well the volume passes through as `observed`
> with a 1:1 note. Every point carries the `report_vintage` it was reported at; a
> series never mixes vintages silently. `null_semantics` distinguishes a reported
> zero, an absent report, and a withheld (confidential) value — these are never
> collapsed.

### 7.4 The S1 stranger test as CI

`bp:99` is the acceptance standard for this whole sub-blueprint, so it gets a job
rather than a demo.

**`stranger` CI job.** Runs against the fixture instance with **only**:
`GET /openapi.json`, a `guest`-scope credential, and `ui/figure-manifest.json`.

SB-05 publishes `ui/figure-manifest.json` at build time — one entry per figure the UI
renders:

```json
{"figure_id": "well_card.cum12_oil",
 "operation_id": "get_well_production",
 "params": {"api10": "33053012340000", "stream": ["oil"], "as_of": "2026-08-01"},
 "pointer": "/summary/cum12_oil",
 "rendered": "128340.000"}
```

The job asserts, per figure:

1. The named operation exists in the document and the parameters validate against it.
2. Calling it with a guest credential succeeds.
3. The value at `pointer` equals `rendered` exactly (string comparison of the Decimal
   form — this is why §1.4 serialises Decimals as strings).
4. The figure carries a handle, and the handle resolves to terminal manifests in one
   `/v1/explain` call.

**Failure is a build failure.** A UI figure with no reproducing endpoint is exactly
what `bp:771`'s anti-story forbids ("No UI figure without an endpoint that reproduces
it"), and a stranger discovering that by hand at P6 is a phase slip.

This job is also what turns S1 from a P6 event into a continuously-held property. The
human version — an actual outsider with an actual guest grant, `bp:795` — still
happens at P6; the CI job is what makes it likely to pass.

---

## 8. Test strategy (DIR-10)

TDD as we go: contract tests are written with or before the endpoint, never
backfilled. Every phase exit includes its API tests passing.

### 8.1 Tier map

| Tier | Marker | Scope |
|---|---|---|
| Unit | `unit` | Cursor codec round-trip, envelope assembly, error mapping, `as_of` resolution, scope resolution, tile-token sign/verify, Decimal serialisation |
| Contract | `contract` | `TestClient` against **every** operation using its OpenAPI examples |
| Property | `contract` | schemathesis over the served document |
| Lineage | `contract` | SB-07 §10 Checks 1–5 and 9 wired against the SB-04 app |
| Auth matrix | `contract` | Every operation × every access class |
| Agent | `contract` | The 10-question suite (§5.6) and the equivalence report (§5.5) |
| Budget | `integration` | The `bp:572` non-functional budgets as assertions |

### 8.2 Contract tier — TestClient over every operation

Driven by `glasswell.lineage.ci.walk_api()` (SB-07 §10) so there is one walker. Per
operation:

- Call with each declared example; assert `2xx`, assert the response validates
  against the declared response schema, assert `meta.request_id` present.
- Assert the envelope invariants: `data`/`meta`/`links` present; `links.self` echoes
  the request; `meta.as_of.resolved` concrete whenever `as_of` was accepted.
- Assert the declared `x-glasswell-cache` class matches the emitted headers, and that
  `If-None-Match` with the returned ETag yields `304`.
- For collections: request `limit=2`, follow `next_cursor` to exhaustion, assert no
  duplicates and no omissions against an unpaginated read; assert a cursor from a
  different filter yields `422 cursor_query_mismatch`.
- For every declared `Problem` type: construct the triggering request and assert the
  exact `type` URI, status and `request_id`.

### 8.3 Naked-number and glossary CI

SB-07 §10 verbatim, with SB-04's contributions named:

- SB-04 supplies the app, the fixture examples, `ci/non_figure_allowlist.yml` (each
  entry carrying a reason — counts, page sizes, echoed parameters, coordinates, ids),
  and `ci/conformance_exempt.yml` review.
- Check 2 walks every numeric leaf; a leaf that is neither in a figure object, nor
  covered by a `_lineage` container entry, nor allowlisted → **FAIL** with the JSON
  pointer.
- Check 5 asserts `unit` + `granularity` + `report_vintage` on production-derived
  figures, `basis` on liquids figures, and `allocation_model_id` + `error_bounds`
  wherever `granularity == "lease_allocated"` (DIR-3).
- **Export extension (SB-04's own):** every `?format=csv` response and every export
  bundle is parsed and asserted to carry the provenance block of §2.7 — resolved
  `as_of`, per-column derivation ids, per-column `granularity` and `unit`, and the 4D
  statements on inventory exports. `bp:400` is a promise until something reads the
  file.
- Glossary checks per §6.3, same walker, different assertions.

### 8.4 Property pass

`schemathesis` against the served document (`bp:452`), ASGI transport:

- Checks enabled: `not_a_server_error`, `status_code_conformance`,
  `response_schema_conformance`, `content_type_conformance`.
- Seeded (`--hypothesis-seed` fixed) so a failure is reproducible; example budget
  capped to keep the whole API suite inside CI's five-minute budget alongside SB-07's
  harness.
- Auth is supplied as an `owner` credential so the property pass reaches every
  operation; the auth *matrix* is a separate, deterministic suite (§8.5).
- Known-noise suppression is explicit and reviewed: endpoints that legitimately
  return `422` for generated garbage declare it in their response set, so
  `status_code_conformance` passes without a blanket exclusion.

### 8.5 Auth matrix

Enumerated from the OpenAPI document (each operation declares its required scope and
capability), so the matrix cannot fall behind the surface. Per operation × per class
∈ {`owner`, `guest`, `service+agent-key`, `service+guest-key`, `lan`, `no-JWT`,
`service+no-key`}: assert allowed or the exact `Problem` code.

Fixed negative cases, all of which are the failure modes SB-06 §5 and §11 name:

| Case | Expected |
|---|---|
| No `Cf-Access-Jwt-Assertion` | `403 unauthenticated` |
| `alg: none` token | `403 unauthenticated` |
| HS256 token signed with a known key | `403 unauthenticated` |
| Valid signature, wrong `aud` | `403 unauthenticated` |
| Valid signature, `aud` a **prefix** of the configured tag | `403` (never prefix-match) |
| Expired token (past leeway) | `403 unauthenticated` |
| JWKS unreachable, inside the 24 h stale window | `200` (stale keys served) |
| JWKS unreachable, past 24 h | `503 jwks_unavailable`, **never allow** |
| Unknown `kid` flood | ≤1 outbound refresh per 300 s |
| `X-Glasswell-Origin: lan` **through the tunnel** | `403` — the Caddy delete-header invariant (SB-06 §4.5, §11 step 27) |
| `service` principal, no `X-Glasswell-Key` | `403 key_required` |
| Key revoked / expired | `403 key_revoked` |
| Key whose `principal` ≠ the service token `common_name` | `403 forbidden` |
| `guest` POST anywhere | `403 forbidden` |
| `guest` GET on an owner's `private` scenario | **`404 not_found`** — existence not disclosed |
| Tile token minted for principal A, presented by principal B | `403 tile_token_invalid` |
| Tile token for layer set {a}, tile requested from layer b | `403 tile_layer_not_entitled` |
| Tile token past 300 s | `403 tile_token_invalid` |
| Direct request to `127.0.0.1:3000` from anything but the API process | Not routable (SB-06 §4.3) |

The last row is verified in SB-06's runbook rather than in pytest, and is cross-linked
so neither side assumes the other covered it.

### 8.6 Budget tests

`bp:570-572` converted to assertions against the fixture instance, p95 over 50 runs:

| Endpoint | Budget |
|---|---|
| `GET /v1/wells/{api10}` | < 300 ms |
| `GET /v1/typecurves` at the result cap | < 2 s |
| `GET /v1/explain` depth 5 | < 500 ms |
| `GET /v1/tiles/{layer}/{z}/{x}/{y}.pbf` warm | < 150 ms |
| `POST /v1/scenarios` single, warm | < 3 s (S3) |

The tile budget is the one the martin-fronting decision (§3.4) puts at risk, so it is
measured from P2 rather than at P6 — if the Python hop costs more than the headroom,
the fallback is Caddy `forward_auth` to a token-check endpoint, which moves the body
streaming back to Caddy at the cost of a subrequest. Recorded here so the fallback is
a decision rather than a scramble.

### 8.7 Fixtures

Per DIR-10, fixtures are cut from real regulator downloads, sanitised only by
truncation, and shared with SB-07 §10's fixture set — one fixture database, not two.
API-tier additions: one key of each scope, one Access JWT signer (a local RSA keypair
standing in for Cloudflare's JWKS), one tile-signing key, and a recorded martin
response set so the tile proxy is testable without martin running.

---

## 9. Interfaces

| Party | SB-04 consumes | SB-04 must supply |
|---|---|---|
| **SB-01 data platform** | Canonical and mart readers with `as_of()`; `api_keys`, `glossary_terms`, `glossary_term_sites` DDL; `api.rate_buckets` and `api.idempotency_keys` DDL | Column and filter requirements per §4; the two `api.*` table shapes |
| **SB-02 modeling** | `resolve_model()`, promoted-model guarantee, calibration and probe artifacts | The `model_not_promoted` / `unregistered_artifact` contract; the slice enum for `/v1/benchmarks` |
| **SB-03 econ / scenarios / inventory / alerts** | Pure `(forecast, deck, assumptions)` valuation; scenario and inventory orchestration; digest materialisation | The S3 budget as a hard requirement; 4D.3/4D.5 fields on every inventory response; `Problem` codes for partial-failure rollups |
| **SB-05 UI** | `ui/figure-manifest.json` and `ui/labels.json` at build time | The envelope, the term index, the Chain JSON for the drawer, tile token flow, **the corrected tile URL** (`/v1/tiles/...`, §10 E-12) |
| **SB-06 infrastructure** | `request.state.principal`, `/etc/glasswell/{app,access}.env`, the Caddy listeners, rate-limit table | Amended Caddyfile per E-12/E-13/E-14; the tile-signing key path; the `/v1/*` Cloudflare rate-limit rules (E-15); a second service-token class for S1's stranger (E-21) |
| **SB-07 spine** | `envelope.figure()`, `attach_lineage()`, `resolve_chain()`, the nine endpoint handlers, `ci.walk_api()`, `lineage_unresolved` | An OpenAPI example for **every** operation; `key.issued` / `key.revoked` / `access.denied` / `config.changed` audit events; request-time derivations through `derive()` only; MCP tools exposing `/explain`, `/manifests`, `/conformance` (§5.4 tools 17–19) |
| **SB-00 consolidation** | — | Ratify or reject every item in §10 |

---

## 10. v0.6 errata

Defects and contradictions found while writing to freeze level. Each states the
divergence taken, so nothing here is silent. **22 items.** E-01 through E-08 and E-22
are internal to v0.6 or v0.6↔SB-07; E-09 through E-15 and E-21 are v0.6↔SB-06;
E-16 through E-20 are gaps.

| # | Where | Defect | Resolution taken |
|---|---|---|---|
| **E-01** | `bp:362-378` vs SB-07 §9.1 | Two incompatible mechanisms for carrying a handle: `meta.derivations` / `meta.units` as JSON-Pointer maps, and SB-07's in-band figure objects plus `_lineage`/`_units`/`_basis` sidecars. Two representations of the same fact can disagree, and SB-07 §10's harness is written against the in-band form | **SB-07 §9.1 is authoritative.** `meta.derivations` and `meta.units` are removed from the envelope. `meta.labels` is retained (glossary binding is SB-04's, not the spine's) and is generated from Pydantic field metadata, not hand-written |
| **E-02** | `bp:424` vs SB-07 §9.2 | v0.6 forbids `?explain=true` on POST; SB-07 defines it post-hoc. Direct contradiction | **Allow it, post-hoc.** `bp:424`'s stated worry — conflating "the run you created" with "the run you would create" — is closed exactly by rejecting `?explain=true` **with** `?dry_run=true` (`422 explain_on_dry_run`), rather than by banning the flag and forcing every agent into a second round trip. POSTs continue to return handles unconditionally, as `bp:424` requires |
| **E-03** | `bp:422` vs SB-07 §9.4 | `/v1/explain?ref=<id>&depth=n` (single ref, uncapped depth) vs `h` (repeatable 1–20) with `depth ≤ 8` or `full` | **Adopt SB-07.** Multi-handle is required for S9's one-call budget (SB-07 §1.8) and the depth cap closes an uncapped recursive-CTE exhaustion surface. `ref` is not accepted, not even as an alias — an alias would appear in the OpenAPI document and confuse the stranger |
| **E-04** | `bp:456-502` vs SB-07 §9.4 | Six spine endpoints specified by SB-07 are absent from the endpoint inventory: `GET /derivations` (collection), `/manifests/{id}/bytes`, `/vintages`, `/vintages/{id}`, `/quarantine/summary`, `/conformance/{rule_id}?include=applied_by` | Added (§4.9, §4.10). `/quarantine/summary` is load-bearing for the per-basin quarantine trigger (3.0.5) and `/conformance/{id}?include=applied_by` is the U21 path — neither is optional |
| **E-05** | `bp:645-649`, D-24 vs SB-07 §4.2 | Determinism vocabularies differ in **content**, not just naming. v0.6: `byte_exact` / `value_equal` / `environment_bound`, where `environment_bound` means "depends on external service state (e.g. a fetch)" and manifests sit there. SB-07: `D1` / `D2` / `D3`, where manifests are D1 by construction and D3 is "semantically identical after declared normalization" for responses and tiles | **Adopt SB-07's D1/D2/D3**, and amend `bp:99` and §4C.5 per SB-07 §4.6. `/v1/recipes/{id}` serves `determinism_class ∈ {D1, D2, D3}`. Justification: D3 is precisely the class an API response falls in, and v0.6's taxonomy has no home for it — SB-04 could not declare its own artifacts' class under v0.6's names |
| **E-06** | `bp:491`, U11 vs SB-07 §4.5, §13 | v0.6 specifies `POST /v1/recipes/{id}/replay` returning a job; SB-07 rejects API-triggered replay because it "would require an async job contract, run states, cancellation and a queue" | **Keep the endpoint.** SB-07's justification cites assessment API-02, which v0.6 **already resolved** by adding C26 (`bp:252`) and `/v1/jobs` — the machinery SB-07 declined to drag in now exists. The endpoint is owner-scoped; the `glasswell repro` CLI remains S1's stranger path, which is the stronger claim SB-07 is right about |
| **E-07** | `bp:279` vs SB-07 §2.2 and `src/glasswell/lineage/ids.py:46` | Manifest id is `man_<sha256[:16]>` in v0.6, `man_<sha256[:32]>` in SB-07 **and in the shipped code** | Adopt `[:32]`. Note that the implementation already diverges from v0.6, which is the more urgent half of this finding |
| **E-08** | `bp:263-264` vs SB-07 §0.3 | Both documents define R6 and R7, differently. v0.6: R6 = derivation coverage, R7 = reproducibility. SB-07 (written pre-consolidation, proposing wording for SB-00 to ratify): R6 = lineage completeness, R7 = explain coverage | **v0.6 §3.3 wins** — it is the consolidated contract and SB-07 §0.3 explicitly defers to it. Remap: SB-07 §10's Check 2 (labelled R7) and Check 3 (labelled R6) are **both R6** under v0.6; Check 8 plus recipe replay are R7. SB-07 §0.3 and §15's first open item should be closed against v0.6 §3.3 |
| **E-09** | `bp:410` vs SB-06 §10.4 | Rate limits disagree: v0.6 says 60 req/min for reads; SB-06 says 120 interactive / 60 service / 600 tiles / 32 global concurrency, keyed on `principal.id` because every request arrives from 127.0.0.1 | **Adopt SB-06** (§2.9). It is later, more specific, and identifies a failure v0.6 does not (IP-keyed limiting puts the entire internet in one bucket). v0.6's "5 concurrent jobs for writes, one training job system-wide" is retained; the two are compatible |
| **E-10** | `bp:336` vs SB-06 §8.3 | `api_keys` shapes disagree. v0.6: `scope (owner\|guest\|agent)`, `layer_entitlements[]`, `hashed_secret`. SB-06: `kind (api\|admin)`, `label`, `sha256`. SB-06's `kind` cannot express D-5's layer entitlement or DIR-6's three scopes | Merged shape in §3.2: v0.6's `scope` + `layer_entitlements` + `hashed_secret` **and** SB-06's `label` + `last_used_at` + show-once lifecycle. SB-06's `kind` is dropped; `capabilities[]` carries the read/write distinction `bp:407` requires |
| **E-11** | `bp:408`, `bp:456-502`, SB-07 §12 | `bp:408` requires key rotation and revocation as "a documented procedure, not an aspiration", and SB-07 §12 requires SB-04 to emit `key.issued`/`key.revoked` — but the endpoint inventory has no key-management endpoints, so neither is reachable | Added `POST/GET/DELETE /v1/keys` and `POST /v1/keys/{id}/rotate` (§3.5), owner-scoped, show-once secret |
| **E-12** | D-5 / `bp:409` vs SB-06 §4.5, §1.3 | **Security defect.** D-5 requires that martin is never exposed directly and that a tile proxy validates the signature and layer scope. SB-06's Caddyfile routes `/tiles/*` straight to martin on **both** listeners with no token check, and SB-06 §1.3 forbids SB-04 from defining routes under `/tiles/*`. As specced, any principal with an Access session can fetch any layer, and layer entitlement does not exist | **martin is removed from public routing.** Tiles move to `/v1/tiles/{layer}/{z}/{x}/{y}.pbf` on the API (§3.4). SB-06 must delete both `handle_path /tiles/*` blocks; SB-05's tile URL changes from `/tiles/{z}/{x}/{y}` to `/v1/tiles/{layer}/{z}/{x}/{y}.pbf`. Cloudflare Access remains the outer gate; it is not the entitlement mechanism |
| **E-13** | SB-06 §4.5 vs §1.3 | The Caddyfile's `handle { reverse_proxy 127.0.0.1:8000 }` is a catch-all, so **static assets are never served** despite §1.3 promising Caddy serves them from `/opt/glasswell/web/` at `/`. The UI would 404 | Amended Caddyfile (both listeners): `handle /v1/*`, `handle /openapi.json`, `handle /docs*`, `handle /mcp*` → `:8000`; `handle /healthz` → `:8000`; catch-all → `root * /opt/glasswell/web`, `try_files {path} /index.html`, `file_server` |
| **E-14** | SB-06 §1.3 vs `bp:464` | SB-06 promises `GET /healthz`; v0.6 row 3 specifies `GET /v1/health` | **Both** (§4.1). `/healthz` is the zero-cost liveness probe SB-06's unit checks depend on; `/v1/health` is the enveloped freshness and degraded-state surface `bp:544` requires |
| **E-15** | SB-06 §10.4 | Cloudflare-side rate limiting is specified on `/api/*` — a path prefix that does not exist anywhere in v0.6's surface | Rules target `/v1/*` and `/v1/tiles/*` |
| **E-16** | `bp:386` vs SB-07 §9.5 | Pagination caps disagree: global max 1000 vs `limit ≤ 200` on spine collections | Reconciled, not overridden: 1000 is the **ceiling**; each endpoint declares its own `maximum` in OpenAPI; spine collections declare 200 (§2.3) |
| **E-17** | DIR-8 vs `bp:498`, `bp:372` | DIR-8 requires terms "auto-highlighted in rendered text and chart/table labels via the glossary index" and "where the term appears in the product". The endpoint inventory has only `GET /v1/glossary` and `GET /v1/glossary/{term}`, and `meta.labels` is a per-response pointer map — not an index a highlighter can run over prose | Added `GET /v1/glossary/index` (§6.2) with pre-expanded surface forms, `n_words`, and a `stopwords` list; added `appears_in[]` to the term detail, derived from OpenAPI bindings and SB-05's label extraction |
| **E-18** | `bp:430` | "Transport: HTTP/SSE" names the MCP HTTP+SSE transport, which was superseded by Streamable HTTP in the MCP specification. Building the retired transport in 2026 creates a client-compatibility problem for no gain | Adopt **Streamable HTTP** (§5.2). SSE remains the streaming mechanism within it, so the intent of `bp:430` is preserved |
| **E-19** | `bp:502` vs `bp:350` | `GET /v1/tiles/attributes` lists params `layer, bbox, model_id, as_of`, but §3.5 describes fetching "the current viewport's key set" — a client-supplied key list at 20k laterals exceeds any URL length | **The server derives the key set from `bbox` + `z`**; the client never sends keys (§3.4). A declared feature cap (default 50,000) returns `422 result_cap_exceeded` with the count — which is also the measurable form of OQ-14 rather than an assumption |
| **E-20** | `bp:400` | `?format=csv` on collections and `POST /v1/exports` are given the same provenance obligation with no boundary between them, and no statement of whether `?format=csv` follows cursors | `?format=csv` is capped at **one page** at the endpoint's limit; anything larger is `POST /v1/exports`. Both carry the provenance block; §8.3 asserts it in CI, because `bp:400` is a promise until something parses the file |
| **E-21** | `bp:99`, `bp:407` vs SB-06 §5.2 | **S1 is unreachable as specced.** The guest class is a One-time-PIN Access policy — an interactive browser flow. A stranger with "the OpenAPI doc and a guest key" running `curl` or a script cannot complete OTP, and SB-06 restricts Service Auth to a single `glasswell-agent` token. There is no non-interactive guest path | A **second service-token class**, `glasswell-guest-<name>`, plus a `guest`-scope app API key whose `api_keys.principal` equals that token's `common_name`. Effective scope for `kind == "service"` therefore comes from the **key**, not the access class (§3.3), which is what lets a service principal be a guest. SB-06 §5.2's four-class table gains a fifth row |
| **E-22** | `bp:493`, `bp:334` vs SB-07 §14 item 1 | v0.6 describes the audit stream as hash-chained (`prev_event_hash`, `event_hash`); SB-07 deliberately cut the hash chain (one writer who is also the auditor; role grants plus an append-only trigger are the guarantee) | `GET /v1/audit` serves no chain fields and its description states the actual enforcement (`REVOKE UPDATE, DELETE` plus a `BEFORE UPDATE OR DELETE` trigger). `bp:334` and `bp:644` should drop the hash-chain language — claiming tamper evidence the system does not implement is the exact credibility failure Mandate B cannot afford |

---

## 11. Rejected alternatives

- **GraphQL.** One flexible endpoint defeats R6's per-operation obligations, makes the
  naked-number harness's "walk every operation with its example" undefinable, and
  gives an agent an unbounded query surface on a one-VM budget.
- **Auto-generated MCP tools from OpenAPI.** D-4 and §5.1.
- **A separate FastAPI app for the lineage spine.** SB-07 §14 item 10 already cut it;
  one app, one package.
- **`401` with `WWW-Authenticate`.** No challenge is meaningful behind Access; it
  would invite client retry loops against an identity edge that has none.
- **Offset pagination as a convenience alongside cursors.** `bp:386` forbids it, and
  a second pagination mode is a second correctness surface under concurrent ingest.
- **Signed cursors.** The cursor carries no authorisation; signing it would imply a
  trust property it does not have (§2.3).
- **`meta.derivations` pointer map alongside in-band figures.** E-01.
- **A user table.** SB-06 §5: identity is enforced at the edge; `owner` vs `guest` is
  config. Owner-created accounts only; no registration path (SB-06 §5, amended 2026-08-29).
- **Per-row ACLs on API keys.** `bp:411` and SB-06 §8.3 both scope this out;
  `owner_principal` + `visibility` is the boundary.
- **Server-side rendering of `/explain` prose.** SB-07 §9.3 is explicit: prose is a
  UI rendering of the graph. A prose payload satisfies the drawer and fails the agent.
- **API-key-in-URL for tiles.** §3.4; leaks through logs and referrers, and tile URLs
  are the most-shared URLs in a map product.
- **Edge-cached tiles.** SB-06 §5.6 step 10 warns against assuming it, and entitlement
  is per-principal — a shared cache would be a leak.
- **A second uvicorn worker.** §1.5 states the state that would need to move; it can be
  revisited when a budget test fails, not before.
- **Response compression in FastAPI.** Caddy owns it; two compressors is a
  `Content-Encoding` bug waiting to happen.

## 12. Cut as gold-plating

Designed, then dropped. Listed so each is a decision:

1. **Webhooks / push notifications for AOI digests.** D-13 pins pull-primary.
2. **A `/v1/search` federated search endpoint.** Per-resource `q` covers the need.
3. **Conditional requests on POST (`If-Match`).** Idempotency keys cover the retry
   story; optimistic concurrency on saved objects is a single-user problem.
4. **JSON Patch on saved objects.** `PATCH` with a partial body is sufficient.
5. **A GraphQL-ish `fields=` projection parameter.** It would make response schemas
   dynamic and break the naked-number harness's schema assertions.
6. **Server-sent events for job progress.** `GET /v1/jobs/{id}` polling at a stated
   interval is proportionate for a dozen jobs on one VM.
7. **An API-key scope editor UI.** Keys are issued by the owner from the CLI-shaped
   endpoints in §3.5.
8. **OAuth2 / OIDC on the app.** Access is the identity edge; a second identity system
   is exactly the multi-tenant work `bp:91` puts out of scope.
9. **Per-endpoint response caching in Redis.** `bp:204` rejects new infrastructure;
   §2.8's ETags plus content addressing get most of the benefit with no daemon.
10. **A tool that wraps `/v1/audit` for the agent.** §5.4's uncovered list; the
    handle-first path is the agent's traceability route.

## 13. Open items handed back

| Item | Owner | Why it is not decided here |
|---|---|---|
| Ratify or reject E-01 … E-22 | **SB-00** | Several touch change-controlled sections (`bp:1007`): §2.5 philosophy (E-05, E-22), §4C.5 (E-05), R6/R7 (E-08) |
| Amend the Caddyfile and the `/tiles/*` reservation; add the fifth Access class | **SB-06** | E-12, E-13, E-14, E-15, E-21 are SB-06's surfaces |
| Publish `ui/figure-manifest.json` and `ui/labels.json` at build time | **SB-05** | §7.4 and §6.3 depend on them; the format is fixed here, the content is SB-05's |
| Tile layer catalog and entitlement groups (which layers are `public`) | **SB-05 / SB-01** | §3.4 needs the group membership; the layer list is C20's |
| Whether `?explain=true` on `GET /v1/tiles/attributes` is meaningful | SB-05 | Attribute bundles are binary; the handle travels in schema metadata. Deferred until the drawer needs it |
| Attribute-bundle feature cap (default 50,000) | SB-05 / SB-02 | OQ-14 — measure in P7, do not assume (`bp:920`) |
| Whether the 10-question suite grows for the Permian | SB-00 | The suite is ND-shaped; P7 may want a TX allocation question. Adding one changes an S-criterion |
| Whether `/v1/activity/duc` needs its own component number | SB-00 | It is served from C5 today; E8 may warrant C-numbering |

---

*SB-04 spec's against `blueprint-v0.6-draft.md` and no earlier version. Every
divergence from it, from SB-06, or from SB-07 is in §10. There is no silent
divergence.*
