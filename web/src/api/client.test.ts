// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ResponseMeta } from "./client.ts";

const {
  ApiError,
  authHeaders,
  getChallenge,
  getEnvelope,
  login,
  logout,
  purgeLegacyKey,
  whoami,
} = await import("./client.ts");

const ENVELOPE = { data: { api10: "3305310451" }, meta: { as_of: "2026-08-01" } };
const CHALLENGE = { data: { csrf_token: "tok", expires_in: 14400 }, meta: {}, links: {} };
const SESSION = {
  data: {
    username: "ryan",
    role: "owner",
    kind: "user",
    expires_at: "2026-08-30T12:00:00Z",
    absolute_expires_at: "2026-08-31T00:00:00Z",
  },
  meta: {},
  links: {},
};

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function responds(status: number, body: unknown, headers: Record<string, string> = {}) {
  return vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json", ...headers },
      }),
    ),
  );
}

/** The challenge, then a scripted reply per subsequent call. */
function exchange(...replies: Response[]) {
  const queue = [...replies];
  return vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
    if (String(input).includes("/v1/session/challenge")) {
      return Promise.resolve(json(200, CHALLENGE));
    }
    return Promise.resolve(queue.shift() ?? json(500, { title: "unscripted call" }));
  });
}

function initOf(spy: ReturnType<typeof vi.fn>, index: number): RequestInit {
  return (spy.mock.calls[index] as [string, RequestInit])[1];
}

beforeEach(async () => {
  window.localStorage.clear();
  window.history.replaceState(null, "", "/");
  // The held token is module state, and logout is the only exported way back to holding none;
  // without this every test would inherit whichever token the one before it left behind.
  vi.stubGlobal("fetch", exchange(json(200, SESSION)));
  await logout();
  vi.unstubAllGlobals();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the owner key is gone, and no path can revive it", () => {
  it("clears a key an earlier build left in this browser", () => {
    window.localStorage.setItem("glasswell.key", "f".repeat(64));

    purgeLegacyKey();

    expect(window.localStorage.getItem("glasswell.key")).toBeNull();
  });

  it("is idempotent, so a second boot is not an error", () => {
    purgeLegacyKey();
    purgeLegacyKey();

    expect(window.localStorage.getItem("glasswell.key")).toBeNull();
  });

  it("never reads a `#key=` fragment back into a header", async () => {
    window.history.replaceState(null, "", `/#key=${"a".repeat(64)}`);
    const fetched = responds(200, ENVELOPE);
    vi.stubGlobal("fetch", fetched);

    await getEnvelope("/v1/wells");

    const headers = initOf(fetched, 0).headers as Record<string, string>;
    expect(Object.keys(headers)).toEqual(["Accept"]);
  });
});

describe("CSRF guards writes and only writes", () => {
  it("sends nothing on a safe method, because the cookie is the credential", async () => {
    vi.stubGlobal("fetch", exchange());
    await getChallenge();

    expect(authHeaders()).toEqual({});
    expect(authHeaders("GET")).toEqual({});
    expect(authHeaders("head")).toEqual({});
    expect(authHeaders("OPTIONS")).toEqual({});
  });

  it("sends the token on a method that changes something", async () => {
    vi.stubGlobal("fetch", exchange());

    await getChallenge();

    expect(authHeaders("POST")).toEqual({ "X-Glasswell-CSRF": "tok" });
    expect(authHeaders("delete")).toEqual({ "X-Glasswell-CSRF": "tok" });
  });

  it("sends no header when no challenge has been answered yet", () => {
    expect(authHeaders("POST")).toEqual({});
  });

  it("drops the token on logout, so a dead session cannot keep proving origin", async () => {
    vi.stubGlobal("fetch", exchange(json(200, SESSION)));
    await getChallenge();

    await logout();

    expect(authHeaders("POST")).toEqual({});
  });
});

describe("a session is opened and closed over the same fetch the app uses", () => {
  it("mints a token before it posts, and posts the credentials in the body", async () => {
    const fetched = exchange(json(201, SESSION));
    vi.stubGlobal("fetch", fetched);

    const session = await login("ryan", "correct horse");

    expect(session).toEqual(SESSION.data);
    expect(String(fetched.mock.calls[0]?.[0])).toContain("/v1/session/challenge");
    expect(String(fetched.mock.calls[1]?.[0])).toBe("/v1/session");
    const init = initOf(fetched, 1);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      username: "ryan",
      password: "correct horse",
    });
  });

  it("drops the token after login, because the server deletes the cookie it bound to", async () => {
    vi.stubGlobal("fetch", exchange(json(201, SESSION)));

    await login("ryan", "correct horse");

    expect(authHeaders("POST")).toEqual({});
  });

  it("states same-origin credentials on every call rather than inheriting a default", async () => {
    const fetched = exchange(json(201, SESSION), json(200, ENVELOPE));
    vi.stubGlobal("fetch", fetched);

    await login("ryan", "correct horse");
    await getEnvelope("/v1/wells");

    expect(fetched.mock.calls).toHaveLength(3);
    for (let index = 0; index < fetched.mock.calls.length; index += 1) {
      expect(initOf(fetched, index).credentials).toBe("same-origin");
    }
  });

  it("resolves whoami out of the envelope, not out of the browser", async () => {
    vi.stubGlobal("fetch", responds(200, SESSION));

    expect(await whoami()).toEqual(SESSION.data);
  });

  it("raises the uniform refusal without inventing a detail for it", async () => {
    vi.stubGlobal(
      "fetch",
      exchange(json(403, { type: "/v1/errors/unauthenticated", title: "Forbidden", status: 403 })),
    );

    const error = await login("ryan", "wrong").catch((thrown: unknown) => thrown);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as InstanceType<typeof ApiError>).code).toBe("unauthenticated");
    expect((error as InstanceType<typeof ApiError>).problem.detail).toBeUndefined();
  });

  it("re-challenges once when a write is refused for a stale token, then gives up", async () => {
    const forbidden = { type: "/v1/errors/forbidden", title: "Forbidden", status: 403 };
    const fetched = exchange(json(403, forbidden), json(403, forbidden));
    vi.stubGlobal("fetch", fetched);

    await expect(logout()).rejects.toBeInstanceOf(ApiError);

    const posts = fetched.mock.calls.filter((call) => String(call[0]) === "/v1/session");
    const challenges = fetched.mock.calls.filter((call) => String(call[0]).includes("challenge"));
    expect(posts).toHaveLength(2);
    expect(challenges).toHaveLength(2);
  });
});

describe("a response can report itself, so the API pane can quote it (SB-08 §4.4)", () => {
  it("fills the out-parameter with the status, the headers and the elapsed milliseconds", async () => {
    vi.stubGlobal("fetch", responds(200, ENVELOPE, { "X-Glasswell-Vintage": "2026-08-01" }));
    const meta: { out?: ResponseMeta } = {};

    const envelope = await getEnvelope<{ api10: string }>("/v1/wells", {}, undefined, meta);

    expect(envelope).toEqual(ENVELOPE);
    expect(meta.out?.status).toBe(200);
    expect(meta.out?.headers.get("x-glasswell-vintage")).toBe("2026-08-01");
    expect(Number.isFinite(meta.out?.elapsed_ms)).toBe(true);
    expect(meta.out?.elapsed_ms).toBeGreaterThanOrEqual(0);
  });

  it("returns the same envelope when nobody asks, so every existing call site is unchanged", async () => {
    const fetchSpy = responds(200, ENVELOPE);
    vi.stubGlobal("fetch", fetchSpy);

    expect(await getEnvelope("/v1/wells")).toEqual(ENVELOPE);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  // §4.7: a failed request keeps its REQUEST block, so it has to keep its status and its timing.
  it("fills the out-parameter before it throws, so a failure is still quotable", async () => {
    vi.stubGlobal(
      "fetch",
      responds(404, { type: "/v1/problems/not_found", title: "Not found", status: 404 }),
    );
    const meta: { out?: ResponseMeta } = {};

    await expect(getEnvelope("/v1/wells/0000000000", {}, undefined, meta)).rejects.toBeInstanceOf(
      ApiError,
    );

    expect(meta.out?.status).toBe(404);
    expect(Number.isFinite(meta.out?.elapsed_ms)).toBe(true);
  });
});
