import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  ABSOLUTE_META_PROPERTIES,
  absoluteMetaUrl,
  absolutizeMetaUrls,
  normalizeOrigin,
} from "./og-url.ts";

const ORIGIN = "https://example.test";
const INDEX = readFileSync("index.html", "utf8");

describe("a card URL is derived from configuration, never from a literal", () => {
  it("makes a root-relative path absolute against the configured origin", () => {
    expect(absoluteMetaUrl("/og-card.png", ORIGIN)).toBe(`${ORIGIN}/og-card.png`);
  });

  it("leaves the path relative when no origin is configured, rather than guessing one", () => {
    // The LAN deployment. A relative URL is useless to an unfurler; a guessed absolute one
    // points at a host that is not this deployment, which is worse.
    for (const unset of [undefined, null, "", "   "]) {
      expect(absoluteMetaUrl("/og-card.png", unset)).toBe("/og-card.png");
    }
  });

  it("treats a malformed or non-http origin as unset", () => {
    for (const bad of ["glasswell", "file:///tmp", "javascript:alert(1)", "//host"]) {
      expect(normalizeOrigin(bad)).toBeNull();
      expect(absoluteMetaUrl("/og-card.png", bad)).toBe("/og-card.png");
    }
  });

  it("strips a path and a trailing slash from the configured origin", () => {
    expect(absoluteMetaUrl("/og-card.png", `${ORIGIN}/`)).toBe(`${ORIGIN}/og-card.png`);
    expect(absoluteMetaUrl("/og-card.png", `${ORIGIN}/sub/page`)).toBe(`${ORIGIN}/og-card.png`);
  });

  it("leaves an already-absolute URL exactly as authored", () => {
    expect(absoluteMetaUrl("https://cdn.test/card.png", ORIGIN)).toBe("https://cdn.test/card.png");
  });
});

describe("the html rewrite touches the card properties and nothing else", () => {
  const DOCUMENT = [
    '<meta property="og:image" content="/og-card.png" />',
    '<meta name="twitter:image" content="/og-card.png">',
    '<meta property="og:title" content="/not-a-url" />',
    '<link rel="icon" href="/favicon-32.png" />',
  ].join("\n");

  it("rewrites og:image and twitter:image, and leaves the rest alone", () => {
    const out = absolutizeMetaUrls(DOCUMENT, ORIGIN);

    expect(out).toContain(`<meta property="og:image" content="${ORIGIN}/og-card.png" />`);
    expect(out).toContain(`<meta name="twitter:image" content="${ORIGIN}/og-card.png">`);
    expect(out).toContain('<meta property="og:title" content="/not-a-url" />');
    expect(out).toContain('<link rel="icon" href="/favicon-32.png" />');
  });

  it("returns the document unchanged when no origin is configured", () => {
    expect(absolutizeMetaUrls(DOCUMENT, undefined)).toBe(DOCUMENT);
  });

  it("passes a document with no card tags through untouched", () => {
    expect(absolutizeMetaUrls("<head></head>", ORIGIN)).toBe("<head></head>");
  });
});

/** Every og:image / twitter:image `content` value in a document, in source order. */
function cardUrls(html: string): string[] {
  return [...html.matchAll(/<meta\b[^>]*>/gi)]
    .filter((match) => {
      const property = /\b(?:property|name)\s*=\s*["']([^"']+)["']/i.exec(match[0])?.[1];
      return property !== undefined
        ? (ABSOLUTE_META_PROPERTIES as readonly string[]).includes(property)
        : false;
    })
    .map((match) => /\bcontent\s*=\s*["']([^"']*)["']/i.exec(match[0])?.[1] ?? "");
}

/**
 * Vacuous today: this branch carries no og:image or twitter:image tag. Every assertion here
 * becomes load-bearing the moment track T4's card tags land, which is the point — the guard
 * is in place before the markup it guards, so a card URL that cannot unfurl fails here.
 *
 * The absolute check runs index.html through the build's own transform rather than reading
 * the authored value. A source-level "must be absolute" would be unsatisfiable: the origin is
 * deployment configuration, so the authored value has to stay root-relative.
 */
describe("index.html's card URLs are absolute by the time they ship", () => {
  it("makes every card URL absolute once an origin is configured", () => {
    for (const value of cardUrls(absolutizeMetaUrls(INDEX, ORIGIN))) {
      expect(value, value).toMatch(/^https?:\/\//);
    }
  });

  it("leaves them root-relative with no origin, which is the LAN deployment", () => {
    for (const value of cardUrls(absolutizeMetaUrls(INDEX, undefined))) {
      expect(value, value).not.toMatch(/^https?:\/\//);
    }
  });

  it("authors them root-relative, which is what leaves the origin to configuration", () => {
    for (const value of cardUrls(INDEX)) expect(value, value).toMatch(/^\//);
  });

  it("hardcodes no deployment hostname anywhere in the shipped markup", () => {
    expect(INDEX).not.toMatch(/rpx\.sh/);
  });
});
