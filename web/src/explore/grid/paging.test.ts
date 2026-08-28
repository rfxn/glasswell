// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { buildCatalogue } from "../catalogue.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import {
  pagedQuarantineEnvelope,
  quarantineEnvelope,
  quarantineSummaryEnvelope,
  vintagesEnvelope,
} from "../fixtures.ts";
import { decodeCursor, paginationOf, renderPagination } from "./paging.ts";

const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8"));
const CATALOGUE = buildCatalogue(SNAPSHOT);

function dataset(id: string): CatalogueDataset {
  const found = CATALOGUE.datasets.find((candidate) => candidate.id === id);
  if (!found) throw new Error(`no dataset ${id}`);
  return found;
}

function rendered(model: ReturnType<typeof paginationOf>): HTMLElement {
  return renderPagination(model, { onNext: () => undefined });
}

describe("pagination is a teaching moment, not a control (§3.6)", () => {
  it("decodes the cursor the server actually minted, four keys and no signature", () => {
    const decoded = decodeCursor(pagedQuarantineEnvelope.meta.next_cursor as string);

    expect(decoded).toEqual({
      k: pagedQuarantineEnvelope.data[1]?.last_seen_at,
      t: pagedQuarantineEnvelope.data[1]?.quarantine_id,
      v: null,
      q: "44136fa3",
    });
  });

  it("re-pads and re-alphabets before decoding, because the input is a server detail", () => {
    const minted = btoa(JSON.stringify({ k: "a?b", t: "t", v: null, q: "q" }))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");

    expect(decodeCursor(minted)?.k).toBe("a?b");
    expect(decodeCursor("not-base64-at-all!!")).toBeNull();
    expect(decodeCursor(btoa("[1,2,3]"))).toBeNull();
  });

  it("offers a next control from meta.next_cursor and puts no page number anywhere", () => {
    const model = paginationOf(dataset("quarantine"), SNAPSHOT, pagedQuarantineEnvelope, 2, null);
    const block = rendered(model);

    expect(model.cursored).toBe(true);
    expect(block.querySelector(".gw-page-next")).not.toBeNull();
    // "Total meta.next_cursor honesty per SB-05 §3.10: no page numbers, ever." The word
    // survives — the block says there is no page number — but a numbered one never appears,
    // and no control offers a jump to one.
    expect(block.textContent?.toLowerCase()).not.toMatch(/page\s*\d/);
    expect(block.textContent?.toLowerCase()).toContain("no page number");
    expect(block.querySelectorAll("button")).toHaveLength(2);
    expect(block.textContent).not.toMatch(/\bof ~/);
  });

  it("follows links.next rather than assembling a URL of its own", () => {
    const model = paginationOf(dataset("quarantine"), SNAPSHOT, pagedQuarantineEnvelope, 2, null);
    let followed: string | null = null;
    const block = renderPagination(model, { onNext: (href) => (followed = href) });

    (block.querySelector(".gw-page-next") as HTMLElement).click();

    expect(followed).toBe(pagedQuarantineEnvelope.links.next);
    // Anti-pattern 3: a cell handle carries `#` and `&`, and so does a cursor's own encoding.
    expect(model.next).toContain("cursor=");
  });

  it("teaches all four keys, including the fingerprint that makes a mid-walk edit a 422", () => {
    const block = rendered(
      paginationOf(dataset("quarantine"), SNAPSHOT, pagedQuarantineEnvelope, 2, null),
    );
    const text = block.textContent ?? "";

    expect(block.querySelector(".gw-cursor-token")?.textContent).toBe(
      pagedQuarantineEnvelope.meta.next_cursor,
    );
    for (const key of ["k", "t", "v", "q"]) {
      expect(block.querySelector(`[data-cursor-key="${key}"]`), key).not.toBeNull();
    }
    expect(text).toMatch(/fingerprint of your filters/);
    expect(text).toMatch(/not signed/);
    expect(text).toMatch(/no offset parameter/i);
  });

  it("renders the uncursored form for a collection that has no cursor parameter (m10)", () => {
    const model = paginationOf(dataset("vintages"), SNAPSHOT, vintagesEnvelope, 2, null);
    const block = rendered(model);

    expect(model.cursored).toBe(false);
    expect(block.textContent).toMatch(/not cursor-paginated/);
    // The decode affordance is absent rather than disabled: inventing a cursor UI for an
    // operation with no cursor teaches a contract the API does not offer.
    expect(block.querySelector(".gw-cursor")).toBeNull();
    expect(block.querySelector(".gw-page-next")).toBeNull();
    expect(block.textContent).toMatch(/caps it at 200/);
  });

  it("shows a total where a summary operation supplies one", () => {
    const model = paginationOf(
      dataset("quarantine"),
      SNAPSHOT,
      quarantineEnvelope,
      quarantineEnvelope.data.length,
      quarantineSummaryEnvelope.data.total,
    );

    expect(model.total).toBe(quarantineSummaryEnvelope.data.total);
    expect(rendered(model).textContent).toContain(
      `${quarantineSummaryEnvelope.data.total} rows matched`,
    );
  });

  it("never invents a total where no summary operation serves one", () => {
    const model = paginationOf(dataset("manifests"), SNAPSHOT, pagedQuarantineEnvelope, 2, null);
    const text = rendered(model).textContent ?? "";

    expect(model.total).toBeNull();
    expect(text).toMatch(/showing 1–2 · more available/);
    expect(text).not.toMatch(/~/);
  });

  it("says the walk is complete rather than offering a next that does not exist", () => {
    const terminal = JSON.parse(JSON.stringify(quarantineEnvelope));
    terminal.links.next = null;
    terminal.meta.next_cursor = null;
    const model = paginationOf(
      dataset("quarantine"),
      SNAPSHOT,
      terminal,
      terminal.data.length,
      null,
    );
    const block = rendered(model);

    expect(model.next).toBeNull();
    expect(block.querySelector(".gw-page-next")).toBeNull();
    expect(block.textContent).toContain(`showing all ${terminal.data.length}`);
  });
});
