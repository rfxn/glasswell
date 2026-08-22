// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_STATE, parseState, serializeState } from "../app/state.ts";
import type { AppState } from "../app/state.ts";
import { onFlyTo, onSelectWell, resetBus } from "../bus.ts";
import { LAYERS, layerDef } from "../map/registry.ts";
import {
  BBOX_DEGREE_CAP,
  DEFERRED_WELLSET,
  TARGETS,
  UNPINNED_LABEL,
  crossingLink,
  cross,
  openThisSeries,
  pinnedState,
  rowsForThisWell,
  showOnMap,
  vintagesCrossing,
  whatsBehindThisLayer,
} from "./bridge.ts";
import type { BridgeContext, Crossing } from "./bridge.ts";
import { buildCatalogue } from "./catalogue.ts";
import type { CatalogueDataset } from "./catalogue.ts";
import { requestFor } from "./router.ts";
import { CLASS_B_DATASETS } from "./rail.ts";

const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8"));
const CATALOGUE = buildCatalogue(SNAPSHOT);
const DATASETS = CATALOGUE.datasets;

const API10 = "3305302532";
/** A box inside the cap, so the geographic filter is the one under test and not the refusal. */
const TIGHT_BBOX = [-103.5, 47.5, -102.5, 48.2] as const;
const WORLD_BBOX = [-180, -85, 180, 85] as const;

function context(over: Partial<BridgeContext> = {}): BridgeContext {
  return { state: { ...DEFAULT_STATE, view: "map" }, resolved: "2026-08-20", ...over };
}

function dataset(id: string): CatalogueDataset {
  const found = DATASETS.find((candidate) => candidate.id === id);
  if (!found) throw new Error(`no dataset ${id}`);
  return found;
}

/** Every query parameter the document declares on a dataset's operation. */
function queryNames(id: string): string[] {
  const operation = Object.values(SNAPSHOT.paths)
    .flatMap((item) => Object.values(item as Record<string, { operationId?: string }>))
    .find((candidate) => candidate.operationId === dataset(id).operationId) as {
    parameters?: { name: string; in: string }[];
  };
  return (operation.parameters ?? []).filter((p) => p.in === "query").map((p) => p.name);
}

function asOfOf(crossing: Crossing | null): string[] {
  return crossing?.next.extra["as_of"] ?? [];
}

/** Every crossing the §2.6 table describes, built from one context so the table is asserted whole. */
function everyCrossing(over: Partial<BridgeContext> = {}): Crossing[] {
  const shared = context(over);
  const wells = layerDef("wells");
  return [
    rowsForThisWell(API10, shared),
    openThisSeries(API10, shared),
    whatsBehindThisLayer(wells?.collection ?? null, TIGHT_BBOX, shared),
    vintagesCrossing(shared),
    showOnMap(API10, { lon: -102.8, lat: 47.8 }, { ...shared, state: { ...shared.state, view: "explore" } }),
  ].filter((crossing): crossing is Crossing => crossing !== null);
}

beforeEach(() => {
  window.history.replaceState(null, "", "/?view=map");
});

afterEach(() => {
  resetBus();
  vi.restoreAllMocks();
});

describe("the §2.6 table, both directions", () => {
  it("carries a map well card to that well's rows, with the row already open", () => {
    const crossing = rowsForThisWell(API10, context());

    expect(crossing?.next.view).toBe("explore");
    expect(crossing?.next.ds).toBe("wells");
    expect(crossing?.next.row).toBe(API10);
    expect(crossing?.next.extra["f.q"]).toEqual([API10]);
  });

  it("carries the production chart header to that well's series", () => {
    const crossing = openThisSeries(API10, context());

    expect(crossing?.next.ds).toBe("production");
    expect(crossing?.next.extra["f.api10"]).toEqual([API10]);
    // A pivot narrowed to one well is a filtered hop, not a row: the row key is the month.
    expect(crossing?.next.row).toBeNull();
  });

  it("carries a layer to the collection behind it, narrowed to the current view", () => {
    const crossing = whatsBehindThisLayer(layerDef("wells")?.collection ?? null, TIGHT_BBOX, context());

    expect(crossing?.next.ds).toBe("wells");
    expect(crossing?.next.extra["f.bbox"]).toEqual(["-103.5,47.5,-102.5,48.2"]);
  });

  it("carries the as_of chip to the vintages collection, and narrows nothing", () => {
    const crossing = vintagesCrossing(context());

    expect(crossing?.next.ds).toBe("vintages");
    expect(Object.keys(crossing?.next.extra ?? {})).toEqual(["as_of"]);
  });

  it("carries an explorer row with geometry back to the map, at that geometry", () => {
    const from = context({ state: { ...DEFAULT_STATE, view: "explore", ds: "wells" } });
    const crossing = showOnMap(API10, { lon: -102.8, lat: 47.8 }, from);

    expect(crossing?.next.view).toBe("map");
    expect(crossing?.next.well).toBe(API10);
    expect(crossing?.next.map.lat).toBe(47.8);
    expect(crossing?.next.map.lon).toBe(-102.8);
    // §2.6's `/?well={api10}&map=z/lat/lon`: the viewport rides the URL, so the link reopens there.
    expect(crossing?.href).toContain("map=");
    expect(crossing?.href).toContain(`well=${API10}`);
  });

  it("clears the well card and the drawer when it lands in the explorer", () => {
    const from = context({
      state: { ...DEFAULT_STATE, view: "map", well: API10, explain: "d_01" },
    });

    for (const crossing of everyCrossing({ state: from.state })) {
      if (crossing.next.view !== "explore") continue;
      expect(crossing.next.well, crossing.id).toBeNull();
      expect(crossing.next.explain, crossing.id).toBeNull();
    }
  });

  it("builds every row of the table, so none of them is silently absent", () => {
    expect(everyCrossing().map((crossing) => crossing.id)).toEqual([
      "rows-for-this-well",
      "open-this-series",
      "whats-behind-this-layer",
      "vintages",
      "show-on-map",
    ]);
  });
});

describe("invariant one — as_of survives every crossing", () => {
  it("carries a vintage the reader pinned, unchanged, across every crossing", () => {
    const pinned: AppState = { ...DEFAULT_STATE, view: "map", extra: { as_of: ["2026-07-01"] } };

    for (const crossing of everyCrossing({ state: pinned })) {
      expect(asOfOf(crossing), crossing.id).toEqual(["2026-07-01"]);
    }
  });

  it("pins the vintage the source surface resolved when the reader pinned none (M6)", () => {
    for (const crossing of everyCrossing()) {
      expect(asOfOf(crossing), crossing.id).toEqual(["2026-08-20"]);
    }
  });

  it("prefers the reader's own pin over the resolved one, never the other way round", () => {
    const state: AppState = { ...DEFAULT_STATE, view: "map", extra: { as_of: ["2026-07-01"] } };

    expect(pinnedState({ ...context({ state }), resolved: "2026-08-20" }).extra["as_of"]).toEqual([
      "2026-07-01",
    ]);
  });

  it("names the vintage its own href carries, so the flag and the link cannot disagree", () => {
    for (const crossing of everyCrossing()) {
      expect(crossing.pinned, crossing.id).toBe("2026-08-20");
      expect(crossing.href, crossing.id).toContain("as_of=2026-08-20");
    }
  });

  /**
   * The half this used to assert on its own — "nothing is invented" — is right and is still
   * here. It was never the whole contract: leaving `as_of` absent and *still offering the
   * crossing* hands the reader a URL that answers differently after the next vintage lands,
   * which is the drift M6 exists to stop. Both halves, together, or neither is worth much.
   */
  it("invents no as_of when the surface resolved nothing, and offers no link either (M6)", () => {
    for (const crossing of everyCrossing({ resolved: null })) {
      expect(asOfOf(crossing), crossing.id).toEqual([]);
      expect(crossing.pinned, crossing.id).toBeNull();

      const link = crossingLink(crossing, { signal: new AbortController().signal });

      expect(link.getAttribute("href"), crossing.id).toBeNull();
      expect(link.getAttribute("aria-disabled"), crossing.id).toBe("true");
      expect(link.textContent, crossing.id).toContain(UNPINNED_LABEL);
      expect(link.title, crossing.id).toContain("would answer differently");
    }
  });

  /**
   * The address bar is a copy surface like any other, so refusing the href is only half of it:
   * a route that pushed the same state would put the drifting URL in front of the reader by
   * another door. `cross` is the one door, so the refusal lives there.
   */
  it("refuses to navigate an unpinned crossing, so no route can write a drifting URL", () => {
    window.history.replaceState(null, "", "/?view=map");
    const crossing = whatsBehindThisLayer(
      layerDef("wells")?.collection ?? null,
      TIGHT_BBOX,
      context({ resolved: null }),
    ) as Crossing;
    const push = vi.spyOn(window.history, "pushState");
    const seen = vi.fn();
    window.addEventListener("popstate", seen);

    cross(crossing);

    expect(push).not.toHaveBeenCalled();
    expect(seen).not.toHaveBeenCalled();
    expect(window.location.search).toBe("?view=map");
    window.removeEventListener("popstate", seen);
  });

  it("still offers the link when the reader pinned one and the surface resolved nothing", () => {
    const state: AppState = { ...DEFAULT_STATE, view: "map", extra: { as_of: ["2026-07-01"] } };

    for (const crossing of everyCrossing({ state, resolved: null })) {
      const link = crossingLink(crossing, { signal: new AbortController().signal });

      expect(crossing.pinned, crossing.id).toBe("2026-07-01");
      expect(link.getAttribute("href"), crossing.id).toBe(crossing.href);
      expect(link.hasAttribute("aria-disabled"), crossing.id).toBe(false);
    }
  });

  it("reads a bare as_of= as nobody's pin, rather than as one that outranks the surface's", () => {
    const state: AppState = { ...DEFAULT_STATE, view: "map", extra: { as_of: [""] } };

    expect(pinnedState({ state, resolved: "2026-08-20" }).extra["as_of"]).toEqual(["2026-08-20"]);
    expect(rowsForThisWell(API10, { state, resolved: null })?.pinned).toBeNull();
  });

  it("survives the round trip through the URL, which is what a shared link actually carries", () => {
    for (const crossing of everyCrossing()) {
      expect(parseState(crossing.href).extra["as_of"], crossing.id).toEqual(["2026-08-20"]);
    }
  });
});

describe("invariant two — every crossing is a pushState", () => {
  it("pushes exactly one history entry, so one back press returns the reader", () => {
    for (const crossing of everyCrossing()) {
      const push = vi.spyOn(window.history, "pushState");
      const replace = vi.spyOn(window.history, "replaceState");

      cross(crossing);

      expect(push, crossing.id).toHaveBeenCalledTimes(1);
      expect(replace, crossing.id).not.toHaveBeenCalled();
      push.mockRestore();
      replace.mockRestore();
    }
  });

  it("pushes the crossing's own URL, not the one the reader was already on", () => {
    const crossing = rowsForThisWell(API10, context()) as Crossing;
    cross(crossing);

    expect(window.location.search).toBe(crossing.href);
    expect(window.location.search).toBe(serializeState(crossing.next));
  });

  it("dispatches the one popstate main.ts renders a surface change through", () => {
    const seen = vi.fn();
    window.addEventListener("popstate", seen);

    cross(rowsForThisWell(API10, context()) as Crossing);

    expect(seen).toHaveBeenCalledTimes(1);
    window.removeEventListener("popstate", seen);
  });

  it("leaves a modified click to the browser, so a crossing can open in a new tab", () => {
    const crossing = rowsForThisWell(API10, context()) as Crossing;
    const link = crossingLink(crossing, { signal: new AbortController().signal });
    const push = vi.spyOn(window.history, "pushState");

    link.dispatchEvent(new MouseEvent("click", { metaKey: true, cancelable: true, bubbles: true }));

    expect(push).not.toHaveBeenCalled();
  });

  /**
   * The owed mounts (§7 E1) live in a host that replaces its whole subtree and holds no
   * controller. The listener is on the anchor, so it goes when the anchor does — requiring a
   * signal there would be asking a host to invent one for a teardown it already performs.
   */
  it("crosses from a link built without a signal, for a host that discards its own subtree", () => {
    const crossing = rowsForThisWell(API10, context()) as Crossing;
    const link = crossingLink(crossing);
    const push = vi.spyOn(window.history, "pushState");

    link.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));

    expect(push).toHaveBeenCalledTimes(1);
    push.mockRestore();
  });

  it("renders the crossing as a link whose href is the state it lands on", () => {
    const crossing = whatsBehindThisLayer(
      layerDef("wells")?.collection ?? null,
      TIGHT_BBOX,
      context(),
    ) as Crossing;
    const link = crossingLink(crossing, { signal: new AbortController().signal });

    expect(link.tagName).toBe("A");
    expect(link.getAttribute("href")).toBe(crossing.href);
    expect(link.dataset["crossing"]).toBe("whats-behind-this-layer");
  });
});

describe("the explorer-to-map path talks to the map only through the bus", () => {
  it("imports no map module, so the explorer cannot pull the canvas into its chunk", () => {
    const source = readFileSync("src/explore/bridge.ts", "utf8");

    expect(source).not.toMatch(/from\s+["'][^"']*\/map\//);
    expect(source).toContain("../bus.ts");
  });

  it("asks the camera for the row's geometry through flyTo", () => {
    const flown = vi.fn();
    onFlyTo(flown);

    cross(
      showOnMap(API10, { lon: -102.8, lat: 47.8 }, context({
        state: { ...DEFAULT_STATE, view: "explore", ds: "wells" },
      })) as Crossing,
    );

    expect(flown).toHaveBeenCalledWith({ lon: -102.8, lat: 47.8, zoom: 12 });
  });

  /**
   * `selectWell` reaches main.ts's `onSelectWell`, which commits the well with a *second*
   * `pushState` — two entries for one crossing, and a back button that needs two presses.
   * The popstate above already commits it through `wellSelected`, so the request channel is
   * deliberately not used here. Recorded as a deviation rather than left to the diff.
   */
  it("does not also request the selection, which would push a second history entry", () => {
    const requested = vi.fn();
    onSelectWell(requested);

    cross(
      showOnMap(API10, { lon: -102.8, lat: 47.8 }, context({
        state: { ...DEFAULT_STATE, view: "explore", ds: "wells" },
      })) as Crossing,
    );

    expect(requested).not.toHaveBeenCalled();
  });

  it("refuses a point that is not two finite numbers, rather than flying to null island", () => {
    const from = context({ state: { ...DEFAULT_STATE, view: "explore", ds: "wells" } });

    expect(showOnMap(API10, { lon: Number.NaN, lat: 47.8 }, from)).toBeNull();
    expect(showOnMap(API10, { lon: -102.8, lat: Number.POSITIVE_INFINITY }, from)).toBeNull();
    expect(showOnMap("", { lon: -102.8, lat: 47.8 }, from)).toBeNull();
  });

  it("puts the well in the pushed state, which is what the popstate route selects from", () => {
    const crossing = showOnMap(API10, { lon: -102.8, lat: 47.8 }, context({
      state: { ...DEFAULT_STATE, view: "explore", ds: "wells" },
    })) as Crossing;

    expect(parseState(crossing.href).well).toBe(API10);
  });
});

/**
 * Four of the five crossings are built on the map, which never fetches `/openapi.json`, so
 * their destinations are declared rather than looked up. That is only honest if the
 * declaration is checked — this block is the check, and it runs against the committed
 * document rather than against a fixture written beside it.
 */
describe("every declared destination is one the committed document actually serves", () => {
  it("names a dataset the catalogue builds, with the path shape the document gives it", () => {
    for (const [key, target] of Object.entries(TARGETS)) {
      const declared = dataset(target.id);
      expect(target.id, key).toBe(declared.id);
      expect([...target.pathParameters], key).toEqual(declared.pathParameters);
    }
  });

  it("narrows by a parameter the operation takes, as a path segment or as a query", () => {
    for (const [key, target] of Object.entries(TARGETS)) {
      if (target.filter === null) continue;
      const declared = dataset(target.id);
      const takes =
        declared.pathParameters.includes(target.filter) ||
        queryNames(target.id).includes(target.filter);
      expect(takes, `${key} narrows by ${target.filter}`).toBe(true);
    }
  });

  it("issues a request with nothing missing, which is what a dead crossing would show as", () => {
    for (const crossing of everyCrossing()) {
      if (crossing.next.view !== "explore" || crossing.next.ds === null) continue;
      const request = requestFor(dataset(crossing.next.ds), crossing.next);
      expect(request.missing, crossing.id).toEqual([]);
      expect(request.path, crossing.id).not.toContain("{");
    }
  });

  it("puts the well in the path for the pivot, and in the query for the collection", () => {
    const series = openThisSeries(API10, context()) as Crossing;
    const rows = rowsForThisWell(API10, context()) as Crossing;

    expect(requestFor(dataset("production"), series.next).path).toBe(
      `/v1/wells/${API10}/production`,
    );
    expect(requestFor(dataset("wells"), rows.next).query["q"]).toEqual([API10]);
  });
});

describe("the geographic filter is the document's, and the server's cap is honoured", () => {
  it("reads the cap off the served parameter, so a change to it reddens this test", () => {
    const parameters = SNAPSHOT.paths["/v1/wells"].get.parameters as { name: string; description?: string }[];
    const bbox = parameters.find((parameter) => parameter.name === "bbox");

    expect(bbox?.description).toContain(`capped at ${BBOX_DEGREE_CAP} degrees`);
  });

  it("refuses to send a viewport wider than the cap, and says the view is too wide", () => {
    const crossing = whatsBehindThisLayer(layerDef("wells")?.collection ?? null, WORLD_BBOX, context());

    expect(crossing?.next.extra["f.bbox"]).toBeUndefined();
    expect(crossing?.title).toContain("too wide");
  });

  it("checks both sides of the box, because the server checks them independently", () => {
    const collection = layerDef("wells")?.collection ?? null;
    // A tall, narrow viewport: one degree of longitude, ten of latitude. A cap that only
    // looked at the longitude span would send this and collect a 422.
    const tall = whatsBehindThisLayer(collection, [-103, 40, -102, 50], context());
    const wide = whatsBehindThisLayer(collection, [-110, 47, -100, 48], context());

    expect(tall?.next.extra["f.bbox"], "tall").toBeUndefined();
    expect(wide?.next.extra["f.bbox"], "wide").toBeUndefined();
  });

  it("still sends a box that fits, so the refusal above is not simply always on", () => {
    const crossing = whatsBehindThisLayer(layerDef("wells")?.collection ?? null, TIGHT_BBOX, context());

    expect(crossing?.next.extra["f.bbox"]).toEqual(["-103.5,47.5,-102.5,48.2"]);
  });

  it("names a collection for every layer, or states that none carries it", () => {
    for (const layer of LAYERS) {
      expect(layer, layer.id).toHaveProperty("collection");
    }
    expect(LAYERS.filter((layer) => layer.collection !== null).length).toBeGreaterThan(0);
  });

  it("declares only datasets and parameters the committed document actually serves", () => {
    for (const layer of LAYERS) {
      const collection = layer.collection;
      if (!collection) continue;
      const declared = dataset(collection.dataset);
      // A layer crossing supplies no path segment, so a target that needs one is a 404.
      expect(declared.pathParameters, `${layer.id} path`).toEqual([]);
      if (!collection.bbox) continue;
      expect(queryNames(collection.dataset), `${layer.id} bbox`).toContain(collection.bbox);
    }
  });

  it("offers no crossing for a layer no served collection carries", () => {
    expect(layerDef("lateral-bores")?.collection).toBeNull();
    expect(whatsBehindThisLayer(null, TIGHT_BBOX, context())).toBeNull();
  });
});

describe("the multi-select crossing is deferred, and stated rather than faked", () => {
  it("builds no control, because the operation it needs is not served", () => {
    const ids = everyCrossing().map((crossing) => crossing.id);

    expect(ids).not.toContain("show-these-on-map");
    expect(Object.keys(SNAPSHOT.paths)).not.toContain(DEFERRED_WELLSET.path);
  });

  it("names the operation in the rail's own class B register, so the two cannot drift", () => {
    const entry = CLASS_B_DATASETS.find((candidate) => candidate.path === DEFERRED_WELLSET.path);

    expect(entry, DEFERRED_WELLSET.path).toBeDefined();
    expect(entry?.section).toBe(DEFERRED_WELLSET.section);
  });
});
