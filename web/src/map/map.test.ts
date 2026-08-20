// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import { tileUrl } from "../api/client.ts";
import { absoluteTileUrl, baseStyle } from "./map.ts";

describe("baseStyle", () => {
  it("declares no style property with an undefined value", () => {
    // MapLibre validates a property that is *present*, so `glyphs: undefined` fails
    // validation, the style never loads, `map.on("load")` never fires, and no source,
    // layer or tile request is ever created. The canvas is then blank with no error
    // visible to the user. Found by P8's browser smoke against the deployed instance.
    for (const [key, value] of Object.entries(baseStyle())) {
      expect(value, `style.${key} is undefined`).toBeDefined();
    }
  });

  it("omits glyphs entirely rather than declaring it empty", () => {
    const style = baseStyle();
    expect("glyphs" in style).toBe(false);
  });

  it("survives the JSON round-trip MapLibre applies to a style object", () => {
    const style = baseStyle();
    expect(JSON.parse(JSON.stringify(style))).toEqual(style);
  });

  it("draws the graticule over the dark canvas and nothing else (M12)", () => {
    const style = baseStyle();
    expect(style.layers.map((layer) => layer.id)).toEqual(["canvas", "graticule"]);
    expect(Object.keys(style.sources)).toEqual(["graticule"]);
  });
});

describe("absoluteTileUrl", () => {
  it("keeps MapLibre's placeholders literal", () => {
    // `new URL()` percent-encodes the braces, and MapLibre then requests
    // /v1/tiles/nd_laterals/%7Bz%7D/... — every tile 422s and the map stays empty.
    // Found by P8's browser smoke against the deployed instance.
    const url = absoluteTileUrl(tileUrl("nd_laterals"));

    expect(url).toBe(`${window.location.origin}/v1/tiles/nd_laterals/{z}/{x}/{y}.pbf`);
    expect(url).not.toContain("%7B");
  });

  it("leaves an already-absolute tile origin alone", () => {
    const absolute = "https://tiles.example/v1/tiles/nd_wells/{z}/{x}/{y}.pbf";
    expect(absoluteTileUrl(absolute)).toBe(absolute);
  });
});
