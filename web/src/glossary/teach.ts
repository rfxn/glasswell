import { highlight } from "./index.ts";
import { onGlossaryReady, termIndex } from "./store.ts";

export interface Teaching {
  /** Re-runs the highlighter, for a surface that rebuilds its own rows. Safe to repeat. */
  retouch(): void;
  /** Drops the ready subscription. Surfaces that unmount owe this; the map lives forever. */
  release(): void;
}

/**
 * Underlines the glossary's words in `root` now, and again when the index lands.
 *
 * Controls are excluded at the call site with `data-no-glossary`: a term inside a button or a
 * row label swallows the click that was the control's, and hover already teaches.
 */
export function teach(root: ParentNode): Teaching {
  const retouch = (): void => highlight(root, termIndex());
  const release = onGlossaryReady(retouch);
  retouch();
  return { retouch, release };
}
