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
    // The served default, not `full`: a chain that always arrives complete makes `truncated`
    // a marker nobody can see, and the way past it is a control beside the marker (N-12).
    expect(requested).toContain("depth=3");

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

  it("keeps the acquisition link out of the app's own tab, so state survives the download", async () => {
    vi.stubGlobal("fetch", vi.fn(stubFetch({ "/v1/explain": explainEnvelope })));
    await renderLineageDrawer(host, OIL_HANDLE, noop);
    const link = host.querySelector("a") as HTMLAnchorElement;

    expect(link.target).toBe("_blank");
    expect(link.rel).toContain("noopener");
  });

  it("splits into a fixed head and a scrolling body like every other panel", async () => {
    vi.stubGlobal("fetch", vi.fn(stubFetch({ "/v1/explain": explainEnvelope })));
    await renderLineageDrawer(host, OIL_HANDLE, noop);

    expect(host.children).toHaveLength(2);
    expect(host.children[0]?.className).toContain("gw-panel-head");
    expect(host.children[1]?.className).toContain("gw-panel-body");
    expect(host.querySelector(".gw-panel-body .gw-chain")).toBeTruthy();
  });

  it("gives the head a focus target so opening the drawer can move focus into it", async () => {
    vi.stubGlobal("fetch", vi.fn(stubFetch({ "/v1/explain": explainEnvelope })));
    await renderLineageDrawer(host, OIL_HANDLE, noop);

    expect(host.querySelector("h2")?.getAttribute("tabindex")).toBe("-1");
  });

  it("offers a way back to the well the reader came from, not only a way out", async () => {
    // Below 1600 the drawer fills the rail's column and hides the card completely; the only
    // control was an x, which says "leave" and not "return to the well I was reading".
    vi.stubGlobal("fetch", vi.fn(stubFetch({ "/v1/explain": explainEnvelope })));
    const onClose = vi.fn();
    await renderLineageDrawer(host, OIL_HANDLE, { onClose, returnTo: "BRENNA 11-14H" });

    const back = host.querySelector<HTMLButtonElement>(".gw-drawer-back");
    expect(back?.textContent).toBe("< Back to BRENNA 11-14H");
    expect(back?.getAttribute("aria-label")).toBe("Back to BRENNA 11-14H");
    back?.click();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("offers no way back where no well is open, rather than a control naming nothing", async () => {
    vi.stubGlobal("fetch", vi.fn(stubFetch({ "/v1/explain": explainEnvelope })));
    await renderLineageDrawer(host, OIL_HANDLE, noop);

    expect(host.querySelector(".gw-drawer-back")).toBeNull();
  });

  it("renders a broken chain as a broken chain, naming the stop reason", async () => {
    vi.stubGlobal("fetch", vi.fn(stubFetch({ "/v1/explain": problemBody })));
    await renderLineageDrawer(host, "drv_missing", noop);
    const text = host.textContent ?? "";
    expect(text).toContain("lineage_unresolved");
    expect(text).toContain("unknown_id");
  });
});

describe("a chain that stopped short", () => {
  const truncated = {
    ...explainEnvelope,
    data: {
      chains: [{ ...explainEnvelope.data.chains[0], truncated: true, depth: 3 }],
    },
  };

  it("says it was truncated and offers the walk that finishes it", async () => {
    const fetchSpy = vi.fn(stubFetch({ "/v1/explain": truncated }));
    vi.stubGlobal("fetch", fetchSpy);
    await renderLineageDrawer(host, OIL_HANDLE, noop);

    expect(host.querySelector(".gw-drawer-summary")?.textContent).toContain("truncated");
    const deeper = host.querySelector<HTMLButtonElement>(".gw-drawer-deeper");
    expect(deeper?.textContent).toBe("Read the full chain");

    deeper?.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(String(fetchSpy.mock.calls[1]?.[0])).toContain("depth=8");
  });

  it("offers nothing extra where the chain already reached its manifests", async () => {
    vi.stubGlobal("fetch", vi.fn(stubFetch({ "/v1/explain": explainEnvelope })));
    await renderLineageDrawer(host, OIL_HANDLE, noop);

    expect(host.querySelector(".gw-drawer-deeper")).toBeNull();
  });
});
