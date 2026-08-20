import { describe, expect, it } from "vitest";

import { asOf, derivationFor, figureAt, labelFor, unwrap } from "./envelope.ts";
import type { Envelope } from "./envelope.ts";

const wellEnvelope: Envelope<Record<string, unknown>> = {
  data: {
    api10: "3305301234",
    lateral_length_ft: {
      value: "9853.24",
      unit: "ft",
      d: "drv_7QK3M2XR4V9B#api10=3305301234&col=lateral_length_ft",
    },
    surface_point: { lon: -102.8, lat: 47.8 },
  },
  meta: {
    request_id: "01J0",
    as_of: { requested: "latest", resolved: "2026-08-01" },
    source_freshness: {},
    labels: { "/lateral_length_ft": "gt_wellbore" },
    next_cursor: null,
    warnings: [],
    deprecations: [],
  },
  links: { self: "/v1/wells/3305301234", next: null, explain: null },
};

const seriesEnvelope: Envelope<Record<string, unknown>> = {
  data: {
    api10: "3305301234",
    granularity: "well_observed",
    series: {
      pm: ["2026-01", "2026-02"],
      oil_bbl: ["1000.000", null],
      oil_bbl_report_vintage: ["2026-08-01", null],
      oil_bbl_null_semantics: ["reported", "no_report"],
    },
    _lineage: {
      "series.oil_bbl": "drv_OIL#api10=3305301234&col=oil_bbl",
      "series.gas_mcf": "drv_GAS#api10=3305301234&col=gas_mcf",
    },
    _units: { "series.oil_bbl": "bbl", "series.gas_mcf": "mcf" },
    _basis: { "series.oil_bbl": "oil+condensate" },
  },
  meta: {
    request_id: "01J1",
    as_of: { requested: "latest", resolved: "2026-08-01" },
    source_freshness: {},
    labels: { "/series/oil_bbl": "gt_liquids_policy" },
    next_cursor: null,
    warnings: [],
    deprecations: [],
  },
  links: { self: "/v1/wells/3305301234/production", next: null, explain: null },
};

describe("unwrap", () => {
  it("returns data", () => {
    expect(unwrap(wellEnvelope)).toBe(wellEnvelope.data);
  });

  it("reads meta.as_of as an object of requested and resolved", () => {
    expect(asOf(wellEnvelope)).toEqual({ requested: "latest", resolved: "2026-08-01" });
  });

  it("reads meta.labels for the glossary binding", () => {
    expect(labelFor(wellEnvelope, "/lateral_length_ft")).toBe("gt_wellbore");
    expect(labelFor(wellEnvelope, "/api10")).toBeNull();
  });
});

describe("derivationFor", () => {
  it("takes a figure's own d in band", () => {
    expect(derivationFor(wellEnvelope.data, "/lateral_length_ft")).toBe(
      "drv_7QK3M2XR4V9B#api10=3305301234&col=lateral_length_ft",
    );
  });

  it("falls back to the nearest ancestor _lineage sidecar entry", () => {
    expect(derivationFor(seriesEnvelope.data, "/series/oil_bbl")).toBe(
      "drv_OIL#api10=3305301234&col=oil_bbl",
    );
  });

  it("covers descendants of a sidecar entry, per point", () => {
    expect(derivationFor(seriesEnvelope.data, "/series/oil_bbl/1")).toBe(
      "drv_OIL#api10=3305301234&col=oil_bbl",
    );
  });

  it("prefers the longest matching sidecar prefix", () => {
    const data = {
      a: { b: { c: 1 } },
      _lineage: { a: "drv_SHORT", "a.b": "drv_LONG" },
    };
    expect(derivationFor(data, "/a/b/c")).toBe("drv_LONG");
  });

  it("does not treat a partial key as a prefix", () => {
    const data = { series: { oil_bbl_extra: ["1"] }, _lineage: { "series.oil_bbl": "drv_OIL" } };
    expect(derivationFor(data, "/series/oil_bbl_extra")).toBeNull();
  });

  it("returns null for an uncovered number rather than inventing a handle", () => {
    expect(derivationFor(wellEnvelope.data, "/surface_point/lon")).toBeNull();
  });

  it("never consults meta.derivations, which the API does not send (B11)", () => {
    const stale = {
      data: { cum: 12 },
      meta: { ...wellEnvelope.meta, derivations: { "/cum": "drv_GHOST" } },
      links: wellEnvelope.links,
    } as unknown as Envelope<Record<string, unknown>>;
    expect(derivationFor(unwrap(stale), "/cum")).toBeNull();
  });
});

describe("figureAt", () => {
  it("parses the figure-object form", () => {
    const found = figureAt(wellEnvelope.data, "/lateral_length_ft");
    expect(found).toMatchObject({ value: "9853.24", unit: "ft" });
  });

  it("returns null where the pointer is not a figure", () => {
    expect(figureAt(wellEnvelope.data, "/api10")).toBeNull();
  });

  it("keeps the value a string so a decimal is never round-tripped through a float", () => {
    expect(typeof figureAt(wellEnvelope.data, "/lateral_length_ft")?.value).toBe("string");
  });
});
