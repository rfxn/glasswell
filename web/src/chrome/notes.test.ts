// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import { disclosure, emptyState, scopeLine, warningNotes, warningTitle } from "./notes.ts";

describe("a scope line", () => {
  it("joins its parts with the separator the app reads scope by", () => {
    expect(scopeLine(["3 mo", "filed gas or oil", "liquids oil+condensate"]).textContent).toBe(
      "3 mo · filed gas or oil · liquids oil+condensate",
    );
  });

  it("drops empty parts so a caller can pass a conditional without a trailing separator", () => {
    expect(scopeLine(["Proximity, not analogs", null, false, undefined, ""]).textContent).toBe(
      "Proximity, not analogs",
    );
  });

  it("opts out of glossary highlighting, because a scope line is chrome and not a claim", () => {
    expect(scopeLine(["current geometry"]).hasAttribute("data-no-glossary")).toBe(true);
  });
});

describe("a warning title", () => {
  it("is derived from the code, so a code the API adds needs no client edit", () => {
    expect(warningTitle("geometry_not_promoted")).toBe("Geometry not promoted");
    expect(warningTitle("source_history_unavailable")).toBe("Source history unavailable");
  });

  it("takes an override only where the mechanical form misreads", () => {
    expect(warningTitle("list_truncated")).toBe("Ranked cut, not the population");
  });

  it("falls back to the code itself rather than rendering an empty summary", () => {
    expect(warningTitle("")).toBe("");
    expect(warningTitle("_")).toBe("_");
  });
});

describe("warning notes", () => {
  const warning = (code: string, detail: string, pointer?: string) => ({ code, detail, pointer });

  it("collapses by default and keeps the served detail and pointer inside", () => {
    const [note] = warningNotes([
      warning("geometry_not_promoted", "1 horizontal geometry rows were not promoted.", "/geometry"),
    ]);

    expect(note?.tagName).toBe("DETAILS");
    expect(note?.hasAttribute("open")).toBe(false);
    expect(note?.dataset["code"]).toBe("geometry_not_promoted");
    expect(note?.querySelector(".gw-note-summary")?.textContent).toBe("Geometry not promoted");
    expect(note?.querySelector(".gw-note-line")?.textContent).toBe(
      "1 horizontal geometry rows were not promoted.",
    );
    expect(note?.querySelector(".gw-note-source")?.textContent).toBe(
      "geometry_not_promoted · /geometry",
    );
  });

  it("groups repeats of one code and counts them, rather than stacking a wall", () => {
    const notes = warningNotes([
      warning("series_spans_derivations", "7 derivations.", "/series/oil_bbl"),
      warning("series_spans_derivations", "7 derivations.", "/series/gas_mcf"),
      warning("series_spans_derivations", "7 derivations.", "/series/water_bbl"),
    ]);

    expect(notes).toHaveLength(1);
    expect(notes[0]?.querySelector(".gw-note-summary")?.textContent).toBe(
      "Column spans derivations ×3",
    );
    // Every pointer the group carried, not just the first: they are what it points at.
    expect(notes[0]?.querySelector(".gw-note-source")?.textContent).toBe(
      "series_spans_derivations · /series/oil_bbl, /series/gas_mcf, /series/water_bbl",
    );
  });

  it("keeps one note per code when several codes arrive together", () => {
    const notes = warningNotes([warning("list_truncated", "a"), warning("bbox_cap", "b")]);

    expect(notes.map((note) => note.dataset["code"])).toEqual(["list_truncated", "bbox_cap"]);
  });

  it("renders the code alone when the warning names no pointer", () => {
    const [note] = warningNotes([{ code: "bbox_cap" }]);

    expect(note?.querySelector(".gw-note-source")?.textContent).toBe("bbox_cap");
    expect(note?.querySelector(".gw-note-line")?.textContent).toBe("");
  });

  it("keeps every distinct wording a repeated code arrived with, against its own pointers", () => {
    // series_spans_derivations counts derivations per column, so a repeated code is not a
    // repeated sentence: collapsing to the first drops a served figure while still listing
    // every pointer, which reads as one claim covering all three columns.
    const [note] = warningNotes([
      warning("series_spans_derivations", "7 derivations contributed.", "/series/oil_bbl"),
      warning("series_spans_derivations", "7 derivations contributed.", "/series/gas_mcf"),
      warning("series_spans_derivations", "5 derivations contributed.", "/series/water_bbl"),
    ]);

    expect(note?.querySelector(".gw-note-summary")?.textContent).toBe(
      "Column spans derivations ×3",
    );
    expect([...note!.querySelectorAll(".gw-note-line")].map((n) => n.textContent)).toEqual([
      "7 derivations contributed.",
      "5 derivations contributed.",
    ]);
    expect([...note!.querySelectorAll(".gw-note-source")].map((n) => n.textContent)).toEqual([
      "series_spans_derivations · /series/oil_bbl, /series/gas_mcf",
      "series_spans_derivations · /series/water_bbl",
    ]);
  });

  it("returns nothing at all for an empty list, so an empty slot stays empty", () => {
    expect(warningNotes([])).toEqual([]);
  });
});

describe("a disclosure", () => {
  it("puts the summary on the surface and the wording it demotes inside", () => {
    const element = disclosure("How this is judged", "Water never counts as producing.");

    expect(element.querySelector("summary")?.textContent).toBe("How this is judged");
    expect(element.querySelector(".gw-note-detail")?.textContent).toBe(
      "Water never counts as producing.",
    );
    expect(element.hasAttribute("open")).toBe(false);
  });

  it("marks a warning tone without changing its shape", () => {
    expect(disclosure("s", "d", "warning").className).toContain("gw-note-warning");
    expect(disclosure("s", "d").className).not.toContain("gw-note-warning");
  });
});

describe("an empty state", () => {
  it("says what is absent in the fewest words that stay true", () => {
    const element = emptyState("None reported");

    expect(element.textContent).toBe("None reported");
    expect(element.className).toBe("gw-empty");
  });
});
