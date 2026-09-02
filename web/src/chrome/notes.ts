/**
 * Scope and disclosure, as chrome rather than paragraphs. The obligations R6 puts on a served
 * figure — the window it was judged over, the cut a list is, the derivations behind a column —
 * were being met with sentences, and a panel of sentences is not readable at a glance. They
 * are met here with a dense summary line and a `<details>` holding the full wording, so the
 * statement still travels with the number and stops costing four lines to say so.
 */

export const NOTE_SEPARATOR = " · ";

/**
 * A token that may not be broken across lines. A date is the case this exists for: wrapped at
 * its own hyphen it reads as a truncated year at the end of a line ("snapshot 2026-" / "08-23").
 */
export function unbreakable(text: string): HTMLSpanElement {
  const span = document.createElement("span");
  span.className = "gw-nowrap";
  span.textContent = text;
  return span;
}

/**
 * A `·`-joined line of short facts. Empty parts drop, so callers can pass conditionals, and a
 * part may be a node so one token can refuse to wrap without the line refusing to.
 * `textContent` reads exactly as it did when this joined strings.
 */
export function scopeLine(
  parts: (string | Node | null | undefined | false)[],
): HTMLParagraphElement {
  const element = document.createElement("p");
  element.className = "gw-scope";
  element.setAttribute("data-no-glossary", "");
  const kept = parts.filter((part): part is string | Node => Boolean(part));
  kept.forEach((part, index) => {
    if (index > 0) element.appendChild(document.createTextNode(NOTE_SEPARATOR));
    element.append(part);
  });
  return element;
}

/**
 * A summary that reads on its own and a body that only opens when asked. `detail` is the
 * wording being demoted, never dropped: the disclosure is where a reader who needs the full
 * statement finds it unchanged.
 */
export function disclosure(summary: string, detail: string | Node, tone?: "warning"): HTMLElement {
  const element = document.createElement("details");
  element.className = tone === "warning" ? "gw-note gw-note-warning" : "gw-note";
  const head = document.createElement("summary");
  head.className = "gw-note-summary";
  head.textContent = summary;
  const body = document.createElement("div");
  body.className = "gw-note-detail";
  body.append(detail);
  element.append(head, body);
  return element;
}

/**
 * `geometry_not_promoted` reads as "Geometry not promoted". Mechanical on purpose: the API
 * owns the code vocabulary and adds to it, and a hand-written title per code goes stale the
 * first time it does. TITLES carries only the codes whose mechanical form misreads.
 */
const TITLES: Record<string, string> = {
  bbox_cap: "Bounding box capped",
  list_truncated: "Ranked cut, not the population",
  series_spans_derivations: "Column spans derivations",
  aggregate_spans_derivations: "Aggregate spans derivations",
  months_withheld: "Months withheld",
  explain_inline_truncated: "Explain truncated inline",
  explain_link_truncated: "Explain truncated",
  search_scopes_the_ranking: "Search scopes the ranking",
  production_pending_allocation: "Production pending allocation",
  current_only_geometry: "Current geometry only",
  below_tile_resolution: "Below tile resolution",
};

export function warningTitle(code: string): string {
  const known = TITLES[code];
  if (known) return known;
  const words = code.replace(/_/g, " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : code;
}

export interface NoteWarning {
  code: string;
  detail?: string;
  pointer?: string;
}

/**
 * One `<details>` per code, with the count in the summary and the server's own wording inside.
 * The card used to print `code: detail (pointers)` verbatim, which put a 199-character
 * internal line above the polished panel saying the same thing.
 *
 * Grouped by code and then by detail, because a repeated code does not imply a repeated
 * sentence: `series_spans_derivations` counts derivations *per column*
 * (`api/routers/production.py`), so one well can carry "7 derivations" against oil and a
 * different number against gas. Collapsing to the first would drop a served figure while
 * still listing every pointer, which reads as one claim covering all of them.
 */
export function warningNotes(warnings: readonly NoteWarning[]): HTMLElement[] {
  const grouped = new Map<string, NoteWarning[]>();
  for (const warning of warnings) {
    grouped.set(warning.code, [...(grouped.get(warning.code) ?? []), warning]);
  }
  return [...grouped.entries()].map(([code, group]) => {
    const summary = warningTitle(code) + (group.length > 1 ? ` ×${group.length}` : "");
    const body = document.createElement("div");
    for (const [text, pointers] of byDetail(group)) {
      const detail = document.createElement("p");
      detail.className = "gw-note-line";
      detail.textContent = text;
      const source = document.createElement("p");
      source.className = "gw-note-source";
      source.setAttribute("data-no-glossary", "");
      source.textContent = pointers.length
        ? `${code}${NOTE_SEPARATOR}${pointers.join(", ")}`
        : code;
      body.append(detail, source);
    }
    const element = disclosure(summary, body, "warning");
    element.dataset["code"] = code;
    return element;
  });
}

/** The distinct wordings a code arrived with, each against the pointers that carried it. */
function byDetail(group: readonly NoteWarning[]): Map<string, string[]> {
  const details = new Map<string, string[]>();
  for (const warning of group) {
    const text = warning.detail ?? "";
    const pointers = details.get(text) ?? [];
    if (warning.pointer) pointers.push(warning.pointer);
    details.set(text, pointers);
  }
  return details;
}

/** An empty slot states what is absent in the fewest words that stay true. */
export function emptyState(text: string): HTMLElement {
  const element = document.createElement("p");
  element.className = "gw-empty";
  element.textContent = text;
  return element;
}
