// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const INDEX_BODY =
  /<body[^>]*>([\s\S]*)<\/body>/
    .exec(readFileSync("index.html", "utf8").replace(/<script[\s\S]*?<\/script>/g, ""))
    ?.[1] ?? "";

const select = vi.fn();
const createMap = vi.fn();

vi.mock("./map/map.ts", () => ({ createMap }));

// main.ts registers window and document listeners at import. Each boot below is a new module
// instance, so the previous instance's listeners have to come off or they answer popstate too.
const detachers: (() => void)[] = [];
const restorers: (() => void)[] = [];

function captureListeners(target: EventTarget): void {
  const original = target.addEventListener;
  const bound = original.bind(target);
  const patched: EventTarget["addEventListener"] = (type, handler, options) => {
    detachers.push(() => target.removeEventListener(type, handler, options));
    bound(type, handler, options);
  };
  const define = (value: EventTarget["addEventListener"]): void => {
    Object.defineProperty(target, "addEventListener", { value, configurable: true, writable: true });
  };
  define(patched);
  restorers.push(() => define(original));
}

function releaseListeners(): void {
  for (const detach of detachers.splice(0)) detach();
  for (const restore of restorers.splice(0)) restore();
}

function host(id: string): HTMLElement {
  const element = document.getElementById(id);
  if (!element) throw new Error(`missing #${id}`);
  return element;
}

async function bootAt(url: string): Promise<typeof import("./bus.ts")> {
  document.body.innerHTML = INDEX_BODY;
  window.history.replaceState(null, "", url);
  captureListeners(window);
  captureListeners(document);
  vi.resetModules();
  const bus = await import("./bus.ts");
  createMap.mockImplementation(() => {
    const handle = { select, flyTo: vi.fn() };
    // map.ts:479 verbatim: connectMap's disposer is discarded, so a second mount is a
    // second handler and one click would select twice.
    bus.connectMap(handle);
    return handle;
  });
  await import("./main.ts");
  return bus;
}

function navigate(url: string): void {
  window.history.pushState(null, "", url);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

beforeEach(() => {
  createMap.mockClear();
  select.mockClear();
  // Every payload a 404: this file tests mount and subscription order, not rendering.
  vi.stubGlobal("fetch", () =>
    Promise.resolve(
      new Response(JSON.stringify({ type: "about:blank", title: "Not found", status: 404 }), {
        status: 404,
        headers: { "content-type": "application/problem+json" },
      }),
    ),
  );
});

afterEach(() => {
  releaseListeners();
  vi.unstubAllGlobals();
});

describe("one dispatch on view, two surfaces (SB-08 §2.1)", () => {
  // B1: createMap is not idempotent and its callee's disposer is discarded, so a second mount
  // is a second canvas and a second bus handler — one click would then select twice.
  it("mounts the map once across map → explore → back, and leaves one subscriber", async () => {
    const bus = await bootAt("/");
    await vi.waitFor(() => expect(createMap).toHaveBeenCalledTimes(1));

    navigate("/?view=explore&ds=wells");
    await vi.waitFor(() => expect(host("gw-explore").hidden).toBe(false));
    expect(host("gw-map").hidden).toBe(true);

    navigate("/");
    await vi.waitFor(() => expect(host("gw-map").hidden).toBe(false));
    expect(host("gw-explore").hidden).toBe(true);

    expect(createMap).toHaveBeenCalledTimes(1);

    select.mockClear();
    bus.wellSelected("3305310451");

    expect(select).toHaveBeenCalledTimes(1);
  });

  it("never constructs a map for a reader who arrives on the explorer", async () => {
    await bootAt("/?view=explore&ds=quarantine");
    await vi.waitFor(() => expect(host("gw-explore").hidden).toBe(false));

    expect(createMap).not.toHaveBeenCalled();
    expect(host("gw-map").hidden).toBe(true);
  });

  // The dynamic import reorders boot: the map subscribes inside createMap, so a selection
  // restored before that await lands in a bus the map has not joined and the well never lights.
  it("gives a ?well= deep link a bus that the map has already joined", async () => {
    await bootAt("/?well=3305310451");

    await vi.waitFor(() => expect(select).toHaveBeenCalledWith("3305310451"));
    expect(select).toHaveBeenCalledTimes(1);
  });
});

describe("the as_of chip honours a pinned route at boot (gate-c12 R5 / visual F3)", () => {
  const LATEST = "2026-08-22";
  const PINNED = "2026-08-20";

  // Two published vintages, so the pin and the service-latest date genuinely differ — the
  // single-vintage harness is exactly what masked F3.
  beforeEach(() => {
    vi.stubGlobal("fetch", (input: RequestInfo | URL) => {
      const path = String(input).split("?")[0];
      if (path === "/v1") {
        const body = {
          data: { published_vintages: [{ vintage_date: LATEST }, { vintage_date: PINNED }] },
          meta: {},
          links: {},
        };
        return Promise.resolve(
          new Response(JSON.stringify(body), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify({ type: "about:blank", title: "Not found", status: 404 }), {
          status: 404,
          headers: { "content-type": "application/problem+json" },
        }),
      );
    });
  });

  it("shows the pinned as_of on a pinned explorer route, not the latest published vintage", async () => {
    await bootAt(`/?view=explore&ds=wells&as_of=${PINNED}`);

    await vi.waitFor(() => expect(host("gw-asof").textContent).toContain(PINNED));
    expect(host("gw-asof").textContent).not.toContain(LATEST);
  });

  it("keeps the latest published vintage for an unpinned route", async () => {
    await bootAt("/");

    await vi.waitFor(() => expect(host("gw-asof").textContent).toContain(LATEST));
  });

  it("reads a bare as_of= as nobody's pin, the same as bridge.ts", async () => {
    await bootAt("/?view=explore&ds=wells&as_of=");

    await vi.waitFor(() => expect(host("gw-asof").textContent).toContain(LATEST));
  });
});
