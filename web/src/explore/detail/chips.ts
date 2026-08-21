import { apiUrl } from "../../api/client.ts";
import { serializeState } from "../../app/state.ts";
import type { AppState } from "../../app/state.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import type { Parameter } from "../facets/schema.ts";
import { operationFor } from "../grid/schema.ts";
import { FILTER_PREFIX, requestFor } from "../router.ts";

/** SB-08 §3.3: a hop lands on a row, or on the collection narrowed to this id. Never on a chain. */
export type HopKind = "row" | "filtered";

export interface Join {
  field: string;
  value: string;
  target: CatalogueDataset;
  kind: HopKind;
  /** The query parameter the target narrows by, where the document declares one. */
  filter: string | null;
}

export interface JoinContext {
  from: CatalogueDataset;
  datasets: readonly CatalogueDataset[];
  document: unknown;
  state: AppState;
}

export interface TrailStep {
  operationId: string;
  request: { path: string; query: Record<string, string[]> };
  /** The app URL this step sits at, which is how a back navigation truncates the trail. */
  url: string;
  title: string;
}

/**
 * S9 budgets a trace at three interactions, so a trail longer than three is a signal rather
 * than a feature: the breadcrumb keeps the three most recent hops and says the older ones are
 * not recorded, instead of implying it remembers a walk it did not.
 */
export const HOP_CAP = 3;

const KEY_PLACEHOLDER = "$GLASSWELL_KEY";

let steps: TrailStep[] = [];

function leafOf(pointer: string): string {
  return pointer.replace(/^\//, "");
}

/** A single-pointer identity is the only one a chip can carry; a composite id is not a value. */
function identityLeaf(dataset: CatalogueDataset): string | null {
  const [only] = dataset.row_id;
  return dataset.row_id.length === 1 && only !== undefined ? leafOf(only) : null;
}

/**
 * The plan's 8.5 rule is exact-leaf equality, and two of the four hops §3.3 draws cannot be
 * expressed by it: `first_seen_manifest_id` is a manifest id and `promotion_derivation_id` is a
 * derivation id. The widening stays derived — a `_`-boundary suffix, longest first — so there
 * is still no hand-maintained mapping table.
 */
function identityTarget(leaf: string, datasets: readonly CatalogueDataset[]): CatalogueDataset | null {
  const candidates = datasets
    .map((dataset) => ({ dataset, identity: identityLeaf(dataset) }))
    .filter((entry): entry is { dataset: CatalogueDataset; identity: string } => entry.identity !== null);

  const exact = candidates.find((entry) => entry.identity === leaf);
  if (exact) return exact.dataset;

  const suffixed = candidates
    .filter((entry) => leaf.endsWith(`_${entry.identity}`))
    .sort((a, b) => b.identity.length - a.identity.length);
  return suffixed[0]?.dataset ?? null;
}

function queryParameter(document: unknown, dataset: CatalogueDataset, name: string): boolean {
  const parameters = (operationFor(document, dataset.operationId)?.parameters ?? []) as Parameter[];
  return parameters.some((parameter) => parameter.name === name && parameter.in === "query");
}

/** An id field is one the document could resolve: a `_id` name, or another dataset's identity. */
export function isJoinField(pointer: string, datasets: readonly CatalogueDataset[]): boolean {
  const leaf = leafOf(pointer);
  if (leaf.endsWith("_id") || leaf.endsWith("_ids")) return true;
  return datasets.some((dataset) => identityLeaf(dataset) === leaf);
}

export function joinsFor(pointer: string, value: string, context: JoinContext): Join[] {
  const leaf = leafOf(pointer).replace(/_ids$/, "_id");
  const joins: Join[] = [];
  const identity = identityTarget(leaf, context.datasets);
  const ownIdentity = identity?.id === context.from.id && context.from.row_id.includes(pointer);

  if (identity && !ownIdentity) {
    joins.push({
      field: leaf,
      value,
      target: identity,
      kind: "row",
      filter: identityFilter(context.document, identity),
    });
  }
  for (const target of context.datasets) {
    if (target.id === context.from.id || target.id === identity?.id) continue;
    if (!queryParameter(context.document, target, leaf)) continue;
    joins.push({ field: leaf, value, target, kind: "filtered", filter: leaf });
  }
  // A hop whose target still needs a path parameter nobody can supply is a 404 wearing a link.
  return joins.filter((join) => requestFor(join.target, stateFor(join, context.state)).missing.length === 0);
}

function identityFilter(document: unknown, target: CatalogueDataset): string | null {
  const identity = identityLeaf(target);
  return identity && queryParameter(document, target, identity) ? identity : null;
}

/**
 * §3.3: the hop carries `as_of` and pushes history. The source collection's own filters and
 * cursor do not travel — they narrowed a different population — but the target's path
 * parameters do, because without them there is nothing to read.
 */
export function stateFor(join: Join, from: AppState): AppState {
  const extra: Record<string, string[]> = {};
  const asOf = from.extra["as_of"];
  if (asOf && asOf.length > 0) extra["as_of"] = [...asOf];
  for (const name of join.target.pathParameters) {
    const carried = from.extra[`${FILTER_PREFIX}${name}`];
    if (carried && carried.length > 0) extra[`${FILTER_PREFIX}${name}`] = [...carried];
  }
  if (join.filter) extra[`${FILTER_PREFIX}${join.filter}`] = [join.value];

  return {
    ...from,
    view: "explore",
    tab: "datasets",
    ds: join.target.id,
    row: join.kind === "row" ? join.value : null,
    extra,
  };
}

export interface ChipOptions {
  navigate(next: AppState): void;
  signal: AbortSignal;
}

export function renderChip(join: Join, from: AppState, options: ChipOptions): HTMLElement {
  const next = stateFor(join, from);
  const chip = document.createElement("a");
  chip.className = "gw-join-chip";
  chip.href = serializeState(next);
  chip.dataset["hop"] = join.kind;
  chip.dataset["target"] = join.target.id;
  chip.textContent =
    join.kind === "row" ? join.target.title : `${join.target.title} · ${join.field}`;
  chip.title =
    join.kind === "row"
      ? `Open this ${join.field} in ${join.target.title}, one request, as_of carried across.`
      : `Narrow ${join.target.title} to ${join.field} ${join.value}, one request.`;
  chip.addEventListener(
    "click",
    (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
      event.preventDefault();
      options.navigate(next);
    },
    { signal: options.signal },
  );
  return chip;
}

/** §3.3's first property: a hop with no operation is inert and says which id it could not open. */
export function inertChip(pointer: string): HTMLElement {
  const leaf = leafOf(pointer);
  const inert = document.createElement("span");
  inert.className = "gw-join-chip gw-join-inert";
  inert.dataset["hop"] = "inert";
  inert.textContent = "no operation";
  inert.title = `No served operation reads ${leaf}, so this id cannot be opened. The gap is stated rather than hidden behind a client-side join.`;
  return inert;
}

export function recordStep(step: TrailStep): void {
  const seen = steps.findIndex((existing) => existing.url === step.url);
  if (seen >= 0) steps = steps.slice(0, seen);
  steps.push(step);
  if (steps.length > HOP_CAP) steps = steps.slice(steps.length - HOP_CAP);
}

export function trail(): readonly TrailStep[] {
  return steps;
}

export function resetTrail(): void {
  steps = [];
}

/** The URL is `apiUrl`'s, resolved against this origin — never a host literal in the bundle. */
export function curlFor(step: TrailStep): string {
  const url = new URL(apiUrl(step.request.path, step.request.query), window.location.origin);
  return `curl -s -H "X-Glasswell-Key: ${KEY_PLACEHOLDER}" '${url.toString()}'`;
}

export function curlList(walked: readonly TrailStep[] = steps): string {
  return walked.map((step, index) => `# ${index + 1}. ${step.title}\n${curlFor(step)}`).join("\n");
}

export interface TrailOptions {
  signal: AbortSignal;
}

/** §3.3: "how did I get here" — the operations walked, and the calls that walked them. */
export function renderTrail(options: TrailOptions): HTMLElement | null {
  const walked = trail();
  if (walked.length < 2) return null;

  const nav = document.createElement("nav");
  nav.className = "gw-trail";
  nav.setAttribute("aria-label", "How did I get here");

  const list = document.createElement("ol");
  list.className = "gw-trail-steps";
  for (const step of walked) {
    const item = document.createElement("li");
    item.className = "gw-trail-step";
    const title = document.createElement("span");
    title.textContent = step.title;
    const operation = document.createElement("code");
    operation.className = "gw-trail-op";
    operation.textContent = step.operationId;
    item.append(title, operation);
    list.append(item);
  }

  const commands = document.createElement("pre");
  commands.className = "gw-trail-curl";
  commands.hidden = true;
  commands.textContent = curlList(walked);

  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "gw-trail-copy";
  copy.textContent = "how did I get here";
  copy.setAttribute("aria-expanded", "false");
  copy.addEventListener(
    "click",
    () => {
      commands.hidden = !commands.hidden;
      copy.setAttribute("aria-expanded", String(!commands.hidden));
      // Clipboard access is a permission, not a guarantee, so the text is on the page either
      // way and the copy is the convenience rather than the mechanism.
      if (!commands.hidden) void navigator.clipboard?.writeText(commands.textContent ?? "");
    },
    { signal: options.signal },
  );

  const cap = document.createElement("p");
  cap.className = "gw-trail-cap";
  cap.textContent = `the last ${HOP_CAP} hops; earlier steps are not recorded`;

  nav.append(list, copy, commands, cap);
  return nav;
}
