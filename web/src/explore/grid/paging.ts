import { getEnvelope } from "../../api/client.ts";
import type { Envelope } from "../../api/envelope.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import { operationFor, pathFor } from "./schema.ts";

export interface CursorParts {
  k: unknown;
  t: unknown;
  v: unknown;
  q: unknown;
}

export interface Pagination {
  cursored: boolean;
  limitCap: number | null;
  token: string | null;
  next: string | null;
  decoded: CursorParts | null;
  shown: number;
  total: number | null;
}

/** SB-04 §2.3: `base64url(canonical_json({k,t,v,q}))`, deliberately unsigned. */
const CURSOR_KEYS = ["k", "t", "v", "q"] as const;

const TEACHING: Record<(typeof CURSOR_KEYS)[number], string> = {
  k: "sort key of the last row on this page",
  t: "tiebreak id, so two rows sharing a sort key cannot be skipped or repeated",
  v: "the as-of this walk is pinned to — why a restatement landing mid-walk cannot shift rows",
  q: "fingerprint of your filters — why changing one mid-walk is a 422 instead of a wrong answer",
};

export function decodeCursor(token: string): CursorParts | null {
  try {
    const normalised = token.replace(/-/g, "+").replace(/_/g, "/");
    const parsed: unknown = JSON.parse(atob(normalised.padEnd(Math.ceil(normalised.length / 4) * 4, "=")));
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return null;
    const record = parsed as Record<string, unknown>;
    if (!CURSOR_KEYS.every((key) => key in record)) return null;
    return { k: record["k"], t: record["t"], v: record["v"], q: record["q"] };
  } catch {
    // A cursor the client cannot read is the server's business, not a reason to lose the grid.
    return null;
  }
}

export function paginationOf(
  dataset: CatalogueDataset,
  document: unknown,
  envelope: Pick<Envelope<unknown>, "meta" | "links">,
  shown: number,
  total: number | null,
): Pagination {
  const operation = operationFor(document, dataset.operationId);
  const parameters = operation?.parameters ?? [];
  const limit = parameters.find((parameter) => parameter.name === "limit");
  const token = envelope.meta.next_cursor;
  return {
    cursored: parameters.some((parameter) => parameter.name === "cursor"),
    limitCap: typeof limit?.schema.maximum === "number" ? limit.schema.maximum : null,
    token,
    next: envelope.links.next ?? null,
    decoded: token ? decodeCursor(token) : null,
    shown,
    total,
  };
}

/**
 * §3.6: where a summary operation supplies a total, show it. Where it does not, there is no
 * total to show — an invented one is a naked number wearing a comma, so this returns null and
 * the count line says `more available` instead.
 *
 * **And a total over a different population is the same defect wearing a comma.**
 * `get_quarantine_summary` declares `source_id` and `state` and not `stage`, `reason_code` or
 * `rule_id` **[V]**; FastAPI ignores a query parameter an operation does not declare, so
 * forwarding the grid's filters returned a total over a broader set and the count line read
 * "29 rows matched · showing 1–10" for a filter that matched ten. The summary is asked only
 * when it can express every filter the grid applied.
 */
export async function summaryTotalFor(
  dataset: CatalogueDataset,
  document: unknown,
  filters: Record<string, string[]>,
  signal: AbortSignal,
): Promise<number | null> {
  const operationId = dataset.summary_operation;
  const path = operationId ? pathFor(document, operationId) : null;
  if (!path) return null;
  const accepted = new Set(
    (operationFor(document, operationId as string)?.parameters ?? [])
      .filter((parameter) => parameter.in === "query")
      .map((parameter) => parameter.name),
  );
  if (Object.keys(filters).some((name) => !accepted.has(name))) return null;
  try {
    const summary = await getEnvelope<{ total?: unknown }>(path, filters, signal);
    return typeof summary.data.total === "number" ? summary.data.total : null;
  } catch {
    // A summary that will not answer costs the reader a total, not the grid they asked for.
    return null;
  }
}

export function renderPagination(
  model: Pagination,
  hooks: { onNext(href: string): void },
): HTMLElement {
  const block = document.createElement("div");
  block.className = "gw-page";
  block.append(countLine(model));

  if (model.next) {
    const next = document.createElement("button");
    next.type = "button";
    next.className = "gw-page-next";
    next.textContent = `▸ next ${model.shown}`;
    // The server built this URL; assembling a second one is how a client invents an offset.
    next.addEventListener("click", () => hooks.onNext(model.next as string));
    block.append(next);
  }
  block.append(model.cursored ? cursorBlock(model) : uncursored(model));
  return block;
}

function countLine(model: Pagination): HTMLElement {
  const line = document.createElement("p");
  line.className = "gw-page-count";
  if (model.total !== null) {
    line.textContent = `${model.total.toLocaleString("en-US")} rows matched · showing 1–${model.shown}`;
  } else if (model.next) {
    // An invented total is a naked number wearing a comma (§3.6).
    line.textContent = `showing 1–${model.shown} · more available`;
  } else {
    line.textContent = `showing all ${model.shown}`;
  }
  return line;
}

function cursorBlock(model: Pagination): HTMLElement {
  const block = document.createElement("div");
  block.className = "gw-cursor";
  if (!model.token) {
    const done = document.createElement("p");
    done.className = "gw-cursor-note";
    done.textContent =
      "This collection is cursor-paginated and this is the last page, so the server minted no" +
      " cursor. There is no page number, and no offset parameter exists.";
    block.append(done);
    return block;
  }

  const token = document.createElement("code");
  token.className = "gw-cursor-token";
  token.setAttribute("data-no-glossary", "");
  token.textContent = model.token;

  const decoded = document.createElement("div");
  decoded.className = "gw-cursor-decoded";
  decoded.hidden = true;
  for (const key of CURSOR_KEYS) {
    const row = document.createElement("p");
    row.className = "gw-cursor-row";
    row.dataset["cursorKey"] = key;
    const name = document.createElement("code");
    name.setAttribute("data-no-glossary", "");
    name.textContent = `"${key}": ${JSON.stringify(model.decoded?.[key] ?? null)}`;
    const gloss = document.createElement("span");
    gloss.className = "gw-cursor-gloss";
    gloss.textContent = `← ${TEACHING[key]}`;
    row.append(name, gloss);
    decoded.append(row);
  }
  const lesson = document.createElement("p");
  lesson.className = "gw-cursor-lesson";
  lesson.textContent =
    "There is no page number, and no offset parameter exists. The cursor is not signed: it" +
    " carries no authorisation, it is a WHERE clause you could have written yourself.";
  decoded.append(lesson);

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "gw-cursor-toggle";
  toggle.textContent = "decode ▾";
  toggle.addEventListener("click", () => {
    decoded.hidden = !decoded.hidden;
    toggle.textContent = decoded.hidden ? "decode ▾" : "decode ▴";
  });

  block.append(labelled("cursor", token), toggle, decoded);
  return block;
}

/** m10: an operation with no cursor gets the stated fallback, not a disabled cursor UI. */
function uncursored(model: Pagination): HTMLElement {
  const note = document.createElement("p");
  note.className = "gw-page-uncursored";
  note.textContent =
    model.limitCap === null
      ? "This collection is not cursor-paginated — it answers in one page."
      : `This collection is not cursor-paginated — limit is the whole control, and the server` +
        ` caps it at ${model.limitCap}.`;
  return note;
}

function labelled(text: string, value: HTMLElement): HTMLElement {
  const wrapper = document.createElement("p");
  wrapper.className = "gw-cursor-line";
  const label = document.createElement("span");
  label.className = "gw-cursor-label";
  label.textContent = text;
  wrapper.append(label, value);
  return wrapper;
}
