import { describe, expect, it } from "vitest";

import config from "../vite.config.ts";

const build = (config as { build?: { sourcemap?: boolean | string } }).build ?? {};

describe("the production build", () => {
  it("ships no source map", () => {
    // M-6: the project is proprietary and the bundle is served by StaticFiles, so a deployed
    // .map publishes readable TypeScript to anyone who can reach the app.
    expect(build.sourcemap).toBe(false);
  });
});
