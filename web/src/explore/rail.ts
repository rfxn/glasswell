import type { Catalogue, DatasetGroup } from "./catalogue.ts";

export const GROUP_TITLES: Record<DatasetGroup, string> = {
  wells: "Wells & production",
  kitchen: "The kitchen",
  vocabulary: "Vocabulary",
  service: "Service",
};

export interface GapEntry {
  title: string;
  /** The operation it will be, quoted from SB-04 §4 — never an operationId invented here. */
  path: string;
  section: string;
  phase: string | null;
}

/**
 * SB-08 §2.4 class B: specified in SB-04 §4, not built. One exported const so the rail, the
 * changelog and the register cannot disagree. Every path is asserted absent from the served
 * document, which is what makes the entry honest rather than decorative — the day one starts
 * resolving, `rail.test.ts` reddens and it moves into the generated rail where it belongs.
 */
export const CLASS_B_DATASETS: readonly GapEntry[] = [
  { title: "Completions", path: "/v1/wells/{api10}/completions", section: "SB-04 §4.2", phase: null },
  { title: "Forecasts", path: "/v1/wells/{api10}/forecast", section: "SB-04 §4.2", phase: "P3" },
  { title: "Models", path: "/v1/models", section: "SB-04 §4.3", phase: "P3" },
  { title: "Benchmarks", path: "/v1/benchmarks", section: "SB-04 §4.3", phase: null },
  { title: "Analogs", path: "/v1/analogs", section: "SB-04 §4.3", phase: null },
  { title: "Operators", path: "/v1/operators", section: "SB-04 §4.6", phase: "P5" },
  { title: "League", path: "/v1/operators/league", section: "SB-04 §4.6", phase: null },
  { title: "Permits", path: "/v1/permits", section: "SB-04 §4.6", phase: null },
  { title: "Activity / DUC", path: "/v1/activity/duc", section: "SB-04 §4.6", phase: null },
  { title: "Land units", path: "/v1/landunits", section: "SB-04 §4.7", phase: null },
  { title: "Formations", path: "/v1/formations", section: "SB-04 §4.7", phase: null },
  { title: "Spacing units", path: "/v1/spacingunits", section: "SB-04 §4.7", phase: null },
  { title: "CRS", path: "/v1/crs", section: "SB-04 §4.7", phase: null },
  { title: "Scorecard", path: "/v1/scorecard", section: "SB-04 §4.10", phase: "P6" },
  { title: "Ledger", path: "/v1/ledger", section: "SB-04 §4.10", phase: null },
  { title: "Audit", path: "/v1/audit", section: "SB-04 §4.9", phase: null },
  { title: "Recipes", path: "/v1/recipes/{recipe_id}", section: "SB-04 §4.9", phase: null },
  { title: "Jobs", path: "/v1/jobs", section: "SB-04 §4.12", phase: null },
  { title: "Exports", path: "/v1/exports/{export_id}", section: "SB-04 §4.12", phase: null },
  { title: "Notebook", path: "/v1/notebook", section: "SB-04 §4.12", phase: null },
  { title: "Inventory", path: "/v1/inventory/runs", section: "SB-04 §4.5", phase: null },
];

export interface ProposedEntry extends GapEntry {
  amendment: string;
  status: string;
}

/** Class C: needs a contract delta. Exactly one dataset in the owner's list falls here. */
export const CLASS_C_DATASETS: readonly ProposedEntry[] = [
  {
    title: "Production across wells",
    path: "/v1/production",
    section: "SB-08 §7.1",
    phase: null,
    amendment: "A-3",
    status: "proposed — Track A1b/D0 owns it; it gates the cross-well grid at P-B",
  },
];

export interface RailOptions {
  catalogue: Catalogue | null;
  selected: string | null;
  onSelect(id: string): void;
  signal?: AbortSignal;
}

export function renderRail(host: HTMLElement, options: RailOptions): void {
  const parts: Node[] = [eyebrow("Datasets")];

  if (!options.catalogue) {
    const degraded = document.createElement("p");
    degraded.className = "gw-explore-rail-degraded";
    degraded.textContent =
      "The catalogue could not be read from /openapi.json, so no dataset is listed. Nothing is missing from the API — this surface simply cannot see it right now.";
    parts.push(degraded);
  } else {
    for (const group of options.catalogue.groups) {
      parts.push(datasetGroup(group.id, group.datasets, options));
    }
  }

  parts.push(gaps());
  host.replaceChildren(...parts);
}

function eyebrow(text: string): HTMLElement {
  const element = document.createElement("p");
  element.className = "gw-explore-rail-eyebrow";
  element.textContent = text;
  return element;
}

function datasetGroup(
  group: DatasetGroup,
  datasets: Catalogue["datasets"],
  options: RailOptions,
): HTMLElement {
  const section = document.createElement("section");
  section.className = "gw-explore-rail-group";
  section.dataset["group"] = group;

  const heading = document.createElement("h3");
  heading.textContent = GROUP_TITLES[group];
  section.appendChild(heading);

  const list = document.createElement("ul");
  for (const dataset of datasets) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "gw-explore-ds";
    button.dataset["ds"] = dataset.id;
    if (dataset.id === options.selected) button.setAttribute("aria-current", "page");
    button.append(label(dataset.title));
    button.addEventListener("click", () => options.onSelect(dataset.id), { signal: options.signal });
    item.appendChild(button);
    list.appendChild(item);
  }
  section.appendChild(list);
  return section;
}

function label(text: string): HTMLElement {
  const element = document.createElement("span");
  element.className = "gw-explore-rail-label";
  element.textContent = text;
  return element;
}

function gaps(): HTMLElement {
  const section = document.createElement("section");
  section.className = "gw-explore-rail-gaps";

  const heading = document.createElement("h3");
  heading.textContent = "Not yet built";
  section.appendChild(heading);

  const note = document.createElement("p");
  note.className = "gw-explore-rail-note";
  note.textContent = "Specified in SB-04 §4, not served. Each names the operation that would carry it.";
  section.appendChild(note);

  const list = document.createElement("ul");
  for (const entry of CLASS_B_DATASETS) list.appendChild(gapEntry(entry, "class-b"));
  for (const entry of CLASS_C_DATASETS) {
    const item = gapEntry(entry, "class-c");
    item.appendChild(chip(`${entry.amendment} · ${entry.status}`, "gw-explore-gap-amendment"));
    list.appendChild(item);
  }
  section.appendChild(list);
  return section;
}

/** No control, no link, no count: §6.5 forbids implying content that does not exist. */
function gapEntry(entry: GapEntry, kind: string): HTMLElement {
  const item = document.createElement("li");
  item.className = "gw-explore-gap";
  item.dataset["gap"] = kind;
  item.setAttribute("aria-disabled", "true");
  item.title = `${entry.section} — specified, not served`;

  const title = document.createElement("span");
  title.className = "gw-explore-gap-title";
  title.textContent = entry.title;
  item.appendChild(title);

  const operation = document.createElement("code");
  operation.className = "gw-explore-gap-op";
  operation.textContent = entry.path;
  item.appendChild(operation);

  if (entry.phase) item.appendChild(chip(entry.phase, "gw-explore-gap-phase"));
  return item;
}

function chip(text: string, className: string): HTMLElement {
  const element = document.createElement("span");
  element.className = `gw-chip ${className}`;
  element.textContent = text;
  return element;
}
