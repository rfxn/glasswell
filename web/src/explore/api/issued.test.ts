// @vitest-environment happy-dom
//
// 9.1, and the reason it is written first: a REQUEST block that drifts from the request is
// worse than none (SB-08 §4.2). The spy sits at the client seam — `getEnvelope` — and not at
// `fetch`, so the assertion is that the pane and the grid share one code path rather than that
// two builders happen to agree today.
import { readFileSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { readState, writeState } from "../../app/state.ts";
import type { AppState } from "../../app/state.ts";
import { conformanceEnvelope, quarantineEnvelope, quarantineSummaryEnvelope } from "../fixtures.ts";
import { conformanceRuleEnvelope, quarantineDetailEnvelope } from "../detail/fixtures.ts";

const { issued } = vi.hoisted(() => ({ issued: [] as string[] }));

vi.mock("../../api/client.ts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client.ts")>();
  return {
    ...actual,
    getEnvelope: (
      path: string,
      query: Record<string, string | string[]> = {},
      signal?: AbortSignal,
      meta?: { out?: unknown },
    ) => {
      issued.push(actual.apiUrl(path, query));
      return actual.getEnvelope(path, query, signal, meta as never);
    },
  };
});

const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8"));
const QUARANTINE_ROW = quarantineDetailEnvelope.data.quarantine_id;
const CONFORMANCE_RULE = conformanceRuleEnvelope.data.rule_id;

const BODIES: Record<string, unknown> = {
  "/openapi.json": SNAPSHOT,
  "/v1/quarantine": quarantineEnvelope,
  "/v1/quarantine/summary": quarantineSummaryEnvelope,
  [`/v1/quarantine/${QUARANTINE_ROW}`]: quarantineDetailEnvelope,
  "/v1/conformance": conformanceEnvelope,
  [`/v1/conformance/${CONFORMANCE_RULE}`]: conformanceRuleEnvelope,
};

// Two values for one filter: the shape a query-string builder gets wrong by collapsing.
const REPEATED = "/?view=explore&ds=quarantine&f.reason_code=unknown_vocab&f.reason_code=key_collision";

let host: HTMLElement;
let state: AppState;

function hooks(): { commit(next: Partial<AppState>, mode?: "push" | "replace"): void } {
  return {
    commit: (next, mode = "push") => {
      state = { ...state, ...next };
      writeState(state, mode);
    },
  };
}

async function settle(times = 4): Promise<void> {
  for (let index = 0; index < times; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

async function mountShell(url: string): Promise<void> {
  window.history.replaceState(null, "", url);
  state = readState();
  vi.resetModules();
  const shell = await import("../shell.ts");
  await shell.mountExplorer(host, state, hooks());
  await settle();
}

/** What the reader can actually copy: the URL inside the rendered curl, not a data attribute. */
function renderedCurlUrl(): string {
  const block = document.querySelector('.gw-api-command[data-dialect="curl"]');
  return /'(https?:\/\/[^']+)'/.exec(block?.textContent ?? "")?.[1] ?? "";
}

function occurrences(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

beforeEach(() => {
  issued.length = 0;
  document.body.innerHTML = '<div id="gw-explore"></div>';
  host = document.getElementById("gw-explore") as HTMLElement;
  window.localStorage.setItem("glasswell.key", "f".repeat(64));
  vi.stubGlobal("fetch", (url: string) => {
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

describe("the pane renders the call the centre column issued (§4.2, 9.1)", () => {
  it("renders the URL the grid actually issued, byte for byte", async () => {
    await mountShell(REPEATED);
    const collection = issued.find((url) => url.startsWith("/v1/quarantine?")) as string;
    const rendered = renderedCurlUrl();

    expect(collection).toBe("/v1/quarantine?reason_code=unknown_vocab&reason_code=key_collision");
    expect(rendered).toContain(collection);
    // Absolute, with the real host: a relative path teaches nothing about calling the service.
    expect(rendered.startsWith(`${window.location.origin}/v1/`)).toBe(true);
    // A repeated filter is two values, in the command exactly as it was on the wire.
    expect(occurrences(collection, "reason_code=")).toBe(2);
    expect(occurrences(rendered, "reason_code=")).toBe(2);
  });

  it("renders the grid's call, not the summary the same render issued (C7 M4)", async () => {
    // `state` is a filter the summary operation can express, so the second call is made and the
    // pane has two candidates to choose between rather than one.
    await mountShell("/?view=explore&ds=quarantine&f.state=open");

    expect(issued.some((url) => url.startsWith("/v1/quarantine/summary"))).toBe(true);
    expect(renderedCurlUrl()).not.toContain("/summary");
  });

  it("follows the reader into a record, because that is the call now in view (C8 N1)", async () => {
    await mountShell(`/?view=explore&ds=quarantine&row=${QUARANTINE_ROW}`);
    const { curlFor } = await import("./request.ts");
    const { trail } = await import("../detail/chips.ts");
    const walked = trail();
    const last = walked[walked.length - 1];

    expect(renderedCurlUrl()).toContain(`/v1/quarantine/${QUARANTINE_ROW}`);
    expect(last?.operationId).toBe("get_quarantine_row");
    // One builder: the breadcrumb's command for the same step is the pane's, character for
    // character. A second URL assembler is what this test exists to make impossible.
    expect(curlFor(last as never)).toContain(renderedCurlUrl());
  });

  it("returns to the collection's call when the record is closed", async () => {
    await mountShell(`/?view=explore&ds=quarantine&row=${QUARANTINE_ROW}`);
    expect(renderedCurlUrl()).toContain(`/${QUARANTINE_ROW}`);

    (document.querySelector(".gw-detail-close") as HTMLElement).click();
    await settle();

    expect(renderedCurlUrl()).toContain("/v1/quarantine");
    expect(renderedCurlUrl()).not.toContain(`/${QUARANTINE_ROW}`);
  });

  it("names the operation the pane is describing, not the dataset's title", async () => {
    await mountShell("/?view=explore&ds=quarantine");

    expect(document.querySelector(".gw-api-operation-id")?.textContent).toBe("list_quarantine");
  });
});
