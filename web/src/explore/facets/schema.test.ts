import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { controlFor, controlsFor, unwrapNullable } from "./schema.ts";
import type { Parameter } from "./schema.ts";

// The committed document, not a hand-written copy of it: a FastAPI upgrade that changes how an
// optional parameter serialises breaks this file rather than the facet bar (SB-08 §3.1 m5).
const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8")) as {
  paths: Record<string, Record<string, { operationId?: string; parameters?: Parameter[] }>>;
};

function parameterOf(operationId: string, name: string): Parameter {
  for (const item of Object.values(SNAPSHOT.paths)) {
    for (const operation of Object.values(item)) {
      if (operation.operationId !== operationId) continue;
      const found = (operation.parameters ?? []).find((parameter) => parameter.name === name);
      if (found) return found;
    }
  }
  throw new Error(`${operationId} declares no parameter ${name}`);
}

function operationOf(operationId: string): { parameters?: Parameter[] } {
  for (const item of Object.values(SNAPSHOT.paths)) {
    for (const operation of Object.values(item)) {
      if (operation.operationId === operationId) return operation;
    }
  }
  throw new Error(`no operation ${operationId}`);
}

describe("a facet control is chosen from the parameter's own schema (SB-08 §3.1)", () => {
  it("reads five real parameter schemas out of the document, so the cases are not invented", () => {
    expect(parameterOf("list_quarantine", "state").schema.anyOf).toHaveLength(2);
    expect(parameterOf("list_wells", "as_of").schema.anyOf).toHaveLength(2);
    expect(parameterOf("list_wells", "operator").schema.anyOf).toHaveLength(2);
    expect(parameterOf("list_quarantine", "limit").schema.anyOf).toBeUndefined();
    expect(parameterOf("get_well_production", "stream").schema.anyOf).toHaveLength(2);
  });

  it("makes an optional enum a chip group over the enum's own vocabulary", () => {
    const control = controlFor(parameterOf("list_quarantine", "state"));

    expect(control.kind).toBe("chips");
    expect(control.options).toEqual(["open", "released", "accepted_loss", "superseded"]);
    expect(control.multiple).toBe(false);
  });

  it("makes an optional date a date control, and hoists as_of out of the facet bar", () => {
    const control = controlFor(parameterOf("list_wells", "as_of"));

    expect(control.kind).toBe("date");
    expect(control.hoisted).toBe(true);
    expect(controlFor(parameterOf("list_conformance_rules", "effective_at")).hoisted).toBe(false);
  });

  it("makes an optional free string a text control carrying the API's own description", () => {
    const control = controlFor(parameterOf("list_wells", "operator"));

    expect(control.kind).toBe("text");
    expect(control.description).toBe("Case-insensitive substring of the reported operator.");
  });

  it("makes a bare integer a stepper stating the server's cap, which differs per collection", () => {
    expect(controlFor(parameterOf("list_quarantine", "limit"))).toMatchObject({
      kind: "stepper",
      maximum: 200,
      minimum: 1,
    });
    // The difference is a teachable fact, not a bug: wells caps ten times higher than the spine.
    expect(controlFor(parameterOf("list_wells", "limit")).maximum).toBe(1000);
  });

  it("makes a repeatable array of enums a multi-select over the item enum", () => {
    const control = controlFor(parameterOf("get_well_production", "stream"));

    expect(control.kind).toBe("chips");
    expect(control.multiple).toBe(true);
    expect(control.options).toEqual(["oil", "gas", "water"]);
  });

  it("reads a month pattern as a month control and carries the pattern the server declares", () => {
    const control = controlFor(parameterOf("get_well_production", "from"));

    expect(control.kind).toBe("month");
    expect(control.pattern).toBe("^\\d{4}-\\d{2}$");
  });

  it("reads a boolean as a toggle and a bbox as its own control", () => {
    expect(controlFor(parameterOf("list_manifests", "head_only")).kind).toBe("toggle");
    expect(controlFor(parameterOf("list_wells", "bbox")).kind).toBe("bbox");
  });

  it("fails loudly on two non-null survivors rather than guessing which one to render", () => {
    const union = { anyOf: [{ type: "string" }, { type: "integer" }, { type: "null" }] };

    expect(() => unwrapNullable(union)).toThrow(/2 non-null members/);
    // One survivor is the whole contract; a bare schema is already its own survivor.
    expect(unwrapNullable({ anyOf: [{ type: "string" }, { type: "null" }] })).toEqual({
      type: "string",
    });
    expect(unwrapNullable({ type: "integer", maximum: 200 })).toEqual({
      type: "integer",
      maximum: 200,
    });
  });

  it("shows what a collection cannot be filtered by, rather than hiding the absence", () => {
    const siblings = [
      "list_quarantine",
      "list_wells",
      "list_manifests",
      "list_derivations",
      "list_conformance_rules",
      "list_glossary_terms",
    ].map(operationOf);
    const vintages = controlsFor(operationOf("list_vintages"), ["source_id"], siblings);

    // Derived from the snapshot's own head rather than hand-listed, so an additive served
    // parameter (explain and explain_depth landed with v0.27's snapshot) moves this expectation
    // instead of reddening it — the same reason line 8 reads the committed document.
    const query = (operationOf("list_vintages").parameters ?? [])
      .filter((parameter) => parameter.in === "query")
      .map((parameter) => parameter.name);
    expect(query).toEqual(expect.arrayContaining(["source_id", "limit"]));
    expect(vintages.controls.map((control) => control.name)).toEqual([
      "source_id",
      ...query.filter((name) => name !== "source_id"),
    ]);
    // §3.1 rule 3: list_vintages accepts no cursor at all, and the reader is told so.
    expect(vintages.unsupported).toContain("cursor");
    expect(vintages.unsupported).not.toContain("source_id");
    // …and told only what most collections accept. `state` lives on two of eleven operations,
    // and naming every parameter any dataset declares turns the line into noise.
    expect(vintages.unsupported).not.toContain("state");
    expect(vintages.unsupported).not.toContain("bbox");
  });

  it("names as_of as an absence on the one kitchen collection that cannot take it", () => {
    const siblings = ["list_wells", "list_manifests", "get_well_production"].map(operationOf);
    const quarantine = controlsFor(operationOf("list_quarantine"), [], siblings);

    expect(quarantine.unsupported).toEqual(["as_of"]);
  });

  it("puts the declared facets first and keeps every other query parameter after them", () => {
    const quarantine = controlsFor(operationOf("list_quarantine"), ["state", "stage"], []);

    expect(quarantine.controls.slice(0, 2).map((control) => control.name)).toEqual([
      "state",
      "stage",
    ]);
    expect(quarantine.controls.map((control) => control.name)).toContain("limit");
    // A path parameter is an anchor, not a facet: it belongs to the route, not to the bar.
    expect(controlsFor(operationOf("get_well_production"), ["stream"], []).controls.map((c) => c.name))
      .not.toContain("api10");
  });
});
