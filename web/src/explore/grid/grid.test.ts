// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_STATE } from "../../app/state.ts";
import type { AppState } from "../../app/state.ts";
import { buildCatalogue } from "../catalogue.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import {
  conformanceEnvelope,
  derivationsEnvelope,
  emptyProductionEnvelope,
  glossaryEnvelope,
  healthEnvelope,
  manifestsEnvelope,
  pagedQuarantineEnvelope,
  pooledProductionEnvelope,
  productionEnvelope,
  quarantineEnvelope,
  quarantineSummaryEnvelope,
  serviceIndexEnvelope,
  vintagesEnvelope,
  wellsEnvelope,
} from "../fixtures.ts";
import { columnsFor } from "./columns.ts";
import { WINDOW, mountGrid, overflowNote } from "./grid.ts";

const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8"));
const CATALOGUE = buildCatalogue(SNAPSHOT);

// One recorded envelope per served path, so a grid test never invents a response shape.
const BY_PATH: Record<string, unknown> = {
  "/v1/wells": wellsEnvelope,
  "/v1/quarantine": quarantineEnvelope,
  "/v1/quarantine/summary": quarantineSummaryEnvelope,
  "/v1/conformance": conformanceEnvelope,
  "/v1/manifests": manifestsEnvelope,
  "/v1/derivations": derivationsEnvelope,
  "/v1/vintages": vintagesEnvelope,
  "/v1/glossary": glossaryEnvelope,
  "/v1/health": healthEnvelope,
  "/v1": serviceIndexEnvelope,
  "/v1/wells/3305310451/production": productionEnvelope,
  "/v1/wells/3305302532/production/pools": pooledProductionEnvelope,
  "/v1/wells/3305300003/production": emptyProductionEnvelope,
};

const DATASET_PATH: Record<string, string> = {
  wells: "/v1/wells",
  quarantine: "/v1/quarantine",
  conformance: "/v1/conformance",
  manifests: "/v1/manifests",
  derivations: "/v1/derivations",
  vintages: "/v1/vintages",
  glossary: "/v1/glossary",
  sources: "/v1/health",
  problems: "/v1",
  production: "/v1/wells/3305310451/production",
  production_pools: "/v1/wells/3305302532/production/pools",
};

let host: HTMLElement;
let facetHost: HTMLElement;
let requested: string[];
let commit: ReturnType<typeof vi.fn>;
let overrides: Record<string, unknown>;

function dataset(id: string): CatalogueDataset {
  const found = CATALOGUE.datasets.find((candidate) => candidate.id === id);
  if (!found) throw new Error(`no dataset ${id}`);
  return found;
}

function state(over: Partial<AppState> = {}): AppState {
  return { ...DEFAULT_STATE, view: "explore", ...over };
}

async function mount(id: string, over: Partial<AppState> = {}): Promise<AbortController> {
  const abort = new AbortController();
  await mountGrid(host, {
    dataset: dataset(id),
    document: SNAPSHOT,
    datasets: CATALOGUE.datasets,
    state: state(over),
    facetHost,
    commit,
    signal: abort.signal,
  });
  return abort;
}

beforeEach(() => {
  requested = [];
  overrides = {};
  commit = vi.fn();
  document.body.innerHTML =
    '<div class="gw-explore-panel"><div id="facets"></div><div id="grid"></div></div>';
  host = document.getElementById("grid") as HTMLElement;
  facetHost = document.getElementById("facets") as HTMLElement;
  vi.stubGlobal("fetch", (url: string) => {
    requested.push(String(url));
    const path = String(url).split("?")[0] as string;
    const body = overrides[String(url)] ?? overrides[path] ?? BY_PATH[path];
    if (body === undefined) return Promise.resolve(new Response("{}", { status: 404 }));
    return Promise.resolve(
      new Response(JSON.stringify(body), { headers: { "content-type": "application/json" } }),
    );
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the grid renders a collection off one state object (§3.1 rule 2)", () => {
  it("issues the request the router composed and renders its rows", async () => {
    await mount("quarantine");

    expect(requested[0]).toBe("/v1/quarantine");
    expect(host.querySelectorAll(".gw-grid-tr")).toHaveLength(quarantineEnvelope.data.length);
    expect(host.querySelectorAll(".gw-grid-th")).toHaveLength(
      (dataset("quarantine").columns.default ?? []).length,
    );
  });

  /**
   * §2.5's card list: at 820 the header row is not painted, so the only thing that says what a
   * value is, is the label the cell carries itself. It has to be a node — generated content is
   * paint and nothing else (gate-c10 R3).
   */
  it("gives every cell the column name as a real element, one it can be read and copied from", async () => {
    await mount("quarantine");
    const columns = (dataset("quarantine").columns.default ?? []) as string[];
    const row = host.querySelector(".gw-grid-tr") as HTMLElement;
    const names = [...row.querySelectorAll(".gw-grid-td")].map(
      (cell) => cell.querySelector(".gw-grid-td-name")?.textContent,
    );

    expect(names).toHaveLength(columns.length);
    expect(names.every((name) => typeof name === "string" && name !== "")).toBe(true);
    expect(names[0]).toBe(
      (row.querySelector(".gw-grid-td") as HTMLElement).dataset["name"],
    );
  });

  it("puts a filter on the wire under the parameter's own name", async () => {
    await mount("quarantine", { extra: { "f.state": ["open"], "f.stage": ["conform"] } });

    expect(requested[0]).toBe("/v1/quarantine?state=open&stage=conform");
  });

  it("carries as_of onto every request, because knowledge time is not a per-dataset choice", async () => {
    await mount("wells", { extra: { as_of: ["2026-08-01"] } });

    expect(requested[0]).toBe("/v1/wells?as_of=2026-08-01");
  });

  it("re-commits through the shell when a facet changes, and drops the cursor when it does", async () => {
    await mount("quarantine", { extra: { "f.state": ["open"], cursor: ["opaque"] } });

    const released = [...facetHost.querySelectorAll(".gw-facet-chip")].find(
      (chip) => chip.textContent === "released",
    ) as HTMLElement;
    released.click();

    // A cursor minted under the old filters is a 422 by design; carrying it would teach the
    // reader that the API is flaky rather than that the fingerprint is doing its job.
    expect(commit).toHaveBeenCalledWith({ extra: { "f.state": ["released"] } });
  });

  it("renders the anchor prompt instead of a request that would 404 (K5)", async () => {
    await mount("production");

    expect(requested).toEqual([]);
    expect(host.textContent).toMatch(/one api10 at a time/);
    const form = host.querySelector(".gw-grid-anchor-form") as HTMLFormElement;
    (form.querySelector("input") as HTMLInputElement).value = "3305310451";
    form.dispatchEvent(new Event("submit"));

    expect(commit).toHaveBeenCalledWith({ extra: { "f.api10": ["3305310451"] } });
  });

  it("pivots a production series into months once the anchor is supplied", async () => {
    await mount("production", { extra: { "f.api10": ["3305310451"] } });

    expect(requested[0]).toBe("/v1/wells/3305310451/production");
    expect(host.querySelectorAll(".gw-grid-tr")).toHaveLength(
      productionEnvelope.data.series.pm.length,
    );
    expect(host.querySelectorAll("gw-figure").length).toBe(
      productionEnvelope.data.series.pm.length * 3,
    );
  });

  it("states one report vintage once above the grid instead of on all eighteen cells", async () => {
    await mount("production", { extra: { "f.api10": ["3305310451"] } });

    expect(host.querySelector(".gw-grid-vintage")?.textContent).toMatch(
      /every value here reports at vintage 2026-08-20/,
    );
    // Eighteen identical chips is a column of noise wide enough to push the fifth column off
    // the surface, which is what the C7 visual pass measured before this rule existed.
    expect(host.querySelectorAll("gw-figure[vintage]")).toHaveLength(0);
  });

  it("chips every cell the moment a second vintage appears, because then it means something", async () => {
    const restated = JSON.parse(JSON.stringify(productionEnvelope));
    restated.data.series.oil_bbl_report_vintage[2] = "2026-07-01";
    overrides["/v1/wells/3305310451/production"] = restated;

    await mount("production", { extra: { "f.api10": ["3305310451"] } });

    expect(host.querySelector(".gw-grid-vintage")).toBeNull();
    expect(host.querySelectorAll("gw-figure[vintage]").length).toBe(
      productionEnvelope.data.series.pm.length * 3,
    );
    expect(
      [...host.querySelectorAll("gw-figure[vintage]")].filter(
        (figure) => figure.getAttribute("vintage") === "2026-07-01",
      ),
    ).toHaveLength(1);
  });

  it("sizes one track per column, and two for a figure so its marks leave the number alone", async () => {
    await mount("production", { extra: { "f.api10": ["3305310451"] } });
    const table = host.querySelector(".gw-grid-table") as HTMLElement;

    // pm identifier, three figures at two tracks each, granularity root scalar.
    expect(table.style.gridTemplateColumns).toBe(
      "max-content max-content auto max-content auto max-content auto max-content",
    );
    const water = host.querySelectorAll(".gw-grid-tr")[5]?.querySelectorAll(".gw-grid-td")[3];
    expect(water?.className).toContain("gw-grid-td-figure");
    expect(water?.querySelector(".gw-cell-marks")).not.toBeNull();
  });

  it("keeps a chip out of the number's track, so one annotated row cannot indent a column", async () => {
    // F2 measured a 63 px break on the one row that carried a chip. `reported_zero` is the
    // case where a number and a chip legitimately coexist — a filed zero is a real number —
    // so it is the case that has to hold the column's right edge.
    const zeroed = JSON.parse(JSON.stringify(productionEnvelope));
    zeroed.data.series.water_bbl_null_semantics[2] = "reported_zero";
    zeroed.data.series.water_bbl[2] = "0.000";
    overrides["/v1/wells/3305310451/production"] = zeroed;

    await mount("production", { extra: { "f.api10": ["3305310451"] } });
    const cells = [...host.querySelectorAll(".gw-grid-tr")].map(
      (row) => row.querySelectorAll(".gw-grid-td")[3] as HTMLElement,
    );

    expect(cells[2]?.querySelector(".gw-cell-marks .gw-state")).not.toBeNull();
    expect(cells[2]?.querySelector("gw-figure")).not.toBeNull();
    // Every row's figure is the value's first child, in the value track; the chip never is.
    for (const [index, cell] of cells.entries()) {
      expect(cell.querySelector(".gw-cell")?.firstElementChild?.tagName, String(index)).toBe(
        "GW-FIGURE",
      );
    }
  });

  it("puts the label in place of the number where the volume is a placeholder (F6)", async () => {
    // The recorded envelope reports every month; the withheld shape comes from the ledger's
    // separate withheld-months query, so it is injected here rather than waited for.
    const held = JSON.parse(JSON.stringify(productionEnvelope));
    held.data.series.water_bbl_null_semantics[5] = "withheld";
    held.data.series.water_bbl[5] = "0.000";
    overrides["/v1/wells/3305310451/production"] = held;

    await mount("production", { extra: { "f.api10": ["3305310451"] } });
    const withheld = host.querySelectorAll(".gw-grid-tr")[5]?.querySelectorAll(".gw-grid-td")[3];

    // The contract fixture seeds a real volume under a withheld label; the ingest cannot —
    // `classify_null_semantics` labels withheld only for a missing volume, which canonical
    // stores as zero. Either way the number is not one the system stands behind.
    expect(withheld?.querySelector("gw-figure")).toBeNull();
    expect(withheld?.querySelector(".gw-state")?.textContent).toContain("withheld");
    expect(withheld?.querySelector(".gw-state")?.getAttribute("title")).toMatch(/placeholder/);
  });

  it("lets prose absorb the width and keeps every other column at its content (F1)", async () => {
    await mount("sources");
    const table = host.querySelector(".gw-grid-table") as HTMLElement;

    // Cadence is the one prose column; identifiers, states, timestamps and the count retain
    // content width rather than being cut mid-glyph.
    expect(table.style.gridTemplateColumns).toBe(
      "max-content max-content max-content max-content max-content" +
        " minmax(8ch, max-content) max-content",
    );
  });

  it("puts a figure's header over its own data, not over the previous column's (F3)", async () => {
    await mount("production", { extra: { "f.api10": ["3305310451"] } });
    const heads = [...host.querySelectorAll(".gw-grid-th")];

    // One header per track: a figure's label occupies the value track alone and is aligned to
    // its right edge, so a plumb line from the header lands on its own numbers.
    expect(heads).toHaveLength(8);
    const oil = heads[1] as HTMLElement;
    expect(oil.className).toContain("gw-grid-th-figure");
    expect(oil.textContent).toContain("oil_bbl");
    expect((heads[2] as HTMLElement).className).toContain("gw-grid-th-spacer");
    expect((heads[2] as HTMLElement).textContent).toBe("");
    expect((heads[2] as HTMLElement).getAttribute("aria-hidden")).toBe("true");
  });

  it("carries the whole value in a title wherever a cell can ellipsize (F1)", async () => {
    const long = JSON.parse(JSON.stringify(healthEnvelope));
    long.data.sources[0].cadence = "Every thirty-five days after the prior completed source poll";
    overrides["/v1/health"] = long;
    await mount("sources");
    const prose = [...host.querySelectorAll(".gw-value-prose")].find((cell) =>
      cell.textContent?.startsWith("Every thirty-five days"),
    ) as HTMLElement;

    // The grid already teaches `…` on prose cells, so a reader reads an un-ellipsized value as
    // complete. Anything that can be shortened says what it was shortened from.
    expect(prose.title).toBe(prose.textContent);
    expect(prose.title.length).toBeGreaterThan(20);
  });

  it("states how many columns are off the right edge rather than cutting one mid-glyph", () => {
    // Layout is what decides this and happy-dom has none, so the sentence is a pure function
    // and the measurement that calls it is one line.
    expect(overflowNote(0)).toBeNull();
    expect(overflowNote(1)?.textContent).toMatch(
      /1 more column is off the right edge of this panel/,
    );
    expect(overflowNote(3)?.textContent).toMatch(/3 more columns are off/);
    expect(overflowNote(3)?.textContent).toMatch(/scroll the grid sideways/);
  });

  it("adds nothing to the table when a reason opens, so the off-edge count stays true (N1)", async () => {
    // `offScreenColumns` measures once, at mount. That is only sound if no later state can
    // change the table's box — and an in-flow reason inside a right-aligned cell did exactly
    // that: 148.6 px past the panel with the sentence still silent. The reason is now the
    // body's child, so the measurement has nothing to go stale against.
    await mount("quarantine");
    const table = host.querySelector(".gw-grid-table") as HTMLElement;
    const nodes = table.querySelectorAll("*").length;

    (table.querySelector(".gw-count-mark") as HTMLElement).click();

    expect(table.querySelectorAll("*").length).toBe(nodes);
    expect(table.querySelector(".gw-count-reason")).toBeNull();
    const popover = document.querySelector(".gw-count-reason") as HTMLElement;
    expect(popover.hidden).toBe(false);
    expect(popover.closest(".gw-grid-table")).toBeNull();
  });

  it("states an empty answer as an answer rather than as a blank rectangle", async () => {
    await mount("production", { extra: { "f.api10": ["3305300003"] } });

    expect(host.querySelectorAll(".gw-grid-tr")).toHaveLength(0);
    expect(host.textContent).toMatch(/no rows/);
    expect(host.textContent).toMatch(/an answer, not a failure/);
  });

  it("renders a problem as a problem when the API refuses the request", async () => {
    overrides["/v1/quarantine"] = undefined;
    vi.stubGlobal("fetch", () =>
      Promise.resolve(
        new Response(JSON.stringify({ type: "/v1/errors/bad", title: "Nope", status: 422 }), {
          status: 422,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    await mount("quarantine");

    expect(host.querySelector(".gw-grid-error")?.textContent).toMatch(/Nope \(422\)/);
  });

  it("shows a summary total where the dataset declares a summary operation", async () => {
    await mount("quarantine");

    expect(requested).toContain("/v1/quarantine/summary");
    expect(host.querySelector(".gw-page-count")?.textContent).toMatch(/3 rows matched/);
  });

  it("asks the summary only for filters it declares, never for a total over another set", async () => {
    // `get_quarantine_summary` declares source_id and state and not stage; FastAPI ignores an
    // undeclared query parameter, so forwarding `stage` returned a total over a broader
    // population and the count line quoted it. Found by the C7 visual pass, not by this test.
    await mount("quarantine", { extra: { "f.state": ["open"], "f.stage": ["conform"] } });

    expect(requested.some((url) => url.includes("/summary"))).toBe(false);
    expect(host.querySelector(".gw-page-count")?.textContent).not.toMatch(/rows matched/);

    requested = [];
    await mount("quarantine", { extra: { "f.state": ["open"] } });

    expect(requested).toContain("/v1/quarantine/summary?state=open");
  });

  it("windows a long page rather than putting a thousand rows in the DOM at once", async () => {
    const long = JSON.parse(JSON.stringify(wellsEnvelope));
    long.data = Array.from({ length: 140 }, (_, index) => ({
      ...(wellsEnvelope.data[0] as object),
      api10: `33053${String(index).padStart(5, "0")}`,
    }));
    overrides["/v1/wells"] = long;

    await mount("wells");
    expect(host.querySelectorAll(".gw-grid-tr")).toHaveLength(WINDOW);

    (host.querySelector(".gw-grid-more") as HTMLElement).click();
    expect(host.querySelectorAll(".gw-grid-tr")).toHaveLength(WINDOW * 2);

    (host.querySelector(".gw-grid-more") as HTMLElement).click();
    expect(host.querySelectorAll(".gw-grid-tr")).toHaveLength(140);
    expect((host.querySelector(".gw-grid-more") as HTMLElement).hidden).toBe(true);
  });

  it("abandons a response whose render was already superseded", async () => {
    const abort = new AbortController();
    abort.abort();
    await mountGrid(host, {
      dataset: dataset("quarantine"),
      document: SNAPSHOT,
      datasets: CATALOGUE.datasets,
      state: state(),
      facetHost,
      commit,
      signal: abort.signal,
    });

    expect(host.querySelectorAll(".gw-grid-tr")).toHaveLength(0);
  });

  it("follows the server's next link and puts the cursor it carried into the URL", async () => {
    overrides["/v1/quarantine"] = pagedQuarantineEnvelope;
    await mount("quarantine");

    (host.querySelector(".gw-page-next") as HTMLElement).click();

    const cursor = pagedQuarantineEnvelope.meta.next_cursor;
    expect(commit).toHaveBeenCalledWith({ extra: { cursor: [cursor] } });
  });
});

describe("every number on this surface handles through or states its exemption (§6.1 item 2)", () => {
  it("renders no numeric cell as bare text, across every dataset P-A serves", async () => {
    let numeric = 0;
    for (const [id, path] of Object.entries(DATASET_PATH)) {
      const anchored: Record<string, string[]> = {};
      if (path.includes("/wells/33")) anchored["f.api10"] = [path.split("/")[3] as string];
      await mount(id, { extra: anchored });

      const columns = columnsFor(dataset(id), SNAPSHOT, BY_PATH[path] as never);
      const indices = columns
        .map((column, index) => ({ column, index }))
        .filter(({ column }) => column.kind === "figure" || column.kind === "count");

      for (const row of host.querySelectorAll(".gw-grid-tr")) {
        const cells = row.querySelectorAll(".gw-grid-td");
        for (const { index, column } of indices) {
          const cell = cells[index] as HTMLElement;
          const figure = cell.querySelector("gw-figure");
          const count = cell.querySelector("gw-count");
          const absent = cell.querySelector(".gw-value-absent, .gw-state");
          expect(
            Boolean(figure ?? count ?? absent),
            `${id} ${column.pointer}: ${cell.textContent}`,
          ).toBe(true);
          if (figure) expect(figure.getAttribute("handle"), `${id} ${column.pointer}`).not.toBe("");
          if (count) {
            expect(
              count.hasAttribute("reason") || count.hasAttribute("no-reason"),
              `${id} ${column.pointer}`,
            ).toBe(true);
          }
          numeric += 1;
        }
      }
    }
    // A walk that met no numeric cell would pass the loop above without asserting anything —
    // which is this project's own named failure mode, so the floor is asserted too.
    expect(numeric).toBeGreaterThan(60);
  });

  it("classifies every schema-numeric column as a figure or a count, never as prose", async () => {
    let checked = 0;
    for (const [id, path] of Object.entries(DATASET_PATH)) {
      const columns = columnsFor(dataset(id), SNAPSHOT, BY_PATH[path] as never, {
        includeHidden: true,
      });
      for (const column of columns) {
        const schema = numericSchema(id, column.pointer, column.namespace);
        if (!schema) continue;
        expect(["figure", "count"], `${id} ${column.pointer}`).toContain(column.kind);
        checked += 1;
      }
    }
    expect(checked).toBeGreaterThan(5);
  });
});

type Node = Record<string, unknown>;

/** Read straight off the document, so the classifier cannot be graded against its own opinion. */
function numericSchema(id: string, pointer: string, namespace: string): boolean {
  if (namespace === "series") return false;
  const declaration = dataset(id);
  const operation = Object.values(SNAPSHOT.paths as Record<string, Node>)
    .flatMap((item) => Object.values(item as Node) as Node[])
    .find((candidate) => candidate["operationId"] === declaration.operationId);
  if (!operation) return false;

  let node = walk(operation, ["responses", "200", "content", "application/json", "schema"]);
  node = walk(node, ["properties", "data"]);
  for (const token of declaration.collection_pointer.split("/").filter(Boolean)) {
    node = walk(node, ["properties", token]);
  }
  const property = walk(node, ["properties", pointer.replace(/^\//, "")]);
  return property["type"] === "integer" || property["type"] === "number";
}

function walk(node: Node, keys: readonly string[]): Node {
  let current = deref(node);
  for (const key of keys) {
    const next = current[key];
    current = deref(typeof next === "object" && next !== null ? (next as Node) : {});
  }
  return current;
}

function deref(node: Node): Node {
  let current = node;
  while (typeof current["$ref"] === "string") {
    const name = (current["$ref"] as string).split("/").pop() as string;
    current = ((SNAPSHOT.components.schemas as Node)[name] ?? {}) as Node;
  }
  return current["type"] === "array" && typeof current["items"] === "object"
    ? deref(current["items"] as Node)
    : current;
}
