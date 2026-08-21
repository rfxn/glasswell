// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { readState, writeState } from "../../app/state.ts";
import type { AppState } from "../../app/state.ts";
import {
  conformanceEnvelope,
  quarantineEnvelope,
  quarantineSummaryEnvelope,
} from "../fixtures.ts";
import { resetTrail } from "./chips.ts";
import { conformanceRuleEnvelope, quarantineDetailEnvelope } from "./fixtures.ts";

const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8"));

const BODIES: Record<string, unknown> = {
  "/openapi.json": SNAPSHOT,
  "/v1/quarantine": quarantineEnvelope,
  "/v1/quarantine/summary": quarantineSummaryEnvelope,
  "/v1/quarantine/qr_01contract0003": quarantineDetailEnvelope,
  "/v1/conformance": conformanceEnvelope,
  "/v1/conformance/cr_nd_status_vocab_1": conformanceRuleEnvelope,
};

const OPENED = "/?view=explore&ds=quarantine&f.state=open&cursor=opaque";

let host: HTMLElement;
let requested: string[];
let state: AppState;

/** main.ts's own commit, which is the only thing the shell is given (C0's seam). */
function hooks(): { commit(next: Partial<AppState>, mode?: "push" | "replace"): void } {
  return {
    commit: (next, mode = "push") => {
      state = { ...state, ...next };
      writeState(state, mode);
    },
  };
}

async function settle(times = 3): Promise<void> {
  for (let index = 0; index < times; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

function collectionRequests(): string[] {
  return requested.filter((url) => url.split("?")[0] === "/v1/quarantine");
}

function rows(): HTMLElement[] {
  return [...document.querySelectorAll(".gw-grid-tr")] as HTMLElement[];
}

function panel(): HTMLElement | null {
  return document.querySelector(".gw-detail");
}

async function mountShell(url = OPENED): Promise<typeof import("../shell.ts")> {
  window.history.replaceState(null, "", url);
  state = readState();
  vi.resetModules();
  const shell = await import("../shell.ts");
  await shell.mountExplorer(host, state, hooks());
  await settle();
  return shell;
}

/** The back button reaches the app as a popstate over the URL history restored. */
async function back(to: string): Promise<void> {
  window.history.replaceState(null, "", to);
  window.dispatchEvent(new PopStateEvent("popstate"));
  await settle();
}

beforeEach(() => {
  requested = [];
  resetTrail();
  document.body.innerHTML = '<div id="gw-explore"></div>';
  host = document.getElementById("gw-explore") as HTMLElement;
  window.localStorage.setItem("glasswell.key", "f".repeat(64));
  vi.stubGlobal("fetch", (url: string) => {
    requested.push(String(url));
    const path = String(url).split("?")[0] as string;
    const body = BODIES[path];
    if (body === undefined) return Promise.resolve(new Response("{}", { status: 404 }));
    return Promise.resolve(
      new Response(JSON.stringify(body), { headers: { "content-type": "application/json" } }),
    );
  });
});

afterEach(async () => {
  const shell = await import("../shell.ts");
  shell.unmountExplorer();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("the detail is URL-addressable and the back button returns the grid (§2.6, C0)", () => {
  it("puts the row in the URL without disturbing the walk that found it", async () => {
    await mountShell();
    const before = collectionRequests().length;
    rows()[0]?.click();
    await settle();

    const next = new URLSearchParams(window.location.search);
    expect(next.get("row")).toBe("qr_01contract0003");
    expect(next.get("f.state")).toBe("open");
    expect(next.get("cursor")).toBe("opaque");
    // One request per hop: the page the reader is looking at is not re-read to expand a row.
    expect(collectionRequests()).toHaveLength(before);
    expect(panel()).not.toBe(null);
  });

  it("restores the cursor and the filters on the way back, and closes the panel", async () => {
    await mountShell();
    rows()[0]?.click();
    await settle();
    expect(panel()).not.toBe(null);

    await back(OPENED);

    expect(panel()).toBe(null);
    // The grid re-read the collection on the back, and read it with the same walk.
    expect(collectionRequests()[collectionRequests().length - 1]).toBe("/v1/quarantine?state=open&cursor=opaque");
    expect(rows().length).toBeGreaterThan(0);
  });

  it("opens the panel from the URL alone, which is what makes a row shareable", async () => {
    await mountShell(`${OPENED}&row=qr_01contract0003`);

    const open = panel();
    expect(open).not.toBe(null);
    expect(open?.dataset["rowId"]).toBe("qr_01contract0003");
    expect(rows()[0]?.getAttribute("aria-expanded")).toBe("true");
  });

  it("keeps the panel out of the row it belongs to, so no cell track is sized by it", async () => {
    await mountShell();
    const table = document.querySelector(".gw-grid-table") as HTMLElement;
    const headers = table.querySelectorAll(".gw-grid-th").length;
    const cells = table.querySelectorAll(".gw-grid-td").length;
    rows()[0]?.click();
    await settle();

    const slot = document.querySelector(".gw-grid-detail") as HTMLElement;
    expect(slot.closest(".gw-grid-tr")).toBe(null);
    expect(slot.previousElementSibling).toBe(rows()[0]);
    expect(table.querySelectorAll(".gw-grid-th")).toHaveLength(headers);
    expect(table.querySelectorAll(".gw-grid-td")).toHaveLength(cells);
  });

  it("stands the panel on its own when the hop lands on a row this page does not hold", async () => {
    await mountShell("/?view=explore&ds=quarantine&row=qr_01contract0003&f.state=open");
    // The recorded page holds this row, so the standalone arm is asserted on one it does not.
    await mountShell("/?view=explore&ds=quarantine&row=qr_not_on_this_page");

    expect(panel()?.dataset["rowId"]).toBe("qr_not_on_this_page");
    expect(document.querySelector(".gw-grid-detail")?.nextElementSibling?.className).toContain(
      "gw-grid-table",
    );
  });

  it("hands the panel the columns the grid hides, reason and all (M3)", async () => {
    // No recorded record for this row, so the detail request 404s and the collection's own
    // fields are what stands — which is the frame a `hidden_reason` can appear in at all.
    await mountShell("/?view=explore&ds=quarantine&row=qr_01contract0002");

    const keys = [...(panel()?.querySelectorAll(".gw-detail-key") ?? [])].map((key) => key.textContent ?? "");
    const reasons = [...(panel()?.querySelectorAll(".gw-detail-hidden") ?? [])];
    expect(keys.some((key) => key.includes("row_fingerprint"))).toBe(true);
    expect(reasons).toHaveLength(2);
    expect((reasons[0] as HTMLElement).title).toContain("content address");
  });

  it("leaves a cell's own affordances alone: a term opens its definition, not the row", async () => {
    await mountShell();
    const term = rows()[0]?.querySelector("gw-term") as HTMLElement;
    // The keyboard path is the one that bubbles: `gw-term` prevents the default on Enter but
    // does not stop the event, so without the guard a definition and a row detail open together.
    term.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await settle();

    expect(panel()).toBe(null);
    expect(new URLSearchParams(window.location.search).get("row")).toBe(null);
  });

  it("closes the row rather than the surface when the panel's own close is used", async () => {
    await mountShell(`${OPENED}&row=qr_01contract0003`);
    (panel()?.querySelector(".gw-detail-close") as HTMLElement).click();
    await settle();

    expect(panel()).toBe(null);
    expect(new URLSearchParams(window.location.search).get("row")).toBe(null);
    expect(rows().length).toBeGreaterThan(0);
  });
});

describe("a chip hop is one request into a filtered dataset (§3.3, §0.4)", () => {
  it("crosses to the target dataset carrying as_of, and never walks a chain", async () => {
    await mountShell(`/?view=explore&ds=quarantine&as_of=2026-08-01&row=qr_01contract0003`);
    const chip = document.querySelector('.gw-join-chip[data-target="conformance"]') as HTMLElement;
    chip.click();
    await settle();

    const next = new URLSearchParams(window.location.search);
    expect(next.get("ds")).toBe("conformance");
    expect(next.get("row")).toBe("cr_nd_status_vocab_1");
    expect(next.get("as_of")).toBe("2026-08-01");
    // The hop's own collection, and its own record. No third request walked an edge.
    expect(requested.filter((url) => url.startsWith("/v1/conformance"))).toEqual([
      "/v1/conformance?as_of=2026-08-01",
      // get_conformance_rule declares no as_of, so none is put on its wire (§3.1 rule 3).
      "/v1/conformance/cr_nd_status_vocab_1",
    ]);
  });

  it("records the hop, so the breadcrumb can answer how the reader got here", async () => {
    await mountShell(`/?view=explore&ds=quarantine&row=qr_01contract0003`);
    (document.querySelector('.gw-join-chip[data-target="conformance"]') as HTMLElement).click();
    await settle();

    const walked = [...document.querySelectorAll(".gw-trail-op")].map((one) => one.textContent);
    expect(walked).toEqual(["get_quarantine_row", "get_conformance_rule"]);
  });
});
