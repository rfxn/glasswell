/**
 * Scope and disclosure, as chrome rather than paragraphs. The obligations R6 puts on a served
 * figure — the window it was judged over, the cut a list is, the derivations behind a column —
 * were being met with sentences, and a panel of sentences is not readable at a glance. They
 * are met here with a dense summary line and a `<details>` holding the full wording, so the
 * statement still travels with the number and stops costing four lines to say so.
 */

export const NOTE_SEPARATOR = " · ";

/** A `·`-joined line of short facts. Empty parts drop, so callers can pass conditionals. */
export function scopeLine(parts: (string | null | undefined | false)[]): HTMLParagraphElement {
  const element = document.createElement("p");
  element.className = "gw-scope";
  element.setAttribute("data-no-glossary", "");
  element.textContent = parts.filter((part): part is string => Boolean(part)).join(NOTE_SEPARATOR);
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
 * One `<details>` per code, with the count in the summary and the server's own detail inside.
 * The card used to print `code: detail (pointers)` verbatim, which put a 199-character
 * internal line above the polished panel saying the same thing.
 */
export function warningNotes(warnings: readonly NoteWarning[]): HTMLElement[] {
  const grouped = new Map<string, NoteWarning[]>();
  for (const warning of warnings) {
    grouped.set(warning.code, [...(grouped.get(warning.code) ?? []), warning]);
  }
  return [...grouped.entries()].map(([code, group]) => {
    const pointers = group
      .map((warning) => warning.pointer)
      .filter((pointer): pointer is string => Boolean(pointer));
    const summary = warningTitle(code) + (group.length > 1 ? ` ×${group.length}` : "");
    const body = document.createElement("div");
    const detail = document.createElement("p");
    detail.className = "gw-note-line";
    detail.textContent = group[0]?.detail ?? "";
    body.appendChild(detail);
    const source = document.createElement("p");
    source.className = "gw-note-source";
    source.setAttribute("data-no-glossary", "");
    source.textContent = pointers.length ? `${code}${NOTE_SEPARATOR}${pointers.join(", ")}` : code;
    body.appendChild(source);
    const element = disclosure(summary, body, "warning");
    element.dataset["code"] = code;
    return element;
  });
}

/** An empty slot states what is absent in the fewest words that stay true. */
export function emptyState(text: string): HTMLElement {
  const element = document.createElement("p");
  element.className = "gw-empty";
  element.textContent = text;
  return element;
}
