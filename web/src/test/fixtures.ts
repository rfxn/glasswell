// Shapes are taken from the P4 routers (wells.py, production.py, lineage.py, glossary.py)
// rather than recorded from a seeded instance; P8's smoke is what exercises the live shapes.
import type { Envelope } from "../api/envelope.ts";

export const API10 = "3305301234";
export const OIL_HANDLE = `drv_oil1#api10=${API10}&col=oil_bbl`;
export const LENGTH_HANDLE = `drv_len1#api10=${API10}&col=lateral_length_ft`;
export const SHA256 = "3f9a1c0d2e4b6a8c0e2f4a6b8c0d2e4f60718293a4b5c6d7e8f90a1b2c3d4e5f";

function meta(labels: Record<string, string> = {}): Envelope<unknown>["meta"] {
  return {
    request_id: "01JBQ7M0Z8K2V4N6X8R0T2Y4W6",
    as_of: { requested: "latest", resolved: "2026-08-01" },
    source_freshness: { nd_dmr_mpr: { retrieval_vintage: "2026-08-01", state: "current" } },
    labels,
    next_cursor: null,
    warnings: [],
    deprecations: [],
  };
}

export const wellEnvelope = {
  data: {
    api10: API10,
    well_name: "SPOTTED HORSE 14-23H",
    operator_name_reported: "CONTINENTAL RESOURCES",
    status_canonical: "active",
    status_reported: "A",
    county_code_at_permit: "053",
    land_unit_label: "150N-96W-14",
    spud_date: "2019-04-02",
    confidential_flag: false,
    basin: "williston",
    lateral_count: 1,
    lateral_length_ft: { value: "9853.24", unit: "ft", d: LENGTH_HANDLE },
    compute_crs: "EPSG:32614",
    storage_crs: "EPSG:4326",
    effective_from: "2026-08-01",
    surface_point: { lon: -102.84, lat: 47.81 },
  },
  meta: meta({ "/api10": "gt_api_10_api_12_api_14", "/lateral_length_ft": "gt_wellbore" }),
  links: { self: `/v1/wells/${API10}`, next: null, explain: null },
};

export const productionEnvelope = {
  data: {
    api10: API10,
    source_id: "nd_dmr_mpr",
    granularity: "well_observed",
    streams: ["oil", "gas", "water"],
    series: {
      pm: ["2026-01", "2026-02"],
      oil_bbl: ["1000.000", null],
      oil_bbl_report_vintage: ["2026-08-01", null],
      oil_bbl_null_semantics: ["reported", "withheld"],
      gas_mcf: ["2500.000", "2400.000"],
      gas_mcf_report_vintage: ["2026-08-01", "2026-08-01"],
      gas_mcf_null_semantics: ["reported", "reported"],
      water_bbl: ["800.000", "0.000"],
      water_bbl_report_vintage: ["2026-08-01", "2026-08-01"],
      water_bbl_null_semantics: ["reported", "reported_zero"],
    },
    _lineage: {
      "series.oil_bbl": OIL_HANDLE,
      "series.gas_mcf": `drv_gas1#api10=${API10}&col=gas_mcf`,
      "series.water_bbl": `drv_wat1#api10=${API10}&col=water_bbl`,
    },
    _units: { "series.oil_bbl": "bbl", "series.gas_mcf": "mcf", "series.water_bbl": "bbl" },
    _basis: { "series.oil_bbl": "oil+condensate", "series.water_bbl": "water" },
  },
  meta: meta({
    "/series/oil_bbl": "gt_liquids_policy",
    "/series/gas_mcf": "gt_stream",
    "/granularity": "gt_granularity",
  }),
  links: { self: `/v1/wells/${API10}/production`, next: null, explain: null },
};

export const explainEnvelope = {
  data: {
    chains: [
      {
        handle: OIL_HANDLE,
        root: "drv_oil1",
        depth: 2,
        truncated: false,
        as_of_vintage: "2026-08-01",
        nodes: [
          {
            id: "drv_oil1",
            type: "derivation",
            operation: "canonical.promote",
            output: { store: "postgres", dataset: "canonical.production_monthly" },
            code_version: "git:9f2c1ab",
            determinism_class: "D1",
            conformance_rules: [{ rule_id: "cr_nd_liquids_policy_1" }],
            explanation:
              "canonical.promote produced canonical.production_monthly, 22014 rows, at code git:9f2c1ab.",
          },
          {
            id: "man_9c3f",
            type: "manifest",
            source_id: "nd_dmr_mpr",
            source_key: "2026_01.xlsx",
            sha256: SHA256,
            bytes: 4182331,
            fetched_at: "2026-08-01T05:02:11+00:00",
            fetch_vintage: "2026-08-01",
            acquisition_method: "https_get",
            acquisition_url: "https://www.dmr.nd.gov/oilgas/mpr/2026_01.xlsx",
            explanation:
              "nd_dmr_mpr 2026_01.xlsx, fetched 2026-08-01T05:02:11+00:00 via https_get; sha256 3f9a1c0d2e4b.",
          },
        ],
        edges: [{ from: "drv_oil1", to: "man_9c3f", role: "primary", as_of_vintage: "2026-08-01" }],
        terminals: ["man_9c3f"],
        recipe: null,
        warnings: [],
      },
    ],
  },
  meta: meta(),
  links: { self: "/v1/explain", next: null, explain: null },
};

export const glossaryIndexEnvelope = {
  data: {
    index_version: "gix_abc123def456",
    entries: [
      { surface: "water cut", term_id: "gt_water_cut", n_words: 2 },
      { surface: "lateral length", term_id: "gt_wellbore", n_words: 2 },
      { surface: "operator", term_id: "gt_operator", n_words: 1 },
    ],
    stopwords: ["band", "stream", "vintage"],
  },
  meta: meta(),
  links: { self: "/v1/glossary/index", next: null, explain: null },
};

export const glossaryTermsEnvelope = {
  data: [
    {
      term_id: "gt_wellbore",
      term: "lateral length",
      aliases: ["lateral"],
      short_definition: "The producing horizontal section of the wellbore, in feet.",
      domain_tags: ["drilling"],
      highlightable: true,
    },
    {
      term_id: "gt_operator",
      term: "operator",
      aliases: [],
      short_definition: "The company responsible for the well as reported to the regulator.",
      domain_tags: ["regulatory"],
      highlightable: true,
    },
  ],
  meta: meta(),
  links: { self: "/v1/glossary", next: null, explain: null },
};

export const problemBody = {
  type: "https://glasswell.rpx.sh/v1/errors/lineage_unresolved",
  title: "The lineage chain could not be resolved",
  status: 404,
  instance: "/v1/explain",
  request_id: "01JBQ7M0Z8K2V4N6X8R0T2Y4W6",
  detail: "handle drv_missing did not resolve",
  handle: "drv_missing",
  last_resolved: null,
  stop_reason: "unknown_id",
};

export function stubFetch(routes: Record<string, unknown>): (input: RequestInfo | URL) => Promise<Response> {
  return (input: RequestInfo | URL) => {
    const url = String(input);
    for (const [path, body] of Object.entries(routes)) {
      if (url.startsWith(path)) {
        if (body === problemBody) {
          return Promise.resolve(
            new Response(JSON.stringify(body), {
              status: 404,
              headers: { "content-type": "application/problem+json" },
            }),
          );
        }
        return Promise.resolve(
          new Response(JSON.stringify(body), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        );
      }
    }
    return Promise.resolve(new Response("{}", { status: 404 }));
  };
}
