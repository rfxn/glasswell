// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LAYER_STORAGE_KEY, readLayerSet, restoreLayerSet, writeLayerSet } from "./persist.ts";

const KNOWN = ["wells", "laterals", "spacing-units"];
const DEFAULT_ON = ["wells", "laterals"];

describe("the layer capability set", () => {
  beforeEach(() => window.localStorage.clear());

  it("falls back to the registry defaults when nothing is stored", () => {
    expect(restoreLayerSet(null, KNOWN, DEFAULT_ON)).toEqual(new Set(DEFAULT_ON));
  });

  it("honours a layer the user turned off", () => {
    const stored = { on: ["laterals"], known: KNOWN };
    expect(restoreLayerSet(stored, KNOWN, DEFAULT_ON)).toEqual(new Set(["laterals"]));
  });

  it("ships a layer the stored set never knew about at its registry default", () => {
    // The capability set is what tells "the user turned this off" apart from "this layer
    // did not exist when that state was written" — no version ladder, no migration.
    const stored = { on: ["laterals"], known: ["laterals", "spacing-units"] };
    expect(restoreLayerSet(stored, KNOWN, DEFAULT_ON)).toEqual(new Set(["laterals", "wells"]));
  });

  it("drops a retired layer without complaint", () => {
    const stored = { on: ["laterals", "sirens"], known: [...KNOWN, "sirens"] };
    expect(restoreLayerSet(stored, KNOWN, DEFAULT_ON)).toEqual(new Set(["laterals"]));
  });

  it("treats malformed storage as absent rather than throwing", () => {
    window.localStorage.setItem(LAYER_STORAGE_KEY, "{not json");
    expect(readLayerSet()).toBe(null);
    window.localStorage.setItem(LAYER_STORAGE_KEY, JSON.stringify({ on: "wells" }));
    expect(readLayerSet()).toBe(null);
  });

  it("round-trips through storage", () => {
    writeLayerSet(new Set(["wells"]), KNOWN, 0);
    expect(readLayerSet()).toEqual({ on: ["wells"], known: KNOWN });
  });

  it("debounces the write so a bulk toggle does not write once per row", async () => {
    vi.useFakeTimers();
    writeLayerSet(new Set(["wells"]), KNOWN);
    writeLayerSet(new Set(["laterals"]), KNOWN);
    expect(window.localStorage.getItem(LAYER_STORAGE_KEY)).toBe(null);
    vi.advanceTimersByTime(500);
    expect(readLayerSet()?.on).toEqual(["laterals"]);
    vi.useRealTimers();
  });
});
