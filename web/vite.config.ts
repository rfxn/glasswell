import { execFileSync, execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

import { PUBLIC_ORIGIN_ENV, absolutizeMetaUrls } from "./src/meta/og-url.ts";

const REPO = new URL("../", import.meta.url);

/** No `VERSION` file means no release has been cut from this tree, and the stamp says so. */
const DEV_VERSION = "0.0-dev";
// The odometer: `X.0`, then `X.01`..`X.09`, then `X.10`..`X.99`. scripts/release.py writes it.
const VERSION = /^(?:0|[1-9][0-9]*)\.(?:0|0[1-9]|[1-9][0-9])$/;

/**
 * The rail has to be able to say which bundle it is, and a version it fetches is one it
 * cannot show while the API is down. Read once, here, and inlined as a constant: `dev` when
 * there is no git to ask (a release archive is not a checkout), and a trailing `+` when the
 * tree had uncommitted changes, because a stamp that rounds to the commit is a lie.
 */
function stamp(): { version: string; hash: string; date: string } {
  const git = (args: string): string =>
    execSync(`git ${args}`, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  let hash = "dev";
  try {
    hash = `${git("rev-parse --short HEAD")}${git("status --porcelain") === "" ? "" : "+"}`;
  } catch {
    // Not a checkout, or no git on the build host: the initialiser above is the honest answer.
  }
  let version = DEV_VERSION;
  try {
    const literal = readFileSync(new URL("VERSION", REPO), "utf8").trim();
    if (VERSION.test(literal)) version = literal;
  } catch {
    // Same reasoning: a tree with no VERSION file is honestly a pre-release tree.
  }
  return { version, hash, date: new Date().toISOString().slice(0, 10) };
}

/**
 * `dist/changelog/index.html`, rendered from CHANGELOG.md by scripts/render-changelog.py.
 *
 * A vite plugin rather than a Makefile step, because `npm run build` is what CI's web job and
 * the deploy runbook's "rebuild the frontend" both run. Behind a Make target, both paths would
 * ship a header stamp linking to a 404 and neither would notice. It throws rather than warns
 * for the same reason: a build host with no python3 must fail loudly, not silently omit a page
 * the rail links to on every screen.
 */
function changelogPage(): Plugin {
  return {
    name: "gw-changelog-page",
    apply: "build",
    closeBundle() {
      const script = fileURLToPath(new URL("scripts/render-changelog.py", REPO));
      const out = fileURLToPath(new URL("web/dist/changelog", REPO));
      execFileSync("python3", [script, "--out", out], { stdio: "inherit" });
    },
  };
}

/**
 * `og:image` and `twitter:image` must be absolute to survive an unfurl, and the origin is
 * deployment configuration rather than a literal. Unset — the LAN deployment — leaves the
 * markup exactly as authored.
 */
function absoluteCardUrls(): Plugin {
  return {
    name: "gw-absolute-card-urls",
    transformIndexHtml: {
      order: "post",
      handler: (html) => absolutizeMetaUrls(html, process.env[PUBLIC_ORIGIN_ENV]),
    },
  };
}

// Tiles moved under /v1 (C11), so one proxy rule covers the API and the tile origin.
export default defineConfig({
  base: "/",
  plugins: [changelogPage(), absoluteCardUrls()],
  define: { __GW_BUILD__: JSON.stringify(stamp()) },
  // No source map: the bundle is served by StaticFiles, and this source is proprietary (M-6).
  // `npm run dev` is unaffected — esbuild maps the dev server's modules regardless.
  build: { outDir: "dist", target: "es2022", sourcemap: false },
  server: {
    proxy: {
      "/v1": { target: "http://127.0.0.1:8000", changeOrigin: false },
    },
  },
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
    coverage: { provider: "v8", reporter: ["text-summary"], include: ["src/**/*.ts"] },
  },
});
