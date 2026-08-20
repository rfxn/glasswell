import { existsSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// vitest roots at web/, so these are the shipped files, not a fixture of them.
const CSS = readFileSync("src/style.css", "utf8");
const FACES = [...CSS.matchAll(/@font-face\s*\{([^}]*)\}/g)].map((match) => match[1]);
const SOURCES = [...CSS.matchAll(/url\(["']?([^"')]+)["']?\)/g)].map((match) => match[1]);

describe("the brand faces are self-hosted", () => {
  it("declares at least one face, or the tokens below are decoration", () => {
    expect(FACES.length).toBeGreaterThan(0);
  });

  it("never reaches a font CDN", () => {
    // Access sits in front of every path; a gstatic request would publish a page view to an
    // origin the reader never agreed to, and it would survive the tunnel being down.
    expect(CSS).not.toMatch(/@import/);
    expect(CSS).not.toMatch(/fonts\.(googleapis|gstatic)\.com|use\.typekit|cdn\.jsdelivr/);
  });

  it("loads every face from a root-relative path under /fonts/", () => {
    expect(SOURCES.length).toBeGreaterThan(0);
    for (const source of SOURCES) expect(source).toMatch(/^\/fonts\/[\w.-]+\.woff2$/);
  });

  it("ships every file it references", () => {
    for (const source of SOURCES) expect(existsSync(`public${source}`), source).toBe(true);
  });

  it("gives every face a font-display, so a cold cache cannot blank the chrome", () => {
    for (const face of FACES) expect(face).toMatch(/font-display:/);
  });

  it("covers U+233E, the explain glyph, from a declared face rather than a fallback", () => {
    // Inter has no ⌾. Without a face carrying it, every figure's affordance renders in
    // whatever the reader's system supplies — which is the VF-4 defect, one glyph at a time.
    const symbols = FACES.filter((face) => /unicode-range:[^;]*233E/i.test(face));
    expect(symbols.length).toBeGreaterThan(0);
  });
});

describe("the type tokens are the single source of truth", () => {
  const root = /:root\s*\{([\s\S]*?)\n\}/.exec(CSS)?.[1] ?? "";

  it.each(["--gw-font-display", "--gw-font-body", "--gw-font-mono"])("declares %s in :root", (token) => {
    expect(root).toContain(`${token}:`);
  });

  it("names a declared family first in every token, then a system fallback", () => {
    for (const token of ["--gw-font-display", "--gw-font-body", "--gw-font-mono"]) {
      const value = new RegExp(`${token}:([^;]+);`).exec(root)?.[1] ?? "";
      const first = value.trim().split(",")[0].replace(/["']/g, "").trim();

      expect(FACES.some((face) => face.includes(`"${first}"`)), `${token} → ${first}`).toBe(true);
      expect(value.split(",").length, `${token} has no fallback`).toBeGreaterThan(1);
    }
  });
});
