import { termDetail } from "../../glossary/store.ts";
import { unwrapNullable } from "../facets/schema.ts";
import type { JsonSchema, Parameter } from "../facets/schema.ts";
import { GLOSSARY_KEY } from "../grid/schema.ts";
import type { Operation } from "../grid/schema.ts";

/** A-8, keyed by parameter name — not by pointer, and not every member is present (C5 P1). */
export const SEMANTICS_KEY = "x-glasswell-semantics";

export interface Fact {
  label: string;
  reason: string | null;
}

export interface ParameterSemantics {
  name: string;
  in: string;
  required: boolean;
  type: string;
  /** WHAT: the OpenAPI description, which SB-04 §7.1 requires of every parameter. */
  what: string;
  /** SO: authored per operation, because the consequence differs per operation (§4.3). */
  so: string | null;
  /** The term WHY and SEE resolve through; a parameter has no `meta.labels` path (C5 P6). */
  termId: string | null;
  annotated: boolean;
  facts: Fact[];
}

export interface SemanticsCoverage {
  annotated: number;
  total: number;
  percent: number;
}

export interface Explanation {
  why: string | null;
  see: string[];
}

const CAP_REASON =
  "this operation declares its own cap; another collection's cap is a different number";
const ENUM_REASON = "a closed vocabulary: a value outside it is refused, not ignored";

function entryFor(operation: Operation | null, name: string): Record<string, unknown> | null {
  const semantics = operation?.[SEMANTICS_KEY];
  if (typeof semantics !== "object" || semantics === null) return null;
  const entry = (semantics as Record<string, unknown>)[name];
  return typeof entry === "object" && entry !== null ? (entry as Record<string, unknown>) : null;
}

/**
 * The facet bar refuses to guess which control a two-member union should take, and is right to.
 * The pane only prints the type, and a printed type is not a control — so a union it cannot
 * name is named as one rather than taking the whole parameter row down with it.
 */
function typeOf(parameter: Parameter): string {
  let schema: JsonSchema;
  try {
    schema = unwrapNullable(parameter.schema);
  } catch {
    return "union";
  }
  if (schema.type === "array") {
    const items = schema.items ? unwrapNullable(schema.items) : {};
    return `array of ${items.type ?? "string"}`;
  }
  const base = schema.type ?? "string";
  return schema.format ? `${base} (${schema.format})` : base;
}

function factsOf(parameter: Parameter): Fact[] {
  let schema: JsonSchema;
  try {
    schema = unwrapNullable(parameter.schema);
  } catch {
    return [];
  }
  const items = schema.type === "array" && schema.items ? unwrapNullable(schema.items) : null;
  const values = schema.enum ?? items?.enum;
  const facts: Fact[] = [];
  if (parameter.required) facts.push({ label: "required", reason: null });
  if (schema.default !== undefined) facts.push({ label: `default ${String(schema.default)}`, reason: null });
  if (schema.maximum !== undefined) facts.push({ label: `at most ${schema.maximum}`, reason: CAP_REASON });
  if (schema.minimum !== undefined) facts.push({ label: `at least ${schema.minimum}`, reason: null });
  if (values) facts.push({ label: `one of ${values.join(", ")}`, reason: ENUM_REASON });
  if (schema.pattern) facts.push({ label: `matches ${schema.pattern}`, reason: null });
  return facts;
}

export function semanticsFor(operation: Operation | null): ParameterSemantics[] {
  return (operation?.parameters ?? []).map((parameter: Parameter) => {
    const entry = entryFor(operation, parameter.name);
    const so = entry?.["so"];
    const term = entry?.[GLOSSARY_KEY];
    return {
      name: parameter.name,
      in: parameter.in,
      required: parameter.required === true,
      type: typeOf(parameter),
      what: parameter.description ?? parameter.schema.description ?? "",
      so: typeof so === "string" ? so : null,
      termId: typeof term === "string" ? term : null,
      annotated: entry !== null,
      facts: factsOf(parameter),
    };
  });
}

/** §4.3: the parameters A-8 has not reached yet are counted, never quietly dropped. */
export function coverageOf(parameters: readonly ParameterSemantics[]): SemanticsCoverage {
  const annotated = parameters.filter((parameter) => parameter.annotated).length;
  const total = parameters.length;
  return { annotated, total, percent: total === 0 ? 0 : Math.round((annotated / total) * 100) };
}

/**
 * WHY and SEE have exactly one source and it is not this client: the glossary row the operation
 * named. A term that does not resolve leaves WHY null, which renders as the degradation §4.3
 * specifies rather than as a sentence the pane made up.
 */
export async function explain(termId: string): Promise<Explanation> {
  try {
    const term = await termDetail(termId);
    return { why: term.expanded_definition, see: term.related_terms };
  } catch {
    return { why: null, see: [] };
  }
}
