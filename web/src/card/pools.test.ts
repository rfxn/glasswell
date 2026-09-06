// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderPools } from "./pools.ts";

const payload = {
  api10: "3002599001",
  granularity: "well_completion_pool",
  reporting_level: "well_completion_pool",
  pools: [
    {
      well_completion_pool: "BONE SPRING",
      entity_key: "3002599001:BONE SPRING",
      streams: ["oil"],
      series: {
        pm: ["2026-01", "2026-02"],
        oil_bbl: ["1200.000", null],
        oil_bbl_report_vintage: ["2026-08-01", "2026-08-01"],
        oil_bbl_null_semantics: ["reported", "no_report"],
      },
    },
  ],
  _lineage: { "pools.0.series.oil_bbl.0": "drv_p#entity_key=3002599001:BONE SPRING&col=oil_bbl" },
  _units: { "pools.0.series.oil_bbl": "bbl" },
  _basis: { "pools.0.series.oil_bbl": "oil+condensate" },
};

const callbacks = { onExplain: vi.fn(), labelTermFor: () => null };
let host: HTMLElement;

const serve = (body: unknown): void => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({ data: body, meta: { as_of: {}, warnings: [], labels: {} }, links: {} }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      ),
    ),
  );
};

beforeEach(() => {
  callbacks.onExplain.mockClear();
  host = document.createElement("div");
  document.body.replaceChildren(host);
});

const render = (links: Record<string, string> = {}) =>
  renderPools(host, "/v1/wells/3002599001/production/pools", {}, links, callbacks);

describe("the pool filings, where the regulator files below the well", () => {
  it("names the rule that decided nothing rolls up, and says these are the filings", async () => {
    serve(payload);
    await render({ reporting_rule: "/v1/conformance/cr_nm_wcproduction_pool_rollup_1" });

    expect(host.textContent).toContain("rolls nothing up to the well");
    expect(host.querySelector(".gw-identity-rule")?.textContent).toBe(
      "cr_nm_wcproduction_pool_rollup_1",
    );
    expect(host.textContent).toContain("no sum of them is served");
  });

  it("says the series above it is a sum of these filings, where a sum is served", async () => {
    // MAJOR-5. The rule id is the same in both states, so a sentence chosen by the presence of
    // a rule link says "no sum of them is served" on the card that draws the sum, under the
    // rule that authorises it. The key the caller passes is which state the well is in.
    serve(payload);
    await render({ aggregation_rule: "/v1/conformance/cr_nm_wcproduction_pool_rollup_2" });

    expect(host.textContent).toContain("the series above is glasswell's sum of them");
    expect(host.textContent).not.toContain("no sum of them is served");
    expect(host.textContent).not.toContain("rolls nothing up to the well");
    expect(host.querySelector(".gw-identity-rule")?.textContent).toBe(
      "cr_nm_wcproduction_pool_rollup_2",
    );
  });

  it("draws one table per pool, in the monthly table's own shape", async () => {
    serve(payload);
    await render();

    expect(host.querySelectorAll(".gw-pool").length).toBe(1);
    expect(host.querySelector(".gw-pool-title")?.textContent).toBe("BONE SPRING");
    expect(host.querySelectorAll(".gw-series-table tbody tr").length).toBe(2);
  });

  it("carries the unit and the class per cell, and the handle per point", async () => {
    serve(payload);
    await render();

    const first = host.querySelector(".gw-series-table tbody tr");
    expect(first?.querySelector(".gw-table-value")?.textContent).toBe("1200.000 bbl");
    expect(first?.querySelector(".gw-table-state")?.textContent).toBe("reported");
    first?.querySelector<HTMLButtonElement>(".gw-handle")?.click();
    // The month, because the cell is a point: the column handle resolves to every month the
    // pool filed, which is the wrong subject for one row of it.
    expect(callbacks.onExplain).toHaveBeenCalledWith(
      "drv_p#entity_key=3002599001:BONE SPRING&col=oil_bbl&pm=2026-01",
    );
  });

  it("says an absent month is absent rather than zero", async () => {
    serve(payload);
    await render();

    const second = [...host.querySelectorAll(".gw-series-table tbody tr")][1];
    expect(second?.querySelector(".gw-table-value")?.textContent).toBe("");
    expect(second?.querySelector(".gw-table-state")?.textContent).toBe("no report");
  });

  it("says so when no pool filing is served, rather than drawing an empty table", async () => {
    serve({ ...payload, pools: [] });
    await render();

    expect(host.textContent).toContain("No pool filings are served");
    expect(host.querySelector("table")).toBeNull();
  });
});
