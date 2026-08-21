export interface JsonSchema {
  type?: string;
  format?: string;
  pattern?: string;
  enum?: string[];
  maximum?: number;
  minimum?: number;
  default?: unknown;
  items?: JsonSchema;
  anyOf?: JsonSchema[];
  oneOf?: JsonSchema[];
  description?: string;
  properties?: Record<string, JsonSchema>;
  $ref?: string;
  [key: string]: unknown;
}

export interface Parameter {
  name: string;
  in: string;
  required?: boolean;
  description?: string;
  schema: JsonSchema;
}

export type ControlKind = "chips" | "text" | "date" | "month" | "stepper" | "toggle" | "bbox";

export interface Control {
  name: string;
  kind: ControlKind;
  description: string;
  multiple: boolean;
  hoisted: boolean;
  options?: string[];
  maximum?: number;
  minimum?: number;
  pattern?: string;
  fallback?: string;
}

export interface FacetBar {
  controls: Control[];
  /** §3.1 rule 3: the filters sibling collections accept and this one does not. */
  unsupported: string[];
}

// The shell owns these: `as_of` is global rather than per-dataset, and `cursor` is the
// pagination block's, where it is taught rather than typed into.
const HOISTED = new Set(["as_of", "cursor"]);
const MONTH_PATTERN = "^\\d{4}-\\d{2}$";

/**
 * SB-08 §3.1 m5: FastAPI serialises an optional parameter as `anyOf: [real, {type: null}]`, so
 * a naive `schema.type` read finds `undefined` on almost every filter. Two survivors is a
 * design question and this refuses to answer it by guessing.
 */
export function unwrapNullable(schema: JsonSchema): JsonSchema {
  const members = schema.anyOf ?? schema.oneOf;
  if (!members) return schema;
  const survivors = members.filter((member) => member.type !== "null");
  if (survivors.length !== 1) {
    throw new Error(
      `a parameter union with ${survivors.length} non-null members is a design question,` +
        " not a rendering one; name the one shape the control should take",
    );
  }
  return unwrapNullable(survivors[0] as JsonSchema);
}

export function controlFor(parameter: Parameter): Control {
  const schema = unwrapNullable(parameter.schema);
  const description = parameter.description ?? schema.description ?? "";
  const base = {
    name: parameter.name,
    description,
    multiple: false,
    hoisted: HOISTED.has(parameter.name),
  };

  if (schema.type === "array") {
    const items = schema.items ? unwrapNullable(schema.items) : {};
    return items.enum
      ? { ...base, kind: "chips", multiple: true, options: [...items.enum] }
      : { ...base, kind: "text", multiple: true };
  }
  if (schema.enum) return { ...base, kind: "chips", options: [...schema.enum] };
  if (schema.type === "boolean") {
    return { ...base, kind: "toggle", fallback: String(schema.default ?? false) };
  }
  if (schema.type === "integer" || schema.type === "number") {
    const stepper: Control = { ...base, kind: "stepper" };
    if (schema.maximum !== undefined) stepper.maximum = schema.maximum;
    if (schema.minimum !== undefined) stepper.minimum = schema.minimum;
    if (schema.default !== undefined) stepper.fallback = String(schema.default);
    return stepper;
  }
  if (schema.pattern === MONTH_PATTERN) return { ...base, kind: "month", pattern: schema.pattern };
  if (schema.format === "date") return { ...base, kind: "date" };
  if (parameter.name === "bbox") return { ...base, kind: "bbox" };
  return { ...base, kind: "text" };
}

/**
 * The declared facets first, every other query parameter after them, path parameters never —
 * a path parameter is an anchor the route already carries, not a dimension to narrow.
 */
export function controlsFor(
  operation: { parameters?: Parameter[] },
  facets: readonly string[],
  siblings: readonly { parameters?: Parameter[] }[],
): FacetBar {
  const query = (operation.parameters ?? []).filter((parameter) => parameter.in === "query");
  const rank = (name: string): number => {
    const declared = facets.indexOf(name);
    return declared === -1 ? facets.length : declared;
  };
  const controls = [...query]
    .sort((left, right) => rank(left.name) - rank(right.name))
    .map(controlFor);

  const own = new Set(query.map((parameter) => parameter.name));
  const counts = new Map<string, number>();
  for (const sibling of siblings) {
    for (const parameter of sibling.parameters ?? []) {
      if (parameter.in !== "query" || own.has(parameter.name)) continue;
      counts.set(parameter.name, (counts.get(parameter.name) ?? 0) + 1);
    }
  }
  // Only what most sibling collections accept. The bare set difference names every parameter
  // any dataset declares — nineteen of them on quarantine, including `bbox` — and a line that
  // long is noise a reader learns to skip, which is the opposite of §3.1 rule 3's intent.
  const common = Math.max(1, Math.ceil(siblings.length / 2));
  const unsupported = [...counts.entries()]
    .filter(([, seen]) => seen >= common)
    .map(([name]) => name)
    .sort();
  return { controls, unsupported };
}
