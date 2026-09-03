// Coverage for lib.mjs's key handling: the single auth path, the header injection, the
// central redactor and the argv/url guards. Runs with `node --test` — no browser, no deps.
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, test } from "node:test";

import {
  KEY_HEADER,
  authenticate,
  contrastAudit,
  forgetSecrets,
  guardTarget,
  instrumentedPage,
  keyGuard,
  ownerKey,
  redact,
  registerSecret,
} from "./lib.mjs";

const FAKE_KEY = "deadbeef".repeat(8);
const SAVED = {};
const VARS = ["GLASSWELL_KEY_FILE", "GLASSWELL_OWNER_KEY", "GLASSWELL_BASE_URL", "GW_BASE"];

beforeEach(() => {
  for (const name of VARS) {
    SAVED[name] = process.env[name];
    delete process.env[name];
  }
});
afterEach(() => {
  forgetSecrets();
  for (const name of VARS) {
    if (SAVED[name] === undefined) delete process.env[name];
    else process.env[name] = SAVED[name];
  }
});

function fakeBrowser() {
  const seen = { routes: [], handlers: {}, gotos: [], contextOptions: null };
  const page = {
    on(event, fn) {
      seen.handlers[event] = fn;
    },
    async goto(url) {
      seen.gotos.push(url);
    },
  };
  const context = {
    async route(glob, handler) {
      seen.routes.push({ glob, handler });
    },
    async newPage() {
      return page;
    },
  };
  const browser = {
    async newContext(options) {
      seen.contextOptions = options;
      return context;
    },
  };
  return { browser, context, page, seen };
}

function fakeRoute(url, headers = {}) {
  const continued = [];
  return {
    request: () => ({ url: () => url, headers: () => ({ ...headers }) }),
    continue(options) {
      continued.push(options ?? null);
    },
    continued,
  };
}

test("ownerKey reads and trims GLASSWELL_OWNER_KEY", () => {
  process.env.GLASSWELL_OWNER_KEY = `  ${FAKE_KEY}\n`;
  assert.equal(ownerKey(), FAKE_KEY);
});

test("ownerKey reads a key file, which wins over the env var", () => {
  const dir = mkdtempSync(join(tmpdir(), "gw-key-"));
  const path = join(dir, "owner.key");
  writeFileSync(path, `${FAKE_KEY}\n`);
  process.env.GLASSWELL_KEY_FILE = path;
  process.env.GLASSWELL_OWNER_KEY = "not-the-key";
  try {
    assert.equal(ownerKey(), FAKE_KEY);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("ownerKey is null when nothing provides a key", () => {
  assert.equal(ownerKey(), null);
});

test("keyGuard refuses to run with the key visible in process.argv", () => {
  process.env.GLASSWELL_OWNER_KEY = FAKE_KEY;
  process.argv.push(`--key=${FAKE_KEY}`);
  try {
    assert.throws(() => keyGuard(), /process\.argv.*never a script argument/s);
  } finally {
    process.argv.pop();
  }
});

test("keyGuard returns the key when argv is clean", () => {
  process.env.GLASSWELL_OWNER_KEY = FAKE_KEY;
  assert.equal(keyGuard(), FAKE_KEY);
});

test("guardTarget refuses a url carrying the key and passes a clean one through", () => {
  process.env.GLASSWELL_OWNER_KEY = FAKE_KEY;
  assert.throws(
    () => guardTarget(`https://example.test/#key=${FAKE_KEY}`),
    /target url.*never any part of a url/s,
  );
  assert.equal(guardTarget("https://example.test/?well=1"), "https://example.test/?well=1");
});

test("redact strips every occurrence of the key from captured text", () => {
  process.env.GLASSWELL_OWNER_KEY = FAKE_KEY;
  const captured = redact(`error: fetch ${FAKE_KEY} refused; retried with ${FAKE_KEY}`);
  assert.ok(!captured.includes(FAKE_KEY));
  assert.equal(captured.match(/REDACTED/g).length, 2);
});

test("redact is a passthrough when no key is configured", () => {
  assert.equal(redact("plain text"), "plain text");
});

test("redact strips case-mutated keys too", () => {
  process.env.GLASSWELL_OWNER_KEY = FAKE_KEY;
  const upper = FAKE_KEY.toUpperCase();
  const mixed = FAKE_KEY.slice(0, 32) + FAKE_KEY.slice(32).toUpperCase();
  const captured = redact(`saw ${upper} and ${mixed}`);
  assert.ok(!captured.toLowerCase().includes(FAKE_KEY));
  assert.equal(captured.match(/REDACTED/g).length, 2);
});

test("guardTarget refuses a case-mutated key in a url", () => {
  process.env.GLASSWELL_OWNER_KEY = FAKE_KEY;
  assert.throws(
    () => guardTarget(`https://example.test/#key=${FAKE_KEY.toUpperCase()}`),
    /target url/,
  );
});

test("authenticate injects the header on same-origin requests only", async () => {
  process.env.GLASSWELL_OWNER_KEY = FAKE_KEY;
  process.env.GLASSWELL_BASE_URL = "https://example.test";
  const { context, seen } = fakeBrowser();
  await authenticate(context);
  const { handler } = seen.routes[0];

  const same = fakeRoute("https://example.test/v1/wells?limit=1", { accept: "*/*" });
  handler(same);
  assert.equal(same.continued[0].headers[KEY_HEADER.toLowerCase()], FAKE_KEY);
  assert.equal(same.continued[0].headers.accept, "*/*");

  const off = fakeRoute("https://elsewhere.example/asset.js");
  handler(off);
  assert.equal(off.continued[0], null);

  const opaque = fakeRoute("about:blank");
  handler(opaque);
  assert.equal(opaque.continued[0], null);
});

test("authenticate fails loud when no key is available", async () => {
  const { context } = fakeBrowser();
  await assert.rejects(() => authenticate(context), /no owner key/);
});

test("an instrumented page redacts a leaked-shaped key out of captured console output", async () => {
  process.env.GLASSWELL_OWNER_KEY = FAKE_KEY;
  process.env.GLASSWELL_BASE_URL = "https://example.test";
  const { browser, seen } = fakeBrowser();
  const { journal } = await instrumentedPage(browser, {});
  seen.handlers.console({ type: () => "error", text: () => `boom: token ${FAKE_KEY} rejected` });
  seen.handlers.pageerror({ message: `Unhandled: ${FAKE_KEY}` });
  const captured = [...journal.console, ...journal.pageerror].join(" | ");
  assert.ok(!captured.includes(FAKE_KEY));
  assert.ok(captured.includes("REDACTED"));
});

test("an instrumented page refuses to navigate to a url carrying the key", async () => {
  process.env.GLASSWELL_OWNER_KEY = FAKE_KEY;
  process.env.GLASSWELL_BASE_URL = "https://example.test";
  const { browser, seen } = fakeBrowser();
  const { page } = await instrumentedPage(browser, {});
  await assert.rejects(
    () => page.goto(`https://example.test/#key=${FAKE_KEY}`),
    /target url/,
  );
  assert.equal(seen.gotos.length, 0);
  await page.goto("https://example.test/");
  assert.deepEqual(seen.gotos, ["https://example.test/"]);
});

test("an instrumented page journals a same-origin request redirecting off-origin", async () => {
  process.env.GLASSWELL_OWNER_KEY = FAKE_KEY;
  process.env.GLASSWELL_BASE_URL = "https://example.test";
  const { browser, seen } = fakeBrowser();
  const { journal } = await instrumentedPage(browser, {});
  const fakeRequest = (url, prior = null) => ({
    url: () => url,
    redirectedFrom: () => prior,
  });

  seen.handlers.request(
    fakeRequest("https://elsewhere.example/land", fakeRequest("https://example.test/redir")),
  );
  assert.equal(journal.offOriginRedirects.length, 1);
  assert.match(journal.offOriginRedirects[0], /example\.test\/redir -> .*elsewhere\.example/);

  seen.handlers.request(fakeRequest("https://elsewhere.example/direct"));
  seen.handlers.request(
    fakeRequest("https://example.test/two", fakeRequest("https://example.test/one")),
  );
  assert.equal(journal.offOriginRedirects.length, 1);
});

test("auth: false builds a context with no route and no header", async () => {
  process.env.GLASSWELL_OWNER_KEY = FAKE_KEY;
  const { browser, seen } = fakeBrowser();
  await instrumentedPage(browser, { auth: false });
  assert.equal(seen.routes.length, 0);
});

// S-3: a minted password is a credential the harness reads out of the DOM, so the journal, the
// url guard and the argv guard have to treat it exactly as they treat the owner key.
const MINTED = "a-43-character-minted-password-nobody-typed";

test("a registered secret is redacted out of captured text, with no key configured", () => {
  registerSecret(MINTED);

  assert.equal(redact(`the page showed ${MINTED} once`), "the page showed REDACTED once");
});

test("a registered secret is refused in a navigation target", () => {
  registerSecret(MINTED);

  assert.throws(() => guardTarget(`https://example.test/?p=${MINTED}`), /credential/);
  assert.equal(guardTarget("https://example.test/?view=status"), "https://example.test/?view=status");
});

test("a registered secret is refused in argv", () => {
  registerSecret(MINTED);
  const saved = process.argv;
  process.argv = [...saved, `--password=${MINTED}`];

  try {
    assert.throws(() => keyGuard(), /credential/);
  } finally {
    process.argv = saved;
  }
});

test("a value too short to be a credential is not registered, so prose survives", () => {
  registerSecret("owner");

  assert.equal(redact("the owner opened it"), "the owner opened it");
});

test("forgetting the registry restores the passthrough", () => {
  registerSecret(MINTED);
  forgetSecrets();

  assert.equal(redact(MINTED), MINTED);
});


/**
 * gate-v078 N8: `posture.json` reported `legend label 14.87` while the receded rows in the same
 * panel rendered at 2.60:1, because the audit measured `querySelector` — the first, brightest
 * match — and never sampled them. An instrument that stops at the first node reports the best
 * case of whatever it is auditing, which is the opposite of an audit.
 *
 * A page whose `evaluate` really runs the callback against a stub document and
 * `getComputedStyle`, so what is under test is the sampler's own body rather than a paraphrase.
 */
function pageOver(nodes) {
  const document = {
    querySelectorAll: (selector) => nodes.filter((node) => node.selector === selector),
    querySelector: (selector) => nodes.find((node) => node.selector === selector) ?? null,
  };
  const getComputedStyle = (node) => ({
    color: node.colour,
    backgroundColor: node.background ?? "rgba(0, 0, 0, 0)",
    fontSize: "12px",
  });
  return {
    async evaluate(fn, args) {
      const saved = [globalThis.document, globalThis.getComputedStyle];
      globalThis.document = document;
      globalThis.getComputedStyle = getComputedStyle;
      try {
        return fn(args);
      } finally {
        [globalThis.document, globalThis.getComputedStyle] = saved;
      }
    },
  };
}

const PANEL = "rgb(17, 25, 32)";
// The two rows the gate measured in the key at 1600: a full-brightness count and the same
// paint on an out-of-scale row, on the panel's own #111920. Both ratios below are the gate's.
const LEGEND_ROWS = [
  { selector: ".gw-lg-count", colour: "rgb(159, 176, 188)", background: PANEL },
  { selector: ".gw-lg-count", colour: "rgb(81, 92, 102)", background: PANEL },
];

test("contrastAudit reports the worst match rather than the first", async () => {
  const [audited] = await contrastAudit(pageOver(LEGEND_ROWS), [
    ["legend count", [".gw-lg-count"]],
  ]);

  assert.equal(audited.count, 2);
  assert.equal(audited.ratio, 2.6, "the receded row is what an audit has to report");
  assert.equal(audited.best, 7.95, "the bright row is still available, as `best`");
  assert.deepEqual(
    audited.samples.map((sample) => sample.ratio),
    [7.95, 2.6],
  );
});

test("contrastAudit still reports a target nothing in the page matches", async () => {
  const [audited] = await contrastAudit(pageOver(LEGEND_ROWS), [["absent", [".gw-nothing"]]]);

  assert.equal(audited.missing, true);
  assert.deepEqual(audited.tried, [".gw-nothing"]);
});
