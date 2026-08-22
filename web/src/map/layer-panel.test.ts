// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { describe, expect, it, vi } from "vitest";

import { createLayerPanel } from "./layer-panel.ts";
import { createPillStrip } from "./pills.ts";
import { LAYERS, defaultLayerSet } from "./registry.ts";

const panel = (on: string[] = defaultLayerSet()) => {
  const events: { id: string; on: boolean }[] = [];
  const opacity: { id: string; value: number }[] = [];
  const handle = createLayerPanel({
    on: new Set(on),
    onToggle: (id, next) => events.push({ id, on: next }),
    onOpacity: (id, value) => opacity.push({ id, value }),
    onBasemap: () => {},
    basemap: "dark",
  });
  return { handle, events, opacity };
};

const rows = (root: HTMLElement) => [...root.querySelectorAll<HTMLElement>(".gw-layer-row")];
const rowFor = (root: HTMLElement, id: string) => rows(root).find((row) => row.dataset["layer"] === id);

describe("the layer panel", () => {
  it("renders one row per registered layer, in draw order", () => {
    const { handle } = panel();
    expect(rows(handle.element).map((row) => row.dataset["layer"])).toEqual(LAYERS.map((l) => l.id));
  });

  it("carries the epistemic subtitle and the provenance badge in the row itself", () => {
    const { handle } = panel();
    const wells = rowFor(handle.element, "wells")!;
    expect(wells.querySelector(".gw-layer-sub")?.textContent).toContain("ND DMR GIS");
    expect(wells.querySelector(".gw-layer-badge")?.textContent?.toLowerCase()).toBe("official");
  });

  it("names both regulators under the one row that draws both of their files", () => {
    // One toggle, two sources. The subtitle can carry the claim they share; it cannot carry
    // which file a line came from, so each source gets its own line under the row.
    const { handle } = panel();
    const row = rowFor(handle.element, "lateral-bores")!;
    const sources = [...row.querySelectorAll(".gw-layer-source")].map((node) => node.textContent);
    expect(sources).toHaveLength(2);
    expect(sources[0]).toContain("ND DMR");
    expect(sources[0]).toContain("marts.nd_laterals_tile");
    expect(sources[1]).toContain("TX RRC");
    expect(sources[1]).toContain("marts.tx_laterals_tile");
    expect(row.querySelector(".gw-layer-sub")?.textContent).toMatch(/not a directional survey/i);
  });

  it("leaves a single-source row with no provenance line, since its subtitle already names one", () => {
    const { handle } = panel();
    expect(rowFor(handle.element, "wells")!.querySelectorAll(".gw-layer-source")).toHaveLength(0);
  });

  it("tells the reader why the laterals row is dark at basin zoom", () => {
    const { handle } = panel();
    handle.setZoom(7);
    const row = rowFor(handle.element, "lateral-bores")!;
    expect(row.getAttribute("data-out-of-scale")).toBe("true");
    expect(row.textContent).toMatch(/zoom 8/i);
    handle.setZoom(8);
    expect(row.getAttribute("data-out-of-scale")).toBe(null);
  });

  it("disables a stub layer and says the source is not ingested", () => {
    const { handle, events } = panel();
    const play = rowFor(handle.element, "play-outline")!;
    const toggle = play.querySelector<HTMLButtonElement>(".gw-layer-toggle")!;
    expect(toggle.disabled).toBe(true);
    toggle.click();
    expect(events).toEqual([]);
    expect(play.textContent).toMatch(/not ingested|no ingest recipe/i);
  });

  it("reports a toggle rather than mutating the map itself", () => {
    const { handle, events } = panel();
    rowFor(handle.element, "spacing-units")!.querySelector<HTMLButtonElement>(".gw-layer-toggle")!.click();
    expect(events).toEqual([{ id: "spacing-units", on: true }]);
  });

  it("keeps aria-pressed in step with the visible state", () => {
    const { handle } = panel();
    const toggle = rowFor(handle.element, "wells")!.querySelector<HTMLButtonElement>(".gw-layer-toggle")!;
    expect(toggle.getAttribute("aria-pressed")).toBe("true");
    handle.setOn(new Set(["lateral-bores"]));
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
  });

  it("patches state in place instead of re-rendering the list", () => {
    const { handle } = panel();
    const toggle = rowFor(handle.element, "wells")!.querySelector(".gw-layer-toggle");
    handle.setOn(new Set(["lateral-bores"]));
    expect(rowFor(handle.element, "wells")!.querySelector(".gw-layer-toggle")).toBe(toggle);
  });

  it("offers per-layer opacity", () => {
    const { handle, opacity } = panel();
    const slider = rowFor(handle.element, "wells")!.querySelector<HTMLInputElement>("input[type=range]")!;
    slider.value = "40";
    slider.dispatchEvent(new Event("input", { bubbles: true }));
    expect(opacity).toEqual([{ id: "wells", value: 0.4 }]);
  });

  it("filters the list by label and by subtitle", () => {
    const { handle } = panel();
    const search = handle.element.querySelector<HTMLInputElement>(".gw-layer-search")!;
    search.value = "spacing";
    search.dispatchEvent(new Event("input", { bubbles: true }));
    const shown = rows(handle.element).filter((row) => !row.hidden).map((row) => row.dataset["layer"]);
    expect(shown).toContain("spacing-units");
    expect(shown).not.toContain("lateral-bores");
  });

  it("marks a row out of scale when the map is zoomed out past its floor", () => {
    const { handle } = panel();
    handle.setZoom(6);
    const spacing = rowFor(handle.element, "spacing-units")!;
    expect(spacing.getAttribute("data-out-of-scale")).toBe("true");
    expect(spacing.textContent).toMatch(/zoom 8/i);
  });

  it("shows the geometry derivation handle once a tile has reported one", () => {
    const { handle } = panel();
    handle.setProvenance("wells", "der_01J9");
    expect(rowFor(handle.element, "wells")!.querySelector(".gw-layer-derivation")?.textContent).toContain(
      "der_01J9",
    );
  });

  it("resets to the registry defaults, not to a second hand-written list", () => {
    const seen: Set<string>[] = [];
    const handle = createLayerPanel({
      on: new Set(["spacing-units"]),
      onToggle: () => {},
      onOpacity: () => {},
      onBasemap: () => {},
      onReset: (next) => seen.push(next),
      basemap: "dark",
    });
    handle.element.querySelector<HTMLButtonElement>(".gw-layer-reset")!.click();
    expect([...(seen[0] ?? [])].sort()).toEqual([...defaultLayerSet()].sort());
  });

  it("groups the basemap switcher above the overlays and reports the chosen id", () => {
    const chosen: string[] = [];
    const handle = createLayerPanel({
      on: new Set(),
      onToggle: () => {},
      onOpacity: () => {},
      onBasemap: (id) => chosen.push(id),
      basemap: "dark",
    });
    const light = handle.element.querySelector<HTMLButtonElement>('.gw-base-option[data-base="light"]')!;
    expect(light.getAttribute("aria-pressed")).toBe("false");
    light.click();
    expect(chosen).toEqual(["light"]);
  });
});

describe("the active-layer pill strip", () => {
  it("names every layer that is on, and hides itself when only the defaults are", () => {
    const removed: string[] = [];
    const strip = createPillStrip({ onRemove: (id) => removed.push(id), onOpen: () => {} });
    strip.setOn(new Set(defaultLayerSet()));
    expect(strip.element.hidden).toBe(true);

    strip.setOn(new Set([...defaultLayerSet(), "spacing-units"]));
    expect(strip.element.hidden).toBe(false);
    const labels = [...strip.element.querySelectorAll(".gw-pill-label")].map((n) => n.textContent);
    expect(labels).toContain("Spacing units");
  });

  it("skips an id this build no longer offers instead of drawing a pill nothing can remove", () => {
    // A shared link from before the lateral rows were combined carries both retired ids.
    const strip = createPillStrip({ onRemove: () => {}, onOpen: () => {} });
    strip.setOn(new Set([...defaultLayerSet(), "laterals", "tx-laterals", "lateral-bores"]));
    const shown = [...strip.element.querySelectorAll(".gw-pill[data-layer]")].map(
      (node) => (node as HTMLElement).dataset["layer"],
    );
    expect(shown).toEqual(["lateral-bores"]);
  });

  it("removes a layer from the strip itself", () => {
    const removed: string[] = [];
    const strip = createPillStrip({ onRemove: (id) => removed.push(id), onOpen: () => {} });
    strip.setOn(new Set([...defaultLayerSet(), "spacing-units"]));
    strip.element.querySelector<HTMLButtonElement>('.gw-pill[data-layer="spacing-units"] .gw-pill-x')!.click();
    expect(removed).toEqual(["spacing-units"]);
  });

  it("ends in an add pill that reopens the panel", () => {
    const open = vi.fn();
    const strip = createPillStrip({ onRemove: () => {}, onOpen: open });
    strip.setOn(new Set([...defaultLayerSet(), "spacing-units"]));
    strip.element.querySelector<HTMLButtonElement>(".gw-pill-add")!.click();
    expect(open).toHaveBeenCalled();
  });
});

describe("SB-08 §2.6 — the crossing from a layer to the collection behind it", () => {
  const TIGHT = [-103.5, 47.5, -102.5, 48.2] as const;
  const WORLD = [-180, -85, 180, 85] as const;

  const crossingIn = (root: HTMLElement, id: string) =>
    rowFor(root, id)?.querySelector<HTMLAnchorElement>(".gw-layer-crossing");

  it("offers no crossing until a viewport has been reported", () => {
    const { handle } = panel();
    expect(crossingIn(handle.element, "wells")?.hidden).toBe(true);
  });

  it("lands the wells row on the wells collection, narrowed to the current box", () => {
    const { handle } = panel();
    handle.setCrossing(TIGHT, "2026-08-20");
    const link = crossingIn(handle.element, "wells")!;

    expect(link.hidden).toBe(false);
    expect(link.getAttribute("href")).toContain("ds=wells");
    expect(link.getAttribute("href")).toContain("f.bbox=-103.5%2C47.5%2C-102.5%2C48.2");
    expect(link.getAttribute("href")).toContain("as_of=2026-08-20");
  });

  it("rebuilds the link when the reader pans, so it never names the viewport they left", () => {
    const { handle } = panel();
    handle.setCrossing(TIGHT, "2026-08-20");
    const first = crossingIn(handle.element, "wells")!.getAttribute("href");
    handle.setCrossing([-104, 47, -103, 48], "2026-08-20");

    expect(crossingIn(handle.element, "wells")!.getAttribute("href")).not.toBe(first);
  });

  it("drops the box rather than sending one the server caps, and says the view is too wide", () => {
    const { handle } = panel();
    handle.setCrossing(WORLD, "2026-08-20");
    const link = crossingIn(handle.element, "wells")!;

    expect(link.getAttribute("href")).not.toContain("f.bbox");
    expect(link.title).toContain("too wide");
  });

  it("states the absence on a layer no served collection carries, and offers no link", () => {
    const { handle } = panel();
    handle.setCrossing(TIGHT, "2026-08-20");
    const laterals = rowFor(handle.element, "lateral-bores")!;

    expect(crossingIn(handle.element, "lateral-bores")?.hidden).toBe(true);
    expect(laterals.querySelector(".gw-layer-nocollection")?.textContent).toContain(
      "No served collection",
    );
  });

  it("carries the reader's own pin over the resolved one", () => {
    window.history.replaceState(null, "", "/?view=map&as_of=2026-07-01");
    const { handle } = panel();
    handle.setCrossing(TIGHT, "2026-08-20");

    expect(crossingIn(handle.element, "wells")!.getAttribute("href")).toContain("as_of=2026-07-01");
    window.history.replaceState(null, "", "/");
  });

  it("lets the hidden attribute win, so no arrow paints on a row with no collection", () => {
    // vitest loads no stylesheet, so the rule is read off the shipped sheet — the same idiom
    // explore/grid/styles.test.ts uses, applied to the sheet it does not scan. The frames
    // caught this one: `display: inline-flex` outranked `[hidden]` and every tile-only row
    // drew a crossing arrow above the line saying it has nowhere to cross to.
    const css = readFileSync("src/map/layer-panel.css", "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    const owning = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
      .map((match) => ({ selector: (match[1] ?? "").trim(), body: match[2] ?? "" }))
      .filter((rule) => rule.selector.startsWith(".gw-layer-crossing"));

    expect(owning.length).toBeGreaterThan(0);
    for (const rule of owning) {
      if (!/display\s*:/.test(rule.body)) continue;
      expect(rule.selector, rule.selector).toContain(":not([hidden])");
    }
  });

  /**
   * The counts request is the map's only reading of the vintage, and its error branch leaves
   * the map with none. On a degraded instance that is not a race — it is every rebuild for the
   * rest of the session — so the row states the absence rather than handing over a link that
   * answers differently after the next vintage lands (gate-c10 B1, SB-08 M6).
   */
  it("offers no link at all while the map has resolved no vintage, and says why", () => {
    const { handle } = panel();
    handle.setCrossing(TIGHT, null);
    const link = crossingIn(handle.element, "wells")!;

    expect(link.hidden).toBe(false);
    expect(link.getAttribute("href")).toBeNull();
    expect(link.getAttribute("aria-disabled")).toBe("true");
    expect(link.textContent).toContain("no vintage yet");
    expect(link.title).toContain("would answer differently");
  });

  it("does not cross on a click while it has no vintage, so the address bar cannot drift", () => {
    const { handle } = panel();
    handle.setCrossing(TIGHT, null);
    const push = vi.spyOn(window.history, "pushState");

    crossingIn(handle.element, "wells")!.dispatchEvent(
      new MouseEvent("click", { bubbles: true, cancelable: true }),
    );

    expect(push).not.toHaveBeenCalled();
    push.mockRestore();
  });

  it("becomes a real link the moment a vintage lands, which is the pre-settle window closing", () => {
    const { handle } = panel();
    handle.setCrossing(TIGHT, null);
    handle.setCrossing(TIGHT, "2026-08-20");
    const link = crossingIn(handle.element, "wells")!;

    expect(link.getAttribute("href")).toContain("as_of=2026-08-20");
    expect(link.hasAttribute("aria-disabled")).toBe(false);
    expect(link.hasAttribute("data-unpinned")).toBe(false);
    expect(link.textContent).toBe("What is behind this layer");
  });

  it("keeps the reader's own pin working on a degraded map, which resolves nothing at all", () => {
    window.history.replaceState(null, "", "/?view=map&as_of=2026-07-01");
    const { handle } = panel();
    handle.setCrossing(TIGHT, null);
    const link = crossingIn(handle.element, "wells")!;

    expect(link.getAttribute("href")).toContain("as_of=2026-07-01");
    expect(link.hasAttribute("aria-disabled")).toBe(false);
    window.history.replaceState(null, "", "/");
  });

  it("crosses in place on a plain click rather than reloading the document", () => {
    const { handle } = panel();
    handle.setCrossing(TIGHT, "2026-08-20");
    const link = crossingIn(handle.element, "wells")!;
    const push = vi.spyOn(window.history, "pushState");

    link.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));

    expect(push).toHaveBeenCalledTimes(1);
    push.mockRestore();
  });
});
