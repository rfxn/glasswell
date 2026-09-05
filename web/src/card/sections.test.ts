// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  SECTION_EVENT,
  SECTION_SET_EVENT,
  applySection,
  mountSections,
  resetSections,
  sectionIds,
  sectionLink,
  sectionsInFlight,
  sectionsSettled,
} from "./sections.ts";
import type { SectionSpec } from "./sections.ts";

let host: HTMLElement;
const committed: { id: string | null; mode: string }[] = [];

const toggle = (id: string): HTMLButtonElement =>
  host.querySelector<HTMLButtonElement>(`#gw-section-${id} .gw-section-toggle`) as HTMLButtonElement;
const body = (id: string): HTMLElement =>
  host.querySelector<HTMLElement>(`#gw-section-${id} .gw-section-body`) as HTMLElement;

/** A load that never settles until its resolver is called, so the queue's depth is observable. */
function held(): { load: () => Promise<void>; release: () => void; calls: () => number } {
  let resolve: () => void = () => {};
  let calls = 0;
  return {
    load: () => {
      calls += 1;
      return new Promise<void>((done) => {
        resolve = done;
      });
    },
    release: () => resolve(),
    calls: () => calls,
  };
}

// Bound once: a listener per test would answer every earlier test's dispatches too.
document.addEventListener(SECTION_SET_EVENT, (event) => {
  committed.push((event as CustomEvent<{ id: string | null; mode: string }>).detail);
});

beforeEach(() => {
  resetSections();
  committed.length = 0;
  document.body.replaceChildren();
  host = document.createElement("div");
  document.body.appendChild(host);
});

const THREE: SectionSpec[] = [
  { id: "production", title: "Production", expanded: true },
  { id: "cumulative", title: "Cumulative", expanded: true },
  { id: "neighbours", title: "Neighbours and spacing", expanded: false },
];

describe("ten ids in one order, three of them expanded", () => {
  it("renders each section as a named region with a disclosure over its own body", () => {
    mountSections(host, "3305310451", THREE);
    const section = host.querySelector("#gw-section-production") as HTMLElement;
    const heading = section.querySelector(".gw-section-head") as HTMLElement;
    expect(section.tagName).toBe("SECTION");
    expect(section.getAttribute("aria-labelledby")).toBe(heading.id);
    expect(toggle("production").getAttribute("aria-controls")).toBe(body("production").id);
    expect(sectionIds()).toEqual(["production", "cumulative", "neighbours"]);
  });

  it("expands the three the reader opened a well for and collapses the rest", () => {
    mountSections(host, "3305310451", THREE);
    expect(toggle("production").getAttribute("aria-expanded")).toBe("true");
    expect(toggle("cumulative").getAttribute("aria-expanded")).toBe("true");
    expect(toggle("neighbours").getAttribute("aria-expanded")).toBe("false");
    expect(body("neighbours").hidden).toBe(true);
  });

  it("does not render a section this well has no business having", () => {
    mountSections(host, "3305310451", [
      ...THREE,
      { id: "peer", title: "Peer control", expanded: false, present: false },
    ]);
    expect(host.querySelector("#gw-section-peer")).toBeNull();
    expect(sectionIds()).not.toContain("peer");
  });

  it("gives a re-render the reader's own disclosures back, not the defaults", () => {
    mountSections(host, "3305310451", THREE);
    toggle("neighbours").click();
    toggle("production").click();
    host.replaceChildren();
    mountSections(host, "3305310451", THREE);
    expect(toggle("neighbours").getAttribute("aria-expanded")).toBe("true");
    expect(toggle("production").getAttribute("aria-expanded")).toBe("false");
  });

  it("starts a different well at the defaults, because it is a different card", () => {
    mountSections(host, "3305310451", THREE);
    toggle("neighbours").click();
    host.replaceChildren();
    mountSections(host, "3305302532", THREE);
    expect(toggle("neighbours").getAttribute("aria-expanded")).toBe("false");
  });
});

describe("what a collapsed section costs", () => {
  it("issues no request until it is first expanded, and never a second one", async () => {
    const neighbours = held();
    mountSections(host, "3305310451", [
      THREE[0] as SectionSpec,
      THREE[1] as SectionSpec,
      { ...(THREE[2] as SectionSpec), load: neighbours.load },
    ]);
    expect(neighbours.calls()).toBe(0);

    toggle("neighbours").click();
    expect(neighbours.calls()).toBe(1);
    neighbours.release();
    await sectionsSettled();

    toggle("neighbours").click();
    toggle("neighbours").click();
    expect(neighbours.calls()).toBe(1);
  });

  it("holds the fan-out to two in flight and queues the rest in expansion order", () => {
    const loads = [held(), held(), held(), held()];
    const specs: SectionSpec[] = loads.map((each, index) => ({
      id: `s${index}`,
      title: `S${index}`,
      expanded: false,
      load: each.load,
    }));
    mountSections(host, "3305310451", specs);

    for (const spec of specs) toggle(spec.id).click();

    // Four sections open at once, two requests out. Without the bound one popstate on a phone
    // connection re-issues seven of them and the card stalls.
    expect(sectionsInFlight()).toBe(2);
    expect(loads.map((each) => each.calls())).toEqual([1, 1, 0, 0]);

    loads[0]?.release();
  });

  it("keeps the bound when a second well mounts while the first is still loading", async () => {
    // R-19's own case: a reader opens another well before the first well's sections settle.
    // The old load's `finally` used to decrement this well's counter to -1 and admit a third.
    const first = [held(), held()];
    mountSections(
      host,
      "3305310451",
      first.map((each, index) => ({
        id: `s${index}`,
        title: `S${index}`,
        expanded: true,
        load: each.load,
      })),
    );
    expect(sectionsInFlight()).toBe(2);

    const second = [held(), held(), held()];
    mountSections(
      host,
      "3305302532",
      second.map((each, index) => ({
        id: `s${index}`,
        title: `S${index}`,
        expanded: true,
        load: each.load,
      })),
    );
    // The first well's loads settle after the second well has mounted.
    for (const each of first) each.release();
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(sectionsInFlight()).toBe(2);
    expect(second.map((each) => each.calls())).toEqual([1, 1, 0]);

    second[0]?.release();
  });
});

describe("?section=", () => {
  it("expands, scrolls to and focuses the section a link named", () => {
    mountSections(host, "3305310451", THREE);
    const scrolled = vi.fn();
    (host.querySelector("#gw-section-neighbours") as HTMLElement).scrollIntoView = scrolled;

    applySection("neighbours");

    expect(toggle("neighbours").getAttribute("aria-expanded")).toBe("true");
    expect(scrolled).toHaveBeenCalled();
    expect(document.activeElement).toBe(toggle("neighbours"));
  });

  it("collapses nothing else on the way", () => {
    mountSections(host, "3305310451", THREE);
    applySection("neighbours");
    expect(toggle("production").getAttribute("aria-expanded")).toBe("true");
  });

  it("renders the default set for an id no card has, and drops it from the URL", () => {
    mountSections(host, "3305310451", THREE);
    applySection("nonsense");
    expect(toggle("production").getAttribute("aria-expanded")).toBe("true");
    expect(toggle("neighbours").getAttribute("aria-expanded")).toBe("false");
    expect(host.querySelector(".gw-section-absent-note")?.textContent).toContain("nonsense");
    expect(committed).toEqual([{ id: null, mode: "replace" }]);
  });

  it("says which section this jurisdiction does not have, and links the rule that decided", () => {
    // Silently dropping it leaves a reader thinking the link was wrong when the jurisdiction
    // was, which is a different fact and the one worth serving.
    mountSections(host, "3305310451", [
      ...THREE,
      {
        id: "peer",
        title: "Peer control",
        expanded: false,
        present: false,
        absentRule: "/v1/conformance/cr_nd_typecurve_scope_1",
      },
    ]);
    applySection("peer");
    const note = host.querySelector(".gw-section-absent-note") as HTMLElement;
    expect(note.textContent).toContain("Peer control");
    expect(note.querySelector(".gw-section-absent-rule")?.getAttribute("href")).toBe(
      "/v1/conformance/cr_nd_typecurve_scope_1",
    );
  });

  it("answers the event main.ts sends on popstate, and nothing else knows what a section is", () => {
    mountSections(host, "3305310451", THREE);
    document.dispatchEvent(new CustomEvent(SECTION_EVENT, { detail: { id: "neighbours" } }));
    expect(toggle("neighbours").getAttribute("aria-expanded")).toBe("true");
  });
});

describe("push and replace, per transition", () => {
  it("replaces on a disclosure the reader toggled, so ten of them are not ten entries", () => {
    mountSections(host, "3305310451", THREE);
    toggle("neighbours").click();
    toggle("neighbours").click();
    expect(committed).toEqual([
      { id: "neighbours", mode: "replace" },
      { id: null, mode: "replace" },
    ]);
  });

  it("pushes on an in-card link, because it is a navigation the reader asked for by name", () => {
    mountSections(host, "3305310451", THREE);
    const link = sectionLink("neighbours", "Neighbours and spacing");
    host.appendChild(link);
    link.click();
    expect(committed).toEqual([{ id: "neighbours", mode: "push" }]);
    expect(toggle("neighbours").getAttribute("aria-expanded")).toBe("true");
  });

  it("writes an href a middle click can follow, well and all", () => {
    // The click handler preventDefaults, so the href is exercised by "open in new tab" and by
    // "copy link address" alone: `?section=basin` on its own lands on the map with no card.
    window.history.replaceState(null, "", "/?well=3305310451&section=production");
    mountSections(host, "3305310451", THREE);

    const link = sectionLink("neighbours", "Neighbours and spacing");

    expect(link.getAttribute("href")).toContain("well=3305310451");
    expect(link.getAttribute("href")).toContain("section=neighbours");
  });
});

describe("the accordion keyboard", () => {
  const press = (id: string, key: string): void => {
    toggle(id).dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
  };

  it("walks the disclosures with the arrow keys, and clamps at both ends", () => {
    mountSections(host, "3305310451", THREE);
    toggle("production").focus();
    press("production", "ArrowDown");
    expect(document.activeElement).toBe(toggle("cumulative"));
    press("cumulative", "ArrowUp");
    expect(document.activeElement).toBe(toggle("production"));
    press("production", "ArrowUp");
    expect(document.activeElement).toBe(toggle("production"));
  });

  it("jumps to the first and last with Home and End", () => {
    mountSections(host, "3305310451", THREE);
    toggle("cumulative").focus();
    press("cumulative", "End");
    expect(document.activeElement).toBe(toggle("neighbours"));
    press("neighbours", "Home");
    expect(document.activeElement).toBe(toggle("production"));
  });

  it("toggles on Enter and Space, which a button does for itself", () => {
    mountSections(host, "3305310351", THREE);
    expect(toggle("neighbours").tagName).toBe("BUTTON");
    expect(toggle("neighbours").type).toBe("button");
  });
});
