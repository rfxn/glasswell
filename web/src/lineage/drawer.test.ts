// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderLineageDrawer } from "./drawer.ts";
import { OIL_HANDLE, SHA256, explainEnvelope, problemBody, stubFetch } from "../test/fixtures.ts";

const noop = { onClose: () => {} };
let host: HTMLElement;

beforeEach(() => {
  document.body.innerHTML = "";
  host = document.createElement("aside");
  document.body.appendChild(host);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("lineage drawer", () => {
  it("resolves a handle in exactly one /v1/explain call and shows the terminal manifest", async () => {
    const fetchSpy = vi.fn(stubFetch({ "/v1/explain": explainEnvelope }));
    vi.stubGlobal("fetch", fetchSpy);

    await renderLineageDrawer(host, OIL_HANDLE, noop);

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const requested = String(fetchSpy.mock.calls[0]?.[0]);
    expect(requested).toContain("/v1/explain?h=");
    expect(requested).toContain("depth=full");

    const nodes = host.querySelectorAll(".gw-chain-node");
    expect(nodes).toHaveLength(3);
    expect(host.querySelector(".gw-chain-manifest")).not.toBeNull();
    // S9: the checksum is on screen after the first interaction, without expanding anything.
    expect(host.querySelector(".gw-sha256")?.textContent).toBe(SHA256);
    expect(host.querySelector(".gw-sha256")?.textContent).toHaveLength(64);
  });

  it("shows the acquisition URL a stranger can go and check", async () => {
    vi.stubGlobal("fetch", vi.fn(stubFetch({ "/v1/explain": explainEnvelope })));
    await renderLineageDrawer(host, OIL_HANDLE, noop);
    expect(host.querySelector("a")?.getAttribute("href")).toBe(
      "https://www.dmr.nd.gov/oilgas/mpr/2025_10.xlsx",
    );
  });

  it("renders each node's server-authored explanation verbatim", async () => {
    vi.stubGlobal("fetch", vi.fn(stubFetch({ "/v1/explain": explainEnvelope })));
    await renderLineageDrawer(host, OIL_HANDLE, noop);
    const explanations = [...host.querySelectorAll(".gw-node-explanation")].map(
      (node) => node.textContent,
    );
    expect(explanations[0]).toBe(explainEnvelope.data.chains[0]?.nodes[0]?.explanation);
    expect(explanations[1]).toBe(explainEnvelope.data.chains[0]?.nodes[1]?.explanation);
  });

  it("renders a broken chain as a broken chain, naming the stop reason", async () => {
    vi.stubGlobal("fetch", vi.fn(stubFetch({ "/v1/explain": problemBody })));
    await renderLineageDrawer(host, "drv_missing", noop);
    const text = host.textContent ?? "";
    expect(text).toContain("lineage_unresolved");
    expect(text).toContain("unknown_id");
  });
});
