# SB-03 — Economics, Scenarios, Inventory & Alerts

**Sub-blueprint. Status: draft for review. Owner: Ryan MacDonald. Authored 2026-08-20.**

Scope charter per `assessment-blueprint.md:801`: DCF + decks + assumptions, sensitivities /
tornado, the scenario loop, the C22 inventory engine with its 4D guardrails, C23 alerting
and AOIs, and well-set rollups. Findings this SB is charged with closing: **D-04**
(batch-vs-interactive latency), **D-10** (minerals persona / NRI), **D-12** (inventory
geometry scope), **D-16** (S12 conditionality), **A-17** (alert delivery), **A-18**
(export surface), and the **R3 purity** reconstruction.

**Contract sources, in precedence order.**
`blueprint-v0.6-draft.md` (cited as **v0.6 §N**) is the contract. `work-output/direction-log.md`
(**DIR-n**) wins where it conflicts with anything older. `blueprints/SB-07-lineage-spine.md`
(**SB-07 §N**) is a frozen interface this document codes against, not a peer.
`work-output/assessment-blueprint.md` (**ab:N**) is cited only for finding identifiers.

**Quality bar.** DIR-1: every decision here must survive two hostile readers — an A&D
analyst who prices deals for a living, and a data scientist who will not accept a
percentile that was arrived at by addition. Where the two disagree, the honest answer wins
and the disagreement is stated. Every convention is explicit; conventions that are merely
conventional are still written down, because "everyone knows" is how a valuation engine
ships a sign error.

**Evidence key** (shared with SB-06 so tags read the same across documents):

| Tag | Meaning |
|---|---|
| **[V]** | Verified — read from a cited file/line or computed in this document |
| **[I]** | Inferred — reasoning stated inline from verified facts |
| **[A]** | Assumed — general-domain knowledge or an unverified estimate; carries a VERIFY gate before it may be served |

**VERIFY gates** are collected in §15. Nothing tagged [A] may be served without its gate
closed, and the seed loader refuses to publish a tax or cost row whose `evidence_url` is
null (§1.8).

---

## 0. Scope and obligations

### 0.1 What SB-03 owns

| Owns | Does not own |
|---|---|
| The DCF engine: cashflow construction, conventions, breakeven, payout (C10) | Forecast production paths, quantile models, conformal calibration (SB-02) |
| Deck and assumption objects, their content addressing, their seed data | Price-data acquisition plumbing and manifests (SB-01 fetchers, SB-07 manifests) |
| Per-state tax regime rows and their evidence discipline | Conformance rules — tax rows are **not** conformance rules (§1.8.4) |
| Interest model: working vs royalty, WI/NRI arithmetic | Ownership graph — explicitly out (v0.6 §2.3) |
| Uncertainty propagation policy from forecast quantiles to NPV bands (§2) | The production-side coverage measurement itself (SB-02, v0.6 §4A.7–4A.8) |
| Sensitivities / tornado: parameter set, delta semantics, output schema | Tornado *rendering* (SB-05) |
| Scenario orchestration (C11), the S3 latency budget and its cache design | Feature builder (C8/SB-02), analog index construction (SB-02) |
| Inventory engine v0 (C22): slot geometry, batch execution, rollups, 4D enforcement | PLSS/land-unit ingest and geometry storage (SB-01), slot map layer (SB-05) |
| AOI objects, the alert diff algorithm, digest schema, digest job (C23) | systemd unit files, timer placement, MTA (SB-06); AOI drawing UI (SB-05) |
| Well sets and portfolio rollup semantics | Set CRUD transport and auth (SB-04) |
| Export provenance-header contract for every SB-03 artifact (closes A-18) | The generic export/job machinery (C26, SB-04/SB-06) |
| `glasswell.econ`, `glasswell.scenarios` Python packages | `glasswell.lineage` (SB-07) — imported, never reimplemented |

### 0.2 Requirements satisfied

| Requirement | Source | Satisfied in |
|---|---|---|
| E5 Economics: decks, assumptions with water opex and per-state tax, DCF, breakeven, payout, tornado | v0.6 §5 E5 | §1, §3 |
| E6 Scenario loop under S3; analog panel; training support on the card | v0.6 §5 E6 | §4 |
| E8 AOI alerts, digest correct against a manual diff with freshness stated | v0.6 §5 E8 | §7 |
| E17 Inventory v0, ND/PLSS only, 4D honored, one township demo | v0.6 §5 E17 | §6 |
| 4B.1–4B.7 economics protocol | v0.6 §4B | §1 (4B.1 §1.3, 4B.2 §1.5, 4B.3 §1.7–1.9, 4B.4 §1.1, 4B.5 §1.10, 4B.6 §3, 4B.7 §2) |
| 4D.1–4D.5 inventory protocol | v0.6 §4D | §6.3 (every clause as a numbered assertion) |
| R3 purity of the dollars path | v0.6 §3.3 R3 | §1.1, §10.4 |
| R5 estimates are labelled | v0.6 §3.3 R5 | §1.13, §5.3, §6.5 |
| R6/R7 derivation coverage and reproducibility | v0.6 §3.3; SB-07 §0.3 | §1.1, §8 |
| S3 scenario + NPV under 3 s p95 warm | v0.6 §2.4 S3 | §4.2 |
| S12 inventory demo (conditional per D-16) | v0.6 §2.4, §8.1 D-11 | §6 |
| U4, U6, U14, U16, U17, U18, U19, U20 | v0.6 §6 | §1.4, §4.4, §3, §6, §7, §5 |
| D-04 batch is not held to the interactive budget | v0.6 §3.6.7; ab:431 | §6.4 |
| D-10 NRI as supplied input — and what that arithmetic actually implies | v0.6 §2.2; ab:488 | §1.4, §11 E-1 |
| A-17 alert delivery is pull-primary | v0.6 §8.1 D-13; ab:673 | §7.5 |
| A-18 export surface defined | ab:679 | §9 |

### 0.3 Dependencies taken as given

- **SB-07** supplies `derive()`, `figure()`, `resolve_model()`, recipes, determinism classes,
  content-addressed ids, and the `econ.value` / `econ.sensitivity` / `forecast.scenario` /
  `inventory.run` operation names (SB-07 §1.4, §11, §12). SB-03 emits exactly those.
- **SB-02** supplies forecast paths as `p10/p50/p90` monthly series per stream, a
  `model_id`, a `training_support` scalar, a calibration reference, and the Arps
  extrapolation beyond the trained horizon (v0.6 §4A.9). SB-03 **validates** what it
  receives (§2.5) and refuses malformed input rather than silently coping.
- **SB-01** supplies canonical production, land units, spacing units, lateral geometry in
  the basin's projected CRS (v0.6 §3.0.3 `crs_registry`), permits, and the bitemporal
  vintage accessors.
- **SB-04** supplies transport, auth, the envelope, pagination, the job contract, and the
  `202 Accepted` async path (v0.6 §3.6.7).

---

## 1. The economics engine (C10)

### 1.1 The pure function — signature and derivation capture

**R3 states valuation is "a pure, deterministic, side-effect-free function of
`(forecast, deck, assumptions)`" with "no hidden state, no ambient configuration, no
wall-clock reads" (v0.6 §3.3 R3).** Taken literally — and it is change-controlled, so it
must be taken literally — a function that opens a database transaction to write a
derivation row is not pure. The engine is therefore split in two, and the split is the
enforcement mechanism:

```python
# glasswell/econ/dcf.py — the pure core. Imports nothing outside stdlib decimal + models.
def value(
    forecast: ForecastPaths,          # frozen; per-stream monthly p10/p50/p90 + provenance refs
    deck: Deck,                       # frozen, content-addressed (§1.5)
    assumptions: Assumptions,         # frozen, content-addressed (§1.7)
    *,
    horizon_months: int = 360,
) -> Valuation: ...

# glasswell/econ/service.py — the impure shell. The only thing that touches the store.
def value_and_record(forecast_ref, deck_ref, assumption_ref, *, horizon_months=360) -> Valuation:
    fc, deck, asm = load_frozen(forecast_ref, deck_ref, assumption_ref)
    spec = derivation_spec(fc, deck, asm, horizon_months)      # computable before the output exists
    with derive("econ.value",
                output=OutputSpec(store="parquet", dataset="marts.valuations",
                                  partition={"valuation_id": spec.id}),
                params={"deck_id": deck.deck_id, "assumption_id": asm.assumption_id,
                        "horizon_months": horizon_months, "discount_rate": str(asm.discount_rate),
                        "interest_type": asm.interest_type, "econ_engine_version": ENGINE_VERSION},
                inputs=[Ref("derivation", fc.forecast_derivation_id),
                        Ref("derivation", deck.derivation_id),
                        Ref("derivation", asm.derivation_id)],
                model_id=fc.model_id) as ctx:
        v = value(fc, deck, asm, horizon_months=horizon_months)
        ctx.set_output_hash(v.content_sha256); ctx.set_rows(len(v.cashflow))
    return v
```

Justifications:

1. **R3 is literally true of `value()`.** A reviewer can read one module and confirm it.
   Enforced mechanically by an import denylist over `glasswell/econ/dcf.py` and its
   siblings — no `datetime`, `time`, `random`, `os.environ`, `logging`, `httpx`, no
   `glasswell.api`, no `glasswell.lineage.store` (test ECON-P1, §10.4).
2. **Derivation capture is uniform with the rest of the system** (SB-07 §1.1): the shell
   opens one `derive()` context per valuation, and nesting is automatic via contextvars,
   so a scenario that calls forecast-then-value produces a correct parent→child edge with
   no hand-wiring.
3. **`valuation_id` is content-addressed and computable before execution** (SB-07 §1.3),
   which is what makes sensitivity sweeps and inventory batches free: an identical
   `(forecast_id, deck_id, assumption_id, horizon, code_version, env_id)` tuple collides on
   the primary key and the stored result is returned. This is the mechanism behind "trivial
   cost via R3 purity" (v0.6 §3.3 R3) — not a hope about CPU time, a cache-hit guarantee.
4. **A determinism violation is caught in production, not only in CI.** If the spec collides
   and `output_sha256` differs, SB-07's store raises `DeterminismViolation` (SB-07 §1.3).
   For the econ path that is the alarm that says a "pure" function became impure.

**The ambient-state trap, stated because Python hides it.** `decimal.getcontext()` is
thread-local ambient state. A function that reads it is *not* pure — the same inputs under
a different context give different outputs. Every entry point in `glasswell.econ` therefore
opens an explicit `localcontext()` with `prec=28` and `rounding=ROUND_HALF_UP` and does all
arithmetic inside it. Test ECON-P2 mutates the global context to `prec=6,
ROUND_FLOOR` and asserts byte-identical output.

**Determinism class: D1 (byte-identical), per SB-07 §4.2.** Achievable because §1.12
removes every float from the path, including the discount factor.

### 1.2 The monthly cashflow ledger

One row per month `m ∈ [1, horizon]`, computed on an 8/8ths (100 % gross) basis first, then
split by interest. Order of operations is normative — reordering changes the answer through
rounding, and a hostile reviewer will diff against a spreadsheet.

| # | Line | Formula (8/8ths) |
|---|---|---|
| 1 | Volumes | `oil_bbl[m]`, `gas_mcf[m]`, `water_bbl[m]` from the forecast bundle (§2.2) |
| 2 | Realized oil price | `deck.oil[m] + deck.oil_diff[m]` (§1.6) |
| 3 | Realized gas price | `(deck.gas[m] + deck.gas_diff[m]) × gas_realization` (§1.6) |
| 4 | NGL revenue | `oil-equiv NGL bbl = gas_mcf × ngl_yield_bbl_per_mmcf / 1000`, priced at `deck.ngl[m]`; **default yield 0.0** (§1.5.4) |
| 5 | Gross revenue | `rev_oil + rev_gas + rev_ngl`, each quantized to the cent |
| 6 | Severance | per-stream, per §1.8: `pct × stream revenue` and/or `per_unit × stream volume` |
| 7 | Ad valorem | `ad_valorem_pct × gross revenue` (an approximation — §1.8.3) |
| 8 | Opex | `fixed_opex + oil_bbl×opex_oil + gas_mcf×opex_gas + water_bbl×opex_water` |
| 9 | Net revenue to interest | `gross revenue × NRI`, then `× (1 − post_production_deduct_pct)` for royalty interests only |
| 10 | Taxes to interest | `(severance + ad valorem) × NRI` |
| 11 | Costs to interest | `opex × WI` for a working interest; **zero** for a royalty interest (§1.4) |
| 12 | Net operating cashflow | line 9 − line 10 − line 11 |
| 13 | Capex | month 0 only by default (§1.9) |
| 14 | Abandonment | at the economic limit or horizon end, `× WI`, zero for a royalty interest |
| 15 | Discount factor | §1.3.1 |
| 16 | PV | line 12 × line 15, quantized to the cent |

Every line is retained in the `cashflow` array on the valuation artifact. A valuation that
serves only a summary cannot be audited, and v0.6 endpoint 18 promises "monthly cash flows"
(v0.6 §3.6.12 #18) while the `valuations` schema stores none (errata **E-8**, §11).

### 1.3 Conventions, pinned

4B.1 gives four: monthly cash flows, mid-month discounting, nominal USD, discount rate
stated on every result (v0.6 §4B.1). Each has an unstated sub-convention that changes the
number, so each is pinned here.

**1.3.1 Discounting.** The discount rate is an **effective annual rate**. The mid-period
factor for month `m` (1-indexed) is

```
DF(m) = (1 + r) ** ( -(2m - 1) / 24 )
```

i.e. cash arrives at the midpoint of the month. Computed as
`exp( -(2m-1)/24 × ln(1+r) )` in `Decimal`, quantized to **12 decimal places**,
`ROUND_HALF_UP`. `Decimal.ln()` and `Decimal.exp()` are correctly rounded by the decimal
specification and are therefore identical across platforms; `math.pow` is not
(§1.12).

*Rejected:* nominal-rate-divided-by-12 monthly compounding (`(1 + r/12)^-(m-0.5)`). It
yields a materially different factor at the same quoted rate — at r = 10 % the two discount
factors differ by 0.41 % at month 12, 2.10 % at month 60, 4.17 % at month 120 and 8.18 % at
month 240 — and the industry quotes the annual effective figure
("NPV10"). Stating which one is in force is the point; `discount_convention:
"effective_annual_mid_month"` is a mandatory field on every valuation response.

*Rejected:* mid-period discounting of capex. Capex sits at **t = 0, undiscounted**
(`DF = 1.000000000000`), because a spud-date capital outlay is the reference point of the
NPV, not a cash event inside month 1. `capex_timing: "t0_undiscounted"` is stated on the
response; `capex_schedule` (§1.9) is the escape hatch for multi-month spend.

**1.3.2 Nominal, not real.** The deck is nominal USD. `opex_escalation_pct_yr` and
`price_escalation_pct_yr` both default to **0.0** and are stated on every response. A flat
nominal deck with zero escalation is a *stated assumption*, not an oversight — the
alternative (silent 2 % opex inflation, which several vendor defaults apply) is exactly the
hidden lever this project exists not to have.

**1.3.3 Economic limit.** Default policy `trailing_3_negative`: production is valued up to
the last month `M` such that no window of three consecutive months at or before `M` has
negative net operating cashflow (line 12). Volumes after `M` are not valued; abandonment
is applied at `M`. Alternatives, selectable and recorded: `first_negative`, and `never`
(value the full horizon). Rationale for the default: a single negative month from a
maintenance-driven opex spike or a one-month price dip should not truncate a well's life,
and `first_negative` makes NPV discontinuous in price, which breaks the linear breakeven
solve in §1.10 more often than it needs to.

**A royalty interest never goes cash-negative** (no opex, no capex), so its economic limit
cannot be derived from its own cashflow. Pinned: **the economic limit is a property of the
well, not of the interest.** A royalty valuation computes `M` from the working-interest
cashflow implied by the same assumption set, and the response states
`economic_limit_basis: "working_interest_implied"`. Without this, a royalty valuation runs
to the 360-month horizon on a well the operator would have plugged in year 9 — an error an
A&D analyst finds in the first review.

**1.3.4 Horizon and the extrapolation share.** `horizon_months` defaults to 360, capped at
600. SB-02's models are trained to cum12/cum24 (v0.6 §4A.2); everything beyond the trained
horizon is Arps hyperbolic with terminal exponential, labelled `modelled` and
`extrapolated` (v0.6 §4A.9). The valuation therefore carries a **mandatory**
`pv_share_from_extrapolated` field: the fraction of positive PV contributed by months
beyond the model's trained horizon. If 70 % of an NPV comes from extrapolated volumes, the
number is a decline-curve opinion wearing a valuation's clothes, and the response says so
rather than leaving the reader to work it out. A value above `0.60` additionally raises the
warning `pv_dominated_by_extrapolation`.

**1.3.5 Rounding.** All monetary quantities quantize to `0.01` with `ROUND_HALF_UP` at each
named line item in §1.2 — not once at the end. Volumes carry three decimals
(`numeric(18,3)`, SB-07 §3.2, §4.4). Percentages and rates are `Decimal`, never float.
Rounding at the line item, rather than at the total, is what makes the printed golden case
in §10.2 reproducible in a spreadsheet by hand.

**1.3.6 Time zero.** Month 1 is the first forecast month, which for a scenario is the
hypothetical first-production month and for a PDP valuation is the first month **after**
the last observed month at the requested `as_of` vintage. A PDP valuation therefore never
includes months already produced; `as_of_production_month` is stated on the response. Mixing
realized and forecast months in one NPV without saying so is how a "PDP value" quietly
becomes a "total well value".

### 1.4 The interest model — working vs royalty

v0.6 resolves the minerals persona by making NRI a user-supplied scalar defaulting to 0.75
(v0.6 §2.2, §3.4.4). That resolves *where the number comes from* and leaves *what the
number does* undefined, and the undefined half is the one that produces wrong dollars.
`econ_assumptions` (v0.6 §3.4.4) carries `capex`, `fixed_opex_per_month`, `opex_*`,
`abandonment_cost`, `wi` and `nri` with **no interest-type switch**, and U6 prices a royalty
through `POST /v1/valuations` with an `nri` parameter (v0.6 §6 U6, §3.6.12 #18). Under that
schema, valuing a 3/16 royalty means subtracting a full working-interest capex and opex
stream from 18.75 % of revenue. This is errata **E-1** (§11), and its magnitude on the
golden fixture is **$4.62 MM on a single well, with a sign flip** (§10.3).

Pinned model:

| Field | Values | Effect |
|---|---|---|
| `interest_type` | `working` \| `royalty` | Selects the arithmetic below. **No default** — the request must state it; a missing value is a `422`, not a guess |
| `royalty_kind` | `royalty` \| `orri` \| `nri_override` | Label only; identical arithmetic. Present so a response can say what was priced |
| `wi` | Decimal, default 1.00 | Share of costs. Ignored (must be null) when `interest_type = royalty` |
| `nri` | Decimal, default 0.75 **with a mandatory warning** (v0.6 §2.2) | Share of revenue |
| `post_production_deduct_pct` | Decimal, default 0.00, royalty only | Gathering/processing/compression deductions. Lease-specific and unknowable to glasswell; **always `assumed`**, never derived |

| Line | `working` | `royalty` |
|---|---|---|
| Revenue | `gross × NRI` | `gross × NRI × (1 − post_production_deduct_pct)` |
| Severance + ad valorem | `× NRI` | `× NRI` |
| Opex | `× WI` | **none** |
| Capex | `× WI` | **none** |
| Abandonment | `× WI` | **none** |
| Economic limit | own cashflow | working-interest implied (§1.3.3) |

**Why royalties still pay severance:** production taxes are levied on the value of
production at the wellhead and are borne by every revenue interest pro rata, including
royalty. Ad valorem treatment varies by state and by lease; glasswell applies it pro rata
by default and flags it `assumed`. Where a state's ad valorem is levied on the operator
rather than deducted from royalty (VERIFY gate V-6), that is a per-state row, not a code
branch.

**What glasswell still does not know and does not claim:** the actual burden stack for a
tract, whether a lease permits post-production deductions, and whether the interest is
subject to a shut-in or minimum royalty. All three are stated as out of scope in the
response's `assumption_warnings` block (v0.6 §2.2 — "the honest boundary").

### 1.5 Price decks as versioned data

**1.5.1 Object.** A deck is immutable and content-addressed (`deck_id = "dck_" +
base32(sha256(canonical_json(...)))[:12]`, matching SB-07 §1.3's id discipline).

| Field | Notes |
|---|---|
| `deck_id`, `name`, `created_at` | |
| `benchmark_oil`, `benchmark_gas`, `benchmark_ngl` | `WTI_CUSHING` \| `BRENT` \| `HH` \| `WAHA` \| `MTBELVIEU`. **New relative to v0.6** — 4B.5's "flat WTI price" is uncheckable if the deck never names its benchmark (errata **E-9**) |
| `price_series` | `{month: {oil, gas, ngl}}`, `Decimal`, nominal USD |
| `terminal_policy` | `flat_last` \| `escalate_pct` \| `explicit`; what happens past the last populated month |
| `basis_differentials` | `{basin: {oil: {form, value}, gas: {form, value}}}`, §1.6 |
| `deck_source` | `eia_steo` \| `manual_entry` \| `flat_assumption` \| `derived` |
| `source_manifest_id` | Set when the deck was built from a fetched artifact — **the deck's lineage terminates in a manifest like everything else** (SB-07 §2) |
| `derivation_id` | `deck.build` derivation |

**1.5.2 Flat, strip and scenario decks are all just decks** (v0.6 §4B.2). There is no
separate "flat deck" type; a flat deck is a `price_series` whose values are constant, and
its `deck_source` says `flat_assumption`.

**1.5.3 The default deck, and an improvement on OQ-6.** v0.6 records the default as a flat
assumption because no free redistributable forward strip is in hand, and files the gap as
`data-unreachable` for the E16 matrix (v0.6 §8.3 OQ-6, §4B.2). That gap is real for a
**NYMEX strip**, which is licensed. It is not the only option:

> **Proposed default: EIA Short-Term Energy Outlook (STEO) monthly price projections for
> the first ~24 months, held flat thereafter at the terminal STEO value.** [A — VERIFY V-1]
> STEO is published monthly by a US federal agency as machine-readable data, is US
> Government work and therefore not subject to domestic copyright, and gets a manifest,
> a checksum and a `deck.build` derivation like any other source.

This converts the default deck from an unevidenced assumption into a manifest-backed
artifact whose lineage chain terminates in a checksummed file — which is the whole thesis
applied to the one input v0.6 currently exempts from it. The honest gap does **not**
disappear: a STEO projection is a government forecast, not a market-clearing forward curve,
and the E16 row stays `data-unreachable` for *strip pricing* specifically. Both statements
go in the deck's provenance note. Adopting this is a change to v0.6 §4B.2 and OQ-6 and is
handed to SB-00 (§15). Until V-1 closes, the default remains a flat deck with
`deck_source = flat_assumption` and a stated provenance.

**1.5.4 NGL.** `decks.price_series` carries an NGL price (v0.6 §3.4.4) while v0.6 §2.3
defers NGL economics and the canonical stream vocabulary has no NGL volume
(`oil | gas | water | condensate`, v0.6 §3.4.3). The deck field is therefore currently
unconsumable — errata **E-3**. Resolution: keep the field (deck ids are immutable and
forward compatibility is free) and consume it only through an explicit
`ngl_yield_bbl_per_mmcf` assumption **defaulting to 0.0**, i.e. off. When non-zero it is
labelled `assumed` and a `ngl_yield_is_assumed` warning is attached, because a yield
glasswell cannot measure from public data is a guess with a decimal point.

### 1.6 Differentials

`basis_differentials` entries carry an explicit `form`:

| `form` | Meaning | Applied as |
|---|---|---|
| `additive_usd` | $/bbl or $/mcf added to the benchmark (negative for a discount) | `benchmark + value` |
| `pct_of_benchmark` | Fraction of the benchmark retained | `benchmark × value` |

v0.6 §3.4.4 gives `basis_differentials` with no unit and no form (errata **E-10**). The
distinction is not cosmetic: under a flat-price breakeven solve, an additive differential
shifts the breakeven by exactly its own magnitude, while a percentage differential scales
the slope `dNPV/dP` and moves the breakeven proportionally. Default form is
`additive_usd`, and the form is echoed on every valuation.

`gas_realization` is a separate multiplicative factor (default 1.000) covering shrink, fuel
and BTU adjustment as a single stated lever. It is `assumed` and it is **not** silently
folded into the differential, because a reader comparing glasswell to an operator's
disclosed realizations needs to see which knob moved.

### 1.7 Opex, including water

| Assumption | Unit | Default | Note |
|---|---|---|---|
| `fixed_opex_per_month` | USD/month | [A] $8,000 ND, $9,000 Permian — VERIFY V-2 | Lease operating expense floor: pumper, chemicals, surface maintenance |
| `opex_oil_per_bbl` | USD/bbl | [A] $2.00 | Gathering, treating, marketing on the liquid stream |
| `opex_gas_per_mcf` | USD/mcf | [A] $0.30 | Gathering and compression |
| `opex_water_per_bbl` | USD/bbl | [A] $1.50 ND, $0.75 Permian — VERIFY V-3 | **The reason three-stream forecasting pays for itself in economics** |
| `opex_escalation_pct_yr` | fraction | 0.00 | §1.3.2 |
| `workover_per_year` | USD/yr | [A] 0 | Off by default; a stated omission, not a hidden zero |

**Water is the point of E5's water-opex requirement** (v0.6 §5 E5, §4B.3). On the golden
fixture — a modest 1.2 water-oil ratio — a ±$0.50/bbl swing in water handling moves NPV by
±$56 k on a well whose base NPV is −$25 k (§10.4). At the water-oil ratios common in the
Delaware Basin (3–6× [A]), water handling is frequently the second-largest cost line after
capital, and a two-stream engine cannot see it at all. Water opex is a first-class
sensitivity parameter (§3.2), not a footnote.

All opex defaults are `assumed` and every one of them appears in the response's
`assumption_warnings` list with its default flag, so a user who never set an opex figure is
told which numbers they inherited.

### 1.8 Tax regimes as evidenced data rows

**1.8.1 Table.** `tax_regimes`, effective-dated and append-only, mirroring the evidence
discipline of `conformance_rules` (v0.6 §3.4.3) without being one (§1.8.4).

| Column | Notes |
|---|---|
| `tax_rule_id` | `tax_<state>_<stream>_<slug>_<n>`; immutable — a rate change is a new row |
| `state`, `stream` | `ND` \| `TX` \| `NM`; `oil` \| `gas` \| `condensate` \| `ngl` |
| `tax_kind` | `severance` \| `conservation` \| `school` \| `ad_valorem` \| `regulatory_fee` |
| `basis` | `pct_of_revenue` \| `per_unit` |
| `rate`, `rate_unit` | `Decimal`; `fraction` \| `usd_per_bbl` \| `usd_per_mcf` |
| `statute_ref` | e.g. `NDCC ch. 57-51.1` |
| `authority` | Publishing agency |
| `evidence_url`, `evidence_sha256` | **Non-null required to publish** (§1.8.5) |
| `effective_from`, `effective_to`, `supersedes_tax_rule_id` | |
| `applies_to_interest` | `all` \| `working_only`; supports the ad valorem case in V-6 |
| `notes` | Exemptions, triggers, and reduced rates that are **not** in the default |
| `confidence` | `verified` \| `assumed` — serving an `assumed` row attaches a warning |

**1.8.2 Seed rows.** Every rate below is **[A]** and carries a VERIFY gate. They are
recorded here so the gate has something concrete to check, not so they can be shipped.

| State | Stream | Kind | Basis | Rate [A] | Statute / authority | Gate |
|---|---|---|---|---|---|---|
| ND | oil | severance (gross production tax) | pct_of_revenue | 0.0500 | NDCC ch. 57-51; ND Office of State Tax Commissioner | V-4 |
| ND | oil | severance (oil extraction tax) | pct_of_revenue | 0.0500 | NDCC ch. 57-51.1 | V-4 |
| ND | oil | ad valorem | pct_of_revenue | **0.0000** | Gross production tax is imposed **in lieu of** property tax on producing properties | V-6 |
| ND | gas | severance (gross production tax) | **per_unit** | 0.1500 usd_per_mcf | NDCC 57-51-02.2; rate reset annually by the Tax Commissioner | V-4 |
| TX | oil | severance (crude oil production tax) | pct_of_revenue | 0.0460 | TX Tax Code ch. 202; TX Comptroller | V-5 |
| TX | condensate | severance | pct_of_revenue | 0.0460 | Taxed as oil | V-5 |
| TX | gas | severance (natural gas production tax) | pct_of_revenue | 0.0750 | TX Tax Code ch. 201 | V-5 |
| TX | oil | regulatory_fee (oil-field cleanup) | per_unit | 0.00625 usd_per_bbl | TX Natural Resources Code; RRC | V-5 |
| TX | gas | regulatory_fee (oil-field cleanup) | per_unit | 0.000667 usd_per_mcf | as above | V-5 |
| TX | both | ad valorem | pct_of_revenue | 0.0200 | County appraisal districts — **varies by county** | V-6 |
| NM | oil | severance (oil & gas severance tax) | pct_of_revenue | 0.0375 | NMSA ch. 7-29; NM Taxation & Revenue | V-7 |
| NM | oil | school (emergency school tax) | pct_of_revenue | 0.0315 | NMSA ch. 7-31 | V-7 |
| NM | gas | school (emergency school tax) | pct_of_revenue | 0.0400 | NMSA ch. 7-31 | V-7 |
| NM | both | conservation (oil & gas conservation tax) | pct_of_revenue | 0.0019 | NMSA ch. 7-30 | V-7 |
| NM | both | ad valorem (production tax) | pct_of_revenue | 0.0100 | NMSA ch. 7-32 — **district-varying** | V-6, V-7 |

**1.8.3 The ad valorem approximation, stated.** Ad valorem tax in Texas and New Mexico is a
*property* tax assessed on the appraised value of the mineral interest, not a percentage of
monthly revenue. Every quick-look economics model in the industry approximates it as a
revenue percentage, and so does glasswell — but the approximation is named in the response
(`ad_valorem_method: "revenue_pct_approximation"`) and its county/district variance is
flagged. Serving 2.0 % as though it were a rate rather than a modelling shortcut is exactly
the class of unlabelled estimate R5 exists to prevent (v0.6 §3.3 R5).

**1.8.4 Why these are not conformance rules.** R8 governs *cross-source mapping decisions* —
how a reported value from source A becomes a canonical value (v0.6 §3.3 R8). A severance
rate maps nothing; it is an economic assumption with a statutory source. Filing tax rows
as conformance rules would pollute R8's coverage CI check (v0.6 §3.6.11) with rows that
have no canonical field to cover, and would let a `tax_regimes` gap hide inside a green R8
coverage report. They get the same *evidence discipline* — immutable rows, effective dates,
evidence URL plus checksum, append-only supersession — under their own table and their own
CI check (§10.6).

**1.8.5 Publication gate.** The seed loader refuses any row with a null `evidence_url` or
`evidence_sha256`, and `GET /v1/assumptions/taxes` marks every `confidence = assumed` row
in its payload. A valuation whose tax rows include an unverified rate carries
`warnings: ["tax_rate_unverified"]` with the offending `tax_rule_id`s listed. **A number
this project cannot evidence is served with a flag or not at all** (v0.6 §2.5).

### 1.9 Capex and abandonment

| Assumption | Default | Notes |
|---|---|---|
| `capex` | **required**; no default | Total D&C plus facilities, 8/8ths. [A] indicative range for a two-mile ND Bakken lateral is $7.5–9.5 MM (VERIFY V-8) but glasswell ships **no default** — a wrong capex is the single fastest route to a wrong NPV, and inheriting one silently is worse than being asked |
| `capex_schedule` | `t0_lump` | Alternative `spread_months: n` distributes evenly across months 1..n **and discounts each tranche**; the chosen form is echoed |
| `abandonment_cost` | [A] $75,000 ND (VERIFY V-9) | Applied at the economic limit or horizon end, `× WI`; zero for royalty |
| `salvage_value` | 0 | Off by default and stated |

### 1.10 Breakeven

**Definition (v0.6 §4B.5):** the flat benchmark oil price at which NPV at the stated
discount rate equals zero, holding the deck's differentials, the gas price, and all
assumptions constant. Three sub-conventions v0.6 leaves open, pinned here and echoed on
every response:

- `breakeven_benchmark`: the deck's `benchmark_oil`. "Flat WTI" is only meaningful if the
  deck says the benchmark is WTI.
- `breakeven_gas_policy`: `hold_deck` (default) or `link_ratio` (gas scales with the oil
  price at a stated ratio). Holding gas constant while sweeping oil is the industry default
  and it is also *wrong* in a directional sense for gassy wells; saying which was used is
  the requirement.
- `breakeven_quantile`: breakeven is computed **per forecast quantile**, giving three
  values. `valuations.breakeven_price` as a scalar (v0.6 §3.4.4) cannot represent this —
  errata **E-4**.

**Solve method.** Within a fixed economic-limit truncation month, NPV is *exactly affine*
in the flat oil price: revenue is linear in price, percentage severance and ad valorem are
linear in revenue, and opex, capex and volumes do not depend on price. Verified on the
golden fixture: NPV(63) = −494,714.60, NPV(70) = −24,613.61, NPV(77) = +445,487.38 — two
differences of exactly 470,100.99 (§10.4). Therefore:

```
1. evaluate NPV at the deck price P0 and at P0 + $1.00  →  slope B
2. P* = P0 − NPV(P0)/B
3. re-evaluate the economic-limit month at P*; if it moved, repeat from 1 at P0 = P*
4. converges in ≤ 5 iterations; report P* quantized to $0.01
```

Two evaluations per iteration, typically one iteration — versus ~40 for bisection. The
response reports `npv_at_breakeven` (the residual, $234.59 on the golden case) so the
reader can see the price-granularity effect rather than being handed a false zero.
**Bisection remains the test oracle** (test ECON-B3, §10.5): the analytic solve must match
a 200-iteration bisection to the cent.

**Non-solutions are reported, not hidden.** `no_breakeven_below_cap` when NPV < 0 at the
$400/bbl cap; `breakeven_at_or_below_zero` when NPV ≥ 0 at $0/bbl (possible for a
gas-weighted well or a zero-capex royalty). Both return `breakeven_price: null` with the
reason code, never a sentinel number.

**Monotonicity precondition.** The solve assumes NPV is non-decreasing in price. This holds
whenever the per-unit oil margin (realized price − per-bbl opex − per-bbl taxes) is
positive; a negative-margin month would invert it. The engine checks the margin sign per
month, and if any valued month is negative it attaches `nonmonotone_margin` and falls back
to bisection over a bracketed scan. Property test ECON-B1 asserts monotonicity across a
price grid (§10.5).

### 1.11 Payout — both of them

v0.6's glossary defines payout as "the number of months until cumulative **discounted** cash
flow turns positive" (v0.6 §9). The industry default is **undiscounted** payout, and the two
differ (month 11 vs month 12 on the golden fixture, §10.2). Serving one under the other's
name is a small error with an outsized credibility cost — errata **E-2**.

Resolution: serve **both**, always, under unambiguous names, and let neither be "payout"
without a qualifier.

| Field | Definition |
|---|---|
| `payout_months_undiscounted` | First month where cumulative (net operating CF − capex) > 0 |
| `payout_months_discounted` | First month where cumulative (PV of net operating CF − capex) > 0 |
| `payout_basis` | `"from_first_production"` — capex at t = 0 is the reference |

`null` when payout is not reached within the horizon (the P10 case on the golden fixture),
never a sentinel like 999.

### 1.12 Numeric policy and determinism

SB-07 §4.4 pins DECIMAL for volumes and money, and notes that float summation order varies
with DuckDB's parallel scan plan. SB-03 extends it to the last remaining float:

- **Every quantity in the econ path is `Decimal`.** Prices, rates, volumes, factors, and
  the discount factor itself. There is no float in `glasswell/econ/dcf.py`. Test ECON-P3
  greps the module AST for float literals and `float(` calls and fails on any hit.
- **The discount factor is the trap.** `math.pow(1.10, -0.0416667)` is a libm call whose
  last ulp is not guaranteed identical across CPU vendors, glibc versions or build flags —
  which would make an otherwise-D1 artifact non-reproducible for a reason nobody would look
  for. `Decimal.ln()`/`Decimal.exp()` are correctly rounded by the decimal specification
  and are the pinned implementation (§1.3.1).
- **Determinism class D1** (SB-07 §4.2): the valuation Parquet is byte-identical on replay
  in any pinned environment. Unlike model artifacts (D2), the econ path has no
  library-version sensitivity beyond `decimal`, which is stdlib and specified.
- **`econ_engine_version`** is recorded in every `econ.value` derivation's params. A
  convention change (a new rounding rule, a new default) is a version bump, so old
  valuations remain explicable rather than becoming quietly irreproducible.

### 1.13 What the valuation carries — R5 labelling

Every valuation figure carries, without exception:

| Field | Value |
|---|---|
| `unit` | `USD` (SB-07 §9.1 makes units mandatory) |
| `granularity` | `modelled` — a valuation is never an observation |
| `volume_granularity` | `observed` \| `allocated` \| `modelled` — the weakest granularity of the volumes that fed it (v0.6 §3.3 R5) |
| `error_bounds` | Mandatory when `volume_granularity = allocated` (DIR-3; SB-07 §10 Check 5) |
| `deck_id`, `assumption_id`, `model_id`, `forecast_id` | The four inputs, always |
| `discount_rate`, `discount_convention`, `capex_timing` | §1.3.1 |
| `interest_type`, `wi`, `nri` | §1.4 |
| `quantile_convention` | `"statistical_ascending"` — §2.1 and errata **E-5** |
| `pv_share_from_extrapolated` | §1.3.4 |
| `assumption_warnings[]` | Every defaulted or unverified input, named |
| `d` | The derivation handle (SB-07 §1.3) |

**"NPV10" is never emitted as a bare string** (v0.6 §4B.1). The rate is a field; the label
is a rendering.

---

## 2. Uncertainty propagation — what the band is and is not

This section exists because it is the one where a data-science reviewer can most easily
dismantle a valuation product, and because v0.6 §4B.7 ("no dollars without a band") states
the requirement without stating the semantics.

### 2.1 What the three quantiles are

SB-02 produces P10/P50/P90 per stream from a LightGBM quantile objective wrapped in
split-conformal calibration, with nominal 80 % central coverage measured empirically
(v0.6 §4A.7). Three properties matter here and only one of them is usually stated:

1. They are **marginal** quantiles of a single well's production target. They carry no
   information about the joint distribution across wells, across streams, or across months.
2. Conformal coverage is a statement about **intervals**, not about points: the
   [P10, P90] interval covers the realized value at a measured rate. P50 is a point
   estimate with no coverage claim attached.
3. **The convention is statistical-ascending**: P90 is the 90th percentile, i.e. the
   *high* production case. v0.6's glossary defines it this way and then calls P90 "the
   conservative case for value" (v0.6 §9), which is the petroleum-reserves convention
   (where P90 means 90 % probability of exceeding, i.e. the low case) leaking into a
   statistical definition. Under the stated definition, P90 production is the *optimistic*
   value case. This is errata **E-5** and it is the single most likely thing to be misread
   by a reserves-literate user, so `quantile_convention: "statistical_ascending"` is a
   mandatory field on every forecast-derived figure and the glossary row is corrected.

### 2.2 The quantile-coherent stream bundle

The naive construction — take P90 oil, P90 gas and P90 water and run one DCF — is what most
of the category does silently, and it is incoherent. Water is a **cost** stream. A "P90
everything" case pairs the highest oil with the highest water disposal bill, which is not
the upside scenario; the real upside is high oil with *low* water. Stacking same-labelled
marginals across streams implicitly assumes perfect rank dependence between a revenue
stream and a cost stream, which no one would assert out loud.

**Decision.** NPV at quantile `p` is computed from a **coherent bundle**:

- **Oil** at its quantile-`p` path (oil is the headline stream, v0.6 §4A.2).
- **Gas** at `oil_p × GOR_p50[m]`, where `GOR_p50` is the P50 gas-oil ratio path.
- **Water** at `oil_p × WOR_p50[m]`, where `WOR_p50` is the P50 water-oil ratio path.

Justification: GOR and water cut are the physically stable, engineering-legible ratios and
v0.6 already treats them as derived surfaces rather than independent targets (v0.6 §4A.11).
Holding the ratio and moving the oil path is the closest available approximation to
"gas and water at their conditional expectation given oil at quantile p" without a joint
model. The bundle is named on the response as
`stream_coupling: "p50_ratio_to_oil"`.

**Alternatives considered and rejected:**

| Alternative | Why rejected |
|---|---|
| Same-quantile stacking across all three streams | Incoherent (above); systematically overstates downside for wet wells and understates upside for dry ones |
| Independent sampling of the three streams | Requires a joint distribution nobody has estimated; produces gas/oil ratios that are physically impossible in the tails |
| A joint three-stream quantile model | The correct long answer. Out of scope for v0; handed to SB-02 as OQ-S3 (§15) |

`stream_coupling: "independent_marginals"` remains selectable so the difference can be
*measured* and written up (Mandate B, v0.6 §1.1), but it is never the default and its
response carries `incoherent_stream_bundle` as a warning.

### 2.3 What can honestly be claimed about the NPV band

Given the bundle, NPV as a function of the oil path is a **monotone non-decreasing map**
whenever the per-unit oil margin is positive in every valued month (§1.10). Under
monotonicity, two things follow exactly, and they are the strongest defensible claims
available:

**(a) Quantile equivariance.** For a monotone non-decreasing `g`, `Q_p(g(X)) = g(Q_p(X))`.
So `NPV(oil path at P90)` **is** the 90th percentile of NPV — *conditional on* the deck and
assumptions being certain and on the ratio coupling holding. It is not an approximation of
it. This is why the monotonicity precondition is checked rather than assumed.

**(b) Coverage transfer.** A monotone map preserves interval coverage:
`P(oil ∈ [Q10, Q90]) = P(NPV ∈ [NPV(Q10), NPV(Q90)])`. Therefore the *measured* empirical
coverage of the production interval (v0.6 §4A.8, published per slice) transfers unchanged
to the NPV band. glasswell can state a measured coverage figure for a dollar band, which
is a rare and genuinely defensible claim — and it rests entirely on monotonicity, which is
why §2.5 makes the guard explicit rather than trusting it.

### 2.4 What is *not* claimed

Stated on the response as `band_semantics` and in the glossary, because the failure mode is
a reader assuming more than was offered:

1. **The band is production uncertainty only.** The deck and the assumption set are treated
   as certain. Price, capex, opex and NRI uncertainty are **not** in the band; they are the
   tornado's job (§3), and the two must never be added together as though they were one
   interval.
2. **It is not a confidence interval** in the frequentist sense and not a credible interval.
   It is a conformal prediction interval mapped through a deterministic function.
3. **Coverage is a fleet property, not a per-well guarantee.** Conformal coverage holds
   marginally over the calibration population; it says nothing about this particular well.
4. **It does not survive a non-monotone margin.** When any valued month has a negative
   per-unit margin, claims (a) and (b) are void; the response drops to
   `band_semantics: "unordered_scenario_evaluations"` and says so.
5. **Extrapolation dominance voids it in practice.** When `pv_share_from_extrapolated`
   exceeds 0.60, the band is measuring Arps parameter choices more than model uncertainty
   (§1.3.4).

### 2.5 Input guards at the econ boundary

The econ engine validates what SB-02 hands it and refuses malformed input. Silent coping is
how a quantile crossing becomes a negative-width NPV band on a chart.

| Guard | Condition | Failure |
|---|---|---|
| `quantile_noncrossing` | `p10[m] ≤ p50[m] ≤ p90[m]` for every month and stream | `422 quantile_crossing` naming the month. Quantile regression crosses; **isotonic rearrangement is SB-02's job**, and SB-03 will not paper over its absence |
| `nonnegative_volumes` | all volumes ≥ 0 | `422 negative_volume` |
| `ratio_sanity` | GOR and WOR paths finite and non-negative; GOR ≤ 100 mcf/bbl [A] | `422 implausible_ratio` |
| `horizon_alignment` | forecast horizon ≥ 1 month; deck covers month 1..horizon or has a `terminal_policy` | `422 deck_horizon_short` |
| `margin_sign` | per-unit oil margin > 0 in every valued month | warning `nonmonotone_margin`; band semantics downgraded (§2.4) |
| `support_present` | `training_support` is non-null | `422 missing_training_support` — 4A.10 makes it a gate, and a gate that accepts null is not a gate |

---

## 3. Sensitivities and the tornado

### 3.1 Semantics

One-at-a-time deltas around a stated base case, ranked by absolute NPV change
(v0.6 §4B.6). Everything about the base case is echoed, because a tornado without its base
is decoration:

- The base is a specific `valuation_id`, therefore a specific
  `(forecast_id, deck_id, assumption_id, quantile, horizon)`.
- **The base quantile is stated.** A tornado on a P50 base and a tornado on a P90 base are
  different charts. `sensitivities` in v0.6 §3.4.4 has no quantile column — errata **E-6**.
- Each row states its parameter, its delta form, its two perturbed NPVs, the two signed
  deltas, and the span (the bar length).
- Deltas are **one-at-a-time**; no interaction terms, no combined cases, and the response
  says so (`method: "one_at_a_time"`). A user who adds two bars together is making an
  assumption glasswell did not make.

### 3.2 Parameter set

4B.6 lists five parameters: price, capex, opex, water handling, and cum12 forecast error
(v0.6 §4B.6). For the A&D and minerals personas that list is missing the two levers that
most often decide a deal. Proposed extension (a 4B.6 amendment, handed to SB-00, §15):

| # | Parameter | Default delta | Rationale |
|---|---|---|---|
| 1 | `forecast_cum12` | P10 / P90 bundle (§2.2) | Uses the model's own uncertainty rather than an invented ±% |
| 2 | `oil_price_flat` | ±10 % of the deck benchmark | 4B.6 |
| 3 | `capex` | ±10 % | 4B.6 |
| 4 | `opex_all` | ±10 % on all opex lines | 4B.6 |
| 5 | `opex_water` | ±$0.50/bbl | 4B.6 — separate, per E5's explicit water requirement |
| 6 | **`oil_differential`** | ±$2.00/bbl | **New.** Basin differentials move by more than this in a quarter and they are pure margin |
| 7 | **`nri`** | ±0.05 | **New.** The minerals persona's entire question is an NRI question (v0.6 §2.2, U6) |
| 8 | **`discount_rate`** | 8 % / 12 % | **New.** Buyer and seller argue about this number more than any other |
| 9 | `gas_price_flat` | ±10 % | Included for gassy wells; usually a short bar in the Bakken, which is itself informative |

Every delta is a **request parameter with a stated default**, never a hardcoded constant.
The response echoes the deltas used.

### 3.3 Output schema

```json
{
  "sensitivity_id": "sen_…",
  "base": {"valuation_id": "val_…", "npv": {"value": "-24613.61", "unit": "USD",
            "granularity": "modelled", "volume_granularity": "modelled",
            "d": "drv_…#col=npv"},
           "quantile": "p50", "deck_id": "dck_…", "assumption_id": "asm_…",
           "discount_rate": "0.10", "horizon_months": 12},
  "method": "one_at_a_time",
  "rows": [
    {"parameter": "forecast_cum12", "rank": 1,
     "low":  {"label": "P10", "value": "-1201694.26", "npv_delta": "-1177080.65"},
     "high": {"label": "P90", "value": "1446737.20",  "npv_delta": "1471350.81"},
     "span": "1471350.81", "unit": "USD", "d": "drv_…#parameter=forecast_cum12"}
  ],
  "warnings": []
}
```

Rows are returned **pre-sorted by `span` descending** with an explicit `rank`, because a
tornado is defined by its ordering and re-sorting client-side invites two clients to
disagree about the same data. Ties break on parameter name ascending, so the ordering is
deterministic.

### 3.4 Cost

A nine-parameter tornado is 18 valuations. Each is a pure call on an already-loaded forecast
with a perturbed deck or assumption set, and each perturbed input is itself
content-addressed — so a repeated tornado on the same base is 18 cache hits and zero
compute (§1.1). This is the concrete cash value of R3, and §4.2 budgets it at 90 ms warm.

**Perturbed inputs create real, immutable objects.** Bumping capex by 10 % constructs a new
`assumption_id`; the sensitivity row cites it. There is no "temporary" assumption set,
because a valuation that cites an object which no longer exists cannot be replayed (R7).

---

## 4. The scenario loop (C11) and the S3 budget

### 4.1 Pipeline

`POST /v1/scenarios` — design + location → features → forecast → valuation → analog panel,
persisted and addressable (v0.6 §5 E6, §3.6.12 #11).

```
 1. validate design + location            (SB-03)
 2. resolve as_of vintage, model, deck, assumptions   (SB-07 resolve_model, §3.6.6)
 3. spatial context: land unit, spacing unit, neighbours, parent-child depletion
    as of the scenario's completion date, in the basin's projected CRS   (SB-01/PostGIS)
 4. feature vector assembly + availability-date enforcement (R4)          (SB-02)
 5. forecast: 3 streams × 3 quantiles + non-crossing check + Arps extension (SB-02)
 6. valuation: coherent bundle → 3 DCFs → NPV/breakeven/payout             (SB-03 §1)
 7. analog panel: KNN query + agreement test                               (SB-02 + §4.4)
 8. persist scenario, attach derivation handles, assemble envelope         (SB-07/SB-04)
```

Steps 5–7 each open a `derive()` context (`forecast.scenario`, `econ.value`,
`analog.query`), nested under one `forecast.scenario` parent via contextvars (SB-07 §11), so
the scenario's `/explain` chain is one graph rather than three orphans.

### 4.2 Where the 3 seconds go

S3: forecast plus NPV in under 3 s, p95, single scenario, warm (v0.6 §2.4 S3). All figures
**[A]**, to be replaced by measurements at P4 exit (VERIFY V-10); the budget's purpose is to
say in advance which stage is allowed to be slow.

| Stage | p95 budget | Note |
|---|---|---|
| Access JWT validation, key auth, request validation | 25 ms | SB-04 |
| Scenario dedupe lookup (content-addressed) | 15 ms | Hit → jump to step 8 |
| **Spatial context in projected CRS (PostGIS)** | **900 ms** | **The dominant term.** Neighbour set, perpendicular distances, parent-child depletion as of completion date |
| Feature vector assembly (Polars, one row) | 60 ms | |
| Model inference: 3 streams × 3 quantiles | 40 ms | Nine single-row LightGBM predicts |
| Non-crossing validation + Arps extension to 360 months | 80 ms | |
| **DCF: 3 quantile paths × 360 months, Decimal** | **120 ms** | ~16 k Decimal ops per path |
| Breakeven: ≤ 2 linear regimes × 3 quantiles | 90 ms | §1.10; ~6 extra DCF evaluations |
| Analog query over the persisted KNN index | 120 ms | SB-02; index always persisted (v0.6 §8.1 D-23) |
| Derivation capture: 4 nodes + edges | 60 ms | SB-07 |
| Envelope assembly, `figure()`, glossary labels | 50 ms | SB-04, DIR-8 |
| Serialization and transit | 90 ms | |
| **Total, warm** | **≈ 1,650 ms** | **45 % headroom** |
| Cold (spatial cache miss) | ≈ 2,550 ms | Still inside 3,000 ms |

**Design consequences that follow from the table, not from taste:**

- The spatial context is 55 % of the warm budget, so it is **the thing that gets cached**,
  keyed on `(land_unit_id, formation_id, as_of_vintage, spacing_assumption_ft)` and
  invalidated on a new canonical vintage for the relevant partition. A design sweep — the
  actual E6 workflow, where a user moves lateral length and proppant intensity at one
  location — reuses one spatial context across every scenario in the sweep.
- The DCF is **not** the bottleneck, which is why Decimal is affordable (§1.12). If it ever
  became one, the answer is a narrower default horizon, not floats.
- **Breakeven is on the interactive path** because it is one of the two numbers the A&D
  persona actually wants (U4); the linear solve is what makes that affordable.
- The analog query is on the path because E6's acceptance requires the panel on the card
  (v0.6 §5 E6). If the budget is breached in practice, the analog panel is the first thing
  to move to a follow-up request — a documented degradation, not a silent one.

**Two budgets v0.6 §3.7.8 omits**, proposed here as additions (errata **E-18**), both
derived from the table above rather than guessed:

| Endpoint | p95 budget | Derivation |
|---|---:|---|
| `POST /v1/valuations` | **400 ms** | Auth + load + 3 DCFs + breakeven + capture + envelope; no spatial context, no inference |
| `POST /v1/sensitivities` | **1,500 ms** | 18 perturbed valuations, all cache-hit-eligible; cold worst case is 18 × the DCF+breakeven terms |

**Budget-breach conditions** (each is a `/v1/health` signal, v0.6 §3.7.7): analog index
rebuild in flight, a training job escaping the CPU cap (v0.6 §3.7.3 forbids it), spatial
cache miss coinciding with a PostGIS autovacuum, or a cold Decimal context in a fresh
worker.

### 4.3 Caching is content addressing, not a cache

There is no separate cache tier. A repeat scenario with an identical design, location,
`as_of`, model, deck and assumption set produces an identical `derivation_id` (SB-07 §1.3)
and the stored artifact is returned. Consequences worth stating:

- A sensitivity sweep, an inventory batch, and an interactive re-request all hit the same
  store, so the numbers cannot diverge between paths (test BATCH-EQUIV, §10.5).
- Request-time derivations for unsaved scenarios are `ttl_class = ephemeral` and swept at
  90 days (SB-07 §1.6); a scenario the user **saves** pins its derivation to `permanent`.
- Under DIR-2 the cache key includes `as_of`, so a restatement produces a new key rather
  than a stale hit. This is the correctness argument for content addressing over a TTL
  cache, and it is why no TTL cache appears anywhere in this design.

### 4.4 Analog panel integration

The panel answers "have wells like this actually done what you are being told this one will
do" — which is the only cheap check on a model that exists (v0.6 §6 U17, §5 E6).

**Contract.** For a `scenario_id`, `GET /v1/analogs?scenario_id=…&n=10` returns ranked
analogs with feature distance and *actual* outcomes (v0.6 §3.6.12 #10). SB-03 adds two
things on top of SB-02's index:

1. **Analogs valued at the same deck.** Each analog's realized production to date is run
   through the same `value()` with the same deck and assumption set, producing
   `npv_realized_to_date`. This is free under R3 and it is the panel's most useful column:
   what these wells actually earned at your prices. It is labelled
   `volume_granularity: observed`, `partial_life: true`, and it is **never plotted on the
   same axis** as the scenario's full-life NPV without a visual break — a partial-life
   realized NPV and a full-life forecast NPV are different quantities and putting them on
   one axis is a category error (SB-05 obligation, §12).
2. **The agreement test (E6 acceptance).** E6 requires that "support and analogs agree or
   the divergence is displayed" (v0.6 §5 E6). Made concrete:

   > **AGREE-1.** Let `Q1, Q3` be the interquartile range of the top-10 analogs' actual
   > cum12 oil **per 1,000 ft** (per-kft normalization, because this is a cross-well
   > comparison — v0.6 §8.1 D-2). If the scenario's P50 cum12 oil per 1,000 ft falls outside
   > `[Q1, Q3]`, emit `analog_divergence` carrying the scenario value, `Q1`, `Q3`, the
   > analog count, and the scenario's `training_support`.

   The warning is not a failure. A high-support scenario that diverges from its analogs is
   interesting (the model has found something the neighbours did not do); a *low*-support
   scenario that diverges is a red flag. Both are shown with the numbers, and the UI is
   required to render the warning whenever it renders the NPV (SB-05 obligation).

   AGREE-1 is the per-scenario instrument; 4A.12's fleet-level analog-quality check
   (v0.6 §4A.12) is SB-02's and reports like calibration. They are deliberately different
   tests at different scopes.

---

## 5. Well sets and portfolio rollups

### 5.1 Aggregation semantics

The trap in a rollup is not the summing; it is the averaging. Pinned per metric class:

| Metric class | Rule | Why |
|---|---|---|
| Volumes, revenue, cost, capex, NPV | **Sum** | Additive quantities |
| Per-kft metrics (`cum12_per_kft`) | **Lateral-weighted mean** = `Σ(value × ft) / Σ ft` | An unweighted mean of ratios over-weights short laterals |
| Ratios (GOR, water cut, realized price) | **Ratio of sums**, never mean of ratios: `GOR = Σ gas / Σ oil` | Mean-of-ratios is Simpson's paradox with a chart attached |
| Breakeven | **Set-level re-solve**, not an average of per-well breakevens | The set's breakeven is the flat price at which the *set's* NPV is zero; averaging per-well breakevens weights a marginal well equally with a large one |
| Payout | Set-level from the summed cashflow | Same argument |
| Quantile-labelled NPV | §5.2 — **not a sum without a stated dependence assumption** | |
| `training_support` | Distribution (min/p10/p50/p90/max) + share below floor, never a mean | A mean support of 0.6 hides a set half of which is unsupported |

### 5.2 The percentile aggregation decision

**The problem, stated precisely.** P10s do not sum. `Q_p(ΣX_i) ≠ ΣQ_p(X_i)` except under
perfect positive dependence (comonotonicity), in which case it holds exactly. The three
conformal quantiles per well are **marginal** and carry zero joint information (§2.1), so no
amount of arithmetic on them can produce a portfolio quantile without an added assumption.
Every product in this category ships the naive sum; most do not say so.

**Decision — three numbers, each with its assumption named:**

| Served field | Definition | Dependence assumption | Label |
|---|---|---|---|
| `npv_expected` | `Σ E[NPV_i]`, with `E[NPV_i] ≈ 0.30·P10 + 0.40·P50 + 0.30·P90` (three-point rule) | **None.** Linearity of expectation holds under any dependence | **Headline** |
| `npv_band_comonotonic` | `(Σ P10_i, Σ P50_i, Σ P90_i)` | ρ = 1 (perfect rank dependence) | `comonotonic_bound` — an **upper** bound on dispersion |
| `npv_band_independent` | `Σμ ± 1.2816 · sqrt(Σσ_i²)`, σ from the same three-point moments, normal approximation to the sum | ρ = 0 | `independence_reference` — a **lower** bound on dispersion |

**Why the expectation is the headline.** It is the only aggregate that is unconditionally
correct. It is also the one that exposes the trap: on the golden fixture, a 40-well set of
identical wells has `Σ P50 = −$984,544` and `Σ E = +$2,546,698` — a $3.53 MM swing, and a
sign flip, purely because the per-well NPV distribution is right-skewed and the median is
not the mean (§10.6). An analyst who sums P50s and calls it the portfolio's expected value
is off by that much, in that direction, every time.

**Why both bands and not one.** The true portfolio quantile lies between them for any
non-negative dependence, which is the realistic case (wells in a basin share price, rock
trend, operator and model error). Reporting the bracket is honest; picking a point inside it
requires a correlation glasswell has not measured. For n identical wells the ratio of the
two band widths scales as `√n` — **6.36× at n = 40** on this fixture (§10.6) — which is the
whole reason this matters: the comonotonic band on a 40-well portfolio is **six times too
wide**, and the independent band is too narrow. A single unlabelled number would be wrong
by that factor in one direction or the other.

**Guards.**
- `npv_band_independent` is **suppressed for n < 20** (`independence_band_suppressed_small_n`)
  — the CLT step is not credible on a handful of wells.
- It is also suppressed when the per-well coefficient of variation exceeds 2.0
  (`independence_band_suppressed_high_cv`): the three-point moment approximation degrades
  badly for heavily skewed distributions, and a well whose P10 NPV is negative and P90 NPV
  is large positive is exactly that case.
- `npv_band_comonotonic` is **never** labelled `portfolio_p10/p50/p90`. The field names
  carry the assumption. A client that renames it is violating the contract, and the CSV
  export column headers carry the same names (§9).
- The three-point weights, the z-value, and the CV threshold are recorded in the rollup's
  derivation params, so the method is inspectable rather than folkloric.

**The measurement that would close this.** SB-02's temporal holdout produces per-well
forecast residuals. The cross-well correlation of those residuals — by basin, vintage, and
distance — is directly estimable, and with it the bracket collapses to a single Gaussian-copula
band with a *measured* ρ. That is real work with a real answer, and it is handed to SB-02 as
**OQ-S1** (§15) rather than guessed at here. Until it exists, the bracket is the honest
answer and the E16 capability-matrix row says so.

*Rejected:* Monte Carlo over fitted per-well distributions. It requires a distributional
family assumption that is less inspectable than the moment method, introduces a seed into a
D1 artifact, and — decisively — its extra precision is entirely spent on a correlation
parameter that is currently a guess. Deterministic analytic bounds beat a precise answer to
an unasked question.

### 5.3 Mixed sets

A well set is user-assembled and will be heterogeneous. Three cases, each with a pinned
behaviour rather than an accident:

| Case | Behaviour |
|---|---|
| **Mixed granularity** (ND observed + TX allocated) | The rollup's `volume_granularity` is the weakest member (`allocated`), the response reports the **share by granularity**, and the allocated members' `error_bounds` aggregate comonotonically with the same labelling discipline as §5.2. DIR-3: estimates never pose as observations, and one allocated well makes the total an estimate |
| **Mixed state** (ND + TX + NM) | Tax rows resolve **per well from the well's state**, never from a set-level scalar. `econ_assumptions.state` is a single column in v0.6 §3.4.4 — errata **E-7**. The assumption set carries a base plus a per-state tax overlay; the response lists every `tax_rule_id` applied and the well count per state |
| **Mixed interest type** | Rejected: `422 mixed_interest_type`. Summing a royalty NPV and a working-interest NPV produces a number with no owner. Two sets, two rollups |

---

## 6. Inventory engine v0 (C22, E17)

**Conditional feature.** E17 is second in the cut order and S12 is conditional on it
surviving (v0.6 §2.4, §7.4, resolving D-16). If cut, the E16 matrix records inventory as
*effort-unreachable* with the cut decision cited; this section is then unbuilt, not
half-built.

### 6.1 Scope

**PLSS-based, North Dakota only** (v0.6 §4D.4, §8.1 D-11, closing D-12). A slot references a
`land_unit_id` of system `plss`. TX inventory geometry is a named deferred design task
(OQ-11). The `land_units` abstraction exists from P0 so TX is a design problem, not a schema
migration.

**Unit of work.** A run is scoped to one `area_ref` (a PLSS township or section), one
`spacing_assumption_ft`, one **target formation list**, and one **design template**.

> `inventory_runs` in v0.6 §3.4.4 carries `area_ref`, `spacing_assumption_ft`, `model_id`,
> `deck_id`, `assumption_id` — and **no target formation and no design**. You cannot forecast
> a slot without a landing zone and a completion design, and the Bakken petroleum system has
> multiple benches (Middle Bakken, Three Forks 1/2/3) that are developed on separate spacing.
> A run without a bench list produces a slot count that means nothing. Errata **E-11**.

### 6.2 Slot generation

Deterministic by construction — no randomness, no iteration order dependence, because slot
geometry feeds a D1 artifact.

```
for each (spacing_unit ∈ area, target_formation ∈ run.formations):
  1. azimuth  := circular median azimuth of existing producing laterals in the unit
                 and formation; fallback to the unit polygon's long axis when none exist.
                 Recorded per unit; a unit that used the fallback is flagged.
  2. corridor := unit polygon buffered inward by boundary_setback_ft
  3. offsets  := parallel candidate centrelines across the corridor's short axis at
                 spacing_assumption_ft, indexed from the westmost/southmost edge
  4. for each candidate, clip to the corridor and compute usable_length_ft
  5. admissibility filters (§6.3)
  6. greedy packing: order surviving candidates by
     (distance_to_nearest_existing_lateral DESC, offset_index ASC);
     accept a candidate only if it is ≥ spacing from every already-accepted slot
  7. emit slots with geometry, admissibility flags, and the azimuth provenance
```

All geometry is computed in the basin's projected metre-based CRS from `crs_registry`
(v0.6 §3.0.3), never in degrees. Every distance figure the run emits is a PostGIS result
that materializes back into DuckDB with a derivation reference (v0.6 §3.5).

**Determinism notes:** the circular median is computed over a sorted azimuth list with a
pinned tie-break; the offset index is deterministic from the corridor's bounding geometry;
the greedy ordering has an explicit total order. Test INV-13 runs a township twice and
asserts identical slot geometry hashes.

**Honest gap, recorded at the moment of design** (v0.6 §2.5): slots are **subsurface
admissible only**. Surface constraints — existing pads, water bodies, roads, occupied
dwellings, refusals — are not modelled, because glasswell has no free source for them. The
run response carries `surface_constraints_modelled: false` and the notebook gets a memo
(E15). A slot count that ignores the surface is an upper bound and is labelled as one.

### 6.3 4D as testable assertions

Every clause of protocol 4D (v0.6 §4D) becomes a named invariant with a test and a defined
failure mode. This table is the acceptance surface for E17.

| ID | 4D clause | Invariant | Failure mode |
|---|---|---|---|
| **INV-01** | 4D.1 | `slot.usable_length_ft ≥ run.min_lateral_ft` (default 8,000 [A]) | Candidate dropped, counted in `rejected_by_reason.too_short` |
| **INV-02** | 4D.1 | Perpendicular distance from slot centreline to **every existing producing lateral in the same target formation** ≥ `spacing_assumption_ft` | Dropped; `too_close_existing` |
| **INV-03** | 4D.1 | Pairwise distance between accepted slots ≥ `spacing_assumption_ft` | Rejected by the packing step; `too_close_slot` |
| **INV-04** | 4D.1 | `ST_Within(slot, corridor)`; corridor = unit inset by `boundary_setback_ft` (default 500 ft [A] — VERIFY V-11) | Dropped; `setback_violation` |
| **INV-05** | 4D.1 | Every distance computed in `crs_registry.compute_crs` for the basin; **zero degree-space distance calls** | Build-time assertion: no `ST_Distance` on a 4326 geometry in `glasswell/scenarios/inventory/**` |
| **INV-06** | 4D.1 | Slot azimuth within ±15° of the unit's recorded azimuth (tolerance [A] — VERIFY V-12) | Dropped; `azimuth_nonconforming` |
| **INV-07** | 4D.2 | **Every** slot forecast carries a non-null `training_support` | `500 inventory_invariant_violation`; the run fails rather than emitting an unsupported slot |
| **INV-08** | 4D.2 | Slots below `support_floor` (default 0.20 [A]) are flagged `low_support`, **excluded from the headline count**, and **reported separately with their count** | Silent exclusion is a defect; the separate count is asserted present |
| **INV-09** | 4D.3 | Every rollup response, UI view and export states `spacing_assumption_ft` | CI: response-schema assertion + export header assertion (§9) |
| **INV-10** | 4D.3 | Every rollup states the **support distribution** (min/p10/p50/p90/max + `low_support` share), not a mean | As INV-09 |
| **INV-11** | 4D.4 | `land_unit.system == 'plss'` **and** `land_unit.state == 'ND'` | `422 inventory_scope_unsupported` naming OQ-11 |
| **INV-12** | 4D.5 | `not_a_reserves_estimate: true` present on the run, on every slot collection, and in every export header. Response contains none of the strings `reserves`, `resource`, `booked location` outside this disclaimer | CI string check on the serialized response. `inventory_runs` has no such column in v0.6 §3.4.4 — errata **E-12** |
| **INV-13** | determinism | Two runs with identical params produce identical slot geometry hashes and an identical `run_content_id` | D1 (SB-07 §4.2) |
| **INV-14** | R5 | Every slot NPV carries `granularity: modelled`, `volume_granularity`, `model_id`, `deck_id`, `assumption_id` | SB-07 §10 Check 5 |
| **INV-15** | 6.2 | `surface_constraints_modelled: false` present on every run | Response-schema assertion |

**Rejection accounting is mandatory.** Every candidate that does not become a slot is
counted by reason in `rejected_by_reason`. A run that reports "18 slots" without reporting
"and 47 candidates rejected, of which 31 were too close to existing laterals" has hidden the
most informative half of the answer — and hiding it is precisely the confident-nonsense
failure 4D.5 names (v0.6 §4D.5).

### 6.4 Batch execution — and why it is not held to the 3 s budget

D-04 flagged the contradiction between "seconds at township scale" and a 3 s per-scenario
budget (ab:431). v0.6 §3.6.7 resolves it — S3 governs a single scenario; a township run is a
job returning `202 Accepted`. This section states the mechanism that makes the batch path
cheap, which the assessment noted was never stated.

**The batch path is a different path, and it is cheaper for four stated reasons:**

1. **One spatial pre-pass per unit**, not per slot. Step 3 of §4.1 — the 900 ms dominant
   term — runs once per `(spacing_unit, formation)` and is shared by every slot in it.
2. **Vectorized inference.** All slots in a run are one LightGBM batch predict, not N
   single-row predicts.
3. **No analog query per slot.** Analogs are a scenario-card affordance; the run reports
   support instead.
4. **Breakeven per slot is opt-in** (`include_breakeven`, default false), because it is
   ~6 extra DCF evaluations per slot and the rollup's set-level breakeven (§5.1) is the
   number that is actually wanted.

**Sizing.** An ND township is 36 sections ≈ 18 1,280-acre spacing units [A]. At 1,320 ft
spacing across a 5,280 ft unit width, ~4 candidate offsets per unit per bench; three benches
gives ~216 candidates, of which a developed township yields far fewer accepted slots. At
~250 ms of marginal cost per slot on the batch path plus a ~20 s spatial pre-pass, a
township run lands at **1–2 minutes** against the §3.7.8 budget of 10 minutes.

**Job contract** (v0.6 §3.6.7, C26): `POST /v1/inventory/runs` returns `202` with a
`job_id`; states, progress, cancellation and a failure representation come from the job
runner. `?dry_run=true` returns the plan — the unit list, candidate counts, and the inputs —
without executing (v0.6 §3.6.9). Rate limits apply (v0.6 §3.6.8: five concurrent write jobs;
unbounded inventory POSTs are a self-DoS).

**Equivalence is asserted, not assumed.** Test BATCH-EQUIV (§10.5) runs one slot through the
interactive scenario path and through the batch path and asserts an **identical
`valuation_id`**. Two code paths that produce different numbers for the same well is the
failure mode D-04 was actually pointing at, and content addressing turns it into a
one-line assertion.

### 6.5 Rollup statements

Every inventory rollup response and export carries, non-optionally:

```json
{"run_id": "inv_…", "area_ref": "plss:ND:150N-96W", "as_of": "2026-08-01",
 "spacing_assumption_ft": 1320, "spacing_assumption_source": "user_input",
 "target_formations": ["MIDDLE_BAKKEN", "THREE_FORKS_1"],
 "design_template": {"lateral_length_ft": 10000, "proppant_lb_per_ft": 1800, "stage_count": 55},
 "slots_admissible": 18, "slots_low_support": 5,
 "rejected_by_reason": {"too_close_existing": 31, "too_short": 9,
                        "setback_violation": 4, "azimuth_nonconforming": 2},
 "training_support": {"min": "0.11", "p10": "0.18", "p50": "0.41", "p90": "0.72",
                      "max": "0.83", "share_below_floor": "0.28", "floor": "0.20",
                      "k": 25, "metric": "euclidean_standardized"},
 "npv_expected": {"value": "…", "unit": "USD", "granularity": "modelled",
                  "volume_granularity": "modelled", "d": "drv_…"},
 "npv_band_comonotonic": {"p10": "…", "p50": "…", "p90": "…",
                          "assumption": "comonotonic_bound"},
 "npv_band_independent": null,
 "npv_band_independent_suppressed_reason": "small_n",
 "surface_constraints_modelled": false,
 "not_a_reserves_estimate": true,
 "quantile_convention": "statistical_ascending",
 "warnings": ["independence_band_suppressed_small_n"]}
```

The spacing assumption and the support distribution are present in the API, the UI, and
every export (4D.3), and the disclaimer field is present in all three (4D.5). §9 makes the
export half enforceable.

---

## 7. AOI alerts (C23, E8)

### 7.1 The AOI object

`aois` (v0.6 §3.4.4): `aoi_id` (ULID), `owner_principal`, `visibility`, `name`, `geom`,
`created_at`, `revision`. AOI geometry is **user-supplied and attacker-reachable**, so
validation is a security control, not a nicety:

| Guard | Limit | Failure |
|---|---|---|
| `ST_IsValid` | must pass | `422 invalid_geometry` with the reason from `ST_IsValidReason` |
| Vertex count | ≤ 2,000 [A] | `422 aoi_too_complex` |
| Area | ≤ 5,000 km² [A] | `422 aoi_too_large` — an AOI covering a whole state turns a weekly diff into a full table scan |
| Ring count | ≤ 20 | `422 aoi_too_complex` |
| SRID | 4326 on input, stored 4326, **evaluated in the basin's projected CRS** | `422 unsupported_srid` |
| Self-intersection | rejected, never auto-repaired | Silent `ST_MakeValid` changes the user's area without telling them |

CRUD is symmetric (`POST`/`GET`/`PATCH`/`DELETE`, v0.6 §3.6.12 #26, closing API-03); a
mutation bumps `revision` and writes an audit event (v0.6 §3.3 R2).

### 7.2 The containment rule — stated, because it is not obvious

"Wells inside the AOI" is ambiguous for horizontals: a well can have its surface location
inside and its lateral entirely outside, or vice versa. Pinned:

> **A well is in the AOI if its lateral geometry intersects the AOI polygon. Where no
> lateral geometry exists, the surface point is used and the well is flagged
> `containment_basis: surface_point`.** A permit with no geometry falls back to its
> `land_unit` centroid and is flagged `containment_basis: land_unit_centroid`.

The rule and the per-item basis are stated in the digest. A BD user chasing activity cares
about where the rock is being drained, which is the lateral; a user who assumed surface
points would get a different well list and never know why.

### 7.3 Knowledge-time diffs — the DIR-2 consequence

**The digest diffs on knowledge time, not valid time.** "What became known between vintage A
and vintage B", not "what happened between date A and date B".

This is forced by DIR-2 and it is the single most important correctness decision in the
alerting feature. Under valid-time diffing, a well whose first production month was March but
which was first reported in the June file would be missed entirely by every weekly digest
(March's window is long closed) or double-counted when the March data is restated. Under
knowledge-time diffing, it appears in the digest for the week glasswell learned about it,
with its production month stated — which is also what the user wants: an alert is about new
information.

| Event class | Detection |
|---|---|
| **New permit** | A `permits` row whose `manifest_id` belongs to a manifest first ingested inside the window, geometry intersecting the AOI |
| **Permit status change** | A permit whose canonical status differs from its value at the window's opening vintage |
| **New first production** | A well whose `first_production_month` is non-null at the closing vintage and was null (or absent) at the opening vintage |
| **Restated first production** | `first_production_month` present at both vintages but different — reported as its own class, never silently merged into "new" |

Each item carries `production_month` (valid time) **and** `report_vintage` (knowledge time),
so the digest can say "we learned this week about a well that started producing in March"
rather than implying it started this week.

### 7.4 Digest schema

```json
{"digest_id": "dig_<sha256[:12]>",
 "aoi_id": "aoi_01J…", "aoi_revision": 3,
 "period_start": "2026-08-13", "period_end": "2026-08-20",
 "vintage_open": {"nd_mpr_xlsx": "2026-07-14", "nd_gis_permits": "2026-08-12"},
 "vintage_close": {"nd_mpr_xlsx": "2026-08-11", "nd_gis_permits": "2026-08-19"},
 "freshness_window": {"nd_mpr_xlsx": {"latest_retrieval": "2026-08-11T04:02Z",
                                      "upstream_declared": "2026-06",
                                      "within_expected_interval": true},
                      "nd_gis_permits": {"latest_retrieval": "2026-08-19T04:01Z",
                                         "upstream_declared": null,
                                         "within_expected_interval": true}},
 "containment_rule": "lateral_intersects_aoi",
 "counts": {"new_permits": 3, "permit_status_changes": 1,
            "new_first_production": 2, "restated_first_production": 1},
 "items": [{"class": "new_first_production", "api10": "33053012340000",
            "operator": "…", "operator_rollup_mode": "as_reported",
            "production_month": "2026-05", "report_vintage": "2026-08-11",
            "containment_basis": "lateral_intersects_aoi",
            "d": "drv_…#api10=33053012340000"}],
 "empty_reason": null,
 "generated_at": "2026-08-20T06:00:11Z",
 "job_id": "job_…", "derivation_id": "drv_…"}
```

**`empty_reason` is the honesty field.** An empty digest has two entirely different causes
and a BD user must be able to tell them apart:

| `empty_reason` | Meaning |
|---|---|
| `null` with zero counts | We diffed fresh data and nothing happened |
| `"no_new_vintage"` | No source advanced its vintage in the window; we learned nothing because nothing arrived |
| `"source_stale"` | A source is beyond its expected pull interval (v0.6 §3.7.4); the digest is incomplete and `/v1/health` is `degraded` |

"Silence" is the failure mode an unattended weekly timer is prone to (v0.6 §3.7.7), and this
field is the specific defence against it.

**Idempotency.** `digest_id` is content-addressed over `(aoi_id, aoi_revision,
vintage_open, vintage_close, containment_rule, code_version)`. Re-running the timer for the
same window returns the same digest and writes no duplicate, so a retry after a failed job
is safe. The `alert_digests` table in v0.6 §3.4.4 has no digest id — errata **E-13**.

### 7.5 Timer, job, delivery

- **Weekly**, Monday 06:00 local, via a systemd timer (C23) that **invokes the job runner's
  entry point** rather than the digest code directly. C23's "one systemd timer plus two
  tables" (v0.6 §3.2 C22–C23) predates C26; running outside the job runner means a failed
  digest writes no `jobs` row, raises no audit event, and does not flip `/v1/health` to
  `degraded` — which is exactly the silence v0.6 §3.7.7 is designed to prevent. Errata
  **E-14**.
- **Delivery is pull-primary** (v0.6 §8.1 D-13, closing A-17): digests are materialized and
  fetched from `GET /v1/aois/{id}/digests`. An optional timer renders the current digest and
  mails it to the owner via the host MTA. No webhooks, no external notification service.
- **Correctness acceptance (E8).** One AOI digest generated and verified against a manual
  diff, with its freshness window stated (v0.6 §5 E8). The manual diff is a checked-in
  fixture: two ND permit/production vintages, a hand-listed expected item set, and the
  containment decisions hand-checked for three wells chosen because their surface and
  lateral fall on opposite sides of the AOI boundary (test ALERT-3, §10.5).

---

## 8. API surface owned by SB-03

Shapes are at the level SB-04 can freeze against; SB-04 owns transport, auth, envelope,
pagination and the job contract.

| Endpoint | Notes |
|---|---|
| `GET /v1/decks` · `GET /v1/decks/{deck_id}` | v0.6 §3.6.12 #16 |
| **`POST /v1/decks`** | **New.** Content-addressed and idempotent: posting an identical deck returns the existing `deck_id` and `200`, not a duplicate. v0.6 makes decks user-selectable inputs with no create path — errata **E-15** |
| `GET /v1/assumptions` · `GET /v1/assumptions/{id}` | v0.6 §3.6.12 #17 |
| **`POST /v1/assumptions`** | **New**, same idempotency rule. Required by the override resolution below |
| **`GET /v1/assumptions/taxes`** | **New.** Per-state tax rows with statute, evidence URL, effective dates and `confidence` (§1.8) |
| `POST /v1/valuations` · `GET /v1/valuations/{id}` | v0.6 §3.6.12 #18 |
| **`GET /v1/valuations/{id}/cashflows`** | **New.** The monthly ledger endpoint 18 promises but the schema does not store — errata **E-8** |
| `POST /v1/sensitivities` | v0.6 §3.6.12 #19; §3.3 schema |
| `GET/POST/PATCH/DELETE /v1/scenarios[/{id}]` | v0.6 §3.6.12 #11; S3 lives here |
| `POST /v1/inventory/runs` (+ `GET`, `/{id}`, `/{id}/slots`, `DELETE`, `?dry_run=`) | v0.6 §3.6.12 #20 |
| `POST/GET/PATCH/DELETE /v1/aois[/{id}]` · `GET /v1/aois/{id}/digests` · `GET /v1/aois/{id}/digest` | v0.6 §3.6.12 #26 |
| `POST/GET/PATCH/DELETE /v1/wellsets[/{id}]` · `GET /v1/wellsets/{id}/rollup` | v0.6 §3.6.12 #27 |
| `POST /v1/exports` for any of the above | v0.6 §3.6.12 #40; §9 |

**The `wi`/`nri` override ambiguity, resolved.** Endpoint 18 accepts `wi` and `nri` as
request parameters while the immutable assumption set also carries them (v0.6 §3.6.12 #18
vs §3.4.4) — two sources of truth for the same value, with no stated precedence
(errata **E-16**). Resolution: a request-level `wi`/`nri`/`interest_type` **constructs a new
content-addressed assumption set** derived from the base one, and the valuation cites that
single `assumption_id`. There is no precedence rule because there is never more than one
value in play, and the valuation stays replayable from exactly one immutable input (R7).
The response echoes both `assumption_id` and `derived_from_assumption_id`.

---

## 9. Exports and the provenance header (closes A-18)

Every SB-03 export carries a header block. An export that strips provenance is not an export
this system produces (v0.6 §3.6.7).

CSV form — comment-prefixed lines before the header row, so the file remains machine-readable:

```
# glasswell export
# artifact: inventory_run  run_id=inv_01J…  generated_at=2026-08-20T06:11:04Z
# api_version: v1   code_version: git:9f2c1ab   econ_engine_version: 1.0.0
# as_of_vintage: 2026-08-01
# not_a_reserves_estimate: true
# spacing_assumption_ft: 1320   spacing_assumption_source: user_input
# target_formations: MIDDLE_BAKKEN,THREE_FORKS_1
# training_support: min=0.11 p10=0.18 p50=0.41 p90=0.72 max=0.83 share_below_floor=0.28 floor=0.20
# surface_constraints_modelled: false
# quantile_convention: statistical_ascending
# aggregation: npv_expected=sum_of_three_point_means; bands=comonotonic_bound|independence_reference
# deck_id: dck_…   assumption_id: asm_…   model_id: mdl_…
# granularity: column npv_p50 = modelled (volume_granularity = modelled)
# derivations: npv_p50=drv_…  slot_geom=drv_…
# explain: https://glasswell.rpx.sh/v1/explain?h=drv_…
slot_id,land_unit_id,spacing_unit_id,usable_length_ft,training_support,npv_p50_usd,...
```

Rules:

1. **Every numeric column** names its derivation in the `# derivations:` line and its unit
   in the column header suffix (`_usd`, `_bbl`, `_ft`).
2. **4D statements are mandatory** on any inventory export (INV-09, INV-10, INV-12).
3. **Percentile columns carry their assumption in the name** — `npv_comonotonic_p10_usd`,
   never `npv_p10_usd`, at set or run scope (§5.2).
4. **Granularity per column**, per R5.
5. Large exports go through `POST /v1/exports` and the job runner (v0.6 §3.6.12 #40).
6. CI asserts the header block on a fixture export of each artifact type (test EXP-1).

---

## 10. Test strategy (DIR-10)

TDD as we go: tests written with or before implementation, never backfilled. Fixtures from
real data where the code touches real data; hand-checked golden cases where the code is
arithmetic.

### 10.1 Tiers

| Tier | Scope |
|---|---|
| **Golden** | Hand-checked numeric fixtures. GOLD-1 (§10.2) is printed in full in this document and is the primary DCF fixture |
| **Property** | Monotonicity, additivity, scaling, and equivariance invariants over generated inputs (Hypothesis) |
| **Purity** | Static (import/AST denylist) and dynamic (repeat-call, context-mutation) regression on R3 |
| **Invariant** | The INV-01..15 table (§6.3), each a named test |
| **Integration** | PostGIS slot geometry against a fixture township; digest against a two-vintage fixture |
| **Contract** | Schema assertions on every response shape here; SB-07's naked-number walker (SB-07 §10) |

### 10.2 GOLD-1 — the primary fixture, worked in full

**Deliberately synthetic and deliberately short.** A 12-month horizon so that every number
below is reproducible in a spreadsheet by hand; capex sized so payout and breakeven both
land inside the horizon. It tests mechanics, not realism. GOLD-3 (§10.3) is the realism
fixture.

**Inputs.** ND working interest; WI = 1.00, NRI = 0.80. Deck: flat WTI $70.00/bbl, HH
$3.00/mcf; differentials additive, oil −$5.00/bbl, gas −$0.75/mcf → realized $65.00/bbl and
$2.25/mcf. Capex $4,000,000 at t = 0 undiscounted. Abandonment $150,000 at month 12. Fixed
opex $8,000/month; oil $2.00/bbl; gas $0.30/mcf; water $1.50/bbl. ND tax: oil 10.0 % of oil
revenue (5 % GPT + 5 % extraction), gas $0.15/mcf volumetric, ad valorem 0.0 %. Discount rate
10 % effective annual, mid-month. GOR 1.5 mcf/bbl, WOR 1.2 bbl/bbl held constant.
Rounding `ROUND_HALF_UP` to the cent at each line; DF quantized to 12 dp.

| m | oil bbl | gas mcf | water bbl | rev 8/8 | tax 8/8 | opex | NR @ NRI | tax @ NRI | opex @ WI | net CF | DF | PV |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 18,000 | 27,000.0 | 21,600.0 | 1,230,750.00 | 121,050.00 | 84,500.00 | 984,600.00 | 96,840.00 | 84,500.00 | 803,260.00 | 0.996036617523 | 800,076.37 |
| 2 | 13,500 | 20,250.0 | 16,200.0 | 923,062.50 | 90,787.50 | 65,375.00 | 738,450.00 | 72,630.00 | 65,375.00 | 600,445.00 | 0.988156915513 | 593,333.88 |
| 3 | 10,800 | 16,200.0 | 12,960.0 | 738,450.00 | 72,630.00 | 53,900.00 | 590,760.00 | 58,104.00 | 53,900.00 | 478,756.00 | 0.980339550271 | 469,343.44 |
| 4 | 9,000 | 13,500.0 | 10,800.0 | 615,375.00 | 60,525.00 | 46,250.00 | 492,300.00 | 48,420.00 | 46,250.00 | 397,630.00 | 0.972584028648 | 386,728.59 |
| 5 | 7,800 | 11,700.0 | 9,360.0 | 533,325.00 | 52,455.00 | 41,150.00 | 426,660.00 | 41,964.00 | 41,150.00 | 343,546.00 | 0.964889861395 | 331,484.05 |
| 6 | 6,900 | 10,350.0 | 8,280.0 | 471,787.50 | 46,402.50 | 37,325.00 | 377,430.00 | 37,122.00 | 37,325.00 | 302,983.00 | 0.957256563134 | 290,032.47 |
| 7 | 6,200 | 9,300.0 | 7,440.0 | 423,925.00 | 41,695.00 | 34,350.00 | 339,140.00 | 33,356.00 | 34,350.00 | 271,434.00 | 0.949683652327 | 257,776.43 |
| 8 | 5,650 | 8,475.0 | 6,780.0 | 386,318.75 | 37,996.25 | 32,012.50 | 309,055.00 | 30,397.00 | 32,012.50 | 246,645.50 | 0.942170651246 | 232,382.15 |
| 9 | 5,200 | 7,800.0 | 6,240.0 | 355,550.00 | 34,970.00 | 30,100.00 | 284,440.00 | 27,976.00 | 30,100.00 | 226,364.00 | 0.934717085941 | 211,586.30 |
| 10 | 4,820 | 7,230.0 | 5,784.0 | 329,567.50 | 32,414.50 | 28,485.00 | 263,654.00 | 25,931.60 | 28,485.00 | 209,237.40 | 0.927322486213 | 194,030.55 |
| 11 | 4,500 | 6,750.0 | 5,400.0 | 307,687.50 | 30,262.50 | 27,125.00 | 246,150.00 | 24,210.00 | 27,125.00 | 194,815.00 | 0.919986385582 | 179,227.15 |
| 12 | 4,220 | 6,330.0 | 5,064.0 | 288,542.50 | 28,379.50 | 25,935.00 | 230,834.00 | 22,703.60 | 25,935.00 | 182,195.40 | 0.912708321258 | 166,291.26 |

Worked check on month 1, so the ordering in §1.2 is verifiable by hand:
oil revenue `18,000 × 65.00 = 1,170,000.00`; gas revenue `27,000 × 2.25 = 60,750.00`;
gross `1,230,750.00`. Severance `1,170,000.00 × 0.10 = 117,000.00` plus
`27,000 × 0.15 = 4,050.00` = `121,050.00`. Opex
`8,000 + 36,000 + 8,100 + 32,400 = 84,500.00`. Net revenue `1,230,750.00 × 0.80 =
984,600.00`; tax to interest `121,050.00 × 0.80 = 96,840.00`; opex at WI `84,500.00`.
Net CF `803,260.00`. `DF(1) = exp(−(1/24)·ln 1.10) = 0.996036617523`. PV `800,076.37`.

**Asserted outputs (the fixture's expected values):**

| Quantity | Value |
|---|---|
| PV of operating cashflow, months 1–12 | **4,112,292.64** |
| Abandonment PV (month 12, WI) | **−136,906.25** |
| Capex (t = 0, undiscounted) | **−4,000,000.00** |
| **NPV10, P50** | **−24,613.61** |
| Payout, undiscounted | month **11** |
| Payout, discounted | month **12** |
| **Breakeven WTI, P50** | **$70.37** (`dNPV/dWTI = 67,157.27`; residual NPV at the reported price = 234.59) |
| Total oil / gas / water | 96,590 bbl / 144,885 mcf / 115,908 bbl |

**Quantile bundle** (§2.2). The fixture's P10 and P90 oil paths are the P50 path scaled by
0.72 and 1.35; GOR and WOR are held at P50 per the coherent bundle. The scaling is a fixture
construction, chosen so the paths are non-crossing by inspection.

| Quantile | NPV10 | Payout (undisc.) | Breakeven WTI |
|---|---:|---:|---:|
| P10 | **−1,201,694.26** | not reached | **$94.85** |
| P50 | **−24,613.61** | month 11 | **$70.37** |
| P90 | **+1,446,737.20** | month 7 | **$54.04** |

Note the shape a reviewer should check: the band is **asymmetric** (−1.18 MM / +1.47 MM
around P50) because NPV is affine in volume while the volume quantiles are asymmetric, and
the P10 case never pays out, which is why `payout_months_undiscounted` must be nullable
(§1.11).

### 10.3 GOLD-2 — the royalty case, and the defect it detects

Same well, same deck, same taxes. Interest: **royalty**, NRI = 0.1875 (a 3/16 royalty), no
capex, no opex, no abandonment.

| Case | NPV10 |
|---|---:|
| **GOLD-2 royalty, correct arithmetic** | **+1,078,189.23** |
| GOLD-2 royalty with a 5 % post-production deduction | +1,018,399.09 |
| The **same inputs run through the working-interest path** (v0.6 as written, §1.4) | **−3,546,698.37** |
| **Delta** | **4,624,887.60**, with a sign flip |

GOLD-2 is a **regression test for errata E-1**: an engine that lacks `interest_type` cannot
produce the correct number, and the test fails loudly rather than producing a plausible-looking
negative valuation for a royalty that is plainly worth money.

**GOLD-3** (not printed): a real ND well at a 360-month horizon with its actual production
history, its forecast, and a checked-in expected artifact SHA-256. It tests the realism path,
the extrapolation share, and D1 determinism. It cannot be hand-checked, which is why GOLD-1
is the primary fixture and GOLD-3 is the secondary.

### 10.4 Purity regression tests (R3)

| ID | Test |
|---|---|
| **ECON-P1** | Static: `glasswell/econ/dcf.py` and siblings import nothing from a denylist (`datetime`, `time`, `random`, `os`, `logging`, `httpx`, `glasswell.api`, `glasswell.lineage.store`). AST-level, not grep |
| **ECON-P2** | Dynamic: mutate the global decimal context to `prec=6, ROUND_FLOOR`, call `value()`, assert byte-identical output to the pinned-context run |
| **ECON-P3** | Static: no float literals and no `float(` calls anywhere in the econ path |
| **ECON-P4** | 1,000 interleaved calls with three different input sets in a shuffled order; every result identical to its single-call baseline. Catches accidental module-level memoization keyed on the wrong thing |
| **ECON-P5** | Two processes, same inputs → identical `output_sha256`; plus a fresh-subprocess run (SB-07 §10 Check 8) |
| **ECON-P6** | Same inputs, two different wall-clock times and two different `TZ` values → identical output. Catches an accidental `date.today()` in a horizon calculation |

### 10.5 Property tests

| ID | Property | Why it matters |
|---|---|---|
| **ECON-B1** | NPV is non-decreasing in flat oil price over a $10–$200 grid, whenever every valued month's per-unit oil margin is positive | The precondition for the breakeven solve (§1.10) and for quantile equivariance (§2.3) |
| **ECON-B2** | NPV is affine in flat oil price within a fixed economic-limit truncation month: three collinear points to the cent | Validates the one-step linear solve; verified on GOLD-1 (470,100.99 twice) |
| **ECON-B3** | The analytic breakeven equals a 200-iteration bisection to the cent, across 200 generated wells | Bisection is the oracle; the fast path must not diverge from it |
| **ECON-B4** | NPV is non-increasing in capex, in each opex rate, and in each tax rate | Catches sign errors, which are the most common DCF bug and the least visible |
| **ECON-B5** | NPV is non-decreasing in NRI for a royalty interest; for a working interest, non-decreasing in NRI at fixed WI | The two interest paths have different monotonicity structure |
| **ECON-B6** | Scaling all volumes by k > 0 scales *revenue, taxes and variable opex* by k but leaves fixed opex and capex unscaled — so NPV is affine, not proportional, in k | The "double the well, double the value" fallacy, asserted false |
| **ECON-B7** | NPV at a zero discount rate equals the undiscounted cashflow sum | Discount-factor sanity |
| **ECON-B8** | Quantile ordering is preserved: `NPV(P10) ≤ NPV(P50) ≤ NPV(P90)` whenever the input paths are non-crossing and margins are positive | The observable form of quantile equivariance (§2.3) |
| **ECON-B9** | `value()` raises `quantile_crossing` on any crossed input; it never silently sorts | §2.5 |
| **AGG-1** | `Σ E[NPV_i]` is invariant to the order of the set | Linearity, and a guard against float drift (there is none — Decimal) |
| **AGG-2** | For n identical wells, `comonotonic band width / independent band width` scales as `√n`: the ratio at 4n is exactly twice the ratio at n, across n ∈ {10, 40, 160} | The §5.2 result; 3.18 at n = 10 and 6.36 at n = 40 (§10.6) |
| **AGG-3** | For a right-skewed per-well NPV distribution, `Σ E > Σ P50`; the rollup's headline and its comonotonic P50 differ and are separately labelled | The $3.53 MM trap in §5.2 |
| **INV-13** | Two identical inventory runs → identical slot geometry hashes | §6.2 |
| **BATCH-EQUIV** | One slot through the interactive path and the batch path → identical `valuation_id` | Closes D-04's real risk (§6.4) |
| **ALERT-1** | A digest re-run over the same vintage window returns the identical `digest_id` and writes no duplicate | §7.4 idempotency |
| **ALERT-2** | A well first reported in window W with a production month before W appears in W's digest, exactly once, with both times stated | Knowledge-time diffing (§7.3) |
| **ALERT-3** | Manual-diff fixture: two ND vintages, hand-listed expected items, three boundary wells whose surface and lateral straddle the AOI edge | E8 acceptance (v0.6 §5 E8) |
| **EXP-1** | Every export artifact type carries the full §9 header block | Closes A-18 |

### 10.6 Aggregation fixture

Derived from GOLD-1's three NPVs, so it is hand-checkable from numbers already printed.
Per-well three-point moments: `μ = 0.30(−1,201,694.26) + 0.40(−24,613.61) +
0.30(1,446,737.20) = 63,667.44`; `σ = 1,028,262.65`; `z = 1.2815515655`.

| n | `Σ P50` (comonotonic P50) | `Σ E` (headline) | comonotonic P10 / P90 | independent P10 / P90 | width ratio |
|---:|---:|---:|---:|---:|---:|
| 10 | −246,136.10 | 636,674.38 | −12,016,942.60 / 14,467,372.00 | −3,530,485.34 / 4,803,834.10 | 3.18 |
| 40 | −984,544.40 | 2,546,697.52 | −48,067,770.40 / 57,869,488.00 | −5,787,621.91 / 10,881,016.95 | 6.36 |

The two facts a reviewer should take from this table: the headline and the comonotonic P50
differ by **$3,531,241.92** at n = 40 and have opposite signs, and the width ratio doubles
from n = 10 to n = 40 — exactly `√4`. Both are consequences of arithmetic, not of modelling
choices, and both are invisible in any product that serves a single unlabelled
"portfolio P50".

The ratio is `((P90 − P10) / (2 z σ)) · √n`, not `√n` itself: the leading factor is 1.005
here because a three-point discrete distribution does not have the same spread-to-sigma
relationship as a normal. AGG-2 tests the `√n` *scaling*, not the absolute value, which is
the invariant that actually holds.

### 10.7 Fixtures from real data

Per DIR-10, fixtures are cut from real regulator downloads, sanitized only by truncation:
one ND township's PLSS sections and spacing units with real lateral geometry (INV
integration tests), two consecutive ND permit vintages (ALERT-3), and one real well's
production history at two report vintages (GOLD-3 and the as-of path). Synthetic data is
used only where the test is pure arithmetic (GOLD-1, GOLD-2, the property tests).

---

## 11. v0.6 errata

Defects found in `blueprint-v0.6-draft.md` while writing this document. Each is stated with
its location, its consequence, and the resolution this SB adopts. Items marked **§10
(change-controlled)** touch protocol or rule text and require a written rationale in the
commit (v0.6 §10).

| # | Severity | Location | Defect | Resolution adopted here |
|---|---|---|---|---|
| **E-1** | **HIGH** | §3.4.4 `econ_assumptions`; §4B.3; §6 U6; §3.6.12 #18 | No `interest_type`. A royalty valuation at a supplied NRI runs full working-interest capex and opex against a fractional revenue share. On GOLD-2 this is a **$4.62 MM error with a sign flip** on one well | §1.4: `interest_type` required, no default; royalty bears taxes only; economic limit inherited from the working-interest cashflow. **§10 (change-controlled — 4B.3)** |
| **E-2** | MED | §9 glossary "Payout" | Defines payout as *discounted*; industry default is undiscounted. GOLD-1 differs by one month | §1.11: serve both under unambiguous names; correct the glossary row |
| **E-3** | MED | §3.4.4 `decks`; §2.3; §3.4.3 stream vocabulary | Deck carries an NGL price that no stream can consume | §1.5.4: keep the field, consume only via `ngl_yield_bbl_per_mmcf` defaulting to 0.0, labelled `assumed` |
| **E-4** | MED | §3.4.4 `valuations.breakeven_price` | Scalar breakeven cannot represent three quantiles; 4B.7 requires all three NPVs | §1.10: breakeven per quantile |
| **E-5** | **HIGH** | §9 glossary "Quantile (P10/P50/P90)" | Defines P90 statistically (90th percentile = high production) then calls it "the conservative case for value" — the reserves convention leaking into a statistical definition. Internally contradictory and the most likely misread in the product | §2.1: adopt statistical-ascending everywhere; `quantile_convention` mandatory on every forecast-derived figure; correct the glossary row |
| **E-6** | MED | §3.4.4 `sensitivities` | No quantile column and no deck/assumption echo; a tornado cannot state its base case | §3.3: base block carries `valuation_id`, quantile, deck, assumptions, discount rate, horizon |
| **E-7** | MED | §3.4.4 `econ_assumptions.state` vs §3.6.12 #27 | A scalar state cannot serve a multi-state well set, which the rollup endpoint permits | §5.3: base assumptions plus per-state tax overlay resolved per well; every applied `tax_rule_id` listed |
| **E-8** | MED | §3.4.4 `valuations` vs §3.6.12 #18 | Endpoint promises "monthly cash flows"; schema stores only summaries | §1.2, §8: retain the cashflow ledger on the artifact; `GET /v1/valuations/{id}/cashflows` |
| **E-9** | LOW | §3.4.4 `decks` | No benchmark field, so 4B.5's "flat WTI" breakeven is uncheckable | §1.5.1: `benchmark_oil` / `benchmark_gas` / `benchmark_ngl` |
| **E-10** | MED | §3.4.4 `decks.basis_differentials` | No unit and no form; additive and percentage differentials move breakeven differently | §1.6: explicit `form` per entry, default `additive_usd`, echoed on every valuation |
| **E-11** | **HIGH** | §3.4.4 `inventory_runs` | No target formation and no design template. A slot count without a bench and a completion design is meaningless, and the Bakken has multiple benches on separate spacing | §6.1: `target_formations[]` and `design_template` required on every run |
| **E-12** | MED | §3.4.4 `inventory_runs` / `inventory_slots` vs §4D.5 | 4D.5 mandates a `not_a_reserves_estimate` field; the schema has no column for it, and §3.6.7 requires it in exports | §6.3 INV-12: field on run, slot collection, and export header; CI string check |
| **E-13** | LOW | §3.4.4 `alert_digests` | No digest id, so a digest cannot be cited, deduped, or made idempotent | §7.4: content-addressed `digest_id` |
| **E-14** | MED | §3.2 C23 vs §3.7.7 | C23 runs the digest from a systemd timer directly; a failure then writes no `jobs` row and does not flip `/v1/health` — the silence failure mode §3.7.7 exists to prevent | §7.5: the timer invokes the C26 job entry point |
| **E-15** | MED | §3.6.12 #16, #17 | Decks and assumption sets are user-selectable inputs with GET-only endpoints; no user can create one | §8: `POST /v1/decks`, `POST /v1/assumptions`, content-addressed and idempotent |
| **E-16** | MED | §3.6.12 #18 vs §3.4.4 | `wi`/`nri` accepted as request params *and* carried on the immutable assumption set, with no precedence rule | §8: an override constructs a derived content-addressed assumption set; the valuation cites exactly one |
| **E-17** | MED | §3.3 R5 vs SB-07 §9.1 | R5's granularity enum is `observed \| allocated \| modelled \| assumed`; SB-07's envelope uses `well_observed \| lease_allocated`. Two vocabularies for one mandatory field; the naked-number CI check (SB-07 §10 Check 5) asserts against one of them | Cross-document reconciliation is SB-00's. SB-03 emits R5's enum plus `volume_granularity` (§1.13) and flags the conflict |
| **E-18** | LOW | §3.7.8 | Non-functional budgets cover scenarios, type curves, explain, tiles and inventory runs, but not valuations or sensitivities — both of which are on the interactive path | §4.2: `POST /v1/valuations` p95 < 400 ms; `POST /v1/sensitivities` p95 < 1.5 s. Proposed additions to §3.7.8 |
| **E-19** | LOW | §4B.6 | Sensitivity parameter list omits differential, NRI and discount rate — for the A&D and minerals personas, three of the top levers | §3.2: extend to nine parameters. **§10 (change-controlled — 4B.6)** |
| **E-20** | LOW | project `CLAUDE.md` "Hard rules" | Still says "support score", which 4A.10 explicitly retires in favour of `training_support` | Use `training_support` throughout; `CLAUDE.md` needs the same edit |

---

## 12. Interfaces

| Counterparty | SB-03 consumes | SB-03 must emit |
|---|---|---|
| **SB-07 lineage** | `derive()`, `figure()`, `resolve_model()`, recipes, determinism classes, content-addressed ids, `lineage_unresolved` | `econ.value`, `econ.sensitivity`, `forecast.scenario`, `inventory.run` derivations with `deck_id` + `model_id` in params; DIR-3 granularity and `error_bounds` on every allocated input consumed and re-served; 4D's spacing assumption and support distribution as **recorded params, not prose** (SB-07 §12) |
| **SB-02 modeling** | Forecast paths (3 streams × 3 quantiles), `model_id`, `training_support`, calibration ref, Arps extension, analog index | Guard failures as typed errors (§2.5); **OQ-S1** (cross-well residual correlation), **OQ-S2** (isotonic rearrangement to guarantee non-crossing), **OQ-S3** (joint three-stream model) |
| **SB-01 data platform** | Canonical production at an `as_of` vintage; land units, spacing units, lateral geometry in the projected CRS; permits; `first_production_month`; bitemporal accessors | Nothing to canonical. Requires: a `(spacing_unit, formation)` lateral-geometry index for §6.2 and a permits-by-vintage index for §7.3 |
| **SB-04 API & agent** | Envelope, auth, pagination, job contract, `202` async, idempotency keys, rate limits | Response schemas in §3.3, §6.5, §7.4; OpenAPI examples for every operation (SB-07 §10 Check 1); MCP tools covering scenario → NPV → tornado → inventory, since questions 4 and 6 of the 10-question suite terminate here (v0.6 §3.6.10) |
| **SB-05 map & UI** | Handles, chain JSON for the drawer | Must render: `analog_divergence` whenever it renders the NPV; the spacing assumption and support distribution wherever a slot count appears (4D.3); `not_a_reserves_estimate` on the inventory layer; the band's `band_semantics` on every NPV chart; **never** plot `npv_realized_to_date` on the same axis as a full-life scenario NPV without a visual break (§4.4) |
| **SB-06 infrastructure** | systemd timer for the weekly digest; CPU-weight isolation so a batch inventory run never preempts interactive serving (v0.6 §3.7.3); the host MTA for optional digest mail | Batch jobs declare their slice; the digest job declares its schedule |
| **SB-00 consolidation** | — | Ratify or reject the twenty errata in §11; apply the change-controlled ones (E-1 → 4B.3, E-19 → 4B.6, and the OQ-6 deck proposal in §1.5.3); add glossary rows for *interest type, working interest, royalty interest, post-production deduction, economic limit, mid-period discounting, comonotonic, quantile convention, coherent stream bundle, breakeven benchmark, extrapolation share, slot admissibility, knowledge-time diff* |

---

## 13. Rejected alternatives

- **Annual cashflows.** Monthly is required by 4B.1 and by the shape of shale decline — an
  annual model misses 60 % of first-year production timing.
- **End-of-period or beginning-of-period discounting.** Mid-period is 4B.1's pin and is the
  category norm; the others are offered as neither default nor option, to keep one
  convention.
- **Float arithmetic with a rounding pass at the end.** Cheaper and untestable across thread
  counts (SB-07 §4.4); the DCF is not the latency bottleneck (§4.2), so there is nothing to
  buy.
- **Bisection as the production breakeven solver.** Correct but ~20× the work of the linear
  solve; retained as the test oracle instead (ECON-B3).
- **A "temporary" assumption object for sensitivity perturbations.** Would make a
  sensitivity row cite an object that no longer exists, breaking R7 replay.
- **Monte Carlo portfolio aggregation.** §5.2 — a seed inside a D1 artifact, a
  distributional assumption less inspectable than the moment method, and precision spent on
  an unmeasured correlation.
- **Serving a single portfolio "P10/P50/P90".** The whole point of §5.2 is that this number
  does not exist without a dependence assumption; naming the assumption in the field name is
  the deliverable.
- **Same-quantile stacking across oil, gas and water.** §2.2 — incoherent, and it prices the
  upside case with the downside water bill.
- **Deriving NRI from ownership data.** Explicitly out of scope (v0.6 §2.3); the honest
  boundary is a supplied scalar (v0.6 §2.2).
- **Auto-repairing invalid AOI polygons with `ST_MakeValid`.** Changes the user's area
  without telling them; rejection with a reason is the correct behaviour.
- **Valid-time (production-month) alert diffs.** §7.3 — silently misses late-reported wells
  and double-counts restatements.
- **A TTL cache in front of the scenario path.** Content addressing gives correctness under
  restatement that a TTL cache cannot (§4.3).
- **Type-curve-based economics as an alternative to model forecasts.** The type curve is the
  benchmark *control* (v0.6 §4A.5), and valuing it is available through the same `value()`
  — but it is not a separate econ path.
- **IRR as a headline metric.** Multiple roots on non-conventional cashflow sign patterns
  and no meaning for a royalty interest with no investment. Available as a derived field
  with an explicit `irr_multiple_roots` warning; never the headline.

## 14. Cut as gold-plating

Designed, then dropped. Listed so the cut is a decision, not an omission.

1. **Monte Carlo economics** (§5.2, §13).
2. **Probabilistic price decks / stochastic price paths.** The tornado is the price-uncertainty
   instrument (§2.4); a price distribution glasswell cannot evidence would be theatre.
3. **Multi-well development scheduling** (rig cadence, capital timing across a pad). Real work
   with real value; a different product. Inventory v0 values slots independently and says so.
4. **Parent-child interference *economics*** — degrading a child slot's forecast for
   proximity to a parent is SB-02's feature-engineering problem (OQ-4), not an econ
   adjustment factor bolted on after the fact.
5. **Tax exemptions, incentives, and trigger rates** (ND stripper and reduced rates, TX
   high-cost gas). Recorded in `tax_regimes.notes`, not implemented; a wrong incentive is
   worse than a stated omission.
6. **Hedging, NGL fractionation economics, and take-or-pay.** Out per v0.6 §2.3.
7. **Automatic spacing inference from recent development.** OQ-9 keeps spacing a user input
   in v0; inferred spacing is a P8 experiment.
8. **Surface-constraint modelling for slots** (§6.2) — no free source; recorded as an honest
   gap with a notebook memo.
9. **Webhook / external alert delivery.** Pull-primary per D-13.
10. **Per-slot breakeven by default** (§6.4) — opt-in, because the set-level breakeven is the
    number that gets used.
11. **Scenario versioning as a first-class diff UI.** Scenarios carry a `revision` counter;
    a comparison UI is SB-05's call, later, if ever.

## 15. Open items handed back, and VERIFY gates

| Item | Owner | Why not decided here |
|---|---|---|
| Ratify the twenty errata (§11); apply the change-controlled ones | SB-00 | v0.6 §10 change control |
| The EIA STEO default-deck proposal (§1.5.3), amending 4B.2 and OQ-6 | SB-00 + owner | Changes a protocol clause and an open question |
| **OQ-S1** Cross-well forecast-residual correlation by basin, vintage and distance | SB-02 | Collapses §5.2's bracket to a measured band; estimable from the temporal holdout |
| **OQ-S2** Isotonic rearrangement to guarantee non-crossing quantiles | SB-02 | SB-03 rejects crossed input rather than repairing it (§2.5) |
| **OQ-S3** Joint three-stream forecast model | SB-02 | Would replace the P50-ratio coupling in §2.2 with a real joint distribution |
| Whether the restatement-drift decomposition becomes a scorecard row | SB-02 / E11 | Recommended in SB-07 §3.5; affects the ledger, not econ |
| Support floor value for INV-08 and the low-support policy | Owner + SB-02 | Needs the measured support distribution from P3 |
| TX inventory geometry (OQ-11) | Deferred design task | v0.6 §8.1 D-11 |

**VERIFY gates.** No `[A]` value below may be served until its gate is closed with a fetched
primary source, a checksum, and an `evidence_url`.

| ID | Gate |
|---|---|
| **V-1** | EIA STEO: machine-readable endpoint, licence/public-domain status, horizon, update cadence (§1.5.3) |
| **V-2** | Fixed opex defaults for ND and Permian |
| **V-3** | Water handling cost per bbl, ND and Permian, including SWD versus recycle |
| **V-4** | ND: gross production tax rate, oil extraction tax rate, current gas volumetric rate and its annual reset mechanism; statute citations |
| **V-5** | TX: crude oil and natural gas production tax rates; oil-field cleanup regulatory fees; statute citations |
| **V-6** | Ad valorem treatment in ND (in-lieu-of confirmation), TX (county range) and NM (district range), **and whether it burdens royalty interests** in each state |
| **V-7** | NM: severance, emergency school, conservation and ad valorem production tax rates; statute citations |
| **V-8** | Indicative D&C capex ranges (used for documentation and fixtures only — no default ships) |
| **V-9** | Abandonment cost defaults, ND |
| **V-10** | The §4.2 latency budget, measured at P4 exit; replaces every `[A]` in that table |
| **V-11** | ND setback and spacing rules: statutory setback from spacing-unit boundary, standard unit sizes, and whether the setback varies by formation (INV-04) |
| **V-12** | ND spacing-unit sizes and typical bench separation for the INV-06 azimuth tolerance |
