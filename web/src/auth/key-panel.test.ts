// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

const { keyPanel } = await import("./key-panel.ts");
const { storedKey } = await import("../api/client.ts");

const KEY = "b".repeat(64);
const onRetry = vi.fn();

function mount(reason: "missing" | "rejected"): HTMLElement {
  const panel = keyPanel({ reason, onRetry });
  document.body.appendChild(panel);
  return panel;
}

function submit(panel: HTMLElement, value: string): void {
  const input = panel.querySelector("input") as HTMLInputElement;
  input.value = value;
  panel.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
}

beforeEach(() => {
  document.body.innerHTML = "";
  window.localStorage.clear();
  onRetry.mockClear();
});

describe("the key panel is the recovery the app never had", () => {
  it("offers an input and both escape hatches", () => {
    const panel = mount("rejected");

    expect(panel.querySelector("input")?.type).toBe("password");
    expect(panel.textContent).toContain("Clear stored key");
    expect(panel.querySelector("button[type='submit']")).toBeTruthy();
  });

  it("names the wrong-key case rather than repeating the no-key copy", () => {
    expect(mount("rejected").textContent).toContain("rejected");
    document.body.innerHTML = "";
    expect(mount("missing").textContent).toContain("needs the owner key");
  });

  it("stores a well-shaped key and retries instead of bricking", () => {
    const panel = mount("rejected");

    submit(panel, KEY);

    expect(storedKey()).toBe(KEY);
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("refuses a malformed key in place, without storing it or retrying", () => {
    const panel = mount("rejected");

    submit(panel, "not-a-key");

    expect(storedKey()).toBeNull();
    expect(onRetry).not.toHaveBeenCalled();
    expect(panel.textContent).toContain("64 hex characters");
  });

  it("clears a stored key so the next load is the honest no-key state", () => {
    window.localStorage.setItem("glasswell.key", KEY);
    const panel = mount("rejected");

    panel.querySelector<HTMLButtonElement>(".gw-key-clear")?.click();

    expect(storedKey()).toBeNull();
    expect(panel.textContent).toContain("cleared");
  });

  it("never renders the stored key back into the DOM", () => {
    window.localStorage.setItem("glasswell.key", KEY);

    expect(mount("rejected").innerHTML).not.toContain(KEY);
  });
});
