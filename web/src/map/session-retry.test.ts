// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CountsState } from "./counts.ts";

const toast = vi.fn();
vi.mock("../chrome/status.ts", () => ({ toast }));

let publishCounts: ((state: CountsState) => void) | undefined;
const countsRequest = vi.fn();
vi.mock("./counts.ts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./counts.ts")>();
  return {
    ...actual,
    createCountSource: (options: { onState(state: CountsState): void }) => {
      publishCounts = options.onState;
      return { request: countsRequest };
    },
  };
});

interface FakeSource {
  setTiles: ReturnType<typeof vi.fn>;
}

const handlers = new Map<string, ((event: unknown) => void)[]>();
const sources = new Map<string, FakeSource>();
const setStyle = vi.fn();

function fire(event: string, payload: unknown = {}): void {
  for (const handler of handlers.get(event) ?? []) handler(payload);
}

class FakeMap {
  dragRotate = { disable: vi.fn() };
  touchZoomRotate = { disableRotation: vi.fn() };
  keyboard = { disableRotation: vi.fn() };

  on(event: string, handler: (event: unknown) => void): this {
    handlers.set(event, [...(handlers.get(event) ?? []), handler]);
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
    return { getWest: () => -104, getSouth: () => 47, getEast: () => -102, getNorth: () => 48 };
  }
  getCenter(): { lat: number; lng: number } {
    return { lat: 47.5, lng: -103 };
  }
  getLayer(): undefined {
    return undefined;
  }
  getSource(id: string): FakeSource | undefined {
    return sources.get(id);
  }
  setStyle = setStyle;
  setLayoutProperty = vi.fn();
  setPaintProperty = vi.fn();
  setFilter = vi.fn();
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

/** A tile refused by the API: what MapLibre hands its `error` listener for a 403 on a source. */
function tileRefusal(sourceId: string): { error: { status: number }; sourceId: string } {
  return { error: { status: 403 }, sourceId };
}

async function mount(): Promise<{
  container: HTMLElement;
  banner: HTMLElement;
  dataSources: string[];
}> {
  const { createMap } = await import("./map.ts");
  const { sourceSpecs } = await import("./style.ts");
  const dataSources = Object.keys(sourceSpecs());
  for (const id of dataSources) sources.set(id, { setTiles: vi.fn() });

  const container = document.createElement("div");
  document.body.appendChild(container);
  createMap(container, { zoom: 7, lat: 47.5, lon: -103 }, { onViewport: vi.fn() });

  const banner = container.querySelector<HTMLElement>(".gw-banner");
  if (!banner) throw new Error("the map mounted without its tile banner");
  return { container, banner, dataSources };
}

beforeEach(async () => {
  handlers.clear();
  sources.clear();
  toast.mockClear();
  countsRequest.mockClear();
  setStyle.mockClear();
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
 * The signed-out arrival: the map mounts before the session resolves, so its first tile and
 * count requests are refused. A refusal is not a failure of the tile service, and the state it
 * leaves behind must not outlive the sign-in that answers it.
 */
describe("a map that mounted before anyone signed in", () => {
  it("raises no banner for a tile the API refused because there is no session", async () => {
    const { banner } = await mount();

    fire("error", tileRefusal("nd_wells"));
    fire("error", tileRefusal("tx_wells"));

    expect(banner.hidden).toBe(true);
    expect(banner.textContent).not.toContain("nd_wells");
    expect(banner.textContent).not.toContain("tx_wells");
  });

  it("keeps a refused tile off the console, the way DR-H20 settled it for the session probe", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    await mount();

    fire("error", tileRefusal("nd_wells"));

    expect(error).not.toHaveBeenCalled();
  });

  it("still banners a tile source that failed for a reason signing in cannot fix", async () => {
    const { banner } = await mount();

    fire("error", { error: { status: 500 }, sourceId: "nd_wells" });

    expect(banner.hidden).toBe(false);
    expect(banner.textContent).toContain("nd_wells");
  });

  it("re-requests every data source's tiles once a session begins", async () => {
    const { dataSources } = await mount();
    const bus = await import("../bus.ts");

    bus.sessionBegan();

    for (const id of dataSources) {
      expect(sources.get(id)?.setTiles, `${id} was never re-requested`).toHaveBeenCalledTimes(1);
    }
  });

  it("re-asks the counts once a session begins", async () => {
    await mount();
    const bus = await import("../bus.ts");
    countsRequest.mockClear();

    bus.sessionBegan();

    expect(countsRequest).toHaveBeenCalled();
  });

  it("drops a banner line for a source it is about to retry", async () => {
    const { banner } = await mount();
    fire("error", { error: { status: 500 }, sourceId: "nd_wells" });
    expect(banner.hidden).toBe(false);

    const bus = await import("../bus.ts");
    bus.sessionBegan();

    expect(banner.hidden).toBe(true);
    expect(banner.textContent).not.toContain("nd_wells");
  });

  it("says nothing about unavailable counts when the refusal is only a missing session", async () => {
    await mount();

    publishCounts?.({ kind: "error", bbox: [-104, 47, -102, 48], message: "Forbidden", auth: true });

    expect(toast).not.toHaveBeenCalled();
  });

  it("still reports counts that failed for a reason signing in cannot fix", async () => {
    await mount();

    publishCounts?.({
      kind: "error",
      bbox: [-104, 47, -102, 48],
      message: "the counts took too long to answer",
    });

    expect(toast).toHaveBeenCalledWith(
      "Well counts unavailable: the counts took too long to answer",
    );
  });
});
