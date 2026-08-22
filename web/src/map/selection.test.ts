import { describe, expect, it } from "vitest";

import { createSelection } from "./selection.ts";
import type { FeatureRef } from "./selection.ts";

const SOURCES = ["nd_wells", "nd_laterals", "tx_wells"];
const refsFor = (api10: string): FeatureRef[] =>
  SOURCES.map((source) => ({ source, sourceLayer: source, id: api10 }));

function target(live: string[] = SOURCES) {
  const sources = new Set(live);
  const calls: string[] = [];
  return {
    calls,
    add: (source: string) => sources.add(source),
    clear: () => sources.clear(),
    gateway: {
      hasSource: (source: string) => sources.has(source),
      set: (reference: FeatureRef) => calls.push(`set ${reference.source}/${reference.id}`),
      remove: (reference: FeatureRef) => calls.push(`remove ${reference.source}/${reference.id}`),
    },
  };
}

describe("what the map remembers about the selected well", () => {
  it("writes the selection into every source that exists", () => {
    const stub = target();
    createSelection(refsFor, stub.gateway).select("3305310451");

    expect(stub.calls).toEqual([
      "set nd_wells/3305310451",
      "set nd_laterals/3305310451",
      "set tx_wells/3305310451",
    ]);
  });

  it("removes exactly what it wrote before writing the next one", () => {
    const stub = target();
    const selection = createSelection(refsFor, stub.gateway);
    selection.select("3305310451");
    stub.calls.length = 0;
    selection.select("3306100001");

    expect(stub.calls).toEqual([
      "remove nd_wells/3305310451",
      "remove nd_laterals/3305310451",
      "remove tx_wells/3305310451",
      "set nd_wells/3306100001",
      "set nd_laterals/3306100001",
      "set tx_wells/3306100001",
    ]);
  });

  // The crash gate-c10 recorded as N3. MapLibre's SourceFeatureState.coalesceChanges runs
  // `delete this.state[layer][feature][key]` for every queued deletion, and for a feature it
  // never coalesced a state for that indexes undefined: an uncaught TypeError inside
  // Map._render, which takes the requestAnimationFrame loop down with it. The remove is only
  // safe when this module did the matching set, so the bookkeeping has to be of writes.
  it("never removes state it did not write", () => {
    const stub = target([]);
    const selection = createSelection(refsFor, stub.gateway);
    selection.select("3305310451");
    stub.add("nd_wells");
    stub.add("nd_laterals");
    stub.add("tx_wells");
    selection.select(null);

    expect(stub.calls).toEqual([]);
  });

  it("paints a selection that arrived before the style's sources did", () => {
    // main.ts restores ?well= as soon as createMap returns, which is before `load` fires and
    // therefore before setBasemap has put a single source on the map. Without a resync the
    // deep-linked well is never highlighted at all.
    const stub = target([]);
    const selection = createSelection(refsFor, stub.gateway);
    selection.select("3305310451");
    expect(stub.calls).toEqual([]);

    stub.add("nd_wells");
    selection.resync();

    expect(stub.calls).toEqual(["set nd_wells/3305310451"]);
  });

  it("stays quiet once every live source carries the selection", () => {
    // resync() runs on `styledata`, which fires repeatedly; re-writing feature state on each
    // one would churn a repaint per event for no change.
    const stub = target();
    const selection = createSelection(refsFor, stub.gateway);
    selection.select("3305310451");
    stub.calls.length = 0;
    selection.resync();
    selection.resync();

    expect(stub.calls).toEqual([]);
  });

  it("does no work at all on a settled resync", () => {
    // `styledata` fires on every setFilter the zoom handler issues, so a settled resync that
    // still rebuilt the reference list would rebuild it once per gated layer per pinch frame.
    let built = 0;
    const counted = (api10: string): FeatureRef[] => {
      built += 1;
      return refsFor(api10);
    };
    const stub = target();
    const selection = createSelection(counted, stub.gateway);
    selection.select("3305310451");
    built = 0;
    for (let index = 0; index < 50; index += 1) selection.resync();

    expect(built).toBe(0);
  });

  it("has nothing to resync when no well is selected", () => {
    const stub = target();
    const selection = createSelection(refsFor, stub.gateway);
    selection.resync();

    expect(stub.calls).toEqual([]);
  });

  it("forgets what a replaced style took with it, without trying to remove it", () => {
    // setStyle({diff:false}) builds new source caches and every feature state written into the
    // old ones is gone. Removing against the new ones is the same uncaught TypeError, reached
    // by a different route: select a well, change the basemap, close the card.
    const stub = target();
    const selection = createSelection(refsFor, stub.gateway);
    selection.select("3305310451");
    stub.calls.length = 0;

    selection.forget();
    selection.select(null);

    expect(stub.calls).toEqual([]);
  });

  it("repaints the surviving selection into the sources a new style brought", () => {
    const stub = target();
    const selection = createSelection(refsFor, stub.gateway);
    selection.select("3305310451");
    selection.forget();
    stub.calls.length = 0;
    selection.resync();

    expect(stub.calls).toEqual([
      "set nd_wells/3305310451",
      "set nd_laterals/3305310451",
      "set tx_wells/3305310451",
    ]);
  });

  it("skips the source that vanished between the write and the removal", () => {
    // DR-81: a source removed without a style swap — removeSource, not setStyle — is a route
    // on which forget() is never called, so the removal pass walks a written reference whose
    // source is gone. Removing against it is N3's uncaught TypeError again; the hasSource
    // guard on the removal loop is what stands between them.
    const stub = target();
    const selection = createSelection(refsFor, stub.gateway);
    selection.select("3305310451");
    stub.calls.length = 0;
    stub.clear();
    stub.add("nd_wells");
    stub.add("nd_laterals");
    selection.select(null);

    expect(stub.calls).toEqual([
      "remove nd_wells/3305310451",
      "remove nd_laterals/3305310451",
    ]);
  });

  it("skips the sources a style does not carry and paints the ones it does", () => {
    const stub = target(["nd_wells"]);
    const selection = createSelection(refsFor, stub.gateway);
    selection.select("3305310451");
    stub.calls.length = 0;
    selection.select(null);

    expect(stub.calls).toEqual(["remove nd_wells/3305310451"]);
  });
});
