// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { describe, expect, it, vi } from "vitest";

import { censusOf, loadCensus, resetCensus } from "./census.ts";
import { LAYER_GROUPS } from "./groups.ts";
import { JURISDICTIONS } from "./jurisdictions.generated.ts";
import { createLayerPanel } from "./layer-panel.ts";
import { createPillStrip } from "./pills.ts";
import { LAYERS, defaultLayerSet, familyMembers, groupEntries } from "./registry.ts";

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
/** The parent is a `.gw-layer-row` so the fold gate measures it, but it is not a layer. */
const layerRows = (root: HTMLElement) => rows(root).filter((row) => row.dataset["layer"]);
const rowFor = (root: HTMLElement, id: string) => rows(root).find((row) => row.dataset["layer"] === id);
const familyOf = (root: HTMLElement, id: string) =>
  root.querySelector<HTMLElement>(`.gw-layer-family[data-family="${id}"]`)!;
const familyToggle = (root: HTMLElement, id: string) =>
  familyOf(root, id).querySelector<HTMLButtonElement>(".gw-layer-family-toggle")!;
const familyName = (root: HTMLElement, id: string) =>
  familyOf(root, id).querySelector<HTMLButtonElement>(".gw-layer-family-name")!;
const familyBody = (root: HTMLElement, id: string) =>
  familyOf(root, id).querySelector<HTMLElement>(".gw-layer-family-body")!;

describe("the layer panel", () => {
  it("renders one row per registered layer, grouped and nested, none dropped", () => {
    const { handle } = panel();
    // Every layer still has exactly one row: grouping and nesting reorder the list, and a
    // member moving under a parent never drops it from it.
    expect(layerRows(handle.element).map((row) => row.dataset["layer"]).sort()).toEqual(
      LAYERS.map((l) => l.id).sort(),
    );
    for (const { group, entries } of groupEntries()) {
      const body = handle.element.querySelector<HTMLElement>(`#gw-layer-group-${group.id}`)!;
      // Direct children only: a member sits inside its parent's body, not in the group's.
      const listed = [...body.children].map((node) =>
        node.classList.contains("gw-layer-family")
          ? `family:${(node as HTMLElement).dataset["family"]}`
          : (node as HTMLElement).dataset["layer"],
      );
      expect(listed).toEqual(
        entries.map((entry) => (entry.kind === "family" ? `family:${entry.family.id}` : entry.layer.id)),
      );
    }
  });

  it("measures the parent against the fold like any other row", () => {
    // chrome-fold.mjs computes the fold over `.gw-layer-row`. A parent that were only
    // `.gw-layer-family-head` would be the one control in the list no gate measures.
    const { handle } = panel();
    const head = handle.element.querySelector<HTMLElement>(".gw-layer-family-head")!;
    expect(head.classList.contains("gw-layer-row")).toBe(true);
    expect(head.dataset["layer"]).toBeUndefined();
  });

  it("heads each group with the reader's name for it, not the mart that publishes it", () => {
    const { handle } = panel();
    const heads = [...handle.element.querySelectorAll(".gw-layer-group-label")].map((n) => n.textContent);
    expect(heads).toEqual(LAYER_GROUPS.map((group) => group.label));
    expect(heads.join(" ")).not.toMatch(/marts\.|_tile|\bND\b|\bTX\b/);
  });

  it("carries the epistemic subtitle and the provenance badge in the row itself", () => {
    const { handle } = panel();
    const wells = rowFor(handle.element, "wells")!;
    expect(wells.querySelector(".gw-layer-sub")?.textContent).toContain("ND DMR GIS");
    expect(wells.querySelector(".gw-layer-badge")?.textContent?.toLowerCase()).toBe("official");
  });

  it("fills a Wells row's count from the served registry, with the handle that resolves it", async () => {
    // v0.76 D3: the panel said Texas held 355,463 wells while /v1/jurisdictions served
    // 359,421 in the same session, and only North Dakota's row carried a handle to ask with.
    resetCensus(
      censusOf([
        {
          jurisdiction_code: JURISDICTIONS.TX.code,
          well_count: { value: "359421", d: "drv_tx_counts#jurisdiction=TX" },
          measured_on: "2026-09-02",
          well_counts_by_status: [],
        },
      ]),
    );
    const { handle } = panel();
    await loadCensus();

    const subtitle = rowFor(handle.element, "tx-wells")!.querySelector<HTMLElement>(".gw-layer-sub")!;
    expect(subtitle.textContent).toContain("359,421 points");
    const count = subtitle.querySelector<HTMLButtonElement>(".gw-layer-count-handle")!;
    expect(count.dataset["handle"]).toBe("drv_tx_counts#jurisdiction=TX");
    expect(count.hidden).toBe(false);
    resetCensus();
  });

  it("states no number for a figure with no handle, since that is a naked number", async () => {
    // The rule the row exists to keep: a count on this panel resolves or it is not stated. The
    // wire cannot omit `d` today — the ledger's derivation_id is not null — so this is the
    // guard rather than a reproduction, and it is the one clause that makes the comment true.
    resetCensus(
      censusOf([
        {
          jurisdiction_code: JURISDICTIONS.TX.code,
          well_count: { value: "359421" },
          measured_on: "2026-09-02",
          well_counts_by_status: [],
        },
      ]),
    );
    const { handle } = panel();
    await loadCensus();

    const subtitle = rowFor(handle.element, "tx-wells")!.querySelector<HTMLElement>(".gw-layer-sub")!;
    expect(subtitle.textContent).not.toContain("359,421");
    expect(subtitle.querySelector<HTMLButtonElement>(".gw-layer-count-handle")!.hidden).toBe(true);
    resetCensus();
  });

  it("builds a count handle only for a row that states a served count", () => {
    const { handle } = panel();
    const handles = handle.element.querySelectorAll(".gw-layer-count-handle");

    expect(handles).toHaveLength(LAYERS.filter((layer) => layer.subtitle.includes("{count}")).length);
    expect(handles.length).toBeGreaterThan(0);
  });

  it("states no number in a Wells subtitle until one is served, rather than a stale literal", () => {
    resetCensus();
    const { handle } = panel();

    for (const id of ["tx-wells", "nm-wells", "mt-wells"]) {
      const subtitle = rowFor(handle.element, id)!.querySelector<HTMLElement>(".gw-layer-sub")!;
      expect(subtitle.textContent, id).not.toMatch(/\d[\d,]*\s+points/);
      expect(subtitle.textContent, id).not.toContain("{count}");
      expect(
        subtitle.querySelector<HTMLButtonElement>(".gw-layer-count-handle")!.hidden,
        id,
      ).toBe(true);
    }
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

  it("offers no disabled promise: every row the panel renders is one that can be switched on", () => {
    // The geology group shipped two stubs saying "no ingest recipe yet" for months after the
    // EIA boundaries were ingested, served and published as tiles. A row a reader cannot
    // press is a claim about the build, and this one was wrong.
    const { handle, events } = panel();
    for (const row of layerRows(handle.element)) {
      const id = row.dataset["layer"];
      expect(row.querySelector<HTMLButtonElement>(".gw-layer-toggle")!.disabled, id).toBe(false);
      expect(row.querySelector<HTMLInputElement>(".gw-layer-opacity")!.disabled, id).toBe(false);
      expect(row.textContent, id).not.toMatch(/not ingested|no ingest recipe/i);
    }
    expect(events).toEqual([]);
  });

  it("finds the boundary rows by the publisher a reader would search for", () => {
    const { handle } = panel();
    const search = handle.element.querySelector<HTMLInputElement>(".gw-layer-search")!;
    search.value = "eia";
    search.dispatchEvent(new Event("input", { bubbles: true }));

    const shown = layerRows(handle.element)
      .filter((row) => !row.hidden)
      .map((row) => row.dataset["layer"]);
    expect(shown.sort()).toEqual(["basins", "plays"]);
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

describe("a group opens on what the reader is already drawing", () => {
  const groupHead = (root: HTMLElement, id: string) =>
    root.querySelector<HTMLButtonElement>(`.gw-layer-group[data-group="${id}"] .gw-layer-group-head`)!;
  const groupBody = (root: HTMLElement, id: string) =>
    root.querySelector<HTMLElement>(`#gw-layer-group-${id}`)!;

  it("opens the group holding a layer that is on, and shuts the ones holding none", () => {
    // Twelve rows and a basemap switcher overflow the phone sheet. The groups nobody is
    // drawing from are the ones that can cost a click instead of a scroll.
    const { handle } = panel();
    expect(groupBody(handle.element, "spine").hidden).toBe(false);
    expect(groupHead(handle.element, "spine").getAttribute("aria-expanded")).toBe("true");
    expect(groupBody(handle.element, "land").hidden).toBe(true);
    expect(groupHead(handle.element, "land").getAttribute("aria-expanded")).toBe("false");
  });

  it("follows the reader's own set rather than the registry's defaults", () => {
    const { handle } = panel(["spacing-units"]);
    expect(groupBody(handle.element, "land").hidden).toBe(false);
    expect(groupBody(handle.element, "spine").hidden).toBe(true);
  });

  it("opens a shut group from its header and says so on the control", () => {
    const { handle } = panel();
    const head = groupHead(handle.element, "geology");
    head.click();
    expect(groupBody(handle.element, "geology").hidden).toBe(false);
    expect(head.getAttribute("aria-expanded")).toBe("true");
    head.click();
    expect(groupBody(handle.element, "geology").hidden).toBe(true);
  });

  it("counts the switches inside a shut group, so nothing drawn is hidden without a mark", () => {
    const { handle } = panel();
    const count = handle.element.querySelector<HTMLElement>(
      '.gw-layer-group[data-group="spine"] .gw-layer-group-count',
    )!;
    expect(count.hidden).toBe(false);
    // Derived, not pinned: a literal here reddens the day a state adds a spine layer, which
    // says nothing about whether the count is right.
    const defaults = new Set(defaultLayerSet());
    const spineOn = LAYERS.filter((layer) => layer.group === "spine" && defaults.has(layer.id));
    expect(spineOn.length).toBeGreaterThan(1);
    expect(count.textContent).toBe(`${spineOn.length} on`);
    const land = handle.element.querySelector<HTMLElement>(
      '.gw-layer-group[data-group="land"] .gw-layer-group-count',
    )!;
    expect(land.hidden).toBe(true);
    handle.setOn(new Set(["land-grid"]));
    expect(land.hidden).toBe(false);
    expect(land.textContent).toBe("1 on");
  });

  it("reaches into a shut group to show what the filter matched, and drops groups with no hit", () => {
    const { handle } = panel();
    const search = handle.element.querySelector<HTMLInputElement>(".gw-layer-search")!;
    search.value = "spacing";
    search.dispatchEvent(new Event("input"));
    expect(groupBody(handle.element, "land").hidden).toBe(false);
    expect(handle.element.querySelector<HTMLElement>('.gw-layer-group[data-group="geology"]')!.hidden).toBe(true);
    search.value = "";
    search.dispatchEvent(new Event("input"));
    // Back to the reader's own state, not to every group standing open.
    expect(groupBody(handle.element, "land").hidden).toBe(true);
    expect(handle.element.querySelector<HTMLElement>('.gw-layer-group[data-group="geology"]')!.hidden).toBe(false);
  });
});

describe("a layer that is on and painting nothing says so rather than looking drawn", () => {
  it("marks the row present but empty, and keeps the toggle live", () => {
    const { handle } = panel(["wells"]);
    handle.setZoom(9);
    handle.setCoverage(new Set(["wells"]));
    const row = rowFor(handle.element, "wells")!;
    expect(row.getAttribute("data-empty")).toBe("true");
    expect(row.querySelector<HTMLElement>(".gw-layer-empty")!.hidden).toBe(false);
    expect(row.querySelector<HTMLButtonElement>(".gw-layer-toggle")!.disabled).toBe(false);
  });

  it("says it about the canvas, never about the ground", () => {
    // A layer whose tiles failed queries empty too, so the sentence cannot claim the ground
    // is bare. The tile banner is what reports a failed source.
    const { handle } = panel(["wells"]);
    handle.setZoom(9);
    handle.setCoverage(new Set(["wells"]));
    const reason = rowFor(handle.element, "wells")!.querySelector(".gw-layer-empty-reason")!;
    expect(reason.textContent).toMatch(/drawn in this view/i);
    expect(reason.textContent).not.toMatch(/no wells|none exist|no data/i);
  });

  it("lets out of scale keep the row, since two marks would be two reasons for one blank", () => {
    const { handle } = panel(["lateral-bores"]);
    handle.setCoverage(new Set(["lateral-bores"]));
    handle.setZoom(7);
    const row = rowFor(handle.element, "lateral-bores")!;
    expect(row.getAttribute("data-out-of-scale")).toBe("true");
    expect(row.getAttribute("data-empty")).toBe(null);
  });

  it("drops the mark when the reader switches the layer off", () => {
    const { handle } = panel(["wells"]);
    handle.setZoom(9);
    handle.setCoverage(new Set(["wells"]));
    handle.setOn(new Set());
    expect(rowFor(handle.element, "wells")!.getAttribute("data-empty")).toBe(null);
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
    expect(labels).toContain("Spacing units (North Dakota)");
  });

  it("names a member by its standalone label, since no parent stands over a pill", () => {
    // The panel can shorten "Wells (Texas)" to "Texas" because the row above says Wells. A
    // pill has nothing above it, and one reading "Texas" alone would name no layer at all.
    const strip = createPillStrip({ onRemove: () => {}, onOpen: () => {} });
    strip.setOn(new Set(defaultLayerSet().filter((id) => id !== "tx-wells")));
    const labels = [...strip.element.querySelectorAll(".gw-pill-label")].map((n) => n.textContent);
    expect(labels).toContain("Wells (Texas)");
    expect(labels).not.toContain("Texas");
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

  // gate-m12 F1, the wired path: the map passes the extent node's state through, so the
  // off-state title names the toggle and not the view's width — on every row that lands on
  // the wells collection, ND and TX both (visual-m12).
  it("blames the Map view toggle when the extent node widened the box, not the view", () => {
    const { handle } = panel();
    handle.setCrossing(WORLD, "2026-08-20", true);

    for (const id of ["wells", "tx-wells"]) {
      const link = crossingIn(handle.element, id)!;
      expect(link.getAttribute("href"), id).not.toContain("f.bbox");
      expect(link.title, id).toContain("Map view is unticked");
      expect(link.title, id).not.toContain("too wide");
    }
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

describe("the row shows one line until it is asked for more", () => {
  const detailOf = (root: HTMLElement, id: string) =>
    rowFor(root, id)!.querySelector<HTMLElement>(".gw-layer-detail")!;
  const discloseOf = (root: HTMLElement, id: string) =>
    rowFor(root, id)!.querySelector<HTMLButtonElement>(".gw-layer-name")!;

  it("collapses the prose and the slider, and keeps what a glance is for", () => {
    // Measured before this landed, at 390x844: scrollHeight 1806 against clientHeight 505,
    // mean row 144 px, two rows of twelve fully above the fold — both default-on layers
    // below it. The row was the length, not the list.
    const { handle } = panel();
    const wells = rowFor(handle.element, "wells")!;
    const detail = detailOf(handle.element, "wells");

    expect(detail.hidden).toBe(true);
    for (const collapsed of [".gw-layer-sub", ".gw-layer-opacity", ".gw-layer-nocollection"]) {
      expect(detail.querySelector(collapsed), collapsed).not.toBeNull();
    }
    // The one-glance provenance claim, the switch and the label stay out of the disclosure.
    for (const kept of [".gw-layer-swatch", ".gw-layer-label", ".gw-layer-badge", ".gw-layer-toggle"]) {
      expect(wells.querySelector(kept), kept).not.toBeNull();
      expect(detail.contains(wells.querySelector(kept)), kept).toBe(false);
    }
  });

  it("keeps the out-of-scale state in the collapsed row and its reason one click in", () => {
    // Zoom gating is the panel's one working "why is this not on screen" signal, so the state
    // has to survive collapsing. The sentence does not: six of twelve rows are out of scale at
    // the opening zoom and each hint wrapped to two lines, 43 px of row apiece.
    const { handle } = panel();
    handle.setZoom(6);
    const row = rowFor(handle.element, "lateral-bores")!;
    const detail = detailOf(handle.element, "lateral-bores");
    const mark = row.querySelector<HTMLElement>(".gw-layer-scale")!;

    expect(mark.hidden).toBe(false);
    expect(detail.contains(mark)).toBe(false);
    expect(mark.textContent).toBe("zoom 8+");
    expect(row.getAttribute("data-out-of-scale")).toBe("true");
    // The sentence, and the row title that carries it, still say the whole thing.
    expect(detail.querySelector<HTMLElement>(".gw-layer-hint")!.hidden).toBe(false);
    expect(row.title).toBe("Visible at zoom 8 and above");

    handle.setZoom(9);
    expect(mark.hidden).toBe(true);
  });

  it("opens the detail from the row's own name, and says so on it", () => {
    const { handle } = panel();
    const disclose = discloseOf(handle.element, "wells");
    const detail = detailOf(handle.element, "wells");

    expect(disclose.getAttribute("aria-expanded")).toBe("false");
    expect(disclose.getAttribute("aria-controls")).toBe(detail.id);
    expect(detail.id).toBeTruthy();

    disclose.click();
    expect(detail.hidden).toBe(false);
    expect(disclose.getAttribute("aria-expanded")).toBe("true");

    disclose.click();
    expect(detail.hidden).toBe(true);
  });

  it("does not switch the layer when the reader asks what it is made of", () => {
    const { handle, events } = panel();
    discloseOf(handle.element, "spacing-units").click();
    expect(events).toEqual([]);
  });

  it("opens every row the filter matched, so search still surfaces what it matched on", () => {
    // The filter reads the per-source strings, which now live inside the disclosure — a
    // match a reader cannot see is a match that did not happen.
    const { handle } = panel();
    const search = handle.element.querySelector<HTMLInputElement>(".gw-layer-search")!;
    search.value = "tx_laterals";
    search.dispatchEvent(new Event("input", { bubbles: true }));

    const row = rowFor(handle.element, "lateral-bores")!;
    expect(row.hidden).toBe(false);
    expect(detailOf(handle.element, "lateral-bores").hidden).toBe(false);
    expect(discloseOf(handle.element, "lateral-bores").getAttribute("aria-expanded")).toBe("true");
  });

  it("re-collapses what the filter opened, and keeps what the reader opened", () => {
    const { handle } = panel();
    discloseOf(handle.element, "wells").click();
    const search = handle.element.querySelector<HTMLInputElement>(".gw-layer-search")!;
    search.value = "spacing";
    search.dispatchEvent(new Event("input", { bubbles: true }));
    search.value = "";
    search.dispatchEvent(new Event("input", { bubbles: true }));

    expect(detailOf(handle.element, "spacing-units").hidden).toBe(true);
    expect(detailOf(handle.element, "wells").hidden).toBe(false);
  });

  it("builds the disclosure once and patches it, like every other part of the row", () => {
    const { handle } = panel();
    const detail = detailOf(handle.element, "wells");
    handle.setOn(new Set(["lateral-bores"]));
    handle.setZoom(3);
    expect(detailOf(handle.element, "wells")).toBe(detail);
  });
});

describe("the panel joins the app's overlay discipline", () => {
  const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

  it("registers itself, so focus lands inside it and returns where it came from", async () => {
    const { releaseOverlays } = await import("../chrome/overlays.ts");
    releaseOverlays();
    document.body.replaceChildren();
    const opener = document.createElement("button");
    opener.className = "gw-layers-button";
    document.body.appendChild(opener);

    const { handle } = panel();
    document.body.appendChild(handle.element);
    opener.focus();

    // The observer that drives focus for every overlay runs on a microtask, so an open is
    // not focused until the turn it was requested in ends. Four other clients behave this way.
    handle.open();
    await tick();
    expect(handle.element.contains(document.activeElement)).toBe(true);

    handle.close();
    await tick();
    expect(document.activeElement).toBe(opener);
    releaseOverlays();
  });

  it("reports its open state on the control that opens it", async () => {
    const { releaseOverlays } = await import("../chrome/overlays.ts");
    releaseOverlays();
    document.body.replaceChildren();
    const opener = document.createElement("button");
    opener.className = "gw-layers-button";
    document.body.appendChild(opener);

    const { handle } = panel();
    document.body.appendChild(handle.element);
    // The control is a MapLibre IControl the panel is never handed, so the first sync waits
    // for the task that adds it to finish.
    await tick();
    expect(opener.getAttribute("aria-expanded")).toBe("false");
    expect(opener.getAttribute("aria-controls")).toBe(handle.element.id);

    handle.toggle();
    await tick();
    expect(opener.getAttribute("aria-expanded")).toBe("true");

    // Escape closes it from main.ts's ladder, which reaches the element rather than the
    // handle — the announcement has to follow the attribute, not the call.
    handle.element.hidden = true;
    await tick();
    expect(opener.getAttribute("aria-expanded")).toBe("false");
    releaseOverlays();
  });
});

describe("the row's provenance handles are the app's, not a third dialect", () => {
  it("raises the explain event from the geometry derivation, as the legend and the key do", () => {
    const { handle } = panel();
    const seen: string[] = [];
    handle.element.addEventListener("gw-explain", (event) =>
      seen.push((event as CustomEvent<{ handle: string }>).detail.handle),
    );

    handle.setProvenance("wells", "drv_01J9");
    const node = rowFor(handle.element, "wells")!.querySelector<HTMLButtonElement>(".gw-layer-derivation")!;
    expect(node.tagName).toBe("BUTTON");
    expect(node.className).toContain("gw-handle");
    node.click();
    expect(seen).toEqual(["drv_01J9"]);
  });

  it("resolves the snapshot the row's own counts were read at", () => {
    const { handle } = panel();
    const seen: string[] = [];
    handle.element.addEventListener("gw-explain", (event) =>
      seen.push((event as CustomEvent<{ handle: string }>).detail.handle),
    );

    for (const id of ["wells", "disposal-wells", "survey-traces", "land-metrics"]) {
      const node = rowFor(handle.element, id)!.querySelector<HTMLButtonElement>(".gw-layer-snapshot");
      expect(node, id).not.toBeNull();
      node!.click();
    }
    expect([...seen].sort()).toEqual(
      LAYERS.filter((layer) => layer.snapshot)
        .map((layer) => layer.snapshot)
        .sort(),
    );
    // Two refreshes, four rows: the wells mart's and the land mart's, neither hand-written.
    expect(new Set(seen).size).toBe(2);
  });

  it("offers no snapshot handle on a row whose counts have none", () => {
    const { handle } = panel();
    expect(rowFor(handle.element, "tx-wells")!.querySelector(".gw-layer-snapshot")).toBeNull();
  });
});

describe("the wells parent", () => {
  const MEMBERS = familyMembers("wells").map((layer) => layer.id);

  it("stands one parent over the state rows, with its members shut on first paint", () => {
    // Nesting adds a row; collapsing it removes four. The four rows a reader who does not
    // care which state would otherwise scroll past are the four this buys back.
    const { handle } = panel();
    expect(familyBody(handle.element, "wells").hidden).toBe(true);
    expect(familyName(handle.element, "wells").getAttribute("aria-expanded")).toBe("false");
    expect(
      [...familyBody(handle.element, "wells").children].map((n) => (n as HTMLElement).dataset["layer"]),
    ).toEqual(MEMBERS);
  });

  it("reads each member by its state, and never repeats the noun the parent carries", () => {
    const { handle } = panel();
    const labels = [...familyBody(handle.element, "wells").querySelectorAll(".gw-layer-label")].map(
      (node) => node.textContent,
    );
    expect(labels).toEqual(["North Dakota", "Texas", "New Mexico", "Montana", "Colorado"]);
    expect(
      familyOf(handle.element, "wells").querySelector(".gw-layer-family-name .gw-layer-label")!
        .textContent,
    ).toBe("Wells");
  });

  it("keeps the standalone name on the controls a screen reader meets on their own", () => {
    // The visible label is shortened by the row above it; a switch announced as "Show Texas"
    // would have lost the only word saying what is being shown.
    const { handle } = panel();
    const row = rowFor(handle.element, "tx-wells")!;
    expect(row.querySelector(".gw-layer-toggle")!.getAttribute("aria-label")).toBe(
      "Show Wells (Texas)",
    );
    expect(row.querySelector(".gw-layer-opacity")!.getAttribute("aria-label")).toBe(
      "Wells (Texas) opacity",
    );
  });

  it("reports all on, all off and some on as three distinct states of one switch", () => {
    const { handle } = panel();
    const toggle = familyToggle(handle.element, "wells");
    expect(toggle.getAttribute("aria-pressed")).toBe("true");

    handle.setOn(new Set(["wells", "tx-wells"]));
    expect(toggle.getAttribute("aria-pressed")).toBe("mixed");

    handle.setOn(new Set());
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
  });

  it("says how many of how many while it is mixed, and stays quiet when it is not", () => {
    const { handle } = panel();
    const count = familyOf(handle.element, "wells").querySelector<HTMLElement>(
      ".gw-layer-family-count",
    )!;
    expect(count.hidden).toBe(true);

    handle.setOn(new Set(["wells", "tx-wells"]));
    expect(count.hidden).toBe(false);
    expect(count.textContent).toBe(`2 of ${MEMBERS.length}`);

    handle.setOn(new Set(MEMBERS));
    expect(count.hidden).toBe(true);
  });

  it("resolves a mixed parent upward, then falls to all off — mixed is never a destination", () => {
    const { handle, events } = panel();
    const toggle = familyToggle(handle.element, "wells");

    handle.setOn(new Set(["wells"]));
    toggle.click();
    expect(events.splice(0)).toEqual(MEMBERS.map((id) => ({ id, on: true })));

    handle.setOn(new Set(MEMBERS));
    toggle.click();
    expect(events.splice(0)).toEqual(MEMBERS.map((id) => ({ id, on: false })));

    handle.setOn(new Set());
    toggle.click();
    expect(events.splice(0)).toEqual(MEMBERS.map((id) => ({ id, on: true })));
  });

  it("switches nothing outside the family, in either direction", () => {
    const { handle, events } = panel();
    familyToggle(handle.element, "wells").click();
    expect(events.map((event) => event.id).sort()).toEqual([...MEMBERS].sort());
  });

  it("mutates the map through the same callback a member's own switch uses", () => {
    // The parent is a control over four switches, not a fifth layer: it owns no id, writes
    // nothing of its own, and every effect it has reaches the map as four ordinary toggles.
    const { handle, events } = panel();
    handle.setOn(new Set());
    familyToggle(handle.element, "wells").click();
    const viaParent = events.splice(0);
    for (const id of MEMBERS) rowFor(handle.element, id)!.querySelector<HTMLButtonElement>(
      ".gw-layer-toggle",
    )!.click();
    expect(events).toEqual(viaParent);
  });

  it("opens and shuts the members from the parent's own name, and says so on it", () => {
    const { handle } = panel();
    const name = familyName(handle.element, "wells");
    name.click();
    expect(familyBody(handle.element, "wells").hidden).toBe(false);
    expect(name.getAttribute("aria-expanded")).toBe("true");
    expect(name.getAttribute("aria-controls")).toBe(familyBody(handle.element, "wells").id);
    name.click();
    expect(familyBody(handle.element, "wells").hidden).toBe(true);
  });

  it("does not switch the family when the reader asks which states are in it", () => {
    const { handle, events } = panel();
    familyName(handle.element, "wells").click();
    expect(events).toEqual([]);
  });

  it("reaches into a shut family to show what the filter matched", () => {
    const { handle } = panel();
    const search = handle.element.querySelector<HTMLInputElement>(".gw-layer-search")!;
    search.value = "montana";
    search.dispatchEvent(new Event("input"));

    expect(familyOf(handle.element, "wells").hidden).toBe(false);
    expect(familyBody(handle.element, "wells").hidden).toBe(false);
    expect(rowFor(handle.element, "mt-wells")!.hidden).toBe(false);
    expect(rowFor(handle.element, "tx-wells")!.hidden).toBe(true);
  });

  it("drops the parent when nothing inside it matched, rather than heading an empty list", () => {
    const { handle } = panel();
    const search = handle.element.querySelector<HTMLInputElement>(".gw-layer-search")!;
    search.value = "spacing";
    search.dispatchEvent(new Event("input"));
    expect(familyOf(handle.element, "wells").hidden).toBe(true);
  });

  it("finds a state by its name now the label spells it out", () => {
    // Before this the haystack held "Wells (TX)": typing "texas" matched nothing, while
    // "montana" matched only because the Montana subtitle happened to spell it.
    const { handle } = panel();
    const search = handle.element.querySelector<HTMLInputElement>(".gw-layer-search")!;
    for (const [term, id] of [["texas", "tx-wells"], ["new mexico", "nm-wells"]] as const) {
      search.value = term;
      search.dispatchEvent(new Event("input"));
      expect(rowFor(handle.element, id)!.hidden, term).toBe(false);
    }
  });

  it("says none here on the parent only when every state it is drawing drew nothing", () => {
    // The present-but-empty state the panel already models, aggregated honestly: Montana and
    // New Mexico are ingested and zero today, so a reader over the Permian has two members
    // painting nothing and one painting. That is not an empty family.
    const { handle } = panel();
    const mark = familyOf(handle.element, "wells").querySelector<HTMLElement>(".gw-layer-empty")!;
    handle.setZoom(9);
    expect(mark.hidden).toBe(true);

    handle.setCoverage(new Set(["nm-wells", "mt-wells"]));
    expect(mark.hidden).toBe(true);

    handle.setCoverage(new Set(MEMBERS));
    expect(mark.hidden).toBe(false);

    // A member nobody is drawing cannot hold the family empty.
    handle.setOn(new Set(["wells"]));
    handle.setCoverage(new Set(["nm-wells", "mt-wells"]));
    expect(mark.hidden).toBe(true);
  });

  it("counts a shut family's members one by one on the group header", () => {
    // Four switches behind one shut parent may not read as one. The group count is what the
    // reader has while the family is closed, so it counts layers and not families.
    const { handle } = panel();
    const count = handle.element.querySelector<HTMLElement>(
      '.gw-layer-group[data-group="spine"] .gw-layer-group-count',
    )!;
    handle.setOn(new Set(MEMBERS));
    expect(count.textContent).toBe(`${MEMBERS.length} on`);
  });
});

describe("the panel's own layout contract, read off the shipped sheets", () => {
  // happy-dom lays nothing out; what is pinnable here is the declaration each measured
  // defect was fixed by. tests/e2e measures the result. The idiom is surfaces.test.ts's.
  const MAP = readFileSync("src/map.css", "utf8");
  const PANEL = readFileSync("src/map/layer-panel.css", "utf8");
  const rule = (css: string, selector: string): string => {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp(`(^|\\})[^{}]*?${escaped}\\s*\\{[^}]*\\}`, "m").exec(css)?.[0] ?? "";
  };

  it("stops capping the panel at 34rem on a screen with room for the list", () => {
    // 544 px against 1,849 px of rows threw away 390 px of available height at 1600x1000.
    expect(rule(MAP, ".gw-sheet")).toContain("max-height: calc(100% - 1.2rem)");
    expect(rule(MAP, ".gw-sheet")).not.toContain("34rem");
  });

  it("clears the map's own control column instead of covering the button that opens it", () => {
    // Measured at 1600x1000: a 19.6 x 29 px intersection with .gw-layers-button, which is
    // also the close control — the frame read "ayers".
    const offset = /\.gw-sheet\s*\{[^}]*right:\s*([\d.]+)rem/.exec(MAP)?.[1];
    expect(offset).toBeTruthy();
    expect(Number(offset)).toBeGreaterThan(4.625);
  });

  it("meets the target floor on the switch, which the row's min-height never was", () => {
    // layer-panel.ts keeps the row out of a <label> on purpose, so the row's 44 px is not a
    // hit area and the switch is the whole target. It measured 34 x 20.
    const toggle = rule(MAP, ".gw-layer-toggle");
    expect(Number(/width:\s*(\d+)px/.exec(toggle)?.[1])).toBeGreaterThanOrEqual(24);
    expect(Number(/height:\s*(\d+)px/.exec(toggle)?.[1])).toBeGreaterThanOrEqual(24);
  });

  it("lets the basemap focus ring out of the switcher that holds its radius", () => {
    expect(rule(MAP, ".gw-base-switcher")).not.toMatch(/overflow:\s*hidden/);
    expect(rule(MAP, ".gw-base-switcher")).toMatch(/overflow:\s*clip/);
  });

  it("keeps the bottom sheet off the home indicator, as the card and the drawer do", () => {
    const sheet = /@media \(width <= 768px\) \{[\s\S]*?\n\}/.exec(MAP)?.[0] ?? "";
    expect(sheet).toContain("env(safe-area-inset-bottom)");
  });

  it("lets the hidden attribute win on every collapsible the panel shuts", () => {
    // The defect .gw-layer-crossing already carries a note about: a bare `display` outranks
    // the UA's `[hidden] { display: none }`. Read over every element this module sets `hidden`
    // on rather than the one that had the bug, because the next disclosure added is the one
    // that will have it. A base rule may instead be answered by an explicit `[hidden]`
    // override, which is how .gw-layer-row settles it. style.css's global `!important` reset
    // covers all of them at runtime; this holds the sheet's own convention so a rule cannot
    // come to depend on that reset silently.
    const css = `${MAP}\n${PANEL}`.replace(/\/\*[\s\S]*?\*\//g, "");
    const shut = [".gw-layer-detail", ".gw-layer-family-body", ".gw-layer-group-body", ".gw-layer-row"];
    for (const match of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      const selector = (match[1] ?? "").trim();
      const base = shut.find((candidate) => selector.startsWith(candidate));
      if (!base || !/display\s*:/.test(match[2] ?? "")) continue;
      if (selector.includes(":not([hidden])") || selector.includes("[hidden]")) continue;
      const override = new RegExp(`\\${base}\\[hidden\\]\\s*\\{[^}]*display\\s*:\\s*none`);
      expect(override.test(css), `${selector} sets display and nothing re-hides it`).toBe(true);
    }
  });
});
