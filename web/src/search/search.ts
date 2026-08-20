import { getEnvelope } from "../api/client.ts";
import { searchRequest, toResults } from "./query.ts";
import type { SearchResult } from "./query.ts";

export interface SearchCallbacks {
  onPick(result: SearchResult): void;
  onError(error: unknown): void;
}

const DEBOUNCE_MS = 250;
const OPTION_ID = "gw-search-option-";

/** The API has answered `q` since day one; this is the input that was never built (UX P1-2). */
export function createSearch(callbacks: SearchCallbacks): HTMLElement {
  const host = document.createElement("div");
  host.className = "gw-search";

  const input = document.createElement("input");
  input.type = "search";
  input.id = "gw-search-input";
  input.className = "gw-search-input";
  input.placeholder = "Find a well by name or API-10";
  input.setAttribute("aria-label", "Find a well by name or API-10");
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-controls", "gw-search-results");
  input.setAttribute("aria-autocomplete", "list");
  input.autocomplete = "off";

  const panel = document.createElement("div");
  panel.className = "gw-search-panel";
  panel.hidden = true;

  const list = document.createElement("ul");
  list.id = "gw-search-results";
  list.className = "gw-search-results";
  list.setAttribute("role", "listbox");
  list.setAttribute("aria-label", "Well search results");

  const note = document.createElement("p");
  note.className = "gw-search-note";
  note.setAttribute("role", "status");
  note.hidden = true;

  panel.append(list, note);
  host.append(input, panel);

  let results: SearchResult[] = [];
  let active = -1;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let inFlight: AbortController | null = null;

  function close(): void {
    results = [];
    active = -1;
    list.replaceChildren();
    note.hidden = true;
    panel.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }

  function highlight(index: number): void {
    active = index;
    for (const [position, option] of [...list.children].entries()) {
      option.classList.toggle("is-active", position === active);
      option.setAttribute("aria-selected", String(position === active));
    }
    if (active >= 0) input.setAttribute("aria-activedescendant", `${OPTION_ID}${active}`);
    else input.removeAttribute("aria-activedescendant");
  }

  function pick(index: number): void {
    const result = results[index];
    if (!result) return;
    input.value = result.name;
    close();
    callbacks.onPick(result);
  }

  function render(found: SearchResult[], term: string): void {
    results = found;
    active = -1;
    list.replaceChildren();
    for (const [index, result] of found.entries()) {
      list.appendChild(option(result, index, () => pick(index)));
    }
    note.hidden = found.length > 0;
    note.textContent = `No well matches “${term}” at this vintage.`;
    panel.hidden = false;
    input.setAttribute("aria-expanded", "true");
    highlight(-1);
  }

  async function run(term: string): Promise<void> {
    const request = searchRequest(term);
    if (!request) {
      close();
      return;
    }
    inFlight?.abort();
    const controller = new AbortController();
    inFlight = controller;
    try {
      const envelope = await getEnvelope<unknown>(request.path, request.query, controller.signal);
      if (controller.signal.aborted) return;
      render(toResults(envelope), term.trim());
    } catch (error) {
      if (controller.signal.aborted) return;
      close();
      callbacks.onError(error);
    }
  }

  input.addEventListener("input", () => {
    if (timer !== null) clearTimeout(timer);
    const term = input.value;
    timer = setTimeout(() => void run(term), DEBOUNCE_MS);
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      close();
      event.preventDefault();
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (results.length === 0) return;
      const step = event.key === "ArrowDown" ? 1 : -1;
      const first = step > 0 ? 0 : results.length - 1;
      highlight(active === -1 ? first : (active + step + results.length) % results.length);
      event.preventDefault();
      return;
    }
    if (event.key === "Enter" && results.length > 0) {
      pick(active >= 0 ? active : 0);
      event.preventDefault();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
    if (isTextEntry(document.activeElement)) return;
    input.focus();
    input.select();
    event.preventDefault();
  });

  return host;
}

function option(result: SearchResult, index: number, onPick: () => void): HTMLElement {
  const item = document.createElement("li");
  item.id = `${OPTION_ID}${index}`;
  item.className = "gw-search-option";
  item.setAttribute("role", "option");
  item.setAttribute("aria-selected", "false");
  item.setAttribute("data-no-glossary", "");

  const name = document.createElement("span");
  name.className = "gw-search-name";
  name.textContent = result.name;

  const api10 = document.createElement("span");
  api10.className = "gw-search-api";
  api10.textContent = result.api10;

  const operator = document.createElement("span");
  operator.className = "gw-search-operator";
  operator.textContent = [result.operator, result.status].filter(Boolean).join(" · ");

  item.append(name, api10, operator);
  // mousedown, not click: a blur-driven close would remove the row before click lands.
  item.addEventListener("mousedown", (event) => {
    event.preventDefault();
    onPick();
  });
  return item;
}

function isTextEntry(element: Element | null): boolean {
  if (!(element instanceof HTMLElement)) return false;
  return (
    element instanceof HTMLInputElement ||
    element instanceof HTMLTextAreaElement ||
    element instanceof HTMLSelectElement ||
    element.isContentEditable
  );
}
