// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from "vitest";

import { mapBus, registerMapBus, resetMapBus, setUrlParam } from "./map-bus.ts";

describe("the map bus", () => {
  beforeEach(() => resetMapBus());

  it("absorbs a call made before the map exists rather than throwing", () => {
    expect(() => mapBus().selectWell("3305300001")).not.toThrow();
    expect(() => mapBus().flyTo({ lon: -102.8, lat: 47.8 })).not.toThrow();
  });

  it("routes to the map once it registers", () => {
    const seen: string[] = [];
    registerMapBus({
      selectWell: (api10) => seen.push(String(api10)),
      flyTo: () => seen.push("fly"),
    });
    mapBus().selectWell("3305300001");
    mapBus().flyTo({ lon: -102.8, lat: 47.8 });
    expect(seen).toEqual(["3305300001", "fly"]);
  });

  it("writes a shareable parameter without pushing a history entry per pan", () => {
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
});
