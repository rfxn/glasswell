// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { describe, expect, it, vi } from "vitest";

import { DEFAULT_STATE } from "../../app/state.ts";
import type { Envelope } from "../../api/envelope.ts";
import { buildCatalogue } from "../catalogue.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import { pagedQuarantineEnvelope, productionEnvelope, wellsEnvelope } from "../fixtures.ts";
import { SORT_KEY, directionOf, ordered, renderSort, sortColumnOf } from "./sort.ts";
import type { Row } from "./rows.ts";

const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8"));
const CATALOGUE = buildCatalogue(SNAPSHOT);

function dataset(id: string): CatalogueDataset {
  const found = CATALOGUE.datasets.find((candidate) => candidate.id === id);
  if (!found) throw new Error(`no dataset ${id}`);
  return found;
}

function rows(count: number): Row[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `row-${index}`,
    index,
    elementIndex: index,
    elementPointer: `/${index}`,
    cells: {},
  }));
}

describe("which collections can be reordered at all", () => {
  it("takes the sort column the operation declares", () => {
    expect(sortColumnOf(dataset("production"), productionEnvelope as unknown as Envelope<unknown>))
      .toBe("/pm");
  });

  /**
   * A page-one descending view whose "next" button walks the server's ascending order is a lie
   * about what the reader is looking at. Reordering is offered only where the loaded rows are
   * the whole filtered population.
   */
  it("refuses when the server has another page to give", () => {
    expect(
      sortColumnOf(dataset("quarantine"), pagedQuarantineEnvelope as unknown as Envelope<unknown>),
    ).toBeNull();
  });

  it("refuses a collection that declares no sort at all", () => {
    const undeclared = { ...dataset("wells"), columns: { hidden: [], hidden_reason: {} } };
    expect(sortColumnOf(undeclared, wellsEnvelope as unknown as Envelope<unknown>)).toBeNull();
  });
});

describe("the direction a link carries", () => {
  it("is the server's own order until the reader says otherwise", () => {
    expect(directionOf(DEFAULT_STATE)).toBe("asc");
    expect(directionOf({ ...DEFAULT_STATE, extra: { [SORT_KEY]: ["nonsense"] } })).toBe("asc");
  });

  it("is read off the URL, so a reordered view is a link somebody else can open", () => {
    expect(directionOf({ ...DEFAULT_STATE, extra: { [SORT_KEY]: ["desc"] } })).toBe("desc");
  });
});

describe("reordering the loaded rows", () => {
  it("leaves the server's order alone when it is the order asked for", () => {
    const served = rows(4);
    expect(ordered(served, "asc")).toBe(served);
  });

  it("reverses the declared sort rather than re-sorting values it cannot parse", () => {
    expect(ordered(rows(4), "desc").map((row) => row.id)).toEqual([
      "row-3",
      "row-2",
      "row-1",
      "row-0",
    ]);
  });
});

describe("the control", () => {
  it("names the column it reorders and which way round it is", () => {
    const commit = vi.fn();
    const control = renderSort("/pm", "pm", "asc", commit);
    const buttons = [...control.querySelectorAll("button")];
    expect(control.textContent).toContain("pm");
    expect(buttons.map((button) => button.getAttribute("aria-pressed"))).toEqual(["true", "false"]);
    buttons[1]?.click();
    expect(commit).toHaveBeenCalledWith("desc");
  });

  it("clears the parameter rather than writing the default into every link", () => {
    const commit = vi.fn();
    const control = renderSort("/pm", "pm", "desc", commit);
    [...control.querySelectorAll("button")][0]?.click();
    expect(commit).toHaveBeenCalledWith("asc");
  });
});
