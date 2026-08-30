// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_STATE, serializeState } from "../../app/state.ts";
import type { AppState } from "../../app/state.ts";
import { buildCatalogue } from "../catalogue.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import {
  HOP_CAP,
  curlFor,
  curlList,
  inertChip,
  isJoinField,
  joinsFor,
  recordStep,
  renderChip,
  renderTrail,
  resetTrail,
  stateFor,
  trail,
} from "./chips.ts";
import type { Join } from "./chips.ts";

const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8"));
const CATALOGUE = buildCatalogue(SNAPSHOT);
const DATASETS = CATALOGUE.datasets;

function dataset(id: string): CatalogueDataset {
  const found = DATASETS.find((candidate) => candidate.id === id);
  if (!found) throw new Error(`no dataset ${id}`);
  return found;
}

function state(over: Partial<AppState> = {}): AppState {
  return { ...DEFAULT_STATE, view: "explore", ...over };
}

function joins(pointer: string, value: string, from: string, over: Partial<AppState> = {}): Join[] {
  return joinsFor(pointer, value, {
    from: dataset(from),
    datasets: DATASETS,
    document: SNAPSHOT,
    state: state({ ds: from, ...over }),
  });
}

function targets(found: Join[]): string[] {
  return found.map((join) => `${join.kind}:${join.target.id}`);
}

beforeEach(() => {
  resetTrail();
  window.history.replaceState(null, "", "/?view=explore");
});

describe("an id field is one the document could resolve (§3.3)", () => {
  it("takes a `_id` name, or any dataset's own identity", () => {
    expect(isJoinField("/rule_id", DATASETS)).toBe(true);
    expect(isJoinField("/manifest_ids", DATASETS)).toBe(true);
    // Wells declare `/api10` as their row identity, so an api10 anywhere is a hop.
    expect(isJoinField("/api10", DATASETS)).toBe(true);
  });

  it("leaves a content address alone: sha256 joins nothing and is not an id", () => {
    expect(isJoinField("/sha256", DATASETS)).toBe(false);
    expect(isJoinField("/row_fingerprint", DATASETS)).toBe(false);
  });
});

describe("the hop table is derived from row_id, never hand-maintained (8.5)", () => {
  it("lands a rule_id on the conformance rule that owns it", () => {
    const found = joins("/rule_id", "cr_nd_stream_vocab_1", "quarantine");

    expect(targets(found)).toContain("row:conformance");
    expect(found[0]?.filter).toBe(null);
  });

  it("reads a prefixed id as the id it is, which is what makes §3.3's diagram real", () => {
    expect(targets(joins("/first_seen_manifest_id", "man_e", "quarantine"))).toContain("row:manifests");
    expect(targets(joins("/promotion_derivation_id", "drv_a", "vintages"))).toContain("row:derivations");
  });

  it("offers the collections a source_id narrows, beside the source it identifies", () => {
    const found = joins("/source_id", "nd_mpr_xlsx", "quarantine");

    expect(targets(found)).toEqual(
      expect.arrayContaining(["row:sources", "filtered:manifests", "filtered:conformance"]),
    );
    // The dataset the reader is already in is not a hop, and every narrowing names its parameter.
    expect(targets(found)).not.toContain("filtered:quarantine");
    for (const join of found.filter((one) => one.kind === "filtered")) {
      expect(join.filter).toBe("source_id");
    }
  });

  it("does not offer a row its own identity as a hop", () => {
    expect(targets(joins("/quarantine_id", "qr_1", "quarantine"))).not.toContain("row:quarantine");
    expect(targets(joins("/api10", "3305310451", "wells"))).not.toContain("row:wells");
  });

  it("drops a hop whose target still needs a path parameter nobody supplies", () => {
    // `/pm` is production's whole identity, so a pooled row could hop to it — but only when the
    // api10 the path is read by travels too. Without it the link would be a 404 wearing a chip.
    expect(targets(joins("/pm", "2026-06", "production_pools"))).toEqual([]);
    expect(
      targets(joins("/pm", "2026-06", "production_pools", { extra: { "f.api10": ["3305302532"] } })),
    ).toContain("row:production");
  });
});

describe("a hop carries as_of and drops the population it left (§3.3)", () => {
  const from = state({
    ds: "quarantine",
    row: "qr_1",
    extra: { as_of: ["2026-08-01"], "f.state": ["open"], cursor: ["opaque"] },
  });

  it("carries as_of, sets the target row, and leaves the old filters behind", () => {
    const [hop] = joins("/rule_id", "cr_nd_stream_vocab_1", "quarantine");
    const next = stateFor(hop as Join, from);

    expect(next.ds).toBe("conformance");
    expect(next.row).toBe("cr_nd_stream_vocab_1");
    expect(next.extra).toEqual({ as_of: ["2026-08-01"] });
  });

  it("writes the narrowing as the parameter it becomes on the wire", () => {
    const filtered = joins("/source_id", "nd_mpr_xlsx", "quarantine").find(
      (join) => join.target.id === "manifests",
    );
    const next = stateFor(filtered as Join, from);

    expect(next.ds).toBe("manifests");
    expect(next.row).toBe(null);
    expect(next.extra["f.source_id"]).toEqual(["nd_mpr_xlsx"]);
  });

  it("carries the target's path parameters, because without them there is nothing to read", () => {
    const [hop] = joins("/pm", "2026-06", "production_pools", {
      extra: { "f.api10": ["3305302532"] },
    });
    const next = stateFor(hop as Join, state({ ds: "production_pools", extra: { "f.api10": ["3305302532"] } }));

    expect(next.extra["f.api10"]).toEqual(["3305302532"]);
  });
});

describe("a chip is a link, and an unresolvable id is inert and says so (§3.3)", () => {
  it("renders the target's own URL so it copies and opens in a tab", () => {
    const [hop] = joins("/rule_id", "cr_nd_stream_vocab_1", "quarantine");
    const chip = renderChip(hop as Join, state({ ds: "quarantine" }), {
      navigate: vi.fn(),
      signal: new AbortController().signal,
    });

    expect(chip.tagName).toBe("A");
    expect(chip.getAttribute("href")).toBe(serializeState(stateFor(hop as Join, state({ ds: "quarantine" }))));
  });

  it("navigates in-document on a plain click and lets the browser have a modified one", () => {
    const navigate = vi.fn();
    const [hop] = joins("/rule_id", "cr_nd_stream_vocab_1", "quarantine");
    const chip = renderChip(hop as Join, state({ ds: "quarantine" }), {
      navigate,
      signal: new AbortController().signal,
    });

    chip.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(navigate).toHaveBeenCalledTimes(1);

    chip.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, ctrlKey: true }));
    expect(navigate).toHaveBeenCalledTimes(1);
  });

  it("has nowhere to send land_unit_id, which no P-A operation serves", () => {
    expect(isJoinField("/land_unit_id", DATASETS)).toBe(true);
    expect(joins("/land_unit_id", "151N-101W-11", "wells")).toEqual([]);

    const inert = inertChip("/land_unit_id");
    expect(inert.tagName).not.toBe("A");
    expect(inert.dataset["hop"]).toBe("inert");
    expect(inert.title).toContain("land_unit_id");
  });
});

describe("the breadcrumb records the walk and copies as the calls that made it (8.3)", () => {
  const step = (index: number, path: string) => ({
    operationId: `op_${index}`,
    request: { path, query: { as_of: ["2026-08-01"] } },
    url: `?view=explore&hop=${index}`,
    title: `hop ${index}`,
  });

  it("lists three operations after three hops, in the order they were walked", () => {
    for (const index of [1, 2, 3]) recordStep(step(index, `/v1/one/${index}`));
    const nav = renderTrail({ signal: new AbortController().signal });

    expect(nav?.querySelectorAll(".gw-trail-step")).toHaveLength(3);
    expect([...(nav?.querySelectorAll(".gw-trail-op") ?? [])].map((one) => one.textContent)).toEqual([
      "op_1",
      "op_2",
      "op_3",
    ]);
  });

  it("copies a numbered list of curls whose URLs are the requests that were issued", () => {
    for (const index of [1, 2, 3]) recordStep(step(index, `/v1/one/${index}`));
    const copied = curlList();

    for (const index of [1, 2, 3]) {
      expect(copied).toContain(`# ${index}. hop ${index}`);
      expect(copied).toContain(`${window.location.origin}/v1/one/${index}?as_of=2026-08-01`);
    }
    expect(copied.split("curl ")).toHaveLength(4);
  });

  it("names the key rather than carrying one, because a copied line is a leak path", () => {
    const line = curlFor(step(1, "/v1/one/1"));

    expect(line).toContain("$GLASSWELL_KEY");
    expect(line).not.toMatch(/[0-9a-f]{32}/);
  });

  it("keeps the last three hops and says the older ones are not recorded", () => {
    for (const index of [1, 2, 3, 4]) recordStep(step(index, `/v1/one/${index}`));

    expect(trail()).toHaveLength(HOP_CAP);
    expect(trail().map((one) => one.operationId)).toEqual(["op_2", "op_3", "op_4"]);
    expect(renderTrail({ signal: new AbortController().signal })?.textContent).toContain(
      "earlier steps are not recorded",
    );
  });

  it("shortens rather than grows when the reader goes back to a step it already has", () => {
    for (const index of [1, 2, 3]) recordStep(step(index, `/v1/one/${index}`));
    recordStep(step(2, "/v1/one/2"));

    expect(trail().map((one) => one.operationId)).toEqual(["op_1", "op_2"]);
  });

  it("renders nothing at all until there is a walk to describe", () => {
    recordStep(step(1, "/v1/one/1"));

    expect(renderTrail({ signal: new AbortController().signal })).toBe(null);
  });
});
