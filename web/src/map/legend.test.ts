// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import { createLegend, legendEnabled } from "./legend.ts";
import { MEASURED_WELL_COUNTS, STATUS_CLASSES, statusIds } from "./status.ts";

const rows = (root: HTMLElement): HTMLElement[] => [...root.querySelectorAll<HTMLElement>(".gw-lg-row")];
const rowFor = (root: HTMLElement, id: string): HTMLElement | undefined =>
  rows(root).find((row) => row.dataset["status"] === id);
const boxFor = (root: HTMLElement, id: string): HTMLInputElement =>
  rowFor(root, id)!.querySelector<HTMLInputElement>("input")!;
const control = (root: HTMLElement, which: "all" | "none"): HTMLButtonElement =>
  root.querySelector<HTMLButtonElement>(`.gw-lg-${which}`)!;
const expand = (root: HTMLElement): HTMLElement => {
  root.querySelector<HTMLElement>(".gw-lg-title")?.click();
  return root;
};

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

describe("the legend's all/none control", () => {
  it("sits in the header, as two named buttons the keyboard can reach", () => {
    const legend = createLegend({ onFilter: () => {} });
    document.body.appendChild(legend.element); // focus is only meaningful on a rendered tree
    expand(legend.element);
    for (const which of ["all", "none"] as const) {
      const button = control(legend.element, which);
      expect(button.tagName).toBe("BUTTON");
      expect(button.type).toBe("button");
      expect(button.disabled).toBe(false);
      expect(button.getAttribute("aria-label")?.length).toBeGreaterThan(0);
      expect(legend.element.querySelector(".gw-lg-head")?.contains(button)).toBe(true);
      button.focus();
      expect(document.activeElement).toBe(button);
    }
    legend.element.remove();
  });

  it("appears with the rows it acts on, not on the collapsed pill", () => {
    // Nine rows are the thing being bulk-toggled; offering the bulk action while they are
    // hidden is a click whose whole effect is off screen.
    const legend = createLegend({ onFilter: () => {} });
    const actions = legend.element.querySelector<HTMLElement>(".gw-lg-actions")!;
    expect(actions.hidden).toBe(true);
    expand(legend.element);
    expect(actions.hidden).toBe(false);
    expand(legend.element);
    expect(actions.hidden).toBe(true);
  });

  it("clears every known class in one click, and reports it down the row-toggle path", () => {
    const seen: string[][] = [];
    const legend = createLegend({ onFilter: (on) => seen.push([...on].sort()) });
    expand(legend.element);
    control(legend.element, "none").click();
    expect(seen).toHaveLength(1);
    expect(seen[0]).toEqual([]);
    expect(legend.activeStatuses().size).toBe(0);
    for (const id of statusIds()) expect(boxFor(legend.element, id).checked, id).toBe(false);
  });

  it("restores every known class in one click", () => {
    const seen: string[][] = [];
    const legend = createLegend({ onFilter: (on) => seen.push([...on].sort()) });
    expand(legend.element);
    control(legend.element, "none").click();
    control(legend.element, "all").click();
    expect(seen[seen.length - 1]).toEqual([...statusIds()].sort());
    for (const id of statusIds()) expect(boxFor(legend.element, id).checked, id).toBe(true);
  });

  it("leaves the unmapped row alone — a defect marker is not a filter the reader owns", () => {
    const legend = createLegend({ onFilter: () => {} });
    expand(legend.element);
    legend.setCounts({ unmapped: 4 }, 12);
    for (const which of ["none", "all"] as const) {
      control(legend.element, which).click();
      expect(boxFor(legend.element, "unmapped").disabled).toBe(true);
      expect(legend.activeStatuses().has("unmapped")).toBe(false);
    }
  });

  it("does not enable an out-of-scale row: disabled is the zoom's to say, not the control's", () => {
    const legend = createLegend({ onFilter: () => {} });
    expand(legend.element);
    legend.setCounts({}, 5);
    for (const which of ["all", "none"] as const) {
      control(legend.element, which).click();
      const plugged = rowFor(legend.element, "plugged")!;
      expect(plugged.querySelector<HTMLInputElement>("input")!.disabled, which).toBe(true);
      expect(plugged.getAttribute("data-out-of-scale"), which).toBe("true");
      expect(plugged.title, which).toMatch(/zoom to 9/i);
    }
  });

  it("clears an out-of-scale class too, so zooming in does not resurrect what was cleared", () => {
    // The alternative — skipping the rows the zoom has disabled — makes "none" mean "none of
    // what you can see", and the wells the reader dismissed come back on the next zoom in.
    const seen: string[][] = [];
    const legend = createLegend({ onFilter: (on) => seen.push([...on].sort()) });
    expand(legend.element);
    legend.setCounts({}, 5);
    control(legend.element, "none").click();
    expect(seen[seen.length - 1]).toEqual([]);
    legend.setCounts({ plugged: 7_316 }, 12);
    expect(boxFor(legend.element, "plugged").disabled).toBe(false);
    expect(boxFor(legend.element, "plugged").checked).toBe(false);
    expect(legend.activeStatuses().has("plugged")).toBe(false);
  });

  it("survives the repaint that follows it, rather than being undone by the next count", () => {
    const legend = createLegend({ onFilter: () => {} });
    expand(legend.element);
    control(legend.element, "none").click();
    legend.setCounts({ active: 20_643, plugged: 7_316 }, 12);
    expect(legend.activeStatuses().size).toBe(0);
  });

  it("does not collapse the legend — the control is a control, like a row", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.element.querySelector<HTMLElement>(".gw-lg-title")?.click();
    control(legend.element, "none").click();
    expect(legend.element.classList.contains("gw-open")).toBe(true);
  });

  it("still drives the filter when ?legend=0 has kept the element off the canvas", () => {
    // map.ts never appends the element in that case but keeps the handle live; a control that
    // needed a layout to work would make the suppressed map unfilterable.
    const seen: string[][] = [];
    const legend = createLegend({ onFilter: (on) => seen.push([...on].sort()) });
    expand(legend.element);
    expect(legend.element.isConnected).toBe(false);
    control(legend.element, "none").click();
    expect(seen[0]).toEqual([]);
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
