// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";

import { EXPLAIN_EVENT } from "../card/gw-figure.ts";
import { createThematicsKey } from "./thematics-key.ts";

const CELL = {
  unit_type: "section",
  bin_edges: JSON.stringify([200, 226, 460, 720, 980, 1240, 1474, 1500]),
  bin_population: 2,
  derivation_id: "drv_thematics",
};

describe("the thematic key", () => {
  it("opens hidden and stays hidden with nothing rendered", () => {
    const key = createThematicsKey();
    expect(key.element.hidden).toBe(true);
    key.set([]);
    expect(key.element.hidden).toBe(true);
  });

  it("states the metric, the basis, the unit, the population and the frozen edges", () => {
    const key = createThematicsKey();
    key.set([CELL]);
    expect(key.element.hidden).toBe(false);
    const text = key.element.textContent ?? "";
    expect(text).toContain("Cumulative liquid");
    expect(text).toContain("oil + condensate as ND files it");
    expect(text).toContain("Per PLSS section");
    expect(text).toContain("bins cut over 2 sections");
    expect(text).toContain("frozen at refresh");
    expect(text).toContain("200");
    expect(text).toContain("1.47K"); // compact P98
    expect(text).toContain("bbl");
    expect(text).toContain("cr_land_agg_membership_1");
    expect(text).toContain("Unpainted = nothing observed");
  });

  it("draws seven ramp bins in order", () => {
    const key = createThematicsKey();
    key.set([CELL]);
    expect(key.element.querySelectorAll(".gw-thm-bin")).toHaveLength(7);
  });

  it("resolves its figures: the handle raises the explain event with the derivation", () => {
    const key = createThematicsKey();
    key.set([CELL]);
    const seen = vi.fn();
    key.element.addEventListener(EXPLAIN_EVENT, (event) =>
      seen((event as CustomEvent).detail.handle),
    );
    key.element.querySelector<HTMLButtonElement>(".gw-thm-handle")?.click();
    expect(seen).toHaveBeenCalledWith("drv_thematics");
  });

  it("clears rather than keeping the last viewport's frame", () => {
    const key = createThematicsKey();
    key.set([CELL]);
    key.clear();
    expect(key.element.hidden).toBe(true);
  });
});
