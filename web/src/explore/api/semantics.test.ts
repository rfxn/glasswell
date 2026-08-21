// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_STATE } from "../../app/state.ts";
import type { AppState } from "../../app/state.ts";
import { buildCatalogue } from "../catalogue.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import { operationFor } from "../grid/schema.ts";
import { glossaryBodies } from "./fixtures.ts";
import { mountPane } from "./pane.ts";
import { coverageOf, explain, semanticsFor } from "./semantics.ts";

const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8"));
const CATALOGUE = buildCatalogue(SNAPSHOT);
const SOURCES = ["src/explore/api/semantics.ts", "src/explore/api/pane.ts"].map((path) => ({
  path,
  source: readFileSync(path, "utf8"),
}));

function dataset(id: string): CatalogueDataset {
  const found = CATALOGUE.datasets.find((candidate) => candidate.id === id);
  if (!found) throw new Error(`no dataset ${id}`);
  return found;
}

function parametersOf(operationId: string) {
  return semanticsFor(operationFor(SNAPSHOT, operationId));
}

function settle(times = 3): Promise<void> {
  return new Promise((resolve) => {
    let left = times;
    const step = (): void => {
      left -= 1;
      if (left <= 0) resolve();
      else setTimeout(step, 0);
    };
    setTimeout(step, 0);
  });
}

function pane(id: string, operationId: string, state: Partial<AppState> = {}): HTMLElement {
  const host = document.getElementById("pane") as HTMLElement;
  mountPane(host, {
    document: SNAPSHOT,
    state: { ...DEFAULT_STATE, view: "explore", ds: id, ...state },
    onSections: () => undefined,
    signal: new AbortController().signal,
    call: {
      state: "loaded",
      role: "collection",
      dataset: dataset(id),
      request: { operationId, path: "/v1/x", query: {} },
      envelope: { data: [], meta: {}, links: {} } as never,
      error: null,
      meta: { status: 200, headers: new Headers(), elapsed_ms: 4 },
    },
  });
  return host;
}

beforeEach(() => {
  document.body.innerHTML = '<aside id="pane"></aside>';
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

describe("WHAT, WHY, SO and SEE each have one source, and none of them is the client (§4.3)", () => {
  it("reads WHAT off the parameter description and SO off the operation's own annotation", () => {
    const stream = parametersOf("get_well_production").find((one) => one.name === "stream");

    expect(stream?.what).toBe("Stream to include; repeatable. Defaults to oil, gas and water.");
    expect(stream?.so).toContain("Repeat it to ask for more than one");
    expect(stream?.termId).toBe("gt_stream");
    expect(stream?.annotated).toBe(true);
  });

  it("resolves WHY and SEE through the term the operation named, and nowhere else", async () => {
    const explanation = await explain("gt_stream");
    const recorded = glossaryBodies["/v1/glossary/gt_stream"] as {
      data: { expanded_definition: string; related_terms: string[] };
    };

    expect(explanation.why).toBe(recorded.data.expanded_definition);
    expect(explanation.see).toEqual(recorded.data.related_terms);
  });

  it("renders the four fields in the pane when the term answers", async () => {
    const host = pane("production", "get_well_production", { extra: { "f.api10": ["3305310451"] } });
    (host.querySelector('.gw-api-param[data-param="stream"] .gw-api-param-head') as HTMLElement).click();
    await settle();

    const fields = [...host.querySelectorAll('.gw-api-param[data-param="stream"] .gw-api-field')];
    expect(fields.map((field) => (field as HTMLElement).dataset["field"])).toEqual([
      "WHAT",
      "WHY",
      "SO",
      "SEE",
    ]);
  });

  it("degrades to WHAT only, with the muted ? an unbound column carries, and counts it", () => {
    const host = pane("production", "get_well_production");
    const api10 = host.querySelector('.gw-api-param[data-param="api10"]') as HTMLElement;

    expect(api10.dataset["annotated"]).toBe("false");
    expect(api10.querySelector(".gw-col-unbound")?.textContent).toBe("?");
    expect([...api10.querySelectorAll(".gw-api-field")].map((f) => (f as HTMLElement).dataset["field"])).toEqual([
      "WHAT",
    ]);
    expect(host.querySelector(".gw-api-coverage")?.textContent).toContain("4 of 5 parameters");
  });

  it("counts the parameters A-8 has not reached rather than hiding them", () => {
    const production = coverageOf(parametersOf("get_well_production"));
    const quarantine = coverageOf(parametersOf("list_quarantine"));
    const record = coverageOf(parametersOf("get_quarantine_row"));

    expect(production).toEqual({ annotated: 4, total: 5, percent: 80 });
    expect(quarantine).toEqual({ annotated: 7, total: 7, percent: 100 });
    // A detail operation carries no A-8 entry at all, which is the whole-operation degradation.
    expect(record).toEqual({ annotated: 0, total: 1, percent: 0 });
  });

  it("never invents a WHY: every line that produces one reads it off the term", () => {
    // Comments and string literals come out first: prose may contain the word, code may not
    // produce the value from anywhere but the glossary row.
    const code = (line: string): string =>
      line.replace(/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`/g, '""');
    const mentions = SOURCES.flatMap((file) =>
      file.source
        .split("\n")
        .filter((line) => {
          const trimmed = line.trimStart();
          return !trimmed.startsWith("//") && !trimmed.startsWith("*") && !trimmed.startsWith("/*");
        })
        .map((line) => ({ path: file.path, line: code(line) }))
        .filter((entry) => /\bwhy\b/i.test(entry.line)),
    );

    // A floor, so a rename that empties the scan cannot pass it green.
    expect(mentions.length).toBeGreaterThan(2);
    for (const { path, line } of mentions) {
      expect(line, `${path}: ${line.trim()}`).toMatch(
        /expanded_definition|why: string \| null|why: null|explanation\.why/,
      );
    }
  });

  it("states the API's own facts with the API's own reason, and adds none", () => {
    const [limit] = parametersOf("list_quarantine").filter((one) => one.name === "limit");
    const [state] = parametersOf("list_quarantine").filter((one) => one.name === "state");

    expect(limit?.facts.map((fact) => fact.label)).toEqual([
      "default 100",
      "at most 200",
      "at least 1",
    ]);
    expect(limit?.facts.find((fact) => fact.label === "at most 200")?.reason).toContain(
      "declares its own cap",
    );
    expect(state?.facts[0]?.label).toBe("one of open, released, accepted_loss, superseded");
    expect(state?.facts[0]?.reason).toContain("refused, not ignored");
  });

  it("names a parameter's type from the schema, unwrapping the nullable FastAPI union (m5)", () => {
    const parameters = parametersOf("list_wells");

    expect(parameters.find((one) => one.name === "as_of")?.type).toBe("string (date)");
    expect(parameters.find((one) => one.name === "limit")?.type).toBe("integer");
    expect(parameters.find((one) => one.name === "bbox")?.type).toBe("string");
    expect(parametersOf("get_well_production").find((one) => one.name === "stream")?.type).toBe(
      "array of string",
    );
  });

  it("says so rather than showing an empty heading when an operation takes no parameters (C5 P4)", () => {
    const host = pane("problems", "get_service_index");

    expect(parametersOf("get_service_index")).toEqual([]);
    expect(host.querySelector(".gw-api-params")).toBe(null);
    expect(host.textContent).toContain("takes no parameters");
  });
});
