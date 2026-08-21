// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  LAYER_STORAGE_KEY,
  STATUS_STORAGE_KEY,
  readCapabilitySet,
  restoreCapabilitySet,
  writeCapabilitySet,
} from "./persist.ts";
import { defaultLayerSet, layerIds } from "./registry.ts";

// Three ids standing in for a registry: these hold the mechanism, not this build's rows. The
// block at the foot of the file is the one that reads the real registry.
const KNOWN = ["wells", "laterals", "spacing-units"];
const DEFAULT_ON = ["wells", "laterals"];

describe("the capability set", () => {
  beforeEach(() => window.localStorage.clear());

  it("falls back to the registry defaults when nothing is stored", () => {
    expect(restoreCapabilitySet(null, KNOWN, DEFAULT_ON)).toEqual(new Set(DEFAULT_ON));
  });

  it("honours a layer the user turned off", () => {
    const stored = { on: ["laterals"], known: KNOWN };
    expect(restoreCapabilitySet(stored, KNOWN, DEFAULT_ON)).toEqual(new Set(["laterals"]));
  });

  it("ships a layer the stored set never knew about at its registry default", () => {
    // The capability set is what tells "the user turned this off" apart from "this layer
    // did not exist when that state was written" — no version ladder, no migration.
    const stored = { on: ["laterals"], known: ["laterals", "spacing-units"] };
    expect(restoreCapabilitySet(stored, KNOWN, DEFAULT_ON)).toEqual(new Set(["laterals", "wells"]));
  });

  it("drops a retired layer without complaint", () => {
    const stored = { on: ["laterals", "sirens"], known: [...KNOWN, "sirens"] };
    expect(restoreCapabilitySet(stored, KNOWN, DEFAULT_ON)).toEqual(new Set(["laterals"]));
  });

  it("treats malformed storage as absent rather than throwing", () => {
    window.localStorage.setItem(LAYER_STORAGE_KEY, "{not json");
    expect(readCapabilitySet(LAYER_STORAGE_KEY)).toBe(null);
    window.localStorage.setItem(LAYER_STORAGE_KEY, JSON.stringify({ on: "wells" }));
    expect(readCapabilitySet(LAYER_STORAGE_KEY)).toBe(null);
  });

  it("round-trips through storage", () => {
    writeCapabilitySet(LAYER_STORAGE_KEY, new Set(["wells"]), KNOWN, 0);
    expect(readCapabilitySet(LAYER_STORAGE_KEY)).toEqual({ on: ["wells"], known: KNOWN });
  });

  it("debounces the write so a bulk toggle does not write once per row", async () => {
    vi.useFakeTimers();
    writeCapabilitySet(LAYER_STORAGE_KEY, new Set(["wells"]), KNOWN);
    writeCapabilitySet(LAYER_STORAGE_KEY, new Set(["laterals"]), KNOWN);
    expect(window.localStorage.getItem(LAYER_STORAGE_KEY)).toBe(null);
    vi.advanceTimersByTime(500);
    expect(readCapabilitySet(LAYER_STORAGE_KEY)?.on).toEqual(["laterals"]);
    vi.useRealTimers();
  });

  it("debounces per key, so a status write does not swallow a layer write in flight", () => {
    // One shared timer would have the legend's All/None cancel a pending layer toggle, and
    // the layer set would silently keep the state before it.
    vi.useFakeTimers();
    const statuses = ["active", "plugged"];
    writeCapabilitySet(LAYER_STORAGE_KEY, new Set(["wells"]), KNOWN);
    writeCapabilitySet(STATUS_STORAGE_KEY, new Set(["active"]), statuses);
    vi.advanceTimersByTime(500);
    expect(readCapabilitySet(LAYER_STORAGE_KEY)?.on).toEqual(["wells"]);
    expect(readCapabilitySet(STATUS_STORAGE_KEY)?.on).toEqual(["active"]);
    vi.useRealTimers();
  });
});

describe("a set stored before the two lateral rows were combined", () => {
  // The combined row is a different capability under a different id, so the {on,known}
  // contract is the whole migration: both retired ids fall out of `known.filter`, and the new
  // row was never seen, so it arrives at its registry default. There is no version ladder
  // because there is nothing a version could tell this shape that the shape does not carry.
  const legacy = {
    on: ["laterals", "tx-laterals", "wells", "tx-wells"],
    known: ["spacing-units", "plss-labels", "laterals", "tx-laterals", "wells", "tx-wells"],
  };

  it("does not resurrect either retired row", () => {
    const restored = restoreCapabilitySet(legacy, layerIds(), defaultLayerSet());
    expect([...restored].sort()).not.toContain("laterals");
    expect([...restored].sort()).not.toContain("tx-laterals");
  });

  it("hands the combined row its new default rather than a bit about a different layer", () => {
    // `laterals` was on because it shipped on, which is not the same fact as a reader choosing
    // it. Inheriting the bit would restore, for every returning reader, the default the
    // combination removed — silently, and at the zoom the owner asked it off.
    const restored = restoreCapabilitySet(legacy, layerIds(), defaultLayerSet());
    expect(restored.has("lateral-bores")).toBe(false);
    expect(restored.has("wells")).toBe(true);
    expect(restored.has("tx-wells")).toBe(true);
  });

  it("keeps the reader's own answer once they give one", () => {
    const chosen = { on: ["lateral-bores", "wells"], known: layerIds() };
    const restored = restoreCapabilitySet(chosen, layerIds(), defaultLayerSet());
    expect(restored.has("lateral-bores")).toBe(true);
  });

  it("survives a set written by a build that predates Texas entirely", () => {
    const older = { on: ["laterals", "wells"], known: ["spacing-units", "laterals", "wells"] };
    const restored = restoreCapabilitySet(older, layerIds(), defaultLayerSet());
    expect(restored.has("lateral-bores")).toBe(false);
    expect(restored.has("tx-wells")).toBe(true);
  });
});
