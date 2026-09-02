// @vitest-environment happy-dom
/**
 * R9 / DIR-8 coverage for the three surfaces the API gate cannot see.
 *
 * `tests/contract/test_glossary_coverage.py` walks what the API emits. Nothing walked what the
 * map key, the layers panel and the status page put on screen, so a word could ship with no row
 * behind it and no gate would redden. This one renders each surface against the committed seed
 * and fails on a term it names but cannot define.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createLegend } from "../map/legend.ts";
import { stubFetch } from "../test/fixtures.ts";
import {
  loadSeed,
  seedIndexPayload,
  seedIsFlowStyle,
  seedTermPayload,
  slug,
} from "../test/glossary-seed.ts";
import { SURFACE_NAMES, renderSurface, statusEnvelope } from "../test/surfaces.ts";
import type { SurfaceName } from "../test/surfaces.ts";
import { loadGlossary } from "./store.ts";

const SEED = loadSeed();
const BY_TERM = new Map(SEED.map((row) => [row.term, row]));

/**
 * How a surface teaches a term. `shown` renders as a `<gw-term>` the reader can hover, whether
 * the highlighter found it or the surface bound it by hand. `related` is reached by one click
 * from a shown term: the word is either ordinary enough to be non-highlightable (M7) or never
 * appears in the copy, and the popover's related chips are the path to it.
 */
type Taught = "shown" | "related";

const INVENTORY: Record<SurfaceName, Record<string, Taught>> = {
  "map status legend": {
    "Producing class": "shown",
    "Geometry provenance": "shown",
    "Vocabulary rule": "shown",
    "Well type": "shown",
    "Disposal well": "shown",
    Lateral: "shown",
    "Station survey": "shown",
    Viewport: "shown",
    Condensate: "shown",
    "Conformance rule": "related",
    "Well status": "related",
    "Rule kind": "related",
    "Liquids policy": "related",
    Wellbore: "related",
  },
  "layers panel": {
    Basemap: "shown",
    Basin: "shown",
    Play: "shown",
    PLSS: "shown",
    Township: "shown",
    "Spacing / spacing unit": "shown",
    Lateral: "shown",
    "Station survey": "shown",
    "Well type": "shown",
    Condensate: "shown",
    Quarantine: "shown",
    "Confidential well": "shown",
    "Section (PLSS)": "related",
    "Land unit": "related",
    Formation: "related",
    "Conformance rule": "related",
  },
  "status page": {
    "Status snapshot": "shown",
    "Schema head": "shown",
    Timer: "shown",
    Cadence: "shown",
    "Scheduled job": "shown",
    "Next due": "shown",
    Refusal: "shown",
    Observing: "shown",
    Manifest: "shown",
    "Declared vintage": "shown",
    "Retrieval vintage": "shown",
    Canonical: "shown",
    Marts: "shown",
    Lineage: "shown",
    Basemap: "shown",
    "Derivation handle": "related",
    "Raw zone": "related",
    Recipe: "related",
  },
};

/** The vocabulary this track was asked to teach, wherever it ends up being taught. */
const REQUIRED = [
  "Producing class",
  "Geometry provenance",
  "Vocabulary rule",
  "Spacing / spacing unit",
  "Lateral",
  "Station survey",
  "Disposal well",
  "PLSS",
  "Township",
  "Section (PLSS)",
  "Basin",
  "Play",
  "Declared vintage",
  "Quarantine",
  "Conformance rule",
  "Manifest",
  "Derivation handle",
  "Status snapshot",
  "Schema head",
  "Timer",
  "Marts",
];

const shownIds = (root: HTMLElement): Set<string> =>
  new Set([...root.querySelectorAll("gw-term")].map((term) => term.getAttribute("term-id") ?? ""));

beforeEach(() => {
  document.body.innerHTML = "";
  vi.stubGlobal(
    "fetch",
    vi.fn(
      stubFetch({
        "/v1/glossary/index": { data: seedIndexPayload(SEED), meta: {} },
        "/v1/glossary": { data: seedTermPayload(SEED), meta: {} },
        "/v1/status": statusEnvelope,
      }),
    ),
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the seed the gate reads", () => {
  it("is the committed file, parsed whole", () => {
    expect(SEED.length).toBeGreaterThan(60);
    expect(BY_TERM.get("PLSS")?.term_id).toBe("gt_plss");
    expect(BY_TERM.get("Basin")?.aliases).toContain("Basins");
  });

  it("keeps its lists in flow style, which is all the parser can read", () => {
    expect(seedIsFlowStyle()).toBe(true);
  });

  it("mints the ids the surfaces bind by hand", () => {
    expect(slug("Producing class")).toBe("gt_producing_class");
    expect(slug("Section (PLSS)")).toBe("gt_section_plss");
  });
});

describe.each(SURFACE_NAMES)("%s", (surface) => {
  const expected = INVENTORY[surface];

  it("names no term the glossary cannot define", () => {
    expect(Object.keys(expected).filter((term) => !BY_TERM.has(term))).toEqual([]);
  });

  it("renders every term it shows as a definition a reader can open", async () => {
    const root = await renderSurface(surface);
    await loadGlossary();
    const rendered = shownIds(root);

    expect(
      Object.entries(expected)
        .filter(([term, taught]) => taught === "shown" && !rendered.has(slug(term)))
        .map(([term]) => term),
    ).toEqual([]);
  });

  it("puts every term it only relates to one click from one it shows", async () => {
    const root = await renderSurface(surface);
    await loadGlossary();
    const rendered = shownIds(root);
    const reachable = new Set(
      SEED.filter((row) => rendered.has(row.term_id)).flatMap((row) => row.related_terms),
    );

    expect(
      Object.entries(expected)
        .filter(([term, taught]) => taught === "related" && !reachable.has(term))
        .map(([term]) => term),
    ).toEqual([]);
  });

  it("points no rendered term at a row the seed does not hold", async () => {
    const root = await renderSurface(surface);
    await loadGlossary();
    const seeded = new Set(SEED.map((row) => row.term_id));

    expect([...shownIds(root)].filter((id) => !seeded.has(id))).toEqual([]);
  });
});

it("covers the vocabulary the track was asked to teach, somewhere", () => {
  const taught = new Set(Object.values(INVENTORY).flatMap((entry) => Object.keys(entry)));

  expect(REQUIRED.filter((term) => !taught.has(term) || !BY_TERM.has(term))).toEqual([]);
});

it("fills a surface built before the index landed, not only one built after", async () => {
  vi.resetModules();
  const fresh = await import("../test/surfaces.ts");
  const store = await import("./store.ts");
  const root = await fresh.renderSurface("map status legend");

  // Only what the legend binds by hand: the highlighter has no index to work from yet.
  expect(shownIds(root)).toEqual(new Set(["gt_producing_class"]));

  await store.loadGlossary();

  expect(shownIds(root).has("gt_geometry_provenance")).toBe(true);
});

describe("what the highlighter must not cost a surface", () => {
  it("leaves a state pill's wording whole, spaces and all", async () => {
    const root = await renderSurface("status page");
    await loadGlossary();

    // The pill is inline-flex, so splitting "Current snapshot" around a term would make two
    // flex items and drop the space between them: the reader saw "Currentsnapshot".
    expect([...root.querySelectorAll(".gw-status-badge")].map((one) => one.textContent)).toContain(
      "Current snapshot",
    );
    expect(root.querySelector(".gw-status-badge gw-term")).toBeNull();
  });

  it("lights a legend row the next viewport introduced, without waiting for a render", async () => {
    const legend = createLegend({ onFilter: () => {} });
    document.body.append(legend.element);
    await loadGlossary();

    // The served order decides these rows, and setProvenance does not go through render().
    legend.setProvenance({ counts: { lateral: 3 }, handles: {}, order: ["lateral"] });

    expect(
      legend.element
        .querySelector('.gw-lg-drow[data-value="lateral"] gw-term')
        ?.getAttribute("term-id"),
    ).toBe("gt_lateral");
  });
});
