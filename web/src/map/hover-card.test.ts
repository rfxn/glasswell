// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import { createHoverCard } from "./hover-card.ts";
import { createTileBanner } from "./tile-banner.ts";

describe("the hover card", () => {
  it("shows only what the tile already carries — identity, never a fetch", () => {
    const card = createHoverCard();
    card.show({ api10: "3305305527", well_name: "BAKKEN 14-23H", status_canonical: "active" }, {
      x: 40,
      y: 60,
    });
    expect(card.element.hidden).toBe(false);
    expect(card.element.textContent).toContain("BAKKEN 14-23H");
    expect(card.element.textContent).toContain("3305305527");
    expect(card.element.textContent).toContain("Active");
  });

  it("falls back to the api10 when the tile has no name, and states it once", () => {
    const card = createHoverCard();
    card.show({ api10: "3305305527", status_canonical: "active" }, { x: 0, y: 0 });
    expect(card.element.textContent).toContain("3305305527");
    expect(card.element.textContent?.match(/3305305527/g)?.length).toBe(1);
  });

  it("hides when nothing is under the cursor", () => {
    const card = createHoverCard();
    card.show({ api10: "33053" }, { x: 0, y: 0 });
    card.hide();
    expect(card.element.hidden).toBe(true);
  });

  it("identifies a survey trace by what ND filed — stations and measured depth, never a length", () => {
    const card = createHoverCard();
    card.show(
      {
        api10: "3305305527",
        status_canonical: "active",
        geometry_provenance: "survey_trace",
        station_count: 82,
        deepest_station_md_ft: 21_340.5,
      },
      { x: 0, y: 0 },
    );
    expect(card.element.textContent).toContain("Survey trace");
    expect(card.element.textContent).toContain("82 stations");
    // Measured depth is what the source filed; a "length" over the plan view would be
    // horizontal travel presented as hole length (m15d-status §7 obligation 3).
    expect(card.element.textContent).toContain("deepest station 21,341 ft MD");
    expect(card.element.textContent?.toLowerCase()).not.toContain("length");
  });

  it("reads the trace facts in the wire types martin serves, string or number alike", () => {
    // Postgres numeric reaches the MVT as a string (see LATERAL_LENGTH in style.ts).
    const card = createHoverCard();
    card.show(
      {
        api10: "3305305527",
        geometry_provenance: "survey_trace",
        station_count: "82",
        deepest_station_md_ft: "21340.5",
      },
      { x: 0, y: 0 },
    );
    expect(card.element.textContent).toContain("82 stations");
    expect(card.element.textContent).toContain("21,341 ft MD");
  });

  it("drops the trace line the moment the cursor moves onto a well or lateral", () => {
    const card = createHoverCard();
    card.show(
      { api10: "x", geometry_provenance: "survey_trace", station_count: 5, deepest_station_md_ft: 100 },
      { x: 0, y: 0 },
    );
    card.show({ api10: "3305305527", status_canonical: "active" }, { x: 0, y: 0 });
    expect(card.element.textContent).not.toContain("Survey trace");
  });

  it("names a status the vocabulary does not cover instead of leaving it blank", () => {
    const card = createHoverCard();
    card.show({ api10: "33053", status_canonical: "brand_new_code" }, { x: 0, y: 0 });
    expect(card.element.textContent).toMatch(/unmapped/i);
  });
});

describe("the tile-failure banner", () => {
  it("stays out of the way until a source actually fails", () => {
    const banner = createTileBanner();
    expect(banner.element.hidden).toBe(true);
  });

  it("names the failing source rather than blaming the map in general", () => {
    const banner = createTileBanner();
    banner.report("protomaps");
    expect(banner.element.hidden).toBe(false);
    expect(banner.element.textContent).toContain("protomaps");
  });

  it("says which basemap it fell back to when one was substituted", () => {
    const banner = createTileBanner();
    banner.report("protomaps", "OpenFreeMap");
    expect(banner.element.textContent).toContain("OpenFreeMap");
  });

  it("collapses repeated failures of the same source into one line", () => {
    const banner = createTileBanner();
    for (let i = 0; i < 40; i += 1) banner.report("protomaps");
    expect(banner.element.querySelectorAll(".gw-banner-line").length).toBe(1);
  });

  it("can be dismissed and stays dismissed for that source", () => {
    const banner = createTileBanner();
    banner.report("protomaps");
    banner.element.querySelector<HTMLButtonElement>(".gw-banner-x")!.click();
    expect(banner.element.hidden).toBe(true);
    banner.report("protomaps");
    expect(banner.element.hidden).toBe(true);
  });
});
