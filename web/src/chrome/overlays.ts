/**
 * One MutationObserver on `hidden` drives focus for every overlay, so no open/close site
 * ever grows focus code. Escape stays out of this helper deliberately: the app keeps one
 * close path so the topmost-layer rule cannot drift between panels.
 */

const FOCUSABLE =
  "[tabindex='-1'], button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])";

interface Overlay {
  element: HTMLElement;
  modal: boolean;
}

const overlays: Overlay[] = [];
const open: HTMLElement[] = [];
let restoreTo: HTMLElement | null = null;
let observer: MutationObserver | null = null;
let watchingFocus = false;

export function registerOverlay(element: HTMLElement, options?: { modal?: boolean }): void {
  overlays.push({ element, modal: options?.modal === true });
  watchFocus();
  observe().observe(element, { attributes: true, attributeFilter: ["hidden"] });
}

/**
 * Re-focus after a panel replaces its own contents: the loading placeholder the observer
 * focused on open is gone by then, and focus would otherwise be stranded on <body>.
 * Focus already elsewhere (the search box, say) is left where the reader put it.
 */
export function focusPanel(element: HTMLElement): void {
  const active = document.activeElement;
  if (active !== null && active !== document.body && !element.contains(active)) return;
  const landing = element.querySelector<HTMLElement>(FOCUSABLE);
  if (!landing) return;
  // gate-v076 D4: a `tabindex="-1"` landing spot is only ever reached programmatically, and on
  // a deep link there has been no interaction at all -- which is precisely the state Chromium
  // resolves `:focus-visible` as true in. So a reader who arrived by URL was shown a dashed
  // ring around the card title they never asked to focus. Focus still moves, and is still
  // announced; only the ring is held back, and only until the reader touches a key, after
  // which the affordance a keyboard user needs is back.
  landing.dataset["gwQuietFocus"] = "";
  const restore = (): void => {
    delete landing.dataset["gwQuietFocus"];
  };
  landing.addEventListener("blur", restore, { once: true });
  document.addEventListener("keydown", restore, { once: true });
  landing.focus();
}

export function releaseOverlays(): void {
  observer?.disconnect();
  observer = null;
  overlays.length = 0;
  open.length = 0;
  restoreTo = null;
}

function observe(): MutationObserver {
  if (!observer) {
    observer = new MutationObserver((records) => {
      for (const record of records) {
        const element = record.target as HTMLElement;
        if (element.hidden) closed(element);
        else opened(element);
      }
      refreshInert();
    });
  }
  return observer;
}

/**
 * Capturing, because an overlay that focuses itself synchronously would otherwise record
 * its own child as the restore target.
 */
function watchFocus(): void {
  if (watchingFocus) return;
  watchingFocus = true;
  document.addEventListener(
    "focusin",
    (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (open.some((element) => element.contains(target))) return;
      restoreTo = target;
    },
    true,
  );
}

function opened(element: HTMLElement): void {
  if (open.includes(element)) return;
  open.push(element);
  const first = element.querySelector<HTMLElement>(FOCUSABLE);
  first?.focus();
}

function closed(element: HTMLElement): void {
  const at = open.indexOf(element);
  if (at === -1) return;
  open.splice(at, 1);
  if (!element.contains(document.activeElement)) return;
  if (restoreTo?.isConnected) restoreTo.focus();
  else (document.body as HTMLElement).focus();
}

function refreshInert(): void {
  for (const element of document.querySelectorAll("[data-gw-inert]")) {
    element.removeAttribute("inert");
    element.removeAttribute("aria-hidden");
    element.removeAttribute("data-gw-inert");
  }
  const topmost = [...open].reverse().find((element) => isModal(element));
  if (!topmost) return;
  for (let node: HTMLElement | null = topmost; node?.parentElement; node = node.parentElement) {
    for (const sibling of node.parentElement.children) {
      if (sibling === node) continue;
      sibling.setAttribute("inert", "");
      sibling.setAttribute("aria-hidden", "true");
      sibling.setAttribute("data-gw-inert", "");
    }
  }
}

function isModal(element: HTMLElement): boolean {
  return overlays.some((overlay) => overlay.element === element && overlay.modal);
}
