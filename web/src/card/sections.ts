/**
 * The card's ten sections: one fixed order, three expanded by default, an ARIA accordion
 * keyboard, a bounded request queue, and the `?section=` deep link.
 *
 * Nothing outside the card knows what a section is. `main.ts` says only which id the URL
 * names, over the document, and this module decides whether that id exists for this well.
 * The list is knowable here and nowhere else: which sections a well has depends on the links
 * its own response carried.
 */
import { focusPanel } from "../chrome/overlays.ts";

/** main.ts -> here, on popstate. Kept as a literal at both ends so no import edge is made. */
export const SECTION_EVENT = "gw-section";
/** here -> main.ts, which is the single writer of app state. */
export const SECTION_SET_EVENT = "gw-section-set";

export interface SectionSpec {
  id: string;
  title: string;
  /** Expanded because its content is why a reader opens a well, not why they open this one. */
  expanded: boolean;
  /** Absent for an eager body. Called at most once, through the queue below. */
  load?: () => Promise<void>;
  /** False where this well has no such section. It stays in the list so a link that named it
   *  can be answered with the section's own name and rule rather than with silence. */
  present?: boolean;
  /** Where a section is absent for this well, the rule path that decided it, when served. */
  absentRule?: string;
}

export interface SectionHandles {
  section: HTMLElement;
  toggle: HTMLButtonElement;
  title: HTMLElement;
  aside: HTMLElement;
  body: HTMLElement;
}

// A rail is a surface a reader leaves open while panning, and ten sections over seven
// endpoints is a stall waiting to happen on a phone connection. Two in flight, the rest in
// expansion order, and a section that has loaded is never asked again.
const IN_FLIGHT_CAP = 2;

// Keyed by api10 and never in the URL: ten booleans on every link is a worse URL than one
// section name. It survives a re-render the well response can still legitimately trigger --
// a vintage change, a retry -- so the reader's own disclosures come back rather than reset.
const expandedByWell = new Map<string, Set<string>>();

let currentWell = "";
let mounted: Map<string, SectionHandles> = new Map();
let specs: SectionSpec[] = [];
const loaded = new Set<string>();
const queue: string[] = [];
const running: Promise<void>[] = [];
let inFlight = 0;
let listening = false;

/** Test seam: the queue and the collapse memory are module state by design. */
export function resetSections(): void {
  expandedByWell.clear();
  currentWell = "";
  mounted = new Map();
  specs = [];
  loaded.clear();
  queue.length = 0;
  running.length = 0;
  inFlight = 0;
}

export function sectionIds(): string[] {
  return [...mounted.keys()];
}

/** Resolves once the queue has drained, so a caller can await the sections it expanded. */
export async function sectionsSettled(): Promise<void> {
  while (running.length > 0) await Promise.all(running.splice(0));
}

/** How many section requests are in flight, for the fetch-spy assertion R-19 asks for. */
export function sectionsInFlight(): number {
  return inFlight;
}

function expandedSet(api10: string): Set<string> {
  let set = expandedByWell.get(api10);
  if (!set) {
    set = new Set(
      specs.filter((spec) => spec.expanded && spec.present !== false).map((spec) => spec.id),
    );
    expandedByWell.set(api10, set);
  }
  return set;
}

function pump(): void {
  while (inFlight < IN_FLIGHT_CAP && queue.length > 0) {
    const id = queue.shift() as string;
    const spec = specs.find((candidate) => candidate.id === id);
    if (!spec?.load || loaded.has(id)) continue;
    loaded.add(id);
    inFlight += 1;
    const job = spec.load().finally(() => {
      inFlight -= 1;
      pump();
    });
    running.push(job);
    void job;
  }
}

function request(id: string): void {
  if (loaded.has(id) || queue.includes(id)) return;
  queue.push(id);
  pump();
}

function setExpanded(id: string, open: boolean): void {
  const handles = mounted.get(id);
  if (!handles) return;
  handles.toggle.setAttribute("aria-expanded", String(open));
  handles.body.hidden = !open;
  const set = expandedSet(currentWell);
  if (open) set.add(id);
  else set.delete(id);
  if (open) request(id);
}

function commitSection(id: string | null, mode: "push" | "replace"): void {
  document.dispatchEvent(new CustomEvent(SECTION_SET_EVENT, { detail: { id, mode } }));
}

function toggles(): HTMLButtonElement[] {
  return [...mounted.values()].map((handles) => handles.toggle);
}

function step(from: HTMLButtonElement, delta: number): void {
  const all = toggles();
  const index = all.indexOf(from);
  const next = all[Math.min(all.length - 1, Math.max(0, index + delta))];
  next?.focus();
}

/**
 * Expands the named section, scrolls the rail's body to it and lands focus on its disclosure.
 * An id this well has no section for renders the default set, says so once, and is dropped
 * from the URL, which is the rule app/state.ts states for `view` and `tab`, applied in the one
 * place the served section list is knowable.
 */
export function applySection(id: string | null): void {
  if (!id) return;
  const handles = mounted.get(id);
  if (!handles) {
    absentNote(id);
    commitSection(null, "replace");
    return;
  }
  setExpanded(id, true);
  handles.section.scrollIntoView({ block: "start", behavior: "auto" });
  // focusPanel carries the quiet-focus rule a deep-linked reader needs: focus moves and is
  // announced, and only the ring is held back until the first key. It declines when focus is
  // already somewhere the reader put it, which is the in-card link case, so that one asks.
  focusPanel(handles.section);
  if (!handles.section.contains(document.activeElement)) handles.toggle.focus();
}

function absentNote(id: string): void {
  const host = document.querySelector<HTMLElement>(".gw-section-absent");
  if (!host) return;
  const spec = specs.find((candidate) => candidate.id === id);
  host.replaceChildren();
  const line = document.createElement("p");
  line.className = "gw-note gw-section-absent-note";
  line.textContent = spec
    ? `The ${spec.title} section is not served for this well, so the card opened at its own order.`
    : `This card has no section named "${id}", so it opened at its own order.`;
  if (spec?.absentRule) {
    const rule = document.createElement("a");
    rule.className = "gw-section-absent-rule";
    rule.href = spec.absentRule;
    rule.textContent = "the rule that decided that";
    line.append(" See ", rule, ".");
  }
  host.appendChild(line);
  host.hidden = false;
}

/** An in-card link to another section: a navigation the reader asked for by name, so it pushes. */
export function sectionLink(id: string, text: string): HTMLAnchorElement {
  const link = document.createElement("a");
  link.className = "gw-section-link";
  link.href = `?section=${encodeURIComponent(id)}`;
  link.textContent = text;
  link.addEventListener("click", (event) => {
    event.preventDefault();
    commitSection(id, "push");
    applySection(id);
  });
  return link;
}

export function mountSections(
  host: HTMLElement,
  api10: string,
  list: SectionSpec[],
): Map<string, SectionHandles> {
  // Every mount builds fresh hosts, so what was loaded into the last set of them is not
  // loaded into these. The collapse memory is the one thing that survives, and it survives
  // keyed by api10, which is what makes a re-render the well response triggers -- a vintage
  // change, a retry -- give the reader their own disclosures back rather than the defaults.
  loaded.clear();
  queue.length = 0;
  running.length = 0;
  inFlight = 0;
  currentWell = api10;
  specs = list;
  mounted = new Map();

  const absent = document.createElement("div");
  absent.className = "gw-section-absent";
  absent.hidden = true;
  host.appendChild(absent);

  const open = expandedSet(api10);
  for (const spec of list) {
    if (spec.present === false) continue;
    const section = document.createElement("section");
    section.className = "gw-section";
    section.id = `gw-section-${spec.id}`;
    section.dataset["section"] = spec.id;
    const headingId = `gw-section-head-${spec.id}`;
    const bodyId = `gw-section-body-${spec.id}`;
    section.setAttribute("aria-labelledby", headingId);

    const heading = document.createElement("h3");
    heading.className = "gw-section-head";
    heading.id = headingId;
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "gw-section-toggle";
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-controls", bodyId);
    const title = document.createElement("span");
    title.className = "gw-section-title";
    title.textContent = spec.title;
    toggle.appendChild(title);
    const aside = document.createElement("span");
    aside.className = "gw-section-aside";
    heading.append(toggle, aside);

    const body = document.createElement("div");
    body.className = "gw-section-body";
    body.id = bodyId;

    section.append(heading, body);
    host.appendChild(section);
    mounted.set(spec.id, { section, toggle, title, aside, body });

    toggle.addEventListener("click", () => {
      const next = toggle.getAttribute("aria-expanded") !== "true";
      setExpanded(spec.id, next);
      // Ten disclosures must not make ten history entries, so a toggle replaces. The
      // consequence is deliberate: back from a section the reader opened by hand returns to
      // the previous well, and back from one a link named returns to the section before it.
      commitSection(next ? spec.id : null, "replace");
    });
    toggle.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") step(toggle, 1);
      else if (event.key === "ArrowUp") step(toggle, -1);
      else if (event.key === "Home") toggles()[0]?.focus();
      else if (event.key === "End") {
        const all = toggles();
        all[all.length - 1]?.focus();
      }
      else return;
      event.preventDefault();
    });
  }

  for (const spec of list) if (spec.present !== false) setExpanded(spec.id, open.has(spec.id));

  if (!listening) {
    listening = true;
    document.addEventListener(SECTION_EVENT, (event) => {
      applySection((event as CustomEvent<{ id: string | null }>).detail.id);
    });
  }
  return mounted;
}
