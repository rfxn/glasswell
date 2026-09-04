import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, normalize } from "node:path";

import { describe, expect, it } from "vitest";

import { CLASS_B_DATASETS, CLASS_C_DATASETS } from "./rail.ts";

// Paths are relative to `web/`, which is vitest's cwd (the chrome/*.test.ts precedent).
const ENTRY = "src/main.ts";

// `import type` is erased before it reaches the bundler, so it is not an edge in this graph —
// which is what lets main.ts name MapHandle while the module stays out of the entry chunk.
// The body is `[^;]*?` and not `[\s\S]*?` because a statement terminator is the one character
// that cannot appear inside one: with the wider class a side-effect `import "x";` followed by
// an `import type ... from "y"` matched across both and reported `y` as a static edge. It did
// that here the moment the lineage drawer's import left main.ts and stopped sitting between
// the two, and reported src/map/map.ts as statically imported when nothing imports it.
const NAMED_IMPORT = /(?:^|\n)\s*(?:import|export)\s+(?!type\s)([^;]*?)\sfrom\s+["']([^"']+)["']/g;
const SIDE_EFFECT_IMPORT = /(?:^|\n)\s*import\s+["']([^"']+)["']/g;

function moduleEdges(source: string): string[] {
  const specifiers = [...source.matchAll(NAMED_IMPORT)].map((match) => match[2]);
  specifiers.push(...[...source.matchAll(SIDE_EFFECT_IMPORT)].map((match) => match[1]));
  return specifiers.filter((specifier): specifier is string => specifier !== undefined);
}

function resolveEdge(from: string, specifier: string): string | null {
  if (!specifier.startsWith(".")) return null;
  const target = normalize(join(dirname(from), specifier));
  return target.endsWith(".ts") && existsSync(target) ? target : null;
}

function staticGraph(entry: string): Set<string> {
  const seen = new Set([entry]);
  const queue = [entry];
  while (queue.length > 0) {
    const current = queue.shift() as string;
    for (const specifier of moduleEdges(readFileSync(current, "utf8"))) {
      const target = resolveEdge(current, specifier);
      if (target && !seen.has(target)) {
        seen.add(target);
        queue.push(target);
      }
    }
  }
  return seen;
}

describe("the explorer's code-split boundary is real (SB-08 §2.6 m7)", () => {
  it("keeps every map module out of the entry chunk's static import graph", () => {
    const graph = staticGraph(ENTRY);

    // A walk that reaches nothing would pass the assertion below by accident.
    expect(graph.size).toBeGreaterThan(15);
    expect(graph.has("src/app/state.ts")).toBe(true);
    expect(graph.has("src/map/map.ts")).toBe(false);
    expect([...graph].filter((module) => module.startsWith("src/map/"))).toEqual([]);
  });

  it("loads the map through a dynamic import, which is what moves it out of the entry chunk", () => {
    expect(readFileSync(ENTRY, "utf8")).toContain('import("./map/map.ts")');
  });
});

// SB-08 §2.3 M10: an ESLint rule with no ESLint in the tree is a rule nothing runs, so the
// invariant is a source scan in the job that already exists.
const EXCLUDED = [/\.test\.ts$/, /\/fixtures\.ts$/];

// The one deliberate exemption, held as an allowlist so it is countable: /openapi.json is not
// an envelope, and getEnvelope types it as one. Reopening the frozen client.ts for that would
// break C0's "from that commit forward SB-08 touches no frozen file".
const FETCH_ALLOWLIST = ["src/explore/shell.ts"];

function sources(directory: string, extensions: readonly string[] = [".ts"]): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) found.push(...sources(path, extensions));
    else if (
      extensions.some((extension) => entry.name.endsWith(extension)) &&
      !EXCLUDED.some((pattern) => pattern.test(path))
    ) {
      found.push(path);
    }
  }
  return found;
}

// CSS has no `//` comment, and stripping one there would eat the rest of a line that merely
// contains a URL.
function withoutComments(source: string, dialect: "ts" | "css" = "ts"): string {
  const blocks = source.replace(/\/\*[\s\S]*?\*\//g, "");
  return dialect === "css" ? blocks : blocks.replace(/(^|[^:])\/\/.*$/gm, "$1");
}

// C9 renders a `fetch` snippet for the reader to copy, and a snippet is text rather than a call
// site. Arms 1 and 2 therefore read the code with its strings taken out: a call cannot hide
// inside a literal, and a literal must not be able to trip a network-surface check. `LITERAL` is
// the tofu sweep's own quote-form regex, declared below and used here rather than restated.
function withoutLiterals(source: string): string {
  return withoutComments(source).replace(LITERAL, '""');
}

const EXPLORE = sources("src/explore").map((path) => ({ path, source: readFileSync(path, "utf8") }));
const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8")) as {
  paths: Record<string, Record<string, { operationId?: string }>>;
};

describe("the explorer's network surface is one call site (SB-08 §2.3 arms 1-3)", () => {
  it("scans the explorer's own source, and would notice if it stopped covering it", () => {
    expect(EXPLORE.length).toBeGreaterThan(3);
    expect(EXPLORE.map((file) => file.path)).toContain("src/explore/shell.ts");
    // §3: widening the exclusion list until the scan covers nothing is the failure mode.
    expect(EXCLUDED.map(String)).toEqual(["/\\.test\\.ts$/", "/\\/fixtures\\.ts$/"]);
  });

  it("calls fetch from exactly one file, and that file is the declared exemption", () => {
    const callers = EXPLORE.filter((file) => /\bfetch\(/.test(withoutLiterals(file.source))).map(
      (file) => file.path,
    );

    expect(FETCH_ALLOWLIST).toHaveLength(1);
    expect(callers).toEqual(FETCH_ALLOWLIST);
  });

  it("still sees a real call once the strings are out, and no longer sees a printed one", () => {
    expect(withoutLiterals("const answer = await fetch(url);")).toMatch(/\bfetch\(/);
    expect(withoutLiterals('const snippet = "await fetch(url)";')).not.toMatch(/\bfetch\(/);
  });

  it("never reaches for XMLHttpRequest anywhere", () => {
    for (const file of EXPLORE) {
      expect(withoutLiterals(file.source), file.path).not.toContain("XMLHttpRequest");
    }
  });

  it("classifies every operation it names against the committed document", () => {
    const servedPaths = new Set(Object.keys(SNAPSHOT.paths));
    const servedIds = new Set(
      Object.values(SNAPSHOT.paths).flatMap((item) =>
        Object.values(item).map((operation) => operation.operationId),
      ),
    );
    const gaps = new Set([...CLASS_B_DATASETS, ...CLASS_C_DATASETS].map((entry) => entry.path));
    const named = EXPLORE.flatMap((file) => [
      ...[...file.source.matchAll(/["'](\/v1\/[^"']*)["']/g)].map((match) => ({
        file: file.path,
        literal: match[1] as string,
        kind: "path" as const,
      })),
      ...[...file.source.matchAll(/operationId\s*:\s*["']([^"']+)["']/g)].map((match) => ({
        file: file.path,
        literal: match[1] as string,
        kind: "operationId" as const,
      })),
    ]);

    // A vacuity floor: an explorer that names no operation would pass the loop below. The
    // register supplies today's twenty; the operationId arm is the rule that catches a
    // hand-written call the moment C7 writes one.
    expect(named.length).toBeGreaterThan(20);
    for (const { file, literal, kind } of named) {
      const served = kind === "path" ? servedPaths.has(literal) : servedIds.has(literal);
      // Either the document serves it, or the honest-gap register says it does not exist —
      // and the day it starts existing, rail.test.ts reddens and the entry has to move.
      expect(served !== gaps.has(literal), `${file}: ${literal}`).toBe(true);
    }
  });

  it("writes no absolute URL, so the deployed origin is never baked into the bundle", () => {
    for (const file of EXPLORE) {
      expect(withoutComments(file.source), file.path).not.toMatch(/https?:\/\//);
    }
  });
});

/**
 * Arm 4 (SB-08 §2.3, §4.7). "No domain prose in the client" cannot be a length rule alone: the
 * explorer legitimately writes long sentences about its own surface — which column is off the
 * right edge, which tab lands in P-B. What it must never write is a sentence about the *data*,
 * because that sentence already exists as a glossary row and a second copy of it drifts.
 *
 * The vocabulary is therefore derived from the served document rather than listed here: every
 * word of every term the API binds through `x-glasswell-glossary`. A long literal that speaks
 * the glossary's own words is a glossary entry the client has re-authored.
 */
const DOMAIN_LEXICON = new Set(
  [
    ...new Set(
      [...readFileSync("../tests/contract/openapi_snapshot.json", "utf8").matchAll(
        /"x-glasswell-glossary":\s*"([^"]+)"/g,
      )].map((match) => match[1] as string),
    ),
  ].flatMap((term) => term.replace(/^gt_/, "").split("_").filter((word) => word.length >= 5)),
);

const PROSE_LIMIT = 120;

/** `${…}` is an expression, not prose, so it is neither counted nor read for vocabulary. */
function proseOf(literal: string): string {
  return literal.slice(1, -1).replace(/\$\{[^}]*\}/g, "");
}

/**
 * Whole comment lines only. `withoutComments` cuts at the first `//` on a line, which inside a
 * shell snippet — `jq -r '.a // empty'` — cuts a string literal in half and pairs its opening
 * quote with the next one, producing an "offender" spanning four lines of code.
 */
function withoutCommentLines(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !line.trimStart().startsWith("//"))
    .join("\n");
}

function domainProse(source: string): string[] {
  return [...withoutCommentLines(source).matchAll(LITERAL)]
    .map(([literal]) => proseOf(literal))
    .filter((prose) => prose.length > PROSE_LIMIT)
    .filter((prose) =>
      [...DOMAIN_LEXICON].some((word) => new RegExp(`\\b${word}s?\\b`, "i").test(prose)),
    );
}

describe("the explorer authors no domain prose of its own (SB-08 §2.3 arm 4)", () => {
  it("derives its vocabulary from the document, and finds a real one", () => {
    expect(DOMAIN_LEXICON.size).toBeGreaterThan(20);
    for (const word of ["vintage", "quarantine", "granularity", "manifest"]) {
      expect([...DOMAIN_LEXICON], word).toContain(word);
    }
  });

  it("can fail, and does not fire on a sentence about the surface itself", () => {
    const domain = `"A report vintage is the knowledge date the regulator published the figure on, and a restatement is a new one rather than an edit of the old."`;
    const surface = `"This collection cannot be narrowed by that filter here, so the control is stated as absent rather than rendered and quietly ignored on the wire."`;

    expect(proseOf(domain).length).toBeGreaterThan(PROSE_LIMIT);
    expect(proseOf(surface).length).toBeGreaterThan(PROSE_LIMIT);
    expect(domainProse(`const a = ${domain};`)).toHaveLength(1);
    expect(domainProse(`const b = ${surface};`)).toEqual([]);
  });

  it("scans the pane, and not the fixtures or the tests that quote the API back", () => {
    const scanned = EXPLORE.map((file) => file.path);

    expect(scanned).toContain("src/explore/api/pane.ts");
    expect(scanned).toContain("src/explore/api/semantics.ts");
    expect(scanned).not.toContain("src/explore/api/fixtures.ts");
    // §3: widening the exclusion list until the scan covers nothing is the failure mode, so the
    // list is asserted whole here as well as at arm 1.
    expect(EXCLUDED.map(String)).toEqual(["/\\.test\\.ts$/", "/\\/fixtures\\.ts$/"]);
  });

  it("finds none under explore/", () => {
    const offenders = EXPLORE.flatMap((file) =>
      domainProse(file.source).map((prose) => `${file.path}: ${prose.slice(0, 60)}…`),
    );

    expect(offenders).toEqual([]);
  });
});

// F5: `ⓔ` (U+24D4) shipped in none of the three self-hosted faces, and `style.css` pins GW
// Symbols to two codepoints — so the browser never attempted that face and the mark resolved to
// whatever the reader's system had, which is the outcome `style.css:22-23`'s own comment exists
// to prevent. A glyph this product renders is either in a declared range or it is tofu.
const RANGES = [...readFileSync("src/style.css", "utf8").matchAll(/unicode-range:\s*([^;]+);/g)]
  .flatMap((match) => (match[1] as string).split(","))
  .map((part) => part.trim().replace(/^U\+/i, "").split("-"))
  .map(([from, to]): [number, number] => [
    Number.parseInt(from as string, 16),
    Number.parseInt((to ?? from) as string, 16),
  ]);

// N2: rev 1 read double-quoted and template strings under `src/explore` only, so `'ⓔ'` passed
// it green and two out-of-range glyphs outside that root were live in the product. A guardrail
// against tofu is only worth its name over every quote form and every file that renders text.
const LITERAL = /"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`/g;
const RENDERED = sources("src", [".ts", ".css"]).map((path) => ({
  path,
  source: readFileSync(path, "utf8"),
}));

function literalsOf(path: string, source: string): string[] {
  const dialect = path.endsWith(".css") ? "css" : "ts";
  return [...withoutComments(source, dialect).matchAll(LITERAL)].map(([literal]) => literal);
}

function outOfRange(path: string, source: string): { point: number; character: string }[] {
  const found: { point: number; character: string }[] = [];
  for (const literal of literalsOf(path, source)) {
    for (const character of literal) {
      const point = character.codePointAt(0) as number;
      if (point < 0x80 || RANGES.some(([from, to]) => from <= point && point <= to)) continue;
      found.push({ point, character });
    }
  }
  return found;
}

describe("every glyph this product renders comes from a face it ships", () => {
  it("reads the declared ranges off style.css rather than assuming them", () => {
    expect(RANGES.length).toBeGreaterThan(5);
    expect(RANGES.some(([from, to]) => from <= 0x233e && 0x233e <= to)).toBe(true);
    // The offender this arm was written for, proving the check can actually fail.
    expect(RANGES.some(([from, to]) => from <= 0x24d4 && 0x24d4 <= to)).toBe(false);
  });

  it("reads every quote form, so single quotes are not a way through it", () => {
    const probe = [
      `const double = "ⓔ";`,
      `const single = 'ⓔ';`,
      "const template = `a",
      "ⓔ`;",
    ].join("\n");

    expect(outOfRange("probe.ts", probe).map((hit) => hit.point)).toEqual([0x24d4, 0x24d4, 0x24d4]);
  });

  it("walks every .ts and .css under src, not one directory of it", () => {
    const paths = RENDERED.map((file) => file.path);

    expect(paths).toContain("src/components/gw-count.ts");
    expect(paths).toContain("src/map.css");
    expect(paths).toContain("src/map/pills.ts");
    expect(paths.length).toBeGreaterThan(EXPLORE.length);
  });

  it("renders no character outside them", () => {
    // Every offender at once rather than the first one: a tofu sweep is worth running whole.
    const offenders = RENDERED.flatMap((file) =>
      outOfRange(file.path, file.source).map(
        (hit) =>
          `${file.path}: U+${hit.point.toString(16).toUpperCase()} (${hit.character}) is in no shipped face`,
      ),
    );

    expect(offenders).toEqual([]);
  });

  it("still meets the characters it is meant to clear, so a green run is not an empty walk", () => {
    const nonAscii = RENDERED.flatMap((file) =>
      literalsOf(file.path, file.source)
        .flatMap((literal) => [...literal])
        .filter((character) => (character.codePointAt(0) as number) >= 0x80),
    );

    // The em dash, the disclosure triangles, ⌾, ✕ and the cursor block's arrow, at least.
    expect(nonAscii.length).toBeGreaterThan(5);
  });
});
