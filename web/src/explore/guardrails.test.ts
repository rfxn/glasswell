import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, normalize } from "node:path";

import { describe, expect, it } from "vitest";

import { CLASS_B_DATASETS, CLASS_C_DATASETS } from "./rail.ts";

// Paths are relative to `web/`, which is vitest's cwd (the chrome/*.test.ts precedent).
const ENTRY = "src/main.ts";

// `import type` is erased before it reaches the bundler, so it is not an edge in this graph —
// which is what lets main.ts name MapHandle while the module stays out of the entry chunk.
const NAMED_IMPORT = /(?:^|\n)\s*(?:import|export)\s+(?!type\s)([\s\S]*?)\sfrom\s+["']([^"']+)["']/g;
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
    const callers = EXPLORE.filter((file) => /\bfetch\(/.test(file.source)).map((file) => file.path);

    expect(FETCH_ALLOWLIST).toHaveLength(1);
    expect(callers).toEqual(FETCH_ALLOWLIST);
  });

  it("never reaches for XMLHttpRequest anywhere", () => {
    for (const file of EXPLORE) expect(file.source, file.path).not.toContain("XMLHttpRequest");
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
    // register supplies today's twenty-two; the operationId arm is the rule that catches a
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

    expect(paths).toContain("src/explore/gw-count.ts");
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
