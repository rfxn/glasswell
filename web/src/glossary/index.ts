export interface IndexEntry {
  surface: string;
  term_id: string;
  n_words: number;
}

export interface GlossaryIndexPayload {
  index_version: string;
  entries: IndexEntry[];
  stopwords: string[];
}

export interface TermIndex {
  version: string;
  surfaces: string[];
  pattern: RegExp | null;
  termIdFor(surface: string): string | null;
}

export type Segment = { text: string; termId?: string };

// A term inside these never gets an underline: two affordances on one word, or a value
// masquerading as vocabulary (SB-05 §5.3).
const SKIP_ELEMENTS = new Set(["A", "CODE", "PRE", "SCRIPT", "STYLE", "GW-TERM", "GW-FIGURE"]);
// A match touching one of these is inside a path, a handle or an id, not prose.
const IDENTIFIER_NEIGHBOUR = /[\w/#]/;

export function buildIndex(payload: GlossaryIndexPayload): TermIndex {
  const stopwords = new Set(payload.stopwords.map((word) => word.toLowerCase()));
  const bySurface = new Map<string, string>();
  for (const entry of payload.entries) {
    bySurface.set(entry.surface.toLowerCase(), entry.term_id);
  }

  const words = new Map(payload.entries.map((entry) => [entry.surface.toLowerCase(), entry.n_words]));
  const surfaces = payload.entries
    .map((entry) => entry.surface.toLowerCase())
    .filter((surface) => !stopwords.has(surface))
    .sort(
      (left, right) =>
        (words.get(right) ?? 1) - (words.get(left) ?? 1) ||
        right.length - left.length ||
        left.localeCompare(right),
    );

  const pattern = surfaces.length
    ? new RegExp(`\\b(?:${surfaces.map(escapeRegExp).join("|")})\\b`, "gi")
    : null;

  return {
    version: payload.index_version,
    surfaces,
    pattern,
    termIdFor: (surface: string) => bySurface.get(surface.toLowerCase()) ?? null,
  };
}

/** Returns segments, never DOM — the invariant that keeps highlighting out of render cycles. */
export function scan(text: string, index: TermIndex): Segment[] {
  if (!index.pattern || text === "") return [{ text }];
  const pattern = new RegExp(index.pattern.source, index.pattern.flags);
  const segments: Segment[] = [];
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    const matched = match[0];
    if (isInsideIdentifier(text, start, matched.length)) continue;
    const termId = index.termIdFor(matched);
    if (!termId) continue;
    if (start > cursor) segments.push({ text: text.slice(cursor, start) });
    segments.push({ text: matched, termId });
    cursor = start + matched.length;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor) });
  return segments.length ? segments : [{ text }];
}

function isInsideIdentifier(text: string, start: number, length: number): boolean {
  const before = text.slice(Math.max(0, start - 1), start);
  const after = text.slice(start + length, start + length + 1);
  return IDENTIFIER_NEIGHBOUR.test(before) || IDENTIFIER_NEIGHBOUR.test(after);
}

/** Rewrites text nodes under `root` into `<gw-term>` wrappers; safe to run repeatedly. */
export function highlight(root: ParentNode, index: TermIndex): void {
  if (!index.pattern) return;
  const document_ = (root as Element).ownerDocument ?? (root as Document);
  const walker = document_.createTreeWalker(root as Node, 4 /* NodeFilter.SHOW_TEXT */);
  const pending: Text[] = [];
  let node = walker.nextNode();
  while (node) {
    const text = node as Text;
    if (text.data.trim() !== "" && !isSkipped(text)) pending.push(text);
    node = walker.nextNode();
  }
  for (const text of pending) {
    const segments = scan(text.data, index);
    if (!segments.some((segment) => segment.termId)) continue;
    const fragment = document_.createDocumentFragment();
    for (const segment of segments) {
      if (segment.termId) {
        const term = document_.createElement("gw-term");
        term.setAttribute("term-id", segment.termId);
        term.setAttribute("tabindex", "0");
        term.setAttribute("role", "button");
        term.textContent = segment.text;
        fragment.appendChild(term);
      } else {
        fragment.appendChild(document_.createTextNode(segment.text));
      }
    }
    text.parentNode?.replaceChild(fragment, text);
  }
}

function isSkipped(text: Text): boolean {
  let element = text.parentElement;
  while (element) {
    if (SKIP_ELEMENTS.has(element.tagName)) return true;
    if (element.hasAttribute("data-no-glossary")) return true;
    element = element.parentElement;
  }
  return false;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
