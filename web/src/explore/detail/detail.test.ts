// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_STATE, serializeState } from "../../app/state.ts";
import type { AppState } from "../../app/state.ts";
import { buildCatalogue } from "../catalogue.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import {
  derivationsEnvelope,
  healthEnvelope,
  productionEnvelope,
  quarantineEnvelope,
  vintagesEnvelope,
  wellsEnvelope,
} from "../fixtures.ts";
import { columnsFor } from "../grid/columns.ts";
import { extractRows } from "../grid/rows.ts";
import type { Row } from "../grid/rows.ts";
import { resetTrail } from "./chips.ts";
import { detailDatasetFor, mountDetail, setPointerLabels } from "./detail.ts";
import {
  conformanceRuleEnvelope,
  derivationEnvelope,
  glossaryTermEnvelope,
  manifestEnvelope,
  quarantineDetailEnvelope,
  vintageEnvelope,
  wellDetailEnvelope,
} from "./fixtures.ts";

const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8"));
const CATALOGUE = buildCatalogue(SNAPSHOT);
const QUARANTINE_ROW = quarantineDetailEnvelope.data.quarantine_id;
const CONFORMANCE_RULE = conformanceRuleEnvelope.data.rule_id;

const COLLECTION: Record<string, { path: string; envelope: unknown }> = {
  quarantine: { path: "/v1/quarantine", envelope: quarantineEnvelope },
  wells: { path: "/v1/wells", envelope: wellsEnvelope },
  sources: { path: "/v1/health", envelope: healthEnvelope },
  vintages: { path: "/v1/vintages", envelope: vintagesEnvelope },
  derivations: { path: "/v1/derivations", envelope: derivationsEnvelope },
  production: { path: "/v1/wells/3305310451/production", envelope: productionEnvelope },
};

const DETAIL: Record<string, unknown> = {
  [`/v1/quarantine/${QUARANTINE_ROW}`]: quarantineDetailEnvelope,
  [`/v1/conformance/${CONFORMANCE_RULE}`]: conformanceRuleEnvelope,
  "/v1/manifests/man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee": manifestEnvelope,
  "/v1/vintages/vin_nd_gis_wells_2026-08-01": vintageEnvelope,
  "/v1/wells/3305310451": wellDetailEnvelope,
  "/v1/glossary/gt_analog": glossaryTermEnvelope,
  "/v1/derivations/drv_obqajdni25f25zmxcz7a": derivationEnvelope,
};

// The spatial well is the one seeded with a lateral length, so it is the one with figures.
const WELL_ROW = 7;

let host: HTMLElement;
let requested: string[];
let overrides: Record<string, unknown>;

function dataset(id: string): CatalogueDataset {
  const found = CATALOGUE.datasets.find((candidate) => candidate.id === id);
  if (!found) throw new Error(`no dataset ${id}`);
  return found;
}

function state(over: Partial<AppState> = {}): AppState {
  return { ...DEFAULT_STATE, view: "explore", ...over };
}

interface Mounted {
  root: HTMLElement;
  keys: string[];
  valueOf(name: string): HTMLElement | null;
}

/** The grid's own columns and rows, built the way `mountGrid` builds them (M2, M3). */
function gridRow(id: string, index = 0): { row: Row; columns: ReturnType<typeof columnsFor>; data: unknown } {
  const envelope = COLLECTION[id]?.envelope as { data: unknown; meta: { labels: Record<string, string> } };
  const columns = columnsFor(dataset(id), SNAPSHOT, envelope, { includeHidden: true });
  const rows = extractRows(dataset(id), envelope.data, columns.map((column) => column.pointer));
  return { row: rows[index] as Row, columns, data: envelope.data };
}

async function mount(id: string, over: Partial<AppState> = {}, at = 0): Promise<Mounted> {
  const { row, columns, data } = gridRow(id, at);
  const rowId = over.row ?? row.id;
  await mountDetail(host, {
    dataset: dataset(id),
    document: SNAPSHOT,
    datasets: CATALOGUE.datasets,
    state: state({ ds: id, row: rowId, ...over }),
    row,
    rowId,
    columns,
    data,
    request: { path: COLLECTION[id]?.path as string, query: {} },
    navigate: vi.fn(),
    close: vi.fn(),
    signal: new AbortController().signal,
  });
  await new Promise((resolve) => setTimeout(resolve, 0));

  const root = host.querySelector(".gw-detail") as HTMLElement;
  const fields = [...root.querySelectorAll(".gw-detail-field")];
  return {
    root,
    keys: fields.map((field) => field.querySelector(".gw-detail-key")?.textContent?.trim() ?? ""),
    valueOf: (name) =>
      (fields
        .find((field) => (field.querySelector(".gw-label")?.textContent ?? "") === name)
        ?.querySelector(".gw-detail-value") as HTMLElement) ?? null,
  };
}

beforeEach(() => {
  requested = [];
  overrides = {};
  setPointerLabels(false);
  resetTrail();
  document.body.innerHTML = '<div id="host"></div>';
  host = document.getElementById("host") as HTMLElement;
  window.history.replaceState(null, "", "/?view=explore");
  vi.stubGlobal("fetch", (url: string) => {
    requested.push(String(url));
    const path = String(url).split("?")[0] as string;
    const body = path in overrides ? overrides[path] : DETAIL[path];
    if (body === undefined) return Promise.resolve(new Response("{}", { status: 404 }));
    return Promise.resolve(
      new Response(JSON.stringify(body), { headers: { "content-type": "application/json" } }),
    );
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("expanding a row calls the dataset's detail operation (8.1)", () => {
  it("renders the fuller record, which is the reason a detail endpoint exists", async () => {
    const detail = await mount("quarantine");

    expect(requested).toEqual([`/v1/quarantine/${QUARANTINE_ROW}`]);
    expect(detail.root.textContent).toContain("get_quarantine_row");
    // The collection serves seven columns and two hidden; the record carries eighteen fields.
    expect(detail.keys.length).toBeGreaterThan((dataset("quarantine").columns.default ?? []).length);
    expect(detail.valueOf("row_payload")).not.toBe(null);
    expect(detail.valueOf("first_seen_manifest_id")).not.toBe(null);
  });

  it("says so, and renders the row's own fields, where no detail operation is declared", async () => {
    const detail = await mount("sources");

    expect(requested).toEqual([]);
    expect(detail.root.textContent).toContain("declares no detail operation");
    expect(detail.keys.length).toBeGreaterThan(0);
  });

  it("lists what the grid hides, with the reason it was hidden rather than in silence", () => {
    // Read before the await: the collection's own fields are the first frame, and they are the
    // only frame that can carry a `hidden_reason` — the record's schema does not declare one.
    const { row, columns, data } = gridRow("quarantine");
    void mountDetail(host, {
      dataset: dataset("quarantine"),
      document: SNAPSHOT,
      datasets: CATALOGUE.datasets,
      state: state({ ds: "quarantine", row: row.id }),
      row,
      rowId: row.id,
      columns,
      data,
      request: { path: "/v1/quarantine", query: {} },
      navigate: vi.fn(),
      close: vi.fn(),
      signal: new AbortController().signal,
    });

    const keys = [...host.querySelectorAll(".gw-detail-key")].map((key) => key.textContent ?? "");
    const reasons = [...host.querySelectorAll(".gw-detail-hidden")].map((one) => (one as HTMLElement).title);
    expect(keys.some((key) => key.includes("row_fingerprint"))).toBe(true);
    expect(reasons).toHaveLength(dataset("quarantine").columns.hidden.length);
    expect(reasons[0]).toContain("content address");
  });

  it("keeps a sidecar out of the field list: `_lineage` is how a figure carries its handle", async () => {
    const detail = await mount("vintages");

    expect(detail.keys.some((key) => key.includes("_lineage"))).toBe(false);
    expect(detail.valueOf("rows_appended")).not.toBe(null);
  });

  it("does not print the envelope's own navigation, and says where it reads instead", async () => {
    const detail = await mount("wells", {}, WELL_ROW);

    expect(detail.valueOf("links")).toBe(null);
    expect(detail.root.textContent).toContain("the API guide renders the envelope's navigation");
  });
});

describe("the field list is the grid's column kinds, read vertically (§3.4)", () => {
  it("renders a figure as a figure, handle and all, even behind a nullable schema", async () => {
    const detail = await mount("wells", {}, WELL_ROW);
    const figure = detail.valueOf("lateral_length_ft")?.querySelector("gw-figure");

    expect(figure).not.toBe(null);
    expect(figure?.getAttribute("handle")).not.toBe("");
    expect(figure?.getAttribute("unit")).toBe("ft");
  });

  it("keeps the handle on a counted number the API has not given a unit (D6)", async () => {
    const detail = await mount("vintages");
    const count = detail.valueOf("rows_appended")?.querySelector("gw-count");

    expect(count?.getAttribute("data-handle")).toMatch(/^drv_/);
  });

  it("renders a placeholder volume as its label and not as a zero (F6)", async () => {
    const { row, columns, data } = gridRow("production", 0);
    const withheld = Object.values(row.cells).some(
      (cell) => cell.companions["_null_semantics"] === "withheld",
    );
    await mountDetail(host, {
      dataset: dataset("production"),
      document: SNAPSHOT,
      datasets: CATALOGUE.datasets,
      state: state({ ds: "production", row: row.id }),
      row,
      rowId: row.id,
      columns,
      data,
      request: { path: "/v1/wells/3305310451/production", query: {} },
      navigate: vi.fn(),
      close: vi.fn(),
      signal: new AbortController().signal,
    });

    const marks = [...host.querySelectorAll(".gw-detail-value .gw-state")].map(
      (chip) => (chip as HTMLElement).dataset["state"],
    );
    expect(withheld).toBe(marks.includes("withheld"));
    for (const value of host.querySelectorAll(".gw-detail-value")) {
      if (value.querySelector('.gw-state[data-state="withheld"]')) {
        expect(value.querySelector("gw-figure")).toBe(null);
      }
    }
  });
});

describe("pointer labels are off by default and stay out of the URL (§3.4, m9)", () => {
  it("is off in the module as loaded, not merely off after a test reset it", async () => {
    vi.resetModules();
    const fresh = (await import("./detail.ts")) as typeof import("./detail.ts");

    expect(fresh.pointerLabels()).toBe(false);
  });

  it("renders every pointer and hides them until the reader asks", async () => {
    const detail = await mount("quarantine");

    expect(detail.root.dataset["pointers"]).toBe("off");
    expect(detail.root.querySelectorAll(".gw-detail-pointer").length).toBeGreaterThan(5);
  });

  it("turns them on without touching what a shared link teaches", async () => {
    const before = window.location.search;
    const detail = await mount("quarantine");
    const toggle = detail.root.querySelector(".gw-detail-pointers") as HTMLElement;
    toggle.click();

    expect(detail.root.dataset["pointers"]).toBe("on");
    expect(toggle.getAttribute("aria-pressed")).toBe("true");
    expect(window.location.search).toBe(before);
    expect(serializeState(state({ ds: "quarantine" }))).not.toContain("pointer");
  });
});

describe("a verbatim source row renders as JSON, and claims nothing about it (§3.7)", () => {
  it("carries the standing caption, word for word", async () => {
    const detail = await mount("quarantine");
    const payload = detail.valueOf("row_payload") as HTMLElement;

    expect(payload.querySelector(".gw-json-block")?.textContent).toContain("GasSold");
    expect(payload.querySelector(".gw-json-caption")?.textContent).toBe(
      "this is the source row as it arrived, not a number the system stands behind",
    );
  });

  it("highlights nothing when the response does not name which field offended", async () => {
    const detail = await mount("quarantine");
    const payload = detail.valueOf("row_payload") as HTMLElement;

    expect(payload.querySelectorAll(".gw-json-offender")).toHaveLength(0);
    expect(payload.textContent).toContain("does not name which field was refused");
  });

  it("highlights the key when the record does name it — the shape the schema permits", async () => {
    // `applies_to_fields` names a column, and `get_quarantine_row` may carry one too; this seed
    // does not, so the arm injects the response the schema allows rather than asserting a rule
    // no fixture can reach (C7's §3 lesson).
    const named = structuredClone(quarantineDetailEnvelope) as { data: Record<string, unknown> };
    named.data["notes"] = "stream_raw";
    overrides[`/v1/quarantine/${QUARANTINE_ROW}`] = named;
    const detail = await mount("quarantine");
    const payload = detail.valueOf("row_payload") as HTMLElement;

    const offenders = [...payload.querySelectorAll(".gw-json-offender")].map(
      (line) => line.textContent ?? "",
    );
    expect(offenders).toHaveLength(1);
    expect(offenders[0]).toContain("stream_raw");
    expect(payload.textContent).not.toContain("does not name which field was refused");
  });
});

describe("every id in the record is a hop, or says why it is not (§3.3)", () => {
  it("puts a chip on the rule the row cites, carrying the filter into its dataset", async () => {
    const detail = await mount("quarantine");
    const chips = detail.valueOf("rule_id")?.querySelectorAll(".gw-join-chip") ?? [];

    expect(chips.length).toBeGreaterThan(0);
    expect((chips[0] as HTMLElement).dataset["target"]).toBe("conformance");
    expect((chips[0] as HTMLAnchorElement).getAttribute("href")).toContain("ds=conformance");
    expect((chips[0] as HTMLAnchorElement).getAttribute("href")).toContain(
      `row=${CONFORMANCE_RULE}`,
    );
  });

  it("offers the collections a source_id narrows as filtered hops", async () => {
    const detail = await mount("quarantine");
    const chips = [...(detail.valueOf("source_id")?.querySelectorAll(".gw-join-chip") ?? [])];

    const filtered = chips.filter((chip) => (chip as HTMLElement).dataset["hop"] === "filtered");
    expect(filtered.length).toBeGreaterThan(0);
    for (const chip of filtered) {
      expect((chip as HTMLAnchorElement).getAttribute("href")).toContain("f.source_id=");
    }
  });

  it("puts no chip on the row's own identity, which is where the reader already is", async () => {
    const detail = await mount("quarantine");
    const own = detail.valueOf("quarantine_id") as HTMLElement;

    expect(own.querySelectorAll(".gw-join-chip")).toHaveLength(0);
  });

  it("states the gap where no operation reads the id (8.2's inert case)", async () => {
    // `env_id` is an id the document serves nowhere, which is §3.3's first property arriving on
    // real data rather than on a field invented to fail — `land_unit_id` is the same shape and
    // is asserted against the derivation directly in chips.test.ts.
    const detail = await mount("derivations", {}, 1);
    const chips = [...(detail.valueOf("env_id")?.querySelectorAll(".gw-join-chip") ?? [])];

    expect(chips).toHaveLength(1);
    expect((chips[0] as HTMLElement).dataset["hop"]).toBe("inert");
    expect(chips[0]?.tagName).not.toBe("A");
  });
});

describe("the detail operation is read as a dataset of one", () => {
  it("drops the pivot, the anchors and the collection pointer the list form needed", () => {
    const detail = detailDatasetFor(dataset("wells"), SNAPSHOT) as CatalogueDataset;

    expect(detail.operationId).toBe("get_well");
    expect(detail.path).toBe("/v1/wells/{api10}");
    expect(detail.collection_pointer).toBe("");
    expect(detail.columns.default).toBe(undefined);
  });

  it("is null where the dataset declares none, which is how the panel knows to say so", () => {
    expect(detailDatasetFor(dataset("sources"), SNAPSHOT)).toBe(null);
    expect(detailDatasetFor(dataset("production"), SNAPSHOT)).toBe(null);
  });

  it("puts as_of on the wire only where the operation declares it", async () => {
    await mount("wells", { extra: { as_of: ["2026-08-01"] } }, WELL_ROW);
    expect(requested).toEqual(["/v1/wells/3305310451?as_of=2026-08-01"]);

    requested.length = 0;
    await mount("vintages", { extra: { as_of: ["2026-08-01"] } });
    expect(requested).toEqual(["/v1/vintages/vin_nd_gis_wells_2026-08-01"]);
  });

  it("keeps the collection's fields and says why, when the detail request fails", async () => {
    overrides[`/v1/quarantine/${QUARANTINE_ROW}`] = undefined;
    const detail = await mount("quarantine");

    expect(detail.root.textContent).toContain("did not answer");
    expect(detail.keys.length).toBeGreaterThan(0);
  });
});

/**
 * SB-08 §2.6's one explorer-to-map row. `cells.ts` refuses to print a coordinate, so the
 * crossing is what the cell offers instead of a value — never a control competing with one.
 */
describe("a record with geometry crosses to the map", () => {
  const located = (over: Record<string, unknown> = {}) => {
    const source = wellDetailEnvelope as { data: Record<string, unknown>; meta: unknown };
    return {
      ...source,
      data: { ...source.data, surface_point: { lon: -102.8123, lat: 47.8456 }, ...over },
    };
  };

  const linkIn = (detail: { root: HTMLElement }) =>
    detail.root.querySelector<HTMLAnchorElement>('[data-crossing="show-on-map"]');

  it("offers the crossing on the geometry field, carrying the well and the viewport", async () => {
    overrides["/v1/wells/3305310451"] = located();
    const link = linkIn(await mount("wells", { row: "3305310451" }, WELL_ROW));

    expect(link?.textContent).toBe("Show on map");
    expect(link?.getAttribute("href")).toContain("well=3305310451");
    expect(link?.getAttribute("href")).toContain("map=12.00%2F47.84560%2F-102.81230");
  });

  it("pins the vintage the record resolved at, so the shared link reproduces it (M6)", async () => {
    overrides["/v1/wells/3305310451"] = located();
    const link = linkIn(await mount("wells", { row: "3305310451" }, WELL_ROW));

    // The crossing names the recorded resolved vintage rather than leaving the map to resolve
    // `latest` again on whatever day the link is opened.
    expect(link?.getAttribute("href")).toContain(
      `as_of=${wellDetailEnvelope.meta.as_of.resolved}`,
    );
  });

  it("offers nothing when the point is present but not a pair of numbers", async () => {
    // A shape drift, not an absence: the field is there and the coordinates are not usable.
    // A crossing built from this would fly the reader to null island and call it the well.
    overrides["/v1/wells/3305310451"] = located({ surface_point: { lon: "x", lat: null } });

    expect(linkIn(await mount("wells", { row: "3305310451" }, WELL_ROW))).toBeNull();
  });

  it("offers nothing when the regulator filed no surface point, and states the absence", async () => {
    // The recorded record: `surface_point` is null, which is the common case in this vintage.
    const detail = await mount("wells", { row: "3305310451" }, WELL_ROW);

    expect(linkIn(detail)).toBeNull();
    expect(detail.valueOf("surface_point")?.textContent).toContain("—");
  });

  it("leaves the geometry value unprinted either way — a coordinate is never a cell (§3.2)", async () => {
    overrides["/v1/wells/3305310451"] = located();
    const detail = await mount("wells", { row: "3305310451" }, WELL_ROW);

    expect(detail.valueOf("surface_point")?.textContent).toContain("on the map");
    expect(detail.valueOf("surface_point")?.textContent).not.toContain("-102.81");
  });
});
