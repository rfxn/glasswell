import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

import type { Plugin } from "vite";
import { beforeEach, describe, expect, it, vi } from "vitest";

import config, { changelogPage } from "../vite.config.ts";

vi.mock("node:child_process", () => ({ execFileSync: vi.fn(), execSync: vi.fn(() => "") }));

const build = (config as { build?: { sourcemap?: boolean | string } }).build ?? {};

/** What the plugin was handed when it wrote the page: `render-changelog.py --out <path>`. */
function renderedInto(root: string, outDir: string): string {
  const plugin = changelogPage();
  (plugin.configResolved as ((resolved: unknown) => void) | undefined)?.({
    root,
    build: { outDir },
  });
  (plugin.closeBundle as () => void).call(plugin);
  const calls = vi.mocked(execFileSync).mock.calls;
  const args = (calls[calls.length - 1]?.[1] ?? []) as string[];
  return args[args.indexOf("--out") + 1] ?? "";
}

describe("the production build", () => {
  beforeEach(() => {
    vi.mocked(execFileSync).mockClear();
  });

  it("ships no source map", () => {
    // M-6: the project is proprietary and the bundle is served by StaticFiles, so a deployed
    // .map publishes readable TypeScript to anyone who can reach the app.
    expect(build.sourcemap).toBe(false);
  });

  it("writes the changelog page inside the outDir the build resolved", () => {
    // A budget walk builds into its own directory. Writing web/dist/changelog regardless of
    // outDir touches the tree another agent may be serving, and leaves the walk's own bundle
    // without the page the rail links to.
    expect(renderedInto("/gw/web", "dist-budget-walk")).toBe(
      resolve("/gw/web", "dist-budget-walk", "changelog"),
    );
  });

  it("honours an outDir the caller already resolved to an absolute path", () => {
    expect(renderedInto("/gw/web", "/gw/elsewhere/dist")).toBe(
      resolve("/gw/elsewhere/dist", "changelog"),
    );
  });

  it("refuses to guess a directory when the build resolved none", () => {
    expect(() => (changelogPage().closeBundle as () => void)()).toThrow(/resolved no outDir/);
    expect(vi.mocked(execFileSync)).not.toHaveBeenCalled();
  });

  it("is still in the build it is tested through", () => {
    const plugins = ((config as { plugins?: Plugin[] }).plugins ?? []).flat(Infinity) as Plugin[];
    expect(plugins.map((plugin) => plugin?.name)).toContain("gw-changelog-page");
  });
});
