// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from "vitest";

import type { Envelope } from "../api/envelope.ts";
import { renderBasin } from "./basin.ts";
import type { BasinContext, WellBasin } from "./basin.ts";

const ND: BasinContext = {
  basin_name: "WILLISTON",
  basin_class: "in_published_boundary",
  basin_overlap: 1,
  play_name: ["BAKKEN"],
  play_class: "plays",
  basin_label_filed: "williston",
  label_class: "agrees",
  label_agrees: true,
  boundary_vintage: "EIA 2024",
  geometry_basis: "surface",
  rule_id: "cr_nd_basin_context_1",
};

const envelope = (context: Partial<BasinContext> | null): Envelope<WellBasin> =>
  ({
    data: { basin_context: context === null ? null : { ...ND, ...context } },
    meta: { as_of: { requested: "latest", resolved: "2026-08-20" }, warnings: [], labels: {} },
    links: {},
  }) as unknown as Envelope<WellBasin>;

let host: HTMLElement;
const text = (): string => host.textContent ?? "";

beforeEach(() => {
  document.body.replaceChildren();
  host = document.createElement("div");
  document.body.appendChild(host);
});

describe("the basin is an answer, not a string", () => {
  it("draws the polygon answer, its plays and the boundary vintage", () => {
    renderBasin(host, envelope({}));
    expect(text()).toContain("WILLISTON");
    expect([...host.querySelectorAll(".gw-basin-play")].map((n) => n.textContent)).toEqual([
      "BAKKEN",
    ]);
    expect(text()).toContain("EIA 2024");
    expect(host.querySelector(".gw-basin-geometry")?.textContent).toBe("surface");
  });

  it("names the rule that decided it, because a basin is a mapping decision", () => {
    renderBasin(host, envelope({}));
    expect(host.querySelector(".gw-identity-rule")?.textContent).toBe(
      "cr_nd_basin_context_1",
    );
  });

  it("keeps the filed label beside the polygon and marks that they agree", () => {
    renderBasin(host, envelope({}));
    const filed = host.querySelector(".gw-basin-label");
    expect(filed?.textContent).toContain("williston");
    expect(filed?.querySelector(".gw-basin-agrees")?.textContent).toContain("agrees");
    expect(text()).toContain("the slice the ingest took, not a geological finding");
  });

  it("marks a disagreement in words as well as in colour", () => {
    // Texas: `permian` on all 359,421 rows is the ingest's slice, and 10,896 of the wells
    // inside a published basin are in a different one.
    renderBasin(
      host,
      envelope({
        basin_name: "FORT WORTH",
        basin_label_filed: "permian",
        label_class: "disagrees",
        label_agrees: false,
        rule_id: "cr_tx_basin_context_1",
      }),
    );
    const mark = host.querySelector(".gw-basin-disagrees");
    expect(mark?.textContent).toContain("disagrees with the polygon");
    expect(text()).toContain("FORT WORTH");
    expect(text()).toContain("permian");
  });
});

describe("every absence is an answer with a reason", () => {
  it("says outside every published boundary, and says whose boundaries", () => {
    // For two thirds of Montana this is the answer, so it reads as a finding about the
    // published set rather than as a failure of the well.
    renderBasin(
      host,
      envelope({
        basin_name: null,
        basin_class: "outside_published_boundaries",
        basin_overlap: 0,
        play_name: [],
        play_class: "no_play_at_this_location",
        basin_label_filed: null,
        label_class: "not_labelled",
        label_agrees: null,
        boundary_vintage: "SedimentaryBasins_US_May2011_v2",
        rule_id: "cr_mt_basin_context_1",
      }),
    );
    expect(text()).toContain("outside every basin the published boundary set draws");
    // Outside what: the set that was asked, named with its vintage rather than gestured at.
    expect(text()).toContain("The set asked was SedimentaryBasins_US_May2011_v2.");
    expect(text()).toContain("not a gap in the record");
    expect(host.querySelector(".gw-basin")?.textContent).toContain(
      "outside_published_boundaries",
    );
  });

  it("names no boundary set where the class is outside and none was served", () => {
    // A mart row written before the boundary set was loaded: the sentence still holds, and it
    // claims no vintage it does not have.
    renderBasin(
      host,
      envelope({
        basin_name: null,
        basin_class: "outside_published_boundaries",
        boundary_vintage: null,
      }),
    );
    expect(text()).toContain("outside every basin the published boundary set draws");
    expect(text()).not.toContain("The set asked was");
  });

  it("separates no geometry from outside every boundary", () => {
    renderBasin(
      host,
      envelope({
        basin_name: null,
        basin_class: "no_geometry",
        geometry_basis: "no_geometry",
        basin_overlap: 0,
      }),
    );
    expect(text()).toContain("No geometry is held for this well");
    expect(text()).not.toContain("outside every basin");
  });

  it("says a location has no play rather than drawing an empty row", () => {
    renderBasin(host, envelope({ play_name: [], play_class: "no_play_at_this_location" }));
    expect(text()).toContain("no_play_at_this_location");
    expect(host.querySelector(".gw-basin-play")).toBeNull();
  });

  it("says an unbuilt mart is a state of the mart, not a fact about the well", () => {
    renderBasin(host, envelope(null));
    expect(text()).toContain("state of the mart, not a fact about the well");
  });

  it("says when the publisher's own polygons overlap rather than picking silently", () => {
    renderBasin(host, envelope({ basin_overlap: 2 }));
    expect(text()).toContain("2 published basins contain this point");
    expect(text()).toContain("the overlap is the publisher's own");
  });

  it("says so where a jurisdiction registers no rule at all", () => {
    renderBasin(host, envelope({ rule_id: null }));
    expect(text()).toContain("registers no basin context rule");
  });
});
