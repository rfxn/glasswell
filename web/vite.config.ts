import { execSync } from "node:child_process";

import { defineConfig } from "vitest/config";

/**
 * The rail has to be able to say which bundle it is, and a version it fetches is one it
 * cannot show while the API is down. Read once, here, and inlined as a constant: `dev` when
 * there is no git to ask (a release archive is not a checkout), and a trailing `+` when the
 * tree had uncommitted changes, because a stamp that rounds to the commit is a lie.
 */
function stamp(): { hash: string; date: string } {
  const git = (args: string): string =>
    execSync(`git ${args}`, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  let hash = "dev";
  try {
    hash = `${git("rev-parse --short HEAD")}${git("status --porcelain") === "" ? "" : "+"}`;
  } catch {
    // Not a checkout, or no git on the build host: the initialiser above is the honest answer.
  }
  return { hash, date: new Date().toISOString().slice(0, 10) };
}

// Tiles moved under /v1 (C11), so one proxy rule covers the API and the tile origin.
export default defineConfig({
  base: "/",
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
