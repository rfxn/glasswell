/**
 * The thematic key, split from thematics.ts because it is DOM: the expressions and frame
 * readers stay importable by node-environment style tests, and only the map shell pays for
 * the custom-element registry this file's explain handle raises events into.
 */
import "./thematics.css";

import { EXPLAIN_EVENT } from "../card/gw-figure.ts";
import {
  LIQUID_RAMP,
  LIQUIDS_BASIS_COPY,
  MEMBERSHIP_COPY,
  MEMBERSHIP_RULE,
  compactVolume,
  frameOf,
} from "./thematics.ts";

const NUMBER = new Intl.NumberFormat("en-US");

export interface ThematicsKeyHandle {
  element: HTMLElement;
  /** The rendered cells' properties; empty (or an off row) hides the key. */
  set(cells: readonly Record<string, unknown>[]): void;
  clear(): void;
}

/**
 * The key states the metric, the unit, the population and the frozen edges — the edges are
 * never silently re-computed. Every figure resolves: the handle button raises the same
 * explain event the status legend's counts do.
 */
export function createThematicsKey(): ThematicsKeyHandle {
  const element = document.createElement("div");
  element.className = "gw-thm";
  element.hidden = true;

  const title = document.createElement("p");
  title.className = "gw-thm-title";
  title.textContent = `Cumulative liquid · ${LIQUIDS_BASIS_COPY}`;
  element.appendChild(title);

  const scope = document.createElement("p");
  scope.className = "gw-thm-scope";
  element.appendChild(scope);

  const ramp = document.createElement("div");
  ramp.className = "gw-thm-ramp";
  for (const colour of LIQUID_RAMP) {
    const bin = document.createElement("span");
    bin.className = "gw-thm-bin";
    bin.style.background = colour;
    ramp.appendChild(bin);
  }
  element.appendChild(ramp);

  const edges = document.createElement("p");
  edges.className = "gw-thm-edges";
  element.appendChild(edges);

  const support = document.createElement("p");
  support.className = "gw-thm-note";
  support.textContent =
    "Pale = 1–2 producing wells behind the cell, mid = 3–7, full = 8+." +
    " Unpainted = nothing observed. Observed sums only — never interpolated.";
  element.appendChild(support);

  const membership = document.createElement("p");
  membership.className = "gw-thm-note";
  membership.textContent = `Membership: ${MEMBERSHIP_COPY} — ${MEMBERSHIP_RULE}.`;
  element.appendChild(membership);

  const handle = document.createElement("button");
  handle.type = "button";
  handle.className = "gw-handle gw-thm-handle";
  handle.textContent = "⌾";
  handle.hidden = true;
  handle.addEventListener("click", () => {
    const derivation = handle.dataset["handle"];
    if (derivation) {
      handle.dispatchEvent(
        new CustomEvent(EXPLAIN_EVENT, { detail: { handle: derivation }, bubbles: true }),
      );
    }
  });
  element.appendChild(handle);

  return {
    element,
    set(cells) {
      const frame = frameOf(cells);
      if (!frame) {
        element.hidden = true;
        return;
      }
      scope.textContent =
        `Per PLSS ${frame.grain} · bins cut over ${NUMBER.format(frame.population)} ` +
        `${frame.grain}s with observed liquid, frozen at refresh`;
      edges.textContent = frame.edges.map((edge) => compactVolume(edge)).join(" · ") + " bbl";
      handle.hidden = frame.handle === null;
      handle.dataset["handle"] = frame.handle ?? "";
      handle.setAttribute(
        "aria-label",
        frame.handle ? `Show where these bin edges came from: ${frame.handle}` : "",
      );
      element.hidden = false;
    },
    clear() {
      element.hidden = true;
    },
  };
}
