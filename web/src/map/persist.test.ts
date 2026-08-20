// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  LAYER_STORAGE_KEY,
  STATUS_STORAGE_KEY,
  readCapabilitySet,
  restoreCapabilitySet,
  writeCapabilitySet,
} from "./persist.ts";

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
