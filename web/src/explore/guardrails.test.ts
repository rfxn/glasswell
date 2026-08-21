import { existsSync, readFileSync } from "node:fs";
import { dirname, join, normalize } from "node:path";

import { describe, expect, it } from "vitest";

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
