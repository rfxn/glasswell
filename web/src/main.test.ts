// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const INDEX_BODY =
  /<body[^>]*>([\s\S]*)<\/body>/
    .exec(readFileSync("index.html", "utf8").replace(/<script[\s\S]*?<\/script>/g, ""))
    ?.[1] ?? "";

const select = vi.fn();
const createMap = vi.fn();
const mountExplorer = vi.fn();
const unmountExplorer = vi.fn();
const mountStatusPage = vi.fn();
const unmountStatusPage = vi.fn();

vi.mock("./map/map.ts", () => ({ createMap }));
vi.mock("./explore/shell.ts", () => ({ mountExplorer, unmountExplorer }));
vi.mock("./status-page/surface.ts", () => ({ mountStatusPage, unmountStatusPage }));

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
  // main starts asynchronously by design. Let its fire-and-forget service index and glossary
  // reads reach the stub before a short routing test can restore the native fetch in afterEach.
  await new Promise((resolve) => setTimeout(resolve, 0));
  return bus;
}

const SESSION = {
  data: {
    username: "ryan",
    role: "owner",
    kind: "user",
    expires_at: null,
    absolute_expires_at: null,
  },
  meta: {},
  links: {},
};

/** The login panel signs in over fetch, so the harness answers the challenge and the POST. */
function servesSession(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const path = String(input).split("?")[0];
  const body =
    path === "/v1/session/challenge"
      ? { data: { csrf_token: "tok", expires_in: 14400 }, meta: {}, links: {} }
      : SESSION;
  if (path !== "/v1/session/challenge" && path !== "/v1/session") {
    return Promise.resolve(
      new Response(JSON.stringify({ type: "about:blank", title: "Not found", status: 404 }), {
        status: 404,
        headers: { "content-type": "application/problem+json" },
      }),
    );
  }
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status: init?.method === "POST" ? 201 : 200,
      headers: { "content-type": "application/json" },
    }),
  );
}

function navigate(url: string): void {
  window.history.pushState(null, "", url);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

beforeEach(() => {
  createMap.mockClear();
  select.mockClear();
  mountExplorer.mockReset();
  unmountExplorer.mockClear();
  mountExplorer.mockResolvedValue(undefined);
  mountStatusPage.mockReset();
  unmountStatusPage.mockClear();
  mountStatusPage.mockResolvedValue(undefined);
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

describe("one dispatch on view, three surfaces (SB-08 §2.1)", () => {
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

  it("never constructs a map for a reader who arrives on Status", async () => {
    await bootAt("/?view=status");
    await vi.waitFor(() => expect(host("gw-status-page").hidden).toBe(false));

    expect(mountStatusPage).toHaveBeenCalledOnce();
    expect(createMap).not.toHaveBeenCalled();
    expect(host("gw-map").hidden).toBe(true);
    expect(host("gw-explore").hidden).toBe(true);
  });

  it("takes a Status search selection to Map before restoring its well", async () => {
    const bus = await bootAt("/?view=status");
    await vi.waitFor(() => expect(host("gw-status-page").hidden).toBe(false));

    bus.selectWell("3305310451", "search");

    await vi.waitFor(() => expect(host("gw-map").hidden).toBe(false));
    await vi.waitFor(() => expect(select).toHaveBeenCalledWith("3305310451"));
    expect(new URLSearchParams(window.location.search).get("view")).toBeNull();
    expect(new URLSearchParams(window.location.search).get("well")).toBe("3305310451");
    expect(host("gw-status-page").hidden).toBe(true);
  });

  it("supports back-forward transitions across all three surfaces", async () => {
    await bootAt("/");
    await vi.waitFor(() => expect(createMap).toHaveBeenCalledOnce());

    navigate("/?view=status");
    await vi.waitFor(() => expect(host("gw-status-page").hidden).toBe(false));

    navigate("/?view=explore&ds=wells");
    await vi.waitFor(() => expect(host("gw-explore").hidden).toBe(false));
    expect(host("gw-status-page").hidden).toBe(true);

    navigate("/?view=status");
    await vi.waitFor(() => expect(host("gw-status-page").hidden).toBe(false));
    expect(host("gw-explore").hidden).toBe(true);
    expect(createMap).toHaveBeenCalledOnce();
  });

  it("does not restore card or drawer overlays on a hostile Status deep link", async () => {
    await bootAt("/?view=status&well=3305310451&explain=drv_1");
    await vi.waitFor(() => expect(host("gw-status-page").hidden).toBe(false));

    expect(host("gw-card").hidden).toBe(true);
    expect(host("gw-drawer").hidden).toBe(true);
    expect(createMap).not.toHaveBeenCalled();
  });

  it("routes a Status 403 through the login panel and remounts Status once signed in", async () => {
    await bootAt("/?view=status");
    await vi.waitFor(() => expect(mountStatusPage).toHaveBeenCalledOnce());
    const hooks = mountStatusPage.mock.calls[0]?.[1] as { onForbidden(error: unknown): void };
    const { ApiError } = await import("./api/client.ts");

    hooks.onForbidden(
      new ApiError({
        type: "/v1/errors/unauthenticated",
        title: "Forbidden",
        status: 403,
      }),
    );
    expect(host("gw-key-host").hidden).toBe(false);

    vi.stubGlobal("fetch", servesSession);
    const panel = host("gw-key-host");
    (panel.querySelector("#gw-login-user") as HTMLInputElement).value = "ryan";
    (panel.querySelector("#gw-login-pass") as HTMLInputElement).value = "correct horse";
    (panel.querySelector("form") as HTMLFormElement).dispatchEvent(
      new SubmitEvent("submit", { bubbles: true, cancelable: true }),
    );

    await vi.waitFor(() => expect(mountStatusPage).toHaveBeenCalledTimes(2));
    expect(host("gw-key-host").hidden).toBe(true);
    expect(createMap).not.toHaveBeenCalled();
  });

  it("clears any owner key an earlier build left in this browser", async () => {
    window.localStorage.setItem("glasswell.key", "f".repeat(64));

    await bootAt("/");

    expect(window.localStorage.getItem("glasswell.key")).toBeNull();
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

describe("one Escape closes one layer (SB-05 §7)", () => {
  const escape = (): void => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  };

  const openPanel = (id: string): HTMLElement => {
    const panel = host(id);
    panel.hidden = false;
    return panel;
  };

  // The rail's popouts and the glossary popover all sit above the panels on the z ladder and
  // all own their own dismissal, but each was a second document listener beside this one: a
  // reader who pressed Escape over an open popover lost the well card under it as well.
  it("leaves the card standing while a layer above it is open", async () => {
    await bootAt("/");
    const card = openPanel("gw-card");
    const popover = document.createElement("div");
    popover.className = "gw-popover";
    document.body.appendChild(popover);

    escape();

    expect(card.hidden).toBe(false);
    popover.remove();
  });

  it("leaves the card standing while the help panel is open", async () => {
    await bootAt("/");
    const card = openPanel("gw-card");
    openPanel("gw-help-panel");

    escape();

    expect(card.hidden).toBe(false);
  });

  it("closes the card once nothing is above it", async () => {
    await bootAt("/?well=3305310451");
    const card = openPanel("gw-card");

    escape();

    await vi.waitFor(() => expect(card.hidden).toBe(true));
  });

  it("takes a hidden popover as no layer at all", async () => {
    await bootAt("/?well=3305310451");
    const card = openPanel("gw-card");
    const popover = document.createElement("div");
    popover.className = "gw-popover";
    popover.hidden = true;
    document.body.appendChild(popover);

    escape();

    await vi.waitFor(() => expect(card.hidden).toBe(true));
    popover.remove();
  });
});
