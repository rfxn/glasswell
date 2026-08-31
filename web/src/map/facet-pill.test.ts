// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { EXPLAIN_EVENT } from "../chrome/handle.ts";
import { createFacetPill } from "./facet-pill.ts";
import { TILE_THIN_MAX_ZOOM, TILE_THIN_PIXELS } from "./style.ts";

const PICK = {
  dimension: "operator",
  value: "HESS CORP",
  wells: { value: "3412", unit: "wells", d: "drv_test#col=wells&operator=HESS+CORP" },
};

const text = (root: HTMLElement, selector: string): string =>
  root.querySelector<HTMLElement>(selector)?.textContent ?? "";
const shown = (element: HTMLElement | null): boolean =>
  element !== null && element.hidden === false && !element.hasAttribute("hidden");

describe("the pill that says what the canvas is narrowed to", () => {
  let pill: ReturnType<typeof createFacetPill>;
  let cleared: number;
  let opened: number;

  beforeEach(() => {
    cleared = 0;
    opened = 0;
    pill = createFacetPill({
      onClear: () => void (cleared += 1),
      onOpen: () => void (opened += 1),
    });
  });

  it("says nothing at all while nothing is pressed", () => {
    expect(shown(pill.element)).toBe(false);
    pill.set(PICK);
    expect(shown(pill.element)).toBe(true);
    pill.set(null);
    expect(shown(pill.element)).toBe(false);
  });

  it("names the dimension and the value the reader pressed", () => {
    pill.set(PICK);

    expect(text(pill.element, ".gw-facet-pill-label")).toContain("operator");
    expect(text(pill.element, ".gw-facet-pill-label")).toContain("HESS CORP");
  });

  it("carries the panel's own figure and its handle, never a count of the canvas", () => {
    // The canvas is a sample below zoom 8 and a viewport above it; a number taken from it would
    // move with the map while claiming to be the bucket's count.
    pill.set(PICK);
    const handle = pill.element.querySelector<HTMLButtonElement>(".gw-handle");

    expect(text(pill.element, ".gw-facet-pill-count")).toBe("3,412");
    expect(handle?.dataset["handle"]).toBe(PICK.wells.d);

    const seen: string[] = [];
    pill.element.addEventListener(EXPLAIN_EVENT, (event) =>
      seen.push((event as CustomEvent<{ handle: string }>).detail.handle),
    );
    handle?.click();
    expect(seen).toEqual([PICK.wells.d]);
  });

  it("shows the value with no number where the panel has served none", () => {
    // A shared link restores the press before the panel has answered. The pill states the press
    // and refuses the figure rather than counting the canvas to fill the space.
    pill.set({ ...PICK, wells: null });

    expect(text(pill.element, ".gw-facet-pill-count")).toBe("");
    expect(pill.element.querySelector<HTMLButtonElement>(".gw-handle")?.hidden).toBe(true);
  });

  it("names the layers a press on this dimension leaves unfiltered, and only when it does", () => {
    pill.set(PICK);
    expect(shown(pill.element.querySelector<HTMLElement>(".gw-facet-pill-partial"))).toBe(false);

    // No line layer publishes well_type_reported, so the dots narrow and the bores do not.
    pill.set({ ...PICK, dimension: "well_type", value: "SWD" });
    const partial = pill.element.querySelector<HTMLElement>(".gw-facet-pill-partial");
    expect(shown(partial)).toBe(true);
    expect(partial?.textContent).toContain("Laterals");
    expect(partial?.textContent).toMatch(/not filtered/i);
  });

  it("says the map is a sample only at the zooms where the tiles thin it", () => {
    pill.set(PICK);
    pill.setZoom(TILE_THIN_MAX_ZOOM + 1);
    expect(shown(pill.element.querySelector<HTMLElement>(".gw-facet-pill-thin"))).toBe(false);

    pill.setZoom(TILE_THIN_MAX_ZOOM);
    const thin = pill.element.querySelector<HTMLElement>(".gw-facet-pill-thin");
    expect(shown(thin)).toBe(true);
    expect(thin?.textContent).toContain(`below zoom ${TILE_THIN_MAX_ZOOM + 1}`);
    expect(thin?.textContent).toContain("half pixel");
  });

  it("un-presses from the pill, because the sheet may be shut", () => {
    pill.set(PICK);
    pill.element.querySelector<HTMLButtonElement>(".gw-facet-pill-x")?.click();

    expect(cleared).toBe(1);
  });

  it("opens the panel the press came from", () => {
    pill.set(PICK);
    pill.element.querySelector<HTMLButtonElement>(".gw-facet-pill-open")?.click();

    expect(opened).toBe(1);
  });
});

describe("the thinning constants the pill states", () => {
  it("are marts/tiles.py's own, not a second copy of them", () => {
    // The rate has never been on screen anywhere in this app. Stating it from a copy would put
    // a number in front of a reader that the tile server had already moved away from.
    const source = readFileSync("../src/glasswell/marts/tiles.py", "utf8");

    expect(/^THIN_MAX_ZOOM = (\d+)$/m.exec(source)?.[1]).toBe(String(TILE_THIN_MAX_ZOOM));
    expect(/^THIN_PIXELS = ([\d.]+)$/m.exec(source)?.[1]).toBe(String(TILE_THIN_PIXELS));
  });
});

describe("the pill's own frame", () => {
  it("is a strip the map chrome can hold, declared once in map.css", () => {
    const css = readFileSync("src/map.css", "utf8");
    expect(css).toContain(".gw-facet-pill");
    expect(/\.gw-facet-pill\[hidden\]\s*\{[^}]*display:\s*none/.test(css)).toBe(true);
  });
});

vi.mock("../chrome/status.ts", () => ({ toast: vi.fn() }));
