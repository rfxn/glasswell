import { describe, expect, it } from "vitest";

import { literalsIn, unescapeLiteral } from "./literals.ts";

/**
 * The corpus gates read shipped text. An escape is a spelling of a character, so a scanner
 * that reads `\u2014` as the four letters `u2014` cannot see the em dash the reader sees —
 * and an escaped spelling is the one form a reviewer's eye does not catch either.
 */
describe("a literal is read as the engine reads it", () => {
  it("decodes the escapes that spell a character", () => {
    expect(unescapeLiteral("a \\u2014 b")).toBe("a \u2014 b");
    expect(unescapeLiteral("\\u{1F600}")).toBe("\u{1F600}");
    expect(unescapeLiteral("\\x41")).toBe("A");
  });

  it("decodes the escapes that spell a control character, rather than dropping the backslash", () => {
    expect(unescapeLiteral("a\\nb")).toBe("a\nb");
    expect(unescapeLiteral("a\\tb")).toBe("a\tb");
  });

  it("keeps a quote, a backslash and an unknown escape as the engine keeps them", () => {
    expect(unescapeLiteral('a \\" b')).toBe('a " b');
    expect(unescapeLiteral("a \\\\u2014 b")).toBe("a \\u2014 b");
    expect(unescapeLiteral("a \\q b")).toBe("a q b");
  });

  it("reads a css code point, because the tofu gate walks stylesheets too", () => {
    expect(unescapeLiteral("\\2014", "css")).toBe("\u2014");
    expect(unescapeLiteral("\\2014 x", "css")).toBe("\u2014x");
  });

  it("hands the corpus the character a shipped literal spells, not its escape", () => {
    const source = 'const label = "an \\u2014 escaped em dash";\n';

    expect(literalsIn("probe.ts", source).map((one) => one.value)).toEqual([
      "an \u2014 escaped em dash",
    ]);
  });
});
