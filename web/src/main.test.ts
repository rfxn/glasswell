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
// Typed to the real signature so `mock.calls[0][1]` is the api10 rather than never.
const renderWellCard = vi.fn(
  async (_container: HTMLElement, _api10: string, _callbacks: unknown): Promise<void> => {},
);

vi.mock("./card/card.ts", () => ({ renderWellCard }));
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

async function bootAt(
  url: string,
  onCreateMap?: () => void,
): Promise<typeof import("./bus.ts")> {
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
    onCreateMap?.();
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
  renderWellCard.mockClear();
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

describe("back and forward across sections do not tear the card down", () => {
  // followHistory replays the well on every popstate and renderWellCard begins by replacing
  // every child of its host, so a section-only entry unloaded every lazily loaded section,
  // re-issued every request and re-landed focus on the first focusable element.
  it("re-renders nothing and re-requests nothing when only the section changed", async () => {
    await bootAt("/?well=3305310451&section=production");
    const card = host("gw-card");
    // What renderWellCard does for itself and the mock does not: a populated, visible host is
    // the condition the guard reads, because an empty one has nothing to preserve.
    card.hidden = false;
    card.replaceChildren(document.createElement("p"));
    const mounted = card.firstElementChild;
    const applied: (string | null)[] = [];
    document.addEventListener("gw-section", (event) => {
      applied.push((event as CustomEvent<{ id: string | null }>).detail.id);
    });

    navigate("/?well=3305310451&section=neighbours");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(renderWellCard.mock.calls.length).toBe(1);
    expect(card.firstElementChild).toBe(mounted);
    expect(applied).toEqual(["neighbours"]);
  });

  it("still renders when the well itself changed, and keeps what the entry recorded", async () => {
    // A replay is not a choice: the section belongs to the history entry the reader is
    // returning to, and nulling it here rewrote the address bar without it (gate H-4).
    await bootAt("/?well=3305310451&section=neighbours");
    host("gw-card").hidden = false;
    host("gw-card").replaceChildren(document.createElement("p"));

    navigate("/?well=3305302532&section=basin");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(renderWellCard.mock.calls.length).toBe(2);
    expect(renderWellCard.mock.calls[1]?.[1]).toBe("3305302532");
    expect(window.location.search).toContain("section=basin");
  });

  it("drops the section when a reader chooses another well rather than replaying one", async () => {
    // The other half of the same rule: a section named for the last card does not survive a
    // choice, because the new card may not have it at all.
    const bus = await bootAt("/?well=3305310451&section=neighbours");
    host("gw-card").hidden = false;
    host("gw-card").replaceChildren(document.createElement("p"));

    bus.selectWell("3305302532", "map");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(window.location.search).not.toContain("section=");
  });

  it("keeps the section a deep link asked for through the first mount", async () => {
    await bootAt("/?well=3305310451&section=neighbours");
    expect(window.location.search).toContain("section=neighbours");
  });

  it("writes the section the card asks for, and only main writes app state", async () => {
    await bootAt("/?well=3305310451");
    const pushed = vi.spyOn(window.history, "pushState");
    const replaced = vi.spyOn(window.history, "replaceState");

    document.dispatchEvent(
      new CustomEvent("gw-section-set", { detail: { id: "land", mode: "replace" } }),
    );
    expect(window.location.search).toContain("section=land");
    expect(replaced).toHaveBeenCalledTimes(1);
    expect(pushed).not.toHaveBeenCalled();

    document.dispatchEvent(
      new CustomEvent("gw-section-set", { detail: { id: "basin", mode: "push" } }),
    );
    expect(window.location.search).toContain("section=basin");
    expect(pushed).toHaveBeenCalledTimes(1);

    document.dispatchEvent(
      new CustomEvent("gw-section-set", { detail: { id: null, mode: "replace" } }),
    );
    expect(window.location.search).not.toContain("section=");
  });
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

  it("renders the well the reader still has selected when the card chunk lands", async () => {
    const bus = await bootAt("/");
    await vi.waitFor(() => expect(createMap).toHaveBeenCalledOnce());

    bus.selectWell("3305310451", "map");

    await vi.waitFor(() => expect(renderWellCard).toHaveBeenCalledOnce());
    expect(renderWellCard.mock.calls[0]?.[1]).toBe("3305310451");
  });

  it("does not render a well the reader closed while the card chunk was still loading", async () => {
    // The card came off the entry path, so opening one is a fetch. Both calls below run
    // before that fetch resolves — without the guard the chunk's callback would paint a card
    // for a well nothing is selecting any more.
    const bus = await bootAt("/");
    await vi.waitFor(() => expect(createMap).toHaveBeenCalledOnce());

    bus.selectWell("3305310451", "map");
    bus.selectWell(null, "map");

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(renderWellCard).not.toHaveBeenCalled();
    expect(host("gw-card").hidden).toBe(true);
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

  // Copilot on PR #48: `showLoginPanel` cleared the name but not the role, and Status renders
  // its owner-only Accounts section from the role. A signed-out reader kept that section, and
  // the two owner-scoped requests behind it, until the next whoami answered.
  it("stops calling the reader an owner once their session is gone", async () => {
    vi.stubGlobal("fetch", servesSession);
    await bootAt("/?view=status");
    await vi.waitFor(() => expect(mountStatusPage).toHaveBeenCalledOnce());
    expect(mountStatusPage.mock.calls[0]?.[1]).toMatchObject({ role: "owner" });

    const hooks = mountStatusPage.mock.calls[0]?.[1] as { onForbidden(error: unknown): void };
    const { ApiError } = await import("./api/client.ts");
    hooks.onForbidden(
      new ApiError({ type: "/v1/errors/unauthenticated", title: "Forbidden", status: 403 }),
    );

    navigate("/?view=explore&ds=wells");
    await vi.waitFor(() => expect(host("gw-explore").hidden).toBe(false));
    navigate("/?view=status");
    await vi.waitFor(() => expect(mountStatusPage).toHaveBeenCalledTimes(2));

    expect(mountStatusPage.mock.calls[1]?.[1]).toMatchObject({ role: null });
  });

  // The map mounts before the session resolves, so its tiles and counts are refused and it
  // latches that. Signing in has to reach it, and the probe that already failed must not be
  // what tells the rest of the app who the reader is.
  describe("signing in after a signed-out arrival on the map", () => {
    const refusesSession = (input: RequestInfo | URL): Promise<Response> => {
      const path = String(input).split("?")[0];
      const status = path === "/v1/session" ? 403 : 404;
      return Promise.resolve(
        new Response(
          JSON.stringify({ type: "/v1/errors/unauthenticated", title: "Forbidden", status }),
          { status, headers: { "content-type": "application/problem+json" } },
        ),
      );
    };

    const signIn = (): void => {
      vi.stubGlobal("fetch", servesSession);
      const panel = host("gw-key-host");
      (panel.querySelector("#gw-login-user") as HTMLInputElement).value = "ryan";
      (panel.querySelector("#gw-login-pass") as HTMLInputElement).value = "correct horse";
      (panel.querySelector("form") as HTMLFormElement).dispatchEvent(
        new SubmitEvent("submit", { bubbles: true, cancelable: true }),
      );
    };

    it("announces the session, so the map can re-ask for what it was refused", async () => {
      vi.stubGlobal("fetch", refusesSession);
      const bus = await bootAt("/");
      await vi.waitFor(() => expect(host("gw-key-host").hidden).toBe(false));
      const began = vi.fn();
      bus.onSessionBegan(began);

      signIn();

      await vi.waitFor(() => expect(began).toHaveBeenCalledTimes(1));
    });

    it("shows the reader they are signed in without re-asking who they are", async () => {
      vi.stubGlobal("fetch", refusesSession);
      await bootAt("/");
      await vi.waitFor(() => expect(host("gw-key-host").hidden).toBe(false));
      expect(host("gw-logout-btn").hidden).toBe(true);

      signIn();

      await vi.waitFor(() => expect(host("gw-logout-btn").hidden).toBe(false));
      expect(host("gw-logout-btn").title).toContain("ryan");
    });
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

  // A deep link that names only a well has chosen no viewport, so the default one is North
  // Dakota by accident. A New Mexico well opened its card 700 km off the visible map.
  describe("a ?well= deep link and the camera", () => {
    const NM = { lon: -103.9, lat: 32.7 };

    function locates(): void {
      renderWellCard.mockImplementationOnce(async (_container, _api10, callbacks) => {
        (callbacks as { onLocated: (point: typeof NM) => void }).onLocated(NM);
      });
    }

    const flownTo = (): unknown[][] =>
      (createMap.mock.results[0]?.value as { flyTo: { mock: { calls: unknown[][] } } }).flyTo.mock
        .calls;

    it("flies to the well when the link named no viewport of its own", async () => {
      locates();

      await bootAt("/?view=map&well=3003912345");

      await vi.waitFor(() => expect(flownTo()).toHaveLength(1));
      expect(flownTo()[0]?.[0]).toEqual({ ...NM, zoom: 12 });
    });

    it("leaves the camera where a link that did choose a viewport put it", async () => {
      locates();

      await bootAt("/?view=map&well=3003912345&map=9/32.9/-104.1");

      await vi.waitFor(() => expect(select).toHaveBeenCalledWith("3003912345"));
      expect(flownTo()).toHaveLength(0);
    });
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

  it("hands focus back to the control that opened the sheet", async () => {
    // visual-map-wells-by D15: focus landed on the brand mark at the far top left, so a
    // keyboard reader lost their place in the control cluster on every Escape.
    await bootAt("/");
    const sheet = document.createElement("section");
    sheet.className = "gw-sheet";
    sheet.id = "gw-wells-by";
    const trigger = document.createElement("button");
    trigger.className = "gw-wells-by-button";
    trigger.setAttribute("aria-controls", sheet.id);
    trigger.setAttribute("aria-expanded", "true");
    document.body.append(sheet, trigger);

    escape();

    expect(sheet.hidden).toBe(true);
    expect(document.activeElement).toBe(trigger);
    sheet.remove();
    trigger.remove();
  });
});

/**
 * A signed-out arrival used to mount the map first and resolve the session second, so every
 * tile source and the status summary fired, 403'd behind the login modal, and stayed errored
 * — MapLibre does not retry a source on its own, which is what `onSessionBegan` in map.ts
 * exists to undo. The fix is an ordering one, so this is an ordering test.
 */
describe("what the first paint asks for before it knows who is asking", () => {
  /** The mocked map stands in for `createMap`, which is where every tile source attaches. */
  const attachTileSources = (): void => {
    void fetch("/v1/tiles/nd_wells/7/33/45.pbf");
  };

  function gatedFetch(sessionStatus = 200): { seen: string[]; answer: () => void } {
    const seen: string[] = [];
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    const problem = (status: number): Response =>
      new Response(JSON.stringify({ type: "about:blank", title: "held", status }), {
        status,
        headers: { "content-type": "application/problem+json" },
      });
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      const path = String(input).split("?")[0] ?? "";
      seen.push(path);
      // Held rather than slow: the assertion is that nothing raced past it, and a timeout
      // would make that a question about how long the test waited.
      if (path === "/v1/session") await held;
      return problem(path === "/v1/session" ? sessionStatus : 404);
    });
    return { seen, answer: release };
  }

  it("asks for no tile until the session has answered", async () => {
    const { seen, answer } = gatedFetch();

    await bootAt("/", attachTileSources);
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(seen).toContain("/v1/session");
    expect(seen.filter((path) => path.startsWith("/v1/tiles"))).toEqual([]);
    expect(createMap).not.toHaveBeenCalled();

    answer();
    await vi.waitFor(() => expect(createMap).toHaveBeenCalledOnce());
    await vi.waitFor(() =>
      expect(seen.some((path) => path.startsWith("/v1/tiles"))).toBe(true),
    );
    // The order, not merely the presence: the session is the first thing this page asks.
    expect(seen.indexOf("/v1/session")).toBeLessThan(
      seen.findIndex((path) => path.startsWith("/v1/tiles")),
    );
  });

  it("still mounts the map for a reader the probe refuses", async () => {
    // The gate orders the first paint; it does not withhold it. A refused reader gets the
    // substrate and the login modal, not a blank canvas — which is what /basemap is for.
    const { answer } = gatedFetch(403);

    await bootAt("/", attachTileSources);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(createMap).not.toHaveBeenCalled();
    answer();
    await vi.waitFor(() => expect(createMap).toHaveBeenCalledOnce());
  });

  it("asks who the reader is exactly once, however many surfaces wait on the answer", async () => {
    // boot() and the surface mount are two callers of one probe. Two probes would be two
    // round trips for one question, and a second 403 toast for a reader already at the modal.
    const { seen, answer } = gatedFetch();

    await bootAt("/", attachTileSources);
    answer();
    await vi.waitFor(() => expect(createMap).toHaveBeenCalledOnce());
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(seen.filter((path) => path === "/v1/session")).toHaveLength(1);
  });
});
