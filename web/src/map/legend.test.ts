// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import { createLegend, legendEnabled } from "./legend.ts";
import { MEASURED_WELL_COUNTS, STATUS_CLASSES } from "./status.ts";

const rows = (root: HTMLElement): HTMLElement[] => [...root.querySelectorAll<HTMLElement>(".gw-lg-row")];
const rowFor = (root: HTMLElement, id: string): HTMLElement | undefined =>
  rows(root).find((row) => row.dataset["status"] === id);

describe("the legend", () => {
  it("collapses to a title pill by default and expands on a click of the title", () => {
    const legend = createLegend({ onFilter: () => {} });
    expect(legend.element.classList.contains("gw-open")).toBe(false);
    legend.element.querySelector<HTMLElement>(".gw-lg-title")?.click();
    expect(legend.element.classList.contains("gw-open")).toBe(true);
  });

  it("does not collapse when a filter row is clicked — a row is a control", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.element.querySelector<HTMLElement>(".gw-lg-title")?.click();
    rows(legend.element)[0]?.click();
    expect(legend.element.classList.contains("gw-open")).toBe(true);
  });

  it("renders one row per canonical status, with a label on every one", () => {
    const legend = createLegend({ onFilter: () => {} });
    expect(rows(legend.element).map((row) => row.dataset["status"])).toEqual(
      STATUS_CLASSES.map((status) => status.id),
    );
    for (const row of rows(legend.element)) {
      expect(row.querySelector(".gw-lg-label")?.textContent?.trim().length).toBeGreaterThan(0);
    }
  });

  it("never lists a class the data does not contain", () => {
    const legend = createLegend({ onFilter: () => {} });
    const listed = rows(legend.element).map((row) => row.dataset["status"]);
    expect(listed).not.toContain("producing");
    for (const id of listed) expect(MEASURED_WELL_COUNTS[id!]).toBeGreaterThan(0);
  });

  it("reports the filtered set back when a row is toggled", () => {
    const seen: string[][] = [];
    const legend = createLegend({ onFilter: (on) => seen.push([...on].sort()) });
    const box = rowFor(legend.element, "active")?.querySelector<HTMLInputElement>("input");
    box!.checked = false;
    box!.dispatchEvent(new Event("change", { bubbles: true }));
    expect(seen[seen.length - 1]).not.toContain("active");
    expect(seen[seen.length - 1]).toContain("plugged");
  });

  it("patches counts in place so a checkbox is never torn out from under the pointer", () => {
    const legend = createLegend({ onFilter: () => {} });
    const box = rowFor(legend.element, "active")!.querySelector("input");
    legend.setCounts({ active: 12_940 }, 12);
    expect(rowFor(legend.element, "active")!.querySelector(".gw-lg-count")?.textContent).toBe("12,940");
    expect(rowFor(legend.element, "active")!.querySelector("input")).toBe(box);
  });

  it("shows an em dash, never a zero, for a count it does not have", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({}, 12);
    expect(rowFor(legend.element, "dry")!.querySelector(".gw-lg-count")?.textContent).toBe("—");
  });

  it("disables an out-of-scale row and says which zoom brings it back", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({}, 5);
    const plugged = rowFor(legend.element, "plugged")!;
    expect(plugged.getAttribute("data-out-of-scale")).toBe("true");
    expect(plugged.querySelector<HTMLInputElement>("input")!.disabled).toBe(true);
    expect(plugged.title).toMatch(/zoom to 9/i);
    expect(rowFor(legend.element, "active")!.getAttribute("data-out-of-scale")).toBe(null);
  });

  it("adds a row for a status the build cannot name, rather than colouring it grey in silence", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ unmapped: 4 }, 12);
    const row = rowFor(legend.element, "unmapped");
    expect(row).toBeTruthy();
    expect(row!.querySelector(".gw-lg-count")?.textContent).toBe("4");
    expect(row!.querySelector<HTMLInputElement>("input")!.disabled).toBe(true);
  });

  it("states the geometry provenance rather than implying a survey trace", () => {
    const legend = createLegend({ onFilter: () => {} });
    expect(legend.element.textContent).toMatch(/not a directional survey trace/i);
    expect(legend.element.textContent).toContain("cr_nd_status_vocab_1");
  });
});

describe("?legend=0", () => {
  it("suppresses the legend on exactly that value", () => {
    expect(legendEnabled("?legend=0")).toBe(false);
    expect(legendEnabled("?base=satellite&legend=0&map=9/47/-102")).toBe(false);
  });

  it("keeps the legend when the parameter is absent", () => {
    expect(legendEnabled("")).toBe(true);
    expect(legendEnabled("?base=light")).toBe(true);
  });

  it("keeps the legend on a value it was not given, rather than guessing at intent", () => {
    // The key is the map's own; a reader who typed something else asked for nothing, and the
    // safe failure for a panel that carries the status vocabulary is to still be there.
    for (const value of ["", "1", "false", "off", "no", "00", " 0", "0 ", "O", "%00", "0,0"]) {
      expect(legendEnabled(`?legend=${encodeURIComponent(value)}`), `legend=${value}`).toBe(true);
    }
  });

  it("is not satisfied by the substring of another parameter", () => {
    expect(legendEnabled("?notlegend=0")).toBe(true);
    expect(legendEnabled("?legendary=0")).toBe(true);
  });
});
