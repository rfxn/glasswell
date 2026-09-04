// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderPeerControl } from "./peer.ts";

const control = {
  api10: "3305310451",
  outcome: "available",
  relation: "control_type_curve_not_a_forecast",
  publication_id: "p3pub_6f9f8124ba4335179693040393527a6e",
  split_set_id: "sset_c7bbb9a6932db76b",
  split_id: "spl_20210101_24",
  split_sha256: "a".repeat(64),
  origin: "2021-01-01",
  knowledge_cutoff: "2021-01-01",
  eval_vintage: "2026-08-28",
  horizon_months: 24,
  stream: "oil",
  normalization: "typecurve_absolute",
  quantile_convention: "p10_is_the_low_case",
  fallback_level: "formation_area_length",
  control_unavailable_reasons: [],
  peer_set_id: "peers_9f",
  formation_group: "BAKKEN",
  area: "NESSON",
  lateral_length_bucket: "gte_8000",
  series: {
    month_index: [1, 2, 3],
    monthly_p10: ["100.000", "90.000", "80.000"],
    monthly_p50: ["200.000", "180.000", "160.000"],
    monthly_p90: ["300.000", "270.000", "240.000"],
    peer_count: [42, 41, 40],
  },
  _lineage: { "series.monthly_p50": "drv_tc#api10=3305310451&col=monthly_p50" },
  _units: {
    "series.monthly_p10": "bbl",
    "series.monthly_p50": "bbl",
    "series.monthly_p90": "bbl",
    "series.peer_count": "count",
  },
};

const envelope = (over: Record<string, unknown> = {}) => ({
  data: { ...control, ...over },
  meta: { as_of: { requested: "latest", resolved: "2026-08-28" }, warnings: [], labels: {} },
  links: { self: "/v1/wells/3305310451/type-curve" },
});

const callbacks = { onExplain: vi.fn() };
let host: HTMLElement;

const serve = (body: unknown): void => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    ),
  );
};

beforeEach(() => {
  callbacks.onExplain.mockClear();
  host = document.createElement("div");
  document.body.replaceChildren(host);
});

describe("the peer control, which is not a forecast", () => {
  it("renders the relation verbatim and never the word forecast", async () => {
    serve(envelope());
    await renderPeerControl(host, "/v1/wells/3305310451/type-curve", {}, callbacks);

    expect(host.querySelector(".gw-peer-relation")?.textContent).toBe(
      "control_type_curve_not_a_forecast",
    );
    expect(host.textContent?.toLowerCase()).not.toContain("forecast this");
  });

  it("carries no heading of its own, because the section already has one", async () => {
    serve(envelope());
    await renderPeerControl(host, "/v1/wells/3305310451/type-curve", {}, callbacks);

    expect(host.querySelector("h4")).toBeNull();
  });

  it("states the quantile convention, the ladder rung and the peer set", async () => {
    serve(envelope());
    await renderPeerControl(host, "/v1/wells/3305310451/type-curve", {}, callbacks);
    const facts = host.querySelector(".gw-peer-facts")?.textContent ?? "";

    expect(facts).toContain("p10_is_the_low_case");
    expect(facts).toContain("BAKKEN · NESSON · gte_8000");
    expect(facts).toContain("peers_9f");
    expect(facts).toContain("2021-01-01");
  });

  it("says the pad group was held out with the subject", async () => {
    serve(envelope());
    await renderPeerControl(host, "/v1/wells/3305310451/type-curve", {}, callbacks);

    expect(host.textContent).toContain("every well on its pad with it");
    expect(host.textContent).toContain("its own training data");
  });

  it("draws the three quantiles and the peers behind each month", async () => {
    serve(envelope());
    await renderPeerControl(host, "/v1/wells/3305310451/type-curve", {}, callbacks);

    const rows = [...host.querySelectorAll(".gw-peer-table tbody tr")];
    expect(rows.length).toBe(3);
    expect([...rows[0]!.querySelectorAll("td")].map((cell) => cell.textContent)).toEqual([
      "100.000",
      "200.000",
      "300.000",
      "42",
    ]);
    expect(host.querySelector(".gw-peer-table caption")?.textContent).toContain(
      "producing-month axis",
    );
  });

  it("keeps the split identity reachable and closed", async () => {
    serve(envelope());
    await renderPeerControl(host, "/v1/wells/3305310451/type-curve", {}, callbacks);
    const details = host.querySelector<HTMLDetailsElement>(".gw-peer-split");

    expect(details?.open).toBe(false);
    expect(details?.textContent).toContain("spl_20210101_24");
    expect(details?.textContent).toContain("a".repeat(64));
  });

  it("renders the reasons and keeps the slots where no control was produced", async () => {
    serve(
      envelope({
        outcome: "control_unavailable",
        control_unavailable_reasons: ["too_few_peers", "no_formation_group"],
      }),
    );
    await renderPeerControl(host, "/v1/wells/3305310451/type-curve", {}, callbacks);

    expect(host.querySelector(".gw-peer-table")).toBeNull();
    const reasons = [...host.querySelectorAll(".gw-peer-reasons li")].map((li) => li.textContent);
    expect(reasons).toEqual(["too_few_peers", "no_formation_group"]);
    expect(host.textContent).toContain("slots below stay in place");
  });

  it("opens the chain from the section's own handle", async () => {
    serve(envelope());
    await renderPeerControl(host, "/v1/wells/3305310451/type-curve", {}, callbacks);

    host.querySelector<HTMLButtonElement>(".gw-handle")?.click();
    expect(callbacks.onExplain).toHaveBeenCalledWith("drv_tc#api10=3305310451&col=monthly_p50");
  });
});

describe("what the quantiles are measured in", () => {
  it("states the stream and the normalisation the control was served on", async () => {
    serve(envelope());
    await renderPeerControl(host, "/v1/wells/3305310451/type-curve", {}, callbacks);

    const facts = [...host.querySelectorAll(".gw-peer-facts dt")].map((node) => node.textContent);
    const values = [...host.querySelectorAll(".gw-peer-facts dd")].map((node) => node.textContent);
    expect(facts).toContain("Stream");
    expect(values).toContain("oil");
    expect(facts).toContain("Normalisation");
    expect(values).toContain("typecurve_absolute");
  });

  it("puts the served unit on every quantile column, so a volume is never a bare number", async () => {
    serve(envelope());
    await renderPeerControl(host, "/v1/wells/3305310451/type-curve", {}, callbacks);

    const heads = [...host.querySelectorAll(".gw-peer-table th[scope=col]")].map(
      (node) => node.textContent,
    );
    expect(heads.filter((head) => head?.includes("bbl"))).toHaveLength(3);
    expect(host.querySelector(".gw-peer-table caption")?.textContent).toContain("bbl");
  });
});
