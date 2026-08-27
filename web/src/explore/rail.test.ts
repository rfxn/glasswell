// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { DATASET_GROUPS, buildCatalogue } from "./catalogue.ts";
import { CLASS_B_DATASETS, CLASS_C_DATASETS, GROUP_TITLES, renderRail } from "./rail.ts";

const SNAPSHOT = JSON.parse(
  readFileSync("../tests/contract/openapi_snapshot.json", "utf8"),
) as { paths: Record<string, Record<string, unknown>> };

const catalogue = buildCatalogue(SNAPSHOT);
let host: HTMLElement;

beforeEach(() => {
  document.body.innerHTML = "";
  host = document.createElement("nav");
  document.body.appendChild(host);
});

function gapSection(): HTMLElement {
  return host.querySelector(".gw-explore-rail-gaps") as HTMLElement;
}

describe("class A — the rail is the document, grouped and ordered", () => {
  it("renders every group the catalogue populates, in the fixed order", () => {
    renderRail(host, { catalogue, selected: null, onSelect: vi.fn() });

    const headings = [...host.querySelectorAll(".gw-explore-rail-group > h3")].map(
      (heading) => heading.textContent,
    );
    expect(headings.slice(0, catalogue.groups.length)).toEqual(
      catalogue.groups.map((group) => GROUP_TITLES[group.id]),
    );
    for (const group of DATASET_GROUPS) expect(GROUP_TITLES[group]).toBeTruthy();
  });

  it("renders one control per dataset and reports the id it was given", () => {
    const onSelect = vi.fn();
    renderRail(host, { catalogue, selected: null, onSelect });
    const controls = [...host.querySelectorAll("button[data-ds]")];

    expect(controls).toHaveLength(catalogue.datasets.length);
    (controls[0] as HTMLButtonElement).click();

    expect(onSelect).toHaveBeenCalledWith(catalogue.datasets[0]?.id);
  });

  it("marks the selected dataset for a screen reader, not only with colour", () => {
    const selected = catalogue.datasets[1]?.id ?? null;

    renderRail(host, { catalogue, selected, onSelect: vi.fn() });

    const current = [...host.querySelectorAll('button[aria-current="page"]')];
    expect(current).toHaveLength(1);
    expect(current[0]?.getAttribute("data-ds")).toBe(selected);
  });

  it("states that it could not read the document rather than rendering an empty rail", () => {
    renderRail(host, { catalogue: null, selected: null, onSelect: vi.fn() });

    expect(host.querySelector(".gw-explore-rail-degraded")?.textContent).toMatch(/openapi\.json/);
    expect(host.querySelectorAll("button[data-ds]")).toHaveLength(0);
  });
});

describe("class B — the honest-gap register is navigable, and implies nothing (§2.4, §6.5)", () => {
  it("holds twenty entries in one exported const", () => {
    // Completions and formations moved into the generated catalogue. The register is curated,
    // not derived: a silent deletion is a gap the product stops admitting to, so the number is
    // asserted rather than measured.
    expect(CLASS_B_DATASETS).toHaveLength(20);
    expect(new Set(CLASS_B_DATASETS.map((entry) => entry.title)).size).toBe(20);
  });

  it("names an operation that genuinely does not exist — that is what makes it class B", () => {
    // The day P3 lands GET /v1/models this goes red, and the entry has to move into the
    // generated rail where it belongs. That is §2.3's promise enforced from the other side.
    for (const entry of CLASS_B_DATASETS) {
      expect(Object.keys(SNAPSHOT.paths), entry.title).not.toContain(entry.path);
    }
  });

  it("cites the SB-04 §4 row every path came from", () => {
    for (const entry of CLASS_B_DATASETS) {
      expect(entry.section, entry.title).toMatch(/^SB-04 §4\.\d+$/);
      expect(entry.path).toMatch(/^\/v1\//);
    }
  });

  it("renders each entry greyed, with the operation it will be", () => {
    renderRail(host, { catalogue, selected: null, onSelect: vi.fn() });
    const entries = [...gapSection().querySelectorAll("[data-gap]")];

    expect(entries).toHaveLength(CLASS_B_DATASETS.length + CLASS_C_DATASETS.length);
    for (const entry of entries) expect(entry.getAttribute("aria-disabled")).toBe("true");
    expect(gapSection().textContent).toContain("/v1/models");
  });

  it("renders no link, no control and no count — §6.5 forbids implying content", () => {
    renderRail(host, { catalogue, selected: null, onSelect: vi.fn() });
    const gaps = gapSection();

    expect(gaps.querySelectorAll("a")).toHaveLength(0);
    expect(gaps.querySelectorAll("button")).toHaveLength(0);
    expect(gaps.querySelectorAll("gw-figure, gw-count")).toHaveLength(0);
    expect(gaps.textContent).not.toMatch(/\b\d{1,3}(,\d{3})+\b|\b\d+\s+rows?\b/);
  });

  it("states a phase where SB-08 §2.4 states one and invents none where it does not", () => {
    const phased = CLASS_B_DATASETS.filter((entry) => entry.phase !== null);

    expect(phased.map((entry) => entry.title).sort()).toEqual([
      "Forecasts",
      "Models",
      "Operators",
      "Scorecard",
    ]);
    for (const entry of phased) expect(entry.phase).toMatch(/^P\d$/);
  });
});

describe("class C — exactly one, and it names the amendment that would land it", () => {
  it("is cross-well production and nothing else", () => {
    expect(CLASS_C_DATASETS).toHaveLength(1);
    expect(CLASS_C_DATASETS[0]?.title).toBe("Production across wells");
    expect(CLASS_C_DATASETS[0]?.amendment).toBe("A-3");
    expect(CLASS_C_DATASETS[0]?.status).toBeTruthy();
  });

  it("renders the amendment and its status where the reader can see the gap", () => {
    renderRail(host, { catalogue, selected: null, onSelect: vi.fn() });

    const rendered = gapSection().querySelector('[data-gap="class-c"]') as HTMLElement;
    expect(rendered.textContent).toContain("A-3");
    expect(rendered.textContent).toContain(CLASS_C_DATASETS[0]?.status);
  });

  it("proposes an operation the document does not serve", () => {
    expect(Object.keys(SNAPSHOT.paths)).not.toContain(CLASS_C_DATASETS[0]?.path);
  });
});
