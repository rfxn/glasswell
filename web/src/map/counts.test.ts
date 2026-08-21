// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Envelope, Warning } from "../api/envelope.ts";
import {
  STATUS_SUMMARY_PATH,
  bboxParam,
  censusOfDrawn,
  createCountSource,
  normaliseBbox,
  parseBbox,
  sameBbox,
  statusCounts,
  statusHandles,
  vocabularyLinks,
} from "./counts.ts";
import type { Bbox, CountsState, WellStatusSummary } from "./counts.ts";
import { UNMAPPED_STATUS } from "./status.ts";

const ND: Bbox = [-104.5, 47.2, -102.1, 48.6];

const figure = (value: string, selector: string) => ({
  value,
  unit: "wells",
  d: `drv_xret5nw2hhouqi5mfvda#${selector}`,
});

const rendered = (box: Bbox): string => box.map((value) => String(value)).join(",");

function summary(box: Bbox, overrides: Partial<WellStatusSummary> = {}): WellStatusSummary {
  return {
    bbox: rendered(box),
    wells: figure("10", "col=wells"),
    unmapped_wells: figure("2", "col=unmapped_wells"),
    statuses: [
      { status: "active", wells: figure("3", "col=wells&status=active") },
      { status: "plugged", wells: figure("2", "col=wells&status=plugged") },
      { status: "dry", wells: figure("1", "col=wells&status=dry") },
    ],
    basins: [],
    vocabulary_rules: ["cr_nd_status_vocab_1"],
    ...overrides,
  };
}

function envelope(
  data: WellStatusSummary,
  links: Record<string, string> = {},
  warnings: Warning[] = [],
): Envelope<WellStatusSummary> {
  return {
    data,
    meta: {
      request_id: "01M0JWJ6ASE1P30C37CVC61WYB",
      as_of: { requested: "latest", resolved: "2026-08-01" },
      source_freshness: {},
      labels: {},
      next_cursor: null,
      warnings,
      deprecations: [],
    },
    links: { self: STATUS_SUMMARY_PATH, next: null, explain: "/v1/explain?h=…&depth=full", ...links },
  };
}

/**
 * A body whose prebuilt explain call is short of its own counts: four buckets, two handles on
 * the link, and the warning that says so. The shape §2.3 rule 4 says is routine.
 */
function truncated(box: Bbox): Envelope<WellStatusSummary> {
  return envelope(
    summary(box),
    { explain: "/v1/explain?h=drv_xret5nw2hhouqi5mfvda%23col%3Dwells&h=drv_xret5nw2hhouqi5mfvda%23col%3Dwells%26status%3Dactive&depth=full" },
    [
      {
        code: "explain_link_truncated",
        detail: "4 counts produced, 2 handles carried, 2 absent",
        pointer: "/links/explain",
      },
    ],
  );
}

/** A load function whose every call is resolved by the test, in whatever order it chooses. */
function deferredLoader() {
  const calls: { bbox: Bbox; signal: AbortSignal; settle(value: Envelope<WellStatusSummary>): void; fail(error: unknown): void }[] = [];
  const load = (bbox: Bbox, signal: AbortSignal): Promise<Envelope<WellStatusSummary>> =>
    new Promise((resolve, reject) => {
      calls.push({ bbox, signal, settle: resolve, fail: reject });
    });
  return { calls, load };
}

function collector() {
  const seen: CountsState[] = [];
  return { seen, onState: (state: CountsState) => void seen.push(state) };
}

const last = (seen: CountsState[]): CountsState => seen[seen.length - 1]!;
const flush = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0));

/** The adjacent double, one unit in the last place away — the smallest difference there is. */
function nextDouble(value: number): number {
  const bits = new DataView(new ArrayBuffer(8));
  bits.setFloat64(0, value);
  bits.setBigUint64(0, bits.getBigUint64(0) + 1n);
  return bits.getFloat64(0);
}

afterEach(() => vi.useRealTimers());

describe("the box the summary is asked for", () => {
  it("renders every corner at the precision that round-trips, not at six digits", () => {
    // gate-wss BLOCK-1, from the other side: two viewports 76 m apart must not send one box.
    expect(bboxParam([-103.5803217, 47.9075, -103.58, 47.91])).toBe(
      "-103.5803217,47.9075,-103.58,47.91",
    );
  });

  it("matches the echo against the viewport by number, so -104 and -104.0 are one box", () => {
    // §2.3 rule 3: the echo is the *parsed* box rendered back, never the string that was sent.
    expect(sameBbox(parseBbox("-104.0,47.0,-102.0,48.0"), [-104, 47, -102, 48])).toBe(true);
  });

  it("refuses an echo that is not four numbers rather than reading past it", () => {
    expect(parseBbox("-104,47,-102")).toBeNull();
    expect(parseBbox("-104,47,-102,north")).toBeNull();
    expect(parseBbox("")).toBeNull();
    expect(sameBbox(null, ND)).toBe(false);
  });

  it("separates two viewports by any difference a double can hold, at no tolerance at all", () => {
    // Not a scale question — an identity one. The echo is the box the query ran with, so any
    // epsilon substituted for `===` is a window in which a count is attributed to the wrong
    // viewport. The last pair differs by one unit in the last place, which is the smallest
    // difference that exists, so no tolerance survives this — not 1e-6, and not 1e-15.
    for (const delta of [1e-7, 1e-9, 1e-12]) {
      expect(sameBbox([-104, 47, -102, 48], [-104 - delta, 47, -102, 48]), `${delta}`).toBe(false);
      expect(sameBbox([-104, 47, -102, 48], [-104, 47, -102, 48 + delta]), `${delta}`).toBe(false);
    }
    expect(sameBbox([-104, 47, -102, 48], [nextDouble(-104), 47, -102, 48])).toBe(false);
    expect(sameBbox([-104, 47, -102, 48], [-104, 47, -102, nextDouble(48)])).toBe(false);
  });

  it("clamps a latitude the projection can produce and the API refuses", () => {
    expect(normaliseBbox([-104, -95.4, -102, 91.2])).toEqual([-104, -90, -102, 90]);
  });

  it("asks for the whole world when the viewport wraps, rather than a slice of what is seen", () => {
    // A wrapped viewport shows the world more than once, so the world is what is in view. The
    // alternative — clamping to [-180, maxLon] — drops wells the reader can see, which is the
    // defect this whole track exists to remove.
    expect(normaliseBbox([-220, -60, -80, 60])).toEqual([-180, -60, 180, 60]);
    expect(normaliseBbox([-400, -60, 400, 60])).toEqual([-180, -60, 180, 60]);
  });

  it("leaves an ordinary viewport alone", () => {
    expect(normaliseBbox(ND)).toEqual(ND);
  });
});

describe("the counts the legend is given", () => {
  it("carries only the classes the box holds — absent, never zero", () => {
    const counts = statusCounts(summary(ND));

    expect(counts).toEqual({ active: 3, plugged: 2, dry: 1, [UNMAPPED_STATUS.id]: 2 });
    expect("inactive" in counts).toBe(false);
    expect("expired" in counts).toBe(false);
  });

  it("keys the absence bucket onto the legend's own class, which the API never publishes", () => {
    // §2.3 rule 1: the API must not publish "unmapped" as if it were in the vocabulary.
    const data = summary(ND);
    expect(data.statuses.map((row) => row.status)).not.toContain(UNMAPPED_STATUS.id);
    expect(statusCounts(data)[UNMAPPED_STATUS.id]).toBe(2);
  });

  it("reports no absence class at all when the box holds none", () => {
    const counts = statusCounts(summary(ND, { unmapped_wells: null }));
    expect(UNMAPPED_STATUS.id in counts).toBe(false);
  });

  it("reads the decimal string, never the object", () => {
    // SB-07 §9.1(a): `value` is a string. `+figure` is NaN and NaN.toLocaleString() is "NaN".
    const counts = statusCounts(summary(ND, {
      statuses: [{ status: "active", wells: figure("20643", "col=wells&status=active") }],
    }));
    expect(counts["active"]).toBe(20_643);
    expect(Number.isFinite(counts["active"])).toBe(true);
  });

  it("gives every class the handle of its own count, not one borrowed from a neighbour", () => {
    const handles = statusHandles(summary(ND));

    expect(handles["active"]).toContain("status=active");
    expect(handles["plugged"]).toContain("status=plugged");
    expect(handles["active"]).not.toBe(handles["plugged"]);
    expect(handles[UNMAPPED_STATUS.id]).toContain("col=unmapped_wells");
  });

  it("names the vocabulary rules the answer was shaped by, linked where they can be read", () => {
    // R8: a mapping decision is a row a reader can open, not a string in the legend.
    const links = vocabularyLinks(
      summary(ND, { vocabulary_rules: ["cr_nd_status_vocab_1", "cr_tx_status_vocab_1"] }),
      { cr_nd_status_vocab_1: "/v1/conformance/cr_nd_status_vocab_1" },
    );

    expect(links).toEqual([
      { rule: "cr_nd_status_vocab_1", href: "/v1/conformance/cr_nd_status_vocab_1" },
      { rule: "cr_tx_status_vocab_1", href: null },
    ]);
  });
});

describe("a viewport that settles", () => {
  it("says it is loading before it says anything else", () => {
    const { load } = deferredLoader();
    const { seen, onState } = collector();
    createCountSource({ load, onState }).request(ND);

    expect(seen).toHaveLength(1);
    expect(seen[0]).toEqual({ kind: "loading", bbox: ND });
  });

  it("asks the summary for the box it normalised, not the raw viewport", () => {
    const { calls, load } = deferredLoader();
    createCountSource({ load, onState: () => {} }).request([-220, -95, -80, 95]);

    expect(calls[0]?.bbox).toEqual([-180, -90, 180, 90]);
  });

  it("paints the counts the box answered with, and the total beside them", async () => {
    const { calls, load } = deferredLoader();
    const { seen, onState } = collector();
    createCountSource({ load, onState }).request(ND);
    calls[0]!.settle(envelope(summary(ND)));
    await flush();

    const state = last(seen);
    expect(state.kind).toBe("ready");
    if (state.kind !== "ready") return;
    expect(state.counts).toEqual({ active: 3, plugged: 2, dry: 1, [UNMAPPED_STATUS.id]: 2 });
    expect(state.total).toBe(10);
    expect(state.totalHandle).toContain("col=wells");
  });

  it("publishes no explain link, truncated or otherwise — every count addresses itself", async () => {
    // §2.3 rule 4: the prebuilt call is capped at 20 handles and a whole-of-ND box exceeds it
    // routinely, so a published link would be a promise the response cannot keep. The
    // assertion is on what reaches the legend, not on the fixture: carrying `links.explain`
    // or `meta.warnings` into the state turns this red.
    const { calls, load } = deferredLoader();
    const { seen, onState } = collector();
    createCountSource({ load, onState }).request(ND);
    calls[0]!.settle(truncated(ND));
    await flush();

    const state = last(seen);
    expect(state.kind).toBe("ready");
    if (state.kind !== "ready") return;
    const published = Object.keys(state);
    expect(published).not.toContain("explain");
    expect(published).not.toContain("warnings");
    expect(JSON.stringify(state)).not.toContain("/v1/explain");
    expect(JSON.stringify(state)).not.toContain("explain_link_truncated");
    // Four buckets the link could carry two of, and four handles that each resolve alone.
    expect(Object.keys(state.handles).sort()).toEqual(["active", "dry", "plugged", "unmapped"]);
    for (const handle of Object.values(state.handles)) expect(handle).toMatch(/^drv_\w+#col=/);
  });

  it("reports an empty box as no classes and no total, rather than a screen of zeroes", async () => {
    const { calls, load } = deferredLoader();
    const { seen, onState } = collector();
    createCountSource({ load, onState }).request(ND);
    calls[0]!.settle(
      envelope(summary(ND, { wells: null, unmapped_wells: null, statuses: [], basins: [] })),
    );
    await flush();

    const state = last(seen);
    expect(state.kind).toBe("ready");
    if (state.kind !== "ready") return;
    expect(state.counts).toEqual({});
    expect(state.total).toBeNull();
  });

  it("does not ask again for a box it has already answered", async () => {
    const { calls, load } = deferredLoader();
    const source = createCountSource({ load, onState: () => {} });
    source.request(ND);
    calls[0]!.settle(envelope(summary(ND)));
    await flush();
    source.request([...ND] as unknown as Bbox);

    expect(calls).toHaveLength(1);
  });

  it("does not ask twice for a box it is already asking about", () => {
    const { calls, load } = deferredLoader();
    const source = createCountSource({ load, onState: () => {} });
    source.request(ND);
    source.request(ND);

    expect(calls).toHaveLength(1);
  });

  it("asks again after a failure, because an error is not an answer", async () => {
    const { calls, load } = deferredLoader();
    const source = createCountSource({ load, onState: () => {} });
    source.request(ND);
    calls[0]!.fail(new Error("network"));
    await flush();
    source.request(ND);

    expect(calls).toHaveLength(2);
  });
});

describe("a late answer for a viewport that has been left", () => {
  it("never paints, even though it arrives last", async () => {
    const { calls, load } = deferredLoader();
    const { seen, onState } = collector();
    const source = createCountSource({ load, onState });
    const moved: Bbox = [-102, 46, -100, 47];

    source.request(ND);
    source.request(moved);
    calls[1]!.settle(envelope(summary(moved, {
      statuses: [{ status: "active", wells: figure("7", "col=wells&status=active") }],
      unmapped_wells: null,
      wells: figure("7", "col=wells"),
    })));
    await flush();
    // The first viewport's answer, arriving after the second's.
    calls[0]!.settle(envelope(summary(ND)));
    await flush();

    const state = last(seen);
    expect(state.kind).toBe("ready");
    if (state.kind !== "ready") return;
    expect(state.bbox).toEqual(moved);
    expect(state.counts).toEqual({ active: 7 });
  });

  it("cannot resurrect a viewport by failing late either", async () => {
    const { calls, load } = deferredLoader();
    const { seen, onState } = collector();
    const source = createCountSource({ load, onState });
    const moved: Bbox = [-102, 46, -100, 47];

    source.request(ND);
    source.request(moved);
    calls[1]!.settle(envelope(summary(moved)));
    await flush();
    calls[0]!.fail(new Error("network"));
    await flush();

    expect(last(seen).kind).toBe("ready");
  });

  it("is abandoned through the signal the client seam already takes", () => {
    const { calls, load } = deferredLoader();
    const source = createCountSource({ load, onState: () => {} });
    source.request(ND);
    source.request([-102, 46, -100, 47]);

    expect(calls[0]?.signal.aborted).toBe(true);
    expect(calls[1]?.signal.aborted).toBe(false);
  });

  it("survives a pan of ten viewports and paints the last one", async () => {
    const { calls, load } = deferredLoader();
    const { seen, onState } = collector();
    const source = createCountSource({ load, onState });
    const boxes: Bbox[] = Array.from(
      { length: 10 },
      (_, index) => [-104 + index * 0.1, 47, -102 + index * 0.1, 48] as Bbox,
    );
    for (const box of boxes) source.request(box);
    // Answered in reverse: the first viewport's answer is the last one to land.
    for (const index of [...calls.keys()].reverse()) {
      calls[index]!.settle(envelope(summary(boxes[index]!, {
        wells: figure(String(index), "col=wells"),
        unmapped_wells: null,
        statuses: [{ status: "active", wells: figure(String(index), "col=wells&status=active") }],
      })));
      await flush();
    }

    const state = last(seen);
    expect(state.kind).toBe("ready");
    if (state.kind !== "ready") return;
    expect(state.bbox).toEqual(boxes[9]);
    expect(state.counts).toEqual({ active: 9 });
  });

  it("refuses an answer whose echo names a box it did not ask about", async () => {
    // Not a stale answer — a wrong one. A cache or a proxy can hand back a body for another
    // box, and a count painted under this viewport's legend would be a false claim.
    const { calls, load } = deferredLoader();
    const { seen, onState } = collector();
    createCountSource({ load, onState }).request(ND);
    calls[0]!.settle(envelope(summary([-99, 30, -98, 31])));
    await flush();

    const state = last(seen);
    expect(state.kind).toBe("error");
    if (state.kind !== "error") return;
    expect(state.message).toMatch(/viewport/i);
  });
});

describe("a summary that cannot be had", () => {
  it("reports the failure rather than the previous viewport's numbers", async () => {
    const { calls, load } = deferredLoader();
    const { seen, onState } = collector();
    const source = createCountSource({ load, onState });
    source.request(ND);
    calls[0]!.settle(envelope(summary(ND)));
    await flush();

    const moved: Bbox = [-102, 46, -100, 47];
    const before = seen.length;
    source.request(moved);
    expect(last(seen)).toEqual({ kind: "loading", bbox: moved });

    calls[1]!.fail(new Error("Service degraded"));
    await flush();

    const state = last(seen);
    expect(state.kind).toBe("error");
    if (state.kind !== "error") return;
    expect(state.message).toContain("Service degraded");
    // Nothing published for the new viewport carried a count — the first viewport's numbers
    // are not what the reader is looking at, and a failure may not borrow them.
    expect(seen.slice(before).map((published) => published.kind)).toEqual(["loading", "error"]);
  });

  it("gives up on a box that never answers, and says that is why", async () => {
    vi.useFakeTimers();
    const { load } = deferredLoader();
    const { seen, onState } = collector();
    createCountSource({ load, onState, timeoutMs: 8_000 }).request(ND);
    await vi.advanceTimersByTimeAsync(8_001);

    const state = last(seen);
    expect(state.kind).toBe("error");
    if (state.kind !== "error") return;
    expect(state.message).toMatch(/too long|timed out/i);
  });

  it("does not report a timeout for a viewport the reader has already left", async () => {
    vi.useFakeTimers();
    const { calls, load } = deferredLoader();
    const { seen, onState } = collector();
    const source = createCountSource({ load, onState, timeoutMs: 8_000 });
    source.request(ND);
    const moved: Bbox = [-102, 46, -100, 47];
    source.request(moved);
    calls[1]!.settle(envelope(summary(moved)));
    await vi.advanceTimersByTimeAsync(8_001);

    expect(last(seen).kind).toBe("ready");
  });
});

describe("the census of what the canvas drew", () => {
  const feature = (api10: string | undefined, derivation?: string) => ({
    properties: {
      ...(api10 === undefined ? {} : { api10 }),
      ...(derivation === undefined ? {} : { derivation_id: derivation }),
    },
  });

  it("counts a well once however many tiles carried it", () => {
    // A point inside a tile's buffer ring is returned once per tile that holds it, and a
    // doubled dot would put the drawn number above the box's own count of the same wells.
    expect(censusOfDrawn([feature("3305310451"), feature("3305310451"), feature("3305300001")]))
      .toEqual({ wells: 2, derivation: null });
  });

  it("counts a feature the tile did not identify rather than dropping it", () => {
    expect(censusOfDrawn([feature(undefined), feature(undefined)]).wells).toBe(2);
  });

  it("carries the geometry build the tiles were cut from", () => {
    expect(censusOfDrawn([feature("3305310451", "drv_geometry")]).derivation).toBe("drv_geometry");
  });

  it("is zero, and says nothing about a build, when nothing was drawn", () => {
    expect(censusOfDrawn([])).toEqual({ wells: 0, derivation: null });
  });
});

describe("the same area at two zooms", () => {
  it("is one box, one request and one set of counts", async () => {
    // The reported defect, as an assertion: the map's zoom is not an input to the question
    // "what is in this area", so two settles over one box cannot disagree.
    const { calls, load } = deferredLoader();
    const { seen, onState } = collector();
    const source = createCountSource({ load, onState });

    source.request(ND);
    calls[0]!.settle(envelope(summary(ND)));
    await flush();
    const atLowZoom = last(seen);

    source.request(ND);
    const atHighZoom = last(seen);

    expect(calls).toHaveLength(1);
    expect(atHighZoom).toBe(atLowZoom);
  });
});
