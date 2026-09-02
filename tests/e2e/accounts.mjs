// The Accounts gate: the DIR-11 ladder against a branch-local instance, and the round trip the
// section exists for — an owner creates a viewer, that viewer signs in, and the surface tells
// them nothing about anyone else.
//
// It signs in as a real account rather than riding the owner key, because the section reads the
// role off a resolved session and a key-authenticated browser on Status resolves none. The
// account is the throwaway `tests/support/serve_seed_accounts.py` mints on an ephemeral
// database; this gate resets its password to a server-minted value nobody reads before it exits.
//
//   GW_ACCOUNTS_PASSWORD=… GLASSWELL_BASE_URL=http://127.0.0.1:8130 \
//     GLASSWELL_KEY_FILE=/tmp/gw-serve/owner.key node tests/e2e/accounts.mjs
//
// No screenshot is taken while the panel holds a live value: the minted password is registered
// as a secret before it is read, and the node it renders into is substituted before capture.

import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  BREAKPOINTS,
  KEY_HEADER,
  baseUrl,
  chromeExecutable,
  instrumentedPage,
  keyGuard,
  launch,
  redact,
  registerSecret,
} from "./lib.mjs";

const REQUIRE = process.env.GLASSWELL_REQUIRE_E2E === "1";
const BASE = baseUrl();
const OWNER = process.env.GW_ACCOUNTS_USER ?? "gate-owner";
const PASSWORD = process.env.GW_ACCOUNTS_PASSWORD ?? "";
const SHOTS =
  process.env.GW_SHOTS ?? fileURLToPath(new URL("../../work-output/accounts-shots/", import.meta.url));
// The three rungs this section is judged at: the desktop it was designed on, the laptop the ask
// named as its condition, and the phone the ladder makes a first-class rung.
const LADDER = BREAKPOINTS.filter(({ width }) => [1600, 1024, 390].includes(width));
const MASK = "•".repeat(43);
// The four the backend seeds `highlightable: false`. Anything else in this section would mean
// the app-wide highlighter reached a surface it is not run on.
const SEEDED_TERMS = new Set(["gt_role", "gt_session", "gt_owner", "gt_viewer"]);
const CREATED = `gate-made-${Date.now().toString(36)}`;

let passed = 0;
let failed = 0;
const ok = (label) => {
  passed += 1;
  console.log(`  ok   ${String(passed + failed).padStart(2)} ${label}`);
};
const bad = (label, detail) => {
  failed += 1;
  console.log(`  FAIL ${String(passed + failed).padStart(2)} ${label} — ${redact(detail)}`);
};
const assert = (condition, label, detail) => (condition ? ok(label) : bad(label, detail));

function unavailable(reason) {
  if (REQUIRE) {
    console.error(`GLASSWELL_REQUIRE_E2E is set but ${reason}`);
    process.exit(1);
  }
  console.log(`accounts skipped: ${reason}`);
  process.exit(0);
}

try {
  await import("playwright-core");
} catch {
  unavailable("playwright-core is not installed (npm --prefix tests/e2e install)");
}
if (!chromeExecutable()) unavailable("no chromium build found (set GW_CHROME)");
if (!PASSWORD) unavailable("GW_ACCOUNTS_PASSWORD is unset (this gate signs in as an account)");

/** Sign in the way a reader does: the login panel, over the app's own client. */
async function signIn(page, username, password) {
  await page.goto(`${BASE}/?view=status`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#gw-login-user", { timeout: 20000 });
  await page.fill("#gw-login-user", username);
  await page.fill("#gw-login-pass", password);
  await page.click(".gw-login-submit");
  // Hidden, not detached: main.ts hides the host rather than tearing the panel down, so a
  // detach wait times out on a login that worked.
  await page.waitForSelector("#gw-login-user", { state: "hidden", timeout: 20000 });
}

/** The Status surface scrolls inside `#gw-status-page`, so `scrollIntoView` is the only way. */
async function scrollTo(page, selector) {
  await page.evaluate((target) => {
    document.querySelector(target)?.scrollIntoView({ block: "start" });
  }, selector);
  await page.waitForTimeout(250);
}

async function accountsReady(page) {
  await page.waitForSelector("#accounts .gw-accounts-users", { timeout: 20000 });
}

/** Substitutes the shown-once value, so nothing captures a credential. Returns what it was. */
async function maskSecret(page) {
  return page.evaluate((mask) => {
    const node = document.querySelector("[data-gw-secret]");
    if (!node) return null;
    const value = node.textContent;
    node.textContent = mask;
    return value;
  }, MASK);
}

mkdirSync(SHOTS, { recursive: true });
const browser = await launch();
const key = keyGuard();
let createdId = null;
let mintedRead = false;

try {
  for (const viewport of LADDER) {
    const at = `${viewport.width}×${viewport.height}`;
    // auth: false — this browser is a signed-in reader, not a key holder. The key would
    // otherwise answer for it and the gate would prove nothing about the session path.
    const { context, page, journal } = await instrumentedPage(browser, { viewport, auth: false });
    await signIn(page, OWNER, PASSWORD);
    await accountsReady(page);
    // The refusals before this line are the signed-out first paint: this instance serves no
    // anonymous reads, so /v1, /v1/status and the glossary are all 403 until the panel is
    // answered. What this gate judges is the surface a signed-in owner sees.
    journal.nonok.length = 0;
    journal.console.length = 0;

    const seen = await page.evaluate(() => {
      const section = document.querySelector("#accounts");
      const box = section?.getBoundingClientRect();
      const overflow = [...document.querySelectorAll("#accounts .gw-status-table-wrap")].map(
        (wrap) => wrap.scrollWidth > wrap.clientWidth,
      );
      return {
        title: section?.querySelector("h2")?.textContent ?? null,
        width: box ? Math.round(box.width) : 0,
        clipped: box ? Math.round(box.right) > document.documentElement.clientWidth + 1 : false,
        users: document.querySelectorAll("#accounts .gw-accounts-users tbody tr").length,
        sessions: document.querySelectorAll("#accounts .gw-accounts-sessions tbody tr").length,
        terms: [...document.querySelectorAll("#accounts gw-term")].map((term) =>
          term.getAttribute("term-id"),
        ),
        addresses: /\b\d{1,3}(\.\d{1,3}){3}\b/.test(section?.textContent ?? ""),
        overflow,
        // gate-v076 D2: `clipped` measures the *section* box, and the section is as wide as the
        // viewport whatever its tables do — so a Revoke button 161 px past the right edge sat
        // inside a section that measured clean. Every action is measured on its own now, and
        // hit-tested, because a control can be inside the viewport and still under a sticky
        // neighbour.
        controls: [...document.querySelectorAll("#accounts .gw-accounts-action")].map((button) => {
          const box = button.getBoundingClientRect();
          const edge = document.documentElement.clientWidth;
          const onScreenVertically = box.bottom > 0 && box.top < window.innerHeight;
          const topmost = onScreenVertically
            ? document.elementFromPoint(
                Math.round(box.left + box.width / 2),
                Math.round(box.top + box.height / 2),
              )
            : null;
          return {
            label: (button.textContent ?? "").trim(),
            left: Math.round(box.left),
            right: Math.round(box.right),
            past: Math.round(Math.max(0, box.right - edge)),
            outside: box.right > edge + 1 || box.left < -1,
            covered: onScreenVertically && !(topmost === button || button.contains(topmost)),
          };
        }),
        // gate-v076 N3: the pinned action column is opaque, so anything sliding under it is
        // painted over — at 390 the last ~5 px of a username, chopped mid-stroke. The DOM says
        // the text is fully laid out, so no scrollWidth assertion can see it; only a hit-test
        // on the last *painted* glyph can. With an ellipsis the logical last character is
        // clipped out of the box entirely, so its own rect says nothing about what is visible.
        names: [...document.querySelectorAll("#accounts .gw-accounts-name")].map((name) => {
          const box = name.getBoundingClientRect();
          const painted = Math.min(box.right, box.left + name.clientWidth);
          const cell = name.closest("th");
          const action = cell?.parentElement?.querySelector("td:last-child") ?? null;
          const onScreen = box.bottom > 0 && box.top < window.innerHeight;
          const topmost = onScreen
            ? document.elementFromPoint(Math.round(painted - 1), Math.round(box.top + box.height / 2))
            : null;
          return {
            text: (name.textContent ?? "").trim(),
            truncated: name.scrollWidth > name.clientWidth + 0.5,
            paintedRight: Math.round(painted),
            actionLeft: action ? Math.round(action.getBoundingClientRect().left) : null,
            occluded: onScreen && action !== null && action.contains(topmost),
            titled: name.getAttribute("title") === (name.textContent ?? "").trim(),
          };
        }),
        modes: document.querySelectorAll(".gw-mode-btn").length,
      };
    });

    assert(seen.title === "Accounts", `${at} the section is titled Accounts`, String(seen.title));
    assert(seen.users >= 3, `${at} the users list has rows to judge`, String(seen.users));
    assert(seen.sessions >= 1, `${at} the sessions list has rows to judge`, String(seen.sessions));
    assert(!seen.clipped, `${at} the section is not clipped by the viewport`, JSON.stringify(seen));
    // The section's only destructive control must be reachable without a horizontal swipe.
    const unreachable = seen.controls.filter((control) => control.outside);
    assert(
      seen.controls.length > 0 && unreachable.length === 0,
      `${at} every account control is inside the viewport`,
      seen.controls.length === 0
        ? "no .gw-accounts-action was found, so this assertion proves nothing"
        : unreachable.map((c) => `${c.label} ${c.past}px past the edge`).join(", "),
    );
    const painted = seen.names.filter((name) => name.occluded);
    assert(
      seen.names.length > 0 && painted.length === 0,
      `${at} no account name is painted over by the pinned action column`,
      seen.names.length === 0
        ? "no .gw-accounts-name was found, so this assertion proves nothing"
        : painted
            .map((n) => `${n.text} ends at ${n.paintedRight}, action column at ${n.actionLeft}`)
            .join(", "),
    );
    // A name held short of that column has to say so, or it is the same silent loss with a
    // tidier edge.
    const untitled = seen.names.filter((name) => name.truncated && !name.titled);
    assert(
      untitled.length === 0,
      `${at} a shortened name still carries the whole one`,
      untitled.map((n) => n.text).join(", "),
    );

    const buried = seen.controls.filter((control) => control.covered);
    assert(
      buried.length === 0,
      `${at} no account control is painted under something else`,
      buried.map((c) => c.label).join(", "),
    );
    assert(
      seen.modes === 3,
      `${at} the header still carries three modes, not a fourth`,
      String(seen.modes),
    );
    assert(
      seen.terms.length > 0 && seen.terms.every((id) => SEEDED_TERMS.has(id)),
      `${at} only the four seeded terms are named, and by hand`,
      JSON.stringify(seen.terms),
    );
    assert(
      !seen.addresses,
      `${at} no session row states a client address`,
      String(seen.addresses),
    );
    // Viewport shots, scrolled: `#gw-status-page` is its own scroll container, so `fullPage`
    // photographs the first screen and an element shot of a tall section is drawn under the
    // fixed chrome. What a reader sees is a viewport with the section scrolled into it.
    await scrollTo(page, "#accounts");
    await page.screenshot({ path: `${SHOTS}/accounts-list-${viewport.width}.png` });
    await scrollTo(page, "#accounts .gw-accounts-sessions");
    await page.screenshot({ path: `${SHOTS}/accounts-sessions-${viewport.width}.png` });

    // The create round trip, once, at the widest rung: the account it makes is the one the
    // viewer leg signs in with, and every rung after this photographs the reveal it produced.
    if (!mintedRead) {
      await page.click(".gw-accounts-add");
      await page.fill("#gw-accounts-username", CREATED);
      await page.selectOption("#gw-accounts-role", "viewer");
      await page.click(".gw-accounts-submit");
      await page.waitForSelector("[data-gw-secret]", { timeout: 20000 });
      // Registered before it is read: a secret registered afterwards is one the journal may
      // already carry.
      const minted = await page.evaluate(() => document.querySelector("[data-gw-secret]").textContent);
      registerSecret(minted);
      process.env.GW_ACCOUNTS_MINTED = minted;
      mintedRead = true;
      assert(
        typeof minted === "string" && minted.length >= 40,
        `${at} the minted password is shown once, in the response that minted it`,
        String(minted?.length),
      );
      const warned = await page.evaluate(
        () => document.querySelector('#accounts .gw-note[data-code="password_shown_once"]') !== null,
      );
      assert(warned, `${at} the server's shown-once warning renders beside it`, "no warning note");
    } else {
      await page.click(".gw-accounts-add");
      await page.fill("#gw-accounts-username", `${CREATED}-${viewport.width}`);
      await page.click(".gw-accounts-submit");
      await page.waitForSelector("[data-gw-secret]", { timeout: 20000 });
      registerSecret(
        await page.evaluate(() => document.querySelector("[data-gw-secret]").textContent),
      );
    }

    const before = await maskSecret(page);
    const masked = await page.evaluate(() => document.querySelector("[data-gw-secret]").textContent);
    assert(
      masked === MASK && before !== MASK,
      `${at} the panel is substituted before anything captures it`,
      `masked=${masked === MASK}`,
    );
    await page
      .locator("#accounts .gw-accounts-secret")
      .screenshot({ path: `${SHOTS}/accounts-create-${viewport.width}.png` });

    assert(journal.pageerror.length === 0, `${at} no page errors`, journal.pageerror.join(" | "));
    assert(
      journal.console.length === 0,
      `${at} no console warnings or errors`,
      journal.console.join(" | "),
    );
    assert(
      journal.nonok.length === 0,
      `${at} no failed network responses`,
      journal.nonok.join(" | "),
    );
    await context.close();
  }

  // The round trip: the account the owner made can sign in, and sees none of this.
  const minted = process.env.GW_ACCOUNTS_MINTED ?? "";
  const { context, page, journal } = await instrumentedPage(browser, {
    viewport: { width: 1600, height: 1000 },
    auth: false,
  });
  await signIn(page, CREATED, minted);
  await page.waitForSelector("#gw-status-page .gw-status-page", { timeout: 20000 });
  const asViewer = await page.evaluate(async () => {
    const users = await fetch("/v1/users", { headers: { Accept: "application/json" } });
    const sessions = await fetch("/v1/sessions", { headers: { Accept: "application/json" } });
    return {
      section: document.querySelector("#accounts") !== null,
      users: users.status,
      sessions: sessions.status,
    };
  });
  assert(!asViewer.section, "a viewer signing in sees no Accounts section", JSON.stringify(asViewer));
  assert(asViewer.users === 403, "a viewer is refused GET /v1/users", String(asViewer.users));
  assert(asViewer.sessions === 403, "a viewer is refused GET /v1/sessions", String(asViewer.sessions));
  assert(journal.pageerror.length === 0, "viewer: no page errors", journal.pageerror.join(" | "));
  await context.close();

  // Teardown, from Node with the key alone: no cookie, so no CSRF, and nothing this gate
  // created keeps a credential. The owner's password becomes one the server minted and nobody
  // read; the account it created is disabled, which revokes its sessions in the same call.
  if (key) {
    const headers = { [KEY_HEADER]: key, Accept: "application/json" };
    const listed = await (await fetch(`${BASE}/v1/users`, { headers })).json();
    const idOf = (name) => listed.data.find((row) => row.username === name)?.user_id ?? null;
    const madeHere = listed.data.filter((row) => row.username.startsWith(CREATED));
    createdId = idOf(CREATED);
    const ownerId = idOf(OWNER);
    // Every account this run made, not only the one the viewer leg used: each rung created one.
    let disabled = null;
    for (const row of madeHere) {
      disabled = await fetch(`${BASE}/v1/users/${row.user_id}`, { method: "DELETE", headers });
      if (disabled.status !== 200) break;
    }
    const rotated = ownerId
      ? await fetch(`${BASE}/v1/users/${ownerId}/password`, {
          method: "POST",
          headers: { ...headers, "Content-Type": "application/json" },
          body: "{}",
        })
      : null;
    assert(
      madeHere.length > 0 && disabled?.status === 200,
      `every account this gate created is disabled (${madeHere.length})`,
      String(disabled?.status),
    );
    assert(
      rotated?.status === 200,
      "the seeded owner's password is replaced by one nobody read",
      String(rotated?.status),
    );
    const after = await (await fetch(`${BASE}/v1/sessions`, { headers })).json();
    const live = after.data.filter((row) => row.state === "active" && row.username === OWNER);
    assert(live.length === 0, "no session the gate opened is still live", JSON.stringify(live.length));
  }
} finally {
  await browser.close();
}

console.log(`\n${passed} passed, ${failed} failed`);
console.log(`shots in ${SHOTS}`);
process.exit(failed === 0 ? 0 : 1);
