// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_STATE } from "../app/state.ts";
import type { AppState } from "../app/state.ts";

const SNAPSHOT = readFileSync("../tests/contract/openapi_snapshot.json", "utf8");

const commit = vi.fn();
let host: HTMLElement;
let fetched: string[];

// A leaked subscriber is counted by what it does, not by what it registered: an AbortSignal
// detaches a listener without ever calling removeEventListener, so wrapping the registration
// pair measures nothing. Each render inserts exactly one .gw-explore root, so one popstate
// answered twice inserts two. C0's map-idempotence lesson, one surface on.
let renders: number;
let observer: MutationObserver | undefined;

function countRenders(): void {
  renders = 0;
  observer = new MutationObserver((records) => {
    renders += records.filter((record) =>
      [...record.addedNodes].some((node) => node instanceof HTMLElement && node.matches(".gw-explore")),
    ).length;
  });
  observer.observe(host, { childList: true });
}

async function settle(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

async function shell(): Promise<typeof import("./shell.ts")> {
  vi.resetModules();
  return await import("./shell.ts");
}

function state(over: Partial<AppState> = {}): AppState {
  return { ...DEFAULT_STATE, view: "explore", ...over };
}

function root(): HTMLElement | null {
  return host.querySelector(".gw-explore");
}

beforeEach(() => {
  commit.mockClear();
  fetched = [];
  renders = 0;
  document.body.innerHTML = '<div id="gw-explore" hidden></div>';
  host = document.getElementById("gw-explore") as HTMLElement;
  window.history.replaceState(null, "", "/?view=explore");
  window.localStorage.setItem("glasswell.key", "f".repeat(64));
  vi.stubGlobal("fetch", (url: string) => {
    fetched.push(String(url));
    return Promise.resolve(new Response(SNAPSHOT, { headers: { "content-type": "application/json" } }));
  });
});

afterEach(() => {
  observer?.disconnect();
  observer = undefined;
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("the shell mounts into the host C0's dispatch gives it", () => {
  it("renders the rail, the three tabs, the centre and the pane host", async () => {
    const { mountExplorer, GRID_HOST_ID, FACET_HOST_ID, PANE_HOST_ID } = await shell();

    await mountExplorer(host, state({ ds: "wells" }), { commit });

    expect(root()).not.toBeNull();
    expect(host.getAttribute("data-tab")).toBe("datasets");
    expect(host.querySelector(".gw-explore-rail")).not.toBeNull();
    expect([...host.querySelectorAll('[role="tab"]')].map((tab) => tab.getAttribute("data-tab"))).toEqual([
      "datasets",
      "query",
      "learn",
    ]);
    // C7 fills the facet host with one control per query parameter of this operation, so the
    // assertion moved from "empty" to "generated" rather than being deleted.
    const facets = document.getElementById(FACET_HOST_ID) as HTMLElement;
    expect(facets.querySelectorAll("[data-facet]").length).toBeGreaterThan(4);
    expect([...facets.querySelectorAll("[data-facet]")].map((f) => f.getAttribute("data-facet")))
      .toContain("operator");
    // The pane still carries C6's placeholder; the grid host keeps its `data-ds` and its
    // children are C7's, which is the contract K1 wrote down.
    expect(document.getElementById(PANE_HOST_ID)?.textContent).toMatch(/renders here/);
    expect(document.getElementById(GRID_HOST_ID)?.dataset["ds"]).toBe("wells");
    expect(document.getElementById(GRID_HOST_ID)?.textContent).toContain("/api10");
  });

  it("reads the document once, however many times the reader flips surfaces", async () => {
    const { mountExplorer } = await shell();

    for (let flip = 0; flip < 4; flip += 1) await mountExplorer(host, state(), { commit });

    expect(fetched.filter((url) => url.includes("/openapi.json"))).toHaveLength(1);
  });

  it("sends the key the same way every other call does, and never builds its own URL", async () => {
    const { mountExplorer } = await shell();

    await mountExplorer(host, state(), { commit });

    expect(fetched[0]).toBe("/openapi.json");
  });
});

describe("mount and teardown are symmetric (C0's contract, C0's idempotence lesson)", () => {
  it("leaves exactly one root and one subscriber however many times it is remounted", async () => {
    const { mountExplorer } = await shell();
    for (let flip = 0; flip < 5; flip += 1) await mountExplorer(host, state(), { commit });
    countRenders();

    window.history.replaceState(null, "", "/?view=explore&ds=quarantine");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await settle();

    expect(host.querySelectorAll(".gw-explore")).toHaveLength(1);
    expect(renders).toBe(1);
  });

  it("clears the host and its attribute, so the map surface inherits nothing", async () => {
    const { mountExplorer, unmountExplorer } = await shell();

    await mountExplorer(host, state(), { commit });
    unmountExplorer();

    expect(host.children).toHaveLength(0);
    expect(host.hasAttribute("data-tab")).toBe(false);
  });

  it("does not answer a popstate after teardown, which is what a leaked handler would do", async () => {
    const { mountExplorer, unmountExplorer } = await shell();
    await mountExplorer(host, state(), { commit });
    unmountExplorer();
    countRenders();

    window.history.replaceState(null, "", "/?view=explore&ds=quarantine");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await settle();

    expect(renders).toBe(0);
    expect(host.children).toHaveLength(0);
  });

  it("re-renders on a same-surface popstate, which main.ts deliberately does not do", async () => {
    const { mountExplorer } = await shell();
    await mountExplorer(host, state({ ds: "wells" }), { commit });

    window.history.replaceState(null, "", "/?view=explore&ds=quarantine");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await vi.waitFor(() =>
      expect(host.querySelector('button[data-ds][aria-current="page"]')?.getAttribute("data-ds")).toBe(
        "quarantine",
      ),
    );
  });
});

describe("selection and tabs go through the URL, never through a local flag", () => {
  it("names the columns the operation declares, rather than an empty rectangle", async () => {
    const { mountExplorer, GRID_HOST_ID } = await shell();

    await mountExplorer(host, state({ ds: "wells" }), { commit });

    const grid = document.getElementById(GRID_HOST_ID) as HTMLElement;
    expect(grid.textContent).toContain("/api10");
    expect(grid.textContent).toContain("/well_name");
  });

  it("commits ds through C0's hook and marks the rail entry current", async () => {
    const { mountExplorer } = await shell();
    await mountExplorer(host, state(), { commit });

    (host.querySelector('button[data-ds="quarantine"]') as HTMLButtonElement).click();

    expect(commit).toHaveBeenCalledWith({ ds: "quarantine", row: null }, "push");
    expect(host.querySelector('button[data-ds="quarantine"]')?.getAttribute("aria-current")).toBe("page");
  });

  it("commits tab and re-renders the centre without touching the selection", async () => {
    const { mountExplorer } = await shell();
    await mountExplorer(host, state({ ds: "wells" }), { commit });

    (host.querySelector('[role="tab"][data-tab="query"]') as HTMLButtonElement).click();

    expect(commit).toHaveBeenCalledWith({ tab: "query" }, "push");
    expect(host.getAttribute("data-tab")).toBe("query");
    expect(host.querySelector('button[data-ds="wells"]')?.getAttribute("aria-current")).toBe("page");
  });

  it("states what the query and learn tabs are, and renders no data on either", async () => {
    const { mountExplorer, GRID_HOST_ID } = await shell();

    for (const tab of ["query", "learn"] as const) {
      await mountExplorer(host, state({ tab }), { commit });
      const panel = host.querySelector('[role="tabpanel"]') as HTMLElement;

      expect(panel.textContent, tab).toMatch(/not built|P-B|P-C/);
      expect(document.getElementById(GRID_HOST_ID), tab).toBeNull();
    }
  });
});

describe("the centre states the operation behind the dataset, and nothing it cannot show", () => {
  it("names the operation and its path from the document, not from a table in the client", async () => {
    const { mountExplorer } = await shell();

    await mountExplorer(host, state({ ds: "quarantine" }), { commit });

    const centre = host.querySelector(".gw-explore-centre") as HTMLElement;
    expect(centre.textContent).toContain("list_quarantine");
    expect(centre.textContent).toContain("/v1/quarantine");
    expect(centre.textContent).toContain("Quarantine");
  });

  it("asks the reader to pick a dataset rather than picking one for them", async () => {
    const { mountExplorer, GRID_HOST_ID } = await shell();

    await mountExplorer(host, state({ ds: null }), { commit });

    expect(host.querySelectorAll('button[data-ds][aria-current="page"]')).toHaveLength(0);
    expect(document.getElementById(GRID_HOST_ID)).toBeNull();
  });

  it("says so when the URL names a dataset the document does not declare", async () => {
    const { mountExplorer } = await shell();

    await mountExplorer(host, state({ ds: "reserves" }), { commit });

    expect((host.querySelector(".gw-explore-centre") as HTMLElement).textContent).toContain("reserves");
    expect(host.querySelectorAll('button[data-ds][aria-current="page"]')).toHaveLength(0);
  });
});

describe("a document the explorer cannot read is a degraded surface, never a thrown boot", () => {
  it("mounts anyway when /openapi.json answers a problem", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve(
        new Response(JSON.stringify({ title: "Forbidden", status: 403 }), { status: 403 }),
      ),
    );
    const { mountExplorer } = await shell();

    await expect(mountExplorer(host, state(), { commit })).resolves.toBeUndefined();

    expect(root()).not.toBeNull();
    expect(host.querySelector(".gw-explore-rail-degraded")).not.toBeNull();
  });

  it("mounts anyway when the fetch itself rejects", async () => {
    vi.stubGlobal("fetch", () => Promise.reject(new Error("offline")));
    const { mountExplorer } = await shell();

    await expect(mountExplorer(host, state(), { commit })).resolves.toBeUndefined();

    expect(root()).not.toBeNull();
  });

  it("still renders the honest-gap register, which no fetch can invalidate", async () => {
    vi.stubGlobal("fetch", () => Promise.reject(new Error("offline")));
    const { mountExplorer } = await shell();

    await mountExplorer(host, state(), { commit });

    expect(host.querySelectorAll(".gw-explore-rail-gaps [data-gap]").length).toBeGreaterThan(20);
  });
});
