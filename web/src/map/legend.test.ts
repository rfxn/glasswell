// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { beforeEach, describe, expect, it } from "vitest";

import { EXPLAIN_EVENT } from "../chrome/handle.ts";
import { createLegend, legendEnabled } from "./legend.ts";
import {
  STATUS_STORAGE_KEY,
  readCapabilitySet,
  restoreCapabilitySet,
  writeCapabilitySet,
} from "./persist.ts";
import { STATUS_CLASSES, filterableStatusIds, measuredWellCount, statusIds } from "./status.ts";

const rows = (root: HTMLElement): HTMLElement[] => [...root.querySelectorAll<HTMLElement>(".gw-lg-row")];
const rowFor = (root: HTMLElement, id: string): HTMLElement | undefined =>
  rows(root).find((row) => row.dataset["status"] === id);
const boxFor = (root: HTMLElement, id: string): HTMLInputElement =>
  rowFor(root, id)!.querySelector<HTMLInputElement>("input")!;
const countFor = (root: HTMLElement, id: string): string =>
  rowFor(root, id)!.querySelector<HTMLElement>(".gw-lg-count")!.textContent ?? "";
const handleFor = (root: HTMLElement, id: string): HTMLButtonElement | null =>
  rowFor(root, id)!.querySelector<HTMLButtonElement>(".gw-lg-handle");
const control = (root: HTMLElement, which: "all" | "none"): HTMLButtonElement =>
  root.querySelector<HTMLButtonElement>(`.gw-lg-${which}`)!;
const expand = (root: HTMLElement): HTMLElement => {
  root.querySelector<HTMLElement>(".gw-lg-title")?.click();
  return root;
};
const partial = (root: HTMLElement): HTMLElement =>
  root.querySelector<HTMLElement>(".gw-lg-partial")!;
const fault = (root: HTMLElement): HTMLElement => root.querySelector<HTMLElement>(".gw-lg-fault")!;
/**
 * Visibility, not text. happy-dom's `textContent` reads into `hidden` subtrees, so a banner
 * that is present-but-hidden and one that is on screen read identically through text — which
 * is how an error surface can end up with no regression net at all (gate-wssweb C-2).
 */
const shown = (element: HTMLElement): boolean =>
  element.hidden === false && element.hasAttribute("hidden") === false;

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
    for (const id of listed) expect(measuredWellCount(id!)).toBeGreaterThan(0);
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
    expect(row!.querySelector<HTMLInputElement>("input")!.disabled).toBe(false);
  });

  it("filters the unmapped row like any other, because it is the largest class on some maps", () => {
    const seen: string[][] = [];
    const legend = createLegend({ onFilter: (on) => seen.push([...on].sort()) });
    legend.setCounts({ unmapped: 66_103 }, 12);
    const box = boxFor(legend.element, "unmapped");

    expect(box.disabled).toBe(false);
    expect(box.checked).toBe(true);
    box.checked = false;
    box.dispatchEvent(new Event("change", { bubbles: true }));

    expect(seen[seen.length - 1]).not.toContain("unmapped");
    expect(legend.activeStatuses().has("unmapped")).toBe(false);
  });

  it("holds the absence class on before it has listed it, so a defect never hides by default", () => {
    // The row is only listed once the class is drawn, but its switch exists from the start —
    // otherwise "None" would leave on the canvas the one class the key had never named.
    const legend = createLegend({ onFilter: () => {} });
    expect(rowFor(legend.element, "unmapped")).toBeUndefined();
    expect(legend.activeStatuses().has("unmapped")).toBe(true);
    legend.setCounts({ unmapped: 4 }, 12);
    expect(boxFor(legend.element, "unmapped").checked).toBe(true);
  });

  it("carries a reader's stored refusal of the absence class through to the filter", () => {
    const legend = createLegend({ on: new Set(statusIds()), onFilter: () => {} });
    expect(legend.activeStatuses().has("unmapped")).toBe(false);
    legend.setCounts({ unmapped: 4 }, 12);
    expect(boxFor(legend.element, "unmapped").checked).toBe(false);
  });

  it("states the geometry provenance rather than implying a survey trace", () => {
    const legend = createLegend({ onFilter: () => {} });
    expect(legend.element.textContent).toMatch(/not a directional survey trace/i);
    expect(legend.element.textContent).toContain("cr_nd_status_vocab_1");
  });

  it("names both regulators the one lateral row now draws", () => {
    // The key's geometry line spoke for a row that was North Dakota's alone. One toggle over
    // two regulators' files may not leave the key saying "regulator GIS" and nothing more.
    const legend = createLegend({ onFilter: () => {} });
    expect(legend.element.textContent).toContain("ND DMR");
    expect(legend.element.textContent).toContain("TX RRC");
  });

  it("names the orchid trace beside the thing it says the laterals are not", () => {
    // visual-m15web N2: "not a directional survey trace" while the trace sat on the canvas
    // unnamed by the key was a half-contrast — the other half is one sentence.
    const legend = createLegend({ onFilter: () => {} });
    expect(legend.element.textContent).toMatch(/orchid line is that trace/i);
    legend.setVocabulary([{ rule: "cr_nd_status_vocab_1", href: null }]);
    expect(legend.element.textContent).toMatch(/orchid line is that trace/i);
  });

  it("names the served provenance vocabulary and the rule that classes it", () => {
    // M1-3: the provenance line stops being prose about two rows and becomes the statement
    // of a served field — the three classes verbatim, the R8 row that maps them.
    const legend = createLegend({ onFilter: () => {} });
    expect(legend.element.textContent).toMatch(/surface, lateral or survey_trace/);
    expect(legend.element.textContent).toContain("cr_nd_geometry_provenance_1");
    legend.setVocabulary([{ rule: "cr_nd_status_vocab_1", href: null }]);
    expect(legend.element.textContent).toContain("cr_nd_geometry_provenance_1");
  });

  it("says why Texas serves no provenance field, where a reader would look for it", () => {
    // The ND-only scope is a licence ruling (RF-1), not an oversight; the surface that
    // states the provenance vocabulary is the surface that owes the reader the exclusion.
    const legend = createLegend({ onFilter: () => {} });
    expect(legend.element.textContent).toMatch(/TX geometry carries no provenance field/i);
    expect(legend.element.textContent).toContain("RF-1");
  });

  it("opens the note with both licence-class sentences, ahead of even the colours preamble", () => {
    // visual-m24 O2: the note's cap holds ~13 lines at 390x844 against a taller scrollHeight,
    // so only what leads is visible on open — the licence pair may spend none of that budget
    // on the status-colours preamble, let alone the laterals/trace/ring detail.
    const legend = createLegend({ onFilter: () => {} });
    const order = (root: HTMLElement): void => {
      const text = root.querySelector<HTMLElement>(".gw-lg-note")!.textContent ?? "";
      const nd = text.indexOf("Every ND feature carries its geometry provenance");
      const tx = text.indexOf("TX geometry carries no provenance field");
      const preamble = text.indexOf("Status colours are data colours");
      const symbology = text.indexOf("Laterals are ND DMR and TX RRC GIS bore geometry");
      expect(nd).toBe(0);
      expect(tx).toBeGreaterThan(nd);
      expect(preamble).toBeGreaterThan(tx);
      expect(symbology).toBeGreaterThan(preamble);
    };
    order(legend.element);
    legend.setVocabulary([{ rule: "cr_nd_status_vocab_1", href: null }]);
    order(legend.element);
  });

  it("keeps the note's fold cap where the order fix was measured against it", () => {
    // happy-dom lays nothing out, so the fold itself is the browser tier's to measure; what
    // is pinnable here is the cap the visual-m24 arithmetic used (192px at 844h) — a cap
    // change silently re-opens the question of whether the TX sentence tail clears the fold.
    const css = readFileSync("src/map.css", "utf8");
    const note = /\.gw-lg-note\s*\{[^}]*\}/.exec(css)?.[0] ?? "";
    expect(note).toContain("max-height: min(28vh, 12rem);");
  });

  it("caps the key against the map it sits on rather than against the blocks it holds", () => {
    // The key is anchored to the bottom and grows upward, so an uncapped one grows off the map
    // and under the app header, taking its own collapse control with it (R1). The ceiling is
    // the map's height less the key's insets and the column is what makes the head the last
    // thing to give way; tests/e2e/map-key-hit.mjs measures what they buy in a real layout.
    const css = readFileSync("src/map.css", "utf8");
    const key = /\.gw-lg\s*\{[^}]*\}/.exec(css)?.[0] ?? "";
    expect(key).toContain("max-height: calc(100% - 2.8rem);");
    expect(key).toContain("flex-direction: column;");
  });

  it("names the blue ring as the regulator's own well_type, and the rule that classes it", () => {
    // The ring is a data colour over a key that opens with "data colours, not severity colours",
    // and the sentence keeps the hue from claiming the class injects only water.
    const legend = createLegend({ onFilter: () => {} });
    expect(legend.element.textContent).toMatch(/teal ring is NDIC's own well_type/i);
    expect(legend.element.textContent).toMatch(/any injected stream/i);
    expect(legend.element.textContent).toContain("cr_nd_well_type_disposal_1");
    legend.setVocabulary([{ rule: "cr_nd_status_vocab_1", href: null }]);
    expect(legend.element.textContent).toMatch(/teal ring is NDIC's own well_type/i);
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

  it("restores every known class in one click, the absence class among them", () => {
    const seen: string[][] = [];
    const legend = createLegend({ onFilter: (on) => seen.push([...on].sort()) });
    expand(legend.element);
    control(legend.element, "none").click();
    control(legend.element, "all").click();
    expect(seen[seen.length - 1]).toEqual([...filterableStatusIds()].sort());
    for (const id of statusIds()) expect(boxFor(legend.element, id).checked, id).toBe(true);
  });

  it("acts on the unmapped row too, once the map has one — it is a class, not an ornament", () => {
    const legend = createLegend({ onFilter: () => {} });
    expand(legend.element);
    legend.setCounts({ unmapped: 4 }, 12);
    control(legend.element, "none").click();
    expect(boxFor(legend.element, "unmapped").checked).toBe(false);
    expect(legend.activeStatuses().has("unmapped")).toBe(false);
    control(legend.element, "all").click();
    expect(boxFor(legend.element, "unmapped").checked).toBe(true);
    expect(legend.activeStatuses().has("unmapped")).toBe(true);
  });

  it("counts the unmapped row in the title, so a hidden defect class is stated on the pill", () => {
    const legend = createLegend({ onFilter: () => {} });
    const title = (): string => legend.element.querySelector(".gw-lg-title")!.textContent!;
    expand(legend.element);
    legend.setCounts({ unmapped: 4 }, 12);
    expect(title()).toBe("Well status");
    boxFor(legend.element, "unmapped").checked = false;
    boxFor(legend.element, "unmapped").dispatchEvent(new Event("change", { bubbles: true }));
    expect(title()).toBe(`Well status · ${statusIds().length}/${statusIds().length + 1}`);
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

describe("the legend's persisted status set", () => {
  beforeEach(() => window.localStorage.clear());

  it("opens with the classes the last visit left on", () => {
    const legend = createLegend({ on: new Set(["active", "drilling"]), onFilter: () => {} });
    expect([...legend.activeStatuses()].sort()).toEqual(["active", "drilling"]);
    expect(boxFor(legend.element, "plugged").checked).toBe(false);
  });

  it("round-trips a deselect-all through storage and back into a fresh legend", () => {
    const first = createLegend({
      on: restoreCapabilitySet(readCapabilitySet(STATUS_STORAGE_KEY), statusIds(), statusIds()),
      onFilter: (next) => writeCapabilitySet(STATUS_STORAGE_KEY, next, statusIds(), 0),
    });
    expand(first.element);
    expect(first.activeStatuses().size).toBe(statusIds().length);

    control(first.element, "none").click();
    expect(readCapabilitySet(STATUS_STORAGE_KEY)).toEqual({ on: [], known: statusIds() });

    const reloaded = createLegend({
      on: restoreCapabilitySet(readCapabilitySet(STATUS_STORAGE_KEY), statusIds(), statusIds()),
      onFilter: () => {},
    });
    expect(reloaded.activeStatuses().size).toBe(0);
    for (const id of statusIds()) expect(boxFor(reloaded.element, id).checked, id).toBe(false);
  });

  it("ships a class the stored set never knew about on, rather than hiding a new one", () => {
    // The {on,known} shape is what tells "the reader turned this off" apart from "this class
    // did not exist when that state was written". A vocabulary row added later must not
    // arrive invisible because a stored `on` list predates it.
    const known = statusIds();
    const stored = { on: [], known: known.filter((id) => id !== "confidential") };
    const legend = createLegend({
      on: restoreCapabilitySet(stored, known, known),
      onFilter: () => {},
    });
    expect([...legend.activeStatuses()]).toEqual(["confidential"]);
  });

  it("says how many classes are on, so a collapsed key cannot hide a filter", () => {
    const legend = createLegend({ onFilter: () => {} });
    const title = (): string => legend.element.querySelector(".gw-lg-title")!.textContent!;
    expect(title()).toBe("Well status");
    expand(legend.element);
    control(legend.element, "none").click();
    expect(title()).toBe(`Well status · 0/${statusIds().length}`);
    control(legend.element, "all").click();
    expect(title()).toBe("Well status");
    expect(
      createLegend({ on: new Set(["active"]), onFilter: () => {} }).element.querySelector(
        ".gw-lg-title",
      )!.textContent,
    ).toBe(`Well status · 1/${statusIds().length}`);
  });
});

describe("counts that are being fetched", () => {
  it("says it is asking, rather than leaving the last viewport's numbers on screen", () => {
    // The honesty rule the whole track turns on: a number under a viewport it was not counted
    // over is a wrong number, and the moment the reader pans it is exactly that.
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 20_643, plugged: 7_316 }, 12);
    legend.setPending(12);

    expect(countFor(legend.element, "active")).not.toContain("20,643");
    expect(countFor(legend.element, "plugged")).not.toContain("7,316");
    for (const id of statusIds()) expect(countFor(legend.element, id), id).toBe("…");
  });

  it("marks itself busy while it asks, so a reader is not left guessing at a still key", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setPending(12);
    expect(legend.element.querySelector(".gw-lg-body")?.getAttribute("aria-busy")).toBe("true");
    legend.setCounts({ active: 3 }, 12);
    expect(legend.element.querySelector(".gw-lg-body")?.getAttribute("aria-busy")).toBe("false");
  });

  it("keeps the out-of-scale marks while it asks — the zoom did not stop being true", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setPending(5);
    expect(rowFor(legend.element, "plugged")!.getAttribute("data-out-of-scale")).toBe("true");
    expect(boxFor(legend.element, "plugged").disabled).toBe(true);
  });
});

describe("counts that could not be had", () => {
  it("shows an em dash and says so, so absence is not read as a count of none", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 20_643 }, 12);
    legend.setUnavailable(12);

    for (const id of statusIds()) expect(countFor(legend.element, id), id).toBe("—");
    expect(legend.element.dataset["counts"]).toBe("unavailable");
    expect(shown(fault(legend.element))).toBe(true);
    expect(fault(legend.element).textContent).toMatch(/could not be read/i);
  });

  it("keeps the failure off the key while the counts are good", () => {
    // The other direction, and the one a string assertion cannot make: a banner that is
    // present but hidden reads the same as one on screen through textContent.
    const legend = createLegend({ onFilter: () => {} });
    legend.setUnavailable(12);
    expect(shown(fault(legend.element))).toBe(true);

    legend.setCounts({ active: 20_643 }, 12);
    expect(shown(fault(legend.element))).toBe(false);
    expect(fault(legend.element).hidden).toBe(true);
  });

  it("announces no failure for a request that is merely in flight", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setPending(12);
    expect(shown(fault(legend.element))).toBe(false);
    expect(legend.element.dataset["counts"]).toBe("pending");
  });

  it("carries no failure banner before anything has been asked", () => {
    expect(shown(fault(createLegend({ onFilter: () => {} }).element))).toBe(false);
  });

  it("carries no handle it cannot resolve", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 3 }, 12, { active: "drv_a#col=wells&status=active" });
    legend.setUnavailable(12);
    expect(handleFor(legend.element, "active")!.hidden).toBe(true);
  });

  it("is cleared by the next answer", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setUnavailable(12);
    legend.setCounts({ active: 3 }, 12);
    expect(legend.element.dataset["counts"]).toBe("ready");
    expect(legend.element.textContent).not.toMatch(/could not be read/i);
    expect(shown(fault(legend.element))).toBe(false);
  });
});

describe("a count that is now a served figure", () => {
  const HANDLES = {
    active: "drv_xret5nw2hhouqi5mfvda#col=wells&status=active&bbox=-104.5:47.2:-102.1:48.6",
    plugged: "drv_xret5nw2hhouqi5mfvda#col=wells&status=plugged&bbox=-104.5:47.2:-102.1:48.6",
  };

  it("offers its own derivation, not one borrowed from the class beside it", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 3, plugged: 2 }, 12, HANDLES);

    expect(handleFor(legend.element, "active")!.dataset["handle"]).toBe(HANDLES.active);
    expect(handleFor(legend.element, "plugged")!.dataset["handle"]).toBe(HANDLES.plugged);
  });

  it("opens the drawer through the one event the app already listens for", () => {
    const legend = createLegend({ onFilter: () => {} });
    document.body.appendChild(legend.element);
    const seen: string[] = [];
    document.addEventListener(EXPLAIN_EVENT, (event) => {
      seen.push((event as CustomEvent<{ handle: string }>).detail.handle);
    });
    legend.setCounts({ active: 3 }, 12, HANDLES);
    handleFor(legend.element, "active")!.click();

    expect(seen).toEqual([HANDLES.active]);
    legend.element.remove();
  });

  it("cancels the click a <label> would otherwise forward to its checkbox", () => {
    // A handle is not a filter. happy-dom does not implement label activation, so the toggle
    // itself cannot fail here — what is observable, and what a browser reads before deciding
    // to forward, is that the click was cancelled. The browser tier carries the visual proof.
    const legend = createLegend({ onFilter: () => {} });
    document.body.appendChild(legend.element);
    legend.setCounts({ active: 3 }, 12, HANDLES);
    let cancelled: boolean | null = null;
    rowFor(legend.element, "active")!.addEventListener("click", (event) => {
      cancelled = event.defaultPrevented;
    });
    handleFor(legend.element, "active")!.click();

    expect(cancelled).toBe(true);
    expect(boxFor(legend.element, "active").checked).toBe(true);
    legend.element.remove();
  });

  it("does not collapse the key it sits in", () => {
    const legend = createLegend({ onFilter: () => {} });
    expand(legend.element);
    legend.setCounts({ active: 3 }, 12, HANDLES);
    handleFor(legend.element, "active")!.click();
    expect(legend.element.classList.contains("gw-open")).toBe(true);
  });

  it("is absent on a class with no count, because there is nothing to explain", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 3 }, 12, HANDLES);
    expect(handleFor(legend.element, "active")!.hidden).toBe(false);
    expect(handleFor(legend.element, "dry")!.hidden).toBe(true);
  });

  it("names the class in its label, so a screen reader is not given ten identical buttons", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 3 }, 12, HANDLES);
    // Asserted whole, not by substring: /active/i also matched the doubled
    // "Lineage for Lineage for the active count" this file used to let through.
    expect(handleFor(legend.element, "active")!.getAttribute("aria-label")).toBe(
      "Lineage for the active count",
    );
  });

  it("says 'Lineage for' once on every handle it renders, not once per author", () => {
    const legend = createLegend({ onFilter: () => {} });
    document.body.appendChild(legend.element);
    expand(legend.element);
    legend.setCounts({ active: 3, plugged: 2 }, 12, HANDLES);

    const names = [...legend.element.querySelectorAll<HTMLButtonElement>("button.gw-handle")].map(
      (button) => button.getAttribute("aria-label") ?? "",
    );
    expect(names.length).toBeGreaterThan(0);
    for (const name of names) {
      expect(name.match(/Lineage for/g), name).toHaveLength(1);
      expect(name, name).toMatch(/^Lineage for \S/);
    }
    legend.element.remove();
  });
});

describe("the canvas beside the counts", () => {
  it("says nothing while the two agree", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 30, plugged: 20 }, 12);
    legend.setDrawn(50);
    expect(partial(legend.element).hidden).toBe(true);
  });

  it("states both numbers when the canvas is drawing a subset of what is in view", () => {
    // The counts are the data's; the canvas is thinned and zoom-culled. Neither is wrong, and
    // a reader who can see both cannot read them as contradicting each other.
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 20_643, plugged: 7_316 }, 6);
    legend.setDrawn(1_204);

    expect(partial(legend.element).hidden).toBe(false);
    expect(partial(legend.element).textContent).toContain("1,204");
    expect(partial(legend.element).textContent).toContain("27,959");
    expect(partial(legend.element).title).toMatch(/zoom|thin/i);
  });

  it("counts only the classes the reader has left on, so a filter is not read as a shortfall", () => {
    // The count states what is in the area; the checkbox states what is drawn. Both stay true.
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 20_643, plugged: 7_316 }, 12);
    boxFor(legend.element, "plugged").checked = false;
    boxFor(legend.element, "plugged").dispatchEvent(new Event("change", { bubbles: true }));
    legend.setDrawn(20_643);

    expect(partial(legend.element).hidden).toBe(true);
    expect(countFor(legend.element, "plugged")).toBe("7,316");
  });

  it("says nothing when there is no canvas census to make — silence, not a zero", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 20_643 }, 12);
    legend.setDrawn(null);
    expect(partial(legend.element).hidden).toBe(true);
  });

  it("withdraws the statement when the counts are no longer known", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 20_643 }, 6);
    legend.setDrawn(1_204);
    expect(partial(legend.element).hidden).toBe(false);
    legend.setPending(6);
    expect(partial(legend.element).hidden).toBe(true);
  });
});

describe("the map-extent filter node (M1-2)", () => {
  const TOTAL = {
    wells: 27_959,
    handle: "drv_xret5nw2hhouqi5mfvda#col=wells&bbox=-104.5:47.2:-102.1:48.6",
  };
  const node = (root: HTMLElement): HTMLElement => root.querySelector<HTMLElement>(".gw-lg-extent")!;
  const nodeBox = (root: HTMLElement): HTMLInputElement =>
    node(root).querySelector<HTMLInputElement>("input")!;
  const nodeCount = (root: HTMLElement): string =>
    node(root).querySelector<HTMLElement>(".gw-lg-count")!.textContent ?? "";
  const nodeHandle = (root: HTMLElement): HTMLButtonElement =>
    node(root).querySelector<HTMLButtonElement>(".gw-lg-handle")!;
  const scope = (root: HTMLElement): HTMLElement => root.querySelector<HTMLElement>(".gw-lg-scope")!;
  const title = (root: HTMLElement): string =>
    root.querySelector<HTMLElement>(".gw-lg-title")!.textContent!;
  const flip = (root: HTMLElement, next: boolean): void => {
    nodeBox(root).checked = next;
    nodeBox(root).dispatchEvent(new Event("change", { bubbles: true }));
  };

  it("lists the viewport as a named, counted, switch-off-able row above the classes", () => {
    const legend = createLegend({ onFilter: () => {} });
    expect(node(legend.element).textContent).toContain("Map view");
    expect(nodeBox(legend.element).checked).toBe(true);
    expect(nodeCount(legend.element)).toBe("—");
    const children = [...legend.element.querySelector(".gw-lg-body")!.children];
    expect(children.indexOf(node(legend.element))).toBeLessThan(
      children.indexOf(rows(legend.element)[0]!),
    );
  });

  it("joins the tree visibly: and to the extent node, any of over the class rows", () => {
    const legend = createLegend({ onFilter: () => {} });
    const joins = legend.element.querySelector<HTMLElement>(".gw-lg-join")!;
    expect(joins.textContent).toContain("and");
    expect(joins.textContent).toContain("any of");
    const children = [...legend.element.querySelector(".gw-lg-body")!.children];
    expect(children.indexOf(joins)).toBeGreaterThan(children.indexOf(node(legend.element)));
    expect(children.indexOf(joins)).toBeLessThan(children.indexOf(rows(legend.element)[0]!));
  });

  // gate-m12 F2: a static tooltip asserted in-view coverage even while the node was off.
  it("flips the row's tooltip with the node, so the hover is true in both states", () => {
    const legend = createLegend({ onFilter: () => {} });
    expect(node(legend.element).title).toContain("Counts cover the wells the map view holds");
    flip(legend.element, false);
    expect(node(legend.element).title).toContain("Counts cover everything ingested");
    expect(node(legend.element).title).not.toContain("Counts cover the wells the map view holds");
    flip(legend.element, true);
    expect(node(legend.element).title).toContain("Counts cover the wells the map view holds");
  });

  it("opens with the off-state tooltip when the URL restored the node off", () => {
    const legend = createLegend({ onFilter: () => {}, extentOn: false });
    expect(node(legend.element).title).toContain("Counts cover everything ingested");
  });

  it("carries the population's own count and its own derivation handle", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 20_643, plugged: 7_316 }, 12, {}, TOTAL);
    expect(nodeCount(legend.element)).toBe("27,959");
    expect(nodeHandle(legend.element).hidden).toBe(false);
    expect(nodeHandle(legend.element).dataset["handle"]).toBe(TOTAL.handle);
  });

  it("shows an em dash, never a zero, when the answer carried no total", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 3 }, 12);
    expect(nodeCount(legend.element)).toBe("—");
    expect(nodeHandle(legend.element).hidden).toBe(true);
  });

  it("waits and withdraws with the class counts, never keeping a stale population", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 3 }, 12, {}, TOTAL);
    legend.setPending(12);
    expect(nodeCount(legend.element)).toBe("…");
    expect(nodeHandle(legend.element).hidden).toBe(true);
    legend.setUnavailable(12);
    expect(nodeCount(legend.element)).toBe("—");
    expect(nodeHandle(legend.element).hidden).toBe(true);
  });

  it("opens the drawer for the population count without toggling the node", () => {
    const legend = createLegend({ onFilter: () => {} });
    document.body.appendChild(legend.element);
    const seen: string[] = [];
    document.addEventListener(EXPLAIN_EVENT, (event) => {
      seen.push((event as CustomEvent<{ handle: string }>).detail.handle);
    });
    legend.setCounts({ active: 3 }, 12, {}, TOTAL);
    nodeHandle(legend.element).click();
    expect(seen).toEqual([TOTAL.handle]);
    expect(nodeBox(legend.element).checked).toBe(true);
    legend.element.remove();
  });

  it("reports the toggle and states the widened population while it is off", () => {
    const seen: boolean[] = [];
    const legend = createLegend({ onFilter: () => {}, onExtent: (on) => seen.push(on) });
    expect(shown(scope(legend.element))).toBe(false);
    flip(legend.element, false);
    expect(seen).toEqual([false]);
    expect(shown(scope(legend.element))).toBe(true);
    expect(scope(legend.element).textContent).toMatch(/every ingested well/i);
    flip(legend.element, true);
    expect(seen).toEqual([false, true]);
    expect(shown(scope(legend.element))).toBe(false);
  });

  it("opens switched off when the URL said so, with the population statement standing", () => {
    const legend = createLegend({ onFilter: () => {}, extentOn: false });
    expect(nodeBox(legend.element).checked).toBe(false);
    expect(shown(scope(legend.element))).toBe(true);
    expect(title(legend.element)).toBe("Well status · everywhere");
  });

  it("says everywhere on the collapsed pill, beside the class fraction it already states", () => {
    const legend = createLegend({ onFilter: () => {} });
    expect(title(legend.element)).toBe("Well status");
    flip(legend.element, false);
    expect(title(legend.element)).toBe("Well status · everywhere");
    boxFor(legend.element, "active").checked = false;
    boxFor(legend.element, "active").dispatchEvent(new Event("change", { bubbles: true }));
    expect(title(legend.element)).toBe(
      `Well status · ${statusIds().length - 1}/${statusIds().length} · everywhere`,
    );
  });

  it("stays out of the class filter: no onFilter call, no change to the active set", () => {
    const seen: string[][] = [];
    const legend = createLegend({ onFilter: (on) => seen.push([...on]) });
    flip(legend.element, false);
    expect(seen).toEqual([]);
    expect(legend.activeStatuses().size).toBe(filterableStatusIds().length);
  });

  it("is not touched by All or None — they speak for the status classes only", () => {
    const seen: boolean[] = [];
    const legend = createLegend({ onFilter: () => {}, onExtent: (on) => seen.push(on) });
    expand(legend.element);
    flip(legend.element, false);
    control(legend.element, "all").click();
    expect(nodeBox(legend.element).checked).toBe(false);
    flip(legend.element, true);
    control(legend.element, "none").click();
    expect(nodeBox(legend.element).checked).toBe(true);
    expect(seen).toEqual([false, true]);
  });

  it("suppresses the drawn-versus-in-view line while the node is off", () => {
    // "Showing X of Y in view" compares the canvas with the counted population; with the node
    // off the population is two basins and the sentence would be false on its face.
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 20_643, plugged: 7_316 }, 6);
    legend.setDrawn(1_204);
    expect(partial(legend.element).hidden).toBe(false);
    flip(legend.element, false);
    expect(partial(legend.element).hidden).toBe(true);
    flip(legend.element, true);
    expect(partial(legend.element).hidden).toBe(false);
  });

  it("does not collapse the key — the node is a control, like a class row", () => {
    const legend = createLegend({ onFilter: () => {} });
    expand(legend.element);
    node(legend.element).click();
    expect(legend.element.classList.contains("gw-open")).toBe(true);
  });
});

describe("the vocabulary the counts were classed by", () => {
  it("names the static pair before any answer, so the key is never unsourced", () => {
    const legend = createLegend({ onFilter: () => {} });
    expect(legend.element.textContent).toContain("cr_nd_status_vocab_1");
    expect(legend.element.textContent).toContain("cr_tx_status_vocab_1");
  });

  it("names the rules that shaped this answer, each opening the row it is", () => {
    // R8: a mapping decision is a row with a rationale and an effective date, not a string.
    const legend = createLegend({ onFilter: () => {} });
    legend.setVocabulary([
      { rule: "cr_nd_status_vocab_1", href: "/v1/conformance/cr_nd_status_vocab_1" },
    ]);
    const links = [...legend.element.querySelectorAll<HTMLAnchorElement>(".gw-lg-rule")];

    expect(links.map((link) => link.textContent)).toEqual(["cr_nd_status_vocab_1"]);
    expect(links[0]!.href).toContain("/v1/conformance/cr_nd_status_vocab_1");
    expect(legend.element.textContent).not.toContain("cr_tx_status_vocab_1");
  });

  it("opens a rule away from the map without handing it the map's window", () => {
    // A rule row is a new tab, so `rel` is load-bearing: without noreferrer the opened page
    // gets `window.opener` and can navigate this one. Classic reverse tabnabbing, and silent.
    const legend = createLegend({ onFilter: () => {} });
    legend.setVocabulary([
      { rule: "cr_nd_status_vocab_1", href: "/v1/conformance/cr_nd_status_vocab_1" },
    ]);
    const link = legend.element.querySelector<HTMLAnchorElement>(".gw-lg-rule")!;

    expect(link.target).toBe("_blank");
    expect(link.rel).toBe("noreferrer");
  });

  it("still names a rule the response did not link, rather than dropping it", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setVocabulary([{ rule: "cr_tx_status_vocab_1", href: null }]);
    expect(legend.element.textContent).toContain("cr_tx_status_vocab_1");
    expect(legend.element.querySelectorAll(".gw-lg-rule")).toHaveLength(0);
  });
});

describe("the vocabulary disclosure (visual-m12/m13: the note sat below the scroll fold)", () => {
  const vocab = (root: HTMLElement): HTMLElement => root.querySelector<HTMLElement>(".gw-lg-vocab")!;
  const title = (root: HTMLElement): HTMLButtonElement =>
    root.querySelector<HTMLButtonElement>(".gw-lg-vocab-title")!;
  const noteOf = (root: HTMLElement): HTMLElement => root.querySelector<HTMLElement>(".gw-lg-note")!;

  it("lives outside the scroll body, so the affordance is in frame whenever the key is open", () => {
    const legend = createLegend({ onFilter: () => {} });
    expect(vocab(legend.element).closest(".gw-lg-body")).toBeNull();
    expect(noteOf(legend.element).closest(".gw-lg-vocab")).not.toBeNull();
  });

  it("opens collapsed and discloses the note on its own title, stating the state", () => {
    const legend = createLegend({ onFilter: () => {} });
    expect(shown(noteOf(legend.element))).toBe(false);
    expect(title(legend.element).getAttribute("aria-expanded")).toBe("false");
    title(legend.element).click();
    expect(shown(noteOf(legend.element))).toBe(true);
    expect(title(legend.element).getAttribute("aria-expanded")).toBe("true");
    title(legend.element).click();
    expect(shown(noteOf(legend.element))).toBe(false);
  });

  it("does not collapse the legend — the disclosure is a control, not the expand target", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.element.querySelector<HTMLElement>(".gw-lg-title")?.click();
    expect(legend.element.classList.contains("gw-open")).toBe(true);
    title(legend.element).click();
    expect(legend.element.classList.contains("gw-open")).toBe(true);
  });

  it("keeps carrying the full vocabulary text, disclosure or not", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setVocabulary([{ rule: "cr_nd_status_vocab_1", href: null }]);
    expect(noteOf(legend.element).textContent).toContain("cr_nd_status_vocab_1");
    expect(noteOf(legend.element).textContent).toMatch(/TX geometry carries no provenance field/i);
  });
});

describe("the two dimensions the summary serves and the key used to discard", () => {
  const block = (root: HTMLElement, dimension: string): HTMLElement | null =>
    root.querySelector<HTMLElement>(`.gw-lg-dim[data-dimension="${dimension}"]`);
  const dimRows = (root: HTMLElement, dimension: string): HTMLElement[] => [
    ...(block(root, dimension)?.querySelectorAll<HTMLElement>(".gw-lg-drow") ?? []),
  ];
  const dimNote = (root: HTMLElement, dimension: string): string =>
    block(root, dimension)?.querySelector<HTMLElement>(".gw-lg-dnote")?.textContent ?? "";
  const counts = (order: string[], values: number[]): {
    counts: Record<string, number>;
    handles: Record<string, string>;
    order: string[];
  } => ({
    counts: Object.fromEntries(order.map((id, at) => [id, values[at]!])),
    handles: Object.fromEntries(order.map((id) => [id, `drv_test#c=${id}`])),
    order,
  });

  it("renders no block at all until the summary carries the dimension", () => {
    const legend = createLegend({ onFilter: () => {} });
    expect(shown(block(legend.element, "well_type")!)).toBe(false);
    expect(shown(block(legend.element, "geometry_provenance")!)).toBe(false);
  });

  it("lists every served well type code verbatim, in the response's own order", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 3 }, 12);
    legend.setWellTypes(counts(["OG", "SWD"], [31204, 1059]));

    expect(dimRows(legend.element, "well_type").map((row) => row.dataset["value"])).toEqual([
      "OG",
      "SWD",
    ]);
    expect(
      dimRows(legend.element, "well_type")[0]?.querySelector(".gw-lg-count")?.textContent,
    ).toBe("31,204");
  });

  it("gives a dimension row no swatch: the map draws no colour for these classes", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setWellTypes(counts(["OG"], [1]));
    legend.setProvenance(counts(["surface"], [1]));

    expect(legend.element.querySelectorAll(".gw-lg-drow .gw-lg-swatch")).toHaveLength(0);
  });

  it("carries a resolvable handle per row, so no figure on the block is naked", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 3 }, 12);
    legend.setProvenance(counts(["surface", "lateral"], [43817, 23228]));

    const handles = [
      ...legend.element.querySelectorAll<HTMLButtonElement>(
        '.gw-lg-dim[data-dimension="geometry_provenance"] .gw-lg-handle',
      ),
    ];
    expect(handles).toHaveLength(2);
    expect(handles.every((handle) => handle.dataset["handle"] !== "")).toBe(true);
  });

  it("says on the provenance block that its classes overlap and do not sum", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setProvenance(counts(["surface", "lateral"], [43817, 23228]));

    expect(dimNote(legend.element, "geometry_provenance")).toMatch(/overlap/i);
    expect(dimNote(legend.element, "geometry_provenance")).toMatch(/do not sum/i);
    expect(dimNote(legend.element, "geometry_provenance")).toContain("cr_nd_geometry_provenance_1");
  });

  it("states each block's zero rule, because the two blocks do not share one", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setWellTypes(counts(["OG"], [1]));
    legend.setProvenance(counts(["surface"], [1]));

    // The status rule: a code the box does not hold is absent rather than zero.
    expect(dimNote(legend.element, "well_type")).toMatch(/absent.*not zero|not zero/i);
    // The producing rule: a registered class the box does not hold is a zero, which is an answer.
    expect(dimNote(legend.element, "geometry_provenance")).toMatch(/zero/i);
  });

  it("withdraws the rows with the rest of the key while a request is out", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 3 }, 12);
    legend.setWellTypes(counts(["OG"], [31204]));
    expect(dimRows(legend.element, "well_type")[0]?.querySelector(".gw-lg-count")?.textContent)
      .toBe("31,204");

    legend.setPending(12);
    expect(dimRows(legend.element, "well_type")[0]?.querySelector(".gw-lg-count")?.textContent)
      .toBe("…");
    const handle = legend.element.querySelector<HTMLButtonElement>(
      '.gw-lg-dim[data-dimension="well_type"] .gw-lg-handle',
    );
    // A ⌾ over a "…" would offer to resolve a figure the cell is not showing.
    expect(handle?.hidden).toBe(true);
  });

  it("names the other scope once, so the two Wells-By surfaces are not two answers", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setWellTypes(counts(["OG"], [1]));

    const crossref = legend.element.querySelector<HTMLElement>(".gw-lg-crossref");
    expect(shown(crossref!)).toBe(true);
    expect(crossref?.textContent).toMatch(/map view/i);
    expect(crossref?.textContent).toMatch(/Wells by/i);
  });

  it("keeps both blocks and the crossref out of the scroll body, so they are always in frame", () => {
    // visual-map-wells-by D5: 575 px of new content went into a 384 px scrollport, which put
    // both blocks and the one sentence pointing at the other surface below the fold at every
    // width. The vocabulary note left that body for the same reason (visual-m12/m13).
    const legend = createLegend({ onFilter: () => {} });
    legend.setWellTypes(counts(["OG"], [1]));
    legend.setProvenance(counts(["surface"], [1]));

    expect(block(legend.element, "well_type")!.closest(".gw-lg-body")).toBeNull();
    expect(block(legend.element, "geometry_provenance")!.closest(".gw-lg-body")).toBeNull();
    expect(legend.element.querySelector(".gw-lg-crossref")!.closest(".gw-lg-body")).toBeNull();
  });

  it("opens each block on its own disclosure, shut until it is asked for", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 3 }, 12);
    legend.setWellTypes(counts(["OG", "SWD"], [31204, 1059]));
    const view = block(legend.element, "well_type")!;
    const title = view.querySelector<HTMLButtonElement>(".gw-lg-dtitle")!;
    const shownRows = view.querySelector<HTMLElement>(".gw-lg-dbody")!;

    expect(title.getAttribute("aria-expanded")).toBe("false");
    expect(shownRows.hidden).toBe(true);

    title.click();

    expect(title.getAttribute("aria-expanded")).toBe("true");
    expect(shownRows.hidden).toBe(false);
    // A control on the key, not the key's own expand target.
    expect(legend.element.classList.contains("gw-open")).toBe(false);
  });

  it("does not collapse the key when a dimension row's ⌾ is clicked", () => {
    // visual-map-wells-by D6: asking where a number came from cost the reader the key they were
    // reading and the scroll position they had reached it at.
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 3 }, 12);
    legend.setWellTypes(counts(["OG"], [31204]));
    expand(legend.element);
    expect(legend.element.classList.contains("gw-open")).toBe(true);

    dimRows(legend.element, "well_type")[0]!
      .querySelector<HTMLButtonElement>(".gw-lg-handle")!
      .click();

    expect(legend.element.classList.contains("gw-open")).toBe(true);
  });

  it("does not collapse the key when a producing row's ⌾ is clicked either", () => {
    // The same hole one class over, fixed as a class rather than for the new rows alone.
    const legend = createLegend({ onFilter: () => {} });
    legend.setCounts({ active: 3 }, 12);
    legend.setProducing({
      counts: { producing: 5 },
      handles: { producing: "drv_test#producing" },
      window: null,
      bbox: "-105,31,-102,48",
    });
    expand(legend.element);

    legend.element.querySelector<HTMLButtonElement>(".gw-lg-prow .gw-lg-handle")!.click();

    expect(legend.element.classList.contains("gw-open")).toBe(true);
  });

  it("drops the block when a later answer no longer carries the dimension", () => {
    const legend = createLegend({ onFilter: () => {} });
    legend.setProvenance(counts(["surface"], [1]));
    expect(shown(block(legend.element, "geometry_provenance")!)).toBe(true);

    legend.setProvenance(null);
    expect(shown(block(legend.element, "geometry_provenance")!)).toBe(false);
  });
});

describe("the count on the collapsed pill", () => {
  it("carries the population's own figure while nothing is filtered off", () => {
    // Not the sum of the class rows: a well the box holds under a class this key does not
    // list would be dropped from that sum without anything on screen saying so.
    const legend = createLegend({ onFilter: () => {} });
    const title = (): string => legend.element.querySelector(".gw-lg-title")!.textContent!;

    legend.setCounts({ active: 23_977, plugged: 11_841, drilling: 423 }, 12, {}, {
      wells: 52_564,
      handle: "drv_total#bbox=1",
    });

    expect(title()).toBe("Well status · 52,564");
  });

  it("moves with the filter, so the pill can never overstate the canvas", () => {
    const legend = createLegend({ on: new Set(["active"]), onFilter: () => {} });
    const title = (): string => legend.element.querySelector(".gw-lg-title")!.textContent!;

    legend.setCounts({ active: 23_977, plugged: 11_841 }, 12, {}, {
      wells: 52_564,
      handle: "drv_total#bbox=1",
    });

    expect(title()).toBe(`Well status · 1/${statusIds().length} · 23,977`);
  });

  it("says nothing while the counts are pending rather than leaving the last viewport's sum", () => {
    const legend = createLegend({ onFilter: () => {} });
    const title = (): string => legend.element.querySelector(".gw-lg-title")!.textContent!;
    legend.setCounts({ active: 23_977 }, 12, {}, { wells: 52_564, handle: "drv_total#bbox=1" });
    expect(title()).toContain("52,564");

    legend.setPending(12);

    expect(title()).toBe("Well status");
  });

  it("says nothing when every class is off, because the class ratio already says it", () => {
    const legend = createLegend({ onFilter: () => {} });
    const title = (): string => legend.element.querySelector(".gw-lg-title")!.textContent!;
    legend.setCounts({ active: 23_977 }, 12, {}, { wells: 52_564, handle: "drv_total#bbox=1" });
    expand(legend.element);

    control(legend.element, "none").click();

    expect(title()).toBe(`Well status · 0/${statusIds().length}`);
  });
});
