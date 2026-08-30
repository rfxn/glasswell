// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loginPanel } from "./login.ts";

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

const onSignedIn = vi.fn();

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

/** Answers the challenge, then whatever the login attempt is supposed to meet. */
function serve(outcome: Response | (() => Response)): ReturnType<typeof vi.fn> {
  return vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
    if (String(input).includes("/v1/session/challenge")) {
      return Promise.resolve(json(200, CHALLENGE));
    }
    return Promise.resolve(typeof outcome === "function" ? outcome() : outcome.clone());
  });
}

function mount(reason: "required" | "expired" = "required"): HTMLElement {
  const panel = loginPanel({ reason, onSignedIn });
  document.body.appendChild(panel);
  return panel;
}

function fill(panel: HTMLElement, username: string, password: string): SubmitEvent {
  (panel.querySelector("#gw-login-user") as HTMLInputElement).value = username;
  (panel.querySelector("#gw-login-pass") as HTMLInputElement).value = password;
  const event = new SubmitEvent("submit", { bubbles: true, cancelable: true });
  panel.querySelector("form")?.dispatchEvent(event);
  return event;
}

function note(panel: HTMLElement): string {
  return panel.querySelector("#gw-login-note")?.textContent ?? "";
}

beforeEach(() => {
  document.body.innerHTML = "";
  onSignedIn.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the login panel is the only credential surface the app has", () => {
  it("offers a username and a password field a password manager can read", () => {
    const panel = mount();
    const username = panel.querySelector("#gw-login-user") as HTMLInputElement;
    const password = panel.querySelector("#gw-login-pass") as HTMLInputElement;

    expect(username.autocomplete).toBe("username");
    expect(password.type).toBe("password");
    expect(password.autocomplete).toBe("current-password");
    expect(panel.querySelector("button[type='submit']")).toBeTruthy();
  });

  it("carries the dialog semantics the overlay wiring focuses against", () => {
    const panel = mount();

    expect(panel.getAttribute("role")).toBe("dialog");
    expect(panel.getAttribute("aria-modal")).toBe("true");
    expect(panel.getAttribute("aria-labelledby")).toBe("gw-login-title");
    expect(panel.querySelector("#gw-login-title")?.getAttribute("tabindex")).toBe("-1");
  });

  // The app's own CSP ships `form-action 'none'`, so a native form POST is blocked by our
  // own policy. The form exists for password managers; fetch is what actually submits.
  it("names no action and cancels the native submit", () => {
    vi.stubGlobal("fetch", serve(json(201, SESSION)));
    const panel = mount();

    const event = fill(panel, "ryan", "correct horse");

    expect(panel.querySelector("form")?.hasAttribute("action")).toBe(false);
    expect(event.defaultPrevented).toBe(true);
  });

  it("distinguishes a first sign-in from a session that ended", () => {
    expect(mount("required").textContent).toContain("serves nothing until you sign in");
    document.body.innerHTML = "";
    expect(mount("expired").textContent).toContain("has ended");
  });

  it("hands the session back and clears the password field on success", async () => {
    vi.stubGlobal("fetch", serve(json(201, SESSION)));
    const panel = mount();

    fill(panel, "ryan", "correct horse");

    await vi.waitFor(() => expect(onSignedIn).toHaveBeenCalledOnce());
    expect(onSignedIn.mock.calls[0]?.[0]).toMatchObject({ username: "ryan", kind: "user" });
    expect((panel.querySelector("#gw-login-pass") as HTMLInputElement).value).toBe("");
  });

  it("posts the credentials as a body, never as a query string", async () => {
    const fetched = serve(json(201, SESSION));
    vi.stubGlobal("fetch", fetched);
    const panel = mount();

    fill(panel, "ryan", "correct horse");

    await vi.waitFor(() => expect(onSignedIn).toHaveBeenCalledOnce());
    const calls = fetched.mock.calls as [string, RequestInit][];
    const [url, init] = calls[calls.length - 1] as [string, RequestInit];
    expect(url).toBe("/v1/session");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect((init.headers as Record<string, string>)["X-Glasswell-CSRF"]).toBe("tok");
    expect(JSON.parse(init.body as string)).toEqual({
      username: "ryan",
      password: "correct horse",
    });
  });
});

describe("a refusal says the same thing however it was earned", () => {
  const REFUSAL = { type: "/v1/errors/unauthenticated", title: "Forbidden", status: 403 };

  it("names neither the field nor the account, because that would enumerate", async () => {
    vi.stubGlobal("fetch", serve(() => json(403, REFUSAL)));
    const panel = mount();

    fill(panel, "nobody", "wrong");

    await vi.waitFor(() => expect(note(panel)).toContain("not accepted"));
    // The pair is refused, never one half of it: "unknown user", "wrong password", "disabled"
    // and "locked" each answer a question the server deliberately refuses to answer.
    expect(note(panel)).not.toMatch(
      /unknown|no such|not found|incorrect|wrong|disabled|locked|does not exist/i,
    );
  });

  it("gives an unknown account and a wrong password the same sentence", async () => {
    vi.stubGlobal("fetch", serve(() => json(403, REFUSAL)));
    const first = mount();
    fill(first, "nobody", "wrong");
    await vi.waitFor(() => expect(note(first)).not.toBe(""));

    document.body.innerHTML = "";
    const second = mount();
    fill(second, "ryan", "wrong");
    await vi.waitFor(() => expect(note(second)).not.toBe(""));

    expect(note(second)).toBe(note(first));
  });

  it("asks a throttled reader to wait without saying which limit fired", async () => {
    vi.stubGlobal(
      "fetch",
      serve(() =>
        json(
          429,
          { type: "/v1/errors/rate_limited", title: "Too many requests", status: 429 },
          { "retry-after": "37" },
        ),
      ),
    );
    const panel = mount();

    fill(panel, "ryan", "correct horse");

    await vi.waitFor(() => expect(note(panel)).toContain("Wait a little"));
    expect(note(panel)).not.toContain("37");
    expect(note(panel)).not.toMatch(/address|account|ip\b/i);
  });

  it("keeps the password out of the DOM whatever the outcome", async () => {
    vi.stubGlobal("fetch", serve(() => json(403, REFUSAL)));
    const panel = mount();

    fill(panel, "ryan", "correct horse");

    await vi.waitFor(() => expect(note(panel)).toContain("not accepted"));
    expect(panel.innerHTML).not.toContain("correct horse");
  });

  it("re-enables the button, so a failed attempt is not a dead panel", async () => {
    vi.stubGlobal("fetch", serve(() => json(403, REFUSAL)));
    const panel = mount();
    const submit = panel.querySelector("button[type='submit']") as HTMLButtonElement;

    fill(panel, "ryan", "wrong");

    await vi.waitFor(() => expect(submit.disabled).toBe(false));
  });

  it("says the service is unreachable rather than blaming the credentials", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("network"))));
    const panel = mount();

    fill(panel, "ryan", "correct horse");

    await vi.waitFor(() => expect(note(panel)).toContain("could not be reached"));
  });
});
