// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from "vitest";

import { buildIndex, highlight, scan } from "./index.ts";
import type { GlossaryIndexPayload } from "./index.ts";

const payload: GlossaryIndexPayload = {
  index_version: "gix_abc123",
  entries: [
    { surface: "water cut", term_id: "gt_water_cut", n_words: 2 },
    { surface: "type curve", term_id: "gt_type_curve", n_words: 2 },
    { surface: "gor", term_id: "gt_gor", n_words: 1 },
    { surface: "water", term_id: "gt_water", n_words: 1 },
    { surface: "spud date", term_id: "gt_spud", n_words: 2 },
  ],
  stopwords: ["band", "stream", "vintage"],
};

let index = buildIndex(payload);

beforeEach(() => {
  index = buildIndex(payload);
  document.body.innerHTML = "";
});

describe("buildIndex", () => {
  it("orders surfaces longest-first so the regex matches the longest term", () => {
    expect(index.surfaces).toEqual(["type curve", "spud date", "water cut", "water", "gor"]);
  });

  it("excludes stopwords from auto-scanning while keeping them resolvable (M7)", () => {
    const withStopword = buildIndex({
      ...payload,
      entries: [...payload.entries, { surface: "band", term_id: "gt_band", n_words: 1 }],
    });
    expect(withStopword.surfaces).not.toContain("band");
    expect(withStopword.termIdFor("band")).toBe("gt_band");
  });

  it("tolerates an empty index instead of throwing", () => {
    const empty = buildIndex({ index_version: "gix_0", entries: [], stopwords: [] });
    expect(empty.surfaces).toEqual([]);
    expect(scan("water cut is high", empty)).toEqual([{ text: "water cut is high" }]);
  });
});

describe("scan", () => {
  it("returns segments, never DOM", () => {
    expect(scan("the water cut rose", index)).toEqual([
      { text: "the " },
      { text: "water cut", termId: "gt_water_cut" },
      { text: " rose" },
    ]);
  });

  it("matches case-insensitively", () => {
    expect(scan("GOR climbed", index)[0]).toEqual({ text: "GOR", termId: "gt_gor" });
  });

  it("resolves overlapping terms to the longest match", () => {
    const segments = scan("water cut", index);
    expect(segments).toEqual([{ text: "water cut", termId: "gt_water_cut" }]);
  });

  it("matches on word boundaries only", () => {
    expect(scan("watercut", index)).toEqual([{ text: "watercut" }]);
    expect(scan("gorge", index)).toEqual([{ text: "gorge" }]);
  });

  it("does not match inside a number or an identifier run", () => {
    expect(scan("3305301234", index)).toEqual([{ text: "3305301234" }]);
  });
});

describe("highlight", () => {
  it("wraps matches in gw-term elements", () => {
    document.body.innerHTML = "<p>the water cut rose</p>";
    highlight(document.body, index);
    const term = document.querySelector("gw-term");
    expect(term?.getAttribute("term-id")).toBe("gt_water_cut");
    expect(term?.textContent).toBe("water cut");
  });

  it("skips text inside an existing anchor", () => {
    document.body.innerHTML = '<p><a href="/x">water cut</a></p>';
    highlight(document.body, index);
    expect(document.querySelector("gw-term")).toBeNull();
  });

  it("skips text inside a code span", () => {
    document.body.innerHTML = "<p><code>water cut</code></p>";
    highlight(document.body, index);
    expect(document.querySelector("gw-term")).toBeNull();
  });

  it("skips text inside a figure, where a number is data and not vocabulary", () => {
    document.body.innerHTML = "<gw-figure>water cut</gw-figure>";
    highlight(document.body, index);
    expect(document.querySelector("gw-term")).toBeNull();
  });

  it("is idempotent: running it twice does not nest spans", () => {
    document.body.innerHTML = "<p>the water cut rose</p>";
    highlight(document.body, index);
    highlight(document.body, index);
    expect(document.querySelectorAll("gw-term")).toHaveLength(1);
    expect(document.querySelector("gw-term gw-term")).toBeNull();
  });

  it("highlights every occurrence of a term once each", () => {
    document.body.innerHTML = "<p>water cut here, water cut there</p>";
    highlight(document.body, index);
    expect(document.querySelectorAll("gw-term")).toHaveLength(2);
  });
});
