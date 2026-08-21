import { defaultLayerSet, layerDef } from "./registry.ts";

export interface PillStripOptions {
  onRemove(id: string): void;
  onOpen(): void;
}

export interface PillStripHandle {
  element: HTMLElement;
  setOn(on: ReadonlySet<string>): void;
}

/**
 * "What am I looking at", answered without opening anything, and one click to undo it.
 * Silent while the map is in its default state — a strip that always shows the same two
 * pills is chrome, not information.
 */
export function createPillStrip(options: PillStripOptions): PillStripHandle {
  const element = document.createElement("div");
  element.className = "gw-pills";
  element.hidden = true;

  const add = document.createElement("button");
  add.type = "button";
  add.className = "gw-pill gw-pill-add";
  // ASCII `+`, not `＋` (U+FF0B): the fullwidth form is in no declared unicode-range, so it drew
  // from the reader's system font rather than from Inter beside the `✕` it pairs with.
  add.textContent = "+";
  add.setAttribute("aria-label", "Open the layer panel");
  add.addEventListener("click", () => options.onOpen());

  function setOn(on: ReadonlySet<string>): void {
    const defaults = new Set(defaultLayerSet());
    const extras = [...on].filter((id) => !defaults.has(id));
    const missing = [...defaults].filter((id) => !on.has(id));
    element.replaceChildren();
    if (extras.length === 0 && missing.length === 0) {
      element.hidden = true;
      return;
    }
    element.hidden = false;
    for (const id of [...extras, ...missing]) {
      const layer = layerDef(id);
      if (!layer) continue;
      element.appendChild(pill(layer.id, layer.label, on.has(id), options));
    }
    element.appendChild(add);
  }

  setOn(new Set(defaultLayerSet()));
  return { element, setOn };
}

function pill(id: string, label: string, on: boolean, options: PillStripOptions): HTMLElement {
  const node = document.createElement("span");
  node.className = on ? "gw-pill" : "gw-pill gw-pill-off";
  node.dataset["layer"] = id;

  const text = document.createElement("span");
  text.className = "gw-pill-label";
  text.textContent = label;
  node.appendChild(text);

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "gw-pill-x";
  remove.textContent = on ? "✕" : "+";
  remove.setAttribute("aria-label", `${on ? "Hide" : "Show"} ${label}`);
  remove.addEventListener("click", () => options.onRemove(id));
  node.appendChild(remove);
  return node;
}
