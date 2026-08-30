import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { DATASET_KEY, buildCatalogue } from "./catalogue.ts";
import { isJoinField } from "./detail/chips.ts";

/**
 * UDM-SPEC §6.4, risk R-3: `wells.row_id` must stay `["/api10"]`.
 *
 * The hop table is derived, not hand-maintained — `chips.ts` matches a column's leaf against
 * every dataset's declared identity — so every column named `api10` anywhere in the explorer
 * reaches the wells dataset for free. Adding `well_id` to the wells dataset is a column; making
 * it the row identity is what kills all of those hops at once, and it is the change a reader
 * optimising the UDM key would think was tidy. This file makes it a red build instead.
 */

// vitest roots at web/, so this is the committed contract artifact, not a fixture of it.
const SNAPSHOT_PATH = "../tests/contract/openapi_snapshot.json";

interface Document {
  paths: Record<string, Record<string, Record<string, unknown>>>;
}

function snapshot(): Document {
  return JSON.parse(readFileSync(SNAPSHOT_PATH, "utf8")) as Document;
}

function datasetsOf(document: Document) {
  return buildCatalogue(document).datasets;
}

function wellsDeclaration(document: Document): Record<string, unknown> {
  for (const operations of Object.values(document.paths)) {
    const declared = operations["get"]?.[DATASET_KEY] as Record<string, unknown> | undefined;
    if (declared?.["id"] === "wells") return declared;
  }
  throw new Error("the document declares no wells dataset");
}

function carriesApi10(dataset: { id: string; anchors: string[]; columns: { default?: string[] } }) {
  return [...(dataset.columns.default ?? []), ...dataset.anchors].includes("/api10");
}

describe("the wells dataset's row identity is the api10, and that is load-bearing (§6.4)", () => {
  it("declares exactly `/api10`, and nothing composite", () => {
    const wells = datasetsOf(snapshot()).find((dataset) => dataset.id === "wells");

    expect(wells?.row_id).toEqual(["/api10"]);
  });

  it("is the reason other datasets' api10 columns hop, so the pin is not decorative", () => {
    const datasets = datasetsOf(snapshot());
    const borrowers = datasets.filter(
      (dataset) => dataset.id !== "wells" && carriesApi10(dataset),
    );

    // A document where nothing else carried an api10 would make the counterfactual below
    // vacuous: no hop would die because none existed.
    expect(borrowers.map((dataset) => dataset.id)).toEqual([
      "production",
      "production_pools",
      "completions",
      "neighbors",
      "type_curves",
    ]);
  });

  it("kills every one of those hops the moment the identity becomes `/well_id`", () => {
    const optimised = snapshot();
    wellsDeclaration(optimised)["row_id"] = ["/well_id"];

    expect(isJoinField("/api10", datasetsOf(snapshot()))).toBe(true);
    expect(isJoinField("/api10", datasetsOf(optimised))).toBe(false);
  });
});
