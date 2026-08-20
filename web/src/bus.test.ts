// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  connectMap,
  flyTo,
  onFlyTo,
  onSelectWell,
  onUrlParam,
  onWellSelected,
  resetBus,
  selectWell,
  setUrlParam,
  wellSelected,
} from "./bus.ts";

afterEach(() => {
  resetBus();
});

describe("the select-well channel", () => {
  it("carries the api10 and the source that asked for it", () => {
    const handler = vi.fn();
    onSelectWell(handler);

    selectWell("3305310451", "search");

    expect(handler).toHaveBeenCalledWith({ api10: "3305310451", source: "search" });
  });

  it("carries a null selection so a close is a request like any other", () => {
    const handler = vi.fn();
    onSelectWell(handler);

    selectWell(null, "map");

    expect(handler).toHaveBeenCalledWith({ api10: null, source: "map" });
  });

  it("delivers to every subscriber", () => {
    const first = vi.fn();
    const second = vi.fn();
    onSelectWell(first);
    onSelectWell(second);

    selectWell("3305310451", "url");

    expect(first).toHaveBeenCalledOnce();
    expect(second).toHaveBeenCalledOnce();
  });

  it("stops delivering once the subscriber unsubscribes", () => {
    const handler = vi.fn();
    const off = onSelectWell(handler);

    off();
    selectWell("3305310451", "map");

    expect(handler).not.toHaveBeenCalled();
  });
});

describe("the committed-selection channel", () => {
  it("is separate from the request channel, so the map never echoes its own click", () => {
    const request = vi.fn();
    const committed = vi.fn();
    onSelectWell(request);
    onWellSelected(committed);

    wellSelected("3305310451");

    expect(committed).toHaveBeenCalledWith("3305310451");
    expect(request).not.toHaveBeenCalled();
  });
});

describe("the fly-to channel", () => {
  it("carries a point and an optional zoom floor", () => {
    const handler = vi.fn();
    onFlyTo(handler);

    flyTo({ lon: -102.74, lat: 47.71, zoom: 12 });

    expect(handler).toHaveBeenCalledWith({ lon: -102.74, lat: 47.71, zoom: 12 });
  });

  it("is inert when nothing has subscribed yet", () => {
    expect(() => flyTo({ lon: -102.74, lat: 47.71 })).not.toThrow();
  });
});

describe("the map connection", () => {
  function fake() {
    const seen: string[] = [];
    return {
      seen,
      select: (api10: string | null) => seen.push(`select:${api10}`),
      flyTo: (target: { lon: number; lat: number; zoom?: number }) =>
        seen.push(`fly:${target.lon},${target.lat},${target.zoom ?? ""}`),
    };
  }

  it("absorbs a committed selection made before the map exists rather than throwing", () => {
    expect(() => wellSelected("3305300001")).not.toThrow();
    expect(() => flyTo({ lon: -102.8, lat: 47.8 })).not.toThrow();
  });

  it("drives the map handle once it connects — one registry, not two", () => {
    const map = fake();
    connectMap(map);

    wellSelected("3305300001");
    flyTo({ lon: -102.8, lat: 47.8, zoom: 12 });

    expect(map.seen).toEqual(["select:3305300001", "fly:-102.8,47.8,12"]);
  });

  it("does not echo a map click back into the map's own highlight", () => {
    const map = fake();
    connectMap(map);

    selectWell("3305300001", "map");

    expect(map.seen).toEqual([]);
  });

  it("disconnects both channels together", () => {
    const map = fake();
    connectMap(map)();

    wellSelected("3305300001");
    flyTo({ lon: -102.8, lat: 47.8 });

    expect(map.seen).toEqual([]);
  });
});

describe("the shareable url parameters the map writes", () => {
  it("writes a parameter without pushing a history entry per pan", () => {
    const before = window.history.length;
    setUrlParam("base", "light");
    expect(new URL(window.location.href).searchParams.get("base")).toBe("light");
    expect(window.history.length).toBe(before);
  });

  it("removes a parameter when the value returns to the default", () => {
    setUrlParam("base", "light");
    setUrlParam("base", null);
    expect(new URL(window.location.href).searchParams.has("base")).toBe(false);
  });

  it("mirrors every write to the owner of the app state", () => {
    const seen: [string, string | null][] = [];
    onUrlParam((key, value) => seen.push([key, value]));

    setUrlParam("layers", "wells,laterals");
    setUrlParam("layers", null);

    expect(seen).toEqual([
      ["layers", "wells,laterals"],
      ["layers", null],
    ]);
  });
});
