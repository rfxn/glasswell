import { afterEach, describe, expect, it, vi } from "vitest";

import { flyTo, onFlyTo, onSelectWell, onWellSelected, resetBus, selectWell, wellSelected } from "./bus.ts";

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
