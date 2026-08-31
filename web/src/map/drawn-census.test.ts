// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CountsState } from "./counts.ts";

vi.mock("../chrome/status.ts", () => ({ toast: vi.fn() }));

let publishCounts: ((state: CountsState) => void) | undefined;
vi.mock("./counts.ts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./counts.ts")>();
  return {
    ...actual,
    createCountSource: (options: { onState(state: CountsState): void }) => {
      publishCounts = options.onState;
      return { request: vi.fn() };
    },
  };
});

/** Style layer id to the API-10s it painted. A layer absent from this table is absent from the map. */
const painted = new Map<string, string[]>();

class FakeMap {
  dragRotate = { disable: vi.fn() };
  touchZoomRotate = { disableRotation: vi.fn() };
  keyboard = { disableRotation: vi.fn() };

  on(): this {
    return this;
  }
  addControl(control: { onAdd?: () => HTMLElement }): this {
    control.onAdd?.();
    return this;
  }
  getZoom(): number {
    return 7;
  }
  getBounds(): Record<string, () => number> {
    return { getWest: () => -105, getSouth: () => 31, getEast: () => -102, getNorth: () => 48 };
  }
  getCenter(): { lat: number; lng: number } {
    return { lat: 40, lng: -104 };
  }
  getLayer(id: string): { id: string; type: string } | undefined {
    return painted.has(id) ? { id, type: "circle" } : undefined;
  }
  getSource(): undefined {
    return undefined;
  }
  setStyle = vi.fn();
  setLayoutProperty = vi.fn();
  setPaintProperty = vi.fn();
  setFilter = vi.fn();
  setFeatureState = vi.fn();
  removeFeatureState = vi.fn();
  // Honours the `layers` option the way MapLibre does — a layer the caller never named
  // contributes nothing — because that omission is the defect this file exists to catch.
  queryRenderedFeatures(options?: { layers?: string[] }): unknown[] {
    const asked = options?.layers ?? [...painted.keys()];
    return asked.flatMap((id) =>
      (painted.get(id) ?? []).map((api10) => ({ layer: { id }, properties: { api10 } })),
    );
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

async function mount(rows: { on: string[]; drew: Record<string, string[]> }): Promise<HTMLElement> {
  const { LAYER_STORAGE_KEY } = await import("./persist.ts");
  const { layerIds } = await import("./registry.ts");
  window.localStorage.setItem(
    LAYER_STORAGE_KEY,
    JSON.stringify({ on: rows.on, known: layerIds() }),
  );
  for (const [layer, wells] of Object.entries(rows.drew)) painted.set(layer, wells);

  const { createMap } = await import("./map.ts");
  const container = document.createElement("div");
  document.body.appendChild(container);
  createMap(container, { zoom: 7, lat: 40, lon: -104 }, { onViewport: vi.fn() });

  const partial = container.querySelector<HTMLElement>(".gw-lg-partial");
  if (!partial) throw new Error("the map mounted without its legend");
  return partial;
}

/** One settled answer for the box, so the census has an in-view number to be crossed against. */
function answerCounts(inView: number): void {
  publishCounts?.({
    kind: "ready",
    bbox: [-105, 31, -102, 48],
    counts: { active: inView },
    handles: {},
    total: inView,
    totalHandle: null,
    vocabulary: [],
    producing: null,
    resolved: null,
  });
}

beforeEach(async () => {
  painted.clear();
  publishCounts = undefined;
  document.body.innerHTML = "";
  window.localStorage.clear();
  vi.resetModules();
  vi.stubGlobal("fetch", () => Promise.resolve(new Response(null, { status: 404 })));
  const bus = await import("../bus.ts");
  bus.resetBus();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/**
 * The census is the one figure on this surface read off the canvas rather than off an answer,
 * so a state missing from the list it queries is not a blank cell — it is a smaller number
 * presented as the whole canvas, which is the failure this project exists to refuse.
 */
describe("the legend's census of what the canvas drew", () => {
  it("reports New Mexico when New Mexico is the only well row switched on", async () => {
    const partial = await mount({
      on: ["nm-wells"],
      drew: { "nm-wells": ["3001520001", "3001520002"] },
    });

    answerCounts(100);

    expect(partial.hidden).toBe(false);
    expect(partial.textContent).toBe("Showing 2 of 100 in view");
  });

  it("counts New Mexico into the census beside the states drawn with it", async () => {
    const partial = await mount({
      on: ["wells", "nm-wells"],
      drew: { wells: ["3305310451"], "nm-wells": ["3001520001", "3001520002"] },
    });

    answerCounts(100);

    expect(partial.textContent).toBe("Showing 3 of 100 in view");
  });
});
