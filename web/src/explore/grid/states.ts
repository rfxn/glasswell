import { ApiError } from "../../api/client.ts";
import type { AppState } from "../../app/state.ts";
import { filtersOf, withFilter } from "../router.ts";

/** The three answers that are not a grid, each stated rather than left as an empty rectangle. */

export interface AnchorOptions {
  state: AppState;
  commit(next: Partial<AppState>): void;
  signal: AbortSignal;
}

/** K5: a dataset behind a path parameter announces the anchor instead of 404-ing. */
export function anchorPrompt(missing: readonly string[], options: AnchorOptions): HTMLElement {
  const wrapper = document.createElement("div");
  wrapper.className = "gw-grid-anchor";
  wrapper.append(
    note(
      `This collection is read one ${missing.join(" and ")} at a time. Supply one and the grid renders that ${missing.join("/")}'s rows; until then there is nothing to list, and asking anyway would only produce a 404.`,
      "gw-explore-note",
    ),
  );
  for (const name of missing) {
    const form = document.createElement("form");
    form.className = "gw-grid-anchor-form";
    const input = document.createElement("input");
    input.className = "gw-facet-input";
    input.name = name;
    input.placeholder = name;
    input.value = filtersOf(options.state)[name]?.[0] ?? "";
    const go = document.createElement("button");
    go.type = "submit";
    go.className = "gw-grid-anchor-go";
    go.textContent = `list this ${name}`;
    form.addEventListener(
      "submit",
      (event) => {
        event.preventDefault();
        if (input.value === "") return;
        options.commit({ extra: withFilter(options.state, name, [input.value]).extra });
      },
      { signal: options.signal },
    );
    form.append(input, go);
    wrapper.append(form);
  }
  return wrapper;
}

export function emptyState(state: AppState): HTMLElement {
  const asOf = state.extra["as_of"]?.[0];
  return note(
    `This operation answered with no rows${asOf ? ` at as_of ${asOf}` : ""}. That is an answer, not a failure: the collection exists, the filters resolved, and nothing matched them.`,
    "gw-explore-note",
  );
}

export function failure(error: unknown): HTMLElement {
  const problem = error instanceof ApiError ? error.problem : null;
  return note(
    problem
      ? `${problem.title} (${problem.status}): ${problem.detail ?? "the API refused this request"}. The API guide pane renders the problem in full when it lands.`
      : `This request did not complete: ${String(error)}`,
    "gw-grid-error",
  );
}

export function note(text: string, className: string): HTMLElement {
  const element = document.createElement("p");
  element.className = className;
  element.textContent = text;
  return element;
}
