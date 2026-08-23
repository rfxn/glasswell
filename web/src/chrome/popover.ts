/**
 * Placement for the `.gw-popover` surface, shared by the glossary term and the explorer's
 * exempt-count reason — one object with one chrome, and until now two copies of this
 * arithmetic. Under the anchor, flipped above it when below cannot hold it, and always with
 * the room it may occupy, so a definition too long for either side scrolls against its own
 * cap instead of running off the fold with nothing saying more is there.
 */

const GUTTER = 8;

export interface PopoverSpot {
  left: number;
  top: number;
  maxHeight: number;
}

interface Size {
  width: number;
  height: number;
}

export function popoverSpot(
  anchor: { top: number; bottom: number; left: number; right: number },
  size: Size,
  viewport: Size,
): PopoverSpot {
  const below = anchor.bottom + GUTTER;
  const roomBelow = viewport.height - GUTTER - below;
  const roomAbove = anchor.top - 2 * GUTTER;
  // The anchor is the word being defined, so a popover that fits neither side takes the
  // larger one and folds rather than covering what raised it.
  const goesBelow = size.height <= roomBelow || roomBelow >= roomAbove;
  const maxHeight = Math.max(GUTTER, goesBelow ? roomBelow : roomAbove);
  const height = Math.min(size.height, maxHeight);
  return {
    left: Math.max(GUTTER, Math.min(anchor.left, viewport.width - size.width - GUTTER)),
    top: Math.max(GUTTER, goesBelow ? below : anchor.top - height - GUTTER),
    maxHeight,
  };
}

/** Places `element` against `anchor` and hands it the height it is allowed to occupy. */
export function placePopover(element: HTMLElement, anchor: Element): void {
  // Uncapped for the measurement: a re-place once the full definition lands would otherwise
  // measure the previous cap and the surface could never grow back into the room it has.
  element.style.setProperty("--gw-popover-room", "none");
  const spot = popoverSpot(
    anchor.getBoundingClientRect(),
    { width: element.offsetWidth || 320, height: element.offsetHeight || 160 },
    { width: window.innerWidth, height: window.innerHeight },
  );
  element.style.left = `${spot.left + window.scrollX}px`;
  element.style.top = `${spot.top + window.scrollY}px`;
  element.style.setProperty("--gw-popover-room", `${spot.maxHeight}px`);
}
