// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from "vitest";

import { focusPanel, registerOverlay, releaseOverlays } from "./overlays.ts";

let map: HTMLElement;
let trigger: HTMLButtonElement;
let panel: HTMLElement;
let heading: HTMLElement;

const settle = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0));

beforeEach(() => {
  releaseOverlays();
  document.body.innerHTML = "";
  map = document.createElement("div");
  trigger = document.createElement("button");
  panel = document.createElement("aside");
  panel.hidden = true;
  heading = document.createElement("h2");
  heading.tabIndex = -1;
  const close = document.createElement("button");
  panel.append(heading, close);
  document.body.append(map, trigger, panel);
});

describe("one observer drives focus for every overlay (harvest item 7)", () => {
  it("moves focus into a panel when it is shown, with no code at the open site", async () => {
    registerOverlay(panel);
    trigger.focus();

    panel.hidden = false;
    await settle();

    expect(document.activeElement).toBe(heading);
  });

  it("restores focus to whatever had it before the panel opened", async () => {
    registerOverlay(panel);
    trigger.focus();
    panel.hidden = false;
    await settle();

    panel.hidden = true;
    await settle();

    expect(document.activeElement).toBe(trigger);
  });

  it("parks focus on the body when the restore target has left the document", async () => {
    // Asserted on where focus ended up, not on the absence of a throw: `.focus()` on a
    // detached element is a silent no-op, so an unguarded restore strands focus inside the
    // panel that just closed while every assertion about another element still passes.
    // This is happy-dom, which fires no blur when a focused element is removed -- so what is
    // pinned is that this module moved focus itself rather than the removal doing it.
    registerOverlay(panel);
    trigger.focus();
    panel.hidden = false;
    await settle();
    trigger.remove();

    panel.hidden = true;
    await settle();

    expect(document.activeElement).toBe(document.body);
    expect(panel.contains(document.activeElement)).toBe(false);
    expect(document.body.contains(panel)).toBe(true);
  });

  it("makes the rest of the document inert for a modal overlay", async () => {
    registerOverlay(panel, { modal: true });

    panel.hidden = false;
    await settle();

    expect(map.hasAttribute("inert")).toBe(true);
    expect(map.getAttribute("aria-hidden")).toBe("true");
    expect(panel.hasAttribute("inert")).toBe(false);
  });

  it("lifts inert again when the modal closes", async () => {
    registerOverlay(panel, { modal: true });
    panel.hidden = false;
    await settle();

    panel.hidden = true;
    await settle();

    expect(map.hasAttribute("inert")).toBe(false);
    expect(map.hasAttribute("aria-hidden")).toBe(false);
  });

  it("leaves the map interactive for a non-modal panel — the card is not a dialog", async () => {
    registerOverlay(panel);

    panel.hidden = false;
    await settle();

    expect(map.hasAttribute("inert")).toBe(false);
  });

  it("re-focuses a panel that swapped its loading state for its content", () => {
    document.body.focus();

    focusPanel(panel);

    expect(document.activeElement).toBe(heading);
  });

  // gate-v076 D4: the landing spot is only ever reached programmatically, and on a deep link
  // there has been no interaction, which is the state Chromium calls :focus-visible — so every
  // deep-linked card painted a dashed ring around a title the reader never focused.
  it("lands focus quietly, and gives the ring back at the first keypress", () => {
    document.body.focus();

    focusPanel(panel);

    expect(document.activeElement).toBe(heading);
    expect(heading.hasAttribute("data-gw-quiet-focus")).toBe(true);

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));

    expect(heading.hasAttribute("data-gw-quiet-focus")).toBe(false);
    // Focus itself never moved: only the painted ring was held back.
    expect(document.activeElement).toBe(heading);
  });

  it("leaves focus where the reader put it, outside the panel", () => {
    trigger.focus();

    focusPanel(panel);

    expect(document.activeElement).toBe(trigger);
  });

  it("inerts an ancestor's siblings, not just the body's children", async () => {
    const shell = document.createElement("div");
    const sibling = document.createElement("div");
    document.body.append(shell);
    shell.append(sibling, panel);
    registerOverlay(panel, { modal: true });

    panel.hidden = false;
    await settle();

    expect(sibling.hasAttribute("inert")).toBe(true);
    expect(shell.hasAttribute("inert")).toBe(false);
  });
});
