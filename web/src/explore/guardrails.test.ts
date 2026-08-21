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

function sources(directory: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) found.push(...sources(path));
    else if (entry.name.endsWith(".ts") && !EXCLUDED.some((pattern) => pattern.test(path))) {
      found.push(path);
    }
  }
  return found;
}

function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
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
