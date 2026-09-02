// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LayerSpecification, StyleSpecification } from "maplibre-gl";

vi.mock("../chrome/status.ts", () => ({ toast: vi.fn() }));
vi.mock("../app/state.ts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../app/state.ts")>();
  return { ...actual, readState: vi.fn(actual.readState) };
});
vi.mock("./counts.ts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./counts.ts")>();
  return { ...actual, createCountSource: () => ({ request: vi.fn() }) };
});

type Handler = (event?: unknown) => void;

/** Every `setFilter` the map wrote, in order, so a clobber shows up as the last write. */
const writes: { layer: string; filter: unknown }[] = [];
const handlers = new Map<string, Handler[]>();
let transformStyle: ((previous: unknown, next: StyleSpecification) => StyleSpecification) | null =
  null;
let zoomNow = 12;

class FakeMap {
  dragRotate = { disable: vi.fn() };
  touchZoomRotate = { disableRotation: vi.fn() };
  keyboard = { disableRotation: vi.fn() };

  on(event: string, handler: Handler): this {
    (handlers.get(event) ?? handlers.set(event, []).get(event)!).push(handler);
    return this;
  }
  // Attached, not merely constructed: the sheets announce their state back onto these buttons
  // through a MutationObserver, and a control off the document is a control nothing observes.
  addControl(control: { onAdd?: () => HTMLElement }): this {
    const element = control.onAdd?.();
    if (element) document.body.append(element);
    return this;
  }
  getZoom(): number {
    return zoomNow;
  }
  getBounds(): Record<string, () => number> {
    return { getWest: () => -105, getSouth: () => 31, getEast: () => -102, getNorth: () => 48 };
  }
  getCenter(): { lat: number; lng: number } {
    return { lat: 40, lng: -104 };
  }
  // Every style layer exists, which is what puts every one of them in reach of a facet press.
  getLayer(id: string): { id: string; type: string } {
    return { id, type: "circle" };
  }
  getSource(): undefined {
    return undefined;
  }
  setStyle(_style: unknown, options?: { transformStyle?: typeof transformStyle }): void {
    transformStyle = options?.transformStyle ?? null;
  }
  setLayoutProperty = vi.fn();
  setPaintProperty = vi.fn();
  setFilter(layer: string, filter: unknown): void {
    writes.push({ layer, filter });
  }
  setFeatureState = vi.fn();
  removeFeatureState = vi.fn();
  queryRenderedFeatures(): unknown[] {
    return [];
  }
  hasImage(): boolean {
    return true;
  }
  addImage = vi.fn();
  easeTo = vi.fn();
  jumpTo = vi.fn();
}

class FakeControl {
  onAdd(): HTMLElement {
    return document.createElement("div");
  }
  onRemove(): void {}
}

vi.mock("maplibre-gl", () => ({
  default: {
    Map: FakeMap,
    NavigationControl: FakeControl,
    ScaleControl: FakeControl,
    AttributionControl: FakeControl,
    addProtocol: vi.fn(),
  },
}));

const figure = (value: string, handle: string) => ({ value, unit: "wells", d: handle });

/** One state, two operators — enough for a press, an un-press and the pill's figure. */
const FACETS = {
  data: {
    state: "33",
    state_name: "North Dakota",
    dimension: "operator",
    dimension_title: "current operator, as the source reported it",
    sort: "count",
    order: "desc",
    q: null,
    top: 15,
    distinct_values: 1590,
    caption: "The 15 operator values with the most wells, of 1,590 in North Dakota.",
    buckets: [
      {
        value: "HESS CORP",
        wells: figure("3412", "drv_test#operator=HESS"),
        links: { wells: "/v1/wells?operator=HESS+CORP&state=33" },
      },
    ],
    remainder: null,
    absence: null,
    wells: figure("87634", "drv_test#wells"),
    matched_wells: null,
    states: [{ code: "33", name: "North Dakota", loaded: true }],
    rules: [],
  },
  meta: {
    request_id: "01M0JWJ6ASE1P30C37CVC61WYB",
    as_of: { requested: "latest", resolved: "2026-08-01" },
    source_freshness: {},
    labels: {},
    next_cursor: null,
    warnings: [],
  },
  links: {},
};

const BARE_STYLE = (): StyleSpecification => ({
  version: 8,
  sources: {},
  layers: [{ id: "background", type: "background", paint: { "background-color": "#0B1014" } }],
});

async function mount(search: string): Promise<void> {
  window.history.replaceState({}, "", search);
  const { createMap } = await import("./map.ts");
  const container = document.createElement("div");
  document.body.appendChild(container);
  createMap(container, { zoom: 12, lat: 47.8, lon: -102.8 }, { onViewport: vi.fn() });
  for (const handler of handlers.get("load") ?? []) handler();
  // setBasemap resolves a style before it calls setStyle; nothing is threaded until it has.
  await vi.waitFor(() => expect(transformStyle).not.toBeNull());
}

const fire = (event: string): void => {
  for (const handler of handlers.get(event) ?? []) handler();
};

const lastWrite = (layer: string): unknown =>
  [...writes].reverse().find((write) => write.layer === layer)?.filter;

/**
 * The style the map hands MapLibre. `withDataLayers` is the one place the well layers are
 * built, at boot and again on every basemap swap — `setStyle` runs with `{diff:false}`, so the
 * whole layer list is replaced and a press held only in a live filter slot would be dropped.
 */
const built = (layer: string): unknown => {
  const rebuilt = transformStyle!(null, BARE_STYLE());
  const found = rebuilt.layers.find((entry: LayerSpecification) => entry.id === layer);
  return (found as { filter?: unknown } | undefined)?.filter;
};

/** Whether the press survives in a filter, whatever else the expression carries. */
const carries = (filter: unknown, property: string, value: string): boolean =>
  JSON.stringify(filter ?? null).includes(`["get","${property}"],["literal",["${value}"]]`);

describe("a Wells-By press written onto the canvas", () => {
  beforeEach(() => {
    writes.length = 0;
    handlers.clear();
    transformStyle = null;
    zoomNow = 12;
    vi.resetModules();
    window.localStorage.clear();
    globalThis.fetch = ((input: RequestInfo | URL) =>
      String(input).includes("/v1/wells/facets")
        ? Promise.resolve(new Response(JSON.stringify(FACETS), { status: 200 }))
        : Promise.reject(new Error("offline"))) as typeof fetch;
  });

  afterEach(() => {
    document.body.replaceChildren();
    window.history.replaceState({}, "", "/");
  });

  it("reaches every status-gated layer the moment the map is built", async () => {
    await mount("?wb.pick=HESS%20CORP");
    const { FACET_FILTERED_LAYERS } = await import("./style.ts");

    for (const layer of FACET_FILTERED_LAYERS.filter((entry) => entry.gated)) {
      expect(carries(built(layer.id), "operator_name", "HESS CORP"), layer.id).toBe(true);
      // Both halves in one slot: the gate is not traded away for the press.
      expect(JSON.stringify(built(layer.id)), layer.id).toContain("status_canonical");
    }
  });

  it("reaches every layer outside the status gate too", async () => {
    // The reported defect: struck plugs, disposal rings and survey traces carry their own
    // predicate, so a press that only rewrote the status gate left them drawing every operator.
    await mount("?wb.pick=HESS%20CORP");
    const { FACET_FILTERED_LAYERS } = await import("./style.ts");

    // Counted from the roster rather than pinned: one struck overlay per registered
    // jurisdiction plus the disposal ring and the survey traces, so a fifth registration does
    // not turn this into a number somebody has to remember to change.
    const { WELLS_ROSTER } = await import("./style.ts");
    const ungated = FACET_FILTERED_LAYERS.filter((entry) => !entry.gated);
    expect(ungated).toHaveLength(WELLS_ROSTER.length + 2);
    for (const layer of ungated) {
      expect(carries(built(layer.id), "operator_name", "HESS CORP"), layer.id).toBe(true);
    }
  });

  it("keeps the disposal ring's own type predicate under the press", async () => {
    await mount("?wb.pick=HESS%20CORP");

    expect(JSON.stringify(built("disposal-wells"))).toContain("well_type_reported");
  });

  it("is still in the slot after a zoom event rewrites it", async () => {
    await mount("?wb.pick=HESS%20CORP");
    writes.length = 0;

    zoomNow = 5;
    fire("zoom");

    expect(writes.length).toBeGreaterThan(0);
    expect(carries(lastWrite("wells"), "operator_name", "HESS CORP")).toBe(true);
    // The gate moved with the zoom, which is what the handler is for — both halves, one write.
    expect(JSON.stringify(lastWrite("wells"))).toContain("status_canonical");
  });

  it("survives the zoom rewrite and the style rebuild in either order", async () => {
    // The two writers on one slot, exercised together: a zoom event replaces the live filter
    // and a basemap swap replaces the whole layer, and the press has to be an input to both.
    await mount("?wb.pick=HESS%20CORP");

    zoomNow = 6;
    fire("zoom");
    expect(carries(lastWrite("wells"), "operator_name", "HESS CORP")).toBe(true);
    expect(carries(built("wells"), "operator_name", "HESS CORP")).toBe(true);
  });

  it("writes no press at all when the reader has pressed nothing", async () => {
    await mount("?map=12/47.8/-102.8");

    expect(carries(built("wells"), "operator_name", "HESS CORP")).toBe(false);
    expect(JSON.stringify(built("wells"))).toContain("status_canonical");
  });

  it("writes no press on a dimension the tiles carry no column for", async () => {
    // completion_year is on one tile layer of thirteen. A press that narrowed Montana and left
    // the rest whole would read as a fact about the other states rather than as a partial filter.
    await mount("?wb.by=completion_year&wb.pick=2021");

    expect(JSON.stringify(built("mt-wells"))).not.toContain("completion_year");
  });
});

describe("the press, from the sheet to the canvas", () => {
  beforeEach(() => {
    writes.length = 0;
    handlers.clear();
    transformStyle = null;
    zoomNow = 12;
    vi.resetModules();
    window.localStorage.clear();
    globalThis.fetch = ((input: RequestInfo | URL) =>
      String(input).includes("/v1/wells/facets")
        ? Promise.resolve(new Response(JSON.stringify(FACETS), { status: 200 }))
        : Promise.reject(new Error("offline"))) as typeof fetch;
  });

  afterEach(() => {
    document.body.replaceChildren();
    window.history.replaceState({}, "", "/");
  });

  const settle = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0));

  it("commits the bucket with a history entry and narrows the canvas to it", async () => {
    await mount("?map=12/47.8/-102.8");
    const sheet = document.querySelector<HTMLElement>("#gw-wells-by")!;
    document.querySelector<HTMLButtonElement>(".gw-wells-by-button")!.click();
    await settle();

    const pushes: string[] = [];
    const original = window.history.pushState.bind(window.history);
    window.history.pushState = ((state: unknown, title: string, url: string) => {
      pushes.push(url);
      original(state, title, url);
    }) as typeof window.history.pushState;

    sheet.querySelector<HTMLButtonElement>("button.gw-wells-by-value")!.click();
    await settle();
    window.history.pushState = original;

    // A decision, not viewport churn: the back button undoes a press.
    expect(pushes.some((url) => url.includes("wb.pick=HESS"))).toBe(true);
    expect(carries(lastWrite("wells"), "operator_name", "HESS CORP")).toBe(true);
    // And the layers the press cannot reach are still rewritten, not left behind.
    expect(carries(lastWrite("disposal-wells"), "operator_name", "HESS CORP")).toBe(true);
  });

  it("puts the panel's own figure on the pill, and its handle", async () => {
    await mount("?map=12/47.8/-102.8");
    document.querySelector<HTMLButtonElement>(".gw-wells-by-button")!.click();
    await settle();
    document
      .querySelector<HTMLElement>("#gw-wells-by")!
      .querySelector<HTMLButtonElement>("button.gw-wells-by-value")!
      .click();
    await settle();

    const pill = document.querySelector<HTMLElement>(".gw-facet-pill")!;
    expect(pill.hidden).toBe(false);
    expect(pill.querySelector(".gw-facet-pill-count")?.textContent).toBe("3,412");
    expect(pill.querySelector<HTMLButtonElement>(".gw-handle")?.dataset["handle"]).toBe(
      "drv_test#operator=HESS",
    );
  });

  it("opens one sheet at a time, because the two share a column", async () => {
    await mount("?map=12/47.8/-102.8");
    const layers = document.querySelector<HTMLElement>("#gw-layers")!;
    const sheet = document.querySelector<HTMLElement>("#gw-wells-by")!;

    document.querySelector<HTMLButtonElement>(".gw-layers-button")!.click();
    expect(layers.hidden).toBe(false);

    document.querySelector<HTMLButtonElement>(".gw-wells-by-button")!.click();
    await settle();
    expect(layers.hidden).toBe(true);
    expect(sheet.hidden).toBe(false);
  });

  it("shuts Wells by when Layers is opened over it, in the other order too", async () => {
    // visual-map-wells-by D3: the rule was implemented one way, so opening Layers second left
    // both sheets on the same column with both triggers announcing themselves expanded.
    await mount("?map=12/47.8/-102.8");
    const layers = document.querySelector<HTMLElement>("#gw-layers")!;
    const sheet = document.querySelector<HTMLElement>("#gw-wells-by")!;

    document.querySelector<HTMLButtonElement>(".gw-wells-by-button")!.click();
    await settle();
    expect(sheet.hidden).toBe(false);

    document.querySelector<HTMLButtonElement>(".gw-layers-button")!.click();
    await settle();

    expect(sheet.hidden).toBe(true);
    expect(layers.hidden).toBe(false);
    expect(document.querySelector(".gw-wells-by-button")?.getAttribute("aria-expanded")).toBe(
      "false",
    );
    expect(document.querySelector(".gw-layers-button")?.getAttribute("aria-expanded")).toBe("true");
  });
});

describe("the press and the back button", () => {
  beforeEach(() => {
    writes.length = 0;
    handlers.clear();
    transformStyle = null;
    zoomNow = 12;
    vi.resetModules();
    window.localStorage.clear();
    globalThis.fetch = ((input: RequestInfo | URL) =>
      String(input).includes("/v1/wells/facets")
        ? Promise.resolve(new Response(JSON.stringify(FACETS), { status: 200 }))
        : Promise.reject(new Error("offline"))) as typeof fetch;
  });

  afterEach(() => {
    document.body.replaceChildren();
    window.history.replaceState({}, "", "/");
  });

  const settle = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0));

  /**
   * What the browser does on a back press, in a document that has no session history: the URL
   * moves to the previous entry and `popstate` fires. happy-dom's `history.back()` does neither,
   * so the entry is restored by hand and the event dispatched — the assertion is about what the
   * map does when the URL has moved under it, which is the half that was missing.
   */
  const goBackTo = (search: string): void => {
    window.history.replaceState(window.history.state, "", search);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  async function press(): Promise<void> {
    document.querySelector<HTMLButtonElement>(".gw-wells-by-button")!.click();
    await settle();
    document
      .querySelector<HTMLElement>("#gw-wells-by")!
      .querySelector<HTMLButtonElement>("button.gw-wells-by-value")!
      .click();
    await settle();
  }

  it("releases the press when the reader goes back over it", async () => {
    // visual-map-wells-by D2: `pushState` was added for this and only the URL moved. A link the
    // reader copies after a back press has to reproduce the canvas they are looking at.
    await mount("?map=12/47.8/-102.8");
    await press();
    expect(carries(lastWrite("wells"), "operator_name", "HESS CORP")).toBe(true);
    expect(document.querySelector<HTMLElement>(".gw-facet-pill")!.hidden).toBe(false);

    goBackTo("?map=12/47.8/-102.8");
    await settle();

    expect(window.location.search).not.toContain("wb.pick");
    expect(document.querySelector<HTMLElement>(".gw-facet-pill")!.hidden).toBe(true);
    expect(carries(lastWrite("wells"), "operator_name", "HESS CORP")).toBe(false);
    expect(
      [...document.querySelectorAll("#gw-wells-by button.gw-wells-by-value")].map((node) =>
        node.getAttribute("aria-pressed"),
      ),
    ).not.toContain("true");
  });

  it("re-applies the press when the reader goes forward onto it again", async () => {
    await mount("?map=12/47.8/-102.8");
    await press();
    goBackTo("?map=12/47.8/-102.8");
    await settle();

    goBackTo("?map=12/47.8/-102.8&wb.pick=HESS+CORP");
    await settle();

    expect(carries(lastWrite("wells"), "operator_name", "HESS CORP")).toBe(true);
    const pill = document.querySelector<HTMLElement>(".gw-facet-pill")!;
    expect(pill.hidden).toBe(false);
    expect(pill.querySelector(".gw-facet-pill-label")?.textContent).toContain("HESS CORP");
  });

  it("leaves the canvas alone on a history move that carries no Wells-By term", async () => {
    // The map is not the only writer of this URL: a card or a drawer moving in history must not
    // cost a re-mount of the sheet or a rewrite of every filter slot.
    await mount("?map=12/47.8/-102.8");
    await press();
    writes.length = 0;

    goBackTo("?map=12/47.8/-102.8&wb.pick=HESS+CORP&well=3305300000");
    await settle();

    expect(writes).toHaveLength(0);
  });
});

describe("a count refresh scheduled before the map was torn down", () => {
  afterEach(() => {
    document.body.replaceChildren();
    window.history.replaceState({}, "", "/");
  });

  it("does not run once the container has left the document", async () => {
    await mount("?wb.pick=HESS%20CORP");
    const { readState } = await import("../app/state.ts");
    const before = vi.mocked(readState).mock.calls.length;
    // What CI saw: the environment tears down while a 250 ms debounce is still pending, and the
    // crossing rebuild then reads a window that no longer exists.
    document.body.replaceChildren();
    fire("moveend");
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(vi.mocked(readState).mock.calls.length).toBe(before);
  });
});
