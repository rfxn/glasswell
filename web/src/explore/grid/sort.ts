/**
 * The declared sort, turned round. The server takes no sort parameter, so this reverses the
 * order it already served rather than re-sorting values the client would have to parse — and it
 * is offered only where every row of the filtered population is loaded, because a descending
 * page one whose `next` walks the ascending order would be a claim the collection does not make.
 */
import type { Envelope } from "../../api/envelope.ts";
import type { AppState } from "../../app/state.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import type { Row } from "./rows.ts";

export type SortDirection = "asc" | "desc";

/** Not `f.`-prefixed: it narrows nothing and never reaches the wire (`requestFor`). */
export const SORT_KEY = "sort";

export function sortColumnOf(
  dataset: CatalogueDataset,
  envelope: Envelope<unknown>,
): string | null {
  const declared = dataset.columns.sort;
  if (declared === undefined || declared === "") return null;
  return envelope.links?.["next"] ? null : declared;
}

export function directionOf(state: AppState): SortDirection {
  return state.extra[SORT_KEY]?.[0] === "desc" ? "desc" : "asc";
}

export function ordered(rows: Row[], direction: SortDirection): Row[] {
  return direction === "desc" ? [...rows].reverse() : rows;
}

export function renderSort(
  pointer: string,
  name: string,
  direction: SortDirection,
  onDirection: (direction: SortDirection) => void,
): HTMLElement {
  const wrapper = document.createElement("div");
  wrapper.className = "gw-grid-sort";
  const label = document.createElement("span");
  label.className = "gw-grid-sort-label";
  label.textContent = `sorted by ${name}`;
  label.title = `The collection declares ${pointer} as its order; every row of it is loaded here.`;
  wrapper.appendChild(label);

  const group = document.createElement("div");
  group.className = "gw-grid-sort-group";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", `The order of ${name}`);
  const choices: [SortDirection, string][] = [
    ["asc", "oldest first"],
    ["desc", "newest first"],
  ];
  for (const [value, text] of choices) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "gw-grid-sort-dir";
    button.setAttribute("aria-pressed", String(value === direction));
    button.textContent = text;
    button.addEventListener("click", () => onDirection(value));
    group.appendChild(button);
  }
  wrapper.appendChild(group);
  return wrapper;
}
