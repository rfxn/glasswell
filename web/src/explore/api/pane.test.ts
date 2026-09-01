// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client.ts";
import { DEFAULT_STATE } from "../../app/state.ts";
import type { AppState } from "../../app/state.ts";
import { buildCatalogue } from "../catalogue.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import {
  pagedQuarantineEnvelope,
  pooledProductionEnvelope,
  productionEnvelope,
  quarantineEnvelope,
} from "../fixtures.ts";
import { publishCall, resetCalls } from "./context.ts";
import type { ApiCall, CallState } from "./context.ts";
import { glossaryBodies } from "./fixtures.ts";
import { SECTIONS, mountPane, openSections, serializeSections } from "./pane.ts";

const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8"));
const CATALOGUE = buildCatalogue(SNAPSHOT);

let host: HTMLElement;
let written: string[];

function dataset(id: string): CatalogueDataset {
  const found = CATALOGUE.datasets.find((candidate) => candidate.id === id);
  if (!found) throw new Error(`no dataset ${id}`);
  return found;
}

function call(over: Partial<ApiCall> & { id?: string } = {}): ApiCall {
  const id = over.id ?? "quarantine";
  return {
    state: (over.state ?? "loaded") as CallState,
    role: over.role ?? "collection",
    dataset: over.dataset ?? dataset(id),
    request: over.request ?? {
      operationId: "list_quarantine",
      path: "/v1/quarantine",
      query: { limit: ["10"] },
    },
    envelope: over.envelope === undefined ? (quarantineEnvelope as never) : over.envelope,
    error: over.error ?? null,
    meta:
      over.meta === undefined
        ? { status: 200, headers: new Headers({ "cache-control": "no-store" }), elapsed_ms: 41.4 }
        : over.meta,
    ...(over.missing ? { missing: over.missing } : {}),
  };
}

function mount(over: Partial<ApiCall> & { id?: string } = {}, state: Partial<AppState> = {}): void {
  mountPane(host, {
    document: SNAPSHOT,
    state: { ...DEFAULT_STATE, view: "explore", ds: over.id ?? "quarantine", ...state },
    onSections: (value) => written.push(value),
    signal: new AbortController().signal,
    call: call(over),
  });
}

function sections(): string[] {
  return [...host.querySelectorAll(".gw-api-section")].map(
    (element) => (element as HTMLElement).dataset["section"] as string,
  );
}

function open(): string[] {
  return [...host.querySelectorAll('.gw-api-toggle[aria-expanded="true"]')].map(
    (element) => element.textContent as string,
  );
}

beforeEach(() => {
  written = [];
  resetCalls();
  document.body.innerHTML = '<aside id="pane"></aside>';
  host = document.getElementById("pane") as HTMLElement;
  vi.stubGlobal("fetch", (url: string) => {
    const body = glossaryBodies[String(url).split("?")[0] as string];
    if (body === undefined) return Promise.resolve(new Response("{}", { status: 404 }));
    return Promise.resolve(
      new Response(JSON.stringify(body), { headers: { "content-type": "application/json" } }),
    );
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the four sections and their state in the URL (§4.1, 9.4)", () => {
  it("renders REQUEST, OPERATION and RESPONSE — and no PROBLEMS, which is P-B", () => {
    mount();

    expect(sections()).toEqual(["request", "operation", "response"]);
    expect(SECTIONS).toHaveLength(3);
    expect(host.textContent).not.toContain("PROBLEMS");
  });

  it("opens every section when the URL says nothing, and only the named ones when it does", () => {
    mount({}, { extra: { api: ["request"] } });

    expect(open()).toEqual(["Request"]);
    expect(host.querySelector('[data-section="response"] .gw-api-body')).toBe(null);
  });

  it("writes the section state to api= without asking the API anything again", () => {
    mount();
    (host.querySelector('[data-section="operation"] .gw-api-toggle') as HTMLElement).click();

    expect(written).toEqual(["request,response"]);
    expect(open()).toEqual(["Request", "Response"]);
  });

  it("carries every section closed as a state a link can hold", () => {
    expect(serializeSections([])).toBe("none");
    expect(openSections({ ...DEFAULT_STATE, extra: { api: ["none"] } })).toEqual([]);
    expect(openSections({ ...DEFAULT_STATE, extra: {} })).toEqual([...SECTIONS]);
  });
});

describe("RESPONSE labels the envelope in place (§4.4)", () => {
  it("annotates data, meta and links where the envelope carries them", () => {
    mount();
    const annotated = [...host.querySelectorAll(".gw-api-annotation")].map(
      (element) => (element as HTMLElement).dataset["member"],
    );

    expect(annotated).toEqual(["data", "meta", "links"]);
    expect(host.querySelector('[data-member="links"]')?.textContent).toContain("navigation");
  });

  it("calls out the sidecars a production response actually carries", () => {
    mount({
      id: "production",
      request: { operationId: "get_well_production", path: "/v1/wells/3305310451/production", query: {} },
      envelope: productionEnvelope as never,
    });
    const callout = host.querySelector('[data-callout="sidecar"]')?.textContent ?? "";

    expect(callout).toContain("/_lineage");
    expect(callout).toContain("/_units");
    expect(callout).toContain("/_basis");
    expect(callout).toContain("one handle for the whole series");
    // m12 the other way up: this page has no figure object and still has units, because the
    // sidecar carries them. Saying "no column claims a unit" here would contradict the grid.
    expect(host.querySelector('[data-callout="unit"]')?.textContent).toContain("_units per response");
  });

  it("claims no unit for a page with no figure on it, because kind is per response (m12)", () => {
    mount();

    expect(host.querySelector('[data-callout="unit"]')?.textContent).toContain("Units arrive with values");
    expect(host.querySelector('[data-callout="figure"]')).toBe(null);
  });

  it("takes status, timing and cache class from C0's out-parameter", () => {
    mount();
    const status = host.querySelector(".gw-api-status")?.textContent ?? "";

    expect(status).toContain("200");
    expect(status).toContain("41 ms");
    expect(status).toContain("no-store");
    expect(host.querySelector(".gw-api-cache")?.getAttribute("title")).toContain("O-3");
  });

  it("says the response declared no cache class rather than inventing one", () => {
    mount({ meta: { status: 200, headers: new Headers(), elapsed_ms: 7 } });

    expect(host.querySelector(".gw-api-cache")?.textContent).toBe("no Cache-Control");
  });

  it("states an exact byte count on both sides of a truncation, never a bare ellipsis", () => {
    mount({
      id: "production_pools",
      envelope: pooledProductionEnvelope as never,
      request: {
        operationId: "get_well_production_pools",
        path: "/v1/wells/3305302532/production/pools",
        query: {},
      },
    });
    const bytes = host.querySelector(".gw-api-bytes")?.textContent ?? "";
    const [, shown, whole] = /^([\d,]+) of ([\d,]+) bytes/.exec(bytes) ?? [];

    expect(bytes, bytes).toMatch(/^[\d,]+ of [\d,]+ bytes/);
    expect(Number((shown ?? "").replace(/,/g, ""))).toBeLessThan(
      Number((whole ?? "").replace(/,/g, "")),
    );
    expect(host.querySelector(".gw-api-envelope")?.textContent).not.toContain("…");
    // The cut lands on a line boundary: a body that stops inside a handle reads as a corrupt one.
    const rendered = (host.querySelector(".gw-api-envelope")?.textContent ?? "").split("\n");
    expect(JSON.stringify(pooledProductionEnvelope, null, 2).split("\n")).toContain(
      rendered[rendered.length - 1],
    );
  });

  it("says the whole response is here when it fits", () => {
    const terminal = JSON.parse(JSON.stringify(quarantineEnvelope));
    terminal.data = terminal.data.slice(0, 1);
    terminal.links.next = null;
    terminal.meta.next_cursor = null;
    mount({ envelope: terminal });

    expect(host.querySelector(".gw-api-bytes")?.textContent).toMatch(/^[\d,]+ bytes · whole$/);
  });

  it("keeps the REQUEST block and names the problem when the call failed (§4.7)", () => {
    mount({
      state: "failed",
      envelope: null,
      error: new ApiError({ type: "/v1/errors/validation_failed", title: "Validation failed", status: 422 }),
      meta: { status: 422, headers: new Headers(), elapsed_ms: 3 },
    });

    expect(host.querySelector('.gw-api-command[data-dialect="curl"]')?.textContent).toContain(
      "/v1/quarantine?limit=10",
    );
    expect(host.querySelector('[data-section="response"]')?.textContent).toContain("Validation failed");
    expect(host.querySelector(".gw-api-status")?.textContent).toContain("422");
  });
});

describe("the cursor is taught as a link to follow (§4.2, 9.6)", () => {
  it("offers this page, the next page and a loop that follows links.next", () => {
    mount({ envelope: pagedQuarantineEnvelope as never });
    const blocks = [...host.querySelectorAll(".gw-api-command")].map((one) => one.textContent ?? "");

    expect(blocks).toHaveLength(3);
    expect(blocks[0]).toContain("/v1/quarantine?limit=10");
    expect(blocks[1]).toContain("cursor=");
    expect(blocks[2]).toContain(".links.next");
  });

  it("renders one command when the server offered no next page", () => {
    const terminal = JSON.parse(JSON.stringify(quarantineEnvelope));
    terminal.data = terminal.data.slice(0, 1);
    terminal.links.next = null;
    terminal.meta.next_cursor = null;
    mount({ envelope: terminal });

    expect(host.querySelectorAll(".gw-api-command")).toHaveLength(1);
  });

  it("switches dialect without asking the API anything", () => {
    mount({ envelope: pagedQuarantineEnvelope as never });
    (host.querySelector('.gw-api-dialect[data-dialect="httpie"]') as HTMLElement).click();
    const blocks = [...host.querySelectorAll(".gw-api-command")].map((one) => one.textContent ?? "");

    expect(blocks[0]).toContain("http GET");
    expect(blocks[1]).toContain("http GET");
    expect(written).toEqual([]);
  });
});

describe("the pane answers to whatever the centre column last issued", () => {
  it("re-renders when a call is published, without a route of its own (C8 N3)", () => {
    mountPane(host, {
      document: SNAPSHOT,
      state: { ...DEFAULT_STATE, view: "explore", ds: "quarantine" },
      onSections: () => undefined,
      signal: new AbortController().signal,
    });
    expect(host.textContent).toContain("renders here");

    publishCall(call());

    expect(host.querySelector(".gw-api-operation-id")?.textContent).toBe("list_quarantine");
  });

  it("states that nothing was issued when the dataset still needs an anchor", () => {
    mount({
      id: "production",
      state: "unissued",
      missing: ["api10"],
      envelope: null,
      meta: null,
      request: { operationId: "get_well_production", path: "/v1/wells/{api10}/production", query: {} },
    });

    expect(host.querySelector(".gw-api-status")?.textContent).toBe("not issued yet");
    expect(host.querySelector(".gw-api-command")).toBe(null);
    expect(host.textContent).toContain("one api10 at a time");
  });

  it("refuses to render a call that belongs to the dataset the reader left", () => {
    mount({ id: "quarantine" }, { ds: "wells" });

    expect(host.querySelector(".gw-api-operation-id")).toBe(null);
    expect(host.textContent).toContain("renders here");
  });
});
