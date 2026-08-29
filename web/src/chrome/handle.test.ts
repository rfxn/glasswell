// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EXPLAIN_EVENT, dispatchExplain, explainHandle, setExplainHandle } from "./handle.ts";

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("the one provenance affordance", () => {
  it("is a real button, so the keyboard reaches it without a key handler of its own", () => {
    const handle = explainHandle({ label: "the well count", handle: "drv_1" });
    expect(handle.tagName).toBe("BUTTON");
    expect(handle.type).toBe("button");
    expect(handle.className).toBe("gw-handle");
    expect(handle.textContent).toBe("⌾");
  });

  it("takes a modifier class beside the shared one, never instead of it", () => {
    const handle = explainHandle({ label: "these bin edges", className: "gw-thm-handle" });
    expect(handle.className).toBe("gw-handle gw-thm-handle");
  });

  it("names the figure it explains before any derivation arrives", () => {
    // The drift this replaced: two of the seven copies set no name at build, so a screen
    // reader met a button called "⌾" until the tile answered.
    const handle = explainHandle({ label: "these cell figures" });
    expect(handle.getAttribute("aria-label")).toBe("Lineage for these cell figures");
  });

  it("keeps the derivation id out of the accessible name and in the title", () => {
    const handle = explainHandle({ label: "lateral length", handle: "drv_9" });
    expect(handle.getAttribute("aria-label")).toBe("Lineage for lateral length");
    expect(handle.title).toBe("Show where lateral length came from: drv_9");
  });

  it("is visible exactly when it has a derivation to resolve", () => {
    const withHandle = explainHandle({ label: "the well count", handle: "drv_1" });
    const without = explainHandle({ label: "the well count" });
    expect(withHandle.hidden).toBe(false);
    expect(without.hidden).toBe(true);
  });

  it("raises the one event the drawer opens on, and it bubbles", () => {
    const handle = explainHandle({ label: "the well count", handle: "drv_1" });
    document.body.appendChild(handle);
    const seen = vi.fn();
    document.addEventListener(EXPLAIN_EVENT, (event) =>
      seen((event as CustomEvent<{ handle: string }>).detail.handle),
    );
    handle.click();
    expect(seen).toHaveBeenCalledWith("drv_1");
  });

  it("stays silent when it carries no derivation, rather than raising an empty handle", () => {
    const handle = explainHandle({ label: "the well count" });
    document.body.appendChild(handle);
    const seen = vi.fn();
    document.addEventListener(EXPLAIN_EVENT, seen);
    handle.click();
    expect(seen).not.toHaveBeenCalled();
  });

  it("lets a host route the explain itself instead of raising the event", () => {
    const routed = vi.fn();
    const handle = explainHandle({ label: "gas", handle: "drv_g", activate: (id) => routed(id) });
    document.body.appendChild(handle);
    const seen = vi.fn();
    document.addEventListener(EXPLAIN_EVENT, seen);
    handle.click();
    expect(routed).toHaveBeenCalledWith("drv_g");
    expect(seen).not.toHaveBeenCalled();
  });
});

describe("re-pointing a handle as its derivation arrives", () => {
  it("moves the dataset, the visibility and the title together", () => {
    const handle = explainHandle({ label: "the active count" });
    setExplainHandle(handle, "drv_active");
    expect(handle.dataset["handle"]).toBe("drv_active");
    expect(handle.hidden).toBe(false);
    expect(handle.title).toBe("Show where the active count came from: drv_active");
  });

  it("keeps the accessible name when the derivation goes away", () => {
    // The blanked `aria-label=""` the map copies used to leave behind is the defect: the
    // button keeps its name and loses only what it points at.
    const handle = explainHandle({ label: "the active count", handle: "drv_active" });
    setExplainHandle(handle, null);
    expect(handle.hidden).toBe(true);
    expect(handle.dataset["handle"]).toBe("");
    expect(handle.title).toBe("");
    expect(handle.getAttribute("aria-label")).toBe("Lineage for the active count");
  });

  it("resolves the derivation it was last pointed at, not the one it was built with", () => {
    const handle = explainHandle({ label: "the active count", handle: "drv_first" });
    document.body.appendChild(handle);
    setExplainHandle(handle, "drv_second");
    const seen = vi.fn();
    document.addEventListener(EXPLAIN_EVENT, (event) =>
      seen((event as CustomEvent<{ handle: string }>).detail.handle),
    );
    handle.click();
    expect(seen).toHaveBeenCalledWith("drv_second");
  });
});

describe("dispatchExplain", () => {
  it("raises the event from whichever node the host wants it attributed to", () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const seen = vi.fn();
    host.addEventListener(EXPLAIN_EVENT, (event) =>
      seen((event as CustomEvent<{ handle: string }>).detail.handle),
    );
    dispatchExplain(host, "drv_host");
    expect(seen).toHaveBeenCalledWith("drv_host");
  });
});
