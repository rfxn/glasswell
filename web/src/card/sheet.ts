/**
 * The bottom sheet's three snap points, below 900 px only. Imported by main.ts when
 * `matchMedia("(max-width: 900px)")` matches, so a desktop reader never downloads it.
 *
 * `aria-expanded` is boolean and this control has three states, so the grab bar is a slider:
 * arrow keys are that role's native keyboard contract, and a drag-only sheet is not operable
 * from a keyboard at all. The heights are style.css's, repeated here only so a pointer drag
 * can snap to the nearest one; the stops themselves are declared in one place.
 */
const STOPS = ["peek", "half", "full"] as const;

type Stop = (typeof STOPS)[number];

function stopHeights(): number[] {
  const dvh = window.innerHeight / 100;
  return [160, 46 * dvh, 78 * dvh];
}

function nearestStop(height: number): number {
  const heights = stopHeights();
  let nearest = 0;
  for (let index = 1; index < heights.length; index += 1) {
    if (Math.abs((heights[index] as number) - height) < Math.abs((heights[nearest] as number) - height)) {
      nearest = index;
    }
  }
  return nearest;
}

export function wireSheet(main: HTMLElement, grab: HTMLElement): void {
  let index = STOPS.indexOf(main.getAttribute("data-sheet-snap") as Stop);
  if (index < 0) index = STOPS.length - 1;

  function apply(next: number): void {
    index = Math.min(STOPS.length - 1, Math.max(0, next));
    const stop = STOPS[index] as Stop;
    main.setAttribute("data-sheet-snap", stop);
    grab.setAttribute("aria-valuenow", String(index + 1));
    grab.setAttribute("aria-valuetext", stop);
  }

  apply(index);

  grab.addEventListener("keydown", (event) => {
    const step = { ArrowUp: 1, ArrowDown: -1, ArrowRight: 1, ArrowLeft: -1 }[event.key];
    if (step !== undefined) apply(index + step);
    else if (event.key === "Home") apply(0);
    else if (event.key === "End") apply(STOPS.length - 1);
    else return;
    event.preventDefault();
  });

  let dragging = false;
  grab.addEventListener("pointerdown", (event) => {
    dragging = true;
    grab.setPointerCapture(event.pointerId);
    // The height follows the pointer while the drag runs, so the transition that makes a
    // snap readable would make a drag lag behind the finger holding it.
    main.setAttribute("data-sheet-drag", "");
  });
  grab.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    main.style.setProperty("--gw-sheet-h", `${window.innerHeight - event.clientY}px`);
  });
  grab.addEventListener("pointerup", (event) => {
    if (!dragging) return;
    dragging = false;
    main.removeAttribute("data-sheet-drag");
    main.style.removeProperty("--gw-sheet-h");
    apply(nearestStop(window.innerHeight - event.clientY));
  });
}
