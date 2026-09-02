// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SessionRecord, UserRecord } from "../api/client.ts";
import { clearSession, seedSession } from "../test/session.ts";
import { accountsSection, loadAccounts } from "./section.ts";

const OWNER: UserRecord = {
  user_id: "usr_owner",
  username: "ryan",
  role: "owner",
  state: "active",
  created_at: "2026-08-01T10:00:00Z",
  created_by: "console",
  password_changed_at: "2026-08-01T10:00:00Z",
  last_login_at: "2026-09-01T09:30:00Z",
  disabled_at: null,
  disabled_by: null,
  sessions_live: 2,
};

const VIEWER: UserRecord = {
  ...OWNER,
  user_id: "usr_viewer",
  username: "reader",
  role: "viewer",
  sessions_live: 0,
  last_login_at: null,
};

const DISABLED: UserRecord = {
  ...VIEWER,
  user_id: "usr_gone",
  username: "former",
  state: "disabled",
  disabled_at: "2026-08-30T12:00:00Z",
  disabled_by: "user:usr_owner",
};

const SESSION: SessionRecord = {
  session_id: "ses_live",
  user_id: "usr_owner",
  username: "ryan",
  role: "owner",
  state: "active",
  created_at: "2026-09-01T09:30:00Z",
  last_seen_at: "2026-09-01T09:45:00Z",
  expires_at: "2026-09-01T21:45:00Z",
  absolute_expires_at: "2026-09-08T09:30:00Z",
  revoked_at: null,
  revoked_reason: null,
  user_agent_family: "Chrome on macOS",
  address_class: "lan",
};

const MINTED = "a-43-character-minted-password-nobody-typed";

let host: HTMLElement;

function envelope(data: unknown, warnings: unknown[] = []): Response {
  return new Response(JSON.stringify({ data, meta: { warnings }, links: {} }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function problem(status: number, body: Record<string, unknown>): Response {
  return new Response(JSON.stringify({ type: "/v1/errors/x", title: "Refused", status, ...body }), {
    status,
    statusText: "Refused",
    headers: { "content-type": "application/problem+json" },
  });
}

/** The collections both routes answer, so a rerender after an action has something to read. */
function collections(users: UserRecord[] = [OWNER, VIEWER], sessions: SessionRecord[] = [SESSION]) {
  return (input: string): Response => {
    if (input.includes("/v1/users")) return envelope(users);
    if (input.includes("/v1/sessions")) return envelope(sessions);
    if (input.includes("/v1/session/challenge")) {
      return envelope({ csrf_token: "token", expires_in: 900 });
    }
    throw new Error(`unexpected request ${input}`);
  };
}

function mount(role: string | null): HTMLElement {
  const section = accountsSection(role);
  if (section) host.append(section);
  return section as HTMLElement;
}

async function settle(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

beforeEach(() => {
  document.body.innerHTML = '<div id="host"></div>';
  host = document.getElementById("host") as HTMLElement;
  seedSession();
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearSession();
});

describe("who the section renders for", () => {
  it("renders for an owner", async () => {
    vi.stubGlobal("fetch", (input: string) => Promise.resolve(collections()(input)));
    const section = mount("owner");

    await loadAccounts(section);

    expect(section.querySelector("h2")?.textContent).toBe("Accounts");
    expect(section.id).toBe("accounts");
    expect([...section.querySelectorAll("tbody tr")].length).toBe(3);
  });

  it("renders nothing for a viewer and nothing for anonymous", () => {
    expect(accountsSection("viewer")).toBeNull();
    expect(accountsSection(null)).toBeNull();
    expect(accountsSection(undefined)).toBeNull();
  });

  it("names the four seeded terms rather than underlining every common word", async () => {
    vi.stubGlobal("fetch", (input: string) => Promise.resolve(collections()(input)));
    const section = mount("owner");

    await loadAccounts(section);

    const terms = [...section.querySelectorAll("gw-term")].map((term) =>
      term.getAttribute("term-id"),
    );
    expect(new Set(terms)).toEqual(new Set(["gt_role", "gt_session", "gt_owner"]));
  });
});

describe("the two collections", () => {
  it("states each empty slot in the fewest words that stay true", async () => {
    vi.stubGlobal("fetch", (input: string) => Promise.resolve(collections([], [])(input)));
    const section = mount("owner");

    await loadAccounts(section);

    expect([...section.querySelectorAll(".gw-empty")].map((note) => note.textContent)).toEqual([
      "No accounts yet.",
      "No sessions.",
    ]);
  });

  it("renders a session's client and a class rather than an address", async () => {
    vi.stubGlobal("fetch", (input: string) => Promise.resolve(collections()(input)));
    const section = mount("owner");

    await loadAccounts(section);

    const row = section.querySelector('[data-session="ses_live"]') as HTMLElement;
    expect(row.textContent).toContain("Chrome on macOS");
    expect(row.textContent).toContain("LAN");
    expect(section.innerHTML).not.toContain("198.51.100");
  });

  it("renders a refusal on the list itself when the reader may not read it", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve(problem(403, { detail: "this operation is owner scope" })),
    );
    const section = mount("owner");

    await loadAccounts(section);

    expect(section.querySelector(".gw-accounts-refusal-line")?.textContent).toBe(
      "this operation is owner scope",
    );
  });
});

describe("a refusal reaches the screen in the server's own words", () => {
  it("renders the 422 detail verbatim and the field it named", async () => {
    const base = collections();
    vi.stubGlobal("fetch", (input: string, init?: RequestInit) => {
      if (init?.method === "PATCH") {
        return Promise.resolve(
          problem(422, {
            detail: "that account is not disabled",
            errors: [{ pointer: "/state", code: "not_disabled" }],
          }),
        );
      }
      return Promise.resolve(base(input));
    });
    const section = mount("owner");
    await loadAccounts(section);

    const select = section.querySelector(".gw-accounts-role") as HTMLSelectElement;
    select.value = "viewer";
    select.dispatchEvent(new Event("change"));
    await settle();

    expect(section.querySelector(".gw-accounts-refusal-line")?.textContent).toBe(
      "that account is not disabled",
    );
    expect(section.querySelector(".gw-accounts-refusal-fields")?.textContent).toContain("/state");
  });

  it("prints no field list when the refusal named none", async () => {
    const base = collections();
    vi.stubGlobal("fetch", (input: string, init?: RequestInit) => {
      if (init?.method === "PATCH") {
        return Promise.resolve(problem(422, { detail: "no fields here", errors: [] }));
      }
      return Promise.resolve(base(input));
    });
    const section = mount("owner");
    await loadAccounts(section);

    const select = section.querySelector(".gw-accounts-role") as HTMLSelectElement;
    select.value = "viewer";
    select.dispatchEvent(new Event("change"));
    await settle();

    expect(section.querySelector(".gw-accounts-refusal-line")?.textContent).toBe("no fields here");
    expect(section.querySelector(".gw-accounts-refusal-fields")).toBeNull();
  });
});

describe("nothing ends until the reader says so", () => {
  it("asks before it disables, and sends nothing while the question stands", async () => {
    const fetch = vi.fn((input: string) => Promise.resolve(collections()(input)));
    vi.stubGlobal("fetch", fetch);
    const section = mount("owner");
    await loadAccounts(section);
    const before = fetch.mock.calls.length;

    const disable = [...section.querySelectorAll("button")].find(
      (button) => button.textContent === "Disable",
    ) as HTMLButtonElement;
    disable.click();

    const dialog = section.querySelector('[role="alertdialog"]') as HTMLElement;
    expect(dialog.getAttribute("aria-label")).toBe("Disable ryan? Their sessions end now.");
    expect(fetch.mock.calls.length).toBe(before);

    (section.querySelector(".gw-accounts-confirm-cancel") as HTMLButtonElement).click();
    expect(section.querySelector('[role="alertdialog"]')).toBeNull();
    expect(fetch.mock.calls.length).toBe(before);
  });

  it("sends the delete once the reader confirms it", async () => {
    const base = collections();
    const fetch = vi.fn((input: string, init?: RequestInit) => Promise.resolve(
      init?.method === "DELETE" ? envelope({ ...OWNER, state: "disabled" }) : base(input),
    ));
    vi.stubGlobal("fetch", fetch);
    const section = mount("owner");
    await loadAccounts(section);

    const disable = [...section.querySelectorAll("button")].find(
      (button) => button.textContent === "Disable",
    ) as HTMLButtonElement;
    disable.click();
    (section.querySelector(".gw-accounts-confirm-go") as HTMLButtonElement).click();
    await settle();

    const deletes = fetch.mock.calls.filter(([, init]) => (init as RequestInit)?.method === "DELETE");
    expect(deletes).toHaveLength(1);
    expect(String(deletes[0]?.[0])).toContain("/v1/users/usr_owner");
  });

  it("re-enables without a question, because nothing ends", async () => {
    const base = collections([OWNER, DISABLED]);
    const fetch = vi.fn((input: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "PATCH" ? envelope({ ...DISABLED, state: "active" }) : base(input)),
    );
    vi.stubGlobal("fetch", fetch);
    const section = mount("owner");
    await loadAccounts(section);

    const enable = [...section.querySelectorAll("button")].find(
      (button) => button.textContent === "Enable",
    ) as HTMLButtonElement;
    enable.click();
    await settle();

    expect(section.querySelector('[role="alertdialog"]')).toBeNull();
    const patches = fetch.mock.calls.filter(([, init]) => (init as RequestInit)?.method === "PATCH");
    expect(patches).toHaveLength(1);
    expect(String(patches[0]?.[1]?.body)).toBe(JSON.stringify({ state: "active" }));
  });

  it("asks the session question in the sessions list's own words", async () => {
    vi.stubGlobal("fetch", (input: string) => Promise.resolve(collections()(input)));
    const section = mount("owner");
    await loadAccounts(section);

    const revoke = [...section.querySelectorAll("button")].find(
      (button) => button.textContent === "Revoke",
    ) as HTMLButtonElement;
    revoke.click();

    expect(section.querySelector('[role="alertdialog"]')?.getAttribute("aria-label")).toBe(
      "Revoke this session? They sign in again.",
    );
  });
});

describe("the password is shown once and then it is gone", () => {
  async function create(section: HTMLElement): Promise<void> {
    const base = collections();
    vi.stubGlobal("fetch", (input: string, init?: RequestInit) => {
      if (init?.method === "POST" && input.includes("/v1/users")) {
        return Promise.resolve(
          envelope({ ...VIEWER, password: MINTED }, [
            { code: "password_shown_once", detail: "Copy it now; it is not stored." },
          ]),
        );
      }
      return Promise.resolve(base(input));
    });
    await loadAccounts(section);
    (section.querySelector(".gw-accounts-add") as HTMLButtonElement).click();
    (section.querySelector("#gw-accounts-username") as HTMLInputElement).value = "newcomer";
    section.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    await settle();
  }

  it("renders the minted password once, behind the harness hook, with the server's warning", async () => {
    const section = mount("owner");

    await create(section);

    const secret = section.querySelector("[data-gw-secret]") as HTMLElement;
    expect(secret.textContent).toBe(MINTED);
    expect(section.querySelector(".gw-accounts-secret-line")?.textContent).toBe(
      "Copy this password. It is not shown again.",
    );
    expect(section.querySelector('.gw-note[data-code="password_shown_once"]')).not.toBeNull();
  });

  // gate-v076 H-8: the panel says the password is not shown again, so a Copy that quietly does
  // nothing costs the reader the credential. The LAN host is plain http, where the clipboard
  // API does not exist at all.
  it("says so when there is no clipboard, rather than doing nothing", async () => {
    const original = Object.getOwnPropertyDescriptor(navigator, "clipboard");
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
    try {
      const section = mount("owner");
      await create(section);

      const copy = [...section.querySelectorAll("button")].find(
        (button) => button.textContent === "Copy",
      );
      copy?.click();

      const state = section.querySelector(".gw-accounts-copy-state");
      expect(state?.textContent).toBe("No clipboard on this connection. Select the value above.");
      expect(state?.getAttribute("role")).toBe("status");
    } finally {
      if (original) Object.defineProperty(navigator, "clipboard", original);
    }
  });

  it("says so when the clipboard refuses, rather than only in the console", async () => {
    const original = Object.getOwnPropertyDescriptor(navigator, "clipboard");
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: () => Promise.reject(new Error("denied")) },
      configurable: true,
    });
    try {
      const section = mount("owner");
      await create(section);

      const copy = [...section.querySelectorAll("button")].find(
        (button) => button.textContent === "Copy",
      );
      copy?.click();
      await Promise.resolve();
      await Promise.resolve();

      expect(section.querySelector(".gw-accounts-copy-state")?.textContent).toBe(
        "Copy refused. Select the value above.",
      );
    } finally {
      if (original) Object.defineProperty(navigator, "clipboard", original);
    }
  });

  it("never sends the password anywhere: not in a URL, not in a body", async () => {
    const base = collections();
    const fetch = vi.fn((input: string, init?: RequestInit) => {
      if (init?.method === "POST" && input.includes("/v1/users")) {
        return Promise.resolve(
          envelope({ ...VIEWER, password: MINTED }, [{ code: "password_shown_once" }]),
        );
      }
      return Promise.resolve(base(input));
    });
    vi.stubGlobal("fetch", fetch);
    const section = mount("owner");
    await loadAccounts(section);
    (section.querySelector(".gw-accounts-add") as HTMLButtonElement).click();
    (section.querySelector("#gw-accounts-username") as HTMLInputElement).value = "newcomer";
    section.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    await settle();

    expect(section.querySelector("[data-gw-secret]")?.textContent).toBe(MINTED);
    for (const [input, init] of fetch.mock.calls) {
      expect(String(input)).not.toContain(MINTED);
      expect(String((init as RequestInit | undefined)?.body ?? "")).not.toContain(MINTED);
    }
    expect(document.location.href).not.toContain(MINTED);
  });

  it("drops the password out of the document when the panel is dismissed", async () => {
    const section = mount("owner");
    await create(section);

    (
      [...section.querySelectorAll("button")].find(
        (button) => button.textContent === "Dismiss",
      ) as HTMLButtonElement
    ).click();

    expect(section.querySelector("[data-gw-secret]")).toBeNull();
    expect(document.body.innerHTML).not.toContain(MINTED);
  });
});
