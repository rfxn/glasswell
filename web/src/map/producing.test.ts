// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import { EXPLAIN_EVENT } from "../chrome/handle.ts";
import { createLegend } from "./legend.ts";
import { PRODUCING_CLASSES, PRODUCING_RULES, producingLabel } from "./producing.ts";

const BOX = "-104,47,-103,48";

const section = (root: HTMLElement): HTMLElement =>
  root.querySelector<HTMLElement>(".gw-lg-producing")!;
const rowFor = (root: HTMLElement, id: string): HTMLElement =>
  root.querySelector<HTMLElement>(`.gw-lg-prow[data-producing="${id}"]`)!;
const countFor = (root: HTMLElement, id: string): string =>
  rowFor(root, id).querySelector<HTMLElement>(".gw-lg-count")!.textContent ?? "";
const linkFor = (root: HTMLElement, id: string): HTMLAnchorElement =>
  rowFor(root, id).querySelector<HTMLAnchorElement>("a")!;
const handleFor = (root: HTMLElement, id: string): HTMLButtonElement =>
  rowFor(root, id).querySelector<HTMLButtonElement>(".gw-lg-handle")!;
const shown = (element: HTMLElement): boolean =>
  element.hidden === false && element.hasAttribute("hidden") === false;

const legend = () => createLegend({ onFilter: () => {} });

const WINDOW = {
  months: 3,
  from: "2026-01-01",
  to: "2026-03-01",
  streams: ["gas", "oil"],
  liquids_basis: "oil+condensate",
};

describe("the producing classes", () => {
  it("names the three the data can distinguish and no fourth", () => {
    expect(PRODUCING_CLASSES.map((entry) => entry.id)).toEqual([
      "producing",
      "not_producing",
      "unknown",
    ]);
  });

  it("never labels a class in a way that implies the status vocabulary", () => {
    // `active` is the regulator's word about a permit. Reusing it here would merge the two
    // facts the whole feature exists to separate.
    for (const entry of PRODUCING_CLASSES) {
      expect(entry.label.toLowerCase()).not.toContain("active");
    }
  });

  it("says of the unknown class that it is an absence and not a zero", () => {
    expect(producingLabel("unknown").note).toMatch(/withheld|no filing|lease/i);
  });

  it("cites the rules that define it", () => {
    expect(PRODUCING_RULES).toContain("cr_producing_window_1");
    expect(PRODUCING_RULES).toContain("cr_producing_streams_1");
    expect(PRODUCING_RULES).toContain("cr_producing_evidence_1");
  });
});

describe("the legend's producing section", () => {
  it("stays hidden until a summary has classed the box", () => {
    const { element } = legend();

    expect(shown(section(element))).toBe(false);
  });

  it("reports each class the box holds, formatted", () => {
    const { element, setProducing } = legend();

    setProducing({ counts: { producing: 18980, not_producing: 437 }, handles: {}, window: WINDOW, bbox: BOX });

    expect(shown(section(element))).toBe(true);
    expect(countFor(element, "producing")).toBe("18,980");
    expect(countFor(element, "not_producing")).toBe("437");
  });

  it("reads a class the box does not hold as absent, never as zero", () => {
    const { element, setProducing } = legend();

    setProducing({ counts: { producing: 12 }, handles: {}, window: WINDOW, bbox: BOX });

    expect(countFor(element, "unknown")).toBe("—");
  });

  it("states the window and the liquids basis beside the numbers", () => {
    const { element, setProducing } = legend();

    setProducing({ counts: { producing: 12 }, handles: {}, window: WINDOW, bbox: BOX });
    const note = section(element).querySelector<HTMLElement>(".gw-lg-pnote")!;

    expect(note.textContent).toContain("2026-01-01");
    expect(note.textContent).toContain("2026-03-01");
    expect(note.textContent).toContain("oil+condensate");
    // The two standing rulings are the same claim, folded: they do not vary by window, so
    // they sit under the summary rather than repeating inside it on every open.
    const rulings = section(element).querySelector<HTMLElement>(".gw-note-detail");
    expect(rulings?.textContent).toMatch(/water/i);
    expect(rulings?.textContent).toMatch(/regulator calls the well/i);
  });

  it("raises the explain event for the count's own handle", () => {
    const { element, setProducing } = legend();
    setProducing({
      counts: { producing: 12 },
      handles: { producing: "drv_abc" },
      window: WINDOW,
      bbox: BOX,
    });

    let seen: string | null = null;
    element.addEventListener(EXPLAIN_EVENT, (event) => {
      seen = (event as CustomEvent<{ handle: string }>).detail.handle;
    });
    handleFor(element, "producing").click();

    expect(seen).toBe("drv_abc");
  });

  it("hides the handle of a count that carries none", () => {
    const { element, setProducing } = legend();

    setProducing({ counts: { producing: 12 }, handles: {}, window: WINDOW, bbox: BOX });

    expect(shown(handleFor(element, "producing"))).toBe(false);
  });

  it("links each class to the wells the count is of, scoped to the same box", () => {
    const { element, setProducing } = legend();

    setProducing({ counts: { producing: 12 }, handles: {}, window: WINDOW, bbox: BOX });
    const href = linkFor(element, "producing").getAttribute("href") ?? "";

    expect(href).toContain("producing=producing");
    expect(href).toContain(`bbox=${encodeURIComponent(BOX)}`);
  });

  it("drops the previous viewport's numbers rather than dimming them", () => {
    const { element, setProducing, setPending } = legend();
    setProducing({ counts: { producing: 12 }, handles: {}, window: WINDOW, bbox: BOX });

    setPending(6);

    expect(countFor(element, "producing")).toBe("…");
  });

  it("withdraws the section when a box carries no producing definition at all", () => {
    const { element, setProducing } = legend();
    setProducing({ counts: { producing: 12 }, handles: {}, window: WINDOW, bbox: BOX });

    setProducing(null);

    expect(shown(section(element))).toBe(false);
  });
});
