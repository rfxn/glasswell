// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";

import { EXPLAIN_EVENT } from "../chrome/handle.ts";
import { createHoverCard, placeCard } from "./hover-card.ts";
import { createTileBanner } from "./tile-banner.ts";

describe("the hover card", () => {
  it("shows only what the tile already carries — identity, never a fetch", () => {
    const card = createHoverCard();
    card.show({ api10: "3305305527", well_name: "BAKKEN 14-23H", status_canonical: "active" }, {
      x: 40,
      y: 60,
    });
    expect(card.element.hidden).toBe(false);
    expect(card.element.textContent).toContain("BAKKEN 14-23H");
    expect(card.element.textContent).toContain("3305305527");
    expect(card.element.textContent).toContain("Active");
  });

  it("falls back to the api10 when the tile has no name, and states it once", () => {
    const card = createHoverCard();
    card.show({ api10: "3305305527", status_canonical: "active" }, { x: 0, y: 0 });
    expect(card.element.textContent).toContain("3305305527");
    expect(card.element.textContent?.match(/3305305527/g)?.length).toBe(1);
  });

  it("reads a land-grid cell as figures with their basis and support, never naked (M2-3)", () => {
    const card = createHoverCard();
    card.show(
      {
        land_unit_id: "ND051520N0950W0SN130",
        unit_type: "section",
        label: "13",
        well_count: 1,
        prod_well_count: 1,
        liquid_cum_bbl: 1500,
        gas_cum_mcf: 3000,
        water_cum_bbl: 0,
        liquid_bin: 6,
        derivation_id: "drv_thematics",
      },
      { x: 10, y: 10 },
    );
    const text = card.element.textContent ?? "";
    expect(text).toContain("Section 13");
    expect(text).toContain("1 wells · 1 producing");
    expect(text).toContain("Liquid 1,500 bbl");
    expect(text).toContain("gas 3,000 mcf");
    expect(text).toContain("observed sums");
    expect(text).toContain("oil + condensate as ND files it");
    expect(text).toContain("cr_land_agg_membership_1");
  });

  it("clears the cell figures when the next hover is a well again", () => {
    const card = createHoverCard();
    card.show(
      { land_unit_id: "x", unit_type: "township", label: "152N 95W", well_count: 2,
        prod_well_count: 2, liquid_cum_bbl: 1700, gas_cum_mcf: 3000, water_cum_bbl: 100 },
      { x: 0, y: 0 },
    );
    card.show({ api10: "3305305527", status_canonical: "active" }, { x: 0, y: 0 });
    const text = card.element.textContent ?? "";
    expect(text).not.toContain("Liquid");
    expect(text).not.toContain("cr_land_agg_membership_1");
    expect(text).toContain("3305305527");
  });

  it("hides when nothing is under the cursor", () => {
    const card = createHoverCard();
    card.show({ api10: "33053" }, { x: 0, y: 0 });
    card.hide();
    expect(card.element.hidden).toBe(true);
  });

  it("states the wellhead's provenance-of-record at hover, the class verbatim", () => {
    // M1-3: provenance in the default tooltip, unasked — the class as the wire serves it,
    // never a decode into "surveyed"/"actual" the register has not asserted.
    const card = createHoverCard();
    card.show(
      { api10: "3305305527", status_canonical: "active", geometry_provenance: "surface" },
      { x: 0, y: 0 },
    );
    expect(card.element.textContent).toContain("Surface location as ND DMR filed it");
    expect(card.element.textContent).toContain("geometry_provenance surface");
    expect(card.element.textContent?.toLowerCase()).not.toContain("surveyed");
  });

  it("gives the lateral's caveat a machine-readable backing — the wire class, not a caption", () => {
    const card = createHoverCard();
    card.show(
      { api10: "3305305527", status_canonical: "active", geometry_provenance: "lateral" },
      { x: 0, y: 0 },
    );
    expect(card.element.textContent).toContain("not a directional survey trace");
    expect(card.element.textContent).toContain("geometry_provenance lateral");
    expect(card.element.textContent).not.toContain("Survey trace ·");
  });

  it("stays silent on provenance for a feature that serves none — Texas, until RF-1", () => {
    const card = createHoverCard();
    card.show({ api10: "4231733333", status_canonical: "plugged" }, { x: 0, y: 0 });
    expect(card.element.textContent).not.toContain("geometry_provenance");
    // Cleared, not just hidden, when the pointer moves off an ND feature onto a TX one.
    card.show(
      { api10: "3305305527", status_canonical: "active", geometry_provenance: "surface" },
      { x: 0, y: 0 },
    );
    card.show({ api10: "4231733333", status_canonical: "plugged" }, { x: 0, y: 0 });
    expect(card.element.textContent).not.toContain("geometry_provenance");
  });

  it("keeps the trace hover as the trace's own provenance line, not two sentences", () => {
    const card = createHoverCard();
    card.show(
      {
        api10: "3305305527",
        status_canonical: "active",
        geometry_provenance: "survey_trace",
        station_count: 82,
        deepest_station_md_ft: 21_340.5,
      },
      { x: 0, y: 0 },
    );
    expect(card.element.textContent).toContain("Survey trace");
    expect(card.element.textContent).not.toContain("geometry_provenance survey_trace");
  });

  it("identifies a survey trace by what ND filed — stations and measured depth, never a length", () => {
    const card = createHoverCard();
    card.show(
      {
        api10: "3305305527",
        status_canonical: "active",
        geometry_provenance: "survey_trace",
        station_count: 82,
        deepest_station_md_ft: 21_340.5,
      },
      { x: 0, y: 0 },
    );
    expect(card.element.textContent).toContain("Survey trace");
    expect(card.element.textContent).toContain("82 stations");
    // Measured depth is what the source filed; a "length" over the plan view would be
    // horizontal travel presented as hole length (m15d-status §7 obligation 3).
    expect(card.element.textContent).toContain("deepest station 21,341 ft MD");
    expect(card.element.textContent?.toLowerCase()).not.toContain("length");
  });

  it("reads the trace facts in the wire types martin serves, string or number alike", () => {
    // Postgres numeric reaches the MVT as a string (see LATERAL_LENGTH in style.ts).
    const card = createHoverCard();
    card.show(
      {
        api10: "3305305527",
        geometry_provenance: "survey_trace",
        station_count: "82",
        deepest_station_md_ft: "21340.5",
      },
      { x: 0, y: 0 },
    );
    expect(card.element.textContent).toContain("82 stations");
    expect(card.element.textContent).toContain("21,341 ft MD");
  });

  it("drops the trace line the moment the cursor moves onto a well or lateral", () => {
    const card = createHoverCard();
    card.show(
      { api10: "x", geometry_provenance: "survey_trace", station_count: 5, deepest_station_md_ft: 100 },
      { x: 0, y: 0 },
    );
    card.show({ api10: "3305305527", status_canonical: "active" }, { x: 0, y: 0 });
    expect(card.element.textContent).not.toContain("Survey trace");
  });

  it("states the disposal class from the code as ND filed it, never an English decode", () => {
    const card = createHoverCard();
    card.show(
      { api10: "3305305527", status_canonical: "active", well_type_reported: "SWD" },
      { x: 0, y: 0 },
    );
    expect(card.element.textContent).toContain("Disposal / injection");
    expect(card.element.textContent).toContain("well_type SWD as ND filed it");
    // Which words SWD abbreviates is the regulator's footnote to own (cr_nd_well_type_disposal_1).
    expect(card.element.textContent?.toLowerCase()).not.toContain("saltwater");
  });

  it("says nothing about disposal for a well typed outside the class, OG included", () => {
    const card = createHoverCard();
    card.show(
      { api10: "3305305527", status_canonical: "active", well_type_reported: "OG" },
      { x: 0, y: 0 },
    );
    expect(card.element.textContent).not.toContain("Disposal");
    card.show({ api10: "3305305527", status_canonical: "active" }, { x: 0, y: 0 });
    expect(card.element.textContent).not.toContain("Disposal");
  });

  it("drops the disposal line the moment the cursor moves onto an OG well", () => {
    const card = createHoverCard();
    card.show({ api10: "a", well_type_reported: "WI" }, { x: 0, y: 0 });
    expect(card.element.textContent).toContain("well_type WI");
    card.show({ api10: "b", well_type_reported: "OG" }, { x: 0, y: 0 });
    expect(card.element.textContent).not.toContain("well_type WI");
  });

  it("names a status the vocabulary does not cover instead of leaving it blank", () => {
    const card = createHoverCard();
    card.show({ api10: "33053", status_canonical: "brand_new_code" }, { x: 0, y: 0 });
    expect(card.element.textContent).toMatch(/unmapped/i);
  });

  it("carries the cell figures' own ⌾, raising the one event the drawer opens on", () => {
    // gate-m23 cycle-1 item 8: a cropped screenshot of the card keeps the affordance.
    const card = createHoverCard();
    card.show(
      { land_unit_id: "x", unit_type: "section", label: "2", well_count: 1,
        prod_well_count: 1, liquid_cum_bbl: 10, gas_cum_mcf: 0, water_cum_bbl: 0,
        derivation_id: "drv_thematics" },
      { x: 0, y: 0 },
    );
    const handle = card.element.querySelector<HTMLButtonElement>(".gw-hover-handle")!;
    expect(handle.hidden).toBe(false);
    // The name says which figure it explains; the derivation id is machine detail and rides
    // the title, so a screen reader is not read an opaque handle string.
    expect(handle.getAttribute("aria-label")).toBe("Lineage for these cell figures");
    expect(handle.title).toContain("drv_thematics");
    // The live ⌾ is why the cell card alone takes the pointer (map.css pairs with this).
    expect(card.element.classList.contains("gw-hover-cell")).toBe(true);
    const seen = vi.fn();
    card.element.addEventListener(EXPLAIN_EVENT, (event) =>
      seen((event as CustomEvent).detail.handle),
    );
    handle.click();
    expect(seen).toHaveBeenCalledWith("drv_thematics");
  });

  it("hides the ⌾ for a cell whose tile carries no handle, rather than raising nothing", () => {
    const card = createHoverCard();
    card.show(
      { land_unit_id: "x", unit_type: "section", label: "2", well_count: 1,
        prod_well_count: 1, liquid_cum_bbl: 10, gas_cum_mcf: 0, water_cum_bbl: 0 },
      { x: 0, y: 0 },
    );
    expect(card.element.querySelector<HTMLButtonElement>(".gw-hover-handle")!.hidden).toBe(true);
  });

  it("drops the ⌾ and the pointer claim the moment the hover is a well again", () => {
    const card = createHoverCard();
    card.show(
      { land_unit_id: "x", unit_type: "section", label: "2", well_count: 1,
        prod_well_count: 1, liquid_cum_bbl: 10, gas_cum_mcf: 0, water_cum_bbl: 0,
        derivation_id: "drv_thematics" },
      { x: 0, y: 0 },
    );
    card.show({ api10: "3305305527", status_canonical: "active" }, { x: 0, y: 0 });
    expect(card.element.querySelector<HTMLButtonElement>(".gw-hover-handle")!.hidden).toBe(true);
    expect(card.element.classList.contains("gw-hover-cell")).toBe(false);
  });
});

describe("edge-aware placement (visual-m13 / visual-m23 V-1)", () => {
  const SIZE = { width: 200, height: 80 };
  const VIEW = { width: 1440, height: 900 };

  it("anchors below-right of the cursor when nothing clips", () => {
    expect(placeCard({ x: 100, y: 100 }, SIZE, VIEW)).toEqual({ x: 114, y: 114 });
  });

  it("flips left of the cursor at the right edge", () => {
    expect(placeCard({ x: 1350, y: 100 }, SIZE, VIEW)).toEqual({ x: 1136, y: 114 });
  });

  it("flips above the cursor at the bottom edge — the hover-low-dark-1440 pose", () => {
    expect(placeCard({ x: 100, y: 860 }, SIZE, VIEW)).toEqual({ x: 114, y: 766 });
  });

  it("flips both ways in the corner", () => {
    expect(placeCard({ x: 1350, y: 860 }, SIZE, VIEW)).toEqual({ x: 1136, y: 766 });
  });

  it("steps around the on-canvas key when another corner clears it", () => {
    const key = { left: 1200, top: 700, right: 1420, bottom: 880 };
    // Below-right lands on the key; below-left fits the canvas and clears it.
    expect(placeCard({ x: 1150, y: 750 }, SIZE, VIEW, key)).toEqual({ x: 936, y: 764 });
  });

  it("keeps the edge-fitting corner when no corner can avoid the key", () => {
    const everywhere = { left: 0, top: 0, right: 1440, bottom: 900 };
    expect(placeCard({ x: 100, y: 100 }, SIZE, VIEW, everywhere)).toEqual({ x: 114, y: 114 });
  });

  it("clamps into the canvas when the card is bigger than it", () => {
    const spot = placeCard({ x: 100, y: 100 }, { width: 2000, height: 1000 }, VIEW);
    expect(spot).toEqual({ x: 0, y: 0 });
  });

  it("never places past the top or left even at a 390-wide viewport", () => {
    // The narrow breakpoint the m23 status queued: a centre hover at 390 must not clip.
    const spot = placeCard({ x: 200, y: 400 }, { width: 256, height: 120 }, { width: 390, height: 844 });
    expect(spot.x).toBeGreaterThanOrEqual(0);
    expect(spot.x + 256).toBeLessThanOrEqual(390);
    expect(spot.y).toBeGreaterThanOrEqual(0);
    expect(spot.y + 120).toBeLessThanOrEqual(844);
  });
});

describe("the tile-failure banner", () => {
  it("stays out of the way until a source actually fails", () => {
    const banner = createTileBanner();
    expect(banner.element.hidden).toBe(true);
  });

  it("names the failing source rather than blaming the map in general", () => {
    const banner = createTileBanner();
    banner.report("protomaps");
    expect(banner.element.hidden).toBe(false);
    expect(banner.element.textContent).toContain("protomaps");
  });

  it("says which basemap it fell back to when one was substituted", () => {
    const banner = createTileBanner();
    banner.report("protomaps", "OpenFreeMap");
    expect(banner.element.textContent).toContain("OpenFreeMap");
  });

  it("collapses repeated failures of the same source into one line", () => {
    const banner = createTileBanner();
    for (let i = 0; i < 40; i += 1) banner.report("protomaps");
    expect(banner.element.querySelectorAll(".gw-banner-line").length).toBe(1);
  });

  it("can be dismissed and stays dismissed for that source", () => {
    const banner = createTileBanner();
    banner.report("protomaps");
    banner.element.querySelector<HTMLButtonElement>(".gw-banner-x")!.click();
    expect(banner.element.hidden).toBe(true);
    banner.report("protomaps");
    expect(banner.element.hidden).toBe(true);
  });
});

/**
 * ARIA forbids focusable content inside an `aria-hidden` subtree: a keyboard reader can land
 * on a control that is not in the accessibility tree and hear nothing about it. The card is a
 * pointer-only affordance — it is driven by `mousemove` and never appears for a keyboard
 * reader — so the handle keeps its click and stops taking Tab. The same derivation still
 * reaches the keyboard through the Layers panel, which map.ts feeds via `setProvenance`.
 */
describe("the hover card's accessibility contract", () => {
  const FOCUSABLE = "a[href], button, input, select, textarea, [tabindex]";
  const CELL = {
    land_unit_id: "T150N-R97W-23",
    unit_type: "section",
    label: "23",
    well_count: 12,
    prod_well_count: 9,
    derivation_id: "drv_cell_1",
  };

  it("puts nothing focusable inside its aria-hidden subtree", () => {
    const card = createHoverCard();
    card.show(CELL, { x: 10, y: 10 });

    expect(card.element.getAttribute("aria-hidden")).toBe("true");
    const focusable = [...card.element.querySelectorAll<HTMLElement>(FOCUSABLE)];
    expect(focusable.length).toBeGreaterThan(0);
    for (const node of focusable) {
      expect(node.tabIndex, `${node.className || node.tagName} takes Tab`).toBeLessThan(0);
    }
  });

  it("keeps the handle clickable, because the cell figures resolve on the card itself", () => {
    const card = createHoverCard();
    const seen = vi.fn();
    card.element.addEventListener(EXPLAIN_EVENT, (event) => {
      seen((event as CustomEvent<{ handle: string }>).detail.handle);
    });
    card.show(CELL, { x: 10, y: 10 });

    const handle = card.element.querySelector<HTMLButtonElement>(".gw-hover-handle");
    expect(handle?.hidden).toBe(false);
    handle?.click();

    expect(seen).toHaveBeenCalledWith("drv_cell_1");
  });
});
